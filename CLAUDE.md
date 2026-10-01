# CLAUDE.md

Repository-wide instructions. Plugin-specific rules live under their own headings.

---

## dev-workflow

Design contract for `plugins/dev-workflow/`. Read before editing anything in it.

### Rules

1. **Agents do WHAT, skills do HOW.** Agents are stack-agnostic step sequences; skills carry the project-specific commands, paths, and tools.
2. **One-way references.** Agents may name skills; skills must never name agents. The twelve entry points (`/code`, `/fix`, `/pilot`, …) live as `.claude/skills/<name>/SKILL.md` because that is where Claude Code puts a slash command with a `references/` directory — they are **commands** in Rules 1–2's sense (they orchestrate agents), and Rules 1–2 bind lifecycle and domain skills.
3. **Agents and commands are uniform across projects.** Same wording, same structure, only `<PREFIX>` differs — variation belongs in skills.
4. **No duplicated instructions.** A rule lives in exactly one place; if it appears in both an agent and a skill, the boundary is wrong — fix the design, don't copy text.
5. **SKILL.md is *what + when + pointer*; references are *how*.** SKILL.md states what the skill owns, when to invoke it, and routes to references via a short read map. Multi-step protocols, full code examples, and detailed checklists live in `references/*.md`, never inlined in SKILL.md. If a SKILL.md restates a reference's content, the duplication is a bug — collapse it to a pointer.
6. **No hardcoded project-variable content.** Allowed: fixed names (`<PREFIX>-dev/qa/pm/verify`, the 8 lifecycle skill names, the command names). Forbidden: stacks, hosting, paths, ports, or discovery-dependent skill names — route those through `governed-paths.conf` / `deploy-config.yaml` / discovery.
7. **Surgical changes only.** Edit existing structure to fit new concepts; never bolt parallel mechanisms on top.

### Workflow contract

The full contract — the shape every install produces, the agents, lifecycle skills, commands, hooks, source-of-truth files, delivery graph and log format, with the measured reason behind each rule — lives in **`plugins/dev-workflow/CONTRACT.md`**. Read it before editing anything in the plugin; it is long because every sentence is an invariant somebody paid for, and it is not in this file because this file loads into every session in this repo.
