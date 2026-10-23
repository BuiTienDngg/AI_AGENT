"""Bounded JSONL compatibility adapter. Logs are observations, never live truth."""
import json
from pathlib import Path
from .quota_policy import timestamp


def parse_jsonl(text):
    latest = None
    for line in text.splitlines():
        try:
            item = json.loads(line)
            payload = item.get('payload') or {}
            limits = payload.get('rate_limits') or item.get('rate_limits')
            if not isinstance(limits, dict):
                continue
            windows = {}
            for bucket in ('primary','secondary'):
                w = limits.get(bucket) or {}
                label = {300:'5h',10080:'week'}.get(w.get('window_minutes',w.get('windowDurationMins')))
                used = w.get('used_percent',w.get('usedPercent'))
                if label and not isinstance(used,bool) and isinstance(used,(int,float)) and 0 <= used <= 100:
                    windows[label] = {'used_percent':used,'resets_at':w.get('resets_at',w.get('resetsAt')),
                                      'window_minutes':300 if label=='5h' else 10080}
            at = item.get('timestamp')
            if windows and timestamp(at) is not None and (latest is None or timestamp(at)>timestamp(latest['captured'])):
                latest = {'windows':windows,'captured':at,'source':'session_jsonl'}
        except (ValueError, TypeError, AttributeError):
            continue
    return latest


def read_session_logs(home):
    observations = []
    try:
        files = sorted((Path(home)/'sessions').rglob('*.jsonl'),key=lambda f:f.stat().st_mtime,reverse=True)[:30]
        for file in files:
            try:
                with file.open('rb') as stream:
                    stream.seek(max(0,file.stat().st_size-2*1024*1024))
                    row = parse_jsonl(stream.read().decode('utf-8',errors='replace'))
                    if row:
                        observations.append(row)
            except OSError:
                continue
    except OSError:
        return None
    return max(observations,key=lambda r:timestamp(r['captured'])) if observations else None
