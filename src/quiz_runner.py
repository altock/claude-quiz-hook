#!/usr/bin/env python3
"""
Interactive Quiz Runner for Claude Code Learning Quiz Hook.

Terminal-based quiz interface with:
- Skip friction (requires reason to skip)
- Self-grading with optional reflection
- Hints and context display
- Progress tracking
"""
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class SkipReason(Enum):
    """Reasons for skipping a question - requires selection."""
    TIME_PRESSURE = "time_pressure"
    ALREADY_KNOW = "already_know"
    UNCLEAR = "unclear"
    OTHER = "other"


@dataclass
class QuizResult:
    """Result of answering a single question."""
    question_type: str
    tags: list[str]
    correct: bool
    skipped: bool
    partial: bool = False
    skip_reason: Optional[SkipReason] = None
    skip_note: str = ""
    reflection: str = ""
    time_seconds: int = 0
    user_answer: str = ""

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        data = {
            "type": self.question_type,
            "tags": self.tags,
            "correct": self.correct,
            "partial": self.partial,
            "skipped": self.skipped,
            "time_seconds": self.time_seconds,
        }
        if self.skipped:
            data["skip_reason"] = self.skip_reason.value if self.skip_reason else None
            data["skip_note"] = self.skip_note
        if self.reflection:
            data["reflection"] = self.reflection
        return data


def load_quiz(quiz_path: Path) -> list[dict]:
    """Load quiz questions from file.

    Args:
        quiz_path: Path to the quiz JSON file

    Returns:
        List of question dicts
    """
    if not quiz_path.exists():
        return []

    try:
        with open(quiz_path) as f:
            data = json.load(f)
        return data.get("questions", [])
    except (json.JSONDecodeError, IOError):
        return []


def format_question_display(question: dict, current: int, total: int) -> str:
    """Format a question for terminal display.

    Args:
        question: Question dict
        current: Current question number (1-indexed)
        total: Total number of questions

    Returns:
        Formatted string for display
    """
    qtype = question.get("type", "unknown").upper().replace("_", " ")
    qtext = question.get("question", "")
    tags = question.get("tags", [])

    lines = [
        "",
        f"Q{current}/{total} [{qtype}]",
        "-" * 60,
        qtext,
        "",
        f"Tags: {', '.join(tags)}" if tags else "",
        "",
        "[s] Skip (requires note)  [h] Hint  [?] Show context",
        ""
    ]

    return "\n".join(line for line in lines if line is not None)


def format_expected_answer(question: dict) -> str:
    """Format the expected answer for display after user answers.

    Args:
        question: Question dict

    Returns:
        Formatted expected answer
    """
    expected = question.get("expected_answer", "")
    context = question.get("context", "")

    lines = [
        "",
        "-" * 60,
        "Expected answer:",
        expected,
    ]

    if context:
        lines.extend([
            "",
            "Context from session:",
            context
        ])

    lines.append("-" * 60)

    return "\n".join(lines)


def process_answer(
    question: dict,
    user_answer: str,
    self_grade: str,
    reflection: str = ""
) -> QuizResult:
    """Process a user's answer to a question.

    Args:
        question: Question dict
        user_answer: User's answer text
        self_grade: Self-assessment ("correct", "partial", "wrong")
        reflection: Optional reflection on what was missed

    Returns:
        QuizResult object
    """
    return QuizResult(
        question_type=question.get("type", "unknown"),
        tags=question.get("tags", []),
        correct=(self_grade == "correct"),
        partial=(self_grade == "partial"),
        skipped=False,
        reflection=reflection,
        user_answer=user_answer,
    )


def process_skip(
    question: dict,
    reason: SkipReason,
    skip_note: str = ""
) -> QuizResult:
    """Process a skipped question.

    Args:
        question: Question dict
        reason: SkipReason enum value
        skip_note: Optional additional note

    Returns:
        QuizResult object
    """
    return QuizResult(
        question_type=question.get("type", "unknown"),
        tags=question.get("tags", []),
        correct=False,
        skipped=True,
        skip_reason=reason,
        skip_note=skip_note,
    )


