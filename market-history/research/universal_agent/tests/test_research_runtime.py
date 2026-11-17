"""Persistence and approval checks for the bounded research runtime."""
from __future__ import annotations

import json
import io
import multiprocessing
import os
import signal
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.engine import locked_state
from universal_agent.research_runtime import main, run, submit


GOAL = '지표 116의 한국 증시 선행 신호 PIT를 검증하라.'


def _stall_after_reservation(queue_dir: Path) -> None:
    from universal_agent import process_supervisor
    with patch.object(process_supervisor, 'run_research_program',
                      side_effect=lambda *args, **kwargs: time.sleep(30)):
        run(queue_dir, max_seconds=40)


class ResearchRuntimeTests(unittest.TestCase):
    def setUp(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=PRIVATE_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.queue_dir = Path(self.temp.name) / 'queue'

    def test_approval_blocks_execution(self):
        item = submit(GOAL, self.queue_dir, approval_required=True)
        self.assertEqual(item['status'], 'APPROVAL_REQUIRED')
        self.assertEqual(run(self.queue_dir, max_seconds=30)['processed'], 0)
        saved = json.loads((self.queue_dir / 'state.json').read_text())
        self.assertEqual(saved['jobs'][item['goal_id']]['attempt_count'], 0)

    def test_checkpoint_resume_does_not_repeat_completed_goal(self):
        item = submit(GOAL, self.queue_dir)
        first = run(self.queue_dir, max_seconds=30)
        self.assertEqual(first['statuses'][item['goal_id']], 'BLOCKED_EVIDENCE')
        saved = json.loads((self.queue_dir / 'state.json').read_text())
        self.assertEqual(saved['jobs'][item['goal_id']]['tasks']['pit_ind116']['attempt_count'], 1)
        self.assertEqual(run(self.queue_dir, max_seconds=30)['processed'], 0)
        resumed = json.loads((self.queue_dir / 'state.json').read_text())
        self.assertEqual(resumed['jobs'][item['goal_id']]['attempt_count'], 1)
        self.assertEqual(resumed['jobs'][item['goal_id']]['tasks']['pit_ind116']['attempt_count'], 1)

    def test_plan_change_fails_closed_before_execution(self):
        item = submit(GOAL, self.queue_dir)
        from universal_agent import research_runtime
        original = research_runtime.plan_goal
        def changed(goal):
            plan = original(goal)
            plan['resource_budget']['max_model_calls'] = 1
            return plan
        with patch.object(research_runtime, 'plan_goal', side_effect=changed):
            run(self.queue_dir, max_seconds=30)
        saved = json.loads((self.queue_dir / 'state.json').read_text())
        self.assertEqual(saved['jobs'][item['goal_id']]['status'], 'FAILED')
        self.assertIsNone(saved['jobs'][item['goal_id']]['checkpoint'])

    def test_same_goal_in_two_queues_keeps_separate_checkpoints(self):
        other = Path(self.temp.name) / 'other_queue'
        item = submit(GOAL, self.queue_dir)
        submit(GOAL, other)
        run(self.queue_dir, max_seconds=30)
        first = json.loads((self.queue_dir / 'state.json').read_text())
        first_hash = first['jobs'][item['goal_id']]['checkpoint_sha256']
        run(other, max_seconds=30)
        self.assertEqual(run(self.queue_dir, max_seconds=30)['processed'], 0)
        latest = json.loads((self.queue_dir / 'state.json').read_text())
        self.assertEqual(latest['jobs'][item['goal_id']]['checkpoint_sha256'], first_hash)

    def test_status_remains_readable_while_worker_holds_lock(self):
        item = submit(GOAL, self.queue_dir)
        output = io.StringIO()
        with locked_state(self.queue_dir), patch('sys.argv', [
                'research_runtime', 'status', '--queue-dir', str(self.queue_dir)]):
            with redirect_stdout(output):
                self.assertEqual(main(), 0)
        self.assertEqual(json.loads(output.getvalue())['statuses'][item['goal_id']], 'PENDING')

    def test_unsupported_goal_preserves_original_contract(self):
        goal = 'Investigate Antarctic whale migration with satellite images.'
        item = submit(goal, self.queue_dir)
        self.assertEqual(item['status'], 'UNSUPPORTED')
        self.assertEqual(run(self.queue_dir, max_seconds=30)['processed'], 0)
        contract = json.loads((self.queue_dir / 'programs' / item['goal_id'] /
            'goal_contract.json').read_text())
        self.assertEqual(contract['original_research_goal'], goal)
        report = json.loads(Path(item['output']).read_text())
        self.assertEqual(report['status'], 'RESEARCH_UNSUPPORTED')

    def test_sigkill_after_reservation_recovers_from_checkpoint(self):
        item = submit(GOAL, self.queue_dir)
        process = multiprocessing.get_context('fork').Process(
            target=_stall_after_reservation, args=(self.queue_dir,))
        process.start()
        self.addCleanup(lambda: process.kill() if process.is_alive() else None)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = json.loads((self.queue_dir / 'state.json').read_text())
            if state['jobs'][item['goal_id']]['status'] == 'RUNNING':
                break
            time.sleep(0.02)
        else:
            self.fail('Runtime did not reserve the Goal before timeout')
        os.kill(process.pid, signal.SIGKILL)
        process.join(timeout=5)
        self.assertEqual(process.exitcode, -signal.SIGKILL)
        result = run(self.queue_dir, max_seconds=30)
        self.assertEqual(result['statuses'][item['goal_id']], 'BLOCKED_EVIDENCE')
        final = json.loads((self.queue_dir / 'state.json').read_text())
        self.assertEqual(final['jobs'][item['goal_id']]['attempt_count'], 2)
        self.assertEqual(final['jobs'][item['goal_id']]['tasks']['pit_ind116']['attempt_count'], 1)
        self.assertEqual(run(self.queue_dir, max_seconds=30)['processed'], 0)

    def test_checkpoint_write_failure_prevents_task_execution(self):
        item = submit(GOAL, self.queue_dir)
        with patch('universal_agent.research_runtime.write_state',
                   side_effect=OSError('injected storage failure')):
            with self.assertRaises(OSError):
                run(self.queue_dir, max_seconds=30)
        saved = json.loads((self.queue_dir / 'state.json').read_text())
        self.assertEqual(saved['jobs'][item['goal_id']]['status'], 'PENDING')
        self.assertEqual(saved['jobs'][item['goal_id']]['attempt_count'], 0)
        self.assertEqual(run(self.queue_dir, max_seconds=30)['statuses'][item['goal_id']],
                         'BLOCKED_EVIDENCE')

    def test_provider_outage_blocks_without_unbounded_retry(self):
        item = submit(GOAL, self.queue_dir)
        with patch('universal_agent.process_supervisor.run_research_program',
                   side_effect=OSError('injected provider outage')):
            result = run(self.queue_dir, max_seconds=30)
        self.assertEqual(result['statuses'][item['goal_id']], 'BLOCKED_ENV')
        self.assertEqual(run(self.queue_dir, max_seconds=30)['processed'], 0)
        saved = json.loads((self.queue_dir / 'state.json').read_text())
        self.assertEqual(saved['jobs'][item['goal_id']]['attempt_count'], 1)
        self.assertEqual(saved['jobs'][item['goal_id']]['network_requests_reserved'], 0)


if __name__ == '__main__':
    unittest.main()
