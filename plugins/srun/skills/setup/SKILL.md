---
name: setup
description: Prepare the current project for srun — give its secrets their own store ids (a namespace in .srun.json) and put the Secrets rule in CLAUDE.md. Use once per project, and again after a srun update to refresh the rule. Safe to re-run.
---

# srun setup

Owns: a project's `.srun.json` namespace and its `CLAUDE.md` `## Secrets` section. The rule text itself lives in `${CLAUDE_PLUGIN_ROOT}/scripts/secrets-rule.md`.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/srun" setup` from the project root (the full path, because `srun` is on PATH only in sessions started after the plugin was installed). Show the lines it printed.
2. Ask which secrets the project needs, if the user has not said. Declare each NAME in `.srun.json` under `"secrets"` with its store — `{"backend": "keychain"}` (default), `"aws"`, `"gcp"`, or `{"cmd": "<command that prints the value>"}`. Never a value.
3. For each keychain, aws or gcp NAME, tell the user to run `srun add NAME` themselves (it opens a hidden dialog); a `cmd` NAME is stored in that secret manager. Never ask for a value in chat.
4. Remind the user to commit `.srun.json` and `CLAUDE.md`, and to start a new session if `srun` is not yet on PATH.

The plugin's `README.md` documents the stores, namespacing and `srun migrate`.
