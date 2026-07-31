# Domain Skill Stub + Project File Sections

---

## § Domain skill stub

Create one copy per confirmed domain skill. Substitute:
- `<SKILL_NAME>` → e.g. `<PREFIX>-backend`
- `<SKILL_DESCRIPTION>` → one-line description of what this skill owns
- `<OWNED_PATHS>` → path patterns this skill owns (e.g. `^lambda/ ^src/lib/api\.ts$`)
- `<PROJECT>` → project name

Substitute also:
- `<REFERENCE_SYNC_CHECKLIST>` → one `- [ ]` line per reference file created (see § Reference files per category)
- `<REFERENCES_LIST>` → one `- \`references/<file>\` — <purpose>` line per reference file
- `<DESIGN_DELEGATION>` → the `## Visual Decisions` section from § Design delegation block if this skill owns the Frontend category AND a `<PREFIX>-design` skill exists in this install; empty string otherwise

(Deploy logic is owned by the `<PREFIX>-deploy` lifecycle skill — domain skills no longer carry a `## Deployment` section. See `tpl-lifecycle.md § <PREFIX>-deploy/SKILL.md`.)

```markdown
---
name: <SKILL_NAME>
description: <SKILL_DESCRIPTION> for <PROJECT>. Use when working on files in <OWNED_PATHS>.
---

# <SKILL_NAME>

Domain skill for <PROJECT>. Owns <OWNED_PATHS>.

## Architecture

<!-- Fill in: tech stack, key files, patterns, constraints for this domain -->

## Preconditions — Verify Before Writing References

Before writing code that references a named identifier (CSS variable, import, function, type, env var, config key, manifest entry), verify the definition exists. **Discovery reads** ("where do I put this?") and **verification reads** ("does the thing I'm referencing actually exist?") are different jobs — do both.

For each reference about to be written:

1. **Grep the project** for the definition with the exact name.
2. **If found**, the `file:line` of the definition must be in your context before you write the reference.
3. **If not found**, define the identifier as part of this change — never emit a reference to a non-existent definition.

This rule fires regardless of how generic the name sounds. `--font-size-sm`, `formatDate`, `process.env.DEBUG` look like they should exist; they only exist if you can cite the line that defines them.

For Frontend skills with the Visual Decisions block: this Preconditions rule is what makes the "if the value already exists in `design-tokens.md`, reference it" clause enforceable — you must verify presence, not assume it.

<DESIGN_DELEGATION>
## Quality Checklist

Run before proceeding to deploy. Every command here must be **non-interactive** (`CI=1`, `--yes`/`--no-input`, explicit timeout) — an interactive prompt inside a subagent stalls the whole pipeline until a watchdog kills the agent. Each command must also be **self-contained from a bare shell**: resolve the project's toolchain explicitly (`uv run …`, `poetry run …`, `pnpm exec …`, or an absolute `.venv/bin/…` / `node_modules/.bin/…` path) rather than a bare `ruff`/`eslint`/`tsc` that only works with the env activated — the same env that `pre-handoff-check.sh` enforces against, and a bare command silently fails there. Every command must also be **verifiably wired** — only list a check whose target actually exists in this project: a named `package.json` script is present under `scripts`, or the invoked tool is an installed dependency / on a resolvable path (not merely a convention like `npm run lint` that no `scripts` entry defines). A check whose target is missing errors on every run — omit the rule entirely rather than ship one that always fails. A new or changed test file must also pass **standalone** (run just that file in a clean interpreter) — a test that only passes inside the full suite is order-dependent (leaked stubs, import-order luck) and ships a hidden defect for QA to trip over.

<!-- Fill in: quality rules for this domain — e.g.
- New module → new test file covering auth, not-found, error, and happy-path cases
- Run <test-runner> and confirm all tests pass
- Run <lint-command> and fix all errors  (omit this line entirely if no lint command is wired)
-->

## Reference Sync

Verify before finishing any <SKILL_NAME> invocation:
<REFERENCE_SYNC_CHECKLIST>

## References

<REFERENCES_LIST>
```

---

## § Domain categories

The installer's discovery layer identifies which categories the project contains. For each category present, capture: the paths/files it occupies, and the specific tool or framework involved. Categories are the operative concept — they describe *what role* something plays. The category list does not change when the toolset does.

