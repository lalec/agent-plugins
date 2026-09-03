# edr

Endpoint Detection & Response for macOS, packaged as a Claude Code plugin. Detection collectors gather raw evidence; the analyst (Claude in `SKILL.md`) performs NIST SP 800-61 Identification — categorize, scope, impact, confidence, evidence, narrate.

## Install

```
/plugin marketplace add lalec/agent-plugins
/plugin install edr@agent-plugins
/reload-plugins
```

## Use

| Command | What it does |
|---|---|
| `/edr:macos` | One-shot scan: run collectors, diff vs baseline, narrate findings |
| `/edr:macos headless` | Same scan under the unattended contract — the nightly job runs this |
| `/edr:macos poll` | Run approved actions (root ones raise the admin dialog), list unreviewed batches from unattended runs |
| `/edr:macos schedule` | Nightly launchd job: `edr schedule install \| uninstall \| status` |
| `/edr:macos test fake_launchagent` | Plant a benign LaunchAgent, verify the launchd collector flags it critical, clean up |
| `/edr:macos test fake_privileged_docker` | Run a `--privileged` container, verify docker collector flags it critical, clean up |
| `/loop 4h /edr:macos` | Attended-session loop, every 4 h |

## Code vs host-local data

- **Plugin install dir** (this repo, copied to `~/.claude/plugins/cache/...` on install): Python runtime, default triage rules, MITRE intel feed, simulator scenarios. Read-only after install.
- **Host data dir** (`~/.claude/edr/`, override with `$EDR_HOME`): per-host baseline, snapshots, secrets, lessons, changelog, `pending_changes/`, `intel/db.sqlite`, telemetry, host-specific `config.yaml`. Created on first run.

User overrides for shipped defaults:
- `${EDR_HOME}/triage_rules.user.yaml` — additional / overriding triage rules
- `${EDR_HOME}/manifest.user.yaml` — per-host collector maturity overrides

## Architecture

```
collectors (Python, fast, deterministic)
   ↓ raw evidence
diff vs baseline → triage fast-path (FP suppress + auto-promote)
   ↓ anomalies
analyst (Claude in SKILL.md) — pivots, enriches ad-hoc, classifies per NIST §3.2.4
   ↓
alert batch state/alerts/<ts>.json — one pre-declared action per finding
   ↓
narrate to chat | nightly: post to Discord, read replies → edr poll runs approved actions
```

## Unattended nightly scan

`edr schedule install` writes a launchd calendar job (default 22:00, fires on wake if missed, runs under `caffeinate`). With `notify.channel: discord` in `config.yaml` the job posts findings to one guild text channel as a numbered list; reply `1`, `1 2`, `ok 2` (accept as benign), `why 1` or `skip`. User-scope actions run the same night; anything needing root queues until the next `/edr:macos` at the Mac, where it raises the admin dialog. With `notify.channel: none` nothing is posted and the batch opens the next interactive run. `edr accept <sig>` / `--all` folds confirmed-benign anomalies into the baseline.

Collectors are pluggable. Drop a `runtime/collectors/foo.py` implementing the `Collector` ABC; it's auto-discovered next tick. Maturity tiers (`experimental → beta → stable`) gate auto-promote behavior. New self-authored proposals land in `${EDR_HOME}/pending_changes/` for user review.

The plugin's `bin/edr` is auto-added to `$PATH` in plugin sessions — `edr`, `edr accept`, `edr poll`, `edr notify`, `edr schedule`, `edr test all`, `edr bootstrap`, `edr intel-sync` work directly.

See [SKILL.md](skills/macos/SKILL.md) for the full analyst playbook.

## Status

Phase A (foundation): 6 stable collectors — processes, launchd, network, sensitive_paths, docker, claude_code_config. Local-only, plus the unattended nightly loop over Discord (no cloud). Phase B (Firebase backend + email alerts), Phase C (interactive IR runner), Phase D (coverage rollout), Phase E (self-evolution) are upcoming.
