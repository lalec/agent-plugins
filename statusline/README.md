# Status line

A minimal Claude Code [status line](https://code.claude.com/docs/en/statusline) showing the current directory, model, context usage, and git branch:

```
~/py-projects/agent-plugins Opus 4.8 (1M context) 43% ctx main
```

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
