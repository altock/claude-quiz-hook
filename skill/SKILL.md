---
name: quiz
description: Run a learning quiz based on your coding sessions. Use when the user types /quiz to test their understanding of system design, debugging, and architectural decisions.
---

# Learning Quiz Skill

This skill runs an interactive learning quiz based on the user's coding sessions.

## When to Use

Use this skill when the user:
- Types `/quiz` to take a quiz
- Types `/quiz-status` to check pending quizzes
- Types `/quiz-report` to see their blind spot report
- Asks about their learning progress

## What This Skill Does

1. **Check for pending quizzes** in the current project
2. **Generate questions** focused on:
   - System design decisions (why was X architecture chosen?)
   - Counterfactuals (what happens if X fails?)
   - Debugging scenarios (how would you diagnose X?)
3. **Run an interactive quiz** with:
   - Skip friction (requires a reason to skip)
   - Self-grading with reflection
   - Hints and context from the original session
4. **Track results** to identify blind spots over time

## Implementation

When the user invokes this skill, run the quiz CLI from the current working directory:

```bash
# For /quiz - run the quiz
python3.11 ~/.claude/scripts/quiz/quiz-cli.py run

# For /quiz-status - show status
python3.11 ~/.claude/scripts/quiz/quiz-cli.py status

# For /quiz-report - show blind spot report
python3.11 ~/.claude/scripts/quiz/quiz-cli.py report

# For /quiz-generate - generate a new quiz from latest session
python3.11 ~/.claude/scripts/quiz/quiz-cli.py generate
```

The CLI uses the current working directory as the project by default.

## Quiz Question Types

Questions are NOT about syntax or API details. They focus on:

1. **System Design**: "Why did you separate the auth service from the API gateway?"
2. **Counterfactuals**: "What happens if the Redis cache goes down?"
3. **Debugging**: "You saw 'connection refused' - what was your diagnosis process?"

## Skip Friction

When users try to skip a question, they must select a reason:
- Time pressure - need to ship
- Already know this well
- Question unclear
- Other (with note)

This makes skipping intentional, not reflexive, and helps identify patterns.

## Blind Spot Tracking

Results are tracked over time to reveal patterns:
- Weak areas (< 50% correct)
- Areas needing work (50-70%)
- Strong areas (> 70%)
- Skip patterns (always skipping under time pressure?)

Run `/quiz-report` to see the weekly blind spot report.
