"""Tests for the results tracker and blind spot analysis."""
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from results_tracker import (
    BlindSpotReport,
    aggregate_results,
    calculate_topic_scores,
    generate_blind_spot_report,
    get_skip_patterns,
    load_all_results,
    merge_result_into_state,
)


class TestLoadAllResults:
    """Tests for loading quiz results."""

    def test_loads_results_from_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / ".claude" / "quiz-results"
            results_dir.mkdir(parents=True)

            # Create some result files
            for i in range(3):
                result = {
                    "session_id": f"session{i}",
                    "completed_at": datetime.now().isoformat(),
                    "questions": [
                        {"type": "system_design", "correct": True, "tags": ["test"]}
                    ]
                }
                with open(results_dir / f"result{i}.json", "w") as f:
                    json.dump(result, f)

            results = load_all_results(Path(tmpdir))
            assert len(results) == 3

    def test_returns_empty_for_no_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = load_all_results(Path(tmpdir))
            assert results == []


class TestCalculateTopicScores:
    """Tests for calculating scores by topic."""

    def test_calculates_scores_per_type(self):
        results = [
            {
                "questions": [
                    {"type": "system_design", "correct": True, "tags": []},
                    {"type": "system_design", "correct": False, "tags": []},
                    {"type": "counterfactual", "correct": True, "tags": []},
                ]
            },
            {
                "questions": [
                    {"type": "system_design", "correct": True, "tags": []},
                    {"type": "debugging", "correct": False, "tags": []},
                ]
            }
        ]

        scores = calculate_topic_scores(results)

        assert scores["system_design"]["correct"] == 2
        assert scores["system_design"]["total"] == 3
        assert scores["counterfactual"]["correct"] == 1
        assert scores["debugging"]["total"] == 1

    def test_calculates_scores_per_tag(self):
        results = [
            {
                "questions": [
                    {"type": "system_design", "correct": True, "tags": ["redis", "caching"]},
                    {"type": "system_design", "correct": False, "tags": ["redis"]},
                    {"type": "debugging", "correct": True, "tags": ["docker"]},
                ]
            }
        ]

        scores = calculate_topic_scores(results)

        assert "redis" in scores
        assert scores["redis"]["correct"] == 1
        assert scores["redis"]["total"] == 2


class TestGetSkipPatterns:
    """Tests for analyzing skip patterns."""

    def test_counts_skip_reasons(self):
        results = [
            {
                "skip_reasons": {"time_pressure": 2, "already_know": 1}
            },
            {
                "skip_reasons": {"time_pressure": 1}
            }
        ]

        patterns = get_skip_patterns(results)

        assert patterns["time_pressure"] == 3
        assert patterns["already_know"] == 1

    def test_returns_empty_for_no_skips(self):
        results = [
            {"skip_reasons": {}}
        ]

        patterns = get_skip_patterns(results)
        assert patterns == {}


class TestGenerateBlindSpotReport:
    """Tests for generating blind spot reports."""

    def test_identifies_weak_areas(self):
        topic_scores = {
            "system_design": {"correct": 8, "total": 10},  # 80% - strong
            "failure_modes": {"correct": 3, "total": 10},  # 30% - weak
            "debugging": {"correct": 6, "total": 10},  # 60% - needs work
        }

        report = generate_blind_spot_report(topic_scores)

        weak_topics = [t[0] for t in report.weak_areas]
        strong_topics = [t[0] for t in report.strong_areas]
        needs_work_topics = [t[0] for t in report.needs_work]

        assert "failure_modes" in weak_topics
        assert "system_design" in strong_topics
        assert "debugging" in needs_work_topics

    def test_handles_no_data(self):
        report = generate_blind_spot_report({})

        assert report.weak_areas == []
        assert report.strong_areas == []

    def test_includes_suggestions(self):
        topic_scores = {
            "async_patterns": {"correct": 2, "total": 10}
        }

        report = generate_blind_spot_report(topic_scores)

        assert len(report.suggestions) >= 1


class TestAggregateResults:
    """Tests for aggregating results across sessions."""

    def test_aggregates_multiple_sessions(self):
        results = [
            {
                "session_id": "session1",
                "summary": {"total": 5, "correct": 4, "skipped": 0},
                "questions": []
            },
            {
                "session_id": "session2",
                "summary": {"total": 5, "correct": 3, "skipped": 1},
                "questions": []
            }
        ]

        aggregated = aggregate_results(results)

        assert aggregated["total_quizzes"] == 2
        assert aggregated["total_questions"] == 10
        assert aggregated["total_correct"] == 7
        assert aggregated["overall_score"] == 70  # 7/10

    def test_handles_empty_results(self):
        aggregated = aggregate_results([])

        assert aggregated["total_quizzes"] == 0
        assert aggregated["overall_score"] == 0


class TestMergeResultIntoState:
    """Tests for merging results into quiz state."""

    def test_updates_topic_scores(self):
        state = {
            "topic_scores": {
                "system_design": {"correct": 5, "total": 10}
            }
        }

        result = {
            "questions": [
                {"type": "system_design", "correct": True, "tags": []},
                {"type": "system_design", "correct": False, "tags": []},
            ]
        }

        updated = merge_result_into_state(state, result)

        assert updated["topic_scores"]["system_design"]["correct"] == 6
        assert updated["topic_scores"]["system_design"]["total"] == 12

    def test_adds_new_topics(self):
        state = {"topic_scores": {}}

        result = {
            "questions": [
                {"type": "debugging", "correct": True, "tags": ["new_tag"]},
            ]
        }

        updated = merge_result_into_state(state, result)

        assert "debugging" in updated["topic_scores"]
        assert "new_tag" in updated["topic_scores"]


class TestBlindSpotReport:
    """Tests for the BlindSpotReport dataclass."""

    def test_to_markdown(self):
        report = BlindSpotReport(
            weak_areas=[("failure_modes", 33)],
            needs_work=[("system_design", 60)],
            strong_areas=[("debugging", 85)],
            skip_patterns={"time_pressure": 5},
            suggestions=["Focus on error handling"]
        )

        markdown = report.to_markdown()

        assert "Failure Modes" in markdown  # Title case conversion
        assert "33%" in markdown
        assert "Debugging" in markdown  # Title case conversion
        assert "time pressure" in markdown  # Converted to readable text
