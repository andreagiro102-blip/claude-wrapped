"""Render the stats as one self-contained HTML file (inline CSS, SVG and fonts, no network)."""
from __future__ import annotations

import base64
import html
import math
import os
import re
from datetime import date, timedelta

from .pricing import PRICES_UPDATED

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FULL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve"]
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONTS = (  # (family, file, weight range) - latin subsets, SIL OFL 1.1 (see fonts/OFL.txt)
    ("Fraunces", "Fraunces-600.woff2", "600"),
    ("Inter", "Inter.woff2", "400 600"),
    ("JetBrains Mono", "JetBrainsMono-500.woff2", "500"),
)


def esc(x) -> str:
    return html.escape(str(x))


def big(n: float) -> str:
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            v = n / div
            return f"{v:.1f}{suf}" if v < 100 else f"{v:.0f}{suf}"
    return f"{n:.0f}"


def usd(x: float) -> str:
    return f"${x:,.0f}" if x >= 10 or x == 0 else f"${x:,.2f}"


def model_name(m: str) -> str:
    base = re.sub(r"-\d{8}$", "", m)
    hit = re.match(r"claude-([a-z]+)-([\d-]+)$", base)
    return f"{hit[1].title()} {hit[2].replace('-', '.')}" if hit else base


def day(d) -> str:
    return f"{d:%b} {d.day}, {d.year}"     # "%-d" is not portable (fails on Windows)


def short_day(d) -> str:
    return f"{d:%b} {d.day}"


def font_faces() -> str:
    """@font-face rules with the fonts inlined, so the report never touches the network.
    A missing font file just falls back to the system stack."""
    out = []
    for family, name, weight in FONTS:
        try:
            with open(os.path.join(FONT_DIR, name), "rb") as fh:
                data = base64.b64encode(fh.read()).decode("ascii")
        except OSError:
            continue
        out.append(f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
                   f"font-display:swap;src:url(data:font/woff2;base64,{data}) format('woff2')}}")
    return "\n".join(out)


def nice_step(mx: float, lines: int = 4) -> float:
    """Round grid step (1, 2, 2.5 or 5 x 10^k) giving about `lines` gridlines up to `mx`."""
    raw = (mx or 1) / lines
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)


def bar_path(x: float, y: float, w: float, h: float, r: float) -> str:
    """A bar with rounded top corners and a flat base."""
    r = min(r, w / 2, h)
    return (f"M{x:.1f},{y + h:.1f}V{y + r:.1f}Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}H{x + w - r:.1f}"
            f"Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f}V{y + h:.1f}Z")


def tip(title: str, value: str) -> str:
    """Hover data, shown by the tooltip script (title on top, numbers below)."""
    return f' data-t="{esc(title)}" data-v="{esc(value)}"'


def bars(values, labels, w=840, h=220, hot=None, fmt=None, every=1, grid=False, tips=None) -> str:
    """Vertical bar chart. `hot` = index to highlight, `every` = label every Nth bar,
    `grid` = horizontal gridlines labelled with `fmt`, `tips` = (title, value) per bar for hover.
    Charts with few bars print every value (there is no hover on paper)."""
    if not values:
        return ""
    fmt = fmt or (lambda v: f"{v:,.0f}")
    top, bottom = 24, 24
    left = 48 if grid else 0
    mx = max(values) or 1
    if grid:
        step = nice_step(mx)
        mx = step * math.ceil(mx / step)
    y = lambda v: top + (h - top - bottom) * (1 - v / mx)
    bw = (w - left) / len(values)
    few = len(values) <= 14
    out = []
    if grid:
        k = 0
        while k * step <= mx + 1e-9:
            gy = y(k * step)
            out.append(f'<line x1="{left}" x2="{w}" y1="{gy:.1f}" y2="{gy:.1f}" class="grid"/>'
                       f'<text x="{left - 8}" y="{gy + 3.5:.1f}" class="ax" text-anchor="end">{esc(fmt(k * step))}</text>')
            k += 1
    else:
        out.append(f'<line x1="0" x2="{w}" y1="{y(0):.1f}" y2="{y(0):.1f}" class="grid"/>')
    for i, v in enumerate(values):
        x = left + i * bw
        t, tv = tips[i] if tips else (labels[i], fmt(v))
        g = [f'<rect x="{x:.1f}" y="0" width="{bw:.1f}" height="{h}" class="hit"/>']
        if v:
            bh = max(y(0) - y(v), 1.5)
            g.append(f'<path d="{bar_path(x + bw * .16, y(0) - bh, bw * .68, bh, min(4, bw * .2))}" '
                     f'class="{"bar hot" if i == hot else "bar"}"/>')
        if i == hot:
            g.append(f'<text x="{x + bw / 2:.1f}" y="{y(v) - 7:.1f}" class="val">{esc(fmt(v))}</text>')
        elif few and v:
            g.append(f'<text x="{x + bw / 2:.1f}" y="{y(v) - 7:.1f}" class="pv">{esc(fmt(v))}</text>')
        out.append(f'<g class="b"{tip(t, tv)}>{"".join(g)}</g>')
        if i % every == 0:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{h - 6}" class="ax">{esc(labels[i])}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart{" few" if few else ""}" role="img">{"".join(out)}</svg>'


