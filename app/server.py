"""
Flask API 서버
로그 데이터 조회, 필터링, 검색 API 제공
"""

import os
import sys
import time
import sqlite3
import threading
from flask import Flask, jsonify, request, render_template, send_from_directory
from parser import get_db_path, init_db, parse_log_file, delete_parsed_file, reset_db

# 파싱 상태 (전역)
parse_state = {
    'active': False,
    'progress': 0,
    'filename': '',
    'error': None,
    'result': None,
}

# 브라우저 heartbeat 추적
_last_heartbeat = time.time()
_HEARTBEAT_TIMEOUT = 10  # 10초간 heartbeat 없으면 종료


def get_db():
    """SQLite 연결 (dict row factory)"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_app():
    import sys
    if getattr(sys, 'frozen', False):
        base_dir = os.path.join(sys._MEIPASS, 'app')
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static'),
    )

    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({'error': '파일이 너무 큽니다 (최대 2GB)'}), 413

    init_db()

    @app.route('/')
    def index():
        return render_template('index.html')

    # ─── 파일 관리 ────────────────────────────────────

    @app.route('/api/files', methods=['GET'])
    def list_files():
        conn = get_db()
        rows = conn.execute(
            'SELECT id, filename, file_size, parsed_at, entry_count FROM parsed_files ORDER BY filename'
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/files/<int:file_id>', methods=['DELETE'])
    def remove_file(file_id):
        conn = get_db()
        row = conn.execute('SELECT filename FROM parsed_files WHERE id = ?', (file_id,)).fetchone()
        conn.close()
        if row:
            delete_parsed_file(row['filename'])
            return jsonify({'ok': True})
        return jsonify({'error': 'not found'}), 404

    @app.route('/api/reset', methods=['POST'])
    def reset_all():
        reset_db()
        return jsonify({'ok': True})

    # ─── 파싱 ─────────────────────────────────────────

    @app.route('/api/upload', methods=['POST'])
    def upload_and_parse():
        """파일 업로드 → 임시 저장 → 파싱"""
        import tempfile

        if parse_state['active']:
            return jsonify({'error': '이미 파싱 중입니다'}), 409

        files = request.files.getlist('files')
        if not files:
            return jsonify({'error': '파일이 없습니다'}), 400

        # 업로드된 파일들을 임시 디렉토리에 저장
        temp_dir = tempfile.mkdtemp(prefix='sl_log_upload_')
        saved = []
        for f in files:
            filename = f.filename
            filepath = os.path.join(temp_dir, filename)
            f.save(filepath)
            saved.append({'filename': filename, 'filepath': filepath})

        def run_parse_all():
            parse_state['active'] = True
            parse_state['error'] = None
            parse_state['result'] = None
            total_count = 0

            try:
                for i, item in enumerate(saved):
                    parse_state['filename'] = item['filename']
                    parse_state['progress'] = 0

                    count = parse_log_file(
                        item['filepath'],
                        progress_callback=lambda p: parse_state.update({
                            'progress': p
                        })
                    )
                    if count > 0:
                        total_count += count

                    # 파싱 완료 후 임시 파일 삭제
                    try:
                        os.remove(item['filepath'])
                    except OSError:
                        pass

                parse_state['result'] = total_count
            except Exception as e:
                parse_state['error'] = str(e)
            finally:
                parse_state['active'] = False
                parse_state['progress'] = 100
                # 임시 디렉토리 정리
                try:
                    os.rmdir(temp_dir)
                except OSError:
                    pass

        thread = threading.Thread(target=run_parse_all, daemon=True)
        thread.start()
        return jsonify({'ok': True, 'count': len(saved)})

    @app.route('/api/parse/progress', methods=['GET'])
    def parse_progress():
        return jsonify(parse_state)

    # ─── 로그 조회 ────────────────────────────────────

    @app.route('/api/logs', methods=['GET'])
    def list_logs():
        # 필터 파라미터
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        offset = (page - 1) * per_page

        method = request.args.get('method', '')
        endpoint = request.args.get('endpoint', '')
        status = request.args.get('status', '')
        ip = request.args.get('ip', '')
        source_file = request.args.get('source_file', '')
        time_from = request.args.get('time_from', '')
        time_to = request.args.get('time_to', '')
        search = request.args.get('search', '')
        errors_only = request.args.get('errors_only', '') == '1'
        hide_noise = request.args.get('hide_noise', '') == '1'

        where = []
        params = []

        if method:
            methods = [m.strip() for m in method.split(',') if m.strip()]
            if methods:
                where.append(f'method IN ({",".join("?" * len(methods))})')
                params.extend(methods)
        if endpoint:
            where.append('endpoint = ?')
            params.append(endpoint)
        if status:
            codes = [int(c.strip()) for c in status.split(',') if c.strip().isdigit()]
            if codes:
                where.append(f'res_status_code IN ({",".join("?" * len(codes))})')
                params.extend(codes)
        if ip:
            where.append('ip = ?')
            params.append(ip)
        if source_file:
            where.append('source_file = ?')
            params.append(source_file)
        def normalize_time(t):
            t = t.strip().replace(':', '')
            if len(t) == 4 and t.isdigit():
                return f'{t[:2]}:{t[2:]}'
            if len(t) == 2 and t.isdigit():
                return f'{t}:00'
            return t.strip()

        if time_from:
            tf = normalize_time(time_from)
            where.append("substr(timestamp, 12, 8) >= ?")
            params.append(tf + ':00' if len(tf) == 5 else tf)
        if time_to:
            tt = normalize_time(time_to)
            where.append("substr(timestamp, 12, 8) <= ?")
            params.append(tt + ':59' if len(tt) == 5 else tt)
        if search:
            where.append('(req_body LIKE ? OR res_body LIKE ? OR url LIKE ? OR error_message LIKE ?)')
            s = f'%{search}%'
            params.extend([s, s, s, s])
        if errors_only:
            where.append('res_status_code >= 400')
        if hide_noise:
            where.append("endpoint NOT IN ('/b1s/v1/Login', '/b1s/v1/Logout', '/b1s/v1/AlertService_RunAlert')")
            where.append("endpoint NOT LIKE '%/ssob1s%'")
            where.append("endpoint NOT LIKE '%balancer%'")

        where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''

        conn = get_db()

        # 총 건수
        count_sql = f'SELECT COUNT(*) as cnt FROM log_pairs {where_clause}'
        total = conn.execute(count_sql, params).fetchone()['cnt']

        # 데이터 조회 (바디 제외 - 목록에서는 불필요)
        data_sql = f'''
            SELECT id, timestamp, timestamp_raw, ip, pid, method, url, endpoint,
                   res_status_code, res_status_text, error_code, error_message, duration_ms, source_file
            FROM log_pairs
            {where_clause}
            ORDER BY timestamp ASC, id ASC
            LIMIT ? OFFSET ?
        '''
        rows = conn.execute(data_sql, params + [per_page, offset]).fetchall()
        conn.close()

        return jsonify({
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page if per_page else 0,
            'items': [dict(r) for r in rows],
        })

    @app.route('/api/logs/<int:log_id>', methods=['GET'])
    def get_log_detail(log_id):
        conn = get_db()
        row = conn.execute('SELECT * FROM log_pairs WHERE id = ?', (log_id,)).fetchone()
        conn.close()
        if row:
            return jsonify(dict(row))
        return jsonify({'error': 'not found'}), 404

    # ─── 필터 옵션 ────────────────────────────────────

    @app.route('/api/filters', methods=['GET'])
    def get_filters():
        conn = get_db()
        endpoints = [r[0] for r in conn.execute(
            'SELECT DISTINCT endpoint FROM log_pairs ORDER BY endpoint'
        ).fetchall()]
        methods = [r[0] for r in conn.execute(
            'SELECT DISTINCT method FROM log_pairs ORDER BY method'
        ).fetchall()]
        ips = [r[0] for r in conn.execute(
            'SELECT DISTINCT ip FROM log_pairs ORDER BY ip'
        ).fetchall()]
        status_codes = [r[0] for r in conn.execute(
            'SELECT DISTINCT res_status_code FROM log_pairs WHERE res_status_code IS NOT NULL ORDER BY res_status_code'
        ).fetchall()]
        files = [r[0] for r in conn.execute(
            'SELECT DISTINCT source_file FROM log_pairs ORDER BY source_file'
        ).fetchall()]
        conn.close()

        return jsonify({
            'endpoints': endpoints,
            'methods': methods,
            'ips': ips,
            'status_codes': status_codes,
            'files': files,
        })

    # ─── 통계 ─────────────────────────────────────────

    @app.route('/api/stats', methods=['GET'])
    def get_stats():
        conn = get_db()
        total = conn.execute('SELECT COUNT(*) FROM log_pairs').fetchone()[0]
        errors = conn.execute('SELECT COUNT(*) FROM log_pairs WHERE res_status_code >= 400').fetchone()[0]
        success = conn.execute('SELECT COUNT(*) FROM log_pairs WHERE res_status_code < 400 AND res_status_code IS NOT NULL').fetchone()[0]
        no_response = conn.execute('SELECT COUNT(*) FROM log_pairs WHERE res_status_code IS NULL').fetchone()[0]

        # 엔드포인트별 에러 Top 5
        top_errors = [dict(r) for r in conn.execute('''
            SELECT endpoint, COUNT(*) as cnt
            FROM log_pairs WHERE res_status_code >= 400
            GROUP BY endpoint ORDER BY cnt DESC LIMIT 5
        ''').fetchall()]

        # 시간대별 요청 분포
        hourly = [dict(r) for r in conn.execute('''
            SELECT substr(timestamp, 12, 2) as hour, COUNT(*) as cnt
            FROM log_pairs
            GROUP BY hour ORDER BY hour
        ''').fetchall()]

        conn.close()
        return jsonify({
            'total': total,
            'success': success,
            'errors': errors,
            'no_response': no_response,
            'top_errors': top_errors,
            'hourly': hourly,
        })

    @app.route('/api/shutdown', methods=['POST'])
    def shutdown():
        os._exit(0)

    @app.route('/api/heartbeat', methods=['POST'])
    def heartbeat():
        global _last_heartbeat
        _last_heartbeat = time.time()
        return jsonify({'ok': True})

    # 브라우저 탭 닫힘 감지 (exe 실행 시에만)
    if getattr(sys, 'frozen', False):
        def watchdog():
            global _last_heartbeat
            while True:
                time.sleep(3)
                if time.time() - _last_heartbeat > _HEARTBEAT_TIMEOUT:
                    os._exit(0)

        watchdog_thread = threading.Thread(target=watchdog, daemon=True)
        watchdog_thread.start()

    return app