def save_quiz_result(
    results: list[QuizResult],
    output_path: Path,
    session_id: str
) -> None:
    """Save quiz results to file.

    Args:
        results: List of QuizResult objects
        output_path: Path to save results
        session_id: Session identifier
    """
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    partial = sum(1 for r in results if r.partial)
    skipped = sum(1 for r in results if r.skipped)
    wrong = total - correct - partial - skipped

    # Group results by type
    by_type = {}
    for r in results:
        qtype = r.question_type
        if qtype not in by_type:
            by_type[qtype] = {"correct": 0, "total": 0}
        by_type[qtype]["total"] += 1
        if r.correct:
            by_type[qtype]["correct"] += 1

    # Group skip reasons
    skip_reasons = {}
    for r in results:
        if r.skipped and r.skip_reason:
            reason = r.skip_reason.value
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    data = {
        "session_id": session_id,
        "completed_at": datetime.now().isoformat(),
        "summary": {
            "total": total,
            "correct": correct,
            "partial": partial,
            "wrong": wrong,
            "skipped": skipped,
            "score_percent": round(correct / total * 100) if total > 0 else 0,
        },
        "by_type": by_type,
        "skip_reasons": skip_reasons,
        "questions": [r.to_dict() for r in results],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def print_header(project_name: str, session_date: str, question_count: int) -> None:
    """Print quiz header."""
    print("\n╭─────────────────────────────────────────────────────────────╮")
    print(f"│  System Design Quiz - {project_name[:20]:<20} ({session_date})    │")
    print(f"│  {question_count} questions · ~{question_count * 2} min                                       │")
    print("╰─────────────────────────────────────────────────────────────╯\n")


def print_skip_prompt() -> SkipReason:
    """Display skip reason prompt and get selection.

    Returns:
        Selected SkipReason
    """
    print("\nYou pressed [s] to skip.\n")
    print("Why are you skipping? (required)")
    print("  [t] Time pressure - need to ship")
    print("  [k] Already know this well")
    print("  [u] Question unclear")
    print("  [o] Other")
    print()

    mapping = {
        "t": SkipReason.TIME_PRESSURE,
        "k": SkipReason.ALREADY_KNOW,
        "u": SkipReason.UNCLEAR,
        "o": SkipReason.OTHER,
    }

    while True:
        choice = input("> ").strip().lower()
        if choice in mapping:
            return mapping[choice]
        print("Please enter t, k, u, or o")


def print_self_grade_prompt() -> tuple[str, str]:
    """Display self-grading prompt.

    Returns:
        Tuple of (grade, reflection)
    """
    print("\nHow'd you do?")
    print("  [c] Correct - I got the key points")
    print("  [p] Partial - I missed something important")
    print("  [w] Wrong - I didn't understand this")
    print()

    mapping = {"c": "correct", "p": "partial", "w": "wrong"}

    while True:
        choice = input("> ").strip().lower()
        if choice in mapping:
            break
        print("Please enter c, p, or w")

    reflection = ""
    if choice in ("p", "w"):
        print("\nWhat did you miss? (optional, press Enter to skip)")
        reflection = input("> ").strip()

    return mapping[choice], reflection


def print_summary(results: list[QuizResult]) -> None:
    """Print quiz summary."""
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    partial = sum(1 for r in results if r.partial)
    skipped = sum(1 for r in results if r.skipped)

    score = round(correct / total * 100) if total > 0 else 0

    print("\n╭─────────────────────────────────────────────────────────────╮")
    print("│  Quiz Complete!                                             │")
    print("╰─────────────────────────────────────────────────────────────╯")
    print(f"\n  Score: {score}% ({correct}/{total} correct)")
    if partial:
        print(f"  Partial: {partial}")
    if skipped:
        print(f"  Skipped: {skipped}")
    print()


def run_interactive_quiz(
    quiz_path: Path,
    session_id: str,
    project_name: str = "project"
) -> list[QuizResult]:
    """Run an interactive quiz session.

    Args:
        quiz_path: Path to the quiz JSON file
        session_id: Session identifier
        project_name: Name of the project

    Returns:
        List of QuizResult objects
    """
    questions = load_quiz(quiz_path)
    if not questions:
        print("No questions found in quiz file.")
        return []

    session_date = datetime.now().strftime("%b %d")
    print_header(project_name, session_date, len(questions))

    results = []

    for i, question in enumerate(questions, 1):
        start_time = time.time()

        # Display question
        print(format_question_display(question, i, len(questions)))

        # Get answer
        print("Your answer:")
        user_input = input("> ").strip()

        # Handle special commands
        if user_input.lower() == "s":
            reason = print_skip_prompt()
            skip_note = ""
            if reason == SkipReason.OTHER:
                skip_note = input("Note: ").strip()

            result = process_skip(question, reason, skip_note)
            result.time_seconds = int(time.time() - start_time)
            results.append(result)
            print("\nNoted. Question deferred to next session.\n")
            continue

        if user_input.lower() == "h":
            # Show hint (partial expected answer)
            expected = question.get("expected_answer", "")
            hint = expected[:len(expected)//3] + "..."
            print(f"\nHint: {hint}\n")
            print("Your answer:")
            user_input = input("> ").strip()

        if user_input.lower() == "?":
            # Show context
            context = question.get("context", "No additional context available.")
            print(f"\nContext: {context}\n")
            print("Your answer:")
            user_input = input("> ").strip()

        # Show expected answer
        print(format_expected_answer(question))

        # Self-grade
        grade, reflection = print_self_grade_prompt()

        result = process_answer(question, user_input, grade, reflection)
        result.time_seconds = int(time.time() - start_time)
        results.append(result)

        print()

    # Show summary
    print_summary(results)

    return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run an interactive quiz")
    parser.add_argument("quiz_file", type=Path, nargs="?", help="Path to quiz JSON file")
    parser.add_argument("--session-id", "-s", default="unknown")
    parser.add_argument("--project", "-p", default="project")
    parser.add_argument("--output", "-o", type=Path, help="Output path for results")

    args = parser.parse_args()

    if not args.quiz_file:
        # Look for most recent quiz in current project
        quiz_dir = Path.cwd() / ".claude" / "quizzes"
        if quiz_dir.exists():
            quizzes = sorted(quiz_dir.glob("*.json"), reverse=True)
            if quizzes:
                args.quiz_file = quizzes[0]

    if not args.quiz_file or not args.quiz_file.exists():
        print("No quiz file found. Generate one with /quiz-generate first.")
        sys.exit(1)

    # Run quiz
    results = run_interactive_quiz(
        quiz_path=args.quiz_file,
        session_id=args.session_id,
        project_name=args.project
    )

    # Save results
    if results:
        if args.output:
            output_path = args.output
        else:
            results_dir = args.quiz_file.parent.parent / "quiz-results"
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_path = results_dir / f"{date_str}-{args.session_id[:8]}-result.json"

        save_quiz_result(results, output_path, args.session_id)
        print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
