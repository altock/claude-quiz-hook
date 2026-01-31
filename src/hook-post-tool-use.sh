#!/bin/bash
# PostToolUse hook for quiz activity collection
# Runs the activity collector on Write|Edit|Bash|Task tool calls

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3.11 "$SCRIPT_DIR/activity_collector.py"
