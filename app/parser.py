"""
SAP B1 ServiceLayer HTTP Dump Log Parser
로그 파일을 파싱하여 SQLite DB에 Request/Response 쌍으로 저장
"""

import re
import os
import sqlite3
import json
import tempfile
import atexit
from datetime import datetime
from collections import deque

# 엔트리 헤더 정규식
ENTRY_HEADER_RE = re.compile(
    r'\[(.+?)\]\s+\[(\d+\.\d+\.\d+\.\d+|[\d.]+)\]\s+\[pid=(\d+)\]\s+'
    r'\[(Request|Response)\]\s+"(\w+)\s+(.+?)\s+HTTP/[\d.]+"'
)

# 상태 코드 정규식
STATUS_CODE_RE = re.compile(r'Status Code:\[(\d+)\s+(.*?)\]')

# URL 키 정규화 정규식
KEY_NUMERIC_RE = re.compile(r'\(\d+\)')
KEY_STRING_RE = re.compile(r"\('.*?'\)")

# DB 경로 - 임시 파일 (앱 종료 시 자동 삭제)
_temp_db = tempfile.NamedTemporaryFile(suffix='.db', prefix='sl_log_', delete=False)
_temp_db.close()
DB_PATH = _temp_db.name

def _cleanup_db():
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        # WAL/SHM 파일도 정리
        for ext in ('-wal', '-shm'):
            p = DB_PATH + ext
            if os.path.exists(p):
                os.remove(p)
    except OSError:
        pass

atexit.register(_cleanup_db)


def get_db_path():
    return DB_PATH


