import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'game_seo' / 'stage_context.py'
spec = importlib.util.spec_from_file_location('stage_context', MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestStageContext(unittest.TestCase):
    def test_preserves_sources_and_citations(self):
        with tempfile.TemporaryDirectory() as d:
            wd = Path(d)
            data = {'sources': [{'id':'SRC001', 'excerpt':'Thử nghiệm đầy đủ [[SRC001]]'}]}
            (wd / 'sources.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            path = mod.prepare_stage_context(wd, 'draft')
            bundled = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(bundled['sources.json'], data)
            self.assertNotIn('article.json', bundled)
    def test_stage_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            wd = Path(d)
            (wd/'article.json').write_text('{"content":"Hello"}',encoding='utf-8')
            (wd/'sources.json').write_text('{"secret":"not_for_translate"}',encoding='utf-8')
            bundle = json.loads(mod.prepare_stage_context(wd,'translate').read_text(encoding='utf-8'))
            self.assertIn('article.json',bundle)
            self.assertNotIn('sources.json',bundle)
    def test_invalid_json_fails(self):
        with tempfile.TemporaryDirectory() as d:
            wd=Path(d)
            (wd/'article.json').write_text('{',encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError):
                mod.prepare_stage_context(wd,'critique')

if __name__ == '__main__':
    unittest.main()
