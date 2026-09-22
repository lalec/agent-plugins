# Status line

A minimal Claude Code [status line](https://code.claude.com/docs/en/statusline) showing the current directory, model, context usage, how much of your plan allowance is spent, and the git branch:

```
~/py-projects/agent-plugins Opus 4.8 (1M context) 43% ctx 5h 55% 7d 100% main
```

`5h` and `7d` are the share of your rolling 5-hour and weekly allowance used — the numbers `/usage` shows as bars, which is where the session actually stops. They appear on a Claude subscription after the first reply, and a session often reports one window and not the other, so each shows only when Claude Code sends it.

Claude Code does not let plugins set the main status line, so it is installed as a personal setting:

1. Install the script (requires [`jq`](https://jqlang.github.io/jq/) — `brew install jq`):
   ```bash
   curl -fsSL https://raw.githubusercontent.com/lalec/agent-plugins/main/statusline/statusline-command.sh \
     -o ~/.claude/statusline-command.sh && chmod +x ~/.claude/statusline-command.sh
   ```
2. Add to `~/.claude/settings.json` (merge with any existing keys):
   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "bash ~/.claude/statusline-command.sh"
     }
   }
   ```

Source: [`statusline-command.sh`](./statusline-command.sh).

The `dev-workflow` plugin can wrap this script to save the same allowance figures where a `/pilot` run reads them before starting work. It wraps whatever command you already have, so the two compose — install this first, then take the plugin's offer.
