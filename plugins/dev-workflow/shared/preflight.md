# Preflight — Required external skills

Before starting (install or upgrade), verify the required external skills are installed:

| Skill | Required by | If missing |
|---|---|---|
| `agent-browser` | `<PREFIX>-test` (E2E browser automation) | Warn the user and link to https://github.com/vercel-labs/agent-browser |
| `skill-creator` | `<PREFIX>-skill` (authoring new skills) | Warn the user and link to https://github.com/anthropics/skills/tree/main/skills/skill-creator |
| `ui-ux-pro-max` | `<PREFIX>-design` (design intelligence: styles, palettes, font pairings, design-system generation) | Conditional — only required if a design skill is installed. Warn the user and link to https://github.com/nextlevelbuilder/ui-ux-pro-max-skill. Can be replaced with any design skill — the installed `<PREFIX>-design/SKILL.md` names the skill to use and can be edited after install. |
| `visual-assets` | `<PREFIX>-design` (icons and artwork: generation at exact platform sizes, icon ladders, style-consistent references) | Conditional — only required if a design skill is installed. Warn the user; it also needs `GEMINI_API_KEY` exported in the environment, without which it hard-gates and an icon step honestly reports blocked rather than hand-drawing a substitute. Can be replaced with any image-generation skill — the installed `<PREFIX>-design/SKILL.md` names the skill to use and can be edited after install. |

If any required skill is absent, surface a clear warning and ask the user whether to continue anyway or install the missing skill first. Do not abort silently — the workflow degrades without these.
