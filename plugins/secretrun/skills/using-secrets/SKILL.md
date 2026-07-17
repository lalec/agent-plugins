---
name: using-secrets
description: Use whenever a task needs a credential — API key, token, password, Bearer/Authorization header, database URL with a password, cloud/deploy credential, or anything a tool authenticates with. Run the tool via `secretrun NAME -- cmd` so the value is resolved from Keychain/cloud Secret Manager into the child process only; the model handles secret NAMES, never values. Trigger on mentions of API keys, tokens, secrets, .env, auth, login, credentials, or "the value is sensitive".
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
  into context and several are blocked by the guard hook.
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

## Project manifest

If the project has a committed `.secretrun.json`, it declares the required secret
NAMES (and their backend/id) — values are never in it. Use those names directly.
`secretrun check` (or `/secretrun:doctor`) verifies each declared secret resolves.
List what is stored with `secretrun ls`.

If `secretrun` is not found on PATH, the plugin's SessionStart hook may not have
run — tell the user to restart the session or run `/secretrun:doctor`.

See the plugin README for the full threat model.
