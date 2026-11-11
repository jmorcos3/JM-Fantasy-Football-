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
.slot{display:none;font:600 10px var(--body);letter-spacing:.05em;padding:2px 6px;border-radius:4px;background:var(--accent-soft);color:var(--accent);margin-right:6px;vertical-align:2px}
details.notes{color:var(--muted);font-size:12px}details.notes summary{cursor:pointer}details.notes li{margin-top:4px}
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);padding-block:8px;margin-block:-8px}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--bg)}
.steps{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.step{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:start;background:var(--panel);border:1px solid var(--accent);border-radius:10px;padding:12px 14px}
.num{font:600 15px var(--display);width:26px;height:26px;border-radius:50%;background:var(--accent);color:var(--bg);display:grid;place-items:center}
.step .body{display:flex;flex-direction:column;gap:8px;min-width:0}
.mv{display:grid;grid-template-columns:44px minmax(0,1fr);gap:8px;align-items:baseline}
.verb{font:600 11px var(--body);text-transform:uppercase;letter-spacing:.06em}
.add .verb{color:var(--good)}.drop .verb{color:var(--bad)}
.bidbox{text-align:right}.bidbox .lab{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600}.bidbox b{font:600 19px var(--display)}
.note{font-weight:400;font-size:12px;padding:8px 12px}
/* phone: every table row becomes a card, so no decision column is ever off-screen */
@media (max-width:680px){
h1{font-size:21px}
.tabs{flex-wrap:nowrap;overflow-x:auto;margin-inline:-16px;padding-inline:16px;scrollbar-width:none}.tabs::-webkit-scrollbar{display:none}
.tabs button{flex:none;padding:10px 14px}
.kpis{grid-template-columns:1fr 1fr}.kpi b{font-size:18px}
.scroll{overflow:visible;background:none;border:0;border-radius:0}
table,tbody{display:block}thead{display:none}
tr{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px 10px;align-items:start;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:6px}
tr.me{background:var(--accent-soft);border-color:var(--accent)}.me td{background:none}
td,td.n{display:block;padding:0;border:0;white-space:normal;text-align:left;min-width:0;font-size:13px}
td.wrapc{min-width:0}
td::before{content:attr(data-l);display:block;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
td.main{grid-column:1/span 3;grid-row:1;font-size:15px}td.main::before{display:none}
td.key{grid-column:4;grid-row:1;text-align:right;font:600 17px var(--display)}
td.wide{grid-column:1/-1}td.half{grid-column:span 2}
td.hide-m,td:empty,td:has(>span.nil:only-child){display:none}
.slot{display:inline-block}
.two{grid-template-columns:1fr}
}
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
        return '<span class="m nil">–</span>'
    c = "up" if v > 0.05 else ("dn" if v < -0.05 else "m")
    return f'<span class="{c}">{v:+.1f}{unit}</span>'


def who(r):
    inj = f' <span class="pill b">{e(r["inj"])}</span>' if r.get("inj") else ""
    return f'<span class="p">{e(r["name"])}</span>{inj}<br><span class="m">{e(str(r.get("pos") or ""))} · {e(str(r.get("team") or ""))}</span>'


def game(r):
    if not r.get("opp"):
        return '<span class="m">bye / no game</span>'
    tot = f' <span class="m">· team total {r["implied"]}</span>' if r.get("implied") else ""
    return f'{"vs" if r.get("home") else "@"} {e(r["opp"])}{tot}'


MAIN = {"Player", "Team", "Buy low", "Sell high", "Position"}
WIDE = {"Action", "Owner", "Best on waivers", "Verdict"}
KEY = {"League rank", "Proj", "Bid", "Playoff odds", "Outlook / gm", "Shift", "Snap share"}
HIDE = {"Slot", "#"}
HALF = {"Game", "Competition", "Would replace", "Status"}


def table(head, rows, cls=None):
    th = "".join(f'<th class="{"n" if h.startswith(">") else ""}">{e(h.lstrip(">"))}</th>' for h in head)
    def lab(c, h):
        name = h.lstrip(">")
        extra = next((f" {c}" for c, names in (("main", MAIN), ("wide", WIDE), ("key", KEY), ("hide-m", HIDE), ("half", HALF)) if name in names), "")
        return c.replace('<td class="', f'<td data-l="{e(name)}" class="{extra.strip()} ' if extra else f'<td data-l="{e(name)}" class="', 1)

    body = "".join(f'<tr class="{(cls[i] if cls else "")}">' + "".join(lab(c, h) for c, h in zip(r, head)) + "</tr>" for i, r in enumerate(rows))
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
    k.append((f'{round(L["playoff_odds"] * 100)}%', f'Playoff odds · avg seed {L["seed"]}'))
    ws = L.get("week_sim")
    if L.get("vp_rules") and ws:
        k += [(L["vp"], "Victory points"), (f'{ws["vp"]:.1f}', "Expected VP this week"),
              (f'{round(ws["top3"] * 100)}% / {round(ws["top6"] * 100)}%', "Top-3 / top-6 score odds")]
    if L["lineup"].get("any_bust") is not None:
        k.append((f'{round(L["lineup"]["any_bust"] * 100)}%', f'Chance a starter scores ≤{L["bust_rule"]["threshold"]} (beer)'))
    if L.get("faab") is not None:
        k.append((f'${L["faab"]}', "FAAB left"))
    h.append('<div class="kpis">' + "".join(f'<div class="kpi"><b>{v}</b><span>{l}</span></div>' for v, l in k) + "</div>")

    br = L.get("bust_rule")
    steps = []
    for n, r in enumerate(L.get("moves") or [], 1):
        bid = f'<span class="lab">Bid</span><b>${r["bid"]}</b>' if r["bid"] is not None else '<span class="lab">Claim</span><b>#{}</b>'.format(n)
        risk = f' <span class="pill b">{round(r["bust"] * 100)}% chance of ≤{br["threshold"]}</span>' if br and (r.get("bust") or 0) >= 0.08 else ""
        drop = (f'<div class="mv drop"><span class="verb">Drop</span><div><span class="p">{e(r["drop"])}</span><br><span class="m">{e(r["drop_why"])}</span></div></div>'
                if r["drop"] else '<div class="mv drop"><span class="verb">Drop</span><div><span class="p">No one</span><br><span class="m">you have an open roster spot</span></div></div>')
        steps.append(f'<li class="step"><div class="num">{n}</div><div class="body">'
                     f'<div class="mv add"><span class="verb">Add</span><div><span class="p">{e(r["name"])}</span> <span class="m">{e(r["pos"])} · {e(r["team"])}</span>{risk}'
                     f'<br><span class="m">{e(r["why"])}</span></div></div>{drop}'
                     + ('<div class="m">Then put him in your starting lineup.</div>' if r["starts"] else "") + f'</div><div class="bidbox">{bid}</div></li>')
    if steps:
        h.append('<section><h2>Moves to make</h2><div class="sub">Put these claims in, in this order. Each one already accounts for the moves above it.</div>'
                 f'<ol class="steps">{"".join(steps)}</ol></section>')
    else:
        h.append('<section><h2>Moves to make</h2><div class="sub">None. No free agent beats what you already have by enough to matter this week.</div></section>')

    def bust(r):
        v = r.get("bust")
        if v is None:
            return '<span class="m">–</span>'
        return f'<span class="pill b">{round(v * 100)}%</span>' if v >= 0.08 else f'{round(v * 100)}%'

    def lrow(r):
        slot = f'<span class="slot">{e(r["slot"])}</span>'
        cells = [td(e(r["slot"])), td(slot + (who(r) if r.get("team") else f'<span class="p">{e(r["name"])}</span>')), td(game(r)),
                 td(r["wk"], 1), td(sign(r.get("mkt")), 1)]
        if br:
            cells.append(td(bust(r) if r.get("team") else '<span class="pill b">100%</span>', 1))
        return cells + [td(FLAG.get(r.get("change"), ""))]

    head = ["Slot", "Player", "Game", ">Proj", ">Market"] + ([f">≤{br['threshold']} pt risk"] if br else []) + ["Action"]
    note = (f' Lineup choices are penalised for the chance of scoring {br["threshold"]} or less.' if br else "")
    h.append(f'<section><h2>Optimal lineup, week {L["week"]}</h2><div class="sub">Starters first, then bench. Market column = shift from betting-market player props.{note}</div>'
             + table(head, [lrow(r) for r in L["lineup"]["starters"] + L["lineup"]["bench"]]) + "</section>")

    if L["waivers"]:
        def comp(r):
            if not r["want"]:
                return '<span class="m">no rival demand</span>'
            t = f'{r["want"]} team{"s" if r["want"] > 1 else ""}'
            if r.get("rival_bid") is not None:
                t += f'<br><span class="m">top: {e(r["rival"])} ~${r["rival_bid"]}</span>'
            return t + (' <span class="pill b">may outbid you</span>' if r["outbid"] else "")

        def bidc(r):
            if r["bid"] is None:
                return "–"
            return f'${r["bid"]}'

        rows = [[td(who(r) + (' <span class="pill w">Trending</span>' if r["hot"] else "")
                    + (f' <span class="pill">Blocks opponent +{r["block"]}</span>' if r.get("block") else "")),
                 td(e(r["kind"])), td(r["wk"], 1), td(r["ppg"], 1), td(sign(r["d_ros"]), 1), td(sign(r["d_wk"]), 1)]
                + ([td(bust(r), 1)] if br else [])
                + [td(bidc(r), 1), td(comp(r)), td(e(r["drop"]) if r["drop"] else '<span class="m">open spot</span>')] for r in L["waivers"]]
        h.append('<section><h2>Other waiver options</h2><div class="sub">Fallbacks if a claim above fails, each priced against your current roster. Bid is the lower of what he is worth to you and what clears the top rival. Blocks = he would also improve this week\'s opponent.</div>'
                 + table(["Player", "Role", ">Wk proj", ">ROS / gm", ">ROS gain", ">Wk gain"] + ([f">≤{br['threshold']} pt risk"] if br else [])
                         + [">Bid", "Competition", "Would replace"], rows) + "</section>")
    else:
        h.append('<section><h2>Other waiver options</h2><div class="sub">Nothing else on the wire improves your lineup.</div></section>')

    if L["trades_open"]:
        if L.get("needs"):
            def vd(n):
                c = "b" if n["verdict"].startswith("Trade") else ("w" if n["verdict"].startswith("Fix") else "")
                return f'<span class="pill {c}">{e(n["verdict"])}</span>' if n["verdict"] != "Fine" else '<span class="m">Fine</span>'
            rows = [[td(f'<span class="p">{e(n["pos"])}</span>'), td(f'{n["rank"]} of {n["teams"]}', 1), td(n["ppg"], 1),
                     td((f'{e(n["fa"])} <span class="m">{n["fa_ppg"]}/gm · {n["fa_gain"]:+.1f} ROS</span>') if n["fa"] else '<span class="m">nothing useful</span>'),
                     td(vd(n))] for n in L["needs"]]
            h.append('<section><h2>Positional needs</h2><div class="sub">Where your starters rank in the league, and whether a free pickup closes the gap before you pay in a trade.</div>'
                     + table(["Position", ">League rank", ">Starters / gm", "Best on waivers", "Verdict"], rows) + "</section>")
        cards = []
        for t in L["trades"]:
            side = lambda cs: "<br>".join(f'<span class="p">{e(c["name"])}</span> <span class="m">{e(c["pos"])} · {c["ppg"]}/gm</span>' for c in cs)
            cards.append(f'<div class="trade"><span class="lab">With {e(t["partner"])}</span><div><span class="lab">Give</span><br>{side(t["give"])}</div>'
                         f'<div><span class="lab">Get</span><br>{side(t["get"])}</div>'
                         f'<div class="m">Your lineup {sign(t["my_gain"], " pts ROS")} · theirs {sign(t["their_gain"], " pts")}</div>'
                         + (f'<div class="m">{sign(t["edge"], " pts")} more than adding {e(t["wire_name"])} off waivers</div>' if t.get("wire_name") else "")
                         + '<div>' + (f'<span class="pill w">Fixes weak {e(t["fixes"])}</span> ' if t.get("fixes") else "")
                         + "".join(f'<span class="pill">From {e(p)} surplus</span> ' for p in t.get("from_strength", []))
                         + "".join(f'<span class="pill b">Thins weak {e(p)}</span> ' for p in t.get("opens_hole", [])) + '</div></div>')
        h.append('<section><h2>Trade offers to send</h2><div class="sub">Ranked by gain beyond what waivers already offer at that position, favouring deals that fix a weak spot from a surplus. Each also helps the other team and is close on value, so it can get accepted.</div>'
                 + ('<div class="trades">' + "".join(cards) + "</div>" if cards else '<div class="sub">No mutually beneficial deals found this week.</div>') + "</section>")
        b = table(["Buy low", "Owner", ">Outlook / gm", ">Last 4 / gm"], [[td(who(r)), td(e(r["owner"]), wrap=True), td(r["ppg"], 1), td(r["recent"], 1)] for r in L["buy"]]) if L["buy"] else '<div class="sub">None.</div>'
        s = table(["Sell high", ">Outlook / gm", ">Last 4 / gm"], [[td(who(r)), td(r["ppg"], 1), td(r["recent"], 1)] for r in L["sell"]]) if L["sell"] else '<div class="sub">None on your roster.</div>'
        h.append(f'<div class="two"><section><h2>Buy low</h2><div class="sub">Other teams\' players producing below their outlook.</div>{b}</section>'
                 f'<section><h2>Sell high</h2><div class="sub">Your players running hot versus their outlook.</div>{s}</section></div>')

    if L["movers"]:
        rows = [[td(who(r)), td("Your roster" if r["mine"] else "Free agent"), td(r["base"], 1), td(r["wk"], 1), td(sign(r["mkt"]), 1)] for r in L["movers"]]
        h.append('<section><h2>Where the markets disagree</h2><div class="sub">Largest gaps between prediction-market props and the baseline projection, among your players and free agents.</div>'
                 + table(["Player", "Status", ">Baseline", ">Blended", ">Shift"], rows) + "</section>")

    if L.get("breakouts"):
        rows = [[td(who(r)), td(r["status"]), td(f'{r["snap"]}%', 1), td(sign(r["d_snap"], " pts"), 1), td(r["opps"], 1), td(sign(r["d_opp"]), 1), td(r["ppg"], 1)]
                for r in L["breakouts"]]
        h.append('<section><h2>Role growth watch</h2><div class="sub">Snap share and touches + targets over the last two games versus the two before. Roles move before projections do.</div>'
                 + table(["Player", "Status", ">Snap share", ">Change", ">Touches + targets", ">Change", ">ROS / gm"], rows) + "</section>")

    rows = [[td(n + 1, 1), td(f'<span class="slot">{n + 1}</span><span class="p">{e(p["name"])}</span>'), td(p["rec"])] + ([td(p["vp"], 1)] if L.get("vp_rules") else [])
            + [td(f'{round(p["odds"] * 100)}%', 1), td(p["pf"], 1), td(p["wk"], 1), td(p["ros"], 1),
             td(f'${p["faab"]}' if L.get("faab") is not None else "–", 1)] for n, p in enumerate(L["power"])]
    vpn = ""
    if L.get("vp_rules"):
        v = L["vp_rules"]
        vpn = f' Standings use victory points: {v["win"]} for a win, +{v["top3"]} for a top-3 weekly score, +{v["top6"]} for top-6.'
    h.append(f'<section><h2>Playoff race</h2><div class="sub">Odds from {4000:,} simulations of the remaining schedule; top {L["playoff_teams"]} qualify, playoffs start week {L["playoff_start"]}.{vpn} '
             f'Your playoff weeks are weighted ×{L["playoff_weight"]} in waiver and trade values.</div>'
             + table([">#", "Team", "Record"] + ([">VP"] if L.get("vp_rules") else []) + [">Playoff odds", ">Points for", ">This week", ">ROS / wk", ">FAAB"], rows, ["me" if p["me"] else "" for p in L["power"]]) + "</section>")
    h.append("</div>")
    return "".join(h)


def fragment(out):
    tabs = "".join(f'<button role="tab" data-t="l{i}" aria-selected="{"true" if i == 0 else "false"}">{e(L.get("league") or "League")}'
                   f' <span style="font-weight:400">· {e(L.get("platform", ""))}</span></button>' for i, L in enumerate(out["leagues"]))
    notes = (f'<details class="notes"><summary>{len(out["notes"])} data note{"s" if len(out["notes"]) != 1 else ""}</summary><ul>'
             + "".join(f"<li>{e(n)}</li>" for n in out["notes"]) + "</ul></details>") if out["notes"] else ""
    return (f'<title>Fantasy War Room</title><meta name="claude:viewport-fit-sides" content="cover">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600&display=swap">'
            f'<style>{CSS}</style><div class="wrap"><header><h1>Fantasy War Room</h1>'
            f'<div class="sub">{e(out["season"])} season · week {out["week"]} · updated {e(out["generated"].replace("T", " ")[:16])} UTC</div></header>'
            f'<div class="bar"><div class="tabs" role="tablist">{tabs}</div></div>{notes}' + "".join(league(L, i) for i, L in enumerate(out["leagues"]))
            + '<footer>Projections: Rotowire weekly stat lines re-scored with each league\'s own rules, blended 50/50 with stat lines implied by Kalshi '
              'player-prop markets where a liquid market exists, and nudged toward the last four weeks of actual production for future weeks. '
              'Team totals are DraftKings lines. Trade and waiver gains are changes in your optimal-lineup points, net of what a free streamer would give you.</footer>'
            f'</div><script>{JS}</script>')


def render(out):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'</head><body>{fragment(out)}</body></html>')
