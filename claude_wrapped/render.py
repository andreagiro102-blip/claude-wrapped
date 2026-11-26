"""Render the stats as one self-contained HTML file (inline CSS + SVG, no network)."""
from __future__ import annotations

import html
import re

from .pricing import PRICES_UPDATED

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def esc(x) -> str:
    return html.escape(str(x))


def big(n: float) -> str:
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            v = n / div
            return f"{v:.1f}{suf}" if v < 100 else f"{v:.0f}{suf}"
    return f"{n:.0f}"


def usd(x: float) -> str:
    return f"${x:,.0f}" if x >= 10 else f"${x:,.2f}"


def model_name(m: str) -> str:
    base = re.sub(r"-\d{8}$", "", m)
    hit = re.match(r"claude-([a-z]+)-([\d-]+)$", base)
    return f"{hit[1].title()} {hit[2].replace('-', '.')}" if hit else base


def day(d) -> str:
    return f"{d:%b} {d.day}, {d.year}"     # "%-d" is not portable (fails on Windows)


def bars(values, labels, w=640, h=170, hot=None, fmt=None, every=1) -> str:
    """Vertical bar chart. `hot` = index to highlight, `every` = label every Nth bar."""
    if not values:
        return ""
    top, bottom = 22, 22
    mx = max(values) or 1
    bw = w / len(values)
    out = []
    for i, v in enumerate(values):
        bh = (h - top - bottom) * v / mx
        x, y = i * bw + bw * 0.15, h - bottom - bh
        cls = "bar hot" if i == hot else "bar"
        if v:
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * .7:.1f}" height="{max(bh, 1.5):.1f}" rx="2" class="{cls}"/>')
        else:
            out.append(f'<rect x="{x:.1f}" y="{h - bottom - 1.5:.1f}" width="{bw * .7:.1f}" height="1.5" class="off"/>')
        if i == hot and fmt:
            out.append(f'<text x="{x + bw * .35:.1f}" y="{y - 6:.1f}" class="val">{esc(fmt(v))}</text>')
        if i % every == 0:
            out.append(f'<text x="{x + bw * .35:.1f}" y="{h - 6}" class="ax">{esc(labels[i])}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">{"".join(out)}</svg>'


def meter_rows(rows) -> str:
    """rows: (label, value text, share 0-1)."""
    return "".join(
        f'<div class="row"><span class="lbl">{esc(lbl)}</span>'
        f'<span class="track"><span class="fill" style="width:{max(share, .01) * 100:.1f}%"></span></span>'
        f'<span class="num">{esc(val)}</span></div>' for lbl, val, share in rows)


def render(s: dict) -> str:
    p, t = s["period"], s["tokens"]
    priced = s["api_usd"] > 0

    # timeline: daily bars for short periods, monthly otherwise
    daily = s["daily"]
    if (p["end"] - p["start"]).days <= 62:
        from datetime import timedelta
        span = [p["start"] + timedelta(i) for i in range((p["end"] - p["start"]).days + 1)]
        by = {d["day"]: d for d in daily}
        key = "usd" if priced else "tokens"
        vals = [by.get(d, {}).get(key, 0) for d in span]
        hot = span.index(s["busiest_day"]["day"])
        timeline = bars(vals, [d.strftime("%d") for d in span], hot=hot,
                        fmt=usd if priced else big, every=max(1, len(span) // 10))
        timeline_title = "Day by day"
    else:
        key = "usd" if priced else "tokens"
        vals = [m[key] for m in s["months"]]
        timeline = bars(vals, [m["month"] for m in s["months"]], hot=vals.index(max(vals)),
                        fmt=usd if priced else big)
        timeline_title = "Month by month"

    peak_hour = max(range(24), key=lambda h: s["hours"][h])
    hours_svg = bars(s["hours"], [f"{h:02d}" for h in range(24)], h=150, hot=peak_hour, every=3)
    peak_wd = max(range(7), key=lambda i: s["weekdays"][i])
    week_svg = bars(s["weekdays"], DAYS, w=360, h=150, hot=peak_wd)

    total_model = sum(m["usd"] if priced else m["tokens"] for m in s["models"]) or 1
    # an unpriced model shows its tokens, never "$0.00" (that would read as "free")
    models = meter_rows((model_name(m["model"]),
                         big(m["tokens"]) + " tok" if not priced or m["model"] in s["unpriced"] else usd(m["usd"]),
                         (m["usd"] if priced else m["tokens"]) / total_model) for m in s["models"][:6])
    top_p = s["projects"][0]["usd" if priced else "tokens"] if s["projects"] else 1
    projects = meter_rows((x["name"], usd(x["usd"]) if priced else big(x["tokens"]),
                           (x["usd"] if priced else x["tokens"]) / (top_p or 1)) for x in s["projects"])
    top_t = s["tools"][0][1] if s["tools"] else 1
    tools = meter_rows((name, f"{n:,}", n / top_t) for name, n in s["tools"])

    arch = ""
    if s["archetype"]:
        title, why = s["archetype"]
        arch = f'<section class="card arch"><p class="kicker">Your Claude Code personality</p><h2>{esc(title)}</h2><p>{esc(why)}</p></section>'

    ls = s["longest_session"]
    longest = (f'<b>{ls["active_min"] / 60:.1f} h</b> of active work on <b>{esc(ls["project"])}</b>, {esc(day(ls["start"]))}'
               if ls else "—")
    bd = s["busiest_day"]
    unpriced = ""
    if s["unpriced"]:
        names = ", ".join(sorted(s["unpriced"]))
        unpriced = f'<p class="warn">No price known for: {esc(names)} — their tokens are counted, their cost is not. Pass <code>--prices</code> to add them.</p>'

    hero_money = (f'<div class="stat"><b>{usd(s["api_usd"])}</b><span>API-equivalent cost</span></div>'
                  if priced else "")
    cache_line = (f'Prompt caching served <b>{s["cache_hit_rate"]:.0%}</b> of the input and saved about <b>{usd(s["cache_saved_usd"])}</b>.'
                  if priced else f'Prompt caching served <b>{s["cache_hit_rate"]:.0%}</b> of the input.')

    return TEMPLATE.format(
        css=CSS,
        period=f'{esc(day(p["start"]))} – {esc(day(p["end"]))}',
        tokens=big(t["total"]),
        hero_money=hero_money,
        active_days=s["active_days"],
        prompts=f'{s["prompts"]:,}',
        tool_calls=f'{s["tool_calls"]:,}',
        sessions=f'{s["sessions"]:,}',
        hours=f'{s["active_hours"]:,.0f}',
        arch=arch,
        timeline_title=timeline_title,
        timeline=timeline,
        busiest=f'Busiest day: <b>{esc(day(bd["day"]))}</b> — {big(bd["tokens"])} tokens'
                + (f', {usd(bd["usd"])}' if priced else ""),
        streak=s["streak"]["days"],
        longest=longest,
        hours_svg=hours_svg,
        peak_hour=f"{peak_hour:02d}:00",
        week_svg=week_svg,
        peak_day=DAYS[peak_wd],
        t_in=big(t["input"]), t_out=big(t["output"]), t_cr=big(t["cache_read"]), t_cw=big(t["cache_write"]),
        cache_line=cache_line,
        models=models,
        projects=projects,
        project_count=s["project_count"],
        tools=tools,
        unpriced=unpriced,
        prices_updated=PRICES_UPDATED,
    )


CSS = """
:root{--bg:#100e17;--card:#1a1724;--line:#2c2839;--ink:#f3eff8;--dim:#a69fb8;--a:#ff8a5c;--b:#b28cff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:40px 16px 64px;display:grid;gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:26px}
.hero{background:radial-gradient(120% 140% at 0% 0%,#3a1f4f 0%,#1a1724 55%),var(--card);padding:40px 26px}
.kicker{margin:0;color:var(--dim);font-size:13px;letter-spacing:.12em;text-transform:uppercase}
h1{margin:6px 0 2px;font-size:clamp(34px,7vw,54px);line-height:1.05;letter-spacing:-.02em}
h2{margin:4px 0 14px;font-size:24px;letter-spacing:-.01em}
.huge{font-size:clamp(64px,16vw,120px);font-weight:800;line-height:1;letter-spacing:-.04em;margin:26px 0 0;
  background:linear-gradient(90deg,var(--a),var(--b));-webkit-background-clip:text;background-clip:text;color:transparent}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-top:24px}
.stat{background:#0003;border-radius:14px;padding:14px}
.stat b{display:block;font-size:26px;letter-spacing:-.02em}
.stat span{color:var(--dim);font-size:13px}
.arch{border-color:var(--a);background:linear-gradient(135deg,#3a2216,#1a1724 70%)}
.arch h2{font-size:34px;margin-bottom:6px}
.arch p:last-child{margin:0;color:var(--dim)}
.two{display:grid;grid-template-columns:1.6fr 1fr;gap:18px}
@media (max-width:640px){.two{grid-template-columns:1fr}}
.chart{width:100%;height:auto;display:block;margin:6px 0 10px}
.bar{fill:var(--b);opacity:.75}.bar.hot{fill:var(--a);opacity:1}.off{fill:var(--line)}
.ax{fill:var(--dim);font-size:11px;text-anchor:middle}.val{fill:var(--ink);font-size:12px;font-weight:700;text-anchor:middle}
.note{color:var(--dim);margin:0}.note b{color:var(--ink)}
.row{display:grid;grid-template-columns:minmax(90px,1.1fr) 2fr auto;gap:12px;align-items:center;margin:9px 0}
.lbl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{height:10px;border-radius:5px;background:#0005;overflow:hidden}
.fill{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,var(--b),var(--a))}
.num{font-variant-numeric:tabular-nums;color:var(--dim);font-size:14px}
.tok{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
@media (max-width:520px){.tok{grid-template-columns:repeat(2,1fr)}}
.warn{color:#ffb86b;font-size:14px}
footer{color:var(--dim);font-size:13px;text-align:center;line-height:1.6}
code{background:#0005;padding:1px 5px;border-radius:4px}
@media print{body{background:#fff}.card{break-inside:avoid}}
"""

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude Code Wrapped</title><style>{css}</style></head>
<body><main>

<section class="card hero">
  <p class="kicker">{period}</p>
  <h1>Your Claude Code Wrapped</h1>
  <p class="huge">{tokens}</p>
  <p class="note">tokens processed</p>
  <div class="grid">
    {hero_money}
    <div class="stat"><b>{active_days}</b><span>active days</span></div>
    <div class="stat"><b>{prompts}</b><span>prompts you typed</span></div>
    <div class="stat"><b>{tool_calls}</b><span>tool calls by Claude</span></div>
    <div class="stat"><b>{sessions}</b><span>sessions</span></div>
    <div class="stat"><b>{hours}</b><span>hours of active work</span></div>
  </div>
</section>

{arch}

<section class="card">
  <p class="kicker">Rhythm</p><h2>{timeline_title}</h2>
  {timeline}
  <p class="note">{busiest}</p>
  <p class="note">Longest streak: <b>{streak} days</b> in a row · Longest session: {longest}</p>
</section>

<div class="two">
  <section class="card"><p class="kicker">Clock</p><h2>Peak hour: {peak_hour}</h2>{hours_svg}</section>
  <section class="card"><p class="kicker">Week</p><h2>Favourite day: {peak_day}</h2>{week_svg}</section>
</div>

<section class="card">
  <p class="kicker">Under the hood</p><h2>Where the tokens went</h2>
  <div class="tok">
    <div class="stat"><b>{t_in}</b><span>input</span></div>
    <div class="stat"><b>{t_out}</b><span>output</span></div>
    <div class="stat"><b>{t_cr}</b><span>cache read</span></div>
    <div class="stat"><b>{t_cw}</b><span>cache write</span></div>
  </div>
  <p class="note">{cache_line}</p>
  {unpriced}
</section>

<section class="card"><p class="kicker">Models</p><h2>Who you worked with</h2>{models}</section>

<div class="two">
  <section class="card"><p class="kicker">Projects · {project_count} total</p><h2>Top projects</h2>{projects}</section>
  <section class="card"><p class="kicker">Tools</p><h2>What Claude reached for</h2>{tools}</section>
</div>

<footer>
  Generated locally from <code>~/.claude/projects</code> — nothing left your machine.<br>
  Costs are what the same usage would cost at API list prices ({prices_updated}); subscriptions are billed differently.<br>
  Unofficial tool, not affiliated with Anthropic.
</footer>
</main></body></html>
"""
