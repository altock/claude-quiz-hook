"""Integration tests for the quiz hook system."""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from activity_collector import extract_learning_event, log_activity, get_session_log_path
from session_summary import (
    generate_summary,
    extract_architectural_decisions,
    extract_debugging_steps,
)
from quiz_generator import generate_questions_from_summary
from scheduler import (
    ScheduleType,
    add_pending_quiz,
    get_due_quizzes,
    load_quiz_state,
    save_quiz_state,
    schedule_quiz,
)
from quiz_runner import process_answer, process_skip, save_quiz_result, QuizResult, SkipReason
from results_tracker import (
    calculate_topic_scores,
    generate_blind_spot_report,
    merge_result_into_state,
)


class TestEndToEndFlow:
    """Test the complete flow from activity collection to quiz completion."""

    def test_full_workflow(self):
        """Simulate a complete coding session -> quiz -> results flow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            session_id = "test-session-123"

            # Phase 1: Activity Collection
            # Simulate tool calls during a coding session
            activities = []

            # File write
            hook_data = {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": f"{tmpdir}/src/services/auth_handler.py",
                    "content": "class AuthHandler:\n    '''Handles authentication'''\n    pass"
                },
                "session_id": session_id
            }
            event = extract_learning_event(hook_data)
            assert event is not None
            activities.append(event)

            # Bash command with description
            hook_data = {
                "tool_name": "Bash",
                "tool_input": {
                    "command": "docker logs -f auth-service",
                    "description": "Check auth service logs for errors"
                },
                "session_id": session_id
            }
            event = extract_learning_event(hook_data)
            assert event is not None
            activities.append(event)

            # Save activities to session file
            session_dir = project_path / ".claude" / "sessions"
            session_dir.mkdir(parents=True)
            session_file = session_dir / f"2026-01-30-{session_id[:8]}.json"
            with open(session_file, "w") as f:
                json.dump({"session_id": session_id, "events": activities}, f)

            # Phase 2: Session Summary
            explanations = [
                "Using JWT because it's stateless and scales better than sessions.",
                "The tradeoff is that we can't invalidate tokens easily."
            ]

            summary = generate_summary(
                session_id=session_id,
                activities=activities,
                explanations=explanations,
                duration_minutes=45
            )

            assert summary["session_id"] == session_id
            assert len(summary["architectural_decisions"]) >= 1
            assert len(summary["debugging_steps"]) >= 1

            # Save summary
            summaries_dir = project_path / ".claude" / "summaries"
            summaries_dir.mkdir(parents=True)
            summary_path = summaries_dir / f"2026-01-30-{session_id[:8]}-summary.json"
            with open(summary_path, "w") as f:
                json.dump(summary, f)

            # Phase 3: Quiz Generation
            questions = generate_questions_from_summary(summary)
            assert len(questions) >= 1

            # Phase 4: Quiz Scheduling
            state = load_quiz_state(project_path)
            schedule = schedule_quiz(
                session_id=session_id,
                schedule_type=ScheduleType.ON_DEMAND,
                summary_path=str(summary_path)
            )
            state = add_pending_quiz(state, schedule)
            save_quiz_state(project_path, state)

            # Verify quiz is due
            state = load_quiz_state(project_path)
            due = get_due_quizzes(state)
            assert len(due) == 1

            # Phase 5: Quiz Running (simulate)
            results = []

            # Answer first question correctly
            result = process_answer(
                question={"type": "system_design", "tags": ["auth"]},
                user_answer="For stateless authentication",
                self_grade="correct"
            )
            results.append(result)

            # Skip second question
            result = process_skip(
                question={"type": "counterfactual", "tags": ["failure"]},
                reason=SkipReason.TIME_PRESSURE
            )
            results.append(result)

            # Phase 6: Save Results
            results_dir = project_path / ".claude" / "quiz-results"
            result_path = results_dir / f"2026-01-30-{session_id[:8]}-result.json"
            save_quiz_result(results, result_path, session_id)

            assert result_path.exists()
            with open(result_path) as f:
                saved_result = json.load(f)
            assert saved_result["summary"]["total"] == 2
            assert saved_result["summary"]["correct"] == 1
            assert saved_result["summary"]["skipped"] == 1

            # Phase 7: Results Tracking
            topic_scores = calculate_topic_scores([saved_result])
            assert "system_design" in topic_scores
            assert topic_scores["system_design"]["correct"] == 1

            # Phase 8: Blind Spot Report
            report = generate_blind_spot_report(topic_scores, {"time_pressure": 1})
            # Should have some content based on results
            assert report is not None

    def test_empty_session_handling(self):
        """Verify graceful handling of empty/minimal sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Empty activities and explanations
            summary = generate_summary(
                session_id="empty-session",
                activities=[],
                explanations=[],
                duration_minutes=5
            )

            # Should still generate a valid summary
            assert summary["session_id"] == "empty-session"
            assert summary["architectural_decisions"] == []

            # Quiz generation should return empty
            questions = generate_questions_from_summary(summary)
            assert questions == []

    def test_state_persistence(self):
        """Verify state persists correctly across operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Add multiple quizzes
            state = load_quiz_state(project_path)
            for i in range(3):
                schedule = schedule_quiz(
                    session_id=f"session-{i}",
                    schedule_type=ScheduleType.ON_DEMAND,
                    summary_path=f"/path/summary{i}.json"
                )
                state = add_pending_quiz(state, schedule)
            save_quiz_state(project_path, state)

            # Reload and verify
            state = load_quiz_state(project_path)
            assert len(state["pending_quizzes"]) == 3

            # Verify all are due
            due = get_due_quizzes(state)
            assert len(due) == 3
