#!/usr/bin/env python3
"""Start the local admin with the project virtual environment."""
from __future__ import annotations

import argparse
import atexit
import os
import webbrowser

from game_seo.core import ROOT


def refresh_user_path():
    if os.name == 'nt':
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r'Environment'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    value, _ = winreg.QueryValueEx(handle, 'Path')
                    os.environ['PATH'] += os.pathsep + os.path.expandvars(value)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description='Game SEO Office — local admin')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open-browser', action='store_true', help='Open local admin in the default browser')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535.')
    refresh_user_path()
    data = ROOT / 'local_admin_data'
    data.mkdir(exist_ok=True)
    lockfile = open(data / 'server.lock', 'a+b')
    lockfile.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            if lockfile.read(1) == b'':
                lockfile.write(b'0')
                lockfile.flush()
            lockfile.seek(0)
            msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        if args.open_browser:
            # Only open an existing admin after checking it responds at this port.
            from urllib.request import urlopen
            try:
                with urlopen(f'http://127.0.0.1:{args.port}/api/state', timeout=3) as response:
                    import json
                    state = json.load(response)
                if 'games' in state and 'settings' in state:
                    webbrowser.open(f'http://127.0.0.1:{args.port}')
                    return
            except (OSError, ValueError):
                pass
        raise SystemExit('Trang quản trị đã chạy. Mở http://127.0.0.1:8765 hoặc kiểm tra terminal đang chạy.')
    from waitress import create_server
    from game_seo.admin_web import MAX_UPLOAD, create_app
    app = create_app(data_dir=data)
    jobs = app.extensions['office_jobs']
    server = create_server(app, host='127.0.0.1', port=args.port, threads=6,
                           max_request_body_size=MAX_UPLOAD, channel_timeout=900)
    accounts = app.extensions['office_accounts']
    accounts.start()
    atexit.register(accounts.close)
    atexit.register(jobs.close)
    print(f'Game SEO Office: http://127.0.0.1:{args.port}', flush=True)
    if args.open_browser:
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    print('Giữ terminal này mở. Ctrl+C để đóng trang quản trị và dừng các lượt đang chạy.', flush=True)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        accounts.close()
        jobs.close()
        server.close()
        lockfile.close()


if __name__ == '__main__':
    main()
