#!/usr/bin/env python3
"""
Results Tracker and Blind Spot Analysis for Claude Code Learning Quiz Hook.

Tracks quiz results over time to:
- Calculate scores by topic/tag
- Identify blind spots (consistently weak areas)
- Analyze skip patterns
- Generate weekly reports
"""
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# Thresholds for categorizing performance
WEAK_THRESHOLD = 0.5  # Below 50% = weak
STRONG_THRESHOLD = 0.7  # Above 70% = strong


@dataclass
class BlindSpotReport:
    """Weekly blind spot report."""
    weak_areas: list[tuple[str, int]] = field(default_factory=list)  # (topic, percent)
    needs_work: list[tuple[str, int]] = field(default_factory=list)
    strong_areas: list[tuple[str, int]] = field(default_factory=list)
    skip_patterns: dict[str, int] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_markdown(self) -> str:
        """Convert report to markdown format."""
        lines = [
            "╭─────────────────────────────────────────────────────────────╮",
            "│  Weekly Blind Spot Report                                   │",
            "╰─────────────────────────────────────────────────────────────╯",
            "",
        ]

        if self.weak_areas:
            lines.append("🔴 Weak areas (< 50% correct):")
            for topic, pct in self.weak_areas:
                lines.append(f"   • {topic.replace('_', ' ').title()} ({pct}%)")
            lines.append("")

        if self.needs_work:
            lines.append("🟡 Needs work (50-70%):")
            for topic, pct in self.needs_work:
                lines.append(f"   • {topic.replace('_', ' ').title()} ({pct}%)")
            lines.append("")

        if self.strong_areas:
            lines.append("🟢 Strong areas (> 70%):")
            for topic, pct in self.strong_areas:
                lines.append(f"   • {topic.replace('_', ' ').title()} ({pct}%)")
            lines.append("")

        if self.skip_patterns:
            lines.append("📝 Skip patterns:")
            for reason, count in self.skip_patterns.items():
                reason_text = reason.replace("_", " ")
                lines.append(f"   • {count} skips due to \"{reason_text}\"")
            lines.append("")

        if self.suggestions:
            lines.append("💡 Suggestions:")
            for suggestion in self.suggestions:
                lines.append(f"   {suggestion}")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "weak_areas": self.weak_areas,
            "needs_work": self.needs_work,
            "strong_areas": self.strong_areas,
            "skip_patterns": self.skip_patterns,
            "suggestions": self.suggestions,
            "generated_at": self.generated_at.isoformat(),
        }


def load_all_results(project_path: Path) -> list[dict]:
    """Load all quiz results for a project.

    Args:
        project_path: Path to the project directory

    Returns:
        List of result dicts
    """
    results_dir = project_path / ".claude" / "quiz-results"
    if not results_dir.exists():
        return []

    results = []
    for result_file in results_dir.glob("*.json"):
        try:
            with open(result_file) as f:
                results.append(json.load(f))
        except (json.JSONDecodeError, IOError):
            continue

    return results


def calculate_topic_scores(results: list[dict]) -> dict[str, dict]:
    """Calculate scores broken down by topic/type and tag.

    Args:
        results: List of quiz result dicts

    Returns:
        Dict mapping topic/tag to {correct, total}
    """
    scores = {}

    for result in results:
        for question in result.get("questions", []):
            qtype = question.get("type", "unknown")
            correct = question.get("correct", False)
            tags = question.get("tags", [])

            # Track by type
            if qtype not in scores:
                scores[qtype] = {"correct": 0, "total": 0}
            scores[qtype]["total"] += 1
            if correct:
                scores[qtype]["correct"] += 1

            # Track by tag
            for tag in tags:
                if tag not in scores:
                    scores[tag] = {"correct": 0, "total": 0}
                scores[tag]["total"] += 1
                if correct:
                    scores[tag]["correct"] += 1

    return scores


def get_skip_patterns(results: list[dict]) -> dict[str, int]:
    """Aggregate skip reasons across all results.

    Args:
        results: List of quiz result dicts

    Returns:
        Dict mapping skip reason to count
    """
    patterns = {}

    for result in results:
        skip_reasons = result.get("skip_reasons", {})
        for reason, count in skip_reasons.items():
            patterns[reason] = patterns.get(reason, 0) + count

    return patterns


