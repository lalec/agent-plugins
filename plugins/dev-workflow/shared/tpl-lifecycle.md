# Lifecycle Skill Templates

Substitute `<PROJECT>` with the project name and `<PREFIX>` with the chosen prefix. For `<PREFIX>-log`, also substitute `<PROJECT_ENCODED>` with the result of `$(echo "$PWD" | sed 's|/|-|g')`.

These skills are project-agnostic and require minimal substitution.

---

## § tosk-log/SKILL.md

```markdown
---
name: <PREFIX>-log
description: Use after every completed task in <PROJECT> — always the final step, after all other skill checklists are done — to append a delivery log entry to docs/project-log.md. Trigger whenever finishing any implementation work, bug fix, refactor, or infrastructure change. Records what shipped, how it was tested, and which skills were used.
---

# <PREFIX>-log

Project delivery log for <PROJECT>. Appends one entry to `docs/project-log.md` after each completed task so there's a running record of what shipped, how it was verified, and which skills drove it. Always the **last** step — run this after all other skill update checklists are done.

## Owned Paths
- `docs/project-log.md`  ← explicit file override; `docs/` directory is otherwise owned by <PREFIX>-docs

## Process

1. Identify the **primary feature/fix commit** for the task — the commit that changed source paths, never workflow bookkeeping (`test:`, `log:`, `docs:`, `chore(deploy-config):` commits). If the invocation prompt names a `Feature commit:` hash, use it; otherwise pick it from `git log --oneline -8`
2. Run `git log <hash> -1 --format="%ai"` to get that commit's timestamp — extract the `HH:MM` in local time for the date field
3. Identify which skills were actually invoked this session by scanning the most recent session transcript:
   ```bash
   PROJECT_ENCODED=$(echo "$PWD" | sed 's|/|-|g')
   grep -o '"skill":"[^"]*"' "$(ls -t ~/.claude/projects/${PROJECT_ENCODED}/*.jsonl 2>/dev/null | head -1)" | sort -u
   ```
   Use only skills that appear in this output for the **Skills** field. If none appear, use `—`.
4. Write the new entry at the **top** of `docs/project-log.md`, immediately below the header block, before the previous `---` separator
5. Commit the log entry — stage `docs/project-log.md` only and commit:
   ```bash
   git add docs/project-log.md
   git commit -m "log: <short title from the entry>"
   ```
6. Reproject the delivery graph so this entry becomes queryable — the log is the projector's
   primary input, so an unprojected entry is invisible to every downstream query:
   ```bash
   python3 .claude/graph/graph.py build
   ```
   The index is gitignored, so nothing further to commit. If the script is absent or exits
   non-zero, note it in the handoff and continue — this step never blocks the close-out.

## Entry Format

~~~
---
### YYYY-MM-DD HH:MM · `<7-char hash>` — <short title (not the commit message verbatim)>

<1–3 sentences. What shipped and why it matters. No label — this is the body.>

**Tests:** <what was actually verified>
**Skills:** <PREFIX>-x · <PREFIX>-y
**Deployed:** <component> → <env> · <url> (omit line entirely if no deploy happened)
**Addresses:** <roadmap **Id:** value(s), comma-separated> (omit line entirely if no tracked item is addressed)
**UAT-deferred:** <verification names + how confirmed> (omit line entirely if nothing was deferred)
**Decisions:** <gate>=<value> (<user|timeout|pilot-auto>) · … (omit line entirely if no gate was answered)
**Checklist:** <skill> — <what changed> (omit line entirely if nothing to note)
~~~

**Field guidance:**

- **Title** — short, plain English. Not the raw commit message — rephrase for a human skimming the log.
- **Body** — 1–3 sentences. Add context beyond the title: *why* it was needed, *what problem* it solves, any non-obvious decisions.
- **Tests** — be honest. "manual smoke" is a real test. Common values: `lint + type check (clean)`, `manual smoke in browser`, `E2E: <scenario>`, `none`. If a gate decision was auto-selected on a timeout, say so here — never record it as user-confirmed.
- **Skills** — only skills confirmed present in the transcript grep output, separated by ` · `. Use `—` if none found.
- **Deployed** — one line per component deployed this session, taken verbatim from the deploy-owning skill's report (e.g. `backend → test · https://test-api.example.com`). Omit the line entirely when no deploy happened.
- **Addresses** — the `**Id:**` of each `docs/roadmap.md` item this task advances or closes, comma-separated (e.g. `verification-email-on-signup, stripe-receipt-sender`). This is the durable roadmap↔delivery link: without it the connection survives only as a status flip that nothing can trace back. Use the ids the pm step confirmed; omit the line when the task addresses no tracked item, and say so in the pm handoff rather than guessing an id.
- **UAT-deferred** — verifications QA could not run in any environment, carried from the pipeline (e.g. `` `login-flow-e2e` (user-confirmed) ``). Backtick each verification name so it stays machine-readable. These are open follow-ups; omit the line when none.
- **Decisions** — one term per gate that was answered this task, as `<gate>=<value> (<how>)`, joined by ` · ` — e.g. `regression=smart (user) · ship=hold (timeout) · defer=accept (user)`. `<how>` is `user` (a real answer), `timeout` (a default taken on silence), or `pilot-auto` (decided autonomously mid-mission). **A timeout or an auto-decision is never recorded as `user`** — this line is the only durable record of whether a shipped change was actually consented to. Omit the line when no gate was answered.
- **Checklist** — one `skill — note` per skill whose reference files were updated. Omit the line entirely if nothing was updated.

