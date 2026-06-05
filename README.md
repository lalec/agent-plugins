# agent-plugins

A collection of Claude Code plugins by [lalec](https://github.com/lalec).

## Setup

**Add this marketplace:**
```
/plugin marketplace add lalec/agent-plugins
```

**Browse available plugins:**
```
/plugin > Discover
```

## Plugins

| Plugin | Description |
|--------|-------------|
| [dev-workflow](./plugins/dev-workflow/README.md) | Bootstrap a 3-agent delivery pipeline (dev → qa → pm) with skill-guard hooks, domain skills, and roadmap tracking on any project |
| [edr](./plugins/edr/README.md) | Endpoint Detection & Response for macOS — collectors gather telemetry, Claude performs NIST SP 800-61 Identification on anomalies |
| [agent-eval](./plugins/agent-eval/README.md) | Evaluate Claude Code instruction-based agent pipelines — 46 deterministic + heuristic checks across efficiency, reliability, behavioral, workflow, spec conformance, and orchestration |

## Install a plugin

```
/plugin install <plugin-name>@agent-plugins
```

Example:
```
/plugin install dev-workflow@agent-plugins
```

## Plugin structure

```
plugins/
└── plugin-name/
    ├── .claude-plugin/
    │   └── plugin.json       # Plugin metadata (required)
    ├── skills/               # Model-invoked skills
    │   └── skill-name/
    │       └── SKILL.md
    ├── commands/             # User-invoked slash commands (optional)
    ├── agents/               # Agent definitions (optional)
    └── README.md
```

## Optional: status line

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

Source: [`statusline/statusline-command.sh`](./statusline/statusline-command.sh).

## Docs

[Claude Code plugin documentation](https://code.claude.com/docs/en/plugins)
