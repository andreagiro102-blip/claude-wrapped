"""Your "coding personality" - the card people screenshot and share.

`signals` (built in stats.py) contains, among others:
    night_share            share of prompts typed between 22:00 and 04:59   (0-1)
    morning_share          share of prompts typed between 05:00 and 09:59   (0-1)
    weekend_share          share of prompts on Saturday/Sunday              (0-1)
    longest_streak_days    longest run of consecutive active days
    active_days, period_days
    avg_session_min        average active minutes per session
    longest_session_min
    subagent_share         share of assistant messages written by subagents (0-1)
    tool_calls_per_prompt  how much Claude does on its own for each prompt
    top_tool               most used tool name ("Bash", "Edit", "Read", ...)
    cache_hit_rate         share of input tokens served from the prompt cache (0-1)
    models_used, projects, api_usd
"""
from __future__ import annotations


def pick_archetype(signals: dict) -> tuple[str, str] | None:
    """Return (title, one-line reason) - e.g. ("The Night Owl", "41% of your prompts after 10 pm").

    Returning None hides the card.
    """
    s = signals
    # rarest traits first: the first rule that matches wins
    if s["night_share"] > 0.25:
        return ("The Night Owl", f"{s['night_share']:.0%} of your prompts came after 10 pm")
    if s["weekend_share"] > 0.35:
        return ("The Weekend Warrior", f"{s['weekend_share']:.0%} of your prompts on Saturdays and Sundays")
    if s["avg_session_min"] > 60:
        return ("The Marathoner", f"your sessions lasted {s['avg_session_min']:.0f} minutes on average")
    if s["tool_calls_per_prompt"] > 25:
        return ("The Delegator",
                f"Claude made {s['tool_calls_per_prompt']:.0f} tool calls for every prompt you typed")
    return ("The Builder", f"{s['active_days']} days shipping with Claude")