## Quality Checklist
Required steps before writing the log entry:
1. [ ] Entry is at the top of docs/project-log.md (below the `# Project Log` header)
2. [ ] Hash is the primary feature/fix commit — not a `test:`/`log:`/`docs:` bookkeeping commit — and HH:MM comes from that commit's timestamp
3. [ ] Skills field is derived from transcript grep, not from memory
4. [ ] Body is 1–3 sentences, no `What:` label
5. [ ] `Deployed:` line included when a deploy occurred this session (env + url sourced from the deploy-owning skill's report); omitted otherwise
6. [ ] `Addresses:` carries the roadmap `**Id:**` the pm step confirmed, or the line is omitted — never a guessed id
7. [ ] `Decisions:` records every answered gate with its true `user` / `timeout` / `pilot-auto` origin
8. [ ] `Checklist:` line omitted when nothing was updated
9. [ ] `docs/project-log.md` committed with `log: <short title>`
10. [ ] `graph.py build` run after the commit (or its failure noted in the handoff)
```

---

## § tosk-review/SKILL.md

```markdown
---
name: <PREFIX>-review
description: Code review practices and verification gates. Use after task completion (request reviewer), when receiving feedback (process before implementing), or before claiming success (verify with evidence).
license: MIT
---

# <PREFIX>-review

Three distinct practices: receiving feedback, requesting reviews, verification gates. Static reference content — load the right reference for the situation. No `## Reference Sync` (this skill ships its references; the project does not author them).

**Core principle:** Technical correctness over social comfort. Verify before implementing. Evidence before claims.

## Read Map

```
SITUATION?
│
├─ Received review feedback       → references/code-review-reception.md
├─ Completed major task/feature   → references/requesting-code-review.md
├─ Issuing review findings (you   → references/issuing-findings.md
│  are the reviewer, e.g. <PREFIX>-qa)
├─ Reviewing for defect classes   → references/security-review.md
│  (deps, secrets, injection,
│  authz/IDOR, headers, dead code)
└─ About to claim success         → <PREFIX>-debug/references/verification.md
```

## References

- `references/code-review-reception.md` — feedback reception protocol (read → understand → verify → evaluate → respond → implement)
- `references/requesting-code-review.md` — code-reviewer subagent dispatch protocol
- `references/issuing-findings.md` — evidence requirements for review findings (no blocking finding without file:line)
- `references/security-review.md` — fast per-task security pass: deps/supply-chain, secrets, injection sinks, access-control (IDOR), insecure defaults + headers, dead surface; recon→verify triage; escalate to `/security-review` for deep changes
- `<PREFIX>-debug/references/verification.md` — completion verification gates (single source of truth — owned by `<PREFIX>-debug`)
```

**Also create these reference files when installing `<PREFIX>-review`:**

`references/code-review-reception.md`:

````markdown
# Code Review Reception

## Overview

Code review requires technical evaluation, not emotional performance.

**Core principle:** Verify before implementing. Ask before assuming. Technical correctness over social comfort.

## The Response Pattern

```
WHEN receiving code review feedback:

1. READ: Complete feedback without reacting
2. UNDERSTAND: Restate requirement in own words (or ask)
3. VERIFY: Check against codebase reality
4. EVALUATE: Technically sound for THIS codebase?
5. RESPOND: Technical acknowledgment or reasoned pushback
6. IMPLEMENT: One item at a time, test each
```

## Forbidden Responses

**NEVER:**
- "You're absolutely right!" (performative agreement)
- "Great point!" / "Excellent feedback!" (performative)
- "Let me implement that now" (before verification)

**INSTEAD:**
- Restate the technical requirement
- Ask clarifying questions
- Push back with technical reasoning if wrong
- Just start working (actions > words)

## Handling Unclear Feedback

```
IF any item is unclear:
  STOP - do not implement anything yet
  ASK for clarification on unclear items

WHY: Items may be related. Partial understanding = wrong implementation.
```

**Example:**
```
Partner: "Fix 1-6"
You understand 1,2,3,6. Unclear on 4,5.

❌ WRONG: Implement 1,2,3,6 now, ask about 4,5 later
✅ RIGHT: "I understand items 1,2,3,6. Need clarification on 4 and 5 before proceeding."
```

## Source-Specific Handling

### From Human Partner
- **Trusted** - implement after understanding
- **Still ask** if scope unclear
- **No performative agreement**
- **Skip to action** or technical acknowledgment

### From External Reviewers
```
BEFORE implementing:
  1. Check: Technically correct for THIS codebase?
  2. Check: Breaks existing functionality?
  3. Check: Reason for current implementation?
  4. Check: Works on all platforms/versions?
  5. Check: Does reviewer understand full context?

IF suggestion seems wrong:
  Push back with technical reasoning

IF can't easily verify:
  Say so: "I can't verify this without [X]. Should I [investigate/ask/proceed]?"

IF conflicts with partner's prior decisions:
  Stop and discuss with partner first
```

## YAGNI Check for "Professional" Features

```
IF reviewer suggests "implementing properly":
  grep codebase for actual usage

  IF unused: "This endpoint isn't called. Remove it (YAGNI)?"
  IF used: Then implement properly
```

## Implementation Order

```
FOR multi-item feedback:
  1. Clarify anything unclear FIRST
  2. Then implement in this order:
     - Blocking issues (breaks, security)
     - Simple fixes (typos, imports)
     - Complex fixes (refactoring, logic)
  3. Test each fix individually
  4. Verify no regressions
```

## When To Push Back

Push back when:
- Suggestion breaks existing functionality
- Reviewer lacks full context
- Violates YAGNI (unused feature)
- Technically incorrect for this stack
- Legacy/compatibility reasons exist
- Conflicts with partner's architectural decisions

**How to push back:**
- Use technical reasoning, not defensiveness
- Ask specific questions
- Reference working tests/code
- Involve partner if architectural

## Acknowledging Correct Feedback

When feedback IS correct:
```
✅ "Fixed. [Brief description of what changed]"
✅ "Good catch - [specific issue]. Fixed in [location]."
✅ [Just fix it and show in the code]

❌ "You're absolutely right!"
❌ "Great point!"
❌ ANY gratitude expression
```

**Why no thanks:** Actions speak. Just fix it.

## Gracefully Correcting Your Pushback

If you pushed back and were wrong:
```
✅ "You were right - I checked [X] and it does [Y]. Implementing now."
✅ "Verified this and you're correct. My initial understanding was wrong because [reason]. Fixing."

❌ Long apology
❌ Defending why you pushed back
❌ Over-explaining
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Performative agreement | State requirement or just act |
| Blind implementation | Verify against codebase first |
| Batch without testing | One at a time, test each |
| Assuming reviewer is right | Check if breaks things |
| Avoiding pushback | Technical correctness > comfort |
| Partial implementation | Clarify all items first |
| Can't verify, proceed anyway | State limitation, ask for direction |

## The Bottom Line

**External feedback = suggestions to evaluate, not orders to follow.**

Verify. Question. Then implement.

No performative agreement. Technical rigor always.
````

`references/requesting-code-review.md`:

````markdown
# Requesting Code Review

Dispatch code-reviewer subagent to catch issues before they cascade.

**Core principle:** Review early, review often.

## When to Request Review

**Mandatory:**
- After each task in subagent-driven development
- After completing major feature
- Before merge to main

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug

## How to Request

**1. Get git SHAs:**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # or origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

**2. Dispatch code-reviewer subagent:**

Use Task tool with `code-reviewer` type, providing these placeholders:

**Placeholders:**
- `{WHAT_WAS_IMPLEMENTED}` - What you just built
- `{PLAN_OR_REQUIREMENTS}` - What it should do
- `{BASE_SHA}` - Starting commit
- `{HEAD_SHA}` - Ending commit
- `{DESCRIPTION}` - Brief summary

**3. Act on feedback:**
- Fix Critical issues immediately
- Fix Important issues before proceeding
- Note Minor issues for later
- Push back if reviewer is wrong (with reasoning)

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request code review before proceeding.

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)

[Dispatch code-reviewer subagent]
  WHAT_WAS_IMPLEMENTED: Verification and repair functions for conversation index
  PLAN_OR_REQUIREMENTS: Task 2 from docs/plans/deployment-plan.md
  BASE_SHA: a7981ec
  HEAD_SHA: 3df7661
  DESCRIPTION: Added verifyIndex() and repairIndex() with 4 issue types

[Subagent returns]:
  Strengths: Clean architecture, real tests
  Issues:
    Important: Missing progress indicators
    Minor: Magic number (100) for reporting interval
  Assessment: Ready to proceed

You: [Fix progress indicators]
[Continue to Task 3]
```

## Integration with Workflows

**Subagent-Driven Development:**
- Review after EACH task
- Catch issues before they compound
- Fix before moving to next task

**Executing Plans:**
- Review after each batch (3 tasks)
- Get feedback, apply, continue

**Ad-Hoc Development:**
- Review before merge
- Review when stuck

## Red Flags

**Never:**
- Skip review because "it's simple"
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback

**If reviewer wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification
````

`references/issuing-findings.md`:

````markdown
# Issuing Review Findings

When **you** are the reviewer producing findings (running `<PREFIX>-qa`, dispatching the code-reviewer subagent, doing a manifest check, lint sweep, schema audit), every blocking finding requires evidence read **in this session**.

For the **defect classes** to inspect during a security pass (dependencies, secrets, injection sinks, access control, insecure defaults, dead surface), see `security-review.md` — the evidence bar below applies to each.

## Core Principle

**Read before you flag.** A finding that something is missing, wrong, stale, or out-of-sync requires reading the target file *in this session* before issuing the finding. Inferred-from-context findings are hypotheses, not findings — and blocking the pipeline on a hypothesis costs a full re-spawn cycle.

## The Rule

```
BEFORE issuing a finding that blocks the pipeline:

1. IDENTIFY: which file / line / symbol the finding is about
2. READ: the actual file (Read tool) or grep result IN THIS SESSION
3. CITE: include file:line + a short snippet in the finding
4. ONLY THEN: issue the finding

No citation in this session = not a finding. State it as
"Suspected: <claim> — verifying" and verify before blocking.
```

## What Counts as Evidence

| Finding type | Evidence required |
|---|---|
| "X is missing from file Y" | Read Y in this session, confirm absence |
| "X has the wrong shape" | Read X's definition, paste the actual shape |
| "Reference Z is broken" | Grep for Z's definition; cite zero hits OR mismatched location |
| "Test fails" | Run the test in this session, capture exit code + output |
| "Token --X is undefined" | Grep for `--X` in :root / token files; cite zero hits |

## Negative-Existence Claims

"X does not exist" requires *one* of:
- A grep across the relevant scope returning zero hits (paste the command and result), OR
- A read of the file that should contain X, confirming X is absent

A failing memory or a hunch is not evidence.

## Common Failure Modes

- **Inferring from context** — "the manifest probably doesn't have rows for patterns 8–11" without reading it.
- **Stale evidence** — citing a file you read 20 messages ago when the dev agent has since edited it. Re-read after any handoff.
- **Lint-by-feel** — "this looks wrong" without identifying the specific rule that's violated.
- **Confusing discovery and verification** — reading a file three times for layout but never grepping for the identifier you're about to flag.

## Finding Format

Every blocking finding should be structured as:

```
**Finding:** <one-line claim>
**Evidence:** <file:line> — <short snippet or grep output>
**Severity:** blocking | important | minor
```

If you cannot fill in **Evidence** with a fresh citation from this session, the finding does not block — convert it to a "suspected" item and verify first.

## Bottom Line

**Findings without evidence are noise.** Cheap to write, expensive to act on. The pipeline cost of one false-positive block is roughly 2 extra agent spawns (~$0.30–$0.60 and 3 minutes wall-clock) — far more than one extra Read or grep.
````

`references/security-review.md`:

````markdown
# Security Review

The fast, deterministic, per-task security pass — the defect classes coding agents ship (and rate as safe) plus the cheap whole-tree checks a diff-scoped reviewer misses. **Not** a replacement for the built-in `/security-review` (deep, diff-aware, multi-file SAST): run that periodically and escalate to it for complex auth/crypto/multi-file logic. This pass is grep- and audit-command-cheap, so run it every task — agent-written code degrades in security across iterations and models over-trust their own output.

## Principle — recon → verify, evidence over artifact

Deterministic first (grep + the project's audit tool), then reason. For every candidate:

1. RECON — locate the candidate (grep / audit output / route file).
2. VERIFY — confirm a **reachable, exploitable path** (trace untrusted input → sink; confirm the endpoint is actually served). A static-shell match, a scanner hit, or a pattern alone is **not** a finding.
3. Fix the underlying **enabler**, not the literal string the scanner matched.

A verified finding blocks; an unverified one is `Suspected: <claim> — verifying`, advisory only. Use the `issuing-findings.md` Finding/Evidence/Severity format — no blocking finding without a fresh `file:line` read in this session.

## Checklist (skip rows that don't apply to this project)

### A. Dependencies & supply chain
- Run the project's audit on the whole tree — `npm audit` / `pnpm audit` / `pip-audit` / `cargo audit` / `osv-scanner` (recognition aids, not a whitelist). **Block** on high/critical, or any vuln the task introduced/touched; note unrelated lower-severity debt without blocking (same policy as pre-existing test failures).
- Every newly-added dependency: confirm the package **actually exists** on its registry and the name is not a typosquat or model hallucination (slopsquatting).
- Flag unused / redundant dependencies — each is attack surface.

### B. Secrets & sensitive data
- No hardcoded secrets, API keys, tokens, or connection strings in source; no committed `.env`.
- Secrets / PII do not leak into logs, error responses, or client-visible output.

### C. Input → sink (injection & output-encoding)
- Untrusted input reaching a SQL / OS-command / HTML-DOM / template / deserialization (`pickle`, `yaml.load`) / `eval` sink is parameterized or sanitized at the sink.
- Output is encoded for its context (HTML, attribute, JSON-LD, URL). Verify the sink is reachable before flagging.

### D. Access control
- Every new endpoint / mutation enforces **object-level authorization** — the caller may act on *this specific resource*, not merely that they are authenticated. Guards against IDOR and missing function-level authz (the authn↔authz confusion agents ship).

### E. Insecure defaults & transport (web-facing only)
- Hosting config sets the standard response headers: `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`. The fix lands in the hosting config owned by `<PREFIX>-deploy`. (When a static host can't inject per-request nonces, an inline-script `unsafe-inline` allowance is a documented tradeoff — not a bug — where there is no reachable sink; skip deprecated `X-XSS-Protection`, CSP supersedes it.)
- CORS is not `*` combined with credentials; cookies set `Secure` + `HttpOnly` + `SameSite`; TLS verification is not disabled (`verify=False`, `rejectUnauthorized: false`, `InsecureSkipVerify`); debug mode and verbose stack traces are off in production.

### F. Dead / unused surface
- Genuinely-unused endpoints, exports, and dependencies are attack surface — flag for removal, evidenced by a usage grep returning zero callers.

## Escalate
For complex authentication, cryptography, or multi-file logic changes, hand off to the built-in `/security-review` (diff-aware deep reasoning across ~25 vulnerability classes) rather than reasoning it through here.
````

(Verification gates content lives in `<PREFIX>-debug/references/verification.md` — `<PREFIX>-review` references it instead of carrying its own copy.)

---

## § tosk-debug/SKILL.md

```markdown
---
name: <PREFIX>-debug
description: Systematic debugging — root cause before fixes. Use for bugs, test failures, unexpected behavior, or before claiming work complete.
---

