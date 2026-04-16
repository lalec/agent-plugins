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

1. Run `git log --oneline -1` to get the short hash and commit message
2. Run `git log -1 --format="%ai"` to get the commit timestamp — extract the `HH:MM` in local time for the date field
3. Identify which skills were actually invoked this session by scanning the most recent session transcript:
   ```bash
   PROJECT_ENCODED=$(echo "$PWD" | sed 's|/|-|g')
   grep -o '"skill":"[^"]*"' "$(ls -t ~/.claude/projects/${PROJECT_ENCODED}/*.jsonl 2>/dev/null | head -1)" | sort -u
   ```
   Use only skills that appear in this output for the **Skills** field. If none appear, use `—`.
4. Write the new entry at the **top** of `docs/project-log.md`, immediately below the header block, before the previous `---` separator

## Entry Format

~~~
---
### YYYY-MM-DD HH:MM · `<7-char hash>` — <short title (not the commit message verbatim)>

<1–3 sentences. What shipped and why it matters. No label — this is the body.>

**Tests:** <what was actually verified>
**Skills:** <tosk-x> · <tosk-y>
**Checklist:** <skill> — <what changed> (omit line entirely if nothing to note)
~~~

**Field guidance:**

- **Title** — short, plain English. Not the raw commit message — rephrase for a human skimming the log.
- **Body** — 1–3 sentences. Add context beyond the title: *why* it was needed, *what problem* it solves, any non-obvious decisions.
- **Tests** — be honest. "manual smoke" is a real test. Common values: `lint + type check (clean)`, `manual smoke in browser`, `E2E: <scenario>`, `none`
- **Skills** — only skills confirmed present in the transcript grep output, separated by ` · `. Use `—` if none found.
- **Checklist** — one `skill — note` per skill whose reference files were updated. Omit the line entirely if nothing was updated.

## Quality Checklist
Required steps before writing the log entry:
1. [ ] Entry is at the top of docs/project-log.md (below the `# Project Log` header)
2. [ ] HH:MM is included in the date (from `git log -1 --format="%ai"`)
3. [ ] Skills field is derived from transcript grep, not from memory
4. [ ] Body is 1–3 sentences, no `What:` label
5. [ ] `Checklist:` line omitted when nothing was updated
```

---

## § tosk-review/SKILL.md

```markdown
---
name: <PREFIX>-review
description: Code review practices with technical rigor and verification gates. Use for receiving feedback, requesting code-reviewer subagent reviews, or preventing false completion claims in pull requests.
license: MIT
---

# Code Review

Guide proper code review practices emphasizing technical rigor, evidence-based claims, and verification over performative responses.

## Overview

Code review requires three distinct practices:

1. **Receiving feedback** - Technical evaluation over performative agreement
2. **Requesting reviews** - Systematic review via code-reviewer subagent
3. **Verification gates** - Evidence before any completion claims

## Core Principle

**Technical correctness over social comfort.** Verify before implementing. Ask before assuming. Evidence before claims.

## When to Use This Skill

### Receiving Feedback
Trigger when:
- Receiving code review comments from any source
- Feedback seems unclear or technically questionable
- Multiple review items need prioritization

### Requesting Review
Trigger when:
- Completing tasks in subagent-driven development (after EACH task)
- Finishing major features or refactors
- Before merging to main branch

### Verification Gates
Trigger when:
- About to claim tests pass, build succeeds, or work is complete
- Before committing, pushing, or creating PRs

## Quick Decision Tree

```
SITUATION?
│
├─ Received feedback
│  ├─ Unclear items? → STOP, ask for clarification first
│  ├─ From human partner? → Understand, then implement
│  └─ From external reviewer? → Verify technically before implementing
│
├─ Completed work
│  └─ Major feature/task? → Request code-reviewer subagent review
│
└─ About to claim status
   ├─ Have fresh verification? → State claim WITH evidence
   └─ No fresh verification? → RUN verification command first
```

## Receiving Feedback Protocol

READ → UNDERSTAND → VERIFY → EVALUATE → RESPOND → IMPLEMENT

- No performative agreement ("You're absolutely right!", "Great point!")
- No implementation before verification
- If unclear: STOP and ask for clarification first
- YAGNI check: grep for usage before implementing suggested features

## Requesting Review Protocol

