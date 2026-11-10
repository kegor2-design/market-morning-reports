# Regime190 service audit, 2026-10-29 KST

The user `regime190-collection.service` was active and running with MainPID `1649143` after the tested read-only adapters were loaded. `regime190-publish.timer` was active and waiting, both units enabled, and `Linger=yes`. `systemd-analyze verify` passed for the installed collection and publisher units. No trading engine, Morning Publisher service, or operating DB schema was changed.

The old worker selected only `PENDING` or due `RETRY_WAIT` tasks. With 111 `NEEDS_REVIEW` and 79 `PARTIAL`, it emitted a heartbeat every five minutes but no new provider request after 2026-10-27 15:50 UTC. Publisher journal entries returned `NO_NEW_PROGRESS`; they were not proof of collection. The updated `--status` reads SQLite without the execution lock. On 2026-10-29 it showed the new derived data growing independently from the heartbeat, then 2,497 symbols and 4,605,978 source rows completed. The rate adapter added 325 dates for IDs 107–111. The checkpoint advanced to 92 `PARTIAL` and 98 `NEEDS_REVIEW`; `PIT_READY=0`.

Checkpoint `PRAGMA quick_check` returned `ok`. An online SQLite backup was made before the first adapter restart and another after the price adapter completed. The service was restarted twice only to load tested research code; the installed unit settings were not changed. The private per-symbol writer uses atomic file replacement, SHA-256 records, a 5 GiB free-space stop, and resumes from completed symbols. Its outputs and database credentials remain outside GitHub.

At inspection, root storage had about 47 GiB free and the HDD about 13 GiB free. The read-only DB connection was confirmed through the dedicated research credential file. Research publication remains separate from collection; a failed push cannot stop the collector.

Validation: Python compilation, five focused unit tests, one real-symbol DB smoke run, resume to a second symbol, private output SHA verification, rate formula/hash check, and live service PID/checkpoint increase all passed. `--status` succeeded while the service held its execution lock.

An additional bounded FRED initial-vintage adapter was added after the price and rate derivations. It stores one series per invocation with an atomic private JSON file and SHA-256 manifest, enforces a 16 MiB response cap and 5 GiB free-space floor, and spaces successful requests by 15 seconds in the service loop. The first real series, `BAMLC0A0CM`, returned 792 observations dated 2023-10-31 through 2026-10-27. These values remain `PIT_UNVERIFIED` because release hour and indicator-definition checks are outstanding. The adapter resumes from verified manifest files; a mock request/resume test passed.

The `DFEDTARL` initial-vintage request returned HTTP 400. The adapter records a private series-specific bad-request file and advances to the next series. This is not evidence that the provider or indicator is permanently blocked; the request parameters and historical coverage require review.

## 2026-11-11 KST continuation

The installed collection service was still active with MainPID 1651169 and the publish timer was enabled and waiting. The service heartbeat continued but its last new raw data remained at 2026-10-29 14:43 UTC, so heartbeat alone was not treated as collection progress. A separate transient user service, `regime190-fred-yearly-20261111.service`, began bounded yearly initial-vintage requests from a dedicated research worktree. It showed a live MainPID and private per-window progress. This job runs independently of SSH and the Codex session; a server reboot would require resuming it with the same command. The existing installed unit settings were not changed.

The first baseline transient job failed because its separate worktree lacked the ignored source CSVs. The retried job used an explicit source directory and completed successfully. Its output is an assumption-based index experiment, not a PIT-verified backtest. Root and HDD usage at the continuation were approximately 60% and 87%, with more than 5 GiB free on each filesystem.

A second independent transient user job, `regime190-ecos-rate-history-20261111.service`, was started after a one-page real API smoke test. It reads ECOS history using existing verified item codes, writes private page files and SHA-256 manifests, resumes at the next unverified page, and stops below 5 GiB free space. The first KTB 3Y page had 1,000 unique daily dates and unit `연%`; no operating database writes or installed unit changes were made.
