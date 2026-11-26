"""The numbers are only worth sharing if deduplication is right - test it on synthetic logs."""
import json
import os
import tempfile
import unittest
from datetime import date

from claude_wrapped.pricing import load_prices
from claude_wrapped.render import render
from claude_wrapped.scan import scan
from claude_wrapped.stats import build

USAGE = {"input_tokens": 10, "output_tokens": 200, "cache_read_input_tokens": 1000,
         "cache_creation_input_tokens": 100, "cache_creation": {"ephemeral_5m_input_tokens": 0}}


def assistant(uuid, msg_id, ts, block, usage=USAGE, model="claude-opus-5", sid="s1"):
    return {"type": "assistant", "uuid": uuid, "sessionId": sid, "timestamp": ts,
            "cwd": "/home/me/code/my-app",
            "message": {"id": msg_id, "model": model, "content": [block], "usage": usage}}


def user(uuid, ts, text, sid="s1", **extra):
    return {"type": "user", "uuid": uuid, "sessionId": sid, "timestamp": ts,
            "cwd": "/home/me/code/my-app", "message": {"role": "user", "content": text}, **extra}


# one prompt, then ONE assistant message written as three lines (thinking, text, tool_use)
SESSION = [
    user("u1", "2026-05-04T10:00:00Z", "fix the login bug"),
    assistant("a1", "msg_1", "2026-05-04T10:00:05Z", {"type": "thinking", "thinking": "..."}),
    assistant("a2", "msg_1", "2026-05-04T10:00:06Z", {"type": "text", "text": "On it"}),
    assistant("a3", "msg_1", "2026-05-04T10:00:07Z", {"type": "tool_use", "id": "toolu_1", "name": "Edit"}),
    user("u2", "2026-05-04T10:00:08Z", [{"type": "tool_result", "tool_use_id": "toolu_1"}],
         toolUseResult={}),
    user("u3", "2026-05-04T10:00:09Z", "<command-name>/clear</command-name>"),
]


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        proj = os.path.join(self.tmp.name, "projects", "-home-me-code-my-app")
        os.makedirs(proj)
        self.write(os.path.join(proj, "s1.jsonl"), SESSION)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, lines):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(json.dumps(x) for x in lines) + "\n{not json\n")

    def test_one_message_counted_once(self):
        sc = scan(self.tmp.name)
        self.assertEqual(len(sc.messages), 1)
        m = sc.messages[0]
        self.assertEqual(m.tokens["output"], 200)          # not 600
        self.assertEqual(list(m.tools.values()), ["Edit"])
        self.assertEqual(m.project, "my-app")

    def test_only_typed_prompts(self):
        self.assertEqual(len(scan(self.tmp.name).prompts), 1)  # not the tool result nor /clear

    def test_resumed_session_copy_is_not_double_counted(self):
        # a resumed session re-writes the old lines into a new file
        proj = os.path.join(self.tmp.name, "projects", "-home-me-code-my-app")
        self.write(os.path.join(proj, "s2.jsonl"), SESSION)
        sc = scan(self.tmp.name)
        self.assertEqual(len(sc.messages), 1)
        self.assertEqual(len(sc.prompts), 1)
        self.assertEqual(sum(len(m.tools) for m in sc.messages), 1)

    def test_cost_and_report(self):
        s = build(scan(self.tmp.name), load_prices())
        # opus-5: 10*5 + 200*25 + 1000*0.5 + 100*5*2 (1h cache write) = 6550 / 1e6
        self.assertAlmostEqual(s["api_usd"], 0.00655)
        self.assertEqual(s["tool_calls"], 1)
        html = render(s)
        self.assertIn("my-app", html)
        self.assertNotIn("fix the login bug", html)         # message text never reaches the report

    def test_archetype(self):
        from claude_wrapped.archetype import pick_archetype
        base = {"night_share": 0.05, "weekend_share": 0.2, "avg_session_min": 30,
                "tool_calls_per_prompt": 5, "active_days": 12}
        self.assertEqual(pick_archetype(base)[0], "The Builder")
        self.assertEqual(pick_archetype({**base, "tool_calls_per_prompt": 42})[0], "The Delegator")
        # night beats delegation: rarer traits come first
        self.assertEqual(pick_archetype({**base, "tool_calls_per_prompt": 42, "night_share": 0.4})[0],
                         "The Night Owl")

    def test_hide_projects(self):
        html = render(build(scan(self.tmp.name), load_prices(), hide_projects=True))
        self.assertNotIn("my-app", html)

    def test_unknown_model_is_unpriced_not_guessed(self):
        proj = os.path.join(self.tmp.name, "projects", "-home-me-code-my-app")
        self.write(os.path.join(proj, "s3.jsonl"), [
            assistant("b1", "msg_9", "2026-05-05T09:00:00Z", {"type": "text", "text": "hi"},
                      model="claude-opus-5-9", sid="s3")])
        s = build(scan(self.tmp.name), load_prices(), since=date(2026, 5, 5))
        self.assertEqual(s["api_usd"], 0)
        self.assertIn("claude-opus-5-9", s["unpriced"])

    def test_every_bar_has_hover_numbers(self):
        html = render(build(scan(self.tmp.name), load_prices()))
        # 24 hours + 7 weekdays + the day-by-day timeline (drawn twice: wide and narrow)
        self.assertGreaterEqual(html.count('<g class="b" data-t='), 24 + 7 + 2)
        self.assertIn('data-t="Monday"', html)
        self.assertIn('class="pdf"', html)

    def test_pdf_without_browser_explains_instead_of_crashing(self):
        from unittest import mock
        from claude_wrapped import pdf
        with mock.patch.object(pdf, "find_browser", return_value=None):
            err = pdf.html_to_pdf(__file__, os.path.join(self.tmp.name, "x.pdf"))
        self.assertIn("Save as PDF", err)


if __name__ == "__main__":
    unittest.main()
