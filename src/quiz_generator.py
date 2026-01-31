#!/usr/bin/env python3
"""
Quiz Question Generator for Claude Code Learning Quiz Hook.

Generates learning questions focused on:
1. System Design - architectural decisions, tradeoffs
2. Counterfactuals - failure modes, "what if" scenarios
3. Debugging - diagnosis process, troubleshooting patterns

NOT focused on:
- Syntax recall
- Library API details
- File location trivia
"""
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class QuestionType(Enum):
    """Types of quiz questions, prioritized by learning value."""
    SYSTEM_DESIGN = "system_design"
    COUNTERFACTUAL = "counterfactual"
    DEBUGGING = "debugging"
    ARCHITECTURAL = "architectural"


# Priority order for question types
QUESTION_PRIORITY = [
    QuestionType.SYSTEM_DESIGN,
    QuestionType.COUNTERFACTUAL,
    QuestionType.DEBUGGING,
    QuestionType.ARCHITECTURAL,
]


@dataclass
class Question:
    """A quiz question with metadata."""
    question_type: QuestionType
    question: str
    expected_answer: str
    tags: list[str] = field(default_factory=list)
    context: str = ""  # Optional context from the session
    difficulty: str = "medium"  # easy, medium, hard


def load_summary(summary_path: Path) -> Optional[dict]:
    """Load a session summary from file.

    Args:
        summary_path: Path to the summary JSON file

    Returns:
        Summary dict or None if not found
    """
    if not summary_path.exists():
        return None

    try:
        with open(summary_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def generate_system_design_questions(
    decisions: list[str],
    explanations: list[str]
) -> list[Question]:
    """Generate system design questions from architectural decisions.

    Focuses on:
    - Why certain patterns/architectures were chosen
    - Tradeoffs involved
    - Data flow understanding

    Args:
        decisions: List of architectural decision descriptions
        explanations: List of explanation strings from transcript

    Returns:
        List of Question objects
    """
    questions = []

    # Generate questions from architectural decisions
    for decision in decisions:
        # Extract key components mentioned
        components = []
        for pattern in [r"\b(service|handler|controller|api|middleware)\b",
                       r"\b(database|cache|queue|store)\b"]:
            matches = re.findall(pattern, decision, re.IGNORECASE)
            components.extend(matches)

        # Also extract named components (e.g., "auth service", "payment handler")
        named_match = re.search(r"(\w+)\s+(service|handler|controller)", decision, re.IGNORECASE)
        component_name = named_match.group(1).lower() if named_match else None

        if components:
            component = components[0].lower()
            name_part = f" ({component_name})" if component_name else ""
            question = Question(
                question_type=QuestionType.SYSTEM_DESIGN,
                question=f"Why was a separate {component}{name_part} created for this functionality? What are the benefits and drawbacks? Context: {decision}",
                expected_answer=f"Based on the session: {decision}. Consider separation of concerns, scalability, and maintainability.",
                tags=[component, "architecture", "separation"] + ([component_name] if component_name else []),
            )
            questions.append(question)

    # Generate questions from tradeoff explanations
    for explanation in explanations:
        if re.search(r"(tradeoff|trade-off|trade off)", explanation, re.IGNORECASE):
            # Extract what's being traded
            question = Question(
                question_type=QuestionType.SYSTEM_DESIGN,
                question="What tradeoff was discussed in this session, and why was that choice made?",
                expected_answer=explanation,
                tags=["tradeoff", "decision"],
            )
            questions.append(question)

        # Look for technology choices
        tech_match = re.search(
            r"(using|chose|picked|selected)\s+(\w+)\s+(because|since|as|for)",
            explanation,
            re.IGNORECASE
        )
        if tech_match:
            tech = tech_match.group(2)
            question = Question(
                question_type=QuestionType.SYSTEM_DESIGN,
                question=f"Why was {tech} chosen for this implementation?",
                expected_answer=explanation,
                tags=[tech.lower(), "technology-choice"],
            )
            questions.append(question)

    return questions


def generate_counterfactual_questions(
    failure_modes: list[str],
    decisions: list[str] = None
) -> list[Question]:
    """Generate counterfactual / failure mode questions.

    Focuses on:
    - What happens when X fails
    - Blast radius of failures
    - Recovery patterns

    Args:
        failure_modes: List of failure mode descriptions
        decisions: Optional list of decisions to generate failure questions from

    Returns:
        List of Question objects
    """
    questions = []
    decisions = decisions or []

    # Generate from explicit failure modes
    for failure in failure_modes:
        # Extract the failing component
        component_match = re.search(
            r"(if|when)\s+(\w+)\s+(fails?|goes?\s+down|is\s+slow)",
            failure,
            re.IGNORECASE
        )

        if component_match:
            component = component_match.group(2)
            question = Question(
                question_type=QuestionType.COUNTERFACTUAL,
                question=f"What happens if {component} fails or becomes unavailable? What's the blast radius?",
                expected_answer=failure,
                tags=[component.lower(), "failure-mode", "resilience"],
            )
            questions.append(question)

    # Generate from decisions that mention multiple services/components
    for decision in decisions:
        # Look for service interactions
        services = re.findall(
            r"\b(writes?\s+to|reads?\s+from|publishes?\s+to|calls?)\s+(\w+)",
            decision,
            re.IGNORECASE
        )
        if services:
            for action, target in services:
                question = Question(
                    question_type=QuestionType.COUNTERFACTUAL,
                    question=f"What happens if the {target} dependency is down when this operation runs?",
                    expected_answer=f"Based on: {decision}. Consider partial failure, data consistency, and user experience.",
                    tags=[target.lower(), "dependency-failure", "resilience"],
                )
                questions.append(question)

    return questions


def generate_debugging_questions(steps: list[dict]) -> list[Question]:
    """Generate debugging scenario questions.

    Focuses on:
    - Diagnosis process, not just commands
    - What would indicate the problem
    - Alternative debugging approaches

    Args:
        steps: List of debugging step dicts with command and description

    Returns:
        List of Question objects
    """
    questions = []

    for step in steps:
        command = step.get("command", "")
        description = step.get("description", "")

        # Skip if no meaningful description
        if not description:
            continue

        # Extract the target being debugged
        target_match = re.search(
            r"(logs?|status|inspect|check|debug)\s+(\w+)",
            command + " " + description,
            re.IGNORECASE
        )

        if target_match:
            target = target_match.group(2)

            question = Question(
                question_type=QuestionType.DEBUGGING,
                question=f"If you saw issues with {target}, what would your debugging approach be? What log entries or metrics would you look for?",
                expected_answer=f"One approach: {command}. Purpose: {description}",
                tags=[target.lower(), "debugging", "diagnosis"],
            )
            questions.append(question)

    # If we have multiple debugging steps, ask about the process
    if len(steps) >= 2:
        commands = [s.get("command", "") for s in steps[:3]]
        question = Question(
            question_type=QuestionType.DEBUGGING,
            question="What was the debugging workflow in this session? What did each step reveal?",
            expected_answer=f"Commands used: {', '.join(commands)}. This represents a progressive diagnosis approach.",
            tags=["debugging-workflow", "diagnosis"],
        )
        questions.append(question)

    return questions


def prioritize_questions(
    questions: list[Question],
    max_questions: int = 5
) -> list[Question]:
    """Prioritize and limit questions to the most valuable.

    Priority order:
    1. System design (highest value)
    2. Counterfactual / failure modes
    3. Debugging scenarios
    4. Architectural decisions

    Args:
        questions: All generated questions
        max_questions: Maximum number to return

    Returns:
        Prioritized list of questions
    """
    if not questions:
        return []

    # Group by type
    by_type: dict[QuestionType, list[Question]] = {t: [] for t in QUESTION_PRIORITY}
    for q in questions:
        if q.question_type in by_type:
            by_type[q.question_type].append(q)

    # Take questions in priority order
    result = []

    # First pass: take up to 2 from each category to ensure variety
    for qtype in QUESTION_PRIORITY:
        if len(result) >= max_questions:
            break
        available = by_type.get(qtype, [])
        for q in available[:2]:
            if len(result) < max_questions:
                result.append(q)
                by_type[qtype] = [x for x in by_type[qtype] if x != q]

    # Second pass: fill remaining slots from highest priority categories
    for qtype in QUESTION_PRIORITY:
        if len(result) >= max_questions:
            break
        available = by_type.get(qtype, [])
        for q in available:
            if len(result) < max_questions:
                result.append(q)

    return result


def generate_questions_from_summary(
    summary: dict,
    max_questions: int = 5
) -> list[Question]:
    """Generate quiz questions from a session summary.

    Main entry point for question generation.

    Args:
        summary: Session summary dict
        max_questions: Maximum questions to generate

    Returns:
        List of prioritized Question objects
    """
    all_questions = []

    # Extract data from summary
    decisions = summary.get("architectural_decisions", [])
    debugging_steps = summary.get("debugging_steps", [])
    failure_modes = summary.get("failure_modes", [])
    explanations = summary.get("explanations", [])

    # Generate each type of question
    all_questions.extend(generate_system_design_questions(decisions, explanations))
    all_questions.extend(generate_counterfactual_questions(failure_modes, decisions))
    all_questions.extend(generate_debugging_questions(debugging_steps))

    # Prioritize and limit
    return prioritize_questions(all_questions, max_questions)


def save_questions(questions: list[Question], output_path: Path) -> None:
    """Save generated questions to a JSON file.

    Args:
        questions: List of Question objects
        output_path: Path to save the questions
    """
    data = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "question_count": len(questions),
        "questions": [
            {
                "type": q.question_type.value,
                "question": q.question,
                "expected_answer": q.expected_answer,
                "tags": q.tags,
                "context": q.context,
                "difficulty": q.difficulty,
            }
            for q in questions
        ]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def main():
    """Main entry point for quiz generation."""
    import sys
    from datetime import datetime

    # Read summary path from args or stdin
    if len(sys.argv) > 1:
        summary_path = Path(sys.argv[1])
    else:
        # Read from stdin
        input_str = sys.stdin.read().strip()
        if not input_str:
            print("Usage: generate-quiz.py <summary_path>", file=sys.stderr)
            sys.exit(1)
        summary_path = Path(input_str)

    # Load summary
    summary = load_summary(summary_path)
    if not summary:
        print(f"Could not load summary from {summary_path}", file=sys.stderr)
        sys.exit(1)

    # Generate questions
    questions = generate_questions_from_summary(summary)

    if not questions:
        print("No questions generated (session may not have enough content)", file=sys.stderr)
        sys.exit(0)

    # Determine output path
    output_dir = summary_path.parent.parent / "quizzes"
    session_id = summary.get("session_id", "unknown")
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = output_dir / f"{date_str}-{session_id[:8]}-quiz.json"

    # Save questions
    save_questions(questions, output_path)
    print(f"Generated {len(questions)} questions: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
