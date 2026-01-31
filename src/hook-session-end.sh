#!/bin/bash
# SessionEnd hook for quiz generation and scheduling
# Generates session summary and schedules quiz for later

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run session summary generator
python3.11 "$SCRIPT_DIR/session_summary.py" 2>/dev/null

# Check if quiz was scheduled and notify
if [ -f "$(pwd)/.claude/quiz-state.json" ]; then
    pending=$(python3.11 -c "
import json
with open('$(pwd)/.claude/quiz-state.json') as f:
    state = json.load(f)
print(len(state.get('pending_quizzes', [])))
" 2>/dev/null)

    if [ "$pending" -gt 0 ]; then
        osascript -e 'display notification "Quiz scheduled! Use /quiz when ready." with title "Claude Learning Quiz"' 2>/dev/null &
    fi
fi
