"""One isolated pipeline invocation. Exit 3 means waiting for web owner review."""
from __future__ import annotations

import argparse
import sys
import traceback
import os
from pathlib import Path

from game_seo.core import load_json
from game_seo.objects import ObjectReviewPending
from game_seo.usage import print_usage
from game_seo.web_review import atomic_json
from run import run_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--task', choices=['article', 'questions_vi'], default='article')
    args = parser.parse_args()
    work = Path(args.run_dir).resolve()
    brief = load_json(work / 'game_brief.json')
    cfg = load_json(work / 'admin_config.json')
    result = {'status': 'failed', 'error': ''}
    code = 1
    try:
        if args.task == 'questions_vi':
            from game_seo.question_translation import translate_questions
            count = translate_questions(work, cfg)
            print(f'Đã dịch {count} câu hỏi sang tiếng Việt.', flush=True)
            result = {'status': 'translated', 'error': ''}
            code = 0
            return code
        code = run_all(brief['video_path'], work, cfg, resume=True,
                       game_title_override=brief['name'], object_review='web')
        result['status'] = 'completed' if code == 0 else 'failed'
        if code:
            result['error'] = 'QA chưa đạt. Xem báo cáo QA và nhật ký; không xuất bài chưa duyệt.'
    except ObjectReviewPending as exc:
        code = 3
        result = {'status': 'waiting', 'error': str(exc)}
        print(str(exc), flush=True)
    except Exception as exc:
        secret = os.environ.get('GAME_SEO_API_KEY')
        message = str(exc)
        detail = traceback.format_exc()
        if secret:
            message = message.replace(secret,'[REDACTED]')
            detail = detail.replace(secret,'[REDACTED]')
        result['error'] = message
        print(detail,flush=True)
    finally:
        atomic_json(work / ('worker_result.json' if args.task == 'article' else 'question_translation_result.json'), result)
        print_usage(work)
    return code


if __name__ == '__main__':
    sys.exit(main())
