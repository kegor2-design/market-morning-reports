# Release Notes — 1.6.5.2 Expert Historical Corpus

Additive overlay on 1.6.5.1. No DB migration and no cron modification in the overlay.

Added:

- historical expert corpus config for Chesley/Park Seik and Park Jong-hoon/KPUNCH
- VTT normalization and archive inventory
- coverage guards using known archive baselines
- claim schema and attribution rules
- reusable primitive consolidation
- NEW/REINFORCED/MODIFIED/CONTRADICTED delta classification
- point-in-time historical validation queue
- Event Intelligence read-only bridge that cannot promote truth status
- focused tests and deployment preflight contract

The actual server archive roots are deliberately not guessed. Codex deployment must locate them on the current server, verify counts, and persist only the resolved paths/config needed by the live project.
