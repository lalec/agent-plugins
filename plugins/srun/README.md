# srun

**Keep secret values out of Claude Code.** The agent handles secret *names*;
`srun` resolves each name to its value inside its own process, hands the
value to one child command, and masks it — plus its base64, URL-encoded and
JSON-escaped forms — out of that command's output as `[REDACTED:NAME]`. Nothing
reaches the command line, the agent's context, or the session transcript.

A Claude Code plugin, Python standard library only. dev-workflow depends on it,
so installing dev-workflow installs srun; any other project uses it on its own.

## Use it in any project

1. Install once per machine: `/plugin install srun@agent-plugins`. Its hooks
   (below) then guard every project, from the next session on.
2. Run `/srun:setup` once per project. It gives `.srun.json` a `namespace` (see
   Namespacing) and writes the Secrets rule into `CLAUDE.md`, so the agent —
   subagents included — uses secrets by name. Commit both.
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

`setup` writes the namespace once, from the repo folder name, and never rewrites
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
srun setup               set the namespace (once) and the Secrets rule in CLAUDE.md
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
| PreToolUse · Bash (`guard.py`) | denies printing a `.env` file or anything under `~/.aws`, `~/.ssh`, `~/.config/gcloud` (`grep -c` still counts), `security … -w`, `dump-keychain`, `env`/`printenv` dumps, and a value on the `add` command line |
| PreToolUse · Read, Grep (`guard.py`) | denies the Read tool, and Grep in content mode, on those same files — never `.env.example`; Glob and Grep's file lists stay allowed |
| PostToolUse (`redact.py`) | replaces credential-*shaped* strings (`sk-…`, `ghp_…`, `AKIA…`, JWTs, keys) in any tool output |

Session transcripts stay readable — debugging across sessions keeps working.

## Limits

- It serves your own machine. Claude cloud sessions and CI do not install the plugin, so a step there that needs a secret stops as `blocked`; deployed services read their secret manager themselves.
- Grep over a whole folder in content mode, or `grep -r`, can still print a `.env` line; the guard catches a secret file only when it is named.
- Masking covers output, not intent: a child that sends a value over the network sends the real value.
- Any process you own can read a child's environment while it runs; `--stdin` avoids that for tools that accept it.
- Python cannot guarantee a value is wiped from memory; the process is short-lived, core dumps are off, and tracebacks never print.
