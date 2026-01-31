# Claude Quiz Hook

A spaced-repetition learning system for Claude Code that builds durable knowledge about system design, debugging, and architectural decisions.

## What It Does

1. **Collects learning events** during your coding sessions (file changes, debugging commands, architectural decisions)
2. **Generates quiz questions** focused on:
   - System design (why was X chosen?)
   - Counterfactuals (what if X fails?)
   - Debugging scenarios (how to diagnose X?)
3. **Schedules quizzes** using spaced repetition (same-day, next-day, weekly)
4. **Tracks blind spots** to reveal patterns in what you're missing

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/claude-quiz-hook.git
cd claude-quiz-hook
./install.sh
```

Then add these hooks to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash|Task",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/scripts/quiz/hook-post-tool-use.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/scripts/quiz/hook-session-end.sh &"
          }
        ]
      }
    ]
  }
}
```

## Usage

In any Claude Code session:

| Command | Description |
|---------|-------------|
| `/quiz` | Take a pending quiz |
| `/quiz-status` | Check how many quizzes are waiting |
| `/quiz-report` | View your blind spot report |
| `/quiz-generate` | Generate a quiz from the latest session |

## How It Works

### Activity Collection
The `PostToolUse` hook captures learning-worthy events:
- File writes/edits (architectural decisions)
- Bash commands with descriptions (debugging steps)
- Task delegations (exploration patterns)

### Question Generation
Questions focus on understanding, not recall:
- **System Design**: "Why was a separate auth service created?"
- **Counterfactual**: "What happens if Redis goes down?"
- **Debugging**: "How would you diagnose connection timeouts?"

### Skip Friction
To skip a question, you must provide a reason:
- Time pressure
- Already know this
- Question unclear
- Other (with note)

This makes skipping intentional and reveals patterns.

### Spaced Repetition
Quizzes are scheduled based on the Ebbinghaus forgetting curve:
- **Same-day**: 4 hours after substantial sessions
- **Next-day**: 9 AM the following day
- **Weekly**: Friday review

### Blind Spot Tracking
Results are tracked to identify weak areas:
```
🔴 Weak areas (< 50% correct):
   • Failure Modes (33%)
   • Async Patterns (29%)

🟡 Needs work (50-70%):
   • System Design (67%)

🟢 Strong areas (> 70%):
   • Debugging (80%)
```

## Project Structure

```
claude-quiz-hook/
├── src/
│   ├── activity_collector.py   # PostToolUse hook
│   ├── session_summary.py      # SessionEnd summary
│   ├── quiz_generator.py       # Question generation
│   ├── scheduler.py            # Spaced repetition
│   ├── quiz_runner.py          # Interactive CLI
│   ├── results_tracker.py      # Blind spot analysis
│   └── quiz-cli.py             # Main CLI
├── skill/
│   └── SKILL.md                # /quiz command definition
├── hooks/
│   └── settings-snippet.json   # Hook configuration
├── launchd/
│   └── com.claude.quiz-reminder.plist
├── tests/                      # 86 unit + integration tests
├── config.json                 # Configuration options
├── install.sh
└── uninstall.sh
```

## Configuration

Edit `config.json` to customize:

```json
{
  "spaced_repetition": {
    "same_day_delay_hours": 4,
    "next_day": true,
    "weekly": true,
    "weekly_day": "friday"
  },
  "questions": {
    "per_quiz": 5,
    "priorities": ["system_design", "counterfactual", "debugging"]
  },
  "triggers": {
    "min_session_minutes": 15,
    "min_activities": 5
  }
}
```

## Uninstall

```bash
./uninstall.sh
```

Then remove the hooks from `~/.claude/settings.json`.

## Development

```bash
# Run tests
python3.11 -m pytest tests/ -v

# Run a specific test file
python3.11 -m pytest tests/test_quiz_generator.py -v
```

## License

MIT
