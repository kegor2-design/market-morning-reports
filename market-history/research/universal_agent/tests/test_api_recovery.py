"""Real child-process DAG recovery against an approved loopback source fixture."""
import datetime
import contextlib
import hashlib
import http.server
import json
import multiprocessing
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from universal_agent.tests import fault_audit
from universal_agent import api_recovery, research_job, research_runtime
from universal_agent.api_recovery import authorize_local
from universal_agent.ai_research_planner import capability_registry
from universal_agent.engine import canonical, write_state
from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.research_planner import _task, dates_for, plan_goal
from universal_agent.research_runtime import submit
from universal_agent.problem_solver import recovery_capability_registry

GOAL = 'Study Treasury yield spread and SOFR from 2018-06-01 to 2018-06-29.'


def _kill_after_api_rollback(directory):
    from universal_agent import process_supervisor
    original = process_supervisor.write_state
    def checkpoint_then_kill(path, value):
        original(path, value)
        if (path.name == 'state.json' and
                value.get('api_recovery_revision', {}).get('status') ==
                'REVISION_ROLLED_BACK'):
            os.kill(os.getpid(), signal.SIGKILL)
    process_supervisor.write_state = checkpoint_then_kill
    research_runtime.run(directory.parents[1], max_jobs=1, max_seconds=120)


