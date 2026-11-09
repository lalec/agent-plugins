# srun

**Keep secret values out of Claude Code.** The agent handles secret *names*;
`srun` resolves each name to its value inside its own process, hands the
value to one child command, and masks it — plus its base64 (also inside a longer
base64 string, such as an HTTP Basic header), URL-encoded and JSON-escaped
forms — out of that command's output as `[REDACTED:NAME]`. Nothing
reaches the command line, the agent's context, or the session transcript.

A Claude Code plugin, Python standard library only. dev-workflow depends on it,
so installing dev-workflow installs srun; any other project uses it on its own.

## Use it in any project

1. Install once per machine: `/plugin install srun@agent-plugins`. Its hooks
   (below) then guard every project, from the next session on.
2. Run `/srun:setup` once per project. It gives `.srun.json` a `namespace` (see
   Namespacing) and writes the Secrets rule into `CLAUDE.md`, so the agent —
   subagents included — uses secrets by name. Commit both.
3. List the project's secrets by name in `.srun.json` at the repo root
   (committed — it never holds values). `"store"` is optional: without it every
   name lives in your personal default store (`srun default 1password`), else
   the keychain.

```json
{ "namespace": "myapp", "store": "1password", "secrets": ["E2E_EMAIL", "E2E_PASSWORD", "OPENAI_KEY"] }
```

4. Store each value yourself, at the place `srun check` names: `srun add NAME`
   in your own terminal (a hidden prompt; inside Claude Code it opens a macOS
   dialog instead), or the password manager's app.

## Stores

Every store holds one entry per secret under the same id, `myapp/NAME`, so
moving a project to another store is a one-word change.

| Store | Where `myapp/API_KEY` lives | `srun add` |
|---|---|---|
| `keychain` (built-in default) | macOS Keychain, service `srun`, account `myapp/API_KEY` | yes |
| `1password` | a Password item titled `myapp/API_KEY`, any vault; srun reads its password field | no — create it in the 1Password app |
| `dashlane` | a login titled `myapp/API_KEY`; srun reads its password | no — Dashlane's CLI cannot write; use the app |
| `lastpass` | an entry `API_KEY` in folder `myapp` | yes — and `rm` |
| `aws` | Secrets Manager secret `myapp/API_KEY` — a path, so IAM can scope by prefix | writes a new version of an existing secret |
| `gcp` | Secret Manager secret `myapp_API_KEY` — GCP ids reject `/` | same |

The password managers need their CLI signed in: `op` (1Password, desktop-app
sign-in may ask for Touch ID), `dcli` (Dashlane), `lpass` (LastPass — srun stops
with "run `lpass login`" once its agent has timed out, rather than let it
prompt). Each title must be unique; srun refuses a duplicate rather than guess.

**One secret somewhere else.** A name can carry its own entry instead of
following the project's store — a store, a fixed `"id"` (a secret shared on
purpose across projects), or a `"cmd"` that prints the value (an env file, AWS
Parameter Store, Bitwarden, Vault, Doppler):

```json
"secrets": { "E2E_PASSWORD": {},
             "SHARED_TOKEN": { "store": "aws", "id": "shared/token" },
             "MAPS_KEY": { "cmd": "sed -n 's/^MAPS_KEY=//p' .env" } }
```

A `cmd` runs from the folder holding `.srun.json`; its error output is
discarded and one trailing newline is stripped. It is committed code, so it
carries the same trust as a `package.json` script; srun only reads through it.
srun looks for `.srun.json` from the working folder up to the repo root (or
`$HOME`), never above, and refuses one that is not yours or that others can
write, so a file planted in a shared folder such as `/tmp` never runs.

## Namespacing

`"namespace"` keeps projects that share a machine or a store apart: without
it, every project that lists `E2E_PASSWORD` reads and writes the same entry, and
one overwrites another's value with no warning. With it, a store id is
`<namespace>/NAME` (`<namespace>_NAME` in GCP); letters, digits, `_` and `-`
only. An explicit `"id"` always wins — that is how a secret shared on purpose
opts out. No namespace means the id is NAME.

