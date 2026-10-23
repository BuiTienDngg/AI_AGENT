r"""Optional browser smoke test. Uses isolated temp data and a fake worker, never Codex.

Install QA tooling only if wanted: .venv\Scripts\python.exe -m pip install playwright
Run: .venv\Scripts\python.exe tools/check_admin_ui.py
Uses installed Microsoft Edge in headless mode. Screenshots go to maintenance_history.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game_seo.admin_web import create_app
from game_seo.local_process import ProcessTree
from local_admin import refresh_user_path

FAKE_WORKER = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from game_seo.core import load_json, save_json
from game_seo.objects import ensure_inventory, ObjectReviewPending
from PIL import Image
from docx import Document
work = Path(sys.argv[1])
save_json(work / 'quota_usage.json', {'summary': {
    '5h': {'before_percent':20,'after_percent':23,'delta_percent_points':3},
    'week': {'before_percent':60,'after_percent':61,'delta_percent_points':1}}})
if len(sys.argv) > 3 and sys.argv[3] == 'questions_vi':
    from game_seo.question_translation import set_translation, set_display_translations
    doc = load_json(work / 'owner_questions.json')
    for q in doc['questions']:
        set_translation(q, 'Bản dịch tiếng Việt: ' + q['question'])
        set_display_translations(q,{k+'_vi':'Bản dịch: '+q[k] for k in ('name','appearance','answer') if q.get(k)})
    save_json(work / 'owner_questions.json', doc)
    save_json(work / 'question_translation_result.json', {'status':'translated','error':''})
    sys.exit(0)
print('[1/7] Extracting video frames for UI test only ...', flush=True)
time.sleep(1)
frames = {'frames': [{'frame_id': 'FRAME001', 'path': str(work / 'frames' / 'FRAME001.jpg')}],
          'source_video': 'ui-test.mp4'}
analysis = {'game_title': 'Block Garden', 'game_objects': [
    {'id': 'OBJ001', 'name': 'Block shape', 'confidence': 'high',
     'frame_ids': ['FRAME001'], 'observed_behavior': 'Colored squares form a movable shape'},
    {'id': 'OBJ002', 'name': 'Combo number', 'confidence': 'low',
     'frame_ids': ['FRAME001'], 'observed_behavior': '', 'question': 'How is the combo calculated?'}],
    'unverified_mechanics': ['Can blocks rotate?']}
if not (work / 'frames.json').exists():
    (work / 'frames').mkdir()
    Image.new('RGB', (480,270), '#d8d0fa').save(work / 'frames' / 'FRAME001.jpg')
    save_json(work / 'frames.json', frames)
    save_json(work / 'analysis.json', analysis)
try:
    ensure_inventory(work, analysis, frames, {}, mode='web')
except ObjectReviewPending:
    print('Chờ trả lời trên trang quản trị.', flush=True)
    save_json(work / 'worker_result.json', {'status':'waiting','error':'Chờ xác nhận'})
    sys.exit(3)
print('[5/7] Writing fixture output without AI ...', flush=True)
(work / 'output').mkdir(exist_ok=True)
files = {}
for lang in ('en','vi'):
    path = work / 'output' / ('ui-test-' + lang + '.docx')
    doc = Document()
    doc.add_heading('UI test only - ' + lang, 0)
    doc.add_paragraph('This isolated fixture does not call Codex.')
    doc.save(path)
    files['docx_' + lang] = str(path)
save_json(work / 'export_manifest.json', {'files': files})
save_json(work / 'worker_result.json', {'status':'completed','error':''})
print('SUCCESS. Fixture documents created.', flush=True)
"""


