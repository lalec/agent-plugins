# Install — Phase 3b: hooks, governed-paths.conf, settings.json, headless shifts, allowance

> Paths of the form `../../shared/<file>` are relative to the install skill's directory (`plugins/dev-workflow/skills/install/`), i.e. the plugin's `shared/`.

Read `tpl-skill-guard.md` for all templates.

**Step 1 — Create `governed-paths.conf`**

Create `.claude/hooks/governed-paths.conf` from the template in `tpl-skill-guard.md § governed-paths.conf`, substituting:
- `<GOVERNED_ROOTS>` → ERE alternation of the paths from `CATEGORY_MAP` belonging to **Frontend, Backend, Database/storage, Auth, Observability, and Third-party SDK** categories (see `tpl-skill-guard.md § How to generate` for an example). **Never use extension globs** (e.g. `.*\.(html|css|js)$`) — these match files outside the project directory (such as `/tmp/`), defeating the guard. Root-level files like `index.html` are owned via explicit `PATH_MAP` entries, not via `GOVERNED_ROOTS`.
- `<DEPLOY_PATHS>` → ERE alternation of **every path from `CATEGORY_MAP` belonging to IaC, CI/CD, Build tooling, or Deployment scripts/config** (see `tpl-skill-guard.md § How to generate` for an example). Independent of `PATH_MAP` ownership — a path can be in `DEPLOY_PATHS` AND owned by a non-deploy skill (a deployment config file may live under the backend skill's ownership and still belong in `DEPLOY_PATHS`; both are correct). Drift watching and ownership are separate concerns. Set to `''` only if no IaC/CI/CD/Build/Deployment categories were discovered — `ref-sync-check.sh` then silently skips the deploy-drift check.
- `<PATH_MAP_ENTRIES>` → one `'PATTERN:SKILL'` entry per confirmed domain skill **plus** one entry for `<PREFIX>-deploy` covering the IaC/CI/CD/Build/Deployment paths from `CATEGORY_MAP` (omit the `<PREFIX>-deploy` entry only when no such categories were discovered). Standard catch-alls go at the end (see `tpl-skill-guard.md § How to generate governed-paths.conf`).
- `<SKILL_SELF_OWNERSHIP_ENTRIES>` → one `'^\.claude/skills/<PREFIX>-<name>/:<PREFIX>-<name>'` entry per installed skill (all lifecycle + domain skills from this run), placed before the `.claude/skills/` catch-all.
- `<REF_WATCH>` → ERE alternation of reference-worthy source paths derived from `CATEGORY_MAP` (Backend route/handler dirs, schema/model files, Auth paths). Set `''` when nothing clearly reference-worthy is identifiable.
- `<COPY_PATHS>` → the Frontend category's paths from `CATEGORY_MAP` when `<PREFIX>-design` was created; `''` otherwise.

This is the **only** file that should contain path→skill mappings. Do not duplicate patterns in hook scripts.

**Step 2 — Create hook scripts**

Create all 12 hooks from their templates in `tpl-skill-guard.md`. Substitute `<PREFIX>` throughout:

| Hook | Template section |
|---|---|
| `skill-guard.sh` | § skill-guard.sh |
| `path-coverage-check.sh` | § path-coverage-check.sh |
| `dependency-guard.sh` | § dependency-guard.sh |
| `package-edit-guard.sh` | § package-edit-guard.sh |
| `pre-handoff-check.sh` | § pre-handoff-check.sh |
| `close-out-gate.sh` | § close-out-gate.sh |
| `ref-sync-check.sh` | § ref-sync-check.sh |
| `skill-mark.sh` | § skill-mark.sh |
| `post-commit.sh` | § post-commit.sh |
| `agent-mark.sh` | § agent-mark.sh |
| `pilot-cleanup.sh` | § pilot-cleanup.sh |
| `limit-mark.sh` | § limit-mark.sh |

For `pre-handoff-check.sh`, also substitute `<LINT_CMD>` and `<TYPECHECK_CMD>` with the commands discovered in Phase 1 — following the **Bare-shell rule** in `tpl-skill-guard.md § pre-handoff-check.sh`: the hook runs without the project's activated environment, so a bare interpreter/tool command (`ruff check .`, `python -m ruff`, `eslint .`, `tsc`) that works in a terminal will silently fail the gate. Substitute an env-launcher (`uv run …`, `poetry run …`, `pnpm exec …`, `npx --no-install …`) or an absolute project-env path (`.venv/bin/…`, `node_modules/.bin/…`); when the interpreter path itself may or may not exist, resolve it defensively at the top of the hook (the venv-fallback snippet in the template Note). If no lint/typecheck command was discovered, leave the `<fill in>` stub and tell the user. A command counts as *discovered* only if it **verifiably resolves** — the `lint` script exists under `scripts` in `package.json`, or the linter is an installed dependency; a conventional-but-unwired `npm run lint` errors on every run, so stub it rather than substitute it.

Make all 12 executable:
```bash
chmod +x .claude/hooks/skill-guard.sh
chmod +x .claude/hooks/path-coverage-check.sh
chmod +x .claude/hooks/dependency-guard.sh
chmod +x .claude/hooks/package-edit-guard.sh
chmod +x .claude/hooks/pre-handoff-check.sh
chmod +x .claude/hooks/close-out-gate.sh
chmod +x .claude/hooks/ref-sync-check.sh
chmod +x .claude/hooks/skill-mark.sh
chmod +x .claude/hooks/post-commit.sh
chmod +x .claude/hooks/agent-mark.sh
chmod +x .claude/hooks/pilot-cleanup.sh
chmod +x .claude/hooks/limit-mark.sh
```

**Step 3 — Wire `settings.json`**

Use `tpl-skill-guard.md § settings.json`. If the file does not exist, create it from the template. If it already exists, merge the `hooks` key — add all hook entries without removing unrelated settings. Do not tell the user to wire hooks manually; write the file in this step.

**Step 4 — Schedule headless shifts (opt-in, macOS only)**

`.claude/pilot/shift.sh` is already copied and staged (Phase 2). Ask once, with `AskUserQuestion`: "Schedule headless shifts on this machine? — a launchd job runs `/pilot --max-tasks N` every interval with a dollar cap, orchestrator on Opus, subagents on Sonnet; you answer what it parks at check-in." Options: `Yes — every 30 min, 3 tasks, $15 cap (Recommended)` / `Not now`; the automatic "Other" takes an interval, task cap, budget and a Discord/Slack webhook URL for `PILOT_NOTIFY_URL`. On yes, run `bash .claude/pilot/shift.sh install [--interval S] [--max-tasks N] [--budget USD] [--notify URL]` and show its output; on no, print that same command so the user can run it later. Never install without asking — it writes to `~/Library/LaunchAgents`, outside the repo — and never run this step from inside a shift or any non-interactive session. Remind the user that a shift asks nothing (the standing mission has no gate, and a question timeout is not relied on — it does not fire in practice) and that the interactive loop form (`/loop 30m /pilot --max-tasks 1`, fixed interval) needs no install at all.

**Step 5 — Let a run see its remaining allowance (opt-in, writes outside the repo)**

Claude Code publishes the account's live allowance — percent of the 5-hour window used, percent of the week, and when each resets — to exactly **one** place: the status-line command's stdin. No hook receives it and no endpoint serves it, so a run cannot know how much is left unless something copies the figures out. Without this, `/pilot` reports `allowance: unknown` forever and its per-task stop never fires; the mission then starts work it cannot finish and dies mid-task, which is what happened on a real 10-item run (6h43m idle after the limit had already lifted).

Check first: read `~/.claude/settings.json`. If its `statusLine.command` already contains `usage-snapshot.sh`, this is done — say so and skip.

Otherwise ask once, with `AskUserQuestion`: "Let runs read your remaining Claude allowance? — copies the figures your status line already receives to a file `/pilot` reads before starting work. Your status-line script is not edited; one settings line wraps it, and deleting that line undoes it." Options: `Yes — wire it (Recommended)` / `No — print it and I'll do it myself`.

On yes:
1. Copy `../../shared/usage-snapshot.sh` **verbatim** to `~/.claude/usage-snapshot.sh` (no substitution — it is account-scoped, not project-scoped, and stays byte-identical everywhere).
2. Edit `~/.claude/settings.json`: take the existing `statusLine.command` string, if any, and set the command to `bash ~/.claude/usage-snapshot.sh <the old command>`; leave `type` as it was; set `refreshInterval` to `60` if absent. When there is no `statusLine` at all, write the wrapper with no wrapped command — it is then a pure tee and prints nothing.
3. Read the file back and show the resulting `statusLine` block.
4. Verify both directions: the write side by confirming a file appears under `~/.claude/usage/` named for a session id once a status line has rendered, and the read side with `bash ~/.claude/usage-snapshot.sh --read`. On a session that has not yet had an API response the read correctly prints `unknown` — that is the right answer, not a failure.

On no, print the copy command and the exact settings block so the user can paste it.

**`refreshInterval` is not optional.** The status line is event-driven and goes quiet exactly while a mission runs, because the main session sits still waiting on background subagents. Without the timer the figures freeze at whatever they said when the mission began, and every number the run reports afterwards is a stale claim presented as a fresh one.

**One file per session is also not optional, and the reason is worth knowing.** A first version wrote one shared path. On a machine running 12 concurrent sessions — each re-rendering every 60 s — that file flipped between 46% and 7% for the same window four seconds apart, and published a missing window under a timestamp zero seconds old. A mission read it, reversed its own correct decision to stop, ran into the limit, and had a subagent killed mid-write against production. The script now writes `~/.claude/usage/<session id>.json` and `--read` reconciles them; **every caller must use `--read`** and never open those files, or it is reading one arbitrary session again.

Never write this without asking — it is the second of only two things in this install that touch anything outside the repo. Never run the step from inside a shift or any non-interactive session. It is machine-scoped, so a second project's install finds it already wired and skips.
