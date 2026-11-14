---
name: upgrade-all
description: Upgrade dev-workflow in every other live Claude Code session on this machine — update the plugins once, then in each session's own iTerm tab compact, reload and run the upgrade. Run it from any one session after a plugin change; macOS + iTerm2 only.
argument-hint: "[--restart] [--session <id>]... [--dry-run]"
disable-model-invocation: true
---

# upgrade-all

`/dev-workflow:upgrade` upgrades the project it runs in. This command runs it in every **other** live session whose project has an install, so one plugin change reaches every running project without visiting each tab.

## What it does

Run `scripts/fanout.sh` from this skill's directory with the user's arguments, using Bash `run_in_background` — it waits for each session to be idle, which can take as long as that session's current turn.

1. **Once for the machine:** updates dev-workflow and every plugin its manifest depends on, each from its own marketplace.
2. **Per session, in parallel, each only once it is idle**, typed into its own iTerm tab: `/compact`, `/reload-plugins`, `/dev-workflow:upgrade --yes`. A session that owns an open `/pilot` run resumes it after the upgrade (`upgrade` Step 8).
3. **`--restart`** also runs `claude update` once, then per session `/compact`, `/exit`, and a relaunch in the same tab with that session's own launch flags plus `--resume <id> '/dev-workflow:upgrade --yes'`, so it runs the new Claude Code. The session id stays the same. A session that owns an open `/pilot` run is never exited — its in-flight agents would die — and gets step 2 instead.

`--session <id>` limits it to those sessions; `--dry-run` lists each session and the mode it would get, and types nothing. Run `--dry-run` first when unsure what is live.

**Why it types.** `/compact`, `/reload-plugins` and `/exit` are built-in commands: no tool runs them and a message from another session arrives as text, not a command. Typing into the tab is the only way, so it needs macOS and iTerm2; elsewhere the script exits and prints what to type in each tab.

## Report

When the script ends, one row per session from its output: project, mode, the last step it reached, `done` or what stopped it. Add a last row for this session if its own project has an install: it is not included, so run `/dev-workflow:upgrade` here.
