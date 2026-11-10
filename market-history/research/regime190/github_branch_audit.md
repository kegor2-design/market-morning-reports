# Git branch and Morning Report audit, 2026-10-29 KST

The Morning Publisher setting `MMP_PUBLIC_REPO_DIR` points to the same Git worktree that was checked out on `research/regime190-data-audit-20261027`. Its report publishing functions write `reports/YYYY-MM/`, commit and push the current branch without an explicit `main` branch guard. This explains why the 2026-10-28 and 2026-10-29 morning outlook commits went to the research branch. At inspection, `origin/main` ended at the 2026-10-27 report; both later reports existed only on the research branch.

A clean, separate local `main` worktree was created. The four missing report files were copied there without a commit or push. Every file's SHA-256 matched the research branch source, each JSON had the expected report date, `quality.passed=true`, and `analysis_meta.status=COMPLETED`. The operating Publisher setting and the remote `main` branch were left untouched pending the user's approval required by the continuation instructions. The intended setting is for `MMP_PUBLIC_REPO_DIR` to point to the dedicated `main` worktree, followed by a dry run and branch verification before the next report publication.

The Regime190 research code and metadata remain on `research/regime190-data-audit-20261027`. The latest published research code commit at this audit stage is `2c25eed`. Report history on the research branch has not been rewritten; no force push is planned.

## 2026-11-11 follow-up

The Publisher environment still points `MMP_PUBLIC_REPO_DIR` to the default research checkout. That checkout had moved to `research/autonomous-agent-v2-architecture-20261101`; morning reports through 2026-11-10 continued to land on research branches while `origin/main` remained at the 2026-10-27 report. The separate local `main` worktree now contains the 28 missing `.json` and `.md` report files dated 2026-10-28 through 2026-11-10. All 14 JSON reports had matching dates, `quality.passed=true`, and `analysis_meta.status=COMPLETED`; every copied file matched the source SHA-256. The files are untracked and have not been committed or pushed. Main publication and the Publisher environment change still await the user's approval required by Phase H.

The GitHub integration rejected Draft PR creation with HTTP 403 `Resource not accessible by integration`. The research branch itself accepted a normal non-force push. The Draft PR remains uncreated until the integration gains pull-request write permission or another authorized route is available.
