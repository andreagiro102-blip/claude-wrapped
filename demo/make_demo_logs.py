"""Generate a fake ~/.claude folder with one year of plausible Claude Code logs.

Used for the screenshot and the video in the README, so that no real usage is published:

    python demo/make_demo_logs.py demo/fake-claude
    python -m claude_wrapped --claude-dir demo/fake-claude --year 2026

The logs mimic the real format, including the quirk the tool corrects for:
one assistant message is written as several lines that repeat the same usage.
"""
import json
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

R = random.Random(2026)
PROJECTS = ["web-dashboard", "api-server", "mobile-app", "data-pipeline", "docs-site", "cli-tools"]
WEIGHTS = [30, 24, 18, 12, 9, 7]
MODELS = [  # (model, first day it is used)
    ("claude-sonnet-4-6", date(2026, 1, 1)),
    ("claude-opus-4-7", date(2026, 2, 10)),
    ("claude-opus-5", date(2026, 6, 1)),
    ("claude-opus-5-5", date(2026, 9, 15)),
]
TOOLS = ["Bash"] * 9 + ["Read"] * 6 + ["Edit"] * 5 + ["Write"] * 2 + ["Grep"] * 3 + ["Glob", "WebSearch", "WebFetch"]


def model_for(day):
    live = [m for m, start in MODELS if start <= day]
    return live[-1] if R.random() < 0.8 else R.choice(live + ["claude-haiku-4-5"])


def session(day, sid, project):
    # mostly late evening / night - the demo user is a night owl
    hour = R.choice([21, 22, 22, 23, 23, 0, 1, 14, 15, 10])
    t = datetime(day.year, day.month, day.day, hour, R.randint(0, 59), tzinfo=timezone.utc).astimezone()
    if hour < 5:
        t += timedelta(days=1)
    cwd = f"/home/dev/code/{project}"
    lines, ctx = [], R.randint(15_000, 30_000)
    n = 0
    for _ in range(R.randint(3, 14)):                       # prompts in this session
        t += timedelta(minutes=R.uniform(0.5, 6))
        n += 1
        lines.append({"type": "user", "uuid": f"{sid}-u{n}", "sessionId": sid, "cwd": cwd,
                      "timestamp": t.isoformat(), "origin": {"kind": "human"},
                      "message": {"role": "user", "content": "(demo prompt)"}})
        for _ in range(R.randint(2, 12)):                   # assistant turns for that prompt
            t += timedelta(seconds=R.uniform(4, 40))
            ctx += R.randint(800, 6000)
            usage = {"input_tokens": R.randint(2, 40), "output_tokens": R.randint(80, 2500),
                     "cache_read_input_tokens": ctx, "cache_creation_input_tokens": R.randint(500, 7000)}
            mid = f"msg_{sid}_{n}_{len(lines)}"
            model = model_for(day)
            blocks = [{"type": "thinking", "thinking": ""}, {"type": "text", "text": ""}]
            blocks += [{"type": "tool_use", "id": f"toolu_{mid}_{k}", "name": R.choice(TOOLS), "input": {}}
                       for k in range(R.choice([1, 1, 1, 2, 3]))]
            for b in blocks:                                # one line per block, same usage: like the real logs
                lines.append({"type": "assistant", "uuid": f"{mid}-{b['type']}-{len(lines)}",
                              "sessionId": sid, "cwd": cwd, "timestamp": t.isoformat(),
                              "message": {"id": mid, "model": model, "role": "assistant",
                                          "content": [b], "usage": usage}})
    return project, lines


def main(out):
    day, sid = date(2026, 1, 5), 0
    while day <= date(2026, 11, 20):
        busy = 0.75 if day.weekday() < 5 else 0.35
        if 6 <= day.month <= 7 or day.month == 10:          # some heavier months
            busy += 0.15
        if R.random() < busy:
            for _ in range(R.choice([1, 1, 2, 2, 3])):
                sid += 1
                project, lines = session(day, f"demo{sid:04d}", R.choices(PROJECTS, WEIGHTS)[0])
                folder = os.path.join(out, "projects", "-home-dev-code-" + project)
                os.makedirs(folder, exist_ok=True)
                with open(os.path.join(folder, f"demo{sid:04d}.jsonl"), "w", encoding="utf-8") as fh:
                    fh.write("\n".join(json.dumps(x) for x in lines) + "\n")
        day += timedelta(days=1)
    with open(os.path.join(out, "settings.json"), "w", encoding="utf-8") as fh:
        json.dump({"cleanupPeriodDays": 365}, fh)
    print(f"{sid} demo sessions written to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "fake-claude"))
