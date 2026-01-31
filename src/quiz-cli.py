#!/usr/bin/env python3
"""
Quiz CLI - Main entry point for quiz operations.

Usage:
  quiz-cli.py run [--project PATH]     Run pending quiz
  quiz-cli.py generate [--project PATH] Generate quiz from latest session
  quiz-cli.py report [--project PATH]   Show blind spot report
  quiz-cli.py status [--project PATH]   Show quiz status
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from quiz_generator import generate_questions_from_summary, load_summary, save_questions
from quiz_runner import run_interactive_quiz, save_quiz_result
from results_tracker import (
    calculate_topic_scores,
    generate_blind_spot_report,
    get_skip_patterns,
    load_all_results,
)
from scheduler import (
    ScheduleType,
    add_pending_quiz,
    get_due_quizzes,
    load_quiz_state,
    mark_quiz_completed,
    save_quiz_state,
    schedule_quiz,
)


def find_latest_summary(project_path: Path) -> Path | None:
    """Find the most recent session summary."""
    summaries_dir = project_path / ".claude" / "summaries"
    if not summaries_dir.exists():
        return None

    summaries = sorted(summaries_dir.glob("*-summary.json"), reverse=True)
    return summaries[0] if summaries else None


def find_latest_quiz(project_path: Path) -> Path | None:
    """Find the most recent quiz file."""
    quizzes_dir = project_path / ".claude" / "quizzes"
    if not quizzes_dir.exists():
        return None

    quizzes = sorted(quizzes_dir.glob("*-quiz.json"), reverse=True)
    return quizzes[0] if quizzes else None


def cmd_run(args):
    """Run a pending or specified quiz."""
    project_path = args.project

    # Check for pending quizzes
    state = load_quiz_state(project_path)
    due = get_due_quizzes(state)

    quiz_path = None
    session_id = "unknown"

    if due:
        # Run the first due quiz
        quiz_info = due[0]
        session_id = quiz_info["session_id"]
        summary_path = Path(quiz_info["summary_path"])

        # Generate quiz if needed
        quiz_dir = project_path / ".claude" / "quizzes"
        date_str = datetime.now().strftime("%Y-%m-%d")
        quiz_path = quiz_dir / f"{date_str}-{session_id[:8]}-quiz.json"

        if not quiz_path.exists():
            summary = load_summary(summary_path)
            if summary:
                questions = generate_questions_from_summary(summary)
                if questions:
                    save_questions(questions, quiz_path)
    else:
        # Try to find existing quiz
        quiz_path = find_latest_quiz(project_path)
        if quiz_path:
            session_id = quiz_path.stem.split("-")[1] if "-" in quiz_path.stem else "unknown"

    if not quiz_path or not quiz_path.exists():
        print("No quiz available. Run 'quiz-cli generate' first or complete a coding session.")
        return 1

    # Run the quiz
    results = run_interactive_quiz(
        quiz_path=quiz_path,
        session_id=session_id,
        project_name=project_path.name
    )

    if results:
        # Save results
        results_dir = project_path / ".claude" / "quiz-results"
        date_str = datetime.now().strftime("%Y-%m-%d")
        result_path = results_dir / f"{date_str}-{session_id[:8]}-result.json"
        save_quiz_result(results, result_path, session_id)

        # Mark quiz as completed
        state = mark_quiz_completed(state, session_id, {
            "score": sum(1 for r in results if r.correct) / len(results) * 100,
            "total": len(results)
        })
        save_quiz_state(project_path, state)

        print(f"\nResults saved to {result_path}")

    return 0


def cmd_generate(args):
    """Generate a quiz from the latest session summary."""
    project_path = args.project

    summary_path = find_latest_summary(project_path)
    if not summary_path:
        print("No session summaries found. Complete a coding session first.")
        return 1

    summary = load_summary(summary_path)
    if not summary:
        print(f"Could not load summary from {summary_path}")
        return 1

    questions = generate_questions_from_summary(summary)
    if not questions:
        print("No questions generated (session may not have enough learning content).")
        return 0

    # Save quiz
    quizzes_dir = project_path / ".claude" / "quizzes"
    session_id = summary.get("session_id", "unknown")
    date_str = datetime.now().strftime("%Y-%m-%d")
    quiz_path = quizzes_dir / f"{date_str}-{session_id[:8]}-quiz.json"

    save_questions(questions, quiz_path)
    print(f"Generated {len(questions)} questions: {quiz_path}")

    # Schedule quiz
    state = load_quiz_state(project_path)
    schedule = schedule_quiz(
        session_id=session_id,
        schedule_type=ScheduleType.ON_DEMAND,
        summary_path=str(summary_path)
    )
    state = add_pending_quiz(state, schedule)
    save_quiz_state(project_path, state)

    print(f"Quiz ready! Run 'quiz-cli run' to start.")
    return 0


def cmd_report(args):
    """Show blind spot report."""
    project_path = args.project

    results = load_all_results(project_path)
    if not results:
        print("No quiz results found. Complete some quizzes first.")
        return 1

    topic_scores = calculate_topic_scores(results)
    skip_patterns = get_skip_patterns(results)
    report = generate_blind_spot_report(topic_scores, skip_patterns)

    print(report.to_markdown())
    return 0


def cmd_status(args):
    """Show quiz status."""
    project_path = args.project

    state = load_quiz_state(project_path)
    due = get_due_quizzes(state)
    pending = state.get("pending_quizzes", [])
    completed = state.get("completed_quizzes", [])

    print(f"\n📊 Quiz Status for {project_path.name}")
    print("=" * 50)
    print(f"  Due now: {len(due)}")
    print(f"  Pending: {len(pending)}")
    print(f"  Completed: {len(completed)}")

    if due:
        print(f"\n⏰ Quizzes due:")
        for q in due:
            print(f"    - Session {q['session_id'][:8]} ({q['type']})")

    if pending and not due:
        print(f"\n📅 Next scheduled:")
        next_quiz = min(pending, key=lambda x: x["scheduled_for"])
        print(f"    - {next_quiz['scheduled_for'][:16]} ({next_quiz['type']})")

    print()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Quiz CLI")
    parser.add_argument("--project", "-p", type=Path, default=Path.cwd(),
                       help="Project directory")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run", help="Run pending quiz")
    subparsers.add_parser("generate", help="Generate quiz from latest session")
    subparsers.add_parser("report", help="Show blind spot report")
    subparsers.add_parser("status", help="Show quiz status")

    args = parser.parse_args()

    commands = {
        "run": cmd_run,
        "generate": cmd_generate,
        "report": cmd_report,
        "status": cmd_status,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
