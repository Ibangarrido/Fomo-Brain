"""Exercise the actual launcher restore selector against hostile/stale metadata."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml


class LauncherRestoreTests(unittest.TestCase):
    def setUp(self):
        workflow = yaml.load(Path('.github/workflows/brain_clean_v1_paper2_continue.yml').read_text(), Loader=yaml.BaseLoader)
        step = next(s for s in workflow['jobs']['paper2']['steps'] if s.get('id') == 'source')
        self.code = step['run'].split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        self.artifact = {'id': 17, 'name': 'brain-clean-v1-paper2-state', 'expired': False,
                         'created_at': '2026-11-07T00:00:00Z',
                         'workflow_run': {'id': 42, 'head_branch': 'main', 'head_sha': 'abc'}}
        self.source = {'id': 42, 'status': 'completed', 'conclusion': 'success',
                       'head_branch': 'main', 'head_sha': 'abc',
                       'path': '.github/workflows/brain_clean_v1_paper2_continue.yml'}

    def select(self, artifacts=None, source=None):
        items = [self.artifact] if artifacts is None else artifacts
        responses = [{'total_count': len(items), 'artifacts': items}, source or self.source]
        def urlopen(request, timeout):
            return io.BytesIO(json.dumps(responses.pop(0)).encode())
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'output'
            env = {'GH_TOKEN': 'test', 'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_OUTPUT': str(output)}
            with patch.dict(os.environ, env), patch('urllib.request.urlopen', side_effect=urlopen):
                exec(compile(self.code, '<launcher-selector>', 'exec'), {})
            return output.read_text()

    def test_main_continuation_is_restorable(self):
        self.assertIn('source_run=42\n', self.select())

    def test_existing_branch_bootstrap_is_restorable(self):
        self.artifact['workflow_run']['head_branch'] = 'brain-clean-v1'
        self.source.update(head_branch='brain-clean-v1', path='.github/workflows/brain_clean_v1_paper2_bootstrap.yml')
        self.assertIn('artifact_id=17\n', self.select())

    def test_missing_or_expired_artifact_never_initializes(self):
        with self.assertRaises(RuntimeError):
            self.select([])
        self.artifact['expired'] = True
        with self.assertRaises(RuntimeError):
            self.select()

    def test_newest_failed_source_never_rolls_back(self):
        older = json.loads(json.dumps(self.artifact))
        older.update(id=16, created_at='2026-11-06T00:00:00Z')
        self.source['conclusion'] = 'failure'
        with self.assertRaises(RuntimeError):
            self.select([older, self.artifact])

    def test_invalid_provenance_is_rejected(self):
        for field, value in [('head_branch', 'foreign'), ('head_sha', 'wrong'),
                             ('status', 'in_progress'), ('path', '.github/workflows/paper2_ci.yml'), ('id', 99)]:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.select(source={**self.source, field: value})


if __name__ == '__main__':
    unittest.main()
