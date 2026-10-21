from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def slugify(text: str):
    val = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return val[:70] or 'game'


def canonical_url(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlunparse
    p = urlparse(url)
    if p.scheme not in ('http', 'https') or not p.hostname:
        return ''
    if p.username or p.password:
        return ''
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')])
    return urlunparse((p.scheme, p.netloc.lower(), p.path or '/', '', query, ''))


def public_url(url: str) -> bool:
    """Conservative URL validation: reject loopback/private literal IP, credentials, non-web protocols."""
    import ipaddress
    u = canonical_url(url)
    if not u:
        return False
    host = urlparse(u).hostname or ''
    if host.lower() in ('localhost', 'localhost.localdomain') or host.lower().endswith('.local'):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return ip.is_global


def trim(s, limit=1800):
    return re.sub(r'\s+', ' ', str(s or '')).strip()[:limit]
