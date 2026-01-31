"""Tests for the activity collector hook."""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from activity_collector import (
    extract_learning_event,
    get_session_log_path,
    log_activity,
    parse_hook_input,
)


class TestParseHookInput:
    """Tests for parsing hook input from stdin."""

    def test_parses_valid_json(self):
        hook_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/project/src/api.py",
                "content": "def handler(): pass"
            },
            "tool_output": "File written successfully",
            "session_id": "abc123",
            "transcript_path": "/Users/sam/.claude/projects/test/transcript.jsonl"
        }
        result = parse_hook_input(json.dumps(hook_input))
        assert result["tool_name"] == "Write"
        assert result["session_id"] == "abc123"

    def test_returns_none_for_invalid_json(self):
        result = parse_hook_input("not valid json")
        assert result is None

    def test_returns_none_for_empty_input(self):
        result = parse_hook_input("")
        assert result is None


class TestExtractLearningEvent:
    """Tests for extracting learning-worthy events from tool calls."""

    def test_extracts_file_write_event(self):
        hook_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/project/src/auth/handler.py",
                "content": "class AuthHandler:\n    pass"
            },
            "session_id": "abc123"
        }
        event = extract_learning_event(hook_data)

        assert event is not None
        assert event["event_type"] == "file_write"
        assert event["file_path"] == "/project/src/auth/handler.py"
        assert event["session_id"] == "abc123"
        assert "timestamp" in event

    def test_extracts_file_edit_event(self):
        hook_data = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/project/src/api.py",
                "old_string": "return None",
                "new_string": "return {\"status\": \"ok\"}"
            },
            "session_id": "abc123"
        }
        event = extract_learning_event(hook_data)

        assert event is not None
        assert event["event_type"] == "file_edit"
        assert "old_string" in event["context"]
        assert "new_string" in event["context"]

    def test_extracts_bash_command_with_description(self):
        hook_data = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "docker logs -f api",
                "description": "Check API container logs for errors"
            },
            "session_id": "abc123"
        }
        event = extract_learning_event(hook_data)

        assert event is not None
        assert event["event_type"] == "command"
        assert event["command"] == "docker logs -f api"
        assert event["description"] == "Check API container logs for errors"

    def test_extracts_task_delegation(self):
        hook_data = {
            "tool_name": "Task",
            "tool_input": {
                "description": "Explore codebase",
                "prompt": "Find all error handling patterns"
            },
            "session_id": "abc123"
        }
        event = extract_learning_event(hook_data)

        assert event is not None
        assert event["event_type"] == "task_delegation"

    def test_ignores_simple_read_operations(self):
        hook_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/project/README.md"},
            "session_id": "abc123"
        }
        event = extract_learning_event(hook_data)
        assert event is None

    def test_ignores_glob_operations(self):
        hook_data = {
            "tool_name": "Glob",
            "tool_input": {"pattern": "**/*.py"},
            "session_id": "abc123"
        }
        event = extract_learning_event(hook_data)
        assert event is None


class TestGetSessionLogPath:
    """Tests for determining the session log path."""

    def test_creates_path_in_project_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            transcript_path = f"/Users/sam/.claude/projects/{tmpdir}/transcript.jsonl"

            result = get_session_log_path("abc123", transcript_path, project_path)

            assert result.parent == project_path / ".claude" / "sessions"
            assert "abc123" in result.name
            assert result.suffix == ".json"

    def test_extracts_project_from_transcript_path(self):
        transcript_path = "/Users/sam/.claude/projects/-Users-sam-myproject/abc123.jsonl"
        result = get_session_log_path("abc123", transcript_path, None)

        # Should derive project path from transcript
        assert ".claude/sessions" in str(result)


class TestLogActivity:
    """Tests for logging activity to session file."""

    def test_creates_new_session_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / ".claude" / "sessions" / "test-session.json"

            event = {
                "timestamp": "2026-01-30T10:30:00",
                "session_id": "test123",
                "event_type": "file_write",
                "file_path": "/project/src/api.py"
            }

            log_activity(event, log_path)

            assert log_path.exists()
            with open(log_path) as f:
                data = json.load(f)
            assert len(data["events"]) == 1
            assert data["events"][0]["event_type"] == "file_write"

    def test_appends_to_existing_session_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "session.json"

            # Create existing file
            existing_data = {
                "session_id": "test123",
                "events": [{"event_type": "file_write", "file_path": "/a.py"}]
            }
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "w") as f:
                json.dump(existing_data, f)

            # Add new event
            new_event = {
                "timestamp": "2026-01-30T10:35:00",
                "session_id": "test123",
                "event_type": "file_edit",
                "file_path": "/b.py"
            }

            log_activity(new_event, log_path)

            with open(log_path) as f:
                data = json.load(f)
            assert len(data["events"]) == 2

    def test_handles_concurrent_writes_safely(self):
        """Ensure file locking prevents corruption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "session.json"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Initialize file
            with open(log_path, "w") as f:
                json.dump({"session_id": "test", "events": []}, f)

            # Simulate multiple rapid writes
            for i in range(10):
                event = {
                    "timestamp": f"2026-01-30T10:{i:02d}:00",
                    "session_id": "test",
                    "event_type": "command",
                    "command": f"cmd{i}"
                }
                log_activity(event, log_path)

            # Verify all events logged correctly
            with open(log_path) as f:
                data = json.load(f)
            assert len(data["events"]) == 10
