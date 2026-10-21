# srun

**Keep secret values out of Claude Code.** The agent handles secret *names*;
`srun` resolves each name to its value inside its own process, hands the
value to one child command, and masks it — plus its base64, URL-encoded and
JSON-escaped forms — out of that command's output as `[REDACTED:NAME]`. Nothing
reaches the command line, the agent's context, or the session transcript.

One folder, Python standard library only. dev-workflow installs it into every
project; any other project can use it on its own.

## Use it in any project

1. Copy this folder into the project, e.g. to `.claude/srun/`.
2. Wire it: `python3 .claude/srun/srun init` — adds the hooks below to
   `.claude/settings.json` and gives `.srun.json` a `namespace` (see
   Namespacing). Takes effect in new sessions. Commit all three.
3. Declare the project's secrets by name in `.srun.json` at the repo root
   (committed — it never holds values):

```json
{ "namespace": "myapp",
  "secrets": {
    "E2E_EMAIL":    { "backend": "keychain" },
    "E2E_PASSWORD": { "backend": "keychain" },
    "DB_URL":       { "backend": "aws", "id": "dev/db/url" },
    "STRIPE_KEY":   { "cmd": "aws ssm get-parameter --with-decryption --name /dev/stripe --query Parameter.Value --output text" },
    "OPENAI_KEY":   { "cmd": "op read op://dev/openai/key" },
    "MAPS_KEY":     { "cmd": "sed -n 's/^MAPS_KEY=//p' .env" }
} }
```

4. Store each value yourself: `srun add NAME` opens a hidden prompt (in a
   terminal) or a macOS dialog (inside Claude Code). For a `cmd` entry, store it
   in that secret manager instead.

For one copy that serves every project (and global skills that call `srun`
by name), put the folder somewhere stable and run `srun init --global`.

## Stores

| Store | Entry | Id with a namespace | Notes |
|---|---|---|---|
| macOS Keychain | `{"backend": "keychain"}` (default) | account `myapp/NAME`, service `srun` | `add`, `rm`, `ls`, `migrate` |
| AWS Secrets Manager | `{"backend": "aws"}` | `myapp/NAME` — a path, so IAM can scope by prefix | `add` writes a new version of an existing secret |
| GCP Secret Manager | `{"backend": "gcp"}` | `myapp_NAME` — GCP ids reject `/` | same |
| Any command | `{"cmd": "<prints the value>"}` | none — the command is the lookup | an env file, AWS Parameter Store, 1Password, Vault, Doppler — read-only here |

A `cmd` runs from the folder holding `.srun.json`; its error output is
discarded and one trailing newline is stripped. It is committed code, so it
carries the same trust as a `package.json` script.

## Namespacing

`"namespace"` keeps projects that share a machine, AWS account or GCP project
apart: without it, every project that declares `E2E_PASSWORD` reads and writes
the same entry, and one overwrites another's value with no warning. With it, an
entry's store id is `<namespace>/NAME` (Keychain, AWS) or `<namespace>_NAME`
(GCP); letters, digits, `_` and `-` only. An explicit `"id"` always wins — that
is how a secret shared on purpose opts out. No namespace means the id is NAME.

`init` writes the namespace once, from the repo folder name, and never rewrites
it. It lives in the committed file, not the folder name, because a worktree or
second clone has a different folder and would look up different entries.

Adding a namespace to a project that already stored values: `srun migrate`
moves each Keychain value from `NAME` to `<namespace>/NAME` inside its own
process (read, store, read back, delete) and prints `moved`, `not stored`,
`kept` (already under the new id) or `skipped` per name — never a value. AWS and
GCP entries are skipped: moving needs create and delete rights there (and AWS
deletes on a delay), so move them in that store, or pin `"id": "NAME"`.

## Commands

```
srun NAME [NAME...] [--stdin NAME] -- cmd args...   run cmd with the values
srun check [NAME...]     OK / MISS and store id per name (default: every manifest entry)
srun add NAME            store a value — the user types it, never the agent
srun rm NAME | ls | sync
srun migrate [NAME...]   move Keychain values from NAME to <namespace>/NAME
srun init [--global]     wire the hooks; project scope also sets the namespace
```

A tool that reads a variable needs nothing else; a shell expansion goes inside
`sh -c` so the value expands in the child, not on the command line:

```
srun E2E_EMAIL E2E_PASSWORD -- sh -c 'agent-browser fill @e1 "$E2E_EMAIL" && agent-browser fill @e2 "$E2E_PASSWORD" && agent-browser click @e3'
srun GH_TOKEN --stdin GH_TOKEN -- gh auth login --with-token
```

An MCP server takes `srun` as its launcher (`"command": "<absolute path>/srun"`,
`"args": ["TOKEN", "--", "npx", "<server>"]`), so the token is never in the config file.

## What `init` wires

| Hook | Does |
|---|---|
| SessionStart | puts this folder on `PATH`, so `srun` works by name |
| PreToolUse · Bash (`guard.py`) | denies printing a `.env` file (`grep -c` still counts), `security … -w`, `dump-keychain`, `env`/`printenv` dumps, and a value on the `add` command line |
| PostToolUse (`redact.py`) | replaces credential-*shaped* strings (`sk-…`, `ghp_…`, `AKIA…`, JWTs, keys) in any tool output |
| `permissions.deny` | the Read tool on `.env` files (never `.env.example`), `~/.aws`, `~/.ssh`, `~/.config/gcloud` |

Session transcripts stay readable — debugging across sessions keeps working.

## Limits

- Masking covers output, not intent: a child that sends a value over the network sends the real value.
- Any process you own can read a child's environment while it runs; `--stdin` avoids that for tools that accept it.
- Python cannot guarantee a value is wiped from memory; the process is short-lived, core dumps are off, and tracebacks never print.
