"""Conservative regressions for known opaque phrases; semantic review remains essential."""
from __future__ import annotations
import re
from .core import ROOT


STYLE_FILE = ROOT / 'WRITING_STYLE.md'


def unclear_phrases(text, language='en'):
    patterns = {
        'en': [r'\bcompact rectangles?\b', r'\bspatial demands?\b',
               r'\bdirect (?:its|their) placement\b'],
        'vi': [r'\bhình chữ nhật gọn\b', r'\bhướng việc đặt\b', r'\bđịnh hướng việc đặt\b'],
    }
    return [match.group(0) for pattern in patterns.get(language, [])
            for match in re.finditer(pattern, text, flags=re.I)]
