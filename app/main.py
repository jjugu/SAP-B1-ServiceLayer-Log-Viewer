"""
SAP B1 ServiceLayer Log Viewer - Entry Point
브라우저 자동 실행 + Flask 서버
"""

import sys
import os
import threading
import socket
import webbrowser
import time

# 패키징 시 경로 처리
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    os.chdir(BASE_DIR)
    sys.path.insert(0, os.path.join(sys._MEIPASS, 'app'))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, BASE_DIR)

from server import create_app


def find_free_port():
    """사용 가능한 포트 찾기"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    port = find_free_port()
    app = create_app()
    url = f'http://127.0.0.1:{port}'

    # Flask 서버 시작 (백그라운드)
    server_thread = threading.Thread(
        target=lambda: app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    server_thread.start()

    # 서버 준비 대기
    time.sleep(0.5)

    # 브라우저에서 열기
    print(f'SL Log Viewer running at {url}')
    webbrowser.open(url)

    # 서버 유지 (콘솔 창 유지)
    try:
        server_thread.join()
    except KeyboardInterrupt:
        print('\nShutting down...')


if __name__ == '__main__':
    main()
