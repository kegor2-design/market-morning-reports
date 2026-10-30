# Bounded universal research supervisor

`supervisor.py` extends the Phase 3 Runner and Phase 2 evidence engine. The old
CLIs and checkpoints remain valid. Supervisor state uses schema version 3 in a
separate directory. Registry entries pin a manifest SHA; changing a registered
manifest requires explicit review and a new registration decision. A model
answer is recorded as a hypothesis, while registered evidence checks decide
whether a task is complete.

## Modes and example commands

These example commands run from `market-history/research/`. The private
state directory is owned by the research user. No `.env` file is sourced by the
supervisor. The price probe's optional source query uses the existing dedicated
read-only DB role and a 20-second SQL statement timeout.

```sh
umask 077
chmod 700 /home/kegor2/MyDream2000/research/universal_agent
python3 -m universal_agent.supervisor_cli inspect --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45
python3 -m universal_agent.supervisor_cli register --project universal_agent/regime190.supervisor.json --registry /home/kegor2/MyDream2000/research/universal_agent/registry.json
python3 -m universal_agent.supervisor_cli plan --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45
python3 -m universal_agent.supervisor_cli dry-run --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45
python3 -m universal_agent.supervisor_cli run-once --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45
python3 -m universal_agent.supervisor_cli run-bounded --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45 --max-tasks 3 --max-seconds 1800
python3 -m universal_agent.supervisor_cli resume --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45
python3 -m universal_agent.supervisor_cli status --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45
python3 -m universal_agent.supervisor_cli report --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45
python3 -m universal_agent.supervisor_cli stop --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45
python3 -m universal_agent.supervisor_cli recover --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45 --resolution clear-stop
# For a reviewed PAUSED read-only task only:
python3 -m universal_agent.supervisor_cli recover --project universal_agent/regime190.supervisor.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-phase45 --task-id TASK_ID --resolution retry
```

`stop` writes a private STOP marker without waiting for the project lock. The
current read-only child is allowed to finish or time out; no further task is
started. After reviewing status and the in-flight result, use
`recover --resolution clear-stop` to permit future runs. If a process died while RUNNING, `resume` marks it PAUSED and never
automatically repeats it. After reviewing the external outcome, an operator can
run `recover --task-id ID --resolution retry` for a read-only task, or use
`--resolution cancel`. An interrupted VERIFYING task is rechecked independently
without rerunning Codex. Corrupt or incompatible checkpoints fail closed.

The hard invocation caps are 30 minutes, three tasks, one concurrent task,
three attempts per task and the project manifest's stricter limits. Codex runs
with `codex exec --sandbox read-only --json --ephemeral` and a structured output
schema. The supervisor never changes Codex approval policy, security rules,
service state, or operating DB data. Approval risks become BLOCKED_APPROVAL.
Success criteria need explicit independent `success_checks`; free-text claims
cannot produce RESEARCH_COMPLETED. Financial CSV checks require source,
release, vintage, availability and as-of timestamps, and reject duplicates,
missing values, and future-available rows. Corporate actions, source parity,
costs, historical membership and walk-forward boundaries require their own
declared evidence fields or review gates; this generic check does not certify
them by itself.

`templates/` contains examples only. Neither systemd nor cron was installed or
enabled in this phase.
