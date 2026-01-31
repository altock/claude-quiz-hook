#!/usr/bin/env python3
"""
Spaced Repetition Scheduler for Claude Code Learning Quiz Hook.

Manages quiz scheduling based on the Ebbinghaus forgetting curve:
- Same-day: Evening after session (immediate consolidation)
- Next-day: 24 hours later (first forgetting curve checkpoint)
- Weekly: End of week (longer-term retention)
- On-demand: /quiz command

Per-project tracking in <project>/.claude/quiz-state.json
"""
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional


class ScheduleType(Enum):
    """Types of quiz schedules based on spaced repetition."""
    SAME_DAY = "same_day"
    NEXT_DAY = "next_day"
    WEEKLY = "weekly"
    ON_DEMAND = "on_demand"


# Default configuration
DEFAULT_CONFIG = {
    "same_day_delay_hours": 4,
    "next_day_hour": 9,  # 9 AM
    "weekly_day": 4,  # Friday (0=Monday)
    "min_session_minutes": 15,
    "min_activities": 5,
}


@dataclass
class QuizSchedule:
    """A scheduled quiz."""
    session_id: str
    schedule_type: ScheduleType
    scheduled_for: datetime
    summary_path: str
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "session_id": self.session_id,
            "type": self.schedule_type.value,
            "scheduled_for": self.scheduled_for.isoformat(),
            "summary_path": self.summary_path,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QuizSchedule":
        """Deserialize from dictionary."""
        return cls(
            session_id=data["session_id"],
            schedule_type=ScheduleType(data["type"]),
            scheduled_for=datetime.fromisoformat(data["scheduled_for"]),
            summary_path=data["summary_path"],
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
        )