# <PREFIX>-debug

Debugging framework. Static reference content — load the right reference for the situation. No `## Reference Sync` (this skill ships its references; the project does not author them).

## Iron Law

**NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.** Random fixes waste time and create new bugs. Find the root cause, fix at source, validate at every layer, verify before claiming success.

## Read Map

```
Bug or issue                    → references/systematic-debugging.md (4-phase framework)
Error deep in call stack        → references/root-cause-tracing.md (trace backward)
Found root cause, hardening it  → references/defense-in-depth.md (4 validation layers)
About to claim success          → references/verification.md (evidence before claims)
```

`scripts/find-polluter.sh` bisects test pollution; documented in `root-cause-tracing.md`.

## References

- `references/systematic-debugging.md` — 4-phase framework (investigate → analyze → hypothesize → implement)
- `references/root-cause-tracing.md` — backward call-stack tracing + `scripts/find-polluter.sh`
- `references/defense-in-depth.md` — 4-layer validation (entry / business / environment / debug instrumentation)
- `references/verification.md` — completion verification gates (single source of truth — also referenced by `<PREFIX>-review`)

## Red Flags — return to read map

"Quick fix for now" · "Just try X" · "It's probably X" · "Should work now" · "Tests pass, we're done" (without rerunning).
```

**Also create these reference files and scripts when installing `<PREFIX>-debug`:**

`references/systematic-debugging.md`:

````markdown
# Systematic Debugging

Four-phase debugging framework that ensures root cause investigation before attempting fixes.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If haven't completed Phase 1, cannot propose fixes.

## The Four Phases

Must complete each phase before proceeding to next.

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully** - Don't skip past errors/warnings, read stack traces completely
2. **Reproduce Consistently** - Can trigger reliably? Exact steps? If not reproducible → gather more data
3. **Check Recent Changes** - What changed? Git diff, recent commits, new dependencies, config changes
   - For a file you suspect, ask the delivery graph what it already knows before re-deriving it:
     `python3 .claude/graph/graph.py history <path>` — what shipped here, what covers it, what was
     reverted. A path with a `(REVERTED)` delivery is the strongest single lead available. Skip
     silently if the script is absent or errors.
4. **Gather Evidence in Multi-Component Systems**
   - For EACH component boundary: log data entering/exiting, verify environment propagation
   - Run once to gather evidence showing WHERE it breaks
   - THEN analyze to identify failing component
5. **Trace Data Flow** - Where does bad value originate? Trace up call stack until finding source (see root-cause-tracing.md)

### Phase 2: Pattern Analysis

**Find pattern before fixing:**

1. **Find Working Examples** - Locate similar working code in same codebase
2. **Compare Against References** - Read reference implementation COMPLETELY, understand fully before applying
3. **Identify Differences** - List every difference however small, don't assume "that can't matter"
4. **Understand Dependencies** - What other components, settings, config, environment needed?

### Phase 3: Hypothesis and Testing

**Scientific method:**

1. **Form Single Hypothesis** - "I think X is root cause because Y", be specific not vague
2. **Test Minimally** - SMALLEST possible change to test hypothesis, one variable at a time
3. **Verify Before Continuing** - Worked? → Phase 4. Didn't work? → NEW hypothesis. DON'T add more fixes
4. **When Don't Know** - Say "I don't understand X", don't pretend, ask for help

### Phase 4: Implementation

**Fix root cause, not symptom:**

1. **Create Failing Test Case** - Simplest reproduction, automated if possible, MUST have before fixing
2. **Implement Single Fix** - Address root cause identified, ONE change, no "while I'm here" improvements
3. **Verify Fix** - Test passes? No other tests broken? Issue actually resolved?
4. **If Fix Doesn't Work**
   - STOP. Count: How many fixes tried?
   - If < 3: Return to Phase 1, re-analyze with new information
   - **If ≥ 3: STOP and question architecture**
5. **If 3+ Fixes Failed: Question Architecture**
   - Pattern: Each fix reveals new shared state/coupling problem elsewhere
   - STOP and question fundamentals: Is pattern sound? Wrong architecture?
   - Discuss with human partner before more fixes

## Red Flags - STOP and Follow Process

If catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "One more fix attempt" (when already tried 2+)

**ALL mean:** STOP. Return to Phase 1.

## Human Partner Signals You're Doing It Wrong

- "Is that not happening?" - Assumed without verifying
- "Will it show us...?" - Should have added evidence gathering
- "Stop guessing" - Proposing fixes without understanding
- "Ultrathink this" - Question fundamentals, not just symptoms
- "We're stuck?" (frustrated) - Approach isn't working

**When see these:** STOP. Return to Phase 1.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too |
| "Emergency, no time for process" | Systematic is FASTER than guess-and-check |
| "Just try this first, then investigate" | First fix sets pattern. Do right from start |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem |

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common
````

`references/root-cause-tracing.md`:

````markdown
# Root Cause Tracing

Systematically trace bugs backward through call stack to find original trigger.

## Core Principle

**Trace backward through call chain until finding original trigger, then fix at source.**

Bugs often manifest deep in call stack. Instinct is to fix where error appears, but that's treating the symptom.

## When to Use

**Use when:**
- Error happens deep in execution (not at entry point)
- Stack trace shows long call chain
- Unclear where invalid data originated
- Need to find which test/code triggers problem

## The Tracing Process

### 1. Observe the Symptom
```
Error: git init failed in /project/packages/core
```

### 2. Find Immediate Cause
What code directly causes this?
```typescript
await execFileAsync('git', ['init'], { cwd: projectDir });
```

### 3. Ask: What Called This?
```typescript
WorktreeManager.createSessionWorktree(projectDir, sessionId)
  → called by Session.initializeWorkspace()
  → called by Session.create()
  → called by test at Project.create()
