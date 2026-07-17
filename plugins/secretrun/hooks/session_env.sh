#!/bin/sh
# SessionStart: put secretrun's bin dir on PATH for this session so the model can
# call `secretrun` / `secretrun-admin` by name. Claude Code sources the exports
# written to $CLAUDE_ENV_FILE. If that mechanism is unavailable (older CLI), the
# using-secrets skill falls back to the absolute ${CLAUDE_PLUGIN_ROOT}/bin path.
[ -n "$CLAUDE_ENV_FILE" ] || exit 0
[ -n "$CLAUDE_PLUGIN_ROOT" ] || exit 0
printf 'export PATH="%s/bin:$PATH"\n' "$CLAUDE_PLUGIN_ROOT" >> "$CLAUDE_ENV_FILE"
exit 0