| Category | Definition (operative — what this category *does*) |
|---|---|
| **Frontend** | Code that renders UI (web, mobile, desktop) |
| **Backend** | Code that serves requests, runs business logic, or processes events |
| **Database / storage** | Persistent state — relational, document, KV, blob, vector, search |
| **Auth** | Identity, sessions, tokens, access control |
| **IaC** | Declarative infrastructure definitions |
| **CI/CD** | Automation that builds, tests, or deploys on events |
| **Build tooling** | Compilation, bundling, packaging |
| **Deployment scripts/config** | Imperative deploy mechanisms or platform configs outside CI |
| **Observability** | Logs, metrics, traces, alerts, dashboards |
| **Third-party SDK / integrations** | External services consumed via SDK or API |

Discovery rules:
- Recognize by **purpose**, not by exact filename. If something fits a category's operative definition, it belongs — even if no example list mentions it.
- New tools entering the ecosystem (e.g. a new IaC framework) do not require installer edits to be recognized — they fit `IaC` if they declaratively define infrastructure.
- A single tool may straddle two categories (e.g. Docker is build tooling *and* deployment config); record it under each category that fits.
- When uncertain whether something fits a category, ask the user before recording it.

§ Anchors below provides recognition aids per category. Use anchors only when uncertainty would otherwise force a guess — not as a whitelist.

---

## § Anchors (recognition aids only)

Common tools or marker files that often indicate each category. **Not a whitelist.** Anything fitting a category's operative definition counts, even if absent here.

| Category | Common anchors |
|---|---|
| Frontend | React, Astro, Vue, Svelte, SwiftUI, Flutter, Next.js, Remix, plain HTML/CSS |
| Backend | FastAPI, Express, Flask, Hono, NestJS, Django, Rails, Spring, AWS Lambda handlers |
| Database / storage | Postgres, MySQL, DynamoDB, Firestore, MongoDB, Redis, S3, GCS, Pinecone, Elastic |
| Auth | OAuth, JWT, Cognito, Auth0, Better Auth, Firebase Auth, session middleware |
| IaC | Terraform, OpenTofu, Pulumi, CDK, Bicep, CloudFormation, Crossplane, Helm charts |
| CI/CD | `.github/workflows/`, `.gitlab-ci.yml`, CircleCI, Jenkins, GitLab CI, Bitbucket Pipelines |
| Build tooling | Vite, Webpack, esbuild, Turbopack, Maven, Gradle, Cargo, `pyproject.toml` build-system |
| Deployment scripts/config | `./deploy.sh`, `vercel.json`, `wrangler.toml`, `firebase.json`, `Dockerfile`, `serverless.yml`, `Procfile`, `app.yaml` |
| Observability | OpenTelemetry, Sentry, DataDog, Grafana, CloudWatch, Honeycomb, structured logging libs |
| Third-party SDK / integrations | Stripe, Twilio, OpenAI, Anthropic, Slack API, Discord API, payment gateways |

---

## § Reference files per category

Each category, when present in a skill's domain, drives creation of a typed reference file. The mapping is one source of truth — every phase that creates references uses this table.

| Category(ies) present | Reference file | Purpose |
|---|---|---|
| Backend | `api-schema.md` | endpoint contracts, request/response shapes |
| Database / storage | `db-schema.md` | table/collection design, key attributes, indexes |
| Frontend | `component-manifest.md` | page components, shared components, routing patterns |
| Auth | `auth-patterns.md` | auth flow, token handling, middleware chain |
| Cloud resources detected in code (any provider — ARNs, bucket names, project IDs) | `resources.md` | concrete resource identifiers used in code |
| Observability | `observability.md` | telemetry endpoints, dashboards, alert routes |
| Third-party SDK / integrations | `patterns.md` | SDK usage patterns, integration conventions |

Rules:
- Create only files for categories actually present in this skill's domain — not all rows
- When no category matches but cloud resources exist, fall back to `resources.md` only
- All reference files are stubs (header + one `<!-- Fill in: ... -->` comment)
- `deploy-config.yaml` is **not** a domain-skill reference — it lives in `<PREFIX>-deploy` (see `tpl-lifecycle.md § <PREFIX>-deploy/SKILL.md`) and is populated during install (see `bootstrap/SKILL.md` Phase 2)

Example stub (`api-schema.md`):
```markdown
# API Schema

<!-- Fill in: endpoint contracts, request/response shapes -->
```

Example `<REFERENCE_SYNC_CHECKLIST>` for a skill with Backend + Database categories present:
```
- [ ] `references/api-schema.md` matches current endpoint shapes
- [ ] `references/db-schema.md` reflects current table/schema design
```