class ApiRecoveryDagTests(unittest.TestCase):
    def test_retry_after_is_bounded_and_parses_http_date(self):
        observed = '2026-11-18T00:00:00+00:00'
        self.assertEqual(api_recovery.retry_after_at('2', observed),
                         '2026-11-18T00:00:02+00:00')
        self.assertEqual(api_recovery.retry_after_at(
            'Wed, 18 Nov 2026 00:00:02 GMT', observed),
            '2026-11-18T00:00:02+00:00')
        for value in (None, '', 'abc', '26', '-1',
                      'Wed, 18 Nov 2026 00:01:00 GMT'):
            self.assertIsNone(api_recovery.retry_after_at(value, observed))

    def test_revision_prepare_failures_leave_original_state_intact(self):
        plan = plan_goal(GOAL)
        tasks = deepcopy(plan['tasks'])
        collect = _task('collect_ust_2y', 'DATA_ACQUISITION', 20,
                        dependencies=['discover_ust_2y'], inputs={'series': 'UST_2Y'})
        tasks.append(collect)
        tasks[3]['dependencies'].append('collect_ust_2y')
        state = {'goal_id': plan['goal_id'], 'plan_sha256': 'plan-hash',
                 'goal_contract_sha256': 'contract-hash', 'tasks': tasks,
                 'records': {task['task_id']: {'status': 'VERIFIED', 'attempts': 1}
                             for task in tasks}, 'network_requests_reserved': 1,
                 'replanning_history': []}
        state['records']['analyze_rates'] = {'status': 'WAITING_DEPENDENCY', 'attempts': 0}
        state['records']['collect_ust_2y'] = {'status': 'BLOCKED_ENV', 'attempts': 1}
        evidence = {'series': 'UST_2Y', 'original_task_id': 'collect_ust_2y',
                    'original_request_sha256': 'a' * 64,
                    'error_evidence_sha256': 'error-hash', 'recovery_reason': 'HTTP 503',
                    'solution_action': 'RETRY_APPROVED_SOURCE_NEW_REQUEST'}
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            write_state(directory / 'api_recovery_approval.json', {'approved': True})
            original = deepcopy(state)
            real_write = api_recovery.write_state
            def fail_journal(path, value):
                if path.name == 'api_recovery_transaction_v1.json':
                    raise OSError('injected journal failure')
                return real_write(path, value)
            with mock.patch.object(api_recovery, 'diagnose', return_value=evidence), \
                 mock.patch.object(api_recovery, 'validate_approval', return_value={
                     'approved': True}), \
                 mock.patch.object(api_recovery, 'write_state', side_effect=fail_journal):
                with self.assertRaisesRegex(OSError, 'injected journal failure'):
                    api_recovery.replan(plan, state, directory)
            self.assertEqual(state, original)
            with mock.patch.object(api_recovery, 'diagnose', return_value=evidence), \
                 mock.patch.object(api_recovery, 'validate_approval', return_value={
                     'approved': True}):
                self.assertTrue(api_recovery.replan(plan, state, directory))
            self.assertEqual(state['api_recovery_revision']['status'], 'REVISION_PREPARED')
            write_state(directory / 'state.json', state)
            def fail_commit(path, value):
                if path.name == 'api_recovery_transaction_v1.json':
                    raise OSError('injected pre-commit failure')
                return real_write(path, value)
            with mock.patch.object(api_recovery, 'write_state', side_effect=fail_commit):
                with self.assertRaisesRegex(OSError, 'injected pre-commit failure'):
                    api_recovery.finalize_transaction(state, directory)
            self.assertEqual(state['api_recovery_revision']['status'], 'REVISION_PREPARED')
            self.assertEqual(json.loads((directory / 'state.json').read_text())[
                'api_recovery_revision']['status'], 'REVISION_PREPARED')
            api_recovery.finalize_transaction(state, directory)
            self.assertEqual(state['api_recovery_revision']['status'], 'REVISION_ACTIVE')
            # The journal may commit before the active checkpoint is rewritten.
            # Reopening that prepared checkpoint must finish the same revision.
            interrupted = json.loads((directory / 'state.json').read_text())
            self.assertEqual(interrupted['api_recovery_revision']['status'],
                             'REVISION_PREPARED')
            api_recovery.finalize_transaction(interrupted, directory)
            self.assertEqual(interrupted['api_recovery_revision']['status'],
                             'REVISION_ACTIVE')
            self.assertEqual(interrupted['active_revision_sha256'],
                             state['active_revision_sha256'])
            snapshot = deepcopy(interrupted)
            with mock.patch.object(api_recovery, 'diagnose', return_value=evidence), \
                 mock.patch.object(api_recovery, 'validate_approval', return_value={
                     'approved': True}):
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    api_recovery.replan(plan, interrupted, directory)
            self.assertEqual(interrupted, snapshot)
            tx_path = directory / 'api_recovery_transaction_v1.json'
            changed = json.loads(tx_path.read_text())
            changed['previous_analysis_record']['attempts'] = 99
            write_state(tx_path, changed)
            with self.assertRaisesRegex(ValueError, 'transaction identity changed'):
                api_recovery.finalize_transaction(state, directory)

    def test_recovery_registry_has_separate_api_permission(self):
        capabilities = recovery_capability_registry()['capabilities']
        self.assertEqual(set(capabilities), {'CALENDAR_MISMATCH',
                                             'SCHEMA_MISMATCH', 'API_ERROR',
                                             'CODE_ERROR'})
        self.assertEqual(capabilities['API_ERROR']['permission'],
                         'EXPLICIT_LOCAL_FIXTURE_APPROVAL')
        self.assertEqual(capabilities['API_ERROR']['network_budget'], 1)
        self.assertEqual(capability_registry()['capabilities']['API_RECOVERY_RETRY'][
                         'execution_permission'], 'EXPLICIT_LOCAL_FIXTURE_APPROVAL')

    def test_503_recovery_resumes_original_goal_and_never_replays(self):
        self._exercise_recovery(503, persist=os.environ.get(
            'UNIVERSAL_KEEP_API_E2E') == '1')

    def test_429_requires_new_approval_then_resumes(self):
        self._exercise_recovery(429)

    def test_429_retry_after_delay_survives_queue_restart(self):
        self._exercise_recovery(429, retry_after='15')

    def test_404_is_not_promoted_to_recovery_task(self):
        self._exercise_recovery(404)

    def test_connection_reset_remains_uncertain_and_blocks_recovery(self):
        self._exercise_recovery('RESET')

    def test_timeout_remains_uncertain_and_blocks_recovery(self):
        self._exercise_recovery('TIMEOUT')

    def test_bad_200_recovery_does_not_resume_analysis(self):
        self._exercise_recovery(503, bad_recovery=True)

    def test_api_recovery_analysis_verification_failure_rolls_back(self):
        self._exercise_recovery(503, bad_analysis=True)

    def test_api_rollback_supervisor_sigkill_finishes_on_restart(self):
        self._exercise_recovery(503, bad_recovery=True, kill_rollback=True)

    def test_sigkill_during_recovery_preserves_uncertain_request(self):
        self._exercise_recovery(503, kill_recovery=True)

    def test_tampered_approval_cannot_create_recovery_task(self):
        self._exercise_recovery(503, tamper_approval=True)

    def test_journal_write_failure_with_real_checkpoint(self):
        self._exercise_recovery(503, transaction_fault='R2')

    def test_commit_interruption_with_real_checkpoint(self):
        self._exercise_recovery(503, transaction_fault='R3')

    def test_duplicate_revision_with_real_checkpoint(self):
        self._exercise_recovery(503, transaction_fault='R7')

    def _exercise_recovery(self, first_status, bad_recovery=False,
                           kill_recovery=False, tamper_approval=False,
                           persist=False, retry_after='0', bad_analysis=False,
                           kill_rollback=False, transaction_fault=None):
        plan = plan_goal(GOAL)
        days = dates_for(plan)
        csv = ('Date,2 Yr,10 Yr\n' + ''.join(
            f'{datetime.date.fromisoformat(day):%m/%d/%y},{2 + i / 100:.2f},'
            f'{3 + i / 100:.2f}\n' for i, day in enumerate(days))).encode()
        sofr = json.dumps({'refRates': [
            {'effectiveDate': day, 'type': 'SOFR', 'percentRate':
             round(1.8 + i / 100, 2)} for i, day in enumerate(days)]}).encode()
        requests = []
        recovery_arrived = threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                failed = self.path == '/treasury.csv' and requests.count('/treasury.csv') == 1
                if failed and first_status == 'RESET':
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if failed and first_status == 'TIMEOUT':
                    time.sleep(2)
                if kill_recovery and self.path == '/treasury.csv' and \
                        requests.count('/treasury.csv') == 3:
                    recovery_arrived.set()
                    time.sleep(4)
                body = (b'' if failed else
                        b'bad csv' if bad_recovery and self.path == '/treasury.csv'
                        and requests.count('/treasury.csv') == 3 else
                        csv if self.path == '/treasury.csv' else sofr)
                self.send_response(first_status if failed and
                                   isinstance(first_status, int) else 200)
                if failed and first_status == 429:
                    self.send_header('Retry-After', retry_after)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if body:
                    try:
                        self.wfile.write(body)
                    except BrokenPipeError:
                        pass
            def log_message(self, *_):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        evidence_dir = PRIVATE_ROOT / 'session_c_api_recovery_e2e'
        if persist and evidence_dir.exists():
            raise ValueError('Persistent API E2E checkpoint already exists')
        context = (contextlib.nullcontext(str(evidence_dir)) if persist else
                   tempfile.TemporaryDirectory(dir=PRIVATE_ROOT))
        with context as folder:
            queue_dir = Path(folder)
            audit_id = (transaction_fault or ('R1' if tamper_approval else 'R4' if kill_recovery
                else 'R8' if kill_rollback else 'R5' if bad_recovery else 'R6' if bad_analysis else None))
            goal = GOAL if audit_id is None else GOAL + ' Trial ' + audit_id
            plan = plan_goal(goal)
            job = submit(goal, queue_dir)
            program_dir = queue_dir / 'programs' / job['goal_id']
            program_dir.mkdir(parents=True, exist_ok=True)
            uris = {'UST_2Y': f'http://127.0.0.1:{server.server_port}/treasury.csv',
                    'UST_10Y': f'http://127.0.0.1:{server.server_port}/treasury.csv',
                    'NYFED_SOFR': f'http://127.0.0.1:{server.server_port}/sofr.json'}
            fixture = {'scope': 'LOCAL_LOOPBACK_TEST', 'goal_id': job['goal_id'],
                       'uris': uris}
            if first_status == 'TIMEOUT':
                fixture['request_timeout_seconds'] = 1
            (program_dir / 'local_http_fixture.json').write_text(json.dumps(fixture))
            self.assertEqual(self._run(queue_dir)['statuses'][job['goal_id']], 'BLOCKED_ENV')
            first = json.loads((program_dir / 'state.json').read_text())
            self.assertEqual(first['network_requests_reserved'], 3)
            self.assertEqual(first['records']['collect_ust_2y']['status'], 'BLOCKED_ENV')
            original_hash = hashlib.sha256(canonical(first['plan']['goal_contract'])).hexdigest()
            original_job = program_dir / 'jobs' / 'collect_ust_2y' / 'job.json'
            original_job_sha = hashlib.sha256(original_job.read_bytes()).hexdigest()
            self.assertEqual(self._run(queue_dir)['processed'], 0)
            self.assertEqual(len(requests), 3)
            expires = (datetime.datetime.now(datetime.timezone.utc) +
                       datetime.timedelta(hours=1)).isoformat()
            if first_status in (404, 'RESET', 'TIMEOUT'):
                with self.assertRaisesRegex(ValueError, 'No eligible API failure'):
                    authorize_local(plan, first, program_dir,
                                    approved_by='LOCAL_TEST_OWNER', valid_until_utc=expires)
                self.assertEqual(self._run(queue_dir)['processed'], 0)
                self.assertEqual(len(requests), 3)
                self.assertFalse((program_dir / 'api_recovery_revision_v1.json').exists())
                if first_status in ('RESET', 'TIMEOUT'):
                    source = json.loads((program_dir / 'jobs' / 'collect_ust_2y' /
                        'data_recovery' / 'data_recovery.json').read_text())
                    self.assertEqual(source['network_call_outcome'],
                                     'UNCERTAIN_REQUEST_OUTCOME')
                    self.assertEqual(source['problem_type'],
                                     'TIMEOUT' if first_status == 'TIMEOUT' else
                                     'CONNECTION_RESET')
                return
            authorize_local(plan, first, program_dir, approved_by='LOCAL_TEST_OWNER',
                            valid_until_utc=expires)
            if first_status == 429 and retry_after != '0':
                waiting = self._run(queue_dir)
                self.assertEqual(waiting['processed'], 0)
                self.assertEqual(waiting['statuses'][job['goal_id']], 'RETRY_WAIT')
                queued = json.loads((queue_dir / 'state.json').read_text())
                self.assertTrue(queued['jobs'][job['goal_id']]['next_eligible_retry_at'])
                self.assertEqual(len(requests), 3)
                eligible = datetime.datetime.fromisoformat(
                    queued['jobs'][job['goal_id']]['next_eligible_retry_at'])
                time.sleep(max(0, (eligible - datetime.datetime.now(
                    datetime.timezone.utc)).total_seconds()) + 0.1)
            def audit(**observation):
                fault_audit.verify(audit_id, program_dir, before, len(requests), observation)

            before = fault_audit.snapshot(program_dir)
            if transaction_fault:
                if transaction_fault == 'R7':
                    self._run(queue_dir)
                    active = json.loads((program_dir / 'state.json').read_bytes())
                    checkpoint_before = deepcopy(active)
                    with self.assertRaisesRegex(ValueError, 'already exists') as refusal:
                        api_recovery.replan(plan, active, program_dir)
                    self.assertEqual(checkpoint_before, active)
                    observation = {'duplicate_rejection': str(refusal.exception)}
                else:
                    state = deepcopy(first)
                    real_write = api_recovery.write_state
                    def fail_write(path, value):
                        if path.name == 'api_recovery_transaction_v1.json':
                            raise OSError('audit journal fault')
                        real_write(path, value)
                    if transaction_fault == 'R2':
                        with mock.patch.object(api_recovery, 'write_state', side_effect=fail_write):
                            with self.assertRaisesRegex(OSError, 'audit journal fault'):
                                api_recovery.replan(plan, state, program_dir)
                        observation = {'journal_absent_after_failed_write': not (program_dir /
                            'api_recovery_transaction_v1.json').exists(), 'state_unchanged': state == first}
                        self.assertEqual(state, first)
                        self.assertFalse((program_dir / 'api_recovery_transaction_v1.json').exists())
                        self._run(queue_dir)
                    else:
                        finalize = api_recovery.finalize_transaction
                        interruptions = []
                        def interrupt_once(candidate, directory):
                            if not interruptions:
                                with mock.patch.object(api_recovery, 'write_state', side_effect=fail_write):
                                    with self.assertRaisesRegex(OSError, 'audit journal fault'):
                                        finalize(candidate, directory)
                                saved = json.loads((directory / 'state.json').read_bytes())
                                self.assertEqual(saved, candidate)
                                self.assertEqual(candidate['api_recovery_revision']['status'], 'REVISION_PREPARED')
                                interruptions.append(saved['api_recovery_revision']['sha256'])
                            finalize(candidate, directory)
                        with mock.patch.object(api_recovery, 'finalize_transaction', side_effect=interrupt_once):
                            research_runtime.run(queue_dir, max_jobs=1, max_seconds=120)
                        self.assertEqual(len(interruptions), 1)
                        observation = {'interrupted_prepared_revision': interruptions[0]}
                audit(**observation)
                return
            if tamper_approval:
                approval_path = program_dir / 'api_recovery_approval.json'
                approval = json.loads(approval_path.read_text())
                # Keep the issued record as well as the intentionally rejected presentation.
                (program_dir / 'issued_approval.json').write_bytes(approval_path.read_bytes())
                issued_hash = before['approval']['api_recovery_approval.json']
                approval['max_network_requests'] = 2
                approval_path.write_text(json.dumps(approval))
                before = fault_audit.snapshot(program_dir)
                self.assertEqual(self._run(queue_dir)['processed'], 0)
                self.assertEqual(len(requests), 3)
                self.assertFalse((program_dir / 'api_recovery_revision_v1.json').exists())
                self.assertEqual(before['approval']['issued_approval.json'], issued_hash)
                audit(issued_approval_sha256=issued_hash, rejected_budget=approval['max_network_requests'])
                return
            if kill_recovery:
                env = {'PATH': '/usr/bin:/bin',
                       'PYTHONPATH': str(Path(__file__).resolve().parents[2])}
                process = subprocess.Popen([sys.executable, '-m',
                    'universal_agent.research_runtime', 'run', '--queue-dir',
                    str(queue_dir), '--max-jobs', '1', '--max-seconds', '120'],
                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True)
                self.assertTrue(recovery_arrived.wait(20))
                child_path = program_dir / 'jobs' / 'api_recover_ust_2y' / 'job.json'
                deadline = time.monotonic() + 5
                pid = None
                while time.monotonic() < deadline:
                    if child_path.is_file():
                        pid = json.loads(child_path.read_text()).get('worker_pid')
                        if pid:
                            break
                    time.sleep(0.05)
                self.assertIsNotNone(pid)
                os.kill(pid, signal.SIGKILL)
                output, error = process.communicate(timeout=40)
                self.assertEqual(process.returncode, 0, error)
                self.assertEqual(json.loads(output)['statuses'][job['goal_id']],
                                 'BLOCKED_ENV')
                saved = json.loads((program_dir / 'state.json').read_text())
                self.assertEqual(saved['goal_id'], job['goal_id'])
                self.assertEqual(saved['recovery_network_requests_reserved'], 1)
                self.assertEqual(self._run(queue_dir)['processed'], 0)
                self.assertEqual(len(requests), 4)
                killed_job = json.loads(child_path.read_bytes())
                self.assertIn(-signal.SIGKILL, [e.get('exit_code') for e in killed_job['events']])
                audit(worker_exit=-signal.SIGKILL, recovery_reservations=saved['recovery_network_requests_reserved'])
                return
            if bad_recovery:
                if kill_rollback:
                    child = multiprocessing.get_context('spawn').Process(
                        target=_kill_after_api_rollback, args=(program_dir,))
                    child.start()
                    child.join(timeout=30)
                    if child.is_alive():
                        child.kill()
                        child.join()
                        self.fail('API rollback Supervisor did not stop')
                    self.assertEqual(child.exitcode, -signal.SIGKILL)
                    interrupted = json.loads((program_dir / 'state.json').read_text())
                    self.assertEqual(interrupted['tasks'], first['tasks'])
                    self.assertEqual(interrupted['goal_id'], first['goal_id'])
                    self.assertEqual(interrupted['api_recovery_revision']['status'],
                                     'REVISION_ROLLED_BACK')
                    self.assertEqual(json.loads((program_dir /
                        'api_recovery_transaction_v1.json').read_text())[
                            'transaction_state'], 'REVISION_COMMITTED')
                    resumed = self._run(queue_dir)
                    self.assertEqual(resumed['statuses'][job['goal_id']], 'BLOCKED_ENV')
                    self.assertEqual(json.loads((program_dir /
                        'api_recovery_transaction_v1.json').read_text())[
                            'transaction_state'], 'REVISION_ROLLED_BACK')
                    self.assertEqual(json.loads((program_dir / 'state.json').read_text())[
                        'records']['analyze_rates']['attempts'], 0)
                    self.assertEqual(len(requests), 4)
                    audit(supervisor_exit=child.exitcode, interrupted_journal='REVISION_COMMITTED',
                          interrupted_state=interrupted['api_recovery_revision']['status'])
                    return
                outcome = self._run(queue_dir)['statuses'][job['goal_id']]
                queue = json.loads((queue_dir / 'state.json').read_text())
                self.assertEqual(outcome, 'BLOCKED_ENV', msg=str(queue['jobs'][job['goal_id']]))
                blocked = json.loads((program_dir / 'state.json').read_text())
                self.assertEqual(blocked['api_recovery_revision']['status'],
                                 'REVISION_ROLLED_BACK')
                self.assertEqual(blocked['retired_recovery_tasks'][0]['record']['status'],
                                 'BLOCKED_EVIDENCE')
                self.assertEqual(hashlib.sha256(canonical(blocked['tasks'])).hexdigest(),
                                 hashlib.sha256(canonical(first['tasks'])).hexdigest())
                transaction = json.loads((program_dir /
                    'api_recovery_transaction_v1.json').read_text())
                self.assertEqual(transaction['transaction_state'],
                                 'REVISION_ROLLED_BACK')
                self.assertEqual(blocked['recovery_network_requests_reserved'], 1)
                self.assertNotEqual(blocked['records']['analyze_rates']['status'],
                                    'COMPLETED_EXPLORATORY')
                self.assertEqual(self._run(queue_dir)['processed'], 0)
                self.assertEqual(len(requests), 4)
                audit(retired_status=blocked['retired_recovery_tasks'][0]['record']['status'],
                      malformed_response_sha256=hashlib.sha256(b'bad csv').hexdigest())
                return
            if bad_analysis:
                original_verify = research_job.verify_artifact
                def fail_independent_analysis(manifest, job_plan, state_dir):
                    item = original_verify(manifest, job_plan, state_dir)
                    if manifest['mode'] == 'rate_analysis':
                        raise ValueError('injected independent analysis mismatch')
                    return item
                with mock.patch.object(research_job, 'verify_artifact',
                                       side_effect=fail_independent_analysis):
                    outcome = research_runtime.run(queue_dir, max_jobs=1, max_seconds=120)
                self.assertEqual(outcome['statuses'][job['goal_id']], 'BLOCKED_ENV')
                blocked = json.loads((program_dir / 'state.json').read_text())
                self.assertEqual(blocked['tasks'], first['tasks'])
                self.assertEqual(blocked['goal_id'], first['goal_id'])
                self.assertEqual(blocked['plan_sha256'], first['plan_sha256'])
                self.assertEqual(blocked['goal_contract_sha256'],
                                 first['goal_contract_sha256'])
                self.assertEqual(blocked['api_recovery_revision']['status'],
                                 'REVISION_ROLLED_BACK')
                self.assertEqual(blocked['retired_recovery_tasks'][0][
                    'record']['status'], 'VERIFIED')
                self.assertEqual(blocked['retired_recovery_tasks'][0][
                    'analysis_record']['status'], 'FAILED')
                self.assertEqual(blocked['records']['analyze_rates']['attempts'], 0)
                self.assertEqual(blocked['recovery_network_requests_reserved'], 1)
                self.assertEqual(blocked['network_requests_reserved'], 3)
                self.assertEqual(len(requests), 4)
                audit(retired_analysis_status=blocked['retired_recovery_tasks'][0]['analysis_record']['status'],
                      retired_recovery_status=blocked['retired_recovery_tasks'][0]['record']['status'])
                return
            self.assertEqual(self._run(queue_dir)['statuses'][job['goal_id']],
                             'COMPLETED_EXPLORATORY')
            second = json.loads((program_dir / 'state.json').read_text())
            revision = json.loads((program_dir / 'api_recovery_revision_v1.json').read_text())
            transaction = json.loads((program_dir /
                'api_recovery_transaction_v1.json').read_text())
            self.assertEqual(transaction['transaction_state'], 'REVISION_COMMITTED')
            self.assertEqual(second['api_recovery_revision']['status'], 'REVISION_ACTIVE')
            self.assertEqual(second['goal_id'], job['goal_id'])
            self.assertEqual(second['goal_contract_sha256'], original_hash)
            self.assertEqual(second['plan_sha256'], first['plan_sha256'])
            self.assertEqual(hashlib.sha256(original_job.read_bytes()).hexdigest(),
                             original_job_sha)
            self.assertNotEqual(revision['new_request_id'],
                                revision['original_request_sha256'][:24])
            self.assertEqual(revision['additional_network_budget'], 1)
            self.assertEqual(second['records']['collect_ust_2y']['status'], 'BLOCKED_ENV')
            self.assertEqual(second['records']['api_recover_ust_2y']['status'], 'VERIFIED')
            self.assertEqual(second['records']['analyze_rates']['status'],
                             'COMPLETED_EXPLORATORY')
            self.assertEqual(second['network_requests_reserved'], 3)
            self.assertEqual(second['recovery_network_requests_reserved'], 1)
            report = json.loads((program_dir / 'research_report.json').read_text())
            self.assertTrue(report['analysis']['fixture_only'])
            self.assertFalse(report['official_market_claim'])
            self.assertEqual(report['analysis']['validation']['accuracy'], 1.0)
            self.assertEqual(report['analysis']['source_sha256'], {
                'UST_2Y': hashlib.sha256(csv).hexdigest(),
                'UST_10Y': hashlib.sha256(csv).hexdigest(),
                'NYFED_SOFR': hashlib.sha256(sofr).hexdigest()})
            count = len(requests)
            self.assertEqual(count, 4)
            self.assertEqual(self._run(queue_dir)['processed'], 0)
            self.assertEqual(len(requests), count)

    @staticmethod
    def _run(queue_dir):
        env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).resolve().parents[2])}
        result = subprocess.run([sys.executable, '-m', 'universal_agent.research_runtime',
            'run', '--queue-dir', str(queue_dir), '--max-jobs', '1',
            '--max-seconds', '120'], env=env, capture_output=True, text=True,
            timeout=150)
        if result.returncode:
            raise AssertionError(result.stderr)
        return json.loads(result.stdout)


if __name__ == '__main__':
    unittest.main()