```

### 4. Keep Tracing Up
What value was passed?
- `projectDir = ''` (empty string!)
- Empty string as `cwd` resolves to `process.cwd()`
- That's the source code directory!

### 5. Find Original Trigger
Where did empty string come from?
```typescript
const context = setupCoreTest(); // Returns { tempDir: '' }
Project.create('name', context.tempDir); // Accessed before beforeEach!
```

## Adding Stack Traces

When can't trace manually, add instrumentation:

```typescript
async function processData(directory: string) {
  const stack = new Error().stack;
  console.error('DEBUG processData:', {
    directory,
    cwd: process.cwd(),
    stack,
  });

  await runOperation({ cwd: directory });
}
```

**Critical:** Use `console.error()` in tests (not logger - may not show)

**Run and capture:**
```bash
<test-runner> 2>&1 | grep 'DEBUG message'
```

**Analyze stack traces:**
- Look for test file names
- Find line number triggering call
- Identify pattern (same test? same parameter?)

## Finding Which Test Causes Pollution

If something appears during tests but don't know which test:

Use bisection script: `scripts/find-polluter.sh`

```bash
./scripts/find-polluter.sh '<artifact-to-check>' '<test-file-pattern>'
```

Runs tests one-by-one, stops at first polluter.

## Key Principle

**NEVER fix just where error appears.** Trace back to find original trigger.

When found immediate cause:
- Can trace one level up? → Trace backwards
- Is this the source? → Fix at source
- Then add validation at each layer (see defense-in-depth.md)

## Real Example

**Symptom:** `.git` created in `packages/core/` (source code)

**Trace chain:**
1. `git init` runs in `process.cwd()` ← empty cwd parameter
2. WorktreeManager called with empty projectDir
3. Session.create() passed empty string
4. Test accessed `context.tempDir` before beforeEach
5. setupCoreTest() returns `{ tempDir: '' }` initially

**Root cause:** Top-level variable initialization accessing empty value

**Fix:** Made tempDir a getter that throws if accessed before beforeEach

**Also added defense-in-depth:**
- Layer 1: Project.create() validates directory
- Layer 2: WorkspaceManager validates not empty
- Layer 3: ENV guard refuses dangerous ops outside tmpdir
- Layer 4: Stack trace logging before critical operations
````

`references/defense-in-depth.md`:

````markdown
# Defense-in-Depth Validation

Validate at every layer data passes through to make bugs impossible.

## Core Principle

**Validate at EVERY layer data passes through. Make bug structurally impossible.**

When fix bug caused by invalid data, adding validation at one place feels sufficient. But single check can be bypassed by different code paths, refactoring, or mocks.

## Why Multiple Layers

Single validation: "We fixed bug"
Multiple layers: "We made bug impossible"

Different layers catch different cases:
- Entry validation catches most bugs
- Business logic catches edge cases
- Environment guards prevent context-specific dangers
- Debug logging helps when other layers fail

## The Four Layers

### Layer 1: Entry Point Validation
**Purpose:** Reject obviously invalid input at API boundary

```typescript
function createProject(name: string, workingDirectory: string) {
  if (!workingDirectory || workingDirectory.trim() === '') {
    throw new Error('workingDirectory cannot be empty');
  }
  if (!existsSync(workingDirectory)) {
    throw new Error(`workingDirectory does not exist: ${workingDirectory}`);
  }
  if (!statSync(workingDirectory).isDirectory()) {
    throw new Error(`workingDirectory is not a directory: ${workingDirectory}`);
  }
  // proceed
}
```

### Layer 2: Business Logic Validation
**Purpose:** Ensure data makes sense for this operation

```typescript
function initializeWorkspace(projectDir: string, sessionId: string) {
  if (!projectDir) {
    throw new Error('projectDir required for workspace initialization');
  }
  // proceed
}
```

### Layer 3: Environment Guards
**Purpose:** Prevent dangerous operations in specific contexts

```typescript
async function gitInit(directory: string) {
  // In tests, refuse git init outside temp directories
  if (process.env.NODE_ENV === 'test') {
    const normalized = normalize(resolve(directory));
    const tmpDir = normalize(resolve(tmpdir()));

    if (!normalized.startsWith(tmpDir)) {
      throw new Error(
        `Refusing git init outside temp dir during tests: ${directory}`
      );
    }
  }
  // proceed
}
```

### Layer 4: Debug Instrumentation
**Purpose:** Capture context for forensics

```typescript
async function gitInit(directory: string) {
  const stack = new Error().stack;
  logger.debug('About to git init', {
    directory,
    cwd: process.cwd(),
    stack,
  });
  // proceed
}
```

## Applying the Pattern

When find bug:

1. **Trace data flow** - Where does bad value originate? Where used?
2. **Map all checkpoints** - List every point data passes through
3. **Add validation at each layer** - Entry, business, environment, debug
4. **Test each layer** - Try to bypass layer 1, verify layer 2 catches it

## Example from Real Session

Bug: Empty `projectDir` caused `git init` in source code

**Data flow:**
1. Test setup → empty string
2. `Project.create(name, '')`
3. `WorkspaceManager.createWorkspace('')`
4. `git init` runs in `process.cwd()`

**Four layers added:**
- Layer 1: `Project.create()` validates not empty/exists/writable
- Layer 2: `WorkspaceManager` validates projectDir not empty
- Layer 3: `WorktreeManager` refuses git init outside tmpdir in tests
- Layer 4: Stack trace logging before git init

**Result:** All tests passed, bug impossible to reproduce

## Key Insight

All four layers were necessary. During testing, each layer caught bugs others missed:
- Different code paths bypassed entry validation
- Mocks bypassed business logic checks
- Edge cases on different platforms needed environment guards
- Debug logging identified structural misuse

**Don't stop at one validation point.** Add checks at every layer.
````

`references/verification.md`:

````markdown
# Verification Before Completion

Run verification commands and confirm output before claiming success.

## Core Principle

**Evidence before claims, always.**

Claiming work complete without verification is dishonesty, not efficiency.

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If haven't run verification command in this message, cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make claim

Skip any step = lying, not verifying
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags - STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!")
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "Partial check is enough" | Partial proves nothing |

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written regression test" (without red-green verification)
```

**Build:**
```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion
- Moving to next task
- Delegating to agents

**Rule applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness

## The Bottom Line

**No shortcuts for verification.**

Run command. Read output. THEN claim result.

Non-negotiable.
````

`scripts/find-polluter.sh` — create as executable file (`chmod +x` after creating):

````bash
#!/bin/bash
# Bisection script to find which test creates unwanted files/state
# Usage: ./find-polluter.sh <file_or_dir_to_check> <test_pattern>
# Example: ./find-polluter.sh '<artifact-to-check>' '<test-file-pattern>'
#
# CONFIGURE: Set your project's test runner command below
# Examples: npm test, pytest, go test ./..., bundle exec rspec, cargo test
TEST_RUNNER="npm test"

set -e

if [ $# -ne 2 ]; then
  echo "Usage: $0 <file_to_check> <test_pattern>"
  echo "Example: $0 '<artifact-to-check>' '<test-file-pattern>'"
  exit 1
fi

POLLUTION_CHECK="$1"
TEST_PATTERN="$2"

echo "🔍 Searching for test that creates: $POLLUTION_CHECK"
echo "Test pattern: $TEST_PATTERN"
echo ""

# Get list of test files
TEST_FILES=$(find . -path "$TEST_PATTERN" | sort)
TOTAL=$(echo "$TEST_FILES" | wc -l | tr -d ' ')

echo "Found $TOTAL test files"
echo ""

COUNT=0
for TEST_FILE in $TEST_FILES; do
  COUNT=$((COUNT + 1))

  # Skip if pollution already exists
  if [ -e "$POLLUTION_CHECK" ]; then
    echo "⚠️  Pollution already exists before test $COUNT/$TOTAL"
    echo "   Skipping: $TEST_FILE"
    continue
  fi

  echo "[$COUNT/$TOTAL] Testing: $TEST_FILE"

  # Run the test
  $TEST_RUNNER "$TEST_FILE" > /dev/null 2>&1 || true

  # Check if pollution appeared
  if [ -e "$POLLUTION_CHECK" ]; then
    echo ""
    echo "🎯 FOUND POLLUTER!"
    echo "   Test: $TEST_FILE"
    echo "   Created: $POLLUTION_CHECK"
    echo ""
    echo "Pollution details:"
    ls -la "$POLLUTION_CHECK"
    echo ""
    echo "To investigate:"
    echo "  $TEST_RUNNER $TEST_FILE    # Run just this test"
    echo "  cat $TEST_FILE         # Review test code"
    exit 1
  fi
done

echo ""
echo "✅ No polluter found - all tests clean!"
exit 0
````

`scripts/find-polluter.test.md`:

````markdown
# find-polluter.sh Test Documentation

## Purpose
Bisection script to find which test creates unwanted files or state pollution.

## Manual Test Procedure

### Setup Test Scenario
```bash
# Create test directory
mkdir -p /tmp/polluter-test && cd /tmp/polluter-test

# Create clean test
cat > test1.test.js << 'EOF'
console.log('Test 1: clean');
EOF

# Create polluter test
cat > test2.test.js << 'EOF'
const fs = require('fs');
fs.mkdirSync('.git', { recursive: true });
console.log('Test 2: creates pollution');
EOF

# Create another clean test
cat > test3.test.js << 'EOF'
console.log('Test 3: clean');
EOF
```

### Run Script
```bash
# Run with your project's test runner (edit TEST_RUNNER in the script first)
./find-polluter.sh '.git' '<test-file-pattern>'
```

### Expected Output
```
🔍 Searching for test that creates: .git
Test pattern: <test-file-pattern>

Found 3 test files

[1/3] Testing: ./test1.test.js
[2/3] Testing: ./test2.test.js

🎯 FOUND POLLUTER!
   Test: ./test2.test.js
   Created: .git
```

### Cleanup
```bash
rm -rf /tmp/polluter-test
```

## Test Results

✅ Script logic verified
- Correctly iterates through test files
- Detects pollution creation
- Reports the polluting test file
- Exits early when polluter found

## Usage Notes

**Prerequisites:**
- Test runner must be configured and installed
- `TEST_RUNNER` variable at top of script must match your project's test command
- Test pattern must match actual test files
- Pollution path must be accurate

**Customization:**
Edit the `TEST_RUNNER` variable at the top of `find-polluter.sh`:
```bash
# Default (Node.js projects)
TEST_RUNNER="npm test"

# Python projects
TEST_RUNNER="pytest"

# Go projects
TEST_RUNNER="go test ./..."

