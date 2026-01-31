#!/bin/bash
# Check all projects for due quizzes and send macOS notification

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find all projects with quiz state
find ~ -name "quiz-state.json" -path "*/.claude/*" 2>/dev/null | while read state_file; do
    project_dir=$(dirname $(dirname "$state_file"))

    # Check for due quizzes
    due_count=$(python3.11 -c "
import json
from datetime import datetime
with open('$state_file') as f:
    state = json.load(f)
due = 0
for q in state.get('pending_quizzes', []):
    if datetime.fromisoformat(q['scheduled_for']) <= datetime.now():
        due += 1
print(due)
" 2>/dev/null)

    if [ "$due_count" -gt 0 ]; then
        project_name=$(basename "$project_dir")
        osascript -e "display notification \"$due_count quiz(es) waiting in $project_name\" with title \"Claude Learning Quiz\" sound name \"Glass\""
    fi
done