def init_db(db_path=None):
    """데이터베이스 테이블 생성"""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS log_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            timestamp_raw TEXT,
            ip TEXT,
            pid INTEGER,
            method TEXT,
            url TEXT,
            endpoint TEXT,
            req_headers TEXT,
            req_body TEXT,
            res_timestamp TEXT,
            res_status_code INTEGER,
            res_status_text TEXT,
            res_headers TEXT,
            res_body TEXT,
            error_code TEXT,
            error_message TEXT,
            duration_ms INTEGER,
            source_file TEXT
        );

        CREATE TABLE IF NOT EXISTS parsed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            file_size INTEGER,
            parsed_at TEXT,
            entry_count INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_timestamp ON log_pairs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_endpoint ON log_pairs(endpoint);
        CREATE INDEX IF NOT EXISTS idx_method ON log_pairs(method);
        CREATE INDEX IF NOT EXISTS idx_status ON log_pairs(res_status_code);
        CREATE INDEX IF NOT EXISTS idx_ip ON log_pairs(ip);
        CREATE INDEX IF NOT EXISTS idx_error ON log_pairs(error_code);
        CREATE INDEX IF NOT EXISTS idx_source ON log_pairs(source_file);
    ''')
    conn.commit()
    conn.close()


def parse_timestamp(ts_str):
    """'Sat Apr 11 00:00:04 2026' -> ISO format"""
    try:
        dt = datetime.strptime(ts_str.strip(), '%a %b %d %H:%M:%S %Y')
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return ts_str


def parse_timestamp_dt(ts_str):
    """'Sat Apr 11 00:00:04 2026' -> datetime object or None"""
    try:
        return datetime.strptime(ts_str.strip(), '%a %b %d %H:%M:%S %Y')
    except ValueError:
        return None


def normalize_endpoint(url):
    """URL 정규화: 키값 제거, 쿼리 제거, 이중슬래시 정리"""
    url = url.split('?')[0]
    url = url.replace('//b1s/', '/b1s/')
    # 복합 파라미터 (key='val',key='val') -> (PARAMS)
    url = re.sub(r"\([^)]*='[^)]*\)", '(PARAMS)', url)
    url = KEY_NUMERIC_RE.sub('(KEY)', url)
    url = KEY_STRING_RE.sub('(KEY)', url)
    return url


def extract_error_info(body):
    """에러 응답 body에서 code, message 추출"""
    try:
        data = json.loads(body)
        error = data.get('error', {})
        code = error.get('code', '')
        message = error.get('message', '')
        if isinstance(message, dict):
            message = message.get('value', '')
        return str(code), str(message)
    except (json.JSONDecodeError, AttributeError):
        return '', ''


def is_file_parsed(filename, db_path=None):
    """파일이 이미 파싱되었는지 확인"""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.execute('SELECT id FROM parsed_files WHERE filename = ?', (filename,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def parse_log_file(filepath, db_path=None, progress_callback=None):
    """
    로그 파일을 파싱하여 SQLite에 저장

    Args:
        filepath: 로그 파일 경로
        db_path: SQLite DB 경로 (None이면 기본 경로)
        progress_callback: 진행률 콜백 함수 (0~100)

    Returns:
        파싱된 쌍 수
    """
    if db_path is None:
        db_path = get_db_path()

    init_db(db_path)

    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)

    # 이미 파싱된 파일 확인
    if is_file_parsed(filename, db_path):
        if progress_callback:
            progress_callback(100)
        return -1  # 이미 파싱됨

    # 1단계: 파일 읽으며 엔트리 추출 + 즉시 매칭
    pending_requests = {}  # pid -> deque of request data
    pairs = []
    batch_size = 200
    total_inserted = 0

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")

    current_entry = None
    current_section = None
    bytes_read = 0
    last_progress = -1

    def finalize_entry(entry):
        """엔트리 완료 시 처리"""
        if entry is None:
            return

        body = '\n'.join(entry.get('body_lines', []))
        headers = '\n'.join(entry.get('headers', []))

        if entry['type'] == 'Request':
            req_data = {
                'timestamp': entry['timestamp'],
                'timestamp_raw': entry['timestamp_raw'],
                'ip': entry['ip'],
                'pid': entry['pid'],
                'method': entry['method'],
                'url': entry['url'],
                'headers': headers,
                'body': body,
            }
            pending_requests.setdefault(entry['pid'], deque()).append(req_data)

        elif entry['type'] == 'Response':
            pid = entry['pid']
            queue = pending_requests.get(pid, deque())

            matched_req = None
            res_url_norm = entry['url'].replace('//', '/')

            # 같은 PID에서 method + URL 매칭
            for i, req in enumerate(queue):
                req_url_norm = req['url'].replace('//', '/')
                if req['method'] == entry['method'] and req_url_norm == res_url_norm:
                    matched_req = queue[i]
                    del queue[i]
                    break

            # 매칭 실패 시 가장 오래된 요청 사용
            if matched_req is None and queue:
                matched_req = queue.popleft()

            if matched_req:
                error_code, error_message = '', ''
                status_code = entry.get('status_code', 0)
                if status_code and status_code >= 400:
                    error_code, error_message = extract_error_info(body)

                # 응답 시간 계산
                duration_ms = None
                req_dt = parse_timestamp_dt(matched_req['timestamp_raw'])
                res_dt = parse_timestamp_dt(entry.get('timestamp_raw', ''))
                if req_dt and res_dt:
                    delta = (res_dt - req_dt).total_seconds()
                    if 0 <= delta < 3600:
                        duration_ms = int(delta * 1000)

                pairs.append({
                    'timestamp': matched_req['timestamp'],
                    'timestamp_raw': matched_req['timestamp_raw'],
                    'ip': matched_req['ip'],
                    'pid': matched_req['pid'],
                    'method': matched_req['method'],
                    'url': matched_req['url'],
                    'endpoint': normalize_endpoint(matched_req['url']),
                    'req_headers': matched_req['headers'],
                    'req_body': matched_req['body'],
                    'res_timestamp': entry.get('timestamp', ''),
                    'res_status_code': status_code,
                    'res_status_text': entry.get('status_text', ''),
                    'res_headers': headers,
                    'res_body': body,
                    'error_code': error_code,
                    'error_message': error_message,
                    'duration_ms': duration_ms,
                    'source_file': filename,
                })

    def flush_pairs():
        """배치 삽입"""
        nonlocal pairs, total_inserted
        if not pairs:
            return
        conn.executemany('''
            INSERT INTO log_pairs (
                timestamp, timestamp_raw, ip, pid, method, url, endpoint,
                req_headers, req_body, res_timestamp,
                res_status_code, res_status_text, res_headers, res_body,
                error_code, error_message, duration_ms, source_file
            ) VALUES (
                :timestamp, :timestamp_raw, :ip, :pid, :method, :url, :endpoint,
                :req_headers, :req_body, :res_timestamp,
                :res_status_code, :res_status_text, :res_headers, :res_body,
                :error_code, :error_message, :duration_ms, :source_file
            )
        ''', pairs)
        total_inserted += len(pairs)
        pairs = []

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            bytes_read += len(line.encode('utf-8', errors='replace'))

            # 진행률 보고
            if progress_callback and file_size > 0:
                progress = min(int(bytes_read * 95 / file_size), 95)
                if progress > last_progress:
                    last_progress = progress
                    progress_callback(progress)

            line_stripped = line.rstrip('\r\n')

            # 엔트리 헤더 매칭
            match = ENTRY_HEADER_RE.match(line_stripped)
            if match:
                finalize_entry(current_entry)

                if len(pairs) >= batch_size:
                    flush_pairs()

                ts_raw, ip, pid, entry_type, method, url = match.groups()
                current_entry = {
                    'timestamp_raw': ts_raw,
                    'timestamp': parse_timestamp(ts_raw),
                    'ip': ip,
                    'pid': int(pid),
                    'type': entry_type,
                    'method': method,
                    'url': url,
                    'headers': [],
                    'body_lines': [],
                    'status_code': None,
                    'status_text': '',
                }
                current_section = 'headers'
                continue

            if current_entry is None:
                continue

            # Status Code 라인
            if line_stripped.startswith('Status Code:'):
                sc_match = STATUS_CODE_RE.match(line_stripped)
                if sc_match:
                    current_entry['status_code'] = int(sc_match.group(1))
                    current_entry['status_text'] = sc_match.group(2)
                continue

            # 빈 줄 = 헤더→바디 전환
            if line_stripped == '':
                if current_section == 'headers' and current_entry.get('headers'):
                    current_section = 'body'
                continue

            # 헤더 또는 바디에 추가
            if current_section == 'headers':
                current_entry['headers'].append(line_stripped)
            elif current_section == 'body':
                current_entry['body_lines'].append(line_stripped)

    # 마지막 엔트리 처리
    finalize_entry(current_entry)

    # 미매칭 Request도 저장 (Response가 없는 경우)
    for pid, queue in pending_requests.items():
        for req in queue:
            pairs.append({
                'timestamp': req['timestamp'],
                'timestamp_raw': req['timestamp_raw'],
                'ip': req['ip'],
                'pid': req['pid'],
                'method': req['method'],
                'url': req['url'],
                'endpoint': normalize_endpoint(req['url']),
                'req_headers': req['headers'],
                'req_body': req['body'],
                'res_timestamp': '',
                'res_status_code': None,
                'res_status_text': '',
                'res_headers': '',
                'res_body': '',
                'error_code': '',
                'error_message': '',
                'duration_ms': None,
                'source_file': filename,
            })

    flush_pairs()

    # 파싱 완료 기록
    conn.execute('''
        INSERT INTO parsed_files (filename, file_size, parsed_at, entry_count)
        VALUES (?, ?, ?, ?)
    ''', (filename, file_size, datetime.now().isoformat(), total_inserted))

    conn.commit()
    conn.close()

    if progress_callback:
        progress_callback(100)

    return total_inserted


def delete_parsed_file(filename, db_path=None):
    """파싱된 파일 데이터 삭제"""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute('DELETE FROM log_pairs WHERE source_file = ?', (filename,))
    conn.execute('DELETE FROM parsed_files WHERE filename = ?', (filename,))
    conn.commit()
    conn.close()


def reset_db(db_path=None):
    """전체 DB 초기화"""
    if db_path is None:
        db_path = get_db_path()
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db(db_path)