# Ruby projects
TEST_RUNNER="bundle exec rspec"
```

## Common Use Cases

1. **Find test creating .git directory:**
   ```bash
   ./find-polluter.sh '.git' '<test-file-pattern>'
   ```

2. **Find test creating node_modules:**
   ```bash
   ./find-polluter.sh 'node_modules' '<test-file-pattern>'
   ```

3. **Find test creating specific file:**
   ```bash
   ./find-polluter.sh 'unwanted-file.txt' '<test-file-pattern>'
   ```
````

---

## § <PREFIX>-design/SKILL.md (conditional — create when frontend/website domain skill is present)

This skill is created in addition to the frontend domain skill whenever the project has an HTML/CSS/JS website or UI framework. The frontend skill owns files; the design skill owns visual decisions.

```markdown
---
name: <PREFIX>-design
description: Visual authority for <PROJECT>. MUST be invoked before any color, gradient, font, spacing, or CSS custom property decision — including declaring `--color-*`, `--font-*`, `--space-*` variables, picking hex values, or modifying typography. Owns the <PROJECT> design system: palette, tokens, typography, surface system.
---

# <PREFIX>-design

Visual authority for all <PROJECT> UI decisions. No other skill is permitted to invent visual values. Use `ui-ux-pro-max` when executing design work.

> **Design skill:** This skill delegates execution to `ui-ux-pro-max` by default. If you prefer a different design skill, replace `ui-ux-pro-max` with your chosen skill name in the two lines above and below this note.

When the user asks to explore design alternatives for a specific component, use `ui-ux-pro-max` to generate variants — but constrain it to the <PROJECT> design system (palette, fonts, surface). Do not propose styles or palettes outside the existing system.

## When this skill MUST be invoked

Other skills (especially `<PREFIX>-frontend`) **must** invoke this skill before:
- Declaring or modifying any CSS custom property (`--color-*`, `--font-*`, `--space-*`, `--radius-*`, `--shadow-*`, etc.)
- Picking or hard-coding any color value (hex, rgb, hsl, named)
- Defining or modifying gradients
- Choosing font family, weight, or size
- Adjusting spacing, radius, shadow, or other visual scales
- Adding a new visual surface (card, panel, modal background)

If a value already exists in `references/design-tokens.md`, reference it. If not, this skill defines it (and adds it to the tokens file) — never the calling skill.

## What this skill owns
- Color palette (exact hex values and gradient stops) — see `references/design-tokens.md`
- CSS custom properties and design variables
- Typography system (font families, weights, sizes)
- Dark/light surface system
- Component visual patterns

## References
- `references/design-tokens.md` — color palette, CSS vars, typography, spacing (immutable constraints — do not override without explicit instruction)

## Reference Sync
Verify before finishing any <PREFIX>-design invocation:
- [ ] `references/design-tokens.md` lists all current design tokens and CSS custom properties
- [ ] Every newly introduced visual value (color, gradient, font, spacing) has a corresponding entry in `design-tokens.md`
- [ ] No removed tokens or renamed classes still referenced
```

**Also create this reference file when installing `<PREFIX>-design`:**

`references/design-tokens.md`:
```markdown
# Design Tokens

<!-- Fill in: color palette (hex values), CSS custom properties, typography (font families, weights), spacing scale, surface colors, glow/shadow values -->
```

---

## § tosk-deploy/SKILL.md

```markdown
---
name: <PREFIX>-deploy
description: Deploy authority for <PROJECT> — single source of truth for how it deploys. Invoked by the <PREFIX>-dev deploy step (target=non-prod) and the /code|/fix --prod prod step (target=prod); not triggered autonomously. Reads references/deploy-config.yaml, runs the right deploy command per affected component/env, respects gates, verifies the result is reachable, and reports env + url so <PREFIX>-log can record the deploy.
---

# <PREFIX>-deploy

Single source of truth for *how* <PROJECT> deploys. Agents and other skills delegate here — no deploy logic lives anywhere else.

## Deployment

Read `references/deploy-config.yaml` before any deploy action.

**Caller contract.** Caller passes `target`:
- `target: non-prod` → deploy only to the **first** non-prod env **with a `deploy:` command** (declaration order). Serve-envs (`run:`) are never deployed — they are started at the command top level, not here. If a component has no non-prod ship-env, return silently for that component. **Early exit:** if no component in the yaml declares a non-prod ship-env at all, report `non-prod: no-op (no non-prod ship-env declared)` immediately — don't walk components one by one.
- `target: prod` → deploy only to the env named `prod`. If `prod` is not declared (pre-launch component), return silently.

Never deploy across the boundary regardless of caller request. `<PREFIX>-dev` always passes `non-prod` (mid-pipeline, so `<PREFIX>-qa` tests a running stack). `target: prod` is passed only by the top-level `/code --prod` / `/fix --prod` command step **after** QA sign-off — never by a subagent, because the prod gate below needs `AskUserQuestion` and that only reaches the user at the top level. If `target: prod` is ever requested from a context where `AskUserQuestion` can't reach the user (i.e. invoked inside a subagent), refuse and return without deploying — prod requires the top-level command.

**Fill-in pass** (before any deploy action, for the resolved target env):
- Required per ship-env: `deploy`, `url`. Required per serve-env: `run`, `url`.
- If any required field is missing or empty, batch every gap into a single `AskUserQuestion`. Apply the answers back to `deploy-config.yaml` and commit with `chore(deploy-config): fill <env> values` before proceeding.
- Never invent values; never write placeholder text like `<fill in>`.

**Per affected component**, resolve `verify:` to its named env:
- `verify:` names a **serve-env** (`run:`) → check its `url` (suffixed by `health_path` if set, else `/`) returns HTTP 2xx/3xx. If not reachable, **do not auto-start it** — when this skill is invoked from the `<PREFIX>-dev` subagent, `AskUserQuestion` (and a long-running server process) can't be driven from there. Report `<env> not running — start with envs.<env>.run` and return without deploying; the caller surfaces it and the user (or the command's ensure-stack step) starts it, then re-runs.
- `verify:` names a **ship-env** (`deploy:`) → run its `deploy`, wait for it to finish, then confirm its `url` (suffixed by `health_path` if set, else `/`) returns HTTP 2xx/3xx.

**Gates** (per env):
- `gate: auto` → run the deploy command directly. Default for any env not named `prod`.
- `gate: user_confirm` → build a context block from values that resolve, omitting any whose source is empty:
  - `env: <name>`
  - `url: <envs.<env>.url>`
  - `command: <envs.<env>.deploy>`
  - `trigger: <manual|ci>` (+ `workflow: <ci-workflow-file>` when `trigger: ci` and the workflow file is known)
  - `commit: <git rev-parse --short HEAD>`
  - `branch: <git rev-parse --abbrev-ref HEAD>`

  Pass the block as `AskUserQuestion` context, ask "Deploy to `<env>`?" with options Yes / No. On Yes, run the deploy command. On No, return `gate: declined` and skip. If the question goes unanswered (timeout), return `gate: unanswered — parked` — never proceed, and never treat silence as consent; the caller parks and resumes when the user responds. The gate runs **inside this skill's turn** — never return control to the caller before the question is answered or times out. Default for any env named `prod` even if the field is omitted.

  **Pre-authorization:** a top-level command caller may pass `preauth: user shipped at Step 0.5` — the user answered the command's Ship question and the caller has verified its cleanliness conditions (clean sign-off, no timeout-auto-decisions, shipped set = reviewed set). With `preauth`, skip the question and proceed, recording `gate: pre-authorized (Step 0.5 Ship)` in the report. Accept `preauth` only from the top-level command (never a subagent), and never infer it — no explicit `preauth` field, no skip.

**Triggers** (per env):
- `trigger: manual` → run the deploy command in this session.
- `trigger: ci` → do **not** run the command. Describe the push/PR that fires the real deploy, then return. When combined with `gate: user_confirm`, still gate via `AskUserQuestion` before describing the action.

**Pre-launch guard:** if the requested env is not declared in `deploy-config.yaml`, do not attempt the deploy. Declaring a new env (for example, a frontend gaining `envs.prod` at GTM) is an explicit decision — update the yaml first.

**Report:** after any deploy, emit one line per component in the form `<component> → <env> · <url>` so `<PREFIX>-log` can include it in the delivery log entry.

## Push policy

`git push` is a deploy action whenever a CI ship-env fires on push. Callers (the `/code`/`/fix` close-out step, `/tweak` exit, `/revert`) resolve pushability here — raw pushes must not bypass this skill's gates:

1. Read `references/deploy-config.yaml`. If any component declares a ship-env with `trigger: ci` whose deploy fires on a push to the current branch, pushing **is** shipping to that env.
2. If that env is `prod` (or gated `user_confirm`): push only after the prod gate passed this session, or after an explicit `AskUserQuestion` confirm with the same context block. Unanswered → `gate: unanswered — parked`; never push on silence.
3. Otherwise pushing is safe — push directly.
4. **After any CI-coupled push:** watch the CI run to completion (`gh run watch` or the platform equivalent) and verify the deployed env's url/health before reporting "deployed". A push with CI still running is "deploying", not "deployed" — never end a shipping turn without the health check.

## Reference Sync

Verify before finishing any `<PREFIX>-deploy` invocation:
- [ ] `references/deploy-config.yaml` matches the components, envs, commands, urls, gates, and triggers currently in use

## References

