---
description: Health-check the secretrun install — is `secretrun` on PATH, which backends (keychain/aws/gcp) are available, does this Claude Code version support hook hard-redaction, are the hook files present, and does every .secretrun.json entry resolve.
---

Run the secretrun health check and report the result:

```
secretrun-admin doctor
```

Interpret the output for the user:

- **secretrun on PATH** — if missing, the SessionStart PATH hook did not run;
  suggest restarting the session (or, one-off, calling the wrapper by its
  absolute `${CLAUDE_PLUGIN_ROOT}/bin/secretrun` path).
- **Claude Code version** — `✓` means the redactor hook hard-replaces tool output
  (`updatedToolOutput`, 2.1.199+); `⚠` means it runs in detect+warn mode while the
  `secretrun` wrapper still masks child output — offer `claude update`.
- **Backends** — `security` (keychain) should be present on macOS; `aws`/`gcloud`
  are optional and only needed for cloud backends.
- **Manifest secrets** — `OK` / `MISS` per entry in `.secretrun.json`. For any
  `MISS`, the user stores it with `! secretrun add NAME`.

Do not print or ask for any secret value.
