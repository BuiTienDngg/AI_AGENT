import json
import tempfile
import unittest
from pathlib import Path
from game_seo.stage_context import prepare_stage_context

class RepairWarningIsolation(unittest.TestCase):
    def test_warnings_not_exposed_to_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            original_critique = {'issues': [
                {'path': 'sections[0].paragraphs[0]', 'severity': 'error'},
                {'path': 'sections[4].paragraphs[1]', 'severity': 'warning'}]}
            (path / 'critique.json').write_text(json.dumps(original_critique), encoding='utf-8')
            (path / 'qa_report.json').write_text(json.dumps({'editorial_issues': original_critique['issues']}), encoding='utf-8')
            (path / 'repair_context.json').write_text(json.dumps({'allowed_edits': [{'path': 'sections[0].paragraphs[0]'}]}), encoding='utf-8')
            bundle = json.loads(prepare_stage_context(path, 'repair').read_text(encoding='utf-8'))
            self.assertEqual([i['severity'] for i in bundle['critique.json']['issues']], ['error'])
            self.assertEqual([i['severity'] for i in bundle['qa_report.json']['editorial_issues']], ['error'])
            self.assertEqual(json.loads((path / 'critique.json').read_text()), original_critique)
            self.assertEqual(len(bundle['repair_context.json']['allowed_edits']), 1)