`setup` writes the namespace once, from the repo folder name, and never rewrites
it; it also keeps the file in the short form above, so an older file that named
a store per secret becomes one `"store"` and a list. It lives in the committed file, not the folder name, because a worktree or
second clone has a different folder and would look up different entries.

Adding a namespace to a project that already stored values: `srun migrate`
moves each Keychain value from `NAME` to `<namespace>/NAME` inside its own
process (read, store, read back, delete) and prints `moved`, `not stored`,
`kept` (already under the new id) or `skipped` per name — never a value. AWS and
GCP entries are skipped: moving needs create and delete rights there (and AWS
deletes on a delay), so move them in that store, or pin `"id": "NAME"`.

## Commands

```
srun NAME [NAME...] [-s STORE] [--stdin NAME] -- cmd args...   run cmd with the values
srun check [NAME...]     OK / MISS, store and id per name (default: every listed name)
srun add NAME [-s STORE] store a value — the user types it, never the agent
srun rm NAME | ls | sync
srun migrate [NAME...]   move Keychain values from NAME to <namespace>/NAME
srun default [STORE]     show or set your personal default store
srun setup [--store S]   namespace (once), short form, the Secrets rule in CLAUDE.md
```

A tool that reads a variable needs nothing else; a shell expansion goes inside
`sh -c` so the value expands in the child, not on the command line:

```
srun E2E_EMAIL E2E_PASSWORD -- sh -c 'agent-browser fill @e1 "$E2E_EMAIL" && agent-browser fill @e2 "$E2E_PASSWORD" && agent-browser click @e3'
srun GH_TOKEN --stdin GH_TOKEN -- gh auth login --with-token
```

An MCP server takes `srun` as its launcher (`"command": "<absolute path>/srun"`,
`"args": ["TOKEN", "--", "npx", "<server>"]`), so the token is never in the config file.
The plugin's path changes with each `/plugin update`; re-point the launcher after one.

## What the plugin wires

| Hook | Does |
|---|---|
| SessionStart | puts `scripts/` on `PATH`, so `srun` works by name |
| PreToolUse · Bash (`guard.py`) | denies printing a `.env` file or anything under `~/.aws`, `~/.ssh`, `~/.config/gcloud` (`grep -c` still counts), `security … -w`, `dump-keychain`, password-manager reads (`op read`, `op item get`, `dcli password`, `lpass show`), `env`/`printenv` dumps, and a value on the `add` command line — wherever the read sits: behind `sudo`, `env`, `time` or `VAR=x`, inside `$(…)`, backticks, `bash -lc '…'` or `op run --`, or on a later line of the same command |
| PreToolUse · Read, Grep (`guard.py`) | denies the Read tool, and Grep in content mode, on those same files — never `.env.example`; Glob and Grep's file lists stay allowed |
| PostToolUse (`redact.py`) | replaces credential-*shaped* strings (`sk-…`, `ghp_…`, `AKIA…`, JWTs, keys, `Bearer`/`Basic` header values) in any tool output |

Session transcripts stay readable — debugging across sessions keeps working.

## Limits

- It serves your own machine. Claude cloud sessions and CI do not install the plugin, so a step there that needs a secret stops as `blocked`; deployed services read their secret manager themselves.
- A project on a FAT or exFAT drive shows every file as writable by others and cannot be `chmod`ed, so srun refuses its `.srun.json`; keep the project on an APFS volume.
- Grep over a whole folder in content mode, or `grep -r`, can still print a `.env` line; the guard catches a secret file only when it is named.
- The guard reads a command's text, not what it does: a heredoc or `echo` whose text names `cat .env` or `op read` is denied too. Write such text with the Edit or Write tool.
- Masking covers output, not intent: a child that sends a value over the network sends the real value.
- Masking is best-effort: it knows the forms listed above. Inside a longer base64 string, one character at each edge of the value stays visible; other encodings (hex, hashes, a value split across lines) are not caught.
- Any process you own can read a child's environment while it runs; `--stdin` avoids that for tools that accept it.
- Python cannot guarantee a value is wiped from memory; the process is short-lived, core dumps are off, and tracebacks never print.
