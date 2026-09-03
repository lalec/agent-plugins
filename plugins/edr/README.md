# edr

Endpoint Detection & Response for macOS, packaged as a Claude Code plugin. Detection collectors gather raw evidence; the analyst (Claude in `SKILL.md`) performs NIST SP 800-61 Identification — categorize, scope, impact, confidence, evidence — and declares one action per finding. You approve with a one-character reply; approved actions run through `edr poll`.

## Requirements and prerequisites

| | Requirement | Notes |
|---|---|---|
| OS | macOS **12 or newer** | Tested on 13. Sources that only exist on some versions are gated per host; `edr doctor` lists them. |
| Python | `python3` 3.10+ with **PyYAML** | Ships with Xcode Command Line Tools or Homebrew. `pip3 install pyyaml` if `edr doctor` reports it missing. |
| Claude Code | current CLI, plugin installed from the `lalec/agent-plugins` marketplace | `bin/edr` is on `$PATH` inside plugin sessions. |
| Permissions | **none** beyond your user | No root, no Full Disk Access. Root-only sources (`eslogger`, `sfltool`) and FDA-only sources (`TCC.db`, Safari history) are not read; `edr doctor` shows them as unavailable. Approved root *actions* raise the native macOS admin dialog. |
| Browsers | any of Chrome, Chromium, Brave, Edge, Arc, Vivaldi, Opera, Firefox, Safari | Discovered at run time; nothing is assumed installed. |
| Discord (optional) | a bot token, a private server, one text channel | Only for the unattended nightly loop. Without it, findings wait for your next `/edr:macos`. |
| Network (optional) | outbound HTTPS to abuse.ch | Intel feeds. Offline runs still work; the IOC database is simply stale. |

Check a host before the first scan:

```
edr doctor
```

## Install

```
/plugin marketplace add lalec/agent-plugins
/plugin install edr@agent-plugins
/reload-plugins
```

## Use

| Command | What it does |
|---|---|
| `/edr:macos` | One-shot scan: collectors → diff vs baseline → triage → analyst → alert batch, narrated in chat |
| `/edr:macos headless` | Same scan under the unattended contract — the nightly job runs this |
| `/edr:macos poll` | Run approved actions (root ones raise the admin dialog), list unreviewed batches from unattended runs |
| `/edr:macos schedule` | Nightly launchd job: `edr schedule install \| uninstall \| status` |
| `/edr:macos test {scenario\|all}` | Red-team simulators (see Testing) |
| `edr accept <sig>… \| --all [--collector X]` | Fold confirmed-benign anomalies into the baseline. The only way the baseline grows after bootstrap. |
| `edr intel-sync` / `edr intel-lookup <type> <value>` | Refresh the IOC database (abuse.ch URLhaus, ThreatFox, Feodo + MITRE) / look one value up |
| `edr doctor` | macOS version, Python, PyYAML, and per-source availability on this host |

## What it detects

| Collector | Shape | Signals |
|---|---|---|
| `processes` | state | Executable inventory with codesign verdict and sha256 for unsigned binaries; parent → child lineage for shells, interpreters and transfer tools; command-line patterns (`curl \| sh`, base64 decode, quarantine strip, Gatekeeper off, AppleScript password prompt); executables running from Downloads, tmp or mounted images |
| `launchd` | state | LaunchAgents / LaunchDaemons with resolved target and its signature |
| `network` | state | TCP and UDP listeners, outbound (command, remote port) pairs with remote IPs, resolvers, system proxy, `/etc/resolver` |
| `downloads` | event | Files that arrived with the quarantine flag since the last run: installers, bundles, scripts, archives, executables — with agent, sha256 and signature |
| `browser` | state | Extensions (id, source, permissions) and forced-install / proxy / homepage / search policies for every installed browser |
| `host_security` | state, daily | Users, admin group, Remote Login / Screen Sharing / Remote Management / SMB, Gatekeeper, SIP, configuration profiles, system extensions, login items |
| `sensitive_paths` | state | SSH files, shell rc files, long-lived credential stores, sudoers, cron / at |
| `docker` | state | Privileged containers and Docker-socket mounts |
| `claude_code_config` | state | Hooks, MCP servers, plugins, skills, commands, agents — the model's own supply chain |

Command-line pattern rules and the IOC match run over the **whole snapshot** every time, not only over what changed: a baselined shell that picks up `curl | sh`, or a known-bad remote inside a normal (command, port) pair, surfaces as `change: flagged`. An IOC hit floors at **critical**.

*State* collectors diff against a baseline that grows only through `edr accept`. *Event* collectors report each event once and never baseline it. On the first run of a new or version-bumped collector everything appears as `added`: review, then `edr accept --all --collector <name>`.

## Unattended nightly scan

`edr schedule install` writes a launchd calendar job (default 22:00, fires on wake if missed, runs under `caffeinate`). With `notify.channel: discord` in `config.yaml` the job posts findings to one guild text channel as a numbered list; reply `1`, `1 2`, `ok 2` (accept as benign), `why 1` or `skip`. User-scope actions run the same night; anything needing root queues until the next `/edr:macos` at the Mac, where it raises the admin dialog. Every failed run posts one `scan incomplete` line; Sundays post a one-line heartbeat when clean. With `notify.channel: none` nothing is posted and the batch opens the next interactive run.

Discord setup, once: a bot token (the Claude Code Discord plugin's works), a private server the bot is in, a text channel the plugin has **not** opted into (the plugin routes DMs into every open Claude session), and in `config.yaml`: `notify.channel: discord`, `channel_id`, `user_id`. `edr notify test` proves it.

## Code vs host-local data

- **Plugin install dir** (this repo, copied to `~/.claude/plugins/cache/...` on install): Python runtime, default triage rules, intel feeds, simulator scenarios. Read-only after install.
- **Host data dir** (`~/.claude/edr/`, override with `$EDR_HOME`): baseline, snapshots, alert batches, approval ledger, lessons, changelog, `pending_changes/`, `intel/db.sqlite`, telemetry, `config.yaml`. Created on first run.

User overrides for shipped defaults: `${EDR_HOME}/triage_rules.user.yaml` (rules, host-specific exclusions) and `${EDR_HOME}/manifest.user.yaml` (collector maturity / version).

## Architecture

```
collectors (Python, ≤ 1 s each, discovery + version gates via macos.py)
   ↓ evidence — state (baselined) or event (windowed since last run)
diff vs baseline → triage: floors from rules, intel match, FP suppress
   ↓ anomalies
analyst (Claude in SKILL.md) — pivots, classifies per NIST §3.2.4, declares one action per finding
   ↓ state/alerts/<ts>.json
chat narration | nightly: Discord post → your reply → edr poll runs approved actions
```

Collectors are pluggable: drop a `runtime/collectors/foo.py` implementing `Collector`; it is auto-discovered next tick. Set `stateless = True` for event collectors. Every source that depends on the macOS version, a tool or a permission goes through `runtime/macos.py`.

## Testing

```
python3 -m pytest plugins/edr/tests -q      # unit: rules, grammar, ledger, browser fixtures, macOS gating
edr test all                                 # simulators against the live install
```

Simulators: `fake_launchagent`, `fake_privileged_docker`, `fake_download_exec`, `fake_outbound_ioc`, `fake_extension`, `notify_offline`.

## Status

Phase A (local): 9 collectors, unattended nightly loop over Discord, intel feeds. Not built: Phase 3 exec telemetry (`eslogger`, root + Full Disk Access, opt-in), Phase B cloud (Firestore, email). Windows and Linux are not supported.
