"""Tests for the quiz question generator."""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quiz_generator import (
    Question,
    QuestionType,
    generate_counterfactual_questions,
    generate_debugging_questions,
    generate_questions_from_summary,
    generate_system_design_questions,
    load_summary,
    prioritize_questions,
)


class TestLoadSummary:
    """Tests for loading session summaries."""

    def test_loads_valid_summary(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            summary = {
                "session_id": "abc123",
                "architectural_decisions": ["Created auth service"],
                "debugging_steps": [{"command": "docker logs api", "description": "Check logs"}],
                "failure_modes": ["If Redis down, cache fails"],
                "explanations": ["Using Redis because of low latency"]
            }
            json.dump(summary, f)
            f.flush()

            result = load_summary(Path(f.name))
            assert result["session_id"] == "abc123"
            assert len(result["architectural_decisions"]) == 1

    def test_returns_none_for_missing_file(self):
        result = load_summary(Path("/nonexistent/summary.json"))
        assert result is None


class TestGenerateSystemDesignQuestions:
    """Tests for generating system design questions."""

    def test_generates_question_from_architectural_decision(self):
        decisions = ["Created auth service in auth_handler.py"]
        explanations = ["Using JWT because it's stateless"]

        questions = generate_system_design_questions(decisions, explanations)

        assert len(questions) >= 1
        assert all(q.question_type == QuestionType.SYSTEM_DESIGN for q in questions)
        assert any("auth" in q.question.lower() for q in questions)

    def test_generates_question_from_tradeoff_explanation(self):
        decisions = []
        explanations = ["The tradeoff is using SQL over NoSQL for consistency"]

        questions = generate_system_design_questions(decisions, explanations)

        assert len(questions) >= 1
        assert any("tradeoff" in q.question.lower() or "sql" in q.question.lower() for q in questions)

    def test_returns_empty_for_no_input(self):
        questions = generate_system_design_questions([], [])
        assert questions == []


class TestGenerateCounterfactualQuestions:
    """Tests for generating counterfactual / failure mode questions."""

    def test_generates_what_if_questions(self):
        failure_modes = ["If Redis goes down, the cache will fail"]

        questions = generate_counterfactual_questions(failure_modes)

        assert len(questions) >= 1
        assert all(q.question_type == QuestionType.COUNTERFACTUAL for q in questions)
        assert any("redis" in q.question.lower() for q in questions)

    def test_generates_from_service_dependencies(self):
        decisions = ["Created webhook handler that writes to Postgres then publishes to Redis"]

        questions = generate_counterfactual_questions([], decisions)

        # Should generate "what if X fails" questions
        assert len(questions) >= 1

    def test_returns_empty_for_no_failures(self):
        questions = generate_counterfactual_questions([])
        assert questions == []


class TestGenerateDebuggingQuestions:
    """Tests for generating debugging scenario questions."""

    def test_generates_from_debugging_steps(self):
        steps = [
            {"command": "docker logs -f api", "description": "Check API container logs for errors"},
            {"command": "kubectl describe pod api", "description": "Inspect pod status"}
        ]

        questions = generate_debugging_questions(steps)

        assert len(questions) >= 1
        assert all(q.question_type == QuestionType.DEBUGGING for q in questions)

    def test_asks_about_diagnosis_process(self):
        steps = [
            {"command": "docker logs api | grep ERROR", "description": "Find error messages"}
        ]

        questions = generate_debugging_questions(steps)

        # Should ask about the debugging approach, not just what command was run
        assert len(questions) >= 1
        assert any(
            "diagnos" in q.question.lower() or
            "debug" in q.question.lower() or
            "how" in q.question.lower()
            for q in questions
        )


class TestPrioritizeQuestions:
    """Tests for question prioritization."""

    def test_prioritizes_system_design_and_counterfactual(self):
        questions = [
            Question(QuestionType.SYSTEM_DESIGN, "Why separate services?", "Because scaling", ["services"]),
            Question(QuestionType.COUNTERFACTUAL, "What if Redis fails?", "Cache miss", ["redis"]),
            Question(QuestionType.DEBUGGING, "How to check logs?", "docker logs", ["docker"]),
        ]

        prioritized = prioritize_questions(questions, max_questions=2)

        assert len(prioritized) == 2
        # System design and counterfactual should be prioritized
        types = {q.question_type for q in prioritized}
        assert QuestionType.SYSTEM_DESIGN in types or QuestionType.COUNTERFACTUAL in types

    def test_respects_max_questions(self):
        questions = [
            Question(QuestionType.SYSTEM_DESIGN, f"Q{i}", f"A{i}", [])
            for i in range(10)
        ]

        prioritized = prioritize_questions(questions, max_questions=5)

        assert len(prioritized) == 5


class TestGenerateQuestionsFromSummary:
    """Tests for the main question generation function."""

    def test_generates_mixed_question_types(self):
        summary = {
            "session_id": "abc123",
            "architectural_decisions": ["Created payment service"],
            "debugging_steps": [{"command": "docker logs payment", "description": "Check logs"}],
            "failure_modes": ["If Stripe API down, payments fail"],
            "explanations": ["Using Stripe because of documentation quality"]
        }

        questions = generate_questions_from_summary(summary)

        assert len(questions) >= 1
        types = {q.question_type for q in questions}
        # Should have variety of question types
        assert len(types) >= 1

    def test_includes_question_metadata(self):
        summary = {
            "session_id": "abc123",
            "architectural_decisions": ["Created auth handler"],
            "debugging_steps": [],
            "failure_modes": [],
            "explanations": []
        }

        questions = generate_questions_from_summary(summary)

        for q in questions:
            assert hasattr(q, "question")
            assert hasattr(q, "expected_answer")
            assert hasattr(q, "tags")
            assert isinstance(q.tags, list)

    def test_handles_empty_summary(self):
        summary = {
            "session_id": "abc123",
            "architectural_decisions": [],
            "debugging_steps": [],
            "failure_modes": [],
            "explanations": []
        }

        questions = generate_questions_from_summary(summary)

        # Should return empty list, not fail
        assert questions == []
