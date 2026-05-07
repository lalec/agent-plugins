# CLAUDE.md

Repository-wide instructions. Plugin-specific rules live under their own headings.

---

## dev-workflow

Design contract for `plugins/dev-workflow/`. Read before editing anything in it.

### Rules

1. **Agents do WHAT, skills do HOW.** Agents are stack-agnostic step sequences; skills carry the project-specific commands, paths, and tools.
2. **One-way references.** Agents may name skills; skills must never name agents.
3. **Agents and commands are uniform across projects.** Same wording, same structure, only `<PREFIX>` differs — variation belongs in skills.
4. **No duplicated instructions.** A rule lives in exactly one place; if it appears in both an agent and a skill, the boundary is wrong — fix the design, don't copy text.
5. **SKILL.md is *what + when + pointer*; references are *how*.** SKILL.md states what the skill owns, when to invoke it, and routes to references via a short read map. Multi-step protocols, full code examples, and detailed checklists live in `references/*.md`, never inlined in SKILL.md. If a SKILL.md restates a reference's content, the duplication is a bug — collapse it to a pointer.
6. **No hardcoded project-variable content.** Allowed: fixed names (`<PREFIX>-dev/qa/pm`, the 6 lifecycle skill names, the 5 command names). Forbidden: stacks, hosting, paths, ports, or discovery-dependent skill names — route those through `governed-paths.conf` / `deploy-config.yaml` / discovery.
7. **Surgical changes only.** Edit existing structure to fit new concepts; never bolt parallel mechanisms on top.

### Workflow contract (from `plugins/dev-workflow/skills/bootstrap/SKILL.md` § Phase 2 `docs/workflow.md` template)

Every install produces this exact shape — preserve it when evolving the plugin.

- **Pipeline:** `/code` or `/fix` → `<PREFIX>-dev` → `<PREFIX>-qa` → `<PREFIX>-pm`.
- **3 agents:** `<PREFIX>-dev` (design → implement → deploy → Reference Sync → handoff), `<PREFIX>-qa` (review + test → sign-off → handoff), `<PREFIX>-pm` (verify QA → write log → docs check).
- **7 lifecycle skills:** `<PREFIX>-log`, `<PREFIX>-review`, `<PREFIX>-debug`, `<PREFIX>-deploy`, `<PREFIX>-test`, `<PREFIX>-skill`, `<PREFIX>-docs`. `<PREFIX>-design` is added only when a Frontend category is present. `<PREFIX>-deploy` is the single source of truth for *how* the project deploys — owns `deploy-config.yaml` and the gate/trigger/verify logic; agents and other skills delegate here.
- **Commands:** thin entry points that hand work to agents — `/code` and `/fix` start the pipeline at `<PREFIX>-dev`, others target a specific phase (roadmap, wrap-up, design). Same `.md` (Claude Code) / `.toml` (Gemini CLI) shape across projects; concrete set evolves over time.
- **Domain skills:** derived from `CATEGORY_MAP` discovery; path ownership is single-sourced in `<CONFIG_DIR>/hooks/governed-paths.conf`.
- **Hooks:** shell scripts wired in `<CONFIG_DIR>/settings.json` that fire on tool events (`PreToolUse` / `PostToolUse` for Edit, Write, Bash, Skill). Two roles only — *gates* that block actions when an invariant is violated (skill not loaded, dirty tree, uncovered path), and *recorders* that mark session state or warn after the fact. Concrete set evolves; the role split does not.
- **Source-of-truth files:** `governed-paths.conf` (path → skill ownership + `DEPLOY_PATHS`), `deploy-config.yaml` on `DEPLOY_OWNER` (per-component verify/envs/gates/urls), `docs/roadmap.md` (open items), `docs/project-log.md` (delivery log).
- **Delivery log entry format** (`docs/project-log.md`, written by `<PREFIX>-log`): `### YYYY-MM-DD HH:MM · <7-char hash> — <title>` + 1–3 sentences + `**Tests:**` + `**Skills:**` + optional `**Checklist:**`. Any field added here must be added in the `<PREFIX>-log` template, the workflow.md template, and the upgrade-pass checklist together.
