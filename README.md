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
| [yggdrasil](./plugins/yggdrasil/README.md) | Bootstrap a 3-agent delivery pipeline (dev → qa → pm) with skill-guard hooks, domain skills, and roadmap tracking on any project |

## Install a plugin

```
/plugin install <plugin-name>@agent-plugins
```

Example:
```
/plugin install yggdrasil@agent-plugins
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

## Docs

[Claude Code plugin documentation](https://code.claude.com/docs/en/plugins)
