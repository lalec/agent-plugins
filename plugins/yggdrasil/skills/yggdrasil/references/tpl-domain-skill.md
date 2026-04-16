# Domain Skill Stub + Project File Sections

---

## § Domain skill stub

Create one copy per confirmed domain skill. Substitute:
- `<SKILL_NAME>` → e.g. `tosk-backend`
- `<SKILL_DESCRIPTION>` → one-line description of what this skill owns
- `<OWNED_PATHS>` → path patterns this skill owns (e.g. `^lambda/ ^src/lib/api\.ts$`)
- `<PROJECT>` → project name

Substitute also:
- `<REFERENCE_SYNC_CHECKLIST>` → one `- [ ]` line per stub file created (see § Domain skill resources stubs)
- `<REFERENCES_LIST>` → one `- \`references/<file>\` — <purpose>` line per stub file

```markdown
---
name: <SKILL_NAME>
description: <SKILL_DESCRIPTION> for <PROJECT>. Use when working on files in <OWNED_PATHS>.
---

# <SKILL_NAME>

Domain skill for <PROJECT>. Owns <OWNED_PATHS>.

## Architecture

<!-- Fill in: tech stack, key files, patterns, constraints for this domain -->

## Quality Checklist

Run before proceeding to deploy:

<!-- Fill in: quality rules for this domain — e.g.
- New module → new test file covering auth, not-found, error, and happy-path cases
- Run <test-runner> and confirm all tests pass
- Run <lint-command> and fix all errors
-->

## Reference Sync

Verify before finishing any <SKILL_NAME> invocation:
<REFERENCE_SYNC_CHECKLIST>

## References

<REFERENCES_LIST>
```

---

## § Domain skill resources stubs

Create one stub file per signal detected in Phase 1 for this skill's owned paths. Use only the stubs that match detected signals — not all of them.

| Signal | Stub file | Title | Fill-in hint |
|---|---|---|---|
| REST/GraphQL API (FastAPI, Express, Flask, Hono, etc.) | `api-schema.md` | API Schema | endpoint contracts, request/response shapes |
| Database (Postgres, DynamoDB, Firestore, MySQL, Mongo) | `db-schema.md` | DB Schema | table/collection design, key attributes, indexes |
| Infra/deploy (Terraform, CDK, serverless.yml, Dockerfile) | `deploy-config.md` | Deploy Config | deploy commands, environment variables, stack names |
| Cloud resources (AWS, GCP, Azure — ARNs, bucket names, etc.) | `resources.md` | Resources | ARNs, bucket names, API Gateway IDs, config values |
| Frontend framework (React, Astro, Vue, Svelte) | `component-manifest.md` | Component Manifest | page components, shared components, routing patterns |
| Auth patterns (OAuth, JWT, session middleware) | `auth-patterns.md` | Auth Patterns | auth flow, token handling, middleware chain |
| SDK / third-party integrations | `patterns.md` | Patterns | SDK usage patterns, integration conventions |

Rules:
- If no specific signal matches, create a single `resources.md` as fallback
- `resources.md` is always created when cloud resources are present (in addition to any other stubs)
- Each stub contains only a `# Title` header and one `<!-- Fill in: ... -->` comment

Example stub (`api-schema.md`):
```markdown
# API Schema

<!-- Fill in: endpoint contracts, request/response shapes -->
```

Example `<REFERENCE_SYNC_CHECKLIST>` for a skill that got `api-schema.md` + `db-schema.md` + `deploy-config.md`:
```
- [ ] `references/api-schema.md` matches current endpoint shapes
- [ ] `references/db-schema.md` reflects current table/schema design
- [ ] `references/deploy-config.md` has current deploy commands and env vars
```

Example `<REFERENCES_LIST>` for the same skill:
```
- `references/api-schema.md` — endpoint contracts, request/response shapes
- `references/db-schema.md` — table key design, schema attributes
- `references/deploy-config.md` — deploy commands, environment variables
```

---

## § Project file sections

Use these templates when upserting sections into CLAUDE.md or GEMINI.md.

Substitute:
- `<PROJECT>` → project name
- `<CONFIG_DIR>` → `.claude` or `.gemini`
- `<SOURCE_OF_TRUTH_DOCS>` → discovered docs from Phase 1 (e.g. README.md, docs/workflow.md)
- `<LINTING_COMMANDS>` → discovered linting commands from Phase 1, or `<fill in>`
- `<DOMAIN_SKILL_TRIGGER_TABLE>` → one line per domain skill: `- path pattern → skill-name`

```markdown
## Plan Mode

- `<SOURCE_OF_TRUTH_DOCS>` — check before assuming how the delivery pipeline is structured

## Docs

Update `docs/workflow.md` whenever any of the following change: agents (`<CONFIG_DIR>/agents/`), skills (`<CONFIG_DIR>/skills/`), commands (`<CONFIG_DIR>/commands/`), hooks (`<CONFIG_DIR>/hooks/`), or hook registrations (`<CONFIG_DIR>/settings.json`).

## Agents

Three orchestrator agents own the full delivery lifecycle:

- **<PREFIX>-dev** — design → implement → deploy → Reference Sync → hand off to <PREFIX>-qa
- **<PREFIX>-qa** — code review (<PREFIX>-review) + tests (<PREFIX>-test) → sign-off → hand off to <PREFIX>-pm
- **<PREFIX>-pm** — verify QA phases ran → write delivery log (<PREFIX>-log) → update docs if needed

For any non-trivial task, invoke `<PREFIX>-dev` to start. The agents sequence the rest.

## Skills

Path→skill ownership is defined in `<CONFIG_DIR>/hooks/governed-paths.conf` — edit that file to add or change path ownership. Both `skill-guard.sh` and `path-coverage-check.sh` source it automatically.

<DOMAIN_SKILL_TRIGGER_TABLE>

## Roadmap

`docs/roadmap.md` is the source of truth for open items.
Format: **Category** (improvement | dogfood | integration | tech-debt), **Priority** (high | medium | low), **Status** (open | in-progress | done · YYYY-MM-DD), **Added** (YYYY-MM-DD HH:MM).
`<PREFIX>-dev` appends new entries autonomously; `<PREFIX>-pm` advances status after delivery.

## Git
- Group interdependent changes in the same commit.
- Commit messages: single short line, no body, no Co-Authored-By.
```

**Linting commands:** Embed in the relevant domain skill's `## Quality Checklist`, not in CLAUDE.md. `<PREFIX>-dev` step 3 delegates to these checklists. The hook `pre-handoff-check.sh` enforces lint at handoff time independently via its own `<LINT_CMD>` substitution.
