"""Tests for the interactive quiz runner."""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quiz_runner import (
    QuizResult,
    SkipReason,
    format_question_display,
    load_quiz,
    process_answer,
    process_skip,
    save_quiz_result,
)


class TestLoadQuiz:
    """Tests for loading quiz files."""

    def test_loads_valid_quiz(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            quiz_data = {
                "generated_at": "2026-01-30T10:00:00",
                "question_count": 2,
                "questions": [
                    {
                        "type": "system_design",
                        "question": "Why use Redis?",
                        "expected_answer": "For caching",
                        "tags": ["redis"],
                        "context": "",
                        "difficulty": "medium"
                    },
                    {
                        "type": "counterfactual",
                        "question": "What if Redis fails?",
                        "expected_answer": "Cache miss",
                        "tags": ["failure"],
                        "context": "",
                        "difficulty": "medium"
                    }
                ]
            }
            json.dump(quiz_data, f)
            f.flush()

            questions = load_quiz(Path(f.name))

            assert len(questions) == 2
            assert questions[0]["type"] == "system_design"

    def test_returns_empty_for_missing_file(self):
        questions = load_quiz(Path("/nonexistent/quiz.json"))
        assert questions == []


class TestFormatQuestionDisplay:
    """Tests for question formatting."""

    def test_formats_system_design_question(self):
        question = {
            "type": "system_design",
            "question": "Why separate the auth service?",
            "tags": ["auth", "architecture"]
        }

        output = format_question_display(question, current=1, total=5)

        assert "Q1/5" in output
        assert "SYSTEM_DESIGN" in output.upper() or "SYSTEM DESIGN" in output.upper()
        assert "auth service" in output

    def test_formats_counterfactual_question(self):
        question = {
            "type": "counterfactual",
            "question": "What happens if the database goes down?",
            "tags": ["database", "failure"]
        }

        output = format_question_display(question, current=2, total=3)

        assert "Q2/3" in output
        assert "database" in output.lower()


class TestProcessAnswer:
    """Tests for processing user answers."""

    def test_records_correct_answer(self):
        question = {
            "type": "system_design",
            "question": "Why use Redis?",
            "expected_answer": "Low latency caching",
            "tags": ["redis"]
        }

        result = process_answer(
            question=question,
            user_answer="For caching with low latency",
            self_grade="correct"
        )

        assert result.correct is True
        assert result.skipped is False
        assert "redis" in result.tags

    def test_records_partial_answer(self):
        question = {
            "type": "debugging",
            "question": "How to debug?",
            "expected_answer": "Check logs then metrics",
            "tags": ["debugging"]
        }

        result = process_answer(
            question=question,
            user_answer="Check logs",
            self_grade="partial",
            reflection="Forgot about metrics"
        )

        assert result.correct is False
        assert result.partial is True
        assert result.reflection == "Forgot about metrics"

    def test_records_wrong_answer(self):
        question = {
            "type": "counterfactual",
            "question": "What if X fails?",
            "expected_answer": "Cascade failure",
            "tags": ["failure"]
        }

        result = process_answer(
            question=question,
            user_answer="Nothing happens",
            self_grade="wrong"
        )

        assert result.correct is False
        assert result.partial is False


class TestProcessSkip:
    """Tests for processing skipped questions."""

    def test_records_skip_with_reason(self):
        question = {
            "type": "system_design",
            "question": "Why this architecture?",
            "tags": ["architecture"]
        }

        result = process_skip(
            question=question,
            reason=SkipReason.TIME_PRESSURE
        )

        assert result.skipped is True
        assert result.skip_reason == SkipReason.TIME_PRESSURE

    def test_records_skip_with_custom_note(self):
        question = {
            "type": "debugging",
            "question": "How to debug?",
            "tags": ["debugging"]
        }

        result = process_skip(
            question=question,
            reason=SkipReason.OTHER,
            skip_note="Need to look this up later"
        )

        assert result.skipped is True
        assert result.skip_note == "Need to look this up later"


class TestSaveQuizResult:
    """Tests for saving quiz results."""

    def test_saves_results_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [
                QuizResult(
                    question_type="system_design",
                    tags=["redis"],
                    correct=True,
                    skipped=False,
                    time_seconds=30
                ),
                QuizResult(
                    question_type="counterfactual",
                    tags=["failure"],
                    correct=False,
                    skipped=True,
                    skip_reason=SkipReason.TIME_PRESSURE,
                    time_seconds=5
                )
            ]

            output_path = Path(tmpdir) / "result.json"
            save_quiz_result(results, output_path, session_id="abc123")

            assert output_path.exists()
            with open(output_path) as f:
                data = json.load(f)

            assert data["session_id"] == "abc123"
            assert len(data["questions"]) == 2
            assert data["summary"]["total"] == 2
            assert data["summary"]["correct"] == 1
            assert data["summary"]["skipped"] == 1


class TestQuizResultDataclass:
    """Tests for the QuizResult dataclass."""

    def test_to_dict_serialization(self):
        result = QuizResult(
            question_type="debugging",
            tags=["logs", "debugging"],
            correct=True,
            partial=False,
            skipped=False,
            time_seconds=45
        )

        data = result.to_dict()

        assert data["type"] == "debugging"
        assert data["tags"] == ["logs", "debugging"]
        assert data["correct"] is True
        assert data["time_seconds"] == 45

    def test_handles_skip_reason_serialization(self):
        result = QuizResult(
            question_type="system_design",
            tags=[],
            correct=False,
            skipped=True,
            skip_reason=SkipReason.ALREADY_KNOW,
            time_seconds=3
        )

        data = result.to_dict()

        assert data["skipped"] is True
        assert data["skip_reason"] == "already_know"