def load_quiz_state(project_path: Path) -> dict:
    """Load quiz state for a project.

    Args:
        project_path: Path to the project directory

    Returns:
        Quiz state dict, creating default if not exists
    """
    state_file = project_path / ".claude" / "quiz-state.json"

    if state_file.exists():
        try:
            with open(state_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Return default state
    return {
        "project": project_path.name,
        "sessions": [],
        "pending_quizzes": [],
        "completed_quizzes": [],
    }


def save_quiz_state(project_path: Path, state: dict) -> None:
    """Save quiz state for a project.

    Args:
        project_path: Path to the project directory
        state: Quiz state dict to save
    """
    state_dir = project_path / ".claude"
    state_dir.mkdir(parents=True, exist_ok=True)

    state_file = state_dir / "quiz-state.json"
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def should_schedule_quiz(summary: dict, config: dict = None) -> bool:
    """Determine if a quiz should be scheduled for this session.

    Args:
        summary: Session summary dict
        config: Optional configuration override

    Returns:
        True if quiz should be scheduled
    """
    config = config or DEFAULT_CONFIG

    duration = summary.get("duration_minutes", 0)
    stats = summary.get("stats", {})
    total_activities = stats.get("total_activities", 0)

    # Must meet minimum thresholds
    if duration < config.get("min_session_minutes", 15):
        return False

    if total_activities < config.get("min_activities", 5):
        return False

    return True


def schedule_quiz(
    session_id: str,
    schedule_type: ScheduleType,
    summary_path: str,
    config: dict = None
) -> QuizSchedule:
    """Create a quiz schedule.

    Args:
        session_id: Session identifier
        schedule_type: Type of schedule (same_day, next_day, weekly)
        summary_path: Path to the session summary
        config: Optional configuration override

    Returns:
        QuizSchedule object
    """
    config = config or DEFAULT_CONFIG
    now = datetime.now()

    if schedule_type == ScheduleType.SAME_DAY:
        delay_hours = config.get("same_day_delay_hours", 4)
        scheduled_for = now + timedelta(hours=delay_hours)

    elif schedule_type == ScheduleType.NEXT_DAY:
        tomorrow = now + timedelta(days=1)
        next_day_hour = config.get("next_day_hour", 9)
        scheduled_for = tomorrow.replace(
            hour=next_day_hour, minute=0, second=0, microsecond=0
        )

    elif schedule_type == ScheduleType.WEEKLY:
        # Find next occurrence of weekly_day
        weekly_day = config.get("weekly_day", 4)  # Friday
        days_ahead = weekly_day - now.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        target_date = now + timedelta(days=days_ahead)
        scheduled_for = target_date.replace(
            hour=9, minute=0, second=0, microsecond=0
        )

    else:  # ON_DEMAND
        scheduled_for = now

    return QuizSchedule(
        session_id=session_id,
        schedule_type=schedule_type,
        scheduled_for=scheduled_for,
        summary_path=summary_path,
    )


def get_due_quizzes(state: dict) -> list[dict]:
    """Get all quizzes that are due now or overdue.

    Args:
        state: Quiz state dict

    Returns:
        List of due quiz dicts
    """
    now = datetime.now()
    due = []

    for quiz in state.get("pending_quizzes", []):
        scheduled_for = datetime.fromisoformat(quiz["scheduled_for"])
        if scheduled_for <= now:
            due.append(quiz)

    return due


def add_pending_quiz(state: dict, schedule: QuizSchedule) -> dict:
    """Add a quiz to the pending list.

    Args:
        state: Current quiz state
        schedule: QuizSchedule to add

    Returns:
        Updated state
    """
    state["pending_quizzes"].append(schedule.to_dict())
    return state


def mark_quiz_completed(state: dict, session_id: str, result: dict) -> dict:
    """Move a quiz from pending to completed.

    Args:
        state: Current quiz state
        session_id: Session ID of completed quiz
        result: Quiz result dict

    Returns:
        Updated state
    """
    # Remove from pending
    state["pending_quizzes"] = [
        q for q in state["pending_quizzes"]
        if q["session_id"] != session_id
    ]

    # Add to completed
    state["completed_quizzes"].append({
        "session_id": session_id,
        "completed_at": datetime.now().isoformat(),
        "result": result,
    })

    return state


def send_notification(title: str, message: str) -> None:
    """Send a macOS notification.

    Args:
        title: Notification title
        message: Notification body
    """
    try:
        # Use osascript for macOS notifications
        script = f'''
        display notification "{message}" with title "{title}"
        '''
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # Silent fail on notification errors


def check_and_notify_due_quizzes(project_path: Path) -> list[dict]:
    """Check for due quizzes and send notifications.

    Args:
        project_path: Path to the project directory

    Returns:
        List of due quizzes
    """
    state = load_quiz_state(project_path)
    due = get_due_quizzes(state)

    if due:
        count = len(due)
        title = "Claude Learning Quiz"
        message = f"You have {count} quiz{'es' if count > 1 else ''} waiting for {project_path.name}"
        send_notification(title, message)

    return due


def print_pending_reminder(project_path: Path) -> None:
    """Print a terminal reminder if quizzes are pending.

    For use in SessionStart hook.

    Args:
        project_path: Path to the project directory
    """
    state = load_quiz_state(project_path)
    due = get_due_quizzes(state)

    if due:
        print("\n╭─────────────────────────────────────────────────────────────╮")
        print(f"│  📚 You have {len(due)} quiz{'es' if len(due) > 1 else ''} waiting!                                    │")
        print("│  Run /quiz to start, or continue working                    │")
        print("╰─────────────────────────────────────────────────────────────╯\n")


def main():
    """Main entry point for scheduler operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Quiz scheduler operations")
    parser.add_argument("command", choices=["check", "notify", "add", "list"])
    parser.add_argument("--project", "-p", type=Path, default=Path.cwd())
    parser.add_argument("--session-id", "-s")
    parser.add_argument("--type", "-t", choices=["same_day", "next_day", "weekly"])
    parser.add_argument("--summary", type=Path)

    args = parser.parse_args()

    if args.command == "check":
        due = check_and_notify_due_quizzes(args.project)
        if due:
            print(f"Due quizzes: {len(due)}")
            for q in due:
                print(f"  - Session {q['session_id'][:8]} ({q['type']})")
        else:
            print("No quizzes due")

    elif args.command == "notify":
        print_pending_reminder(args.project)

    elif args.command == "add":
        if not args.session_id or not args.type or not args.summary:
            print("--session-id, --type, and --summary are required for add")
            sys.exit(1)

        state = load_quiz_state(args.project)
        schedule = schedule_quiz(
            session_id=args.session_id,
            schedule_type=ScheduleType(args.type),
            summary_path=str(args.summary),
        )
        state = add_pending_quiz(state, schedule)
        save_quiz_state(args.project, state)
        print(f"Scheduled {args.type} quiz for {schedule.scheduled_for}")

    elif args.command == "list":
        state = load_quiz_state(args.project)
        pending = state.get("pending_quizzes", [])
        if pending:
            print(f"Pending quizzes ({len(pending)}):")
            for q in pending:
                print(f"  - {q['session_id'][:8]}: {q['type']} at {q['scheduled_for']}")
        else:
            print("No pending quizzes")


if __name__ == "__main__":
    main()
