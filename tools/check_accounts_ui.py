"""Isolated browser QA for profile CRUD and quota monitoring. No model calls."""
import json
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game_seo.admin_web import create_app
from game_seo.core import ROOT


def main():
    from playwright.sync_api import sync_playwright, expect
    from waitress import create_server
    output = ROOT / 'maintenance_history' / 'accounts_validation'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        home = root / 'codex-home'
        home.mkdir()
        app = create_app(root/'data', root/'runs')
        monitor = app.extensions['office_accounts']
        import time
        monitor.reader = lambda **kwargs: {
            '5h': {'used_percent':90, 'resets_at':time.time()+1000, 'window_minutes':300},
            'week': {'used_percent':40, 'resets_at':time.time()+10000, 'window_minutes':10080}}
        server = create_server(app, host='127.0.0.1', port=0, threads=4)
        worker = threading.Thread(target=server.run, daemon=True)
        worker.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width':1360,'height':1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.effective_port}/')
                page.get_by_role('link', name='Codex Accounts').click()
                expect(page.get_by_role('heading',name='Codex Accounts',exact=True)).to_be_visible()
                page.get_by_role('link',name='Quản trị tài khoản').click()
                page.locator('#admin-password').fill('fixture-admin-password')
                page.locator('#admin-confirm').fill('fixture-admin-password')
                page.get_by_role('button',name='Tạo admin local').click()
                expect(page.get_by_role('heading',name='Codex Account Management',exact=True)).to_be_visible()
                page.get_by_role('button',name='+ Thêm hồ sơ').click()
                page.locator('#account-form [name=name]').fill('Hồ sơ kiểm thử')
                page.locator('[name=home]').fill(str(home))
                page.locator('#account-form [name=notes]').fill('Dữ liệu mô phỏng để kiểm tra UI.')
                page.get_by_role('button',name='Lưu hồ sơ',exact=True).click()
                expect(page.locator('#account-dialog')).not_to_be_visible()
                expect(page.get_by_role('heading',name='Hồ sơ kiểm thử',exact=True)).to_be_visible()
                monitor.scan()
                page.reload()
                expect(page.get_by_text('Còn 10%',exact=True)).to_be_visible()
                expect(page.get_by_text('Còn 60%',exact=True)).to_be_visible()
                expect(page.locator('.account-status')).to_contain_text('LOW_QUOTA')
                page.locator('#account-table').get_by_role('button',name='Xem',exact=True).click()
                expect(page.get_by_role('heading',name='Lịch sử quota & workflow')).to_be_visible()
                page.locator('#close-history').click()
                page.screenshot(path=str(output/'accounts-desktop.png'),full_page=True)
                page.get_by_role('button',name='Sửa',exact=True).click()
                page.locator('#account-form [name=name]').fill('Đã sửa tên')
                page.get_by_role('button',name='Lưu hồ sơ',exact=True).click()
                expect(page.get_by_role('heading',name='Đã sửa tên',exact=True)).to_be_visible()
                page.locator('#policy-form [name=primary_account]').select_option(monitor.profiles()[0]['id'])
                page.locator('#policy-form [name=enabled]').check()
                page.get_by_role('button',name='Lưu policy',exact=True).click()
                expect(page.locator('#policy-state')).to_contain_text('Policy đang bật')
                page.locator('#policy-form [name=enabled]').uncheck()
                page.get_by_role('button',name='Lưu policy',exact=True).click()
                expect(page.locator('#policy-state')).to_contain_text('Policy đang tắt')
                page.get_by_role('button',name='+ Thêm API provider').click()
                page.locator('#provider-form [name=name]').fill('API mô phỏng')
                page.locator('#provider-form [name=model]').fill('fixture-model')
                page.locator('#provider-form [name=api_key]').fill('fixture-key-not-real')
                page.get_by_role('button',name='Lưu provider',exact=True).click()
                expect(page.get_by_role('heading',name='API mô phỏng',exact=True)).to_be_visible()
                page.locator('#providers-list').get_by_role('button',name='Sửa',exact=True).click()
                expect(page.locator('#provider-form [name=api_key]')).to_have_value('')
                page.get_by_role('button',name='Đóng',exact=True).filter(visible=True).first.click()
                page.set_viewport_size({'width':390,'height':844})
                page.screenshot(path=str(output/'accounts-mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.on('dialog',lambda dialog:dialog.accept())
                page.locator('#accounts-list').get_by_role('button',name='Xóa',exact=True).click()
                expect(page.get_by_role('heading',name='Chưa có hồ sơ theo dõi')).to_be_visible()
                assert home.exists()
                page.get_by_role('button',name='Đăng xuất',exact=True).click()
                expect(page.get_by_role('heading',name='Đăng nhập quản trị')).to_be_visible()
                page.goto(f'http://127.0.0.1:{server.effective_port}/accounts')
                expect(page.locator('#add-account')).to_have_count(0)
                browser.close()
        finally:
            server.close()
            monitor.close()
            app.extensions['office_jobs'].close()
    report = {'passed':not errors,'model_calls':0,'browser_errors':errors,
              'checks':['admin navigation','profile create','quota display','low quota warning',
                        'edit','policy save','encrypted provider save','key never displayed',
                        'mobile width','delete preserves home','logout and viewer access']}
    (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