Example `<REFERENCES_LIST>` for the same skill:
```
- `references/api-schema.md` — endpoint contracts, request/response shapes
- `references/db-schema.md` — table key design, schema attributes
```

---

## § Design delegation block

Substitute into `<DESIGN_DELEGATION>` in the Domain skill stub **only** for the skill that owns the Frontend category, and **only when** a `<PREFIX>-design` skill exists in this install. Otherwise replace `<DESIGN_DELEGATION>` with an empty string (drop the placeholder line entirely).

Substitute `<PREFIX>` before insertion. This block enforces that visual decisions are made by `<PREFIX>-design` rather than re-invented inside the frontend skill (the gap that lets agents hard-code hex values into CSS files the frontend owns).

~~~markdown
## Visual Decisions — Delegate to <PREFIX>-design

`<PREFIX>-design` is the single authority for visual values. Before this skill declares CSS custom properties, picks colors/gradients, chooses fonts, or adjusts spacing/radius/shadow scales, **invoke `<PREFIX>-design`** and read `references/design-tokens.md`.

Specifically — invoke `<PREFIX>-design` first when about to:
- Add or modify any `--color-*`, `--font-*`, `--space-*`, `--radius-*`, `--shadow-*` (or similar) custom property
- Hard-code any hex / rgb / hsl / named color
- Define or tweak a gradient
- Pick a font family, weight, or size
- Introduce a new visual surface (card, panel, modal background)

This skill's job is to **apply** tokens defined by `<PREFIX>-design`, not to invent them. If the value already exists in `design-tokens.md`, reference it via `var(--token-name)`. If it doesn't, stop — invoke `<PREFIX>-design` to define it (which adds it to the tokens file), then return here to apply it.

~~~

---

## § deploy-config.yaml schema

The installer writes `<PREFIX>-deploy/references/deploy-config.yaml` during install (`install/SKILL.md § Populate deploy-config.yaml`) by detecting signals across the repo (CI workflows, deploy scripts, package.json scripts, IaC vars, framework configs). Canonical schema:

~~~yaml
components:
  <component_name>:                  # e.g. frontend, backend, worker
    verify: <env_name>                # which env's url proves this component works (e.g. local, dev, prod)
    envs:
      <env_name>:                     # e.g. local, dev, staging, prod — names are free; only "prod" is special
        run: "<cmd>"                  # serve-env: long-lived command that starts the component here (e.g. a dev server)
        deploy: "<cmd>"               # ship-env: terminating deploy command; when trigger: ci, a description of the triggering push/PR
        trigger: manual | ci          # ship-envs only; default: manual
        url: "<url>"                  # where the component is reachable in this env
        health_path: "<path>"         # optional, default "/" — appended to url for HTTP 2xx/3xx verification
        gate: auto | user_confirm     # ship-envs only; default: user_confirm for env named "prod", auto otherwise
        stack:                        # serve-envs only, optional — how to compose a verifiable local stack
          env:                        #   env-var overrides applied to `run` (e.g. point the frontend at the local backend, not prod)
            <VAR>: "<value>"
          seed: "<cmd>"               #   optional one-shot command that seeds test data before verification
          auth: "<strategy>"          #   optional note: how headless verification authenticates (test user creds env vars, bypass token, "none needed")
~~~

Rules encoded in the schema:
- **Every env declares exactly one of `run:` / `deploy:`.** `run:` marks a **serve-env** — a long-lived process started in place (typically `local`, a dev server); it is started only at the command top level, never by a subagent, and is never "deployed". `deploy:` marks a **ship-env** — a terminating command (or CI-push description) run by `<PREFIX>-deploy`.
- **Env selection is by simple predicate** (declaration order everywhere):
  - `<PREFIX>-dev` deploy (`target: non-prod`) → first non-prod env **with `deploy:`**; none → silent no-op.
  - Typed verifications (`<PREFIX>-test` UX/E2E) → first non-prod env's url — **never `prod`**; none → the verification is blocked.
  - `/code|/fix` pre-QA ensure-stack → first non-prod env **with `run:`** whose url is unreachable → started in background at the top level.
  - `target: prod` → the env named `prod` only.
