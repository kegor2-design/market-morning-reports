import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.engine import check_evidence, load_project, reopen, run


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'evidence.json').write_text('{"ready": true}')
        self.project = self.root / 'project.json'
        self.state_dir = self.root / 'state'
        self.spec = {
            'schema_version': 1, 'project_id': 'sample', 'workspace_root': str(self.root),
            'tasks': [
                {'id': 'first', 'priority': 1,
                 'checks': [{'kind': 'json_equals', 'path': 'evidence.json',
                             'pointer': '/ready', 'equals': True}]},
                {'id': 'second', 'priority': 2, 'depends_on': ['first'],
                 'checks': [{'kind': 'csv_unique_count', 'path': 'rows.csv',
                             'field': 'id', 'equals': 2}]},
            ]}
        (self.root / 'rows.csv').write_text('id\na\nb\n')
        self.save_spec()

    def save_spec(self):
        self.project.write_text(json.dumps(self.spec))

    def test_dependency_order_and_resume(self):
        first = run(self.project, self.state_dir)
        self.assertEqual(first['tasks']['first']['status'], 'COMPLETED')
        self.assertEqual(first['tasks']['second']['status'], 'PENDING')
        self.assertEqual(first['next_task'], 'second')
        second = run(self.project, self.state_dir)
        self.assertEqual(second['tasks']['second']['status'], 'COMPLETED')
        self.assertEqual(second['tasks']['second']['attempts'], 1)
        self.assertIn('VERIFIED', [event['status'] for event in second['events']])

    def test_failed_evidence_does_not_complete_and_retry_is_bounded(self):
        (self.root / 'rows.csv').write_text('id\na\na\n')
        run(self.project, self.state_dir)
        for _ in range(3):
            state = run(self.project, self.state_dir)
        self.assertEqual(state['tasks']['second']['status'], 'BLOCKED')
        self.assertEqual(state['tasks']['second']['attempts'], 3)
        self.assertIsNone(state['next_task'])

    def test_path_escape_and_unsafe_sql_are_rejected(self):
        outside = self.root.parent / 'outside-evidence.txt'
        with self.assertRaises(ValueError):
            check_evidence(self.root, {'kind': 'file_exists', 'path': '../outside-evidence.txt'})
        db_path = self.root / 'data.sqlite'
        with sqlite3.connect(db_path) as db:
            db.execute('create table records(id integer)')
        with self.assertRaises(ValueError):
            check_evidence(self.root, {'kind': 'sqlite_count', 'path': 'data.sqlite',
                                       'table': 'records;DROP TABLE records', 'equals': 0})
        self.assertFalse(outside.exists())

    def test_changed_manifest_fails_closed(self):
        run(self.project, self.state_dir)
        self.spec['tasks'][0]['priority'] = 0
        self.save_spec()
        with self.assertRaisesRegex(ValueError, 'manifest changed'):
            run(self.project, self.state_dir)

    def test_interrupted_run_recovers_without_claiming_completion(self):
        state = run(self.project, self.state_dir)
        path = self.state_dir / 'state.json'
        state['tasks']['second']['status'] = 'IN_PROGRESS'
        state['tasks']['second']['attempts'] = 1
        path.write_text(json.dumps(state))
        recovered = run(self.project, self.state_dir)
        self.assertEqual(recovered['tasks']['second']['status'], 'COMPLETED')
        self.assertEqual(recovered['tasks']['second']['attempts'], 2)
        self.assertIn('FAILED', [event['status'] for event in recovered['events']])

    def test_rejects_dependency_cycle(self):
        self.spec['tasks'][0]['depends_on'] = ['second']
        self.save_spec()
        with self.assertRaisesRegex(ValueError, 'cycle'):
            load_project(self.project)

    def test_reopen_after_new_evidence(self):
        (self.root / 'rows.csv').write_text('id\na\na\n')
        run(self.project, self.state_dir, max_steps=2)
        self.assertEqual(json.loads((self.state_dir / 'state.json').read_text())
                         ['tasks']['second']['status'], 'BLOCKED')
        (self.root / 'rows.csv').write_text('id\na\nb\n')
        reopened = reopen(self.project, self.state_dir, 'second')
        self.assertEqual(reopened['next_task'], 'second')
        finished = run(self.project, self.state_dir)
        self.assertEqual(finished['tasks']['second']['status'], 'COMPLETED')

    def test_review_gate_never_passes_on_summary_claim(self):
        check = {'kind': 'review_required', 'reason': 'Independent PIT audit missing'}
        self.assertFalse(check_evidence(self.root, check)['ok'])


if __name__ == '__main__':
    unittest.main()
