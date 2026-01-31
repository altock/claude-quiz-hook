#!/bin/bash
# Install claude-quiz-hook
# Creates symlinks and configures Claude Code hooks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "Installing claude-quiz-hook..."

# Create directories
mkdir -p "$CLAUDE_DIR/scripts"
mkdir -p "$CLAUDE_DIR/skills"

# Remove old installation if exists
rm -rf "$CLAUDE_DIR/scripts/quiz"
rm -rf "$CLAUDE_DIR/skills/quiz"

# Create symlinks
ln -sf "$SCRIPT_DIR/src" "$CLAUDE_DIR/scripts/quiz"
ln -sf "$SCRIPT_DIR/skill" "$CLAUDE_DIR/skills/quiz"

echo "✓ Symlinked src/ → ~/.claude/scripts/quiz"
echo "✓ Symlinked skill/ → ~/.claude/skills/quiz"

# Install launchd job for notifications
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/com.claude.quiz-reminder.plist"
if [ -f "$LAUNCHD_PLIST" ]; then
    launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true
fi
cp "$SCRIPT_DIR/launchd/com.claude.quiz-reminder.plist" "$LAUNCHD_PLIST"
launchctl load "$LAUNCHD_PLIST"
echo "✓ Installed launchd job for hourly quiz reminders"

# Check if hooks are configured
if grep -q "hook-post-tool-use.sh" "$CLAUDE_DIR/settings.json" 2>/dev/null; then
    echo "✓ Hooks already configured in settings.json"
else
    echo ""
    echo "⚠️  Add these hooks to ~/.claude/settings.json manually:"
    echo ""
    cat "$SCRIPT_DIR/hooks/settings-snippet.json"
    echo ""
fi

echo ""
echo "Installation complete!"
echo ""
echo "Usage:"
echo "  /quiz         - Take a pending quiz"
echo "  /quiz-status  - Check quiz status"
echo "  /quiz-report  - View blind spot report"
echo ""
echo "Quizzes are automatically generated from your coding sessions."
