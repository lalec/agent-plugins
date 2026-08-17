---
name: using-secrets
description: Use whenever a task needs a credential — API key, token, password, Bearer/Authorization header, database URL with a password, cloud/deploy credential, or anything a tool authenticates with. Run the tool via `secretrun NAME -- cmd` so the value is resolved from Keychain/cloud Secret Manager into the child process only; the model handles secret NAMES, never values. Also use when adding or editing an MCP server config (.mcp.json, mcpServers, claude_desktop_config.json) that wants a token in its env block or headers. Trigger on mentions of API keys, tokens, secrets, .env, auth, login, credentials, MCP server setup, or "the value is sensitive". Also use for any question about token usage, session/model cost or spend, or inspecting past Claude sessions — `~/.claude/projects/**` is off-limits, and `secretrun usage` / `secretrun sessions` are the sanctioned readers, so the answer is measurable rather than unknown.
---

# Using secrets without exposing their values

The golden rule: **you handle secret NAMES; the `secretrun` wrapper handles values.**
A value must never appear in a command's argv, in a file you read, or in your
context/transcript. `secretrun` resolves `NAME → value` in its own process,
passes it to the child, and masks it out of the child's output as
`[REDACTED:NAME]`.

## Running a command that needs a secret

Most tools read credentials from an environment variable:

```
secretrun OPENAI_API_KEY -- <cmd that reads $OPENAI_API_KEY>
secretrun A B C -- <cmd>          # inject several at once
```

For tools that take the secret on **stdin** instead of the environment (avoids
even a same-user `ps` reading the child's env), use `--stdin`:

```
secretrun GH_TOKEN --stdin GH_TOKEN -- gh auth login --with-token
secretrun DOCKER_PAT --stdin DOCKER_PAT -- docker login -u me --password-stdin
```

Add `-b aws` / `-b gcp` to resolve from a cloud backend instead of the default
Keychain (a project `.secretrun.json` may already declare the backend — see below).

## Hard rules

- **Never** `cat .env`, `echo $SOME_KEY`, `printenv`, `env`, read `~/.aws`,
  `~/.ssh`, `~/.config/gcloud`, or `~/.claude/projects/**`. These leak values
  into context and several are blocked by the guard hook. To inspect sessions or
  answer a cost question, use `secretrun sessions` / `secretrun usage` (see
  below), not a raw read of the transcript.
- **Never** put a value on a command line yourself. Reference it by NAME through
  `secretrun`.
- Using a secret inside `sh -c '... $NAME ...'` under `secretrun` is fine — the
  wrapper masks the output. But do not pipe a secret to a network tool you don't
  trust; masking covers output, not deliberate exfiltration.

## Storing a new secret (the user types the value, never you)

Tell the user a dialog is coming, then run:

```
secretrun add NAME            # -b aws / -b gcp for a cloud backend
```

On macOS this opens a native hidden-input dialog on the user's screen (Claude
Code's shell has no terminal, so there is no prompt in-session). The user types
the value into the dialog; it goes straight from the dialog into the Keychain —
you never see it. The command blocks until they answer and times out after ~110 s,
so tell them to expect the dialog *before* running it. "dialog cancelled" or
"empty value" means nothing was stored — ask the user, don't retry blindly.

Never work around a failed `add` by piping or echoing the value
(`echo x | secretrun add` is blocked by the guard hook). If there is no GUI
either (e.g. SSH), the user runs `secretrun add NAME` in their own terminal.

## MCP server configs

Never write a secret value into `.mcp.json` / `claude_desktop_config.json` —
`"env": {"TOKEN": "paste-here"}` is a plaintext leak on disk. Make `secretrun`
the server's launcher instead; the value then exists only in the server's env:

```json
{ "command": "/absolute/path/to/secretrun",
  "args": ["BREVO_MCP_TOKEN", "--", "npx", "mcp-remote",
           "https://mcp.brevo.com/v1/brevo/mcp",
           "--header", "Authorization:Bearer ${BREVO_MCP_TOKEN}"] }
```

Drop the `env` block; the user stores the value once via
`secretrun add BREVO_MCP_TOKEN`. Rules:

- `command` is the **absolute path** from `which secretrun` — MCP servers
  launch before the plugin's PATH hook runs.
- A `${NAME}` placeholder in args is fine: it passes through unexpanded
  (Claude Code leaves unset vars literal; Claude Desktop never expands) and the
  server — e.g. `mcp-remote`'s `--header` — interpolates it from the injected
  env. Never expand it yourself and never paste a value in its place.
- Servers that simply read an env var need no placeholder at all:
  `secretrun API_KEY -- npx <server>` replaces the whole `env` block.

## Project manifest

If the project has a committed `.secretrun.json`, it declares the required secret
NAMES (and their backend/id) — values are never in it. Use those names directly.
`secretrun check` (or `/secretrun:doctor`) verifies each declared secret resolves.
List what is stored with `secretrun ls` — for the keychain this reads a local
names-only index (no `dump-keychain`); run `secretrun sync` after storing a secret
outside secretrun so `ls` picks it up.

If `secretrun` is not found on PATH, the plugin's SessionStart hook may not have
run — tell the user to restart the session or run `/secretrun:doctor`.

## Debugging past sessions

To find which session produced some uncommitted work — or otherwise inspect
session history — never read `~/.claude/projects/**` directly (it can pull
previously-seen secret values back into context, and the guard blocks it). Use
the sanctioned reader, which reads transcripts inside the wrapper and surfaces
only redacted metadata (session id, cwd, timestamps, files touched, git commands,
and a shape-redacted one-line label) — never raw message content:

```
secretrun sessions              # sessions for the current project, newest first
secretrun sessions --all        # across every project
secretrun session <id>          # one session's detail (id may be a prefix)
```

## Token usage and cost

When the user asks what a session, a day, or the project has cost — or how many
tokens something burned — do not answer from memory and do not say the data is
unreachable. The numbers are in the transcripts, and `secretrun usage` is the
sanctioned way to read them (numbers only: no labels, no paths, no content):

```
secretrun usage                 # this project, per session + per model, with cost
secretrun usage --all           # every project
secretrun usage --since 7       # only sessions active in the last 7 days
```

`secretrun session <id>` also reports that one session's tokens and cost.

Report what the tool prints, including its footer. Prices come from a dated table
(`share/prices.json`, overridable via `$SECRETRUN_PRICES`), so:

- A `—` cost or an "unpriced model(s)" line means that model has no entry — report
  the tokens and say the cost is unpriced. Never substitute a remembered price.
- The "prices as of <date>" footer is the currency of the figures — pass it on
  rather than presenting a total as authoritative.

See the plugin README for the full threat model.
