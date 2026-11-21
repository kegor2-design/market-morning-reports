"""Common deadline observations for the program and single-job supervisor trials."""
import time
from datetime import datetime, timezone

from universal_agent.tests.fault_audit import export


def clock():
    return datetime.now(timezone.utc), time.monotonic()


def record(test_id, start, deadline, tasks, grace, restarts, boot, duplicates, budget, scope):
    wall, mono = clock()
    elapsed = mono - start[1]
    late = sum(datetime.fromisoformat(t['started_at_utc']) >=
               datetime.fromisoformat(t['task_deadline_utc']) for t in tasks)
    assert all(t['ended_at_utc'] and datetime.fromisoformat(t['ended_at_utc']) >=
               datetime.fromisoformat(t['started_at_utc']) for t in tasks)
    assert len(grace) % 2 == 0
    for begin, end in zip(grace[::2], grace[1::2]):
        assert begin['event'] == 'SHUTDOWN_GRACE_STARTED' and end['event'] == 'SHUTDOWN_GRACE_ENDED'
        assert 0 <= end['monotonic'] - begin['monotonic'] <= 2.1
    # 100 ms polling/scheduling tolerance plus 500 ms for reap and checkpoint I/O.
    assert elapsed <= (deadline - start[0]).total_seconds() + 2.6, (test_id, elapsed)
    assert late == duplicates == 0 and boot
    export(dict(test_id=test_id, scope=scope, goal_start_utc=start[0].isoformat(),
                deadline_utc=deadline.isoformat(), end_utc=wall.isoformat(), elapsed_seconds=elapsed,
                approved_budget_seconds=budget, remaining_seconds=max(0, (deadline-wall).total_seconds()),
                restarts=restarts, boot_id=boot, tasks=tasks, shutdown_grace=grace,
                post_deadline_starts=late, duplicates=duplicates, final_verdict='PASS'))


def job(test_id, start, deadline, state, restarts):
    events = state['events']
    starts = [e for e in events if e['event'] == 'WORKER_STARTED']
    ends = [e for e in events if e['event'] in ('WORKER_EXITED', 'SURVIVING_WORKER_EXITED')]
    assert len(starts) == len(ends) == 1
    tasks = [dict(started_at_utc=starts[0]['at_utc'], ended_at_utc=ends[0]['at_utc'],
                  task_deadline_utc=deadline.isoformat())]
    record(test_id, start, deadline, tasks, [e for e in events if e['event'].startswith('SHUTDOWN_GRACE')],
           restarts, state['deadline_boot_id'], state['duplicate_completion_count'],
           (deadline-start[0]).total_seconds(), 'single Research Job with outer Goal deadline')


def program(test_id, start, state, restarts, deadline=None):
    tasks = [{k: row[k] for k in ('selected', 'started_at_utc', 'ended_at_utc', 'task_deadline_utc')}
             for row in state['selection_history']]
    assert tasks
    record(test_id, start, deadline or datetime.fromisoformat(state['goal_deadline_utc']),
           tasks, [], restarts, state['goal_boot_id'], len(tasks)-len({t['selected'] for t in tasks}),
           state['goal_budget_seconds'], 'Research Program')
