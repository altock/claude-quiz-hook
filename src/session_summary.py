#!/usr/bin/env python3
"""
Session Summary Generator for Claude Code Learning Quiz Hook.

SessionEnd hook that generates a learning summary including:
- Architectural decisions made
- Failure modes discussed
- Debugging steps taken

This summary is used by the quiz generator to create relevant questions.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


def load_session_activities(session_file: Path) -> list[dict]:
    """Load activities from a session log file.

    Args:
        session_file: Path to the session JSON file

    Returns:
        List of activity events, empty if file doesn't exist
    """
    if not session_file.exists():
        return []

    try:
        with open(session_file) as f:
            data = json.load(f)
        return data.get("events", [])
    except (json.JSONDecodeError, IOError):
        return []


def extract_architectural_decisions(activities: list[dict]) -> list[str]:
    """Extract architectural decisions from session activities.

    Looks for:
    - Service/handler/controller file creation
    - Config file changes
    - Dependency additions

    Args:
        activities: List of session activity events

    Returns:
        List of architectural decision descriptions
    """
    decisions = []

    # Patterns indicating architectural components
    arch_patterns = [
        r"/services?/",
        r"/handlers?/",
        r"/controllers?/",
        r"/middleware/",
        r"/api/",
        r"/routes?/",
        r"/models?/",
        r"/repositories?/",
        r"/adapters?/",
    ]

    for activity in activities:
        if activity.get("event_type") != "file_write":
            continue

        file_path = activity.get("file_path", "")

        # Skip test files
        if "/test" in file_path.lower() or "test_" in file_path.lower():
            continue

        # Check if path matches architectural patterns
        for pattern in arch_patterns:
            if re.search(pattern, file_path, re.IGNORECASE):
                # Extract component name from path
                parts = file_path.split("/")
                filename = parts[-1] if parts else "unknown"
                component_type = None

                for part in parts:
                    if re.match(r"(services?|handlers?|controllers?|middleware|api|routes?|models?)", part, re.IGNORECASE):
                        component_type = part.rstrip("s")
                        break

                decision = f"Created {component_type or 'component'}: {filename}"

                # Add context if available
                preview = activity.get("context", {}).get("content_preview", "")
                if preview:
                    # Try to extract class/function name
                    class_match = re.search(r"class\s+(\w+)", preview)
                    func_match = re.search(r"def\s+(\w+)", preview)
                    if class_match:
                        decision = f"Created {component_type or 'class'} {class_match.group(1)} in {filename}"
                    elif func_match:
                        decision = f"Created {component_type or 'function'} {func_match.group(1)} in {filename}"

                decisions.append(decision)
                break

    return decisions


def extract_debugging_steps(activities: list[dict]) -> list[dict]:
    """Extract debugging steps from session activities.

    Looks for:
    - Log inspection commands
    - Debug flag usage
    - Error investigation patterns

    Args:
        activities: List of session activity events

    Returns:
        List of debugging step dicts with command and description
    """
    steps = []

    # Patterns indicating debugging activity
    debug_patterns = [
        r"\blogs?\b",           # log, logs
        r"debug",               # DEBUG=true, etc
        r"trace",
        r"inspect",
        r"tail\s+-f",
        r"kubectl\s+logs",
        r"docker\s+logs",
        r"journalctl",
        r"strace",
        r"tcpdump",
        r"curl\s+.*-v",        # verbose curl
    ]

    # Commands that are NOT debugging
    exclude_patterns = [
        r"^npm\s+(install|i|ci)\b",
        r"^pip\s+install",
        r"^yarn\s+(add|install)",
        r"^git\s+(add|commit|push|pull)",
        r"^mkdir",
        r"^rm\s",
        r"^cp\s",
        r"^mv\s",
    ]

    for activity in activities:
        if activity.get("event_type") != "command":
            continue

        command = activity.get("command", "")
        description = activity.get("description", "")

        # Skip excluded commands
        if any(re.search(p, command, re.IGNORECASE) for p in exclude_patterns):
            continue

        # Check if it matches debugging patterns
        is_debug = any(re.search(p, command, re.IGNORECASE) for p in debug_patterns)
        is_debug = is_debug or any(re.search(p, description, re.IGNORECASE) for p in debug_patterns)

        if is_debug:
            steps.append({
                "command": command,
                "description": description
            })

    return steps


def extract_failure_modes(explanations: list[str]) -> list[str]:
    """Extract failure mode discussions from explanations.

    Looks for:
    - "What if X fails/goes down"
    - "When X is slow/unavailable"
    - Error handling explanations
    - Tradeoff discussions

    Args:
        explanations: List of explanation strings from transcript

    Returns:
        List of failure mode descriptions
    """
    failures = []

    # Patterns indicating failure mode discussion
    failure_patterns = [
        r"(if|when)\s+\w+\s+(fails?|goes?\s+down|is\s+slow|is\s+unavailable|times?\s+out)",
        r"(tradeoff|trade-off|trade off)",
        r"(retry|fallback|circuit.?breaker)",
        r"(cascading|failure|error).*(handling|recovery)",
        r"what\s+happens\s+(if|when)",
        r"(handle|catch).*(error|exception)",
    ]

    for explanation in explanations:
        for pattern in failure_patterns:
            if re.search(pattern, explanation, re.IGNORECASE):
                # Extract the relevant sentence
                sentences = re.split(r'[.!?]+', explanation)
                for sentence in sentences:
                    if re.search(pattern, sentence, re.IGNORECASE):
                        cleaned = sentence.strip()
                        if cleaned and cleaned not in failures:
                            failures.append(cleaned)
                break

    return failures


def parse_transcript_for_explanations(transcript_path: Path) -> list[str]:
    """Parse transcript to extract Claude's explanations.

    Looks for:
    - "because" statements (reasoning)
    - "tradeoff" discussions
    - "instead of" alternatives

    Args:
        transcript_path: Path to the JSONL transcript file

    Returns:
        List of explanation strings
    """
    if not transcript_path.exists():
        return []

    explanations = []

    # Patterns indicating explanations worth capturing
    explanation_patterns = [
        r"\bbecause\b",
        r"\b(tradeoff|trade-off|trade off)\b",
        r"\binstead of\b",
        r"\bthe reason\b",
        r"\bthis (allows?|enables?|ensures?)\b",
        r"\bso that\b",
        r"\bin order to\b",
    ]

    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                # Only look at assistant messages
                if entry.get("role") != "assistant":
                    continue

                content = entry.get("content", "")
                if not content:
                    continue

                # Check for explanation patterns
                for pattern in explanation_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        # Extract relevant sentences
                        sentences = re.split(r'(?<=[.!?])\s+', content)
                        for sentence in sentences:
                            if re.search(pattern, sentence, re.IGNORECASE):
                                cleaned = sentence.strip()
                                if len(cleaned) > 20 and cleaned not in explanations:
                                    explanations.append(cleaned)
                        break

    except IOError:
        return []

    return explanations


def generate_summary(
    session_id: str,
    activities: list[dict],
    explanations: list[str],
    duration_minutes: int
) -> dict:
    """Generate a complete session summary.

    Args:
        session_id: Session identifier
        activities: List of session activities
        explanations: Extracted explanations from transcript
        duration_minutes: Session duration in minutes

    Returns:
        Complete summary dict
    """
    architectural_decisions = extract_architectural_decisions(activities)
    debugging_steps = extract_debugging_steps(activities)
    failure_modes = extract_failure_modes(explanations)

    # Determine quiz schedule based on session length and content
    # Longer sessions with more content get same-day quiz
    has_substantial_content = (
        len(architectural_decisions) >= 2 or
        len(debugging_steps) >= 3 or
        len(failure_modes) >= 2
    )

    if duration_minutes >= 30 and has_substantial_content:
        quiz_type = "same_day"
        # Schedule for 4 hours later or evening, whichever is sooner
        scheduled_time = datetime.now() + timedelta(hours=4)
    else:
        quiz_type = "next_day"
        # Schedule for 9am next day
        tomorrow = datetime.now() + timedelta(days=1)
        scheduled_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

    return {
        "session_id": session_id,
        "generated_at": datetime.now().isoformat(),
        "duration_minutes": duration_minutes,
        "architectural_decisions": architectural_decisions,
        "debugging_steps": debugging_steps,
        "failure_modes": failure_modes,
        "explanations": explanations[:10],  # Keep top 10 for quiz generation
        "quiz_scheduled": {
            "type": quiz_type,
            "scheduled_for": scheduled_time.isoformat()
        },
        "stats": {
            "total_activities": len(activities),
            "file_writes": sum(1 for a in activities if a.get("event_type") == "file_write"),
            "file_edits": sum(1 for a in activities if a.get("event_type") == "file_edit"),
            "commands": sum(1 for a in activities if a.get("event_type") == "command"),
        }
    }


def find_session_file(project_path: Path, session_id: str) -> Optional[Path]:
    """Find the session activity file for a given session.

    Args:
        project_path: Project directory path
        session_id: Session identifier

    Returns:
        Path to session file or None
    """
    sessions_dir = project_path / ".claude" / "sessions"
    if not sessions_dir.exists():
        return None

    # Look for file matching session ID
    for session_file in sessions_dir.glob("*.json"):
        if session_id[:8] in session_file.name:
            return session_file

    # Also check by date (today's sessions)
    today = datetime.now().strftime("%Y-%m-%d")
    for session_file in sessions_dir.glob(f"{today}*.json"):
        return session_file

    return None


def save_summary(summary: dict, project_path: Path) -> Path:
    """Save the session summary to project directory.

    Args:
        summary: The generated summary
        project_path: Project directory path

    Returns:
        Path where summary was saved
    """
    summaries_dir = project_path / ".claude" / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    session_id = summary["session_id"]
    date_str = datetime.now().strftime("%Y-%m-%d")
    summary_path = summaries_dir / f"{date_str}-{session_id[:8]}-summary.json"

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    return summary_path


def main():
    """Main entry point for the SessionEnd hook."""
    # Read hook input from stdin
    input_str = sys.stdin.read()

    try:
        hook_data = json.loads(input_str) if input_str else {}
    except json.JSONDecodeError:
        hook_data = {}

    session_id = hook_data.get("session_id", "unknown")
    transcript_path = hook_data.get("transcript_path", "")
    # Duration would come from session tracking
    duration_minutes = hook_data.get("session_duration_minutes", 30)

    # Determine project path from transcript
    project_path = Path.cwd()
    if transcript_path and ".claude/projects/" in transcript_path:
        parts = transcript_path.split(".claude/projects/")
        if len(parts) > 1:
            encoded = parts[1].split("/")[0]
            decoded = "/" + encoded.replace("-", "/")
            project_path = Path(decoded)

    # Find and load session activities
    session_file = find_session_file(project_path, session_id)
    activities = load_session_activities(session_file) if session_file else []

    # Parse transcript for explanations
    explanations = []
    if transcript_path:
        explanations = parse_transcript_for_explanations(Path(transcript_path))

    # Generate summary
    summary = generate_summary(
        session_id=session_id,
        activities=activities,
        explanations=explanations,
        duration_minutes=duration_minutes
    )

    # Save summary
    summary_path = save_summary(summary, project_path)

    # Output for logging
    print(f"Session summary saved to {summary_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