1. Get git SHAs: `BASE_SHA=$(git rev-parse HEAD~1)` and `HEAD_SHA=$(git rev-parse HEAD)`
2. Dispatch code-reviewer subagent via Task tool with: WHAT_WAS_IMPLEMENTED, PLAN_OR_REQUIREMENTS, BASE_SHA, HEAD_SHA, DESCRIPTION
3. Act on feedback: Fix Critical immediately, Important before proceeding, note Minor for later

## Verification Gates

**NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE**

Run the command. Read the output. Then claim the result.

Red flags — stop if thinking:
- "Should work now" / "Seems fixed"
- "Tests pass, we're done" (without having just run them)
- Using "should"/"probably"/"seems to" when describing correctness

## References
- `references/code-review-reception.md` — detailed feedback reception protocol
- `references/requesting-code-review.md` — code-reviewer subagent dispatch protocol
- `references/verification-before-completion.md` — iron law evidence requirements

## Reference Sync
Verify before finishing any `<PREFIX>-review` invocation:
- [ ] `references/code-review-reception.md` reflects current feedback reception protocol
- [ ] `references/requesting-code-review.md` reflects current review dispatch workflow
- [ ] `references/verification-before-completion.md` iron law is current
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

`references/verification-before-completion.md`:

````markdown
# Verification Before Completion

## Overview

Claiming work is complete without verification is dishonesty, not efficiency.

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

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
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)
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

Run the command. Read the output. THEN claim the result.

This is non-negotiable.
````

---

## § tosk-debug/SKILL.md

```markdown
---
name: <PREFIX>-debug
description: Systematic debugging framework ensuring root cause investigation before fixes. Includes four-phase debugging process, backward call stack tracing, multi-layer validation, and verification protocols. Use when encountering bugs, test failures, unexpected behavior, performance issues, or before claiming work complete. Prevents random fixes, masks over symptoms, and false completion claims.
---

# Debugging

Comprehensive debugging framework combining systematic investigation, root cause tracing, defense-in-depth validation, and verification protocols.

## Core Principle

**NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST**

Random fixes waste time and create new bugs. Find the root cause, fix at source, validate at every layer, verify before claiming success.

## When to Use

**Always use for:** Test failures, bugs, unexpected behavior, performance issues, build failures, integration problems, before claiming work complete

**Especially when:** Under time pressure, "quick fix" seems obvious, tried multiple fixes, don't fully understand issue, about to claim success

## The Four Techniques

### 1. Systematic Debugging (`references/systematic-debugging.md`)

Four-phase framework ensuring proper investigation:
- Phase 1: Root Cause Investigation (read errors, reproduce, check changes, gather evidence)
- Phase 2: Pattern Analysis (find working examples, compare, identify differences)
- Phase 3: Hypothesis and Testing (form theory, test minimally, verify)
- Phase 4: Hand off to the owning domain skill when the fix is identified.

**Key rule:** Complete each phase before proceeding. No fixes without Phase 1.

**Load when:** Any bug/issue requiring investigation and fix

### 2. Root Cause Tracing (`references/root-cause-tracing.md`)

Trace bugs backward through call stack to find original trigger.

**Technique:** When error appears deep in execution, trace backward level-by-level until finding source where invalid data originated. Fix at source, not at symptom.

**Includes:** `scripts/find-polluter.sh` for bisecting test pollution

**Load when:** Error deep in call stack, unclear where invalid data originated

### 3. Defense-in-Depth (`references/defense-in-depth.md`)

Validate at every layer data passes through. Make bugs impossible.

**Four layers:** Entry validation → Business logic → Environment guards → Debug instrumentation

**Load when:** After finding root cause, need to add comprehensive validation

### 4. Verification (`references/verification.md`)

Run verification commands and confirm output before claiming success.

**Iron law:** NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE

Run the command. Read the output. Then claim the result.

**Load when:** About to claim work complete, fixed, or passing

## Quick Reference

```
Bug → systematic-debugging.md (Phase 1-4)
  Error deep in stack? → root-cause-tracing.md (trace backward)
  Found root cause? → defense-in-depth.md (add layers)
  About to claim success? → verification.md (verify first)
```

## Red Flags

Stop and follow process if thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "It's probably X, let me fix that"
- "Should work now" / "Seems fixed"
- "Tests pass, we're done"

**All mean:** Return to systematic process.
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
description: Use when making any visual decision — color, spacing, gradient, component appearance. Owns the <PROJECT> design system: color palette, CSS tokens, typography, and surface system.
---

# <PREFIX>-design

Visual authority for all <PROJECT> UI decisions. Use `frontend-design` when executing design work.

> **Design skill:** This skill delegates execution to `frontend-design` by default. If you prefer a different design skill, replace `frontend-design` with your chosen skill name in the two lines above and below this note.

When the user asks to explore design alternatives for a specific component, use `frontend-design` to generate variants — but constrain it to the <PROJECT> design system (palette, fonts, surface). Do not propose styles or palettes outside the existing system.

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
- [ ] No removed tokens or renamed classes still referenced
```