- `references/deploy-config.yaml` — per-component deploy profile (verify target, envs, commands, urls, gates, triggers, optional health_path)
```

`references/deploy-config.yaml` is **populated** during install (not a stub) — see `tpl-domain-skill.md § deploy-config.yaml schema` for the schema and `bootstrap/SKILL.md` Phase 2 for the population procedure.

---

## § tosk-test/SKILL.md

```markdown
---
name: <PREFIX>-test
description: Use when writing or performing tests for <PROJECT>. Trigger any time the user wants to verify the app works, run tests against the deployed stack, test a new feature, or perform end-to-end UI testing.
---

# <PREFIX>-test

Testing authority for <PROJECT>. Runs three tiers — **Smoke** (always), **Functional Feature Tests** (per-task verifications captured by `/code` and `/fix`), and **Regression** (on demand). Unit tests are not this skill's responsibility — they belong to domain skill Quality Checklists.

## Test Plan

**Step 1 — Select tiers** from the invoking context:

| Tier | Source | When to run |
|---|---|---|
| **Smoke** | `references/test-commands.md § Smoke` | Always, every invocation |
| **Functional Feature** | `references/custom-tests.yaml` | This task's verifications always; prior verifications whose `paths:` intersect the changed paths named in the prompt |
| **Regression** | `references/test-commands.md § Regression` + every `custom-tests.yaml` verification | Only when the caller passes `regression_mode: full` |

If the prompt names no changed paths and no new verifications (a bare smoke request), run Smoke only — plus Regression when `regression_mode: full`.

**Step 2 — Execute** in tier order (Smoke → Functional Feature → Regression). Report actual vs expected per tier before moving to the next.

## Smoke

Always-run baseline: service/endpoint reachability + log check. Curl templates and run commands: `references/test-commands.md § Smoke`. Smoke is liveness only — don't add a check for an endpoint already covered by an Integration/E2E verification in `custom-tests.yaml`.

## Functional Feature Tests

Per-task verifications captured up-front by `/code` and `/fix` and accumulated in `references/custom-tests.yaml`. This skill resolves *how* to verify each one at runtime — read `references/custom-tests.md` for the schema, the execution protocol (type → tool → pass criterion, including the UX/E2E screenshot rule), and the prior-selection rule before running this tier.

## Regression

Full broad suite — `references/test-commands.md § Regression` (hand-authored) plus every verification in `custom-tests.yaml`. Run only when the caller passes `regression_mode: full`. The hand-authored part holds broad invariants *not yet* captured per-task; retire a hand-authored flow only once a `custom-tests.yaml` entry covers that journey — don't duplicate a check that already runs as a typed verification.

## Rules

- Run tests after every significant change before closing the task.
- **Never re-run domain unit/lint suites** — those are `<PREFIX>-dev`'s Quality Checklist gates, already run before handoff. This skill's tiers are Smoke, Functional Feature, and Regression only; a full unit suite is not an acceptable "superset" substitute for the selected tier set — it re-proves what dev proved and overrides the caller's `regression_mode`.
- Never start automated actions against live targets without explicit user confirmation.
- Use representative placeholder inputs for smoke tests; live/real targets require explicit opt-in.
- In the `/code`/`/fix` pipeline this skill runs inside the `<PREFIX>-qa` subagent and **must not** ask the user interactively — resolve each verification deterministically; if a target cannot be resolved, report that verification as blocked rather than prompting. Interactive disambiguation is allowed only when this skill is invoked directly at top level (see `references/custom-tests.md`).

## Reference Sync

Verify before finishing any `<PREFIX>-test` invocation that touches API handlers or test infrastructure:
- [ ] `references/test-commands.md` Smoke / Regression / Functional Feature Subjects match current handlers, endpoints, and run scripts
- [ ] `references/custom-tests.yaml` verifications reflect current behavior; stale `type`/`paths` corrected
- [ ] Every verification executed this invocation has its `last:` block written (including `blocked` ones)
- [ ] `references/custom-tests.md` execution protocol matches the types in use
- [ ] `references/sync-checklist.md` trigger rules reflect current API surface and test tooling

## References
- `references/test-commands.md` — Smoke snippets, Regression suite, Functional Feature Subjects (data-store query helpers)
- `references/custom-tests.yaml` — per-task verifications captured by `/code` and `/fix`
- `references/custom-tests.md` — schema + runtime execution/inference protocol + prior-selection rule
- `references/sync-checklist.md` — when-to-update rules for the reference files
```

**Also create these reference files when installing `<PREFIX>-test`:**

`references/sync-checklist.md`:
```markdown
# Sync Checklist — <PREFIX>-test

## Update `references/test-commands.md` when:

- [ ] A handler, endpoint, or API route is added, removed, or renamed
- [ ] Request or response shape for any endpoint changes
- [ ] Auth pattern changes (session cookie format, JWT validation, API keys)
- [ ] Database schema, table/collection name, or query pattern changes
- [ ] A Smoke or Regression command no longer matches current handlers / run scripts
- [ ] Dev server port changes

## Update `references/custom-tests.yaml` when:

- [ ] A functional feature entry's `assert`, `type`, or `paths` no longer matches current behavior
- [ ] A captured verification is permanently obsolete (feature removed) — delete the entry
- [ ] A verification ran this invocation — write its `last:` outcome block
```

`references/test-commands.md`:
```markdown
# Test Commands — <PROJECT>

## Smoke

<!-- Always-run baseline. Curl templates / run commands for service & endpoint reachability + log check. Fill in per stack. -->

## Regression

<!-- Full broad suite, run only on regression_mode: full. Hand-authored; grows as broad invariants are added. -->

## Functional Feature Subjects

<!-- Data-store query snippets used to pick representative subjects when executing an `Integration` verification's query driver (or an E2E verification's confirmation query).
     Fill in the query pattern for this stack, e.g.:
     # resp = table.scan(Limit=50); items = resp.get("Items", [])
     # subjects = db.query(Model).filter(Model.status.in_([...])).limit(3).all()
-->
```

`references/custom-tests.yaml`:
```yaml
# Functional Feature Tests captured by /code and /fix.
# <PREFIX>-test resolves each entry's concrete target at runtime from
# type + task + project context (deploy-config.yaml, test-commands.md).
# Entries are atomic + named so a future optional `story` grouping can be added without reshaping them.
# Schema + execution protocol: references/custom-tests.md
tests: []
```

`references/custom-tests.md`:
~~~markdown
# Functional Feature Tests — schema + execution

Per-task verifications captured by `/code` and `/fix`, stored in `custom-tests.yaml`.
Each entry is one verification — a plain statement of what must be true; this skill resolves *how* to verify it at runtime.

## Schema (`custom-tests.yaml`)

```yaml
tests:
  - name: <short-kebab-slug>        # auto-generated at capture
    added: YYYY-MM-DD
    task: '<the /code or /fix invocation that captured this>'
    assert: '<one sentence: what must be true>'
    type: UX | Integration | E2E     # UX=frontend · Integration=backend (api/data) · E2E=full journey
    paths: ["<changed path/glob>"]   # from dev's `Files changed:` (minus .claude/**); drives prior-selection
    last:                            # written by this skill after every run it executes
      status: pass | fail | blocked  #   the outcome recorded in the Evidence trace
      commit: <sha7>                 #   HEAD at the moment it ran
      ts: YYYY-MM-DDTHH:MM:SSZ       #   UTC
```

`task` and `assert` are **single-quoted** (double any internal `'`): both routinely contain colons,
braces, or double-quotes — e.g. an assert quoting a JSON fragment like `{"key": "value"}` — which
break unquoted *and* double-quoted YAML. Single quotes survive all of those.

`type` and `paths` are the only persisted **selection** signals — both stable. The concrete target
(url / endpoint / query) is re-derived every run, never stored, so route changes can't go stale.

`last` is the persisted **outcome** signal, and it exists because without it a verification that
has been blocked for six consecutive runs is indistinguishable from one that has never run. It
records only the outcome, never the target. Absent on entries that have not run since the field
was introduced — treat a missing `last` as "never run", not as a pass.

## Execution (per verification, every run)

1. Read `type`, `assert`, `task`, `paths`.
2. Resolve the concrete target deterministically:
   - **UX / E2E** → the component's **first non-prod env url** from `<PREFIX>-deploy/references/deploy-config.yaml` (declaration order) — **never `envs.prod.url`**: QA runs before the prod deploy, so prod carries the old code. No non-prod env declared → report the verification **blocked** (`no non-prod env for <component> — add one with run: or deploy: to deploy-config.yaml`).
   - **Integration** → endpoint from `test-commands.md`, or subject query from `test-commands.md § Functional Feature Subjects` — whichever the assert names
3. Execute and check the predicate:

| type | how to run | pass criterion |
|---|---|---|
| UX | `agent-browser` to the resolved url; check the UI | predicate holds **and** a screenshot of the live UI was saved |
| Integration | curl/wget the resolved endpoint **or** run the data-store query — whichever the assert names | HTTP 2xx and body satisfies, or result row(s) satisfy, the verification |
| E2E | `agent-browser`: perform the UI action, then confirm the backend effect | UI predicate holds **and** a screenshot was saved **and** the backend effect is confirmed |

**Screenshot rule (UX and E2E):** every UX and E2E entry must take a screenshot of the actual UI at
the moment of verification — the screenshot is the evidence; DOM injection or console inspection is
not a substitute. After screenshots, run `open <paths>` via Bash so the user sees them immediately.