def calendar(daily, start, end, key, fmt, busiest, w=840, blocks=1) -> str:
    """One square per day, weeks as columns (Monday on top), shaded by quartile of the active days.
    `blocks` > 1 stacks the weeks in several rows, so a phone gets bigger squares."""
    by = {d["day"]: d for d in daily}
    active = sorted(d[key] for d in daily if d[key] > 0)
    cuts = [active[min(len(active) - 1, int(len(active) * k / 4))] for k in (1, 2, 3)] if active else []
    first = start - timedelta(start.weekday())
    weeks = (end - first).days // 7 + 1
    per = math.ceil(weeks / blocks)
    left, head = 30, 18
    pitch = min(18.0, (w - left) / per)
    cell, block_h = pitch * .8, head + 7 * pitch + 10
    out = []
    for b in range(blocks):
        oy = b * block_h
        for r, name in ((0, "Mon"), (2, "Wed"), (4, "Fri")):
            out.append(f'<text x="{left - 8}" y="{oy + head + r * pitch + cell * .78:.1f}" class="ax" '
                       f'text-anchor="end">{name}</text>')
        marks = []                     # (column, month label) where a month starts
        for c in range(per):
            wk = b * per + c
            if wk >= weeks:
                break
            for r in range(7):
                d = first + timedelta(wk * 7 + r)
                if d < start or d > end:
                    continue
                if d.day == 1 or (c == 0 and not marks):
                    marks.append((c, f"{d:%b}"))
                v = by.get(d, {})
                n = v.get(key, 0)
                lvl = "hot" if d == busiest else f"h{1 + sum(n > q for q in cuts)}" if n > 0 else "h0"
                if n > 0:
                    val = (f'{usd(v["usd"])} · ' if key == "usd" else "") + f'{big(v["tokens"])} tokens'
                    if v.get("prompts"):
                        val += f' · {v["prompts"]} prompt{"s" if v["prompts"] != 1 else ""}'
                else:
                    val = "no activity"
                out.append(f'<rect x="{left + c * pitch:.1f}" y="{oy + head + r * pitch:.1f}" width="{cell:.1f}" '
                           f'height="{cell:.1f}" rx="{cell * .22:.1f}" class="d {lvl}"'
                           f'{tip(f"{d:%a} " + day(d), val)}/>')
        marks = [m for i, m in enumerate(marks) if i + 1 >= len(marks) or marks[i + 1][0] - m[0] >= 3]
        out += [f'<text x="{left + c * pitch:.1f}" y="{oy + 11}" class="ax" text-anchor="start">{m}</text>'
                for c, m in marks]
    vw = left + per * pitch
    vh = blocks * block_h - 10
    return (f'<svg viewBox="0 0 {vw:.0f} {vh:.0f}" class="cal" style="max-width:{vw:.0f}px" '
            f'role="img">{"".join(out)}</svg>')