**Also create this reference file when installing `<PREFIX>-design`:**

`references/design-tokens.md`:
```markdown
# Design Tokens

<!-- Fill in: color palette (hex values), CSS custom properties, typography (font families, weights), spacing scale, surface colors, glow/shadow values -->
```

---

## § tosk-test/SKILL.md

```markdown
---
name: <PREFIX>-test
description: Use when writing or performing tests for <PROJECT>. Trigger any time the user wants to verify the app works, run tests against the deployed stack, test a new feature, or perform end-to-end UI testing.
---

# <PREFIX>-test

Testing authority for <PROJECT>. Covers unit/integration tests, API smoke tests, and E2E browser tests.

## Test Commands

Fill in project-specific test commands: `references/test-commands.md`

## Unit / Integration Tests

Run with: `<fill in unit test command>`

See `references/test-commands.md` for full details.

## Functional Feature Tests

When a change touches a core handler, route, or service, run max 3 different scenario tests — one per distinct code path the feature or fix introduces. Always use subject IDs provided in the prompt if given; otherwise select them dynamically from the data store.

**How to pick subjects if none are provided:**

Query the data store for representative items that cover each distinct scenario (e.g. different statuses, types, or states). Fill this in during project setup — the query pattern depends on the stack:

```
# Example: DynamoDB (Python)
# resp = table.scan(Limit=50); items = resp.get("Items", [])
# active   = next((i for i in items if i.get("status") == "active"), None)
# done     = next((i for i in items if i.get("status") == "done"), None)
# failed   = next((i for i in items if i.get("status") == "failed"), None)

# Example: SQL / ORM
# subjects = db.query(Model).filter(Model.status.in_(["active","done","failed"])).limit(3).all()
```

Run the relevant operation against each selected subject and confirm each takes the expected code path (check logs or test output). Three scenarios is the ceiling — stop there unless a fourth genuinely distinct path exists.

See `references/test-commands.md` for project-specific query snippets and data store access setup.

## API Smoke Tests

Curl templates for endpoints: `references/test-commands.md`

## E2E Browser Tests

Use the `agent-browser` skill for browser automation against `<APP_URL>`.

**Screenshot rule:** Every E2E test that verifies a visual or real-time state must take a screenshot of the actual UI at the moment of verification. The screenshot is the evidence — without it, the test did not happen. Never substitute DOM injection, console evaluation, or code inspection for a real screenshot of the live UI.

**Open rule:** After taking screenshots, always run `open <paths>` via Bash so the user can view them immediately.

## Rules

- Run tests after every significant change before closing the task.
- Never start automated actions against live targets without explicit user confirmation.
- Use representative placeholder inputs for smoke tests; live/real targets require explicit opt-in.

## Reference Sync

Verify before finishing any `<PREFIX>-test` invocation that touches API handlers or test infrastructure:
- [ ] `references/test-commands.md` commands match current handlers, endpoints, and run scripts
- [ ] `references/sync-checklist.md` trigger rules reflect current API surface and test tooling

## References
- `references/test-commands.md` — test commands, curl templates, environment setup
- `references/sync-checklist.md` — when-to-update rules for test-commands.md
```

**Also create this reference file when installing `<PREFIX>-test`:**

`references/sync-checklist.md`:
```markdown
# Sync Checklist — <PREFIX>-test

## Update `references/test-commands.md` when:

- [ ] A handler, endpoint, or API route is added, removed, or renamed
- [ ] Request or response shape for any endpoint changes
- [ ] Auth pattern changes (session cookie format, JWT validation, API keys)
- [ ] Database schema, table/collection name, or query pattern changes
- [ ] A new E2E browser target URL or environment is added
- [ ] Dev server port changes
- [ ] Test structure changes (new test directory, new fixture pattern, new test runner config)
```

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
5. **References ↔ Reference Sync parity.** `## Reference Sync` must enumerate every file in `## References` — one checklist item per file, no omissions, no extras. When a reference file is added or removed, update both sections in the same edit.
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
- [ ] Each `<PREFIX>-*` skill in `skill-manifest.md` has `## References` and `## Reference Sync` in 1:1 parity (same files, no extras, no omissions)
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
