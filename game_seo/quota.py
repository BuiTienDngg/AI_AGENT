"""Read account quota snapshots from the official Codex app-server protocol.

These are account-wide percentages, not token-derived costs of a single article.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .core import load_json, utc_now


WINDOWS = {300: '5h', 10080: 'week'}


def read_rate_limits(binary='codex', timeout=12, *, codex_home=None):
    executable = shutil.which(binary)
    if not executable:
        raise RuntimeError('Codex CLI unavailable')
    environment = os.environ.copy()
    if codex_home is not None:
        environment['CODEX_HOME'] = str(codex_home)
    proc = subprocess.Popen([executable, 'app-server'], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding='utf-8', errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                            env=environment)
    messages = queue.Queue()
    deadline = time.monotonic() + timeout

    def receive():
        try:
            for line in proc.stdout:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    continue
        except (OSError, ValueError):
            pass

    threading.Thread(target=receive, daemon=True).start()

    def send(message):
        proc.stdin.write(json.dumps(message) + '\n')
        proc.stdin.flush()

    def reply(request_id):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Timed out reading Codex quota')
            item = messages.get(timeout=remaining)
            if item.get('id') == request_id:
                if item.get('error'):
                    raise RuntimeError(item['error'].get('message', 'Codex app-server error'))
                return item.get('result') or {}

    try:
        send({'method': 'initialize', 'id': 1, 'params': {'clientInfo': {
            'name': 'game_seo_office', 'title': 'Game SEO Office', 'version': '1.1'}}})
        reply(1)
        send({'method': 'initialized', 'params': {}})
        send({'method': 'account/rateLimits/read', 'id': 2})
        result = reply(2)
        buckets = result.get('rateLimitsByLimitId') or {}
        bucket = buckets.get('codex') or result.get('rateLimits') or {}
        windows = {}
        for value in (bucket.get('primary'), bucket.get('secondary')):
            if not isinstance(value, dict):
                continue
            label = WINDOWS.get(value.get('windowDurationMins'))
            used = value.get('usedPercent')
            if label and isinstance(used, (int, float)) and 0 <= used <= 100:
                windows[label] = {'used_percent': used, 'resets_at': value.get('resetsAt'),
                                  'window_minutes': value['windowDurationMins']}
        if not windows:
            raise RuntimeError('Codex did not return 5-hour or weekly quota windows')
        return windows
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        for pipe in (proc.stdin, proc.stdout):
            pipe.close()


def summarize_samples(samples):
    summary = {}
    for label in WINDOWS.values():
        valid = [sample for sample in samples if label in sample.get('windows', {})]
        if not valid:
            continue
        first, last = valid[0], valid[-1]
        before, after = first['windows'][label], last['windows'][label]
        has_before = first.get('point') == 'before'
        has_after = last.get('point') == 'after'
        same_window = before.get('resets_at') == after.get('resets_at')
        delta = after['used_percent'] - before['used_percent'] if same_window else None
        summary[label] = {'before_percent': before['used_percent'] if has_before else None,
                          'after_percent': after['used_percent'] if has_after else None,
                          'latest_percent': after['used_percent'], 'measurement_complete': has_before and has_after,
                          'reset_detected': not same_window,
                          'delta_percent_points': delta if has_before and has_after and delta is not None and delta >= 0 else None,
                          'before_at': first['timestamp_utc'], 'after_at': last['timestamp_utc'],
                          'resets_at': after.get('resets_at')}
    return summary


def capture_quota(workdir, stage, point, binary='codex', reader=read_rate_limits):
    path = Path(workdir) / 'quota_usage.json'
    try:
        doc = load_json(path, default={'version': 1, 'samples': []})
    except (OSError, ValueError):
        doc = {'version': 1, 'samples': [], 'recovery_note': 'Previous quota report was unreadable.'}
    sample = {'timestamp_utc': utc_now(), 'stage': stage, 'point': point}
    try:
        sample['windows'] = reader(binary)
    except (OSError, RuntimeError, queue.Empty, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        sample['windows'] = {}
        sample['error'] = str(exc)[:300]
    doc['samples'].append(sample)
    doc['summary'] = summarize_samples(doc['samples'])
    doc['note'] = ('Account-wide Codex quota snapshots. Differences can include other Codex activity; '
                   'they are not a measured per-article charge. A reset or missing reading has no delta.')
    doc['updated_at_utc'] = utc_now()
    from .web_review import atomic_json
    atomic_json(path, doc)
    return sample