def generate_blind_spot_report(
    topic_scores: dict[str, dict],
    skip_patterns: dict[str, int] = None
) -> BlindSpotReport:
    """Generate a blind spot report from topic scores.

    Args:
        topic_scores: Dict mapping topic to {correct, total}
        skip_patterns: Optional dict of skip reasons

    Returns:
        BlindSpotReport object
    """
    weak_areas = []
    needs_work = []
    strong_areas = []
    suggestions = []

    for topic, scores in topic_scores.items():
        total = scores.get("total", 0)
        if total == 0:
            continue

        correct = scores.get("correct", 0)
        pct = round(correct / total * 100)

        if pct < WEAK_THRESHOLD * 100:
            weak_areas.append((topic, pct))
        elif pct < STRONG_THRESHOLD * 100:
            needs_work.append((topic, pct))
        else:
            strong_areas.append((topic, pct))

    # Sort by percentage
    weak_areas.sort(key=lambda x: x[1])
    needs_work.sort(key=lambda x: x[1])
    strong_areas.sort(key=lambda x: x[1], reverse=True)

    # Generate suggestions based on weak areas
    for topic, pct in weak_areas[:3]:  # Top 3 weakest
        topic_text = topic.replace("_", " ")
        suggestions.append(
            f"Next session, pay extra attention when Claude discusses {topic_text}."
        )

    # Suggestions based on skip patterns
    skip_patterns = skip_patterns or {}
    if skip_patterns.get("time_pressure", 0) >= 3:
        suggestions.append("Consider shorter quizzes to reduce time pressure skips.")

    return BlindSpotReport(
        weak_areas=weak_areas,
        needs_work=needs_work,
        strong_areas=strong_areas,
        skip_patterns=skip_patterns,
        suggestions=suggestions,
    )


def aggregate_results(results: list[dict]) -> dict:
    """Aggregate statistics across all quiz results.

    Args:
        results: List of quiz result dicts

    Returns:
        Aggregated statistics dict
    """
    if not results:
        return {
            "total_quizzes": 0,
            "total_questions": 0,
            "total_correct": 0,
            "total_skipped": 0,
            "overall_score": 0,
        }

    total_quizzes = len(results)
    total_questions = 0
    total_correct = 0
    total_skipped = 0

    for result in results:
        summary = result.get("summary", {})
        total_questions += summary.get("total", 0)
        total_correct += summary.get("correct", 0)
        total_skipped += summary.get("skipped", 0)

    overall_score = round(total_correct / total_questions * 100) if total_questions > 0 else 0

    return {
        "total_quizzes": total_quizzes,
        "total_questions": total_questions,
        "total_correct": total_correct,
        "total_skipped": total_skipped,
        "overall_score": overall_score,
    }


def merge_result_into_state(state: dict, result: dict) -> dict:
    """Merge a quiz result into the persistent state.

    Updates topic_scores with new results.

    Args:
        state: Current quiz state (with topic_scores)
        result: New quiz result to merge

    Returns:
        Updated state
    """
    if "topic_scores" not in state:
        state["topic_scores"] = {}

    for question in result.get("questions", []):
        qtype = question.get("type", "unknown")
        correct = question.get("correct", False)
        tags = question.get("tags", [])

        # Update type scores
        if qtype not in state["topic_scores"]:
            state["topic_scores"][qtype] = {"correct": 0, "total": 0}
        state["topic_scores"][qtype]["total"] += 1
        if correct:
            state["topic_scores"][qtype]["correct"] += 1

        # Update tag scores
        for tag in tags:
            if tag not in state["topic_scores"]:
                state["topic_scores"][tag] = {"correct": 0, "total": 0}
            state["topic_scores"][tag]["total"] += 1
            if correct:
                state["topic_scores"][tag]["correct"] += 1

    return state


def save_weekly_report(report: BlindSpotReport, project_path: Path) -> Path:
    """Save weekly report to file.

    Args:
        report: BlindSpotReport object
        project_path: Path to project directory

    Returns:
        Path where report was saved
    """
    reports_dir = project_path / ".claude" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = reports_dir / f"weekly-{date_str}.json"

    with open(report_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    # Also save markdown version
    md_path = reports_dir / f"weekly-{date_str}.md"
    with open(md_path, "w") as f:
        f.write(report.to_markdown())

    return report_path


def main():
    """Main entry point for results tracking."""
    import argparse

    parser = argparse.ArgumentParser(description="Quiz results tracking")
    parser.add_argument("command", choices=["report", "stats", "merge"])
    parser.add_argument("--project", "-p", type=Path, default=Path.cwd())
    parser.add_argument("--result", "-r", type=Path, help="Result file to merge")

    args = parser.parse_args()

    if args.command == "report":
        results = load_all_results(args.project)
        if not results:
            print("No quiz results found.")
            sys.exit(0)

        topic_scores = calculate_topic_scores(results)
        skip_patterns = get_skip_patterns(results)
        report = generate_blind_spot_report(topic_scores, skip_patterns)

        print(report.to_markdown())

        # Save report
        report_path = save_weekly_report(report, args.project)
        print(f"\nReport saved to {report_path}")

    elif args.command == "stats":
        results = load_all_results(args.project)
        aggregated = aggregate_results(results)

        print(f"Total quizzes: {aggregated['total_quizzes']}")
        print(f"Total questions: {aggregated['total_questions']}")
        print(f"Correct: {aggregated['total_correct']}")
        print(f"Skipped: {aggregated['total_skipped']}")
        print(f"Overall score: {aggregated['overall_score']}%")

    elif args.command == "merge":
        if not args.result:
            print("--result is required for merge")
            sys.exit(1)

        # Load current state
        state_file = args.project / ".claude" / "quiz-results.json"
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
        else:
            state = {"topic_scores": {}, "results_history": []}

        # Load result
        with open(args.result) as f:
            result = json.load(f)

        # Merge
        state = merge_result_into_state(state, result)

        # Save
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        print(f"Merged result into {state_file}")


if __name__ == "__main__":
    main()
