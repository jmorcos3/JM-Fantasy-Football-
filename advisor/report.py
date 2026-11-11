"""Renders the advice as one self-contained HTML page (no external data calls)."""
from html import escape as e

CSS = """
/* layout: one column of dense decision tables per league, league switcher on top */
:root{--bg:#f3f5f2;--panel:#ffffff;--ink:#16211b;--muted:#5d6b63;--line:#d9dfd9;--accent:#0f6b4a;--accent-soft:#dcefe6;
--good:#11734b;--bad:#b3372c;--warn:#8a5a00;--warn-soft:#fbefcf;--bad-soft:#f8dedb;
--display:"Space Grotesk",system-ui,sans-serif;--body:"Inter",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0e1512;--panel:#16201b;--ink:#e6ede8;--muted:#93a39a;--line:#28362f;--accent:#4fd0a0;--accent-soft:#17352a;
--good:#5cd6a4;--bad:#ff8f84;--warn:#f0c060;--warn-soft:#3a2f12;--bad-soft:#41201d;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0e1512;--panel:#16201b;--ink:#e6ede8;--muted:#93a39a;--line:#28362f;--accent:#4fd0a0;--accent-soft:#17352a;
--good:#5cd6a4;--bad:#ff8f84;--warn:#f0c060;--warn-soft:#3a2f12;--bad-soft:#41201d;color-scheme:dark}
[hidden]{display:none!important}
body{background:var(--bg);color:var(--ink);font:14px/1.45 var(--body);margin:0}
.wrap{max-width:1040px;margin:0 auto;padding-block:20px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:flex;flex-direction:column;gap:20px}
h1,h2{font-family:var(--display);margin:0;text-wrap:balance}h1{font-size:24px}h2{font-size:17px}
.sub{color:var(--muted);font-size:13px}
.tabs{display:flex;gap:8px;flex-wrap:wrap}
.tabs button{font:600 13px var(--body);padding:8px 14px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:999px;cursor:pointer}
.tabs button[aria-selected="true"]{background:var(--accent);border-color:var(--accent);color:var(--bg)}
.tabs button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.league{display:flex;flex-direction:column;gap:20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.kpi{background:var(--panel);padding:12px 14px;min-width:0}.kpi b{display:block;font:600 20px var(--display);font-variant-numeric:tabular-nums}
.kpi span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}
section{display:flex;flex-direction:column;gap:8px;min-width:0}
.scroll{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);text-align:left;font-weight:600}
th,td{padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap}tr:last-child td{border-bottom:0}
td.n,th.n{text-align:right}td.wrapc{white-space:normal;min-width:150px}
.p{font-weight:600}.m{color:var(--muted);font-size:12px}
.pill{display:inline-block;font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--accent-soft);color:var(--accent)}
.pill.w{background:var(--warn-soft);color:var(--warn)}.pill.b{background:var(--bad-soft);color:var(--bad)}
.up{color:var(--good)}.dn{color:var(--bad)}
.alert{background:var(--warn-soft);color:var(--warn);border-radius:10px;padding:10px 14px;font-weight:600}
.trades{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.trade{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:6px;min-width:0}
.trade .lab{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.me td{background:var(--accent-soft)}
footer{color:var(--muted);font-size:12px;max-width:70ch}
"""
JS = """
document.querySelectorAll('.tabs button').forEach(function(b){b.addEventListener('click',function(){
document.querySelectorAll('.tabs button').forEach(function(x){x.setAttribute('aria-selected',x===b)});
document.querySelectorAll('.league').forEach(function(l){l.hidden=l.id!==b.dataset.t});
try{localStorage.setItem('ff-tab',b.dataset.t)}catch(_){}});});
try{var t=localStorage.getItem('ff-tab');var b=t&&document.querySelector('.tabs button[data-t="'+t+'"]');if(b)b.click()}catch(_){}
"""


def sign(v, unit=""):
    if v is None:
        return '<span class="m">–</span>'
    c = "up" if v > 0.05 else ("dn" if v < -0.05 else "m")
    return f'<span class="{c}">{v:+.1f}{unit}</span>'


def who(r):
    inj = f' <span class="pill b">{e(r["inj"])}</span>' if r.get("inj") else ""
    return f'<span class="p">{e(r["name"])}</span>{inj}<br><span class="m">{e(str(r.get("pos") or ""))} · {e(str(r.get("team") or ""))}</span>'


