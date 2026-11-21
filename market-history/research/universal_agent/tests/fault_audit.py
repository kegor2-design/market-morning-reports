"""Independent observations of a loopback recovery trial; export hashes only."""
import hashlib
import json
import os
from pathlib import Path

from universal_agent.engine import canonical
from universal_agent.research_runtime import _load


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def files(directory, pattern):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.glob(pattern)) if p.is_file()}


def snapshot(directory):
    state = json.loads((directory / 'state.json').read_bytes())
    queue = _load(directory.parents[1] / 'state.json')
    return {
        'state': state, 'generation': queue['generation'], 'events': queue['events'],
        'queue_model_calls': queue['model_calls'],
        'sealed': {**files(directory, 'plan.json'), **files(directory, 'goal_contract.json')},
        'approval': files(directory, '*approval.json'),
        'jobs': files(directory, 'jobs/*/job.json'),
        'source': files(directory, 'jobs/*/data_recovery/source.*'),
        'requests': files(directory, 'jobs/*/data_recovery/data_recovery.json'),
        'completed': {k: v for k, v in state['records'].items()
                      if v['status'] in ('VERIFIED', 'COMPLETED_EXPLORATORY')},
    }


def export(row):
    destination = os.getenv('UNIVERSAL_AUDIT_DIR')
    if destination:
        path = Path(destination)
        path.mkdir(parents=True, exist_ok=True)
        (path / (row['test_id'] + '.json')).write_text(json.dumps(row, indent=2) + '\n')


def verify(test_id, directory, before, calls):
    after = snapshot(directory)
    old, new = before['state'], after['state']
    tx_path = directory / 'api_recovery_transaction_v1.json'
    tx = json.loads(tx_path.read_bytes()) if tx_path.exists() else {}
    rev = new.get('api_recovery_revision', {})
    violations = []
    def require(condition, field):
        if not condition:
            violations.append(field)
    for field in ('goal_id', 'goal_contract_sha256', 'plan_sha256'):
        require(old[field] == new[field], field)
    for field in ('sealed', 'approval', 'jobs', 'source', 'requests', 'completed'):
        require(bool(before[field]) and all(after[field].get(k) == v
                for k, v in before[field].items()), field)
    require(before['events'] == after['events'][:len(before['events'])] and
            after['generation'] >= before['generation'], 'generation')
    require(after['queue_model_calls'] == before['queue_model_calls'] ==
            old['model_calls'] == new['model_calls'] == 0, 'model ledger')
    original_dag = digest(old['tasks'])
    if tx:
        require(tx['previous_dag_sha256'] == original_dag and
                tx['revision_sha256'] == rev['sha256'] and tx['revision_sha256'] ==
                next(iter(files(directory, 'api_recovery_revision_v1.json').values())),
                'revision identity')
        rolled = rev['status'] == 'REVISION_ROLLED_BACK'
        require(tx['transaction_state'] == ('REVISION_ROLLED_BACK' if rolled else
                'REVISION_COMMITTED') and digest(new['tasks']) ==
                tx['previous_dag_sha256' if rolled else 'proposed_dag_sha256'] and
                new.get('active_revision_sha256') == (tx['previous_active_revision']
                if rolled else tx['revision_sha256']), 'active journal')
    else:
        require(test_id == 'R1' and not rev and original_dag == digest(new['tasks']),
                'unexpected missing journal')
    duplicates = sum(max(0, json.loads(p.read_bytes())['attempts'] - 1)
                     for p in directory.glob('jobs/*/job.json'))
    require(duplicates == 0 and all(v['attempts'] <= 1 for v in new['records'].values()),
            'duplicate task starts')
    require(calls == (3 if test_id == 'R1' else 4) ==
            new['network_requests_reserved'] + new.get('recovery_network_requests_reserved', 0),
            'request ledger vs observed HTTP calls')
    require(new['status'] in {'RESEARCH_BLOCKED', 'RESEARCH_COMPLETED_EXPLORATORY'},
            'terminal goal state')
    failure = 'jobs/collect_ust_2y/data_recovery/data_recovery.json'
    require(after['requests'][failure] == before['requests'][failure], 'original failure evidence')
    row = dict(test_id=test_id, goal_id=new['goal_id'], original_goal_hash=digest(old['plan']['research_goal']),
               contract_hash=old['goal_contract_sha256'], plan_hash=old['plan_sha256'],
               original_dag_hash=original_dag, active_revision_hash=new.get('active_revision_sha256'),
               source_hash=digest(before['source']), completed_task_hash=digest(before['completed']),
               approval_ledger_hash=digest(before['approval']), request_ledger_hash=digest(after['requests']),
               failure_evidence_hash=after['requests'][failure], observed_http_calls=calls,
               checkpoint_generation=[before['generation'], after['generation']], model_calls=new['model_calls'],
               duplicate_execution_count=duplicates, invariant_violations=violations,
               final_verdict='FAIL' if violations else 'PASS')
    export(row)
    if violations:
        raise AssertionError(row)
