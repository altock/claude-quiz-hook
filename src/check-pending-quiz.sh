#!/bin/bash
# Check for pending quizzes and print reminder
# Called at session start to remind user of due quizzes

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3.11 "$SCRIPT_DIR/scheduler.py" notify --project "$(pwd)" 2>/dev/null
