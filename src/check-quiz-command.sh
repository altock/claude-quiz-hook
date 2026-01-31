#!/bin/bash
# UserPromptSubmit hook - intercepts /quiz command
# Also shows reminder if quizzes are pending

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Read the hook input from stdin
INPUT=$(cat)

# Extract the user's prompt
PROMPT=$(echo "$INPUT" | python3.11 -c "import sys, json; d=json.load(sys.stdin); print(d.get('prompt', ''))" 2>/dev/null)

# Check if user typed /quiz
if [[ "$PROMPT" == "/quiz"* ]]; then
    # Run the quiz CLI
    cd "$(pwd)"
    python3.11 "$SCRIPT_DIR/quiz-cli.py" run --project "$(pwd)"

    # Exit with special code to indicate we handled it
    echo '{"result": "handled"}'
    exit 0
fi

# Check if user typed /quiz-report
if [[ "$PROMPT" == "/quiz-report"* ]]; then
    python3.11 "$SCRIPT_DIR/quiz-cli.py" report --project "$(pwd)"
    echo '{"result": "handled"}'
    exit 0
fi

# Check if user typed /quiz-status
if [[ "$PROMPT" == "/quiz-status"* ]]; then
    python3.11 "$SCRIPT_DIR/quiz-cli.py" status --project "$(pwd)"
    echo '{"result": "handled"}'
    exit 0
fi

# For other prompts, just pass through
exit 0
