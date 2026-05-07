---
description: Upgrade an existing dev-workflow install — present a gap diff against the latest templates, apply confirmed fixes idempotently. Aborts if no install is detected (use /dev-workflow:install instead).
---

Use the `upgrade` skill to upgrade the dev-workflow install on this project: $ARGUMENTS

The skill aborts if no `.claude/agents/<PREFIX>-dev.md` exists. For a fresh install, use `/dev-workflow:install`.
