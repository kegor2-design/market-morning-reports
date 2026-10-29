# Regime190 service audit, 2026-10-29 KST

The user `regime190-collection.service` was active and running with MainPID `1649143` after the tested read-only adapters were loaded. `regime190-publish.timer` was active and waiting, both units enabled, and `Linger=yes`. `systemd-analyze verify` passed for the installed collection and publisher units. No trading engine, Morning Publisher service, or operating DB schema was changed.

The old worker selected only `PENDING` or due `RETRY_WAIT` tasks. With 111 `NEEDS_REVIEW` and 79 `PARTIAL`, it emitted a heartbeat every five minutes but no new provider request after 2026-10-27 15:50 UTC. Publisher journal entries returned `NO_NEW_PROGRESS`; they were not proof of collection. The updated `--status` reads SQLite without the execution lock. On 2026-10-29 it showed the new derived data growing independently from the heartbeat, then 2,497 symbols and 4,605,978 source rows completed. The rate adapter added 325 dates for IDs 107–111. The checkpoint advanced to 92 `PARTIAL` and 98 `NEEDS_REVIEW`; `PIT_READY=0`.

Checkpoint `PRAGMA quick_check` returned `ok`. An online SQLite backup was made before the first adapter restart and another after the price adapter completed. The service was restarted twice only to load tested research code; the installed unit settings were not changed. The private per-symbol writer uses atomic file replacement, SHA-256 records, a 5 GiB free-space stop, and resumes from completed symbols. Its outputs and database credentials remain outside GitHub.

At inspection, root storage had about 47 GiB free and the HDD about 13 GiB free. The read-only DB connection was confirmed through the dedicated research credential file. Research publication remains separate from collection; a failed push cannot stop the collector.

Validation: Python compilation, three focused unit tests, one real-symbol DB smoke run, resume to a second symbol, private output SHA verification, rate formula/hash check, and live service PID/checkpoint increase all passed. `--status` succeeded while the service held its execution lock.
