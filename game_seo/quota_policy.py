"""Conservative subscription policy. Percentages are not derived from tokens."""
from datetime import datetime, timezone
import math

DEFAULTS = {'enabled': False, 'primary_account': '', 'warning':20, 'minimum':13,
            'safety_margin':20, 'interval':60, 'max_age':180, 'cold_start_cost':20,
            'max_job_quota':50, 'allow_api':False}


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def quota_state(windows, captured, *, error='', now=None, max_age=180, warning=20):
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    at = timestamp(captured)
    if not at or not isinstance(windows, dict) or any(k not in windows for k in ('5h','week')):
        return 'UNKNOWN'
    if now-at > max_age or at > now+30:
        return 'STALE'
    remaining = []
    for key in ('5h','week'):
        w = windows[key]
        if not isinstance(w, dict):
            return 'UNKNOWN'
        used, reset = w.get('used_percent'), w.get('resets_at')
        if isinstance(used, bool) or not isinstance(used,(int,float)) or not math.isfinite(used) or not 0 <= used <= 100:
            return 'UNKNOWN'
        if reset is not None and (not isinstance(reset,(int,float)) or not math.isfinite(reset)):
            return 'UNKNOWN'
        if reset is not None and reset <= now:
            return 'STALE'
        remaining.append(100-used)
    if error:
        return 'ERROR'
    return 'EXHAUSTED' if min(remaining) <= 0 else 'LOW_QUOTA' if min(remaining) <= warning else 'AVAILABLE'


def evaluate(profile, settings=None, history=(), now=None):
    cfg = {**DEFAULTS, **(settings or {})}
    state = quota_state(profile.get('windows',{}), profile.get('last_success'),
                        error=profile.get('error',''), max_age=cfg['max_age'], warning=cfg['warning'], now=now)
    if not profile.get('enabled',True) or state in ('UNKNOWN','STALE','ERROR','EXHAUSTED'):
        return {'allowed':False,'status':state,'reason':'Quota thiếu, cũ, lỗi hoặc đã hết.'}
    # Only use full successful run measurements for this same provider/model.
    valid = [h for h in history if h.get('result') == 'completed' and
             all(isinstance(h.get(k),(int,float)) and h[k] >= 0 for k in ('delta_5h','delta_week'))]
    estimate = {label: max([h['delta_'+label] for h in valid[:20]]) if len(valid) >= 3 else cfg['cold_start_cost']
                for label in ('5h','week')}
    needed = {key:max(cfg['minimum'], cost*(1+cfg['safety_margin']/100)) for key,cost in estimate.items()}
    allowed = all(needed[key] <= cfg['max_job_quota'] and
                  100-profile['windows'][key]['used_percent'] >= needed[key] for key in needed)
    return {'allowed':allowed,'status':state,'required_percent_points':needed,
            'confidence':'historical_upper_bound' if len(valid)>=3 else 'conservative_cold_start',
            'samples':len(valid), 'reason':'Đủ theo policy, vẫn có sai số.' if allowed else 'Quota dưới mức an toàn theo policy.'}
