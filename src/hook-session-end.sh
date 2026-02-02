#!/bin/bash
# SessionEnd hook for quiz generation and scheduling
# Generates session summary, generates quiz, and schedules it

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(pwd)"

# Run session summary generator - outputs summary path to stderr
SUMMARY_OUTPUT=$(python3.11 "$SCRIPT_DIR/session_summary.py" 2>&1)
SUMMARY_PATH=$(echo "$SUMMARY_OUTPUT" | grep -o '/.*summary.json' | head -1)

# If we have a summary, generate quiz and schedule it
if [ -n "$SUMMARY_PATH" ] && [ -f "$SUMMARY_PATH" ]; then
    # Generate quiz questions
    QUIZ_OUTPUT=$(python3.11 "$SCRIPT_DIR/quiz_generator.py" "$SUMMARY_PATH" 2>&1)
    QUIZ_PATH=$(echo "$QUIZ_OUTPUT" | grep -o '/.*quiz.json' | head -1)

    if [ -n "$QUIZ_PATH" ] && [ -f "$QUIZ_PATH" ]; then
        # Schedule the quiz using the scheduler
        SESSION_ID=$(python3.11 -c "import json; print(json.load(open('$SUMMARY_PATH')).get('session_id', 'unknown'))")
        python3.11 "$SCRIPT_DIR/scheduler.py" add \
            --project "$PROJECT_DIR" \
            --session-id "$SESSION_ID" \
            --type next_day \
            --summary "$SUMMARY_PATH" 2>/dev/null

        # Send notification
        osascript -e 'display notification "Quiz scheduled for tomorrow! Use /quiz when ready." with title "Claude Learning Quiz"' 2>/dev/null &
    fi
fi