def game(r):
    if not r.get("opp"):
        return '<span class="m">bye / no game</span>'
    tot = f'<br><span class="m">team total {r["implied"]}</span>' if r.get("implied") else ""
    return f'{"vs" if r.get("home") else "@"} {e(r["opp"])}{tot}'


def table(head, rows, cls=None):
    th = "".join(f'<th class="{"n" if h.startswith(">") else ""}">{e(h.lstrip(">"))}</th>' for h in head)
    body = "".join(f'<tr class="{(cls[i] if cls else "")}">' + "".join(c for c in r) + "</tr>" for i, r in enumerate(rows))
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def td(v, n=False, wrap=False):
    return f'<td class="{"n" if n else ""}{" wrapc" if wrap else ""}">{v}</td>'


FLAG = {"swap": '<span class="pill w">Start — not in your lineup</span>', "coin": '<span class="pill">Coin flip</span>',
        "sit": '<span class="pill b">Sit</span>'}


def league(L, i):
    if L.get("error"):
        return f'<div class="league" id="l{i}"><div class="alert">{e(L["error"])}</div></div>'
    h = [f'<div class="league" id="l{i}"{" hidden" if i else ""}>']
    if L.get("deadline") and L["trades_open"] and L["deadline"] - L["week"] <= 1:
        h.append(f'<div class="alert">Trade deadline is week {L["deadline"]}. Any trade below has to go out now.</div>')
    if not L["trades_open"]:
        h.append('<div class="alert">Trade deadline has passed in this league. Waivers are the only lever left.</div>')
    mu = L.get("matchup")
    k = [(L["record"], "Record"), (L["lineup"]["total"], f'Projected, week {L["week"]}')]
    if mu:
        k += [(mu["them"], f'Opponent: {e(mu["opp"])}'), (f'{round(mu["win"] * 100)}%', "Win probability")]
    if L.get("faab") is not None:
        k.append((f'${L["faab"]}', "FAAB left"))
    h.append('<div class="kpis">' + "".join(f'<div class="kpi"><b>{v}</b><span>{l}</span></div>' for v, l in k) + "</div>")

    rows = [[td(e(r["slot"])), td(who(r) if r.get("team") else f'<span class="p">{e(r["name"])}</span>'), td(game(r)),
             td(r["wk"], 1), td(sign(r.get("mkt")), 1), td(FLAG.get(r.get("change"), ""))] for r in L["lineup"]["starters"]]
    rows += [[td(e(r["slot"])), td(who(r)), td(game(r)), td(r["wk"], 1), td(sign(r.get("mkt")), 1), td(FLAG.get(r.get("change"), ""))]
             for r in L["lineup"]["bench"]]
    h.append(f'<section><h2>Optimal lineup, week {L["week"]}</h2><div class="sub">Starters first, then bench. Market column = shift from betting-market player props.</div>'
             + table(["Slot", "Player", "Game", ">Proj", ">Market", "Action"], rows) + "</section>")

    if L["waivers"]:
        rows = [[td(who(r) + (' <span class="pill w">Trending</span>' if r["hot"] else "")), td(e(r["kind"])), td(r["wk"], 1), td(r["ppg"], 1),
                 td(sign(r["d_ros"]), 1), td(sign(r["d_wk"]), 1), td(f'${r["bid"]}' if r["bid"] is not None else "–", 1),
                 td(e(r["drop"]) if r["drop"] else '<span class="m">open spot</span>')] for r in L["waivers"]]
        h.append('<section><h2>Waiver targets</h2><div class="sub">Ranked by points added to your best lineup: rest of season, then this week. Bid is a suggested FAAB amount.</div>'
                 + table(["Player", "Role", ">Wk proj", ">ROS / gm", ">ROS gain", ">Wk gain", ">Bid", "Drop"], rows) + "</section>")
    else:
        h.append('<section><h2>Waiver targets</h2><div class="sub">Nothing on the wire improves your lineup this week.</div></section>')

    if L["trades_open"]:
        cards = []
        for t in L["trades"]:
            side = lambda cs: "<br>".join(f'<span class="p">{e(c["name"])}</span> <span class="m">{e(c["pos"])} · {c["ppg"]}/gm</span>' for c in cs)
            cards.append(f'<div class="trade"><span class="lab">With {e(t["partner"])}</span><div><span class="lab">Give</span><br>{side(t["give"])}</div>'
                         f'<div><span class="lab">Get</span><br>{side(t["get"])}</div>'
                         f'<div class="m">Your lineup {sign(t["my_gain"], " pts ROS")} · theirs {sign(t["their_gain"], " pts")}</div></div>')
        h.append('<section><h2>Trade offers to send</h2><div class="sub">Each one raises your rest-of-season lineup and theirs, and is close to even on player value, so it has a real chance of being accepted.</div>'
                 + ('<div class="trades">' + "".join(cards) + "</div>" if cards else '<div class="sub">No mutually beneficial deals found this week.</div>') + "</section>")
        b = table(["Buy low", "Owner", ">Outlook / gm", ">Last 4 / gm"], [[td(who(r)), td(e(r["owner"]), wrap=True), td(r["ppg"], 1), td(r["recent"], 1)] for r in L["buy"]]) if L["buy"] else '<div class="sub">None.</div>'
        s = table(["Sell high", ">Outlook / gm", ">Last 4 / gm"], [[td(who(r)), td(r["ppg"], 1), td(r["recent"], 1)] for r in L["sell"]]) if L["sell"] else '<div class="sub">None on your roster.</div>'
        h.append(f'<div class="two"><section><h2>Buy low</h2><div class="sub">Other teams\' players producing below their outlook.</div>{b}</section>'
                 f'<section><h2>Sell high</h2><div class="sub">Your players running hot versus their outlook.</div>{s}</section></div>')

    if L["movers"]:
        rows = [[td(who(r)), td("Your roster" if r["mine"] else "Free agent"), td(r["base"], 1), td(r["wk"], 1), td(sign(r["mkt"]), 1)] for r in L["movers"]]
        h.append('<section><h2>Where the markets disagree</h2><div class="sub">Largest gaps between prediction-market props and the baseline projection, among your players and free agents.</div>'
                 + table(["Player", "Status", ">Baseline", ">Blended", ">Shift"], rows) + "</section>")

    rows = [[td(n + 1, 1), td(f'<span class="p">{e(p["name"])}</span>'), td(p["rec"]), td(p["pf"], 1), td(p["wk"], 1), td(p["ros"], 1),
             td(f'${p["faab"]}' if L.get("faab") is not None else "–", 1)] for n, p in enumerate(L["power"])]
    h.append('<section><h2>League power ranking</h2><div class="sub">Sorted by projected weekly points for the rest of the season.</div>'
             + table([">#", "Team", "Record", ">Points for", ">This week", ">ROS / wk", ">FAAB"], rows, ["me" if p["me"] else "" for p in L["power"]]) + "</section>")
    h.append("</div>")
    return "".join(h)