def main():
    from playwright.sync_api import sync_playwright, expect
    from waitress import create_server
    refresh_user_path()
    output = ROOT / 'maintenance_history' / 'admin_ui_validation'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='game-seo-ui-') as temp:
        folder = Path(temp)
        worker = folder / 'fake_worker.py'
        worker.write_text(FAKE_WORKER, encoding='utf-8')
        video = folder / 'gameplay.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0x6651db:s=480x270:d=1',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True, timeout=30)
        def factory(command, **kwargs):
            args = [sys.executable, str(worker), command[command.index('--run-dir')+1], str(ROOT)]
            if '--task' in command:
                args.append(command[command.index('--task')+1])
            return ProcessTree(args, **kwargs)
        app = create_app(folder / 'data', folder / 'runs', process_factory=factory)
        server = create_server(app, host='127.0.0.1', port=0, threads=4)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        address = f'http://127.0.0.1:{server.effective_port}'
        problems = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width':1440,'height':1000}, device_scale_factor=1)
                page.on('pageerror', lambda error: problems.append(str(error)))
                page.goto(address)
                assert page.locator('html').evaluate("(e)=>getComputedStyle(e).getPropertyValue('--accent').trim()") == '#be3277'
                page.locator('#execution-panel').wait_for()
                page.locator('#run-model').select_option('gpt-6-luna')
                page.locator('#run-effort').select_option('low')
                page.get_by_role('button', name='Thêm game mới').first.click()
                page.locator('[name=name]').fill('Block Garden')
                page.locator('[name=game_url]').fill('https://slope3.com/block-garden')
                page.locator('[name=idea_origin]').fill('Từ những viên gạch mosaic, tạo bàn chơi đầy màu sắc.')
                page.locator('[name=story]').fill('Không có cốt truyện nhân vật; tập trung vào xếp khối.')
                page.locator('[name=game_style]').fill('Màu tươi sáng, nhịp chơi thư giãn.')
                page.locator('[name=controls_pc]').fill('Giữ chuột để cầm khối, kéo lên bàn rồi thả.')
                page.locator('[name=controls_mobile]').fill('Chạm giữ khối, kéo bằng ngón tay rồi thả.')
                # Test actual drag/drop, not just the hidden file picker.
                payload = list(video.read_bytes())
                page.evaluate("""({payload}) => {
                    const transfer = new DataTransfer();
                    transfer.items.add(new File([new Uint8Array(payload)], 'gameplay.mp4', {type:'video/mp4'}));
                    document.querySelector('#dropzone').dispatchEvent(new DragEvent('drop', {dataTransfer:transfer,bubbles:true}));
                }""", {'payload':payload})
                page.locator('#game-dialog').evaluate('(e) => e.scrollTop = 0')
                page.screenshot(path=str(output / '01-game-form.png'), full_page=True)
                page.get_by_role('button', name='Lưu game', exact=True).click()
                page.locator('#game-dialog').wait_for(state='hidden')
                page.locator('.game-card').wait_for()
                page.screenshot(path=str(output / '02-library.png'), full_page=True)
                page.locator('.game-card [data-action=edit]').click()
                page.locator('[name=name]').fill('Block Garden · Bản cập nhật')
                page.get_by_role('button', name='Lưu game', exact=True).click()
                page.locator('#game-dialog').wait_for(state='hidden')
                page.locator('.game-card h3').filter(has_text='Bản cập nhật').wait_for()
                page.locator('.game-card [data-action=run]').click()
                page.locator('.question-card').first.wait_for(timeout=20000)
                assert 'gpt-6-luna / low' in page.locator('#job-subtitle').inner_text()
                page.get_by_role('button', name='Dịch câu hỏi sang VI').click()
                page.get_by_role('button', name='Dịch câu hỏi sang VI').wait_for(state='hidden')
                assert page.locator('.question-vietnamese').count() == 3
                assert 'Bản dịch tiếng Việt' in page.locator('.question-vietnamese').nth(1).inner_text()
                question = page.locator('.question-card').nth(1)
                question.locator('[data-field=answer]').fill('Xóa nhiều hàng liên tiếp để tăng combo.')
                question.locator('.question-decision').select_option('confirmed')
                question.locator('summary').click()
                question.locator('[data-field=question]').fill('Khi nào người chơi nhận được combo?')
                page.locator('.manual-object summary').click()
                page.locator('#manual-name').fill('Quy luật xóa hàng')
                page.locator('#manual-behavior').fill('Hàng ngang hoặc cột dọc đầy sẽ biến mất, tạo chỗ trống.')
                page.wait_for_timeout(3500)  # A polling refresh must not discard a manual-object draft.
                assert page.locator('#manual-name').input_value() == 'Quy luật xóa hàng'
                page.get_by_role('button', name='Lưu đối tượng mới').click()
                page.locator('.question-card').nth(3).wait_for()
                page.get_by_role('button', name='Bỏ các mục chưa rõ').click()
                page.get_by_role('button', name='Lưu trả lời', exact=True).click()
                page.locator('#job-footer-note').filter(has_text='Chạy tiếp').wait_for()
                page.screenshot(path=str(output / '03-questions.png'), full_page=True)
                page.locator('#tab-answers').click()
                page.locator('.answer-version').first.wait_for()
                page.locator('#tab-questions').click()
                page.get_by_role('button', name='Lưu, duyệt & chạy tiếp').click()
                page.locator('.job-banner.completed').wait_for(timeout=20000)
                assert '20% → 23%' in page.locator('.quota-box').inner_text()
                with page.expect_download() as pending:
                    page.locator('#job-content a', has_text='Word EN').click()
                download = pending.value
                assert download.suggested_filename.endswith('.docx')
                page.screenshot(path=str(output / '04-completed.png'), full_page=True)
                page.locator('#close-job').click()
                page.locator('.game-card [data-action=saved]').click()
                cards=page.locator('.saved-answer-card')
                cards.first.wait_for()
                assert cards.count() >= 2
                cards.nth(0).locator('.saved-answer').fill('Saved first answer for next run.')
                cards.nth(1).locator('.saved-answer').fill('Second answer stays while first saves.')
                cards.nth(0).get_by_role('button',name='Lưu thay đổi').click()
                expect(cards.nth(0).get_by_role('button',name='Lưu thay đổi')).to_be_enabled()
                page.locator('.saved-answer-card.is-dirty').nth(0).wait_for()
                assert cards.nth(1).locator('.saved-answer').input_value()=='Second answer stays while first saves.'
                cards.nth(1).get_by_role('button',name='Lưu thay đổi').click()
                expect(page.locator('.saved-answer-card.is-dirty')).to_have_count(0)
                page.screenshot(path=str(output / '08-saved-answers-pink.png'), full_page=True)
                page.locator('#close-saved-answers').click()
                page.locator('[data-nav=history]').click()
                page.locator('tbody tr').first.wait_for()
                assert page.locator('tbody tr').count() == 1
                page.set_viewport_size({'width':390,'height':844})
                page.screenshot(path=str(output / '05-mobile.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.set_viewport_size({'width':1440,'height':1000})
                page.locator('[data-nav=games]').click()
                # Start/stop via UI; uses only the fake worker.
                page.locator('.game-card [data-action=run]').click()
                page.get_by_role('button', name='Dừng viết bài').click()
                page.locator('.job-banner.stopped').wait_for(timeout=15000)
                page.locator('#close-job').click()
                page.locator('.game-card [data-action=delete]').click()
                page.locator('#confirm-ok').click()
                page.get_by_role('heading', name='Bắt đầu với game đầu tiên').wait_for()
                page.reload()
                page.locator('[data-nav=history]').click()
                page.locator('tbody tr').first.wait_for()
                assert page.locator('tbody tr').count() == 2
                assert not problems, problems
                # Real workspace read-only: history and Word downloads.
                page.goto('http://127.0.0.1:8765')
                page.locator('[data-nav=history]').click()
                page.locator('tbody tr').first.wait_for()
                assert page.locator('a', has_text='Word EN').count() > 0
                page.screenshot(path=str(output / '06-real-history.png'), full_page=True)
                page.locator('[data-action=import]').first.click()
                page.locator('#game-dialog').wait_for()
                assert page.locator('[name=controls_pc]').input_value() == ''
                assert page.locator('[name=controls_mobile]').input_value() == ''
                page.screenshot(path=str(output / '07-legacy-import.png'), full_page=True)
                page.locator('.close-game').first.click()
                browser.close()
            report = {'passed':True, 'codex_calls':0,
                      'checks':['model/effort selection captured per run','bilingual question translation',
                                'pink theme','quota before/after in UI','saved answer library edit without losing other drafts',
                                'drag-drop upload','create/edit/delete','saved revisions','start/wait/answer/edit question',
                                'manual object survives polling and saves','answer history','resume/completed','Word download','mobile width','stop',
                                'restart persistence','legacy history','legacy import form'],
                      'browser_errors':problems, 'screenshots':str(output)}
            (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            app.extensions['office_jobs'].close()
            limit = time.monotonic() + 10
            while app.extensions['office_jobs'].active and time.monotonic() < limit:
                time.sleep(.05)
            server.close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