def meter_rows(rows) -> str:
    """rows: (label, value text, share 0-1, optional secondary text, optional hover text)."""
    out = []
    for lbl, val, share, *extra in rows:
        sec = f'<span class="mt">{esc(extra[0])}</span>' if extra and extra[0] else ""
        hover = tip(lbl, extra[1]) if len(extra) > 1 and extra[1] else ""
        out.append(f'<div class="mrow{" has-mt" if sec else ""}"{hover}><span class="mn">{esc(lbl)}</span>'
                   f'<span class="mbar"><i style="width:{max(share, .015) * 100:.1f}%"></i></span>'
                   f'<span class="mv">{esc(val)}</span>{sec}</div>')
    return "".join(out)


def pct(x: float) -> str:
    return "&lt;0.1" if 0 < x < .001 else f"{x * 100:.1f}"


def mix_bar(t: dict) -> str:
    """Token composition as one segmented bar plus legend."""
    total = t["total"] or 1
    parts = [("Cache read", t["cache_read"], "c1"), ("Cache write", t["cache_write"], "c2"),
             ("Output", t["output"], "c3"), ("Input", t["input"], "c4")]
    segs = "".join(f'<i class="{c}" style="width:{v / total * 100:.3f}%"'
                   f'{tip(lbl, f"{v:,} tokens · {html.unescape(pct(v / total))}%")}></i>'
                   for lbl, v, c in parts if v)
    leg = "".join(f'<div class="li"><b class="{c}"></b><span>{lbl}</span>'
                  f'<strong>{big(v)}</strong><em>{pct(v / total)}%</em></div>'
                  for lbl, v, c in parts)
    return f'<div class="mix">{segs}</div><div class="leg">{leg}</div>'


def span_title(start, end) -> str:
    """'Eleven months' / '23 days' - the cover headline."""
    days = (end - start).days + 1
    if days < 45:
        return f"{WORDS[days] if days < len(WORDS) else days} day{'s' if days != 1 else ''}"
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    return f"{WORDS[months] if months < len(WORDS) else months} months"


