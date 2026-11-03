---
name: setup
description: Prepare the current project for srun — give its secrets their own store ids (a namespace in .srun.json), list their names, and put the Secrets rule in CLAUDE.md. Use once per project, and again after a srun update to refresh the rule and the file's form. Safe to re-run.
---

# srun setup

Owns: a project's `.srun.json` and its `CLAUDE.md` `## Secrets` section. The rule text itself lives in `${CLAUDE_PLUGIN_ROOT}/scripts/secrets-rule.md`.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/srun" setup` from the project root (the full path, because `srun` is on PATH only in sessions started after the plugin was installed). Show the lines it printed.
2. Ask which secrets the project needs, if the user has not said, and where they keep them: `keychain`, `1password`, `dashlane`, `lastpass`, `aws` or `gcp`. Leaving it unset uses the user's own default (`srun default`), else the keychain — offer that first. A chosen store goes in with `srun setup --store STORE`.
3. List each NAME in `.srun.json` under `"secrets"`, a plain list. Never a value. Only a secret kept in a different store than the rest gets an object entry — see the plugin's `README.md`.
4. Tell the user where each value goes, using the store id `srun check` prints: for `keychain`, `aws`, `gcp` and `lastpass`, run `srun add NAME` in their own terminal (a hidden prompt); for `1password` and `dashlane`, create the item in that app as the README's Stores table says. Never ask for a value in chat.
5. Remind the user to commit `.srun.json` and `CLAUDE.md`, and to start a new session if `srun` is not yet on PATH.