**Running-stack rule:** every verification runs against the actually-running deployed target
resolved above (the live url / endpoint / datastore). If that target is unreachable — typically the
serve-env isn't started — report the verification **blocked** (`target not running — start with
deploy-config \`envs.<env>.run\``). **Never** substitute an in-process test runner (FastAPI `TestClient`,
supertest, an imported app handler, etc.), and never count component/unit tests (Vitest, Jest, pytest)
as satisfying a typed verification: a source-level pass does not prove the running stack works,
and `<PREFIX>-test`'s job is to test the running stack, not dead code. Blocked is an honest result; a
faked green is not.

**Freshness rule:** before counting any evidence, confirm the target runs the code under test — a
serve-env started before the latest commits, or a cloud env deployed earlier, is running **stale**
code and its 200s prove nothing about this change. Check process start time vs the latest commit, a
build/version marker, or ask the top level to restart the serve-env. Evidence from a stale target is
reported as `stale target — non-evidence`, never as a pass.

**Evidence trace:** record one compact line per verification: the exact command or browser action →
the observed result (HTTP status + relevant body fragment, or the screenshot path — a few lines max)
→ `pass | fail | blocked`. These lines flow into the qa handoff `Evidence:` field verbatim — they
are what the user reads instead of re-testing, so concrete observations, not claims.

**Record the outcome:** after running a verification, write its `last:` block (`status`, `commit`
= `git rev-parse --short HEAD`, `ts` = UTC now) back to its `custom-tests.yaml` entry. Write it for
every verification this run executed, including `blocked` ones — a blocked run is the outcome that
most needs a history. Commit the file with `test: record verification outcomes`.

## Prior-selection

Resolve the prior set with the delivery graph:

```bash
python3 .claude/graph/graph.py covers <changed paths…>
```

It returns the verification names whose stored `paths:` intersect the changed paths — the same rule
stated below, evaluated against the index instead of by reading the whole file. **Fall back** to the
manual rule if the script is missing or exits non-zero.

The rule it implements: include a prior verification when its stored `paths:` set intersects the
changed-paths list passed by the caller. This task's own verifications always run.

## Interactive fallback — top-level only

When invoked **directly** at top level (a manual test run, not via `<PREFIX>-qa`), this skill may
`AskUserQuestion` once for a genuinely ambiguous piece, use the answer, and continue — **do not**
write the answer back to the yaml (re-infer next run). In the `/code`/`/fix` pipeline this skill
runs inside the `<PREFIX>-qa` subagent and must never ask: resolve deterministically, or report the
verification as blocked in the handoff.
~~~

---

## § tosk-skill/SKILL.md

```markdown
---
name: <PREFIX>-skill
description: Use when work touches directories no existing skill owns, when a concern falls outside any loaded skill's scope, or when a loaded skill lacks domain knowledge for current work
---

# <PREFIX>-skill

Meta-skill for the <PROJECT> skill system. Uses `skill-creator` for all authoring.

## Skill Inventory

Current skill inventory: `references/skill-manifest.md`

## Global Invariants

These rules apply to **every project (`<PREFIX>-*`) skill**. Third-party skills (e.g. `agent-browser`, `sdk-development`) are not project-managed and are excluded. <PREFIX>-skill is the single source of truth.

1. **governed-paths.conf is the single source of truth for path ownership.** When directories are added or moved, update `<CONFIG_DIR>/hooks/governed-paths.conf` — both `skill-guard.sh` and `path-coverage-check.sh` source it automatically. Never edit path patterns in those scripts directly.
2. **Reference files must stay current.** When a domain fact changes (schema, API contract, pattern), update the corresponding reference file before finishing.
3. **No orphaned paths.** Every project directory must be covered by a pattern in `<CONFIG_DIR>/hooks/governed-paths.conf`, owned by exactly one skill.
4. **skill-manifest.md must stay current.** Whenever a skill is added, removed, or renamed, or a reference file is added or removed, update `<PREFIX>-skill/references/skill-manifest.md` before finishing.
5. **References ↔ Reference Sync parity.** `## Reference Sync` must enumerate every file in `## References` — one checklist item per file, no omissions, no extras. When a reference file is added or removed, update both sections in the same edit. **Exception:** static-content skills (`<PREFIX>-debug`, `<PREFIX>-review`) ship references that the project does not author and omit `## Reference Sync` entirely — agents skip them in the Reference Sync step. The exemption is decided by content ownership, not skill name: if such a skill carries a **project-authored** reference (values that drift with the project), it keeps a `## Reference Sync` scoped to exactly those project-authored files — template-shipped references stay out of the checklist.
6. **Reference files must be named for their content domain, not generically.** Use: `api-schema.md`, `design-tokens.md`, `deploy-config.md`, `aws-resources.md`. Avoid: `resources.md`, `notes.md`, `misc.md`, `reference.md`.

## When This Fires

**Path gaps:**
- Code is added in a directory not covered by `governed-paths.conf`
- An existing skill's path ownership needs to grow to cover adjacent directories

**Concern gaps:**
- Work introduces a recurring concern — maintenance, auditing, health checks, dependency management — that no existing skill explicitly handles
- A new technology or process is introduced that requires ongoing expertise not covered by any existing skill's stated domain
- <PREFIX>-dev flags that the work falls outside all loaded skills' scope

**New dependency gate:**
- dependency-guard blocks `pnpm add` / `pip install` commands — assess whether new packages need reference files

**Skill evolution gaps:**
- A loaded skill owns the path but its domain knowledge doesn't cover the current work
- A technology or service within a skill's domain has changed significantly
- A recurring concern within a skill's domain is not yet documented

## Decision: Expand, Evolve, or Create

**Expand** when a new directory is closely related to an existing skill's domain:
- New `src/hooks/` → expand frontend skill
- New `infra/scripts/` → expand deploy skill

**Evolve** when a loaded skill owns the path but lacks domain knowledge:
- New technology within the skill's existing domain → new reference file or inline section (see Evolve path step 1 for criteria)
- Significant change to a covered pattern → update the relevant section or reference

**Create** when it's a genuinely new domain with its own expertise:
- `src/telemetry/` → new observability skill
- `src/jobs/` → new workers skill

## Process

### Skill evolution gap (Evolve path)

1. **Identify the missing knowledge** — name the technology, pattern, or concern.
   Create a **new reference file** when the technology has its own package, its own API surface (components, hooks, config objects), and would need to be found by filename in future tasks. Examples: Framer Motion → `animation-patterns.md`, Recharts → `chart-patterns.md`. Add an **inline section** when it's a utility, plugin, or config option within a framework already covered by a reference file. Examples: Astro plugin → existing `astro-patterns.md`, Tailwind preset → existing `shadcn-conventions.md`.
2. **Confirm with user** — present the proposed addition before authoring
3. **Author with skill-creator** — write new content following existing skill structure
4. **Update SKILL.md** — add References pointer if new reference file was created; add item to Reference Sync checklist
5. **Update skill-manifest.md** — if a new reference file was added

### Path gap or concern gap (Expand or Create path)

1. **Identify the gap** — name the concern or domain; describe the recurring work pattern
2. **Confirm with user** — present proposed skill name + one-line purpose; do not proceed without approval
3. **Author with `skill-creator`** — frontmatter (name, description), `## When to Use`, `## Domain Knowledge`, `## Reference Sync`
4. **Create or expand** — write/update SKILL.md under `<CONFIG_DIR>/skills/<skill-name>/`
5. **Register in the workflow:**
   - `governed-paths.conf` — add path pattern + skill name; both hooks pick it up automatically
   - `<CONFIG_DIR>/skills/<PREFIX>-skill/references/skill-manifest.md` — always
   - `<PREFIX>-dev.md` — only if invoked during implementation
   - `<PREFIX>-qa.md` — only if invoked during review or testing
   - `<PREFIX>-pm.md` — only if invoked during delivery logging or docs
   - `.claude/commands/` — if skill introduces a new workflow step users invoke directly

## Reference File Lifecycle

Structural changes to reference files (rename, retire, split, add) must be done atomically — all in one edit session. <PREFIX>-skill owns these operations.

**Add:** create file → add to `## References` → add item to `## Reference Sync` → add to `skill-manifest.md`

**Rename:** rename file → update description in `## References` → update item text in `## Reference Sync` → update `skill-manifest.md` → delete old file

**Retire:** delete file → remove from `## References` → remove from `## Reference Sync` → update `skill-manifest.md`

**Split:** create new files → update `## References` (remove old, add new) → update `## Reference Sync` (remove old item, add new items) → update `skill-manifest.md` → delete old file

## Ownership Rules

- Every directory under the project must be owned by exactly one skill (tracked in `governed-paths.conf`, not in individual skill files)
- Config files are owned by the skill whose domain they configure
- `<CONFIG_DIR>/skills/` is owned by this skill (<PREFIX>-skill)
- File-level overrides: a single file within a directory may be claimed by a different skill than the directory owner; note the override in the project file and cross-reference both skills

## Reference Sync

Verify before finishing any <PREFIX>-skill invocation:
- [ ] `references/skill-manifest.md` reflects current `<PREFIX>-*` skill inventory (correct skill names, reference file list, no stale entries) — third-party skills are excluded
- [ ] `governed-paths.conf` patterns match current skill ownership
- [ ] Each `<PREFIX>-*` skill in `skill-manifest.md` has `## References` and `## Reference Sync` in 1:1 parity (same files, no extras, no omissions) — except static-content skills (`<PREFIX>-debug`, `<PREFIX>-review`) which legitimately omit `## Reference Sync`, or scope it to their project-authored references only (see Global Invariant 5)
```

---

## § tosk-docs/SKILL.md

```markdown
---
name: <PREFIX>-docs
description: Keep README.md and docs/workflow.md in sync with <PROJECT> code. Trigger after any change to the API, architecture, data model, or delivery workflow.
---

