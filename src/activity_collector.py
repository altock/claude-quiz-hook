#!/usr/bin/env python3
"""
Activity Collector for Claude Code Learning Quiz Hook.

PostToolUse hook that captures learning-worthy events:
- Files created/modified (what and why)
- Libraries/dependencies added
- Bash commands with descriptions (debugging steps)
- Key decisions from tool inputs

Usage:
  Called as a hook with JSON input on stdin containing:
  - tool_name: Name of the tool that was used
  - tool_input: Input passed to the tool
  - tool_output: Output from the tool
  - session_id: Current session identifier
  - transcript_path: Path to session transcript
"""
import fcntl
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def parse_hook_input(input_str: str) -> Optional[dict]:
    """Parse JSON hook input from stdin.

    Args:
        input_str: JSON string from hook stdin

    Returns:
        Parsed dict or None if invalid
    """
    if not input_str or not input_str.strip():
        return None
    try:
        return json.loads(input_str)
    except json.JSONDecodeError:
        return None


def extract_learning_event(hook_data: dict) -> Optional[dict]:
    """Extract a learning-worthy event from hook data.

    Filters for events that are worth remembering:
    - File writes/edits (architectural decisions)
    - Bash commands with descriptions (debugging steps)
    - Task delegations (exploration patterns)

    Ignores:
    - Read operations (not learning events)
    - Glob/Grep (search, not action)

    Args:
        hook_data: Parsed hook input containing tool_name, tool_input, etc.

    Returns:
        Learning event dict or None if not learning-worthy
    """
    tool_name = hook_data.get("tool_name", "")
    tool_input = hook_data.get("tool_input", {})
    session_id = hook_data.get("session_id", "unknown")

    timestamp = datetime.now().isoformat()

    # File write - new file creation
    if tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "")

        return {
            "timestamp": timestamp,
            "session_id": session_id,
            "event_type": "file_write",
            "file_path": file_path,
            "context": {
                "content_preview": content[:500] if content else "",
                "content_lines": len(content.split("\n")) if content else 0
            }
        }

    # File edit - modifications
    if tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")

        return {
            "timestamp": timestamp,
            "session_id": session_id,
            "event_type": "file_edit",
            "file_path": file_path,
            "context": {
                "old_string": old_string[:200] if old_string else "",
                "new_string": new_string[:200] if new_string else "",
                "replace_all": tool_input.get("replace_all", False)
            }
        }

    # Bash command - debugging steps
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        description = tool_input.get("description", "")

        # Skip trivial commands without descriptions
        trivial_prefixes = ("ls", "pwd", "cd", "echo", "cat ", "which ")
        if not description and any(command.strip().startswith(p) for p in trivial_prefixes):
            return None

        return {
            "timestamp": timestamp,
            "session_id": session_id,
            "event_type": "command",
            "command": command,
            "description": description,
            "context": {
                "run_in_background": tool_input.get("run_in_background", False)
            }
        }

    # Task delegation - exploration patterns
    if tool_name == "Task":
        return {
            "timestamp": timestamp,
            "session_id": session_id,
            "event_type": "task_delegation",
            "context": {
                "description": tool_input.get("description", ""),
                "prompt": tool_input.get("prompt", "")[:500],
                "subagent_type": tool_input.get("subagent_type", "")
            }
        }

    # Ignore Read, Glob, Grep, etc. - not learning events
    return None


def get_session_log_path(
    session_id: str,
    transcript_path: str,
    project_path: Optional[Path] = None
) -> Path:
    """Determine the path for the session activity log.

    Creates per-session JSON files in the project's .claude/sessions/ directory.

    Args:
        session_id: Session identifier
        transcript_path: Path to the session transcript
        project_path: Optional explicit project path

    Returns:
        Path to the session log file
    """
    if project_path:
        base = project_path
    else:
        # Extract project path from transcript path
        # Format: /Users/sam/.claude/projects/-Users-sam-myproject/session.jsonl
        # Convert back to: /Users/sam/myproject
        if transcript_path and ".claude/projects/" in transcript_path:
            # Get the encoded project path segment
            parts = transcript_path.split(".claude/projects/")
            if len(parts) > 1:
                encoded = parts[1].split("/")[0]
                # Decode: -Users-sam-myproject -> /Users/sam/myproject
                decoded = "/" + encoded.replace("-", "/")
                base = Path(decoded)
            else:
                base = Path.cwd()
        else:
            base = Path.cwd()

    sessions_dir = base / ".claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Include date in filename for easier browsing
    date_str = datetime.now().strftime("%Y-%m-%d")
    return sessions_dir / f"{date_str}-{session_id[:8]}.json"


def log_activity(event: dict, log_path: Path) -> None:
    """Log an activity event to the session file.

    Uses file locking to prevent corruption from concurrent writes.

    Args:
        event: The learning event to log
        log_path: Path to the session log file
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Use file locking for safe concurrent access
    lock_path = log_path.with_suffix(".lock")

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            # Read existing data or create new
            if log_path.exists():
                with open(log_path, "r") as f:
                    data = json.load(f)
            else:
                data = {
                    "session_id": event.get("session_id", "unknown"),
                    "started": datetime.now().isoformat(),
                    "events": []
                }

            # Append event
            data["events"].append(event)
            data["updated"] = datetime.now().isoformat()

            # Write back atomically
            temp_path = log_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(log_path)

        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def main():
    """Main entry point for the hook."""
    # Read hook input from stdin
    input_str = sys.stdin.read()

    hook_data = parse_hook_input(input_str)
    if not hook_data:
        sys.exit(0)  # Silent exit on invalid input

    # Extract learning event
    event = extract_learning_event(hook_data)
    if not event:
        sys.exit(0)  # Not a learning-worthy event

    # Get log path
    session_id = hook_data.get("session_id", "unknown")
    transcript_path = hook_data.get("transcript_path", "")
    log_path = get_session_log_path(session_id, transcript_path)

    # Log the activity
    log_activity(event, log_path)


if __name__ == "__main__":
    main()
