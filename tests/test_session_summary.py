"""Tests for the session summary generator."""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from session_summary import (
    extract_architectural_decisions,
    extract_debugging_steps,
    extract_failure_modes,
    generate_summary,
    load_session_activities,
    parse_transcript_for_explanations,
)


class TestLoadSessionActivities:
    """Tests for loading session activity logs."""

    def test_loads_existing_session_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            data = {
                "session_id": "abc123",
                "events": [
                    {"event_type": "file_write", "file_path": "/a.py"},
                    {"event_type": "command", "command": "docker logs api"}
                ]
            }
            with open(session_file, "w") as f:
                json.dump(data, f)

            result = load_session_activities(session_file)
            assert len(result) == 2
            assert result[0]["event_type"] == "file_write"

    def test_returns_empty_for_missing_file(self):
        result = load_session_activities(Path("/nonexistent/session.json"))
        assert result == []


class TestExtractArchitecturalDecisions:
    """Tests for extracting architectural decisions from activities."""

    def test_extracts_service_creation(self):
        activities = [
            {
                "event_type": "file_write",
                "file_path": "/project/src/services/auth.py",
                "context": {"content_preview": "class AuthService:\n    '''Handles authentication'''"}
            }
        ]
        decisions = extract_architectural_decisions(activities)
        assert len(decisions) >= 1
        assert any("auth" in d.lower() for d in decisions)

    def test_extracts_from_service_directories(self):
        activities = [
            {
                "event_type": "file_write",
                "file_path": "/project/src/handlers/webhook_handler.py",
                "context": {"content_preview": "def handle_webhook(): pass"}
            }
        ]
        decisions = extract_architectural_decisions(activities)
        assert len(decisions) >= 1

    def test_ignores_test_files(self):
        activities = [
            {
                "event_type": "file_write",
                "file_path": "/project/tests/test_auth.py",
                "context": {"content_preview": "def test_login(): pass"}
            }
        ]
        decisions = extract_architectural_decisions(activities)
        # Test files shouldn't be architectural decisions
        assert len(decisions) == 0


class TestExtractDebuggingSteps:
    """Tests for extracting debugging steps from activities."""

    def test_extracts_log_inspection_commands(self):
        activities = [
            {
                "event_type": "command",
                "command": "docker logs -f api",
                "description": "Check API container logs for errors"
            },
            {
                "event_type": "command",
                "command": "kubectl logs pod/api-123",
                "description": "Inspect Kubernetes pod logs"
            }
        ]
        steps = extract_debugging_steps(activities)
        assert len(steps) == 2

    def test_extracts_debug_environment_commands(self):
        activities = [
            {
                "event_type": "command",
                "command": "DEBUG=true npm start",
                "description": "Start with debug logging enabled"
            }
        ]
        steps = extract_debugging_steps(activities)
        assert len(steps) >= 1

    def test_ignores_trivial_commands(self):
        activities = [
            {
                "event_type": "command",
                "command": "npm install",
                "description": "Install dependencies"
            }
        ]
        steps = extract_debugging_steps(activities)
        # Regular install isn't debugging
        assert len(steps) == 0


class TestExtractFailureModes:
    """Tests for extracting failure mode discussions."""

    def test_extracts_from_transcript_explanations(self):
        explanations = [
            "If Redis goes down, the webhook handler will fail because...",
            "The tradeoff here is that we lose consistency for performance.",
            "What happens when the database is slow? The request will timeout."
        ]
        failures = extract_failure_modes(explanations)
        assert len(failures) >= 2

    def test_identifies_error_handling_patterns(self):
        explanations = [
            "Added try/catch to handle connection errors",
            "The retry logic prevents cascading failures"
        ]
        failures = extract_failure_modes(explanations)
        assert len(failures) >= 1


class TestParseTranscriptForExplanations:
    """Tests for extracting explanations from transcript."""

    def test_extracts_because_statements(self):
        transcript_lines = [
            {"role": "assistant", "content": "I'm using Redis here because it provides low latency."},
            {"role": "assistant", "content": "The trade-off is memory vs speed."}
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for line in transcript_lines:
                f.write(json.dumps(line) + "\n")
            f.flush()

            explanations = parse_transcript_for_explanations(Path(f.name))

        os.unlink(f.name)
        assert len(explanations) >= 1
        assert any("Redis" in e or "trade-off" in e.lower() for e in explanations)

    def test_handles_missing_transcript(self):
        explanations = parse_transcript_for_explanations(Path("/nonexistent.jsonl"))
        assert explanations == []


class TestGenerateSummary:
    """Tests for generating the complete session summary."""

    def test_generates_complete_summary(self):
        activities = [
            {
                "event_type": "file_write",
                "file_path": "/project/src/services/payment.py",
                "context": {"content_preview": "class PaymentService: pass"}
            },
            {
                "event_type": "command",
                "command": "docker logs -f payment",
                "description": "Check payment service logs"
            }
        ]
        explanations = [
            "Using Stripe because it has better documentation than alternatives."
        ]

        summary = generate_summary(
            session_id="abc123",
            activities=activities,
            explanations=explanations,
            duration_minutes=45
        )

        assert "session_id" in summary
        assert "architectural_decisions" in summary
        assert "debugging_steps" in summary
        assert "duration_minutes" in summary
        assert summary["duration_minutes"] == 45

    def test_includes_quiz_scheduling_info(self):
        summary = generate_summary(
            session_id="abc123",
            activities=[],
            explanations=[],
            duration_minutes=30
        )

        assert "quiz_scheduled" in summary
        # Should schedule for next day by default
        assert summary["quiz_scheduled"]["type"] in ["same_day", "next_day"]