# <PREFIX>-docs

Owns documentation correctness for `<PROJECT>`. After any significant change, run this skill to verify docs reflect reality.

## File Roles

**`README.md`** — source of truth for setup, usage, commands, and configuration variables.
Structured, concise, and actionable. A developer cloning the repo should be able to run the project using only this file.
Do not put architecture or design decisions here.

**`docs/workflow.md`** — source of truth for the delivery workflow, agent pipeline, and skill system.
Must contain: pipeline diagram, skills table, skill anatomy overview, delivery log format.
Do not put setup commands or config values here.

## When to Update

- `README.md`: when env vars, install steps, or run commands change
- `docs/workflow.md`: when agent pipeline, skills, or hook infrastructure changes
- Both: when the architecture changes significantly

## References
- `references/sync-checklist.md` — when-to-update rules for README.md and docs/workflow.md

## Reference Sync
Verify before finishing any `<PREFIX>-docs` invocation:
- [ ] README.md is structured, concise, and actionable — no architecture content
- [ ] docs/workflow.md is structured, concise, and readable — no setup commands
- [ ] All env vars in README match `.env.example` exactly (if applicable)
- [ ] `references/sync-checklist.md` trigger rules reflect current docs and workflow structure
```

**Also create this reference file when installing `<PREFIX>-docs`:**

`references/sync-checklist.md`:
```markdown
# Sync Checklist — <PREFIX>-docs

## Update `README.md` when:

- [ ] Install command or runtime version changes
- [ ] Dev server command or port changes
- [ ] Environment variable added, removed, or renamed
- [ ] Build or deploy steps change
- [ ] Auth setup steps change

## Update `docs/workflow.md` when:

- [ ] Agent pipeline changes (new agent added, sequence changes)
- [ ] Skill added, removed, or renamed
- [ ] Path→skill table in project file changes
- [ ] Skill gap types or resolution process changes
- [ ] Delivery log format changes
```

---

## § tosk-graph/SKILL.md

**`graph.py` is not inlined here.** Copy `shared/graph.py` from the dev-workflow plugin to
`.claude/graph/graph.py` **verbatim** — it takes no `<PREFIX>` substitution (skill dirs are
glob-discovered), so it stays byte-identical across every project and can be diffed on upgrade.

```markdown
---
name: <PREFIX>-graph
description: Delivery graph for <PROJECT> — the queryable index of what shipped, what covers which paths, what is deployed where, and what is still deferred. Use when a question spans more than one delivery ("what verifies this file", "what has been delivered here", "which deferrals are still open", "which roadmap items relate to these paths"), when the index looks stale or wrong, or when changing anything under `.claude/graph/`.
---

# <PREFIX>-graph

Owns the delivery graph: a typed, provenanced edge index projected from the project's own records.

**The index is derived and disposable.** git, `docs/project-log.md`, `docs/roadmap.md`,
`custom-tests.yaml`, `deploy-config.yaml` and `governed-paths.conf` stay the source of truth;
`graph.py build` discards `edges.jsonl` and reprojects from them. Never hand-edit `edges.jsonl`,
and never record a fact only in the graph — write it to its owning artifact and reproject.

**Every caller falls back.** If `graph.py` is missing, python3 is unavailable, or the command
exits non-zero, the caller uses its pre-graph behaviour. The graph is an accelerator, never a gate.

## Owned Paths
- `.claude/graph/` — `graph.py` and the schema reference (`edges.jsonl` itself is EXEMPT: machine-generated)

## Commands

```
python3 .claude/graph/graph.py build                      reproject the index (<1s)
python3 .claude/graph/graph.py covers <path>...           verifications whose paths intersect these
python3 .claude/graph/graph.py blast <path>...            owners · verifications+status · deliveries · deferrals
python3 .claude/graph/graph.py history <path>             what shipped, was verified, or was reverted here
python3 .claude/graph/graph.py roadmap-open [--for <path>...]   open items; path-affine ones marked ~match
python3 .claude/graph/graph.py open-deferrals [<path>...] deferred and never since passed
```

Add `--json` to any query for machine-readable output. Queries rebuild automatically when the
index is missing or behind `HEAD`, so `build` is only needed after a manual artifact edit.

## Read Map

```
SITUATION?
│
├─ Need an answer from the graph        → run the query above; no reading required
├─ Adding/changing an edge or query     → references/graph-schema.md
├─ A query returns something surprising → references/graph-schema.md § Provenance, then the cited artifact
└─ Index looks stale or corrupt         → `graph.py build`; it is always safe to reproject
```

## References
- `references/graph-schema.md` — node ids, the 12 edge types, which artifact each is projected from, and the provenance contract

## Reference Sync
Verify before finishing any `<PREFIX>-graph` invocation:
- [ ] `references/graph-schema.md` lists every edge type `graph.py` emits, with its source artifact and field
- [ ] Any new query is documented in `## Commands` here and in the schema reference
- [ ] `graph.py` still matches the plugin's `shared/graph.py` (no local drift — fix the plugin instead)
```

**Also create this reference file when installing `<PREFIX>-graph`:**

`references/graph-schema.md`:
~~~markdown
# Delivery graph — schema

One JSON object per line in `.claude/graph/edges.jsonl`. Line 1 is `_meta`
(`version`, `head`, `built`, `edges`); every other line is one edge.

```json
{"e":"COVERS","from":"verif:login-redirects-home","to":"path:app/auth/login.tsx",
 "src":"custom-tests.yaml#login-redirects-home.paths"}
```

## Provenance contract

**Every edge carries a non-empty `src`** naming the artifact and field it was projected from.
An answer cites an edge; the edge cites the file. Nothing is asserted that cannot be traced back
to a record a human can open. An edge without `src` is a bug in the projector.

## Node ids — `<type>:<natural-key>`

| Node | Id | Key from |
|---|---|---|
| Task | `task:<slug>` | delivery-log entry title |
| RoadmapItem | `road:<id>` | roadmap `**Id:**` (falls back to the title slug when absent) |
| Commit | `commit:<sha7>` | git |
| Path | `path:<repo-relative>` | git / `paths:` / `PATH_MAP` pattern |
| Skill | `skill:<PREFIX>-<name>` | `governed-paths.conf` |
| Verification | `verif:<name>` | `custom-tests.yaml` `name` |
| Component | `comp:<name>` | `deploy-config.yaml` |
| Env | `env:<comp>/<env>` | `deploy-config.yaml` |
| Decision | `dec:<sha7>/<gate>` | delivery-log `**Decisions:**` |

Ids are exact natural keys that already exist, so there is **no entity-resolution step** and no
model call anywhere in the projector — projection is pure parsing.

## Edges

| Edge | From → To | Props | Projected from |
|---|---|---|---|
| `LANDED_AS` | task → commit | — | log entry hash (several when an entry names several) |
| `TOUCHES` | commit → path | — | one `git log --name-only` pass, filtered to delivery commits |
| `USED` | commit → skill | — | log `**Skills:**` |
| `DEPLOYED_TO` | commit → env | `url` | log `**Deployed:**` |
| `DEFERRED` | commit → verif | `accepted_by` | log `**UAT-deferred:**` |
| `DECIDED` | commit → decision | `value`, `by` | log `**Decisions:**` |
| `ADDRESSES` | task → road | — | log `**Addresses:**` |
| `SUPERSEDES` | commit → commit | — | `git log --grep=^Revert` |
| `COVERS` | verif → path | — | `custom-tests.yaml` `paths:` |
| `VERIFIED` | commit → verif | `status`, `ts` | `custom-tests.yaml` `last:` |
| `OWNED_BY` | path-pattern → skill | — | `governed-paths.conf` `PATH_MAP` |
| `HAS_ENV` | comp → env | `url`, `kind` | `deploy-config.yaml` |

`OWNED_BY` stores the **PATH_MAP pattern, not resolved files** — ownership is evaluated
first-match at query time, the same rule the hooks apply, so new files are covered without a rebuild.

## Field precedence

Two fields can describe how a deferral was accepted: `**Decisions:** defer=accept (<how>)` and the
prose in `**UAT-deferred:**`. **`Decisions:` wins** — it is the structured record. The prose scan is
a fallback for entries written before that field existed. Where any two records disagree, the
structured one is authoritative and the other is treated as commentary.

A verification is an **open deferral** when it has a `DEFERRED` edge and no `VERIFIED` edge with
`status: pass`. A missing `last:` block means "never run" — never a pass.

## Rebuild semantics

`build` always reprojects in full. There is deliberately no incremental mode: a full build is
under a second on a 200-entry log, and an append path would leave deleted verifications and
retired path patterns lingering in the index.

## Tolerated input variation

The log parser accepts entry headings that predate the current format — missing `HH:MM`, several
hashes joined by `+` or `,`, and non-commit placeholders such as `uncommit`. An entry with no
usable sha still contributes its `ADDRESSES` edge; commit-keyed edges need a commit.
`custom-tests.yaml` `paths:` is read in both the block-list and inline-flow-list forms.
~~~
