"""Turn scanned messages into the numbers shown in the report."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from .archetype import pick_archetype
from .pricing import message_cost
from .scan import TOKEN_KINDS, Scan

IDLE_GAP_MIN = 15   # a pause longer than this does not count as time spent in a session


class NoData(Exception):
    pass


def _active_minutes(events) -> float:
    total = 0.0
    for a, b in zip(events, events[1:]):
        gap = (b - a).total_seconds() / 60
        if gap <= IDLE_GAP_MIN:
            total += gap
    return total


def _longest_streak(days) -> tuple[int, date | None]:
    best, run, end, prev = 0, 0, None, None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        if run > best:
            best, end = run, d
        prev = d
    return best, end


def build(sc: Scan, prices: dict, since: date | None = None, until: date | None = None,
          hide_projects: bool = False) -> dict:
    inside = lambda ts: (since is None or ts.date() >= since) and (until is None or ts.date() <= until)
    msgs = [m for m in sc.messages if inside(m.ts)]
    prompts = [p for p in sc.prompts if inside(p)]
    if not msgs:
        raise NoData("no Claude Code activity found in this period")

    tokens = {k: sum(m.tokens[k] for m in msgs) for k in TOKEN_KINDS}
    by_model = defaultdict(lambda: {"tokens": 0, "usd": 0.0, "messages": 0})
    by_day = defaultdict(lambda: {"tokens": 0, "usd": 0.0, "messages": 0, "prompts": 0})
    projects = defaultdict(lambda: {"tokens": 0, "usd": 0.0, "sessions": set()})
    tools = Counter()
    unpriced = Counter()
    usd_total = saved_total = 0.0

    for m in msgs:
        usd, saved = message_cost(m, prices)
        n = sum(m.tokens.values())
        if usd is None:
            unpriced[m.model] += n
            usd = 0.0
        usd_total += usd
        saved_total += saved
        for bucket in (by_model[m.model], by_day[m.ts.date()], projects[m.project]):
            bucket["tokens"] += n
            bucket["usd"] += usd
        by_model[m.model]["messages"] += 1
        by_day[m.ts.date()]["messages"] += 1
        projects[m.project]["sessions"].add(m.session)
        tools.update(m.tools.values())
    for p in prompts:
        by_day[p.date()]["prompts"] += 1

    # when you work: hour/weekday of the prompts you typed (fallback: assistant messages)
    clock = prompts or [m.ts for m in msgs]
    hours = [0] * 24
    weekdays = [0] * 7
    for t in clock:
        hours[t.hour] += 1
        weekdays[t.weekday()] += 1

    sessions = []
    for s in sc.sessions.values():
        ev = [t for t in s.events if inside(t)]
        if len(ev) >= 2:
            sessions.append({"id": s.id, "project": s.project, "start": ev[0],
                             "active_min": _active_minutes(ev)})
    longest = max(sessions, key=lambda s: s["active_min"], default=None)

    ranked = sorted(projects.items(), key=lambda kv: kv[1]["usd"] or kv[1]["tokens"], reverse=True)
    alias = {name: (f"Project {i + 1}" if hide_projects else name) for i, (name, _) in enumerate(ranked)}
    top_projects = [{"name": alias[name], "tokens": p["tokens"], "usd": p["usd"],
                     "sessions": len(p["sessions"])} for name, p in ranked[:6]]
    if longest:
        longest = {**longest, "project": alias.get(longest["project"], "Project ?" if hide_projects
                                                    else longest["project"])}

    days = sorted(by_day)
    streak, streak_end = _longest_streak(days)
    busiest = max(days, key=lambda d: (by_day[d]["usd"], by_day[d]["tokens"]))
    months = defaultdict(lambda: {"tokens": 0, "usd": 0.0})
    for d in days:
        months[d.strftime("%Y-%m")]["tokens"] += by_day[d]["tokens"]
        months[d.strftime("%Y-%m")]["usd"] += by_day[d]["usd"]

    fed = tokens["input"] + tokens["cache_read"] + tokens["cache_write"]
    total_active = sum(s["active_min"] for s in sessions)
    n_prompts = len(prompts)

    signals = {
        # everything pick_archetype() may want, as plain numbers (0-1 shares, counts, minutes)
        "night_share": sum(hours[h] for h in (22, 23, 0, 1, 2, 3, 4)) / max(1, len(clock)),
        "morning_share": sum(hours[h] for h in range(5, 10)) / max(1, len(clock)),
        "weekend_share": (weekdays[5] + weekdays[6]) / max(1, len(clock)),
        "longest_streak_days": streak,
        "active_days": len(days),
        "period_days": (days[-1] - days[0]).days + 1,
        "avg_session_min": total_active / max(1, len(sessions)),
        "longest_session_min": longest["active_min"] if longest else 0,
        "subagent_share": sum(m.sidechain for m in msgs) / len(msgs),
        "tool_calls_per_prompt": sum(tools.values()) / max(1, n_prompts),
        "top_tool": tools.most_common(1)[0][0] if tools else None,
        "cache_hit_rate": tokens["cache_read"] / fed if fed else 0,
        "models_used": len(by_model),
        "projects": len(projects),
        "api_usd": usd_total,
    }

    return {
        "period": {"start": days[0], "end": days[-1]},
        "tokens": {**tokens, "total": sum(tokens.values())},
        "api_usd": usd_total,
        "cache_saved_usd": saved_total,
        "cache_hit_rate": signals["cache_hit_rate"],
        "unpriced": dict(unpriced),
        "messages": len(msgs),
        "prompts": n_prompts,
        "tool_calls": sum(tools.values()),
        "active_days": len(days),
        "active_hours": total_active / 60,
        "sessions": len(sessions),
        "streak": {"days": streak, "end": streak_end},
        "busiest_day": {"day": busiest, **by_day[busiest]},
        "longest_session": longest,
        "hours": hours,
        "weekdays": weekdays,
        "daily": [{"day": d, **by_day[d]} for d in days],
        "months": [{"month": k, **v} for k, v in sorted(months.items())],
        "models": sorted(({"model": k, **v} for k, v in by_model.items()),
                         key=lambda x: (x["usd"], x["tokens"]), reverse=True),
        "projects": top_projects,
        "project_count": len(projects),
        "tools": tools.most_common(8),
        "signals": signals,
        "archetype": pick_archetype(signals),
    }