def fragment(out):
    tabs = "".join(f'<button role="tab" data-t="l{i}" aria-selected="{"true" if i == 0 else "false"}">{e(L.get("league") or "League")}'
                   f' <span style="font-weight:400">· {e(L.get("platform", ""))}</span></button>' for i, L in enumerate(out["leagues"]))
    notes = "".join(f'<div class="alert">{e(n)}</div>' for n in out["notes"])
    return (f'<title>Fantasy War Room</title><meta name="claude:viewport-fit-sides" content="cover">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600&display=swap">'
            f'<style>{CSS}</style><div class="wrap"><header><h1>Fantasy War Room</h1>'
            f'<div class="sub">{e(out["season"])} season · week {out["week"]} · updated {e(out["generated"].replace("T", " ")[:16])} UTC</div></header>'
            f'{notes}<div class="tabs" role="tablist">{tabs}</div>' + "".join(league(L, i) for i, L in enumerate(out["leagues"]))
            + '<footer>Projections: Rotowire weekly stat lines re-scored with each league\'s own rules, blended 50/50 with stat lines implied by Kalshi '
              'player-prop markets where a liquid market exists, and nudged toward the last four weeks of actual production for future weeks. '
              'Team totals are DraftKings lines. Trade and waiver gains are changes in your optimal-lineup points, net of what a free streamer would give you.</footer>'
            f'</div><script>{JS}</script>')


def render(out):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'</head><body>{fragment(out)}</body></html>')