- A component may declare only the envs that currently exist. Omitting `envs.prod` means "cannot deploy to prod yet" — this is how pre-launch components (typically frontends) are represented. Adding `envs.prod` is the GTM flip.
- `prod` is implicitly `gate: user_confirm` even if the field is omitted. Any other env name defaults to `gate: auto`.
- `trigger: ci` is the recommended default for prod. `<PREFIX>-deploy` does **not** run the command itself for `trigger: ci` — it gates via `AskUserQuestion`, then describes the push/PR that fires the deploy.
- `verify:` names the env whose `url` (+ optional `health_path`) `<PREFIX>-deploy` checks after acting. Any env name is valid.
- A component that can run locally should declare an `envs.local` serve-env even when it ships elsewhere — it is the zero-cost non-prod target typed verifications resolve to when no cloud non-prod env exists.
- **Composed local stack (`stack:`).** A serve-env's plain `run` often starts a component wired to prod (frontend pointing at the prod API, no auth session, no data) — headless verification against it silently degrades to nothing. When that's the case, declare `stack:` on the serve-env: `env:` overrides that wire components to each other locally (e.g. the frontend's API-base-URL var pointing at the local backend), an optional `seed:` command for test data, and an `auth:` strategy for headless login. The command's ensure-stack step applies `stack:` when starting the env; `<PREFIX>-test` then has a target it can actually verify. If a component's local verification is impossible even with overrides (e.g. hard dependency on a cloud-only service), leave `stack:` out — typed verifications will report blocked, which is the honest state.
- `health_path` is optional everywhere. When set, the skill appends it to the base url and checks HTTP 2xx/3xx; when absent, the skill checks the base url itself (effectively `/`).
- **Prefer one trigger workflow / deploy script per component.** The schema accommodates a monolithic trigger (one `deploy.yml` with multi-job branches keyed off paths or inputs) and per-component triggers (`deploy-<component>.yml`) equally — but only the split shape gets cleanly scoped top-level `paths:` filters and per-component dispatch. When `deploy-config.yaml` shows two or more components sharing the same `deploy:` value, that's a deferred refactor signal: every push has to evaluate cross-component job conditionals, and a tiny path-filter mistake silently bills the whole monolith. Split when adding a new component or when CI runtime starts mattering.
- There is no top-level `gtm` field. GTM status is implicit: pre-launch components omit `envs.prod`; live components declare it.
- **Caller-driven targeting.** `<PREFIX>-deploy` is invoked with `target: non-prod` (by `<PREFIX>-dev`) or `target: prod` (by the `/code|/fix --prod` command step). The skill never deploys across the boundary regardless of caller request; env resolution follows the selection predicates above.
- All consumption logic lives in `<PREFIX>-deploy/SKILL.md § Deployment` — never duplicate it in agents or other skills.

---

## § Project file sections

Use these templates when upserting sections into CLAUDE.md.

Substitute:
- `<PROJECT>` → project name
- `<PREFIX>` → project skill prefix
- `<SOURCE_OF_TRUTH_DOCS>` → discovered docs from Phase 1 (e.g. README.md, docs/workflow.md)

```markdown
## Plan Mode

- `<SOURCE_OF_TRUTH_DOCS>` — check before assuming how the delivery pipeline is structured
- After finalizing a plan, invoke `/code` to hand off to the agent pipeline

## Agents

Pipeline: `/code` or `/fix` → <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm. Details in `docs/workflow.md`.

Pipeline-shaped work started mid-conversation (a feature or fix that needs review and testing) routes through `/code` or `/fix` — never spawn the pipeline agents ad hoc; the commands own the capture, gating, and close-out steps the agents can't do. For small iterative rounds (pixel nudges, copy, hotfixes), use `/tweak` — its close-out is batched and enforced at push time. For multi-task autonomous runs (a roadmap batch, a goal to iterate toward), use `/pilot` — one up-front gate, per-task lane routing, single batched close-out. For leftover WIP (a dirty tree, orphaned stashes, stale branches), use `/tidy` — it establishes what each item is from history before proposing a disposition, rather than stashing or discarding blind.

## Skills

Path→skill ownership is defined in `.claude/hooks/governed-paths.conf` — edit that file to add or change path ownership. Both `skill-guard.sh` and `path-coverage-check.sh` source it automatically.

## Roadmap

`docs/roadmap.md` is the source of truth for open items.

## Secrets

Never ask for or accept secret values through chat — they become permanent transcript content. When a secret is needed, name the variable and where it goes, and have the user place it directly (edit `.env` themselves, use a `! <command>` shell escape, or a secret manager). Verify presence afterward (`grep -c '^VAR=' .env`), never echo values.
```

**Linting commands:** Embed in the relevant domain skill's `## Quality Checklist`, not in CLAUDE.md. `<PREFIX>-dev` step 3 delegates to these checklists. The hook `pre-handoff-check.sh` enforces lint at handoff time independently via its own `<LINT_CMD>` substitution.
