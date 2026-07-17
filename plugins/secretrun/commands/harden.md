---
description: Merge secretrun's native hardening (S2) into settings.json — deny reads of secret files (.env, ~/.aws, ~/.ssh, gcloud, ~/.claude/projects), enable CLAUDE_CODE_SUBPROCESS_ENV_SCRUB, cut transcript retention. Pass --project (default) or --global. Timestamped backup first.
argument-hint: [--project | --global]
---

Harden this machine's Claude Code settings with secretrun's S2 layer. Plugins
cannot ship permission rules, so this merges them into your own settings.json.

Run (choose scope; default to `--project` if the user gave no argument):

```
secretrun-admin harden $ARGUMENTS
```

The command backs up the target `settings.json` to a timestamped `.bak-…` file,
then merges the snippet at `${CLAUDE_PLUGIN_ROOT}/settings/hardening-snippet.json`:
`permissions.deny` for `.env*`, `~/.aws`, `~/.ssh`, `~/.config/gcloud`, and
`~/.claude/projects`; `env.CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`; and
`cleanupPeriodDays: 7`. Existing permission entries are preserved (union, dedup);
a stricter `cleanupPeriodDays` you already set is kept.

After it runs, report the changes it printed. Note that `permissions.deny` and
`env` changes apply to **new** sessions. Mention the optional `sandbox` block in
the README (§ S2) as a manual, review-before-enabling step.
