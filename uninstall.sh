#!/bin/bash
# Uninstall claude-quiz-hook

set -e

CLAUDE_DIR="$HOME/.claude"

echo "Uninstalling claude-quiz-hook..."

# Remove symlinks
rm -f "$CLAUDE_DIR/scripts/quiz"
rm -f "$CLAUDE_DIR/skills/quiz"
echo "✓ Removed symlinks"

# Unload and remove launchd job
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/com.claude.quiz-reminder.plist"
if [ -f "$LAUNCHD_PLIST" ]; then
    launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true
    rm -f "$LAUNCHD_PLIST"
    echo "✓ Removed launchd job"
fi

echo ""
echo "Uninstall complete!"
echo ""
echo "Note: You may want to remove the hooks from ~/.claude/settings.json manually."
echo "Quiz data in your projects (.claude/quiz-state.json, etc.) is preserved."
