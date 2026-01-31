"""Tests for the spaced repetition scheduler."""
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scheduler import (
    QuizSchedule,
    ScheduleType,
    get_due_quizzes,
    load_quiz_state,
    save_quiz_state,
    schedule_quiz,
    should_schedule_quiz,
)


class TestLoadQuizState:
    """Tests for loading quiz state."""

    def test_loads_existing_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".claude" / "quiz-state.json"
            state_file.parent.mkdir(parents=True)

            data = {
                "project": "test-project",
                "sessions": [{"id": "abc123", "date": "2026-01-30"}],
                "pending_quizzes": [],
                "completed_quizzes": []
            }
            with open(state_file, "w") as f:
                json.dump(data, f)

            result = load_quiz_state(Path(tmpdir))
            assert result["project"] == "test-project"
            assert len(result["sessions"]) == 1

    def test_creates_default_state_for_new_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_quiz_state(Path(tmpdir))

            assert "sessions" in result
            assert "pending_quizzes" in result
            assert "completed_quizzes" in result
            assert result["sessions"] == []


class TestSaveQuizState:
    """Tests for saving quiz state."""

    def test_saves_state_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {
                "project": "test",
                "sessions": [{"id": "xyz"}],
                "pending_quizzes": [],
                "completed_quizzes": []
            }

            save_quiz_state(Path(tmpdir), state)

            state_file = Path(tmpdir) / ".claude" / "quiz-state.json"
            assert state_file.exists()
            with open(state_file) as f:
                loaded = json.load(f)
            assert loaded["project"] == "test"


class TestShouldScheduleQuiz:
    """Tests for determining if a quiz should be scheduled."""

    def test_schedules_for_substantial_session(self):
        summary = {
            "duration_minutes": 45,
            "stats": {"total_activities": 20}
        }
        assert should_schedule_quiz(summary) is True

    def test_skips_for_short_session(self):
        summary = {
            "duration_minutes": 5,
            "stats": {"total_activities": 3}
        }
        assert should_schedule_quiz(summary) is False

    def test_skips_for_low_activity_session(self):
        summary = {
            "duration_minutes": 30,
            "stats": {"total_activities": 2}
        }
        assert should_schedule_quiz(summary) is False


class TestScheduleQuiz:
    """Tests for scheduling quizzes."""

    def test_schedules_same_day_quiz(self):
        schedule = schedule_quiz(
            session_id="abc123",
            schedule_type=ScheduleType.SAME_DAY,
            summary_path="/project/.claude/summaries/summary.json"
        )

        assert schedule.schedule_type == ScheduleType.SAME_DAY
        assert schedule.session_id == "abc123"
        # Same day should be today
        assert schedule.scheduled_for.date() == datetime.now().date()

    def test_schedules_next_day_quiz(self):
        schedule = schedule_quiz(
            session_id="abc123",
            schedule_type=ScheduleType.NEXT_DAY,
            summary_path="/project/.claude/summaries/summary.json"
        )

        assert schedule.schedule_type == ScheduleType.NEXT_DAY
        tomorrow = datetime.now().date() + timedelta(days=1)
        assert schedule.scheduled_for.date() == tomorrow

    def test_schedules_weekly_quiz(self):
        schedule = schedule_quiz(
            session_id="abc123",
            schedule_type=ScheduleType.WEEKLY,
            summary_path="/project/.claude/summaries/summary.json"
        )

        assert schedule.schedule_type == ScheduleType.WEEKLY
        # Weekly should be within 7 days
        delta = schedule.scheduled_for.date() - datetime.now().date()
        assert 0 <= delta.days <= 7


class TestGetDueQuizzes:
    """Tests for finding due quizzes."""

    def test_finds_past_due_quizzes(self):
        state = {
            "pending_quizzes": [
                {
                    "session_id": "abc123",
                    "scheduled_for": (datetime.now() - timedelta(hours=2)).isoformat(),
                    "type": "same_day",
                    "summary_path": "/path/summary.json"
                },
                {
                    "session_id": "def456",
                    "scheduled_for": (datetime.now() + timedelta(days=1)).isoformat(),
                    "type": "next_day",
                    "summary_path": "/path/summary2.json"
                }
            ]
        }

        due = get_due_quizzes(state)

        assert len(due) == 1
        assert due[0]["session_id"] == "abc123"

    def test_finds_quizzes_due_now(self):
        state = {
            "pending_quizzes": [
                {
                    "session_id": "abc123",
                    "scheduled_for": datetime.now().isoformat(),
                    "type": "same_day",
                    "summary_path": "/path/summary.json"
                }
            ]
        }

        due = get_due_quizzes(state)

        assert len(due) == 1

    def test_returns_empty_for_no_due_quizzes(self):
        state = {
            "pending_quizzes": [
                {
                    "session_id": "abc123",
                    "scheduled_for": (datetime.now() + timedelta(days=5)).isoformat(),
                    "type": "weekly",
                    "summary_path": "/path/summary.json"
                }
            ]
        }

        due = get_due_quizzes(state)

        assert len(due) == 0


class TestQuizScheduleDataclass:
    """Tests for the QuizSchedule dataclass."""

    def test_to_dict_serialization(self):
        schedule = QuizSchedule(
            session_id="abc123",
            schedule_type=ScheduleType.NEXT_DAY,
            scheduled_for=datetime(2026, 1, 31, 9, 0, 0),
            summary_path="/path/to/summary.json"
        )

        data = schedule.to_dict()

        assert data["session_id"] == "abc123"
        assert data["type"] == "next_day"
        assert "2026-01-31" in data["scheduled_for"]
        assert data["summary_path"] == "/path/to/summary.json"

    def test_from_dict_deserialization(self):
        data = {
            "session_id": "abc123",
            "type": "same_day",
            "scheduled_for": "2026-01-30T14:00:00",
            "summary_path": "/path/summary.json"
        }

        schedule = QuizSchedule.from_dict(data)

        assert schedule.session_id == "abc123"
        assert schedule.schedule_type == ScheduleType.SAME_DAY
        assert schedule.scheduled_for.hour == 14
