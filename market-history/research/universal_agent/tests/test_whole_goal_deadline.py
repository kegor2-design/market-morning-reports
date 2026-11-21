"""Whole DAG timing, including discovery, interrupted collection and shutdown."""
import http.server
import json
import multiprocessing
import os
import signal
import tempfile
import threading
import time
import unittest
from pathlib import Path

from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.process_supervisor import run_research_program
from universal_agent.research_job import _worker_identity
from universal_agent.research_planner import plan_goal
from universal_agent.tests import time_audit


class WholeGoalDeadlineTests(unittest.TestCase):
    def test_normal(self):
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as tmp:
            directory = Path(tmp)
            start = time_audit.clock()
            outcome = run_research_program('한국 급락 전 변동성 연구 전체시간 감사', directory, max_seconds=10)
            self.assertEqual(outcome['status'], 'RESEARCH_COMPLETED_EXPLORATORY')
            time_audit.program('T1_program', start, json.loads((directory/'state.json').read_bytes()), 0)

    def test_timeout(self):
        self.trial('T2_program')

    def test_supervisor_kill(self):
        self.trial('T5_program')

    def test_supervisor_recovers_after_expiry(self):
        self.trial('T5_late')

    def test_stopped_worker(self):
        self.trial('T6_program')

    def trial(self, case):
        goal = 'Study Treasury spread and SOFR. Whole goal ' + case
        arrived = threading.Event()
        release = threading.Event()
        calls = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(1)
                arrived.set()
                release.wait(15)
            def log_message(self, *_):
                pass
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as tmp, http.server.ThreadingHTTPServer(
                ('127.0.0.1', 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            directory = Path(tmp)
            base = f'http://127.0.0.1:{server.server_port}'
            (directory/'local_http_fixture.json').write_text(json.dumps({
                'scope':'LOCAL_LOOPBACK_TEST', 'goal_id':plan_goal(goal)['goal_id'],
                'uris':{'UST_2Y':base+'/treasury.csv','UST_10Y':base+'/treasury.csv','NYFED_SOFR':base+'/sofr.json'}}))
            child = None
            worker = None
            job = directory/'jobs/collect_ust_2y'
            def launch():
                process = multiprocessing.get_context('spawn').Process(target=run_research_program,
                    args=(goal, directory), kwargs={'max_seconds':300})
                process.start()
                return process
            start = time_audit.clock()
            try:
                run_research_program(goal, directory, max_tasks=3, max_seconds=10)
                original = json.loads((directory/'state.json').read_bytes())
                time.sleep(max(0, original['goal_deadline_monotonic'] - time.monotonic() - 5))
                child = launch()
                self.assertTrue(arrived.wait(4))
                worker = json.loads((job/'job.json').read_bytes())['worker_pid']
                if case.startswith('T5'):
                    child.kill()
                    child.join(2)
                    self.assertEqual(child.exitcode, -signal.SIGKILL)
                    if case == 'T5_late':
                        time.sleep(max(0, original['goal_deadline_monotonic'] - time.monotonic()) + .05)
                    child = launch()
                if case == 'T6_program':
                    os.kill(worker, signal.SIGSTOP)
                child.join(10)
                self.assertEqual(child.exitcode, 0)
                state = json.loads((directory/'state.json').read_bytes())
                end = json.loads((job/'job.json').read_bytes())
                self.assertEqual(calls, [1])
                self.assertEqual(end['attempts'], 1)
                self.assertIsNone(_worker_identity(worker, job.resolve()))
                self.assertEqual(state['network_requests_reserved'], 1)
                self.assertEqual(state['goal_deadline_monotonic'], original['goal_deadline_monotonic'])
                self.assertEqual(state['next_action'], 'GOAL_DEADLINE_EXHAUSTED')
                self.assertTrue((job/'data_recovery/data_recovery.json').is_file())
                grace = [e for e in end['events'] if e['event'].startswith('SHUTDOWN_GRACE')]
                self.assertEqual(len(grace), 2)
                time_audit.program(case, start, state, 2 if case.startswith('T5') else 1, grace=grace)
            finally:
                if child and child.is_alive():
                    child.kill()
                    child.join(2)
                if worker and _worker_identity(worker, job.resolve()) is not None:
                    os.kill(worker, signal.SIGKILL)
                release.set()
                server.shutdown()
                thread.join(2)