def render(s: dict) -> str:
    p, t = s["period"], s["tokens"]
    priced = s["api_usd"] > 0
    key = "usd" if priced else "tokens"
    vfmt = usd if priced else big

    def amount(x) -> str:        # hover text for anything with tokens (and maybe a cost)
        return (f'{usd(x["usd"])} · ' if priced else "") + f'{big(x["tokens"])} tokens'

    def plural(n, one, many=None) -> str:
        return f"{n:,} {one if n == 1 else many or one + 's'}"

    # timeline: daily bars for short periods, monthly otherwise
    short = (p["end"] - p["start"]).days <= 62
    if short:
        span = [p["start"] + timedelta(i) for i in range((p["end"] - p["start"]).days + 1)]
        by = {d["day"]: d for d in s["daily"]}
        rows = [by.get(d, {"tokens": 0, "usd": 0.0, "prompts": 0}) for d in span]
        vals = [r[key] for r in rows]
        labels, hot, every = [str(d.day) for d in span], span.index(s["busiest_day"]["day"]), max(1, len(span) // 12)
        tips = [(f"{d:%a} {short_day(d)}",
                 amount(r) + (f' · {plural(r["prompts"], "prompt")}' if r["prompts"] else "") if r["tokens"]
                 else "no activity") for d, r in zip(span, rows)]
        timeline_title = "Day by day"
        timeline_sub = "per day; the busiest one highlighted."
    else:
        vals = [m[key] for m in s["months"]]
        firsts = [date(int(m["month"][:4]), int(m["month"][5:]), 1) for m in s["months"]]
        labels = [f"{d:%b}" for d in firsts]
        tips = [(f"{d:%B %Y}", amount(m)) for d, m in zip(firsts, s["months"])]
        hot, every = vals.index(max(vals)), 1
        timeline_title = "Month by month"
        timeline_sub = "per month; the busiest one highlighted."

    # two sizes of the same chart: SVG text scales with the viewBox, so a phone gets its own
    timeline = (bars(vals, labels, hot=hot, fmt=vfmt, every=every, grid=True, tips=tips)
                .replace('class="chart', 'class="wide chart', 1)
                + bars(vals, labels, w=420, h=200, hot=hot, fmt=vfmt, every=every * 2, grid=True, tips=tips)
                .replace('class="chart', 'class="narrow chart', 1))

    days_section = ""
    if not short:
        def cal(**kw):
            return calendar(s["daily"], p["start"], p["end"], key, vfmt, s["busiest_day"]["day"], **kw)
        days_section = DAYS_SECTION.format(
            active=s["active_days"],
            total=(p["end"] - p["start"]).days + 1,
            what="cost" if priced else "tokens",
            cal=cal().replace('class="cal', 'class="wide cal', 1)
            + cal(w=420, blocks=2).replace('class="cal', 'class="narrow cal', 1))

    hp, wd = s["hours"], s["weekdays"]
    peak_hour = max(range(24), key=lambda h: hp[h])
    hours_svg = bars(hp, [f"{h:02d}" for h in range(24)], w=480, h=170, hot=peak_hour, every=3,
                     tips=[(f"{h:02d}:00 – {(h + 1) % 24:02d}:00", plural(hp[h], "prompt")) for h in range(24)])
    peak_wd = max(range(7), key=lambda i: wd[i])
    week_svg = bars(wd, [d[0] for d in DAYS], w=300, h=170, hot=peak_wd,
                    tips=[(FULL_DAYS[i], plural(wd[i], "prompt")) for i in range(7)])

    total_model = sum(m[key] for m in s["models"]) or 1
    # an unpriced model shows its tokens, never "$0.00" (that would read as "free")
    models = meter_rows((model_name(m["model"]),
                         big(m["tokens"]) + " tok" if not priced or m["model"] in s["unpriced"] else usd(m["usd"]),
                         m[key] / total_model,
                         f'{big(m["tokens"])} tok' if priced and m["model"] not in s["unpriced"] else "",
                         (amount(m) if m["model"] not in s["unpriced"] else f'{big(m["tokens"])} tokens, no price')
                         + f' · {plural(m["messages"], "reply", "replies")}'
                         + f' · {m[key] / total_model:.0%} of the {"cost" if priced else "total"}')
                        for m in s["models"][:6])
    top_p = s["projects"][0][key] if s["projects"] else 1
    projects = meter_rows((x["name"], vfmt(x[key]), x[key] / (top_p or 1), "",
                           f'{amount(x)} · {plural(x["sessions"], "session")}') for x in s["projects"])
    top_t = s["tools"][0][1] if s["tools"] else 1
    tools = meter_rows((name, f"{n:,}", n / top_t, "",
                        f"{plural(n, 'call')} · {n / (s['tool_calls'] or 1):.0%} of all tool calls")
                       for name, n in s["tools"])

    arch = ""
    if s["archetype"]:
        title, why = s["archetype"]
        head, _, last = title.rpartition(" ")
        name = f'{esc(head)} <em>{esc(last)}</em>' if head else f"<em>{esc(last)}</em>"
        arch = (f'<section class="persona"><p class="kicker">Your Claude Code personality</p>'
                f'<h2>{name}</h2><p class="sub">{esc(why[:1].upper() + why[1:])}.</p></section>')

    ls, bd = s["longest_session"], s["busiest_day"]
    facts = [
        (short_day(bd["day"]), f'busiest day: {big(bd["tokens"])} tokens'
         + (f', {usd(bd["usd"])}' if priced else "")),
        (f'{s["streak"]["days"]} day{"s" if s["streak"]["days"] != 1 else ""}', "longest streak in a row"),
    ]
    if ls:
        facts.append((f'{ls["active_min"] / 60:.1f} h',
                      f'longest session, on {ls["project"]} ({short_day(ls["start"])})'))
    facts_html = "".join(f'<div class="stat"><div class="v">{esc(v)}</div><div class="l">{esc(l)}</div></div>'
                         for v, l in facts)

    unpriced = ""
    if s["unpriced"]:
        names = ", ".join(sorted(s["unpriced"]))
        unpriced = (f'<p class="warn">No price known for {esc(names)}: their tokens are counted, '
                    f'their cost is not. Pass <code>--prices</code> to add them.</p>')

    tiles = [(f'{s["active_days"]:,}', "active days"),
             (f'{s["prompts"]:,}', "prompts you typed"),
             (f'{s["tool_calls"]:,}', "tool calls by Claude (files, shell, web…)"),
             (f'{s["sessions"]:,}', "sessions"),
             (f'{s["active_hours"]:,.0f} h', "of active work, pauses left out")]
    tiles_html = "".join(f'<div class="tile"><div class="v">{v}</div><div class="l">{l}</div></div>'
                         for v, l in tiles)
    if priced:
        tiles_html = (f'<div class="tile hl"><div class="v">{usd(s["api_usd"])}</div>'
                      f'<div class="l">what this usage would cost at API list prices</div></div>') + tiles_html

    cache_line = f'Prompt caching served <b>{s["cache_hit_rate"]:.0%}</b> of the input'
    cache_line += (f' and saved about <b>{usd(s["cache_saved_usd"])}</b>.' if priced else ".")
    cache_line += (" Every turn re-sends the whole conversation, and the server reads it back from"
                   " the cache at a tenth of the price. That is why tokens run into the billions.")

    return TEMPLATE.format(
        fonts=font_faces(),
        css=CSS,
        script=SCRIPT,
        year=p["end"].year,
        headline=span_title(p["start"], p["end"]),
        period=f'{esc(short_day(p["start"]))} → {esc(day(p["end"]))}',
        active_days=s["active_days"],
        sessions=f'{s["sessions"]:,}',
        tokens=big(t["total"]),
        hit=f'{s["cache_hit_rate"]:.0%}',
        tiles=tiles_html,
        arch=arch,
        timeline_title=timeline_title,
        timeline_unit=("API-equivalent cost " if priced else "Tokens ") + timeline_sub,
        timeline=timeline,
        facts=facts_html,
        days=days_section,
        hours_svg=hours_svg,
        peak_hour=f"{peak_hour:02d}:00",
        week_svg=week_svg,
        peak_day=DAYS[peak_wd],
        mix=mix_bar(t),
        cache_line=cache_line,
        unpriced=unpriced,
        model_count=len(s["models"]),
        models=models,
        projects=projects,
        project_count=s["project_count"],
        tools=tools,
        prices_updated=PRICES_UPDATED,
    )


CSS = """
:root{--ink:#1d1b18;--mute:#6b665e;--line:#e8e4dc;--paper:#fdfcfa;--chip:#f2eee7;--acc:#c8603f;--acc-soft:#fbe3d8;
--c1:#2f4858;--c2:#c8603f;--c3:#e9b44c;--c4:#8aa39b;
--h0:#efebe4;--h1:#d3dce0;--h2:#9db0ba;--h3:#62808f;--h4:#2f4858;
--serif:Fraunces,Georgia,"Times New Roman",serif;--sans:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:"JetBrains Mono",ui-monospace,"Cascadia Mono",Consolas,monospace}
*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
html{color-scheme:light}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
main{max-width:880px;margin:0 auto;padding:64px 24px 40px}
section{padding:40px 0;border-top:1px solid var(--line)}
h1,h2,.v{font-family:var(--serif);font-weight:600;letter-spacing:-.02em}
h1 em,h2 em{font-style:normal;color:var(--acc)}
.kicker{margin:0 0 12px;font:500 11px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--acc)}
h2{font-size:30px;line-height:1.12;margin:0 0 6px}
h3{font:600 13px/1.3 var(--sans);margin:0 0 10px}
.sub{color:var(--mute);margin:0 0 22px;max-width:62ch}
.sub b{color:var(--ink);font-weight:600}
code{font:12.5px var(--mono);background:var(--chip);padding:1px 5px;border-radius:4px}
/* cover */
.cover{border-top:none;padding-top:0}
.top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:0 0 14px}
.top .kicker{margin:0}
.pdf{display:inline-flex;align-items:center;gap:7px;font:500 11px/1 var(--mono);letter-spacing:.1em;
text-transform:uppercase;color:var(--ink);background:#fff;border:1px solid var(--line);border-radius:999px;
padding:8px 13px 8px 11px;cursor:pointer;white-space:nowrap;flex:none;transition:border-color .15s,background .15s}
.pdf:hover{border-color:var(--ink)}
.pdf:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.pdf svg{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
/* tooltip */
.tip{position:fixed;left:0;top:0;z-index:10;pointer-events:none;opacity:0;transition:opacity .12s;
background:var(--ink);color:#fff;border-radius:9px;padding:8px 11px 8px;white-space:nowrap;
box-shadow:0 8px 24px #1d1b1833;font:600 13px/1.35 var(--sans);font-variant-numeric:tabular-nums}
.tip.show{opacity:1}
.tip b{display:block;font:500 10px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:#bdb5a8;margin-bottom:2px}
h1{font-size:clamp(46px,9vw,76px);line-height:.95;margin:0 0 18px}
.range{font:13px/1.5 var(--mono);color:var(--mute)}
.hero{margin-top:56px}
.hero .v{font-size:clamp(80px,17vw,132px);line-height:.9}
.hero .l{color:var(--mute);margin-top:10px}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:44px}
.tile{border:1px solid var(--line);border-radius:14px;padding:16px 18px 15px;background:#fff}
.tile .v{font-size:32px;line-height:1.05}
.tile .l{font-size:12.5px;line-height:1.4;color:var(--mute);margin-top:7px}
.tile.hl{background:var(--acc);border-color:var(--acc);color:#fff}
.tile.hl .l{color:var(--acc-soft)}
/* personality */
.persona h2{font-size:clamp(40px,7vw,58px);line-height:1;margin:2px 0 12px}
.persona .sub{font-size:17px;margin:0}
/* charts */
.chart{display:block;width:100%;height:auto;margin:4px 0 0;overflow:visible}
.chart .grid{stroke:var(--line)}
.chart .ax{font:10px var(--mono);fill:var(--mute);text-anchor:middle}
.chart .val{font:600 12px var(--sans);fill:var(--ink);text-anchor:middle}
.chart .bar{fill:var(--c1);transition:opacity .15s}
.chart .bar.hot{fill:var(--acc)}
.chart .hit{fill:transparent}
.chart .pv{display:none;font:500 10px var(--mono);fill:var(--mute);text-anchor:middle}
.chart:has(.b.on) .bar{opacity:.32}
.chart .b.on .bar{opacity:1}
[data-t]{cursor:default}
/* calendar */
.cal{display:block;width:100%;height:auto;margin:6px 0 0;overflow:visible}
.cal .ax{font:10px var(--mono);fill:var(--mute)}
.cal .d{stroke:transparent;stroke-width:1.5}
.cal .d.on{stroke:var(--ink)}
.h0{fill:var(--h0);background:var(--h0)}.h1{fill:var(--h1);background:var(--h1)}
.h2{fill:var(--h2);background:var(--h2)}.h3{fill:var(--h3);background:var(--h3)}
.h4{fill:var(--h4);background:var(--h4)}.cal .hot,.calleg .hot{fill:var(--acc);background:var(--acc)}
.calleg{display:flex;align-items:center;gap:4px;margin-top:14px;font:11px var(--mono);color:var(--mute)}
.calleg i{width:11px;height:11px;border-radius:3px;display:inline-block}
.calleg span{margin:0 6px}.calleg span:first-child{margin-left:0}
.calleg .gap{flex:1}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:0 24px;margin-top:22px}
.stat{border-top:1px solid var(--line);padding:12px 0 0}
.stat .v{font-size:26px;line-height:1.1}
.stat .l{font-size:12.5px;color:var(--mute);margin-top:3px}
.two{display:grid;grid-template-columns:8fr 5fr;gap:48px}
.two.even{grid-template-columns:1fr 1fr}
.two>section{border-top:none;padding:0}
.pair{border-top:1px solid var(--line);padding:40px 0}
/* tokens */
.mix{display:flex;height:24px;border-radius:7px;overflow:hidden;gap:2px;background:var(--paper)}
.mix i{display:block;height:100%;transition:opacity .15s}
.mix:has(.on) i:not(.on){opacity:.35}
.c1{background:var(--c1)}.c2{background:var(--c2)}.c3{background:var(--c3)}.c4{background:var(--c4)}
.leg{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:16px 0 20px}
.li{display:grid;grid-template-columns:auto 1fr;column-gap:8px;align-items:baseline}
.li b{width:9px;height:9px;border-radius:2px;display:inline-block}
.li span{font-size:12.5px;color:var(--mute)}
.li strong{grid-column:2;font:600 22px/1.15 var(--serif);letter-spacing:-.02em}
.li em{grid-column:2;font:11px var(--mono);font-style:normal;color:var(--mute)}
.note{font-size:13.5px;color:var(--mute);margin:0;max-width:66ch}
.note b{color:var(--ink);font-weight:600}
.warn{font-size:13.5px;color:#8a4a1c;background:#fdf1e7;border-radius:8px;padding:10px 12px;margin:14px 0 0}
/* meters */
.mrow{display:grid;grid-template-columns:minmax(80px,140px) 1fr 64px;align-items:center;gap:12px;padding:6px 8px;margin:0 -8px;border-radius:8px;font-size:14px;transition:background .15s}
.mrow.on{background:var(--chip)}
.mrow.has-mt{grid-template-columns:minmax(80px,140px) 1fr 64px 64px}
.mn{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mv{text-align:right;font-weight:600;font-variant-numeric:tabular-nums}
.mt{text-align:right;font:11px var(--mono);color:var(--mute)}
.mbar{height:8px;background:var(--chip);border-radius:99px;overflow:hidden}
.mbar i{display:block;height:100%;background:var(--c1);border-radius:99px}
.mrow:first-of-type .mbar i{background:var(--acc)}
.narrow{display:none}
.two .mrow{grid-template-columns:minmax(70px,110px) 1fr 58px}
/* footer */
footer{border-top:1.5px solid var(--ink);padding-top:14px;display:flex;justify-content:space-between;gap:24px;
font:11px/1.6 var(--mono);color:var(--mute)}
footer p{margin:0;max-width:60ch}
footer code{font-size:11px}
@media (max-width:680px){
  main{padding:40px 16px 32px}
  .tiles{grid-template-columns:1fr 1fr}
  .pdf .lg{display:none}
  .stats{grid-template-columns:1fr;gap:12px}
  .two,.two.even{grid-template-columns:1fr;gap:40px}
  .leg{grid-template-columns:1fr 1fr}
  footer{flex-direction:column}
  .wide{display:none}.narrow{display:block}
  .mrow.has-mt{grid-template-columns:minmax(70px,110px) 1fr 58px}.mt{display:none}
  .two .chart{max-width:420px}
}
@page{size:A4;margin:13mm 12mm}
@media print{
  body{background:#fff;font-size:13.5px}
  main{max-width:none;padding:0;zoom:.9}
  .pdf,.tip{display:none!important}
  .wide{display:block!important}.narrow{display:none!important}
  .chart.few .pv{display:inline}
  section{padding:26px 0}.pair{padding:26px 0}
  .hero{margin-top:36px}.tiles{margin-top:30px}
  .tile{background:#fff}
  section,.pair,.stats,.tiles,.mrow,.leg{break-inside:avoid}
  h2,.kicker{break-after:avoid}
}
"""

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude Code Wrapped {year}</title>
<style>{fonts}
{css}</style></head>
<body><main>

<section class="cover">
  <div class="top"><p class="kicker">Claude Code · Wrapped {year}</p>
    <button class="pdf" type="button" title="Save this report as a PDF"><svg viewBox="0 0 16 16"><path d="M8 2v8M4.5 6.5 8 10l3.5-3.5M3 13.5h10"/></svg><span class="lg">Save as </span>PDF</button></div>
  <h1>{headline}<br>of <em>code</em>,<br>for four hands.</h1>
  <div class="range">{period} · {active_days} active days · {sessions} sessions</div>
  <div class="hero">
    <div class="v">{tokens}</div>
    <div class="l">tokens processed, {hit} of the input read from the cache</div>
  </div>
  <div class="tiles">{tiles}</div>
</section>

{arch}

<section>
  <p class="kicker">Rhythm</p>
  <h2>{timeline_title}</h2>
  <p class="sub">{timeline_unit}</p>
  {timeline}
  <div class="stats">{facts}</div>
</section>
{days}

<div class="pair two">
  <section><p class="kicker">Clock</p><h2>Peak hour {peak_hour}</h2><p class="sub">When you type your prompts.</p>{hours_svg}</section>
  <section><p class="kicker">Week</p><h2>Mostly on {peak_day}</h2><p class="sub">Prompts by weekday.</p>{week_svg}</section>
</div>

<section>
  <p class="kicker">Under the hood</p>
  <h2>Where the tokens went</h2>
  {mix}
  <p class="note">{cache_line}</p>
  {unpriced}
</section>

<section>
  <p class="kicker">Models · {model_count} used</p>
  <h2>Who you worked with</h2>
  {models}
</section>

<div class="pair two even">
  <section><p class="kicker">Projects · {project_count} total</p><h2>Top projects</h2>{projects}</section>
  <section><p class="kicker">Tools</p><h2>What Claude reached for</h2>{tools}</section>
</div>

<footer>
  <p>Generated locally from <code>~/.claude/projects</code>. Nothing left your machine.
  Costs are API list prices ({prices_updated}); subscriptions are billed differently.</p>
  <p>Claude Code Wrapped<br>Unofficial, not affiliated with Anthropic.</p>
</footer>
</main>
<script>{script}</script>
</body></html>
"""

DAYS_SECTION = """
<section>
  <p class="kicker">Calendar</p>
  <h2>{active} of {total} days</h2>
  <p class="sub">One square per day, darker when the {what} was higher. Hover a day to read it.</p>
  {cal}
  <div class="calleg"><span>Less</span><i class="h0"></i><i class="h1"></i><i class="h2"></i><i class="h3"></i><i class="h4"></i><span>More</span><b class="gap"></b><i class="hot"></i><span>busiest day</span></div>
</section>
"""

# Tooltip for every [data-t] element (bars, calendar days, meters) and the PDF button.
# Plain DOM, no network; the report still works without it (numbers stay in the page).
SCRIPT = """
(function () {
  var tip = document.createElement("div"), t = document.createElement("b"), v = document.createElement("span");
  tip.className = "tip"; tip.setAttribute("role", "tooltip"); tip.append(t, v); document.body.append(tip);
  var on = null;
  function hide() { if (on) on.classList.remove("on"); on = null; tip.classList.remove("show"); }
  function move(e) {
    var el = e.target.closest && e.target.closest("[data-t]");
    if (!el) return hide();
    if (el !== on) {
      hide(); on = el; el.classList.add("on");
      t.textContent = el.getAttribute("data-t"); v.textContent = el.getAttribute("data-v") || "";
      tip.classList.add("show");
    }
    var w = tip.offsetWidth, h = tip.offsetHeight, x = e.clientX + 14, y = e.clientY - h - 14;
    if (x + w > innerWidth - 8) x = Math.max(8, e.clientX - w - 14);
    if (y < 8) y = e.clientY + 20;
    tip.style.transform = "translate(" + x + "px," + y + "px)";
  }
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerdown", move);
  document.documentElement.addEventListener("pointerleave", hide);
  addEventListener("scroll", hide, { passive: true });
  addEventListener("beforeprint", hide);
  document.querySelector(".pdf").addEventListener("click", function () { hide(); print(); });
})();
"""
