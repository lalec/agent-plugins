# Preflight — Required external skills

Before starting (install or upgrade), verify the required external skills are installed:

| Skill | Required by | If missing |
|---|---|---|
| `agent-browser` | `<PREFIX>-test` (E2E browser automation) | Warn the user and link to https://github.com/vercel-labs/agent-browser |
| `skill-creator` | `<PREFIX>-skill` (authoring new skills) | Warn the user and link to https://github.com/anthropics/skills/tree/main/skills/skill-creator |
| `frontend-design` | `<PREFIX>-design` (generating HTML design variants) | Conditional — only required if a design skill is installed. Warn the user and link to https://github.com/anthropics/skills/tree/main/skills/frontend-design. Can be replaced with any design skill — the installed `<PREFIX>-design/SKILL.md` names the skill to use and can be edited after install. |

If any required skill is absent, surface a clear warning and ask the user whether to continue anyway or install the missing skill first. Do not abort silently — the workflow degrades without these.
