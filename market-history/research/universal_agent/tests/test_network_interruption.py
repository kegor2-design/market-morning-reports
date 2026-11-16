"""Local HTTP process kills around a real read-only source response."""
import json
import multiprocessing
import os
import signal
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import urlopen

from universal_agent import data_recovery
from universal_agent.research_job import PRIVATE_ROOT


PAYLOAD = b'Date,2 Yr\n04/03/18,2.28\n'


def _child(request, state_dir, url, mode, at_checkpoint):
    def fetch(_uri, _attempts, _seconds):
        if mode == 'before_request':
            at_checkpoint.set()
            time.sleep(10)
        with urlopen(url, timeout=5) as response:
            payload = response.read()
        if mode == 'before_persist':
            at_checkpoint.set()
            time.sleep(10)
        return payload, 1
    original = data_recovery.write_state
    if mode == 'sealed':
        def paused(path, state):
            if (path == state_dir / 'data_recovery.json' and
                    state.get('content_sha256') and
                    (state_dir / 'source_receipt.json').exists()):
                at_checkpoint.set()
                time.sleep(10)
            original(path, state)
        data_recovery.write_state = paused
    data_recovery.recover(request, state_dir, fetch=fetch)


class NetworkInterruptionTests(unittest.TestCase):
    def setUp(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=PRIVATE_ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.request = {'goal_id': 'network_test', 'job_id': 'network_test',
            'task_id': 'collect_ust_2y', 'series': 'UST_2Y', 'market': 'US',
            'unit': 'percent', 'start': '2018-04-03', 'end': '2018-04-03',
            'expected_dates': ['2018-04-03'], 'existing': {},
            'allowed_sources': ['US_TREASURY'], 'budget': {
                'max_network_requests': 1, 'max_seconds': 10,
                'max_retries': 0, 'max_model_calls': 0}}
        self.received = threading.Event()
        self.release = threading.Event()
        self.count = 0
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.count += 1
                owner.received.set()
                owner.release.wait(5)
                try:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(PAYLOAD)
                except BrokenPipeError:
                    pass
            def log_message(self, *_args):
                pass
        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def run_kill(self, mode):
        state_dir = self.root / 'state'
        context = multiprocessing.get_context('spawn')
        event = context.Event()
        url = f'http://127.0.0.1:{self.server.server_port}/source.csv'
        worker = context.Process(target=_child,
            args=(self.request, state_dir, url, mode, event))
        worker.start()
        try:
            if mode == 'before_request':
                self.assertTrue(event.wait(5))
            else:
                self.assertTrue(self.received.wait(5))
                self.release.set()
            if mode in {'before_persist', 'sealed'}:
                self.assertTrue(event.wait(5))
            os.kill(worker.pid, signal.SIGKILL)
            worker.join(5)
            self.assertEqual(worker.exitcode, -signal.SIGKILL)
        finally:
            self.release.set()
            if worker.is_alive():
                worker.kill()
                worker.join()
        def no_retry(*_args):
            self.fail('Uncertain external request was replayed')
        result = data_recovery.recover(self.request, state_dir, fetch=no_retry)
        self.assertEqual(self.count, 0 if mode == 'before_request' else 1)
        return result, state_dir

    def test_request_received_without_response_blocks_replay(self):
        result, state_dir = self.run_kill('waiting_response')
        self.assertEqual(result['status'], 'BLOCKED_UNCERTAIN_API_CALL')
        self.assertFalse((state_dir / 'source_receipt.json').exists())

    def test_sealed_response_resumes_without_network_replay(self):
        result, state_dir = self.run_kill('sealed')
        self.assertEqual(result['status'], 'DATA_RECOVERED_PIT_UNVERIFIED')
        receipt = json.loads((state_dir / 'source_receipt.json').read_text())
        self.assertEqual(receipt['content_sha256'], result['content_sha256'])

    def test_killed_before_request_still_preserves_reserved_budget(self):
        result, _state_dir = self.run_kill('before_request')
        self.assertEqual(result['status'], 'BLOCKED_UNCERTAIN_API_CALL')
        self.assertEqual(self.count, 0)

    def test_response_received_before_persistence_blocks_replay(self):
        result, state_dir = self.run_kill('before_persist')
        self.assertEqual(result['status'], 'BLOCKED_UNCERTAIN_API_CALL')
        self.assertFalse((state_dir / 'source_receipt.json').exists())


if __name__ == '__main__':
    unittest.main()
