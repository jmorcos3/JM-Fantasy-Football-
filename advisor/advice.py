"""Decision layer: start/sit, waivers + FAAB, trades, buy-low/sell-high, power rankings."""
import math
from itertools import combinations

from .model import ELIG

SKILL = ("QB", "RB", "WR", "TE")


def card(m, pid, **extra):
    line = m.lines.get(m.team(pid)) or {}
    inj = m.injury(pid)
    if pid in m.unprojected:
        inj = (inj + " · " if inj else "") + "no projection, check status"
    return {"id": pid, "name": m.name(pid), "pos": m.pos(pid), "team": m.team(pid), "inj": inj,
            "wk": round(m.proj[m.week].get(pid, 0), 1), "base": round(m.base[m.week].get(pid, 0), 1),
            "mkt": round(m.mkt_delta[pid], 1) if pid in m.mkt_delta else None,
            "ppg": round(m.ppg(pid), 1), "ros": round(m.ros.get(pid, 0), 1), "recent": round(m.recent.get(pid, 0), 1)
            if pid in m.recent else None, "value": round(m.value(pid), 1), "opp": m.opp.get(pid) or line.get("opp"),
            "home": line.get("home"), "implied": line.get("implied"),
            "bust": round(m.bust.get(pid, 1.0), 2) if m.bust else None, "usage": m.usage.get(pid), **extra}


def lineup_advice(m, me, current_starters):
    slots, total = m.lineup(m.active(me), m.week)
    starting = {p for _, p, _ in slots if p}
    cur = [p for p in (current_starters or []) if p and p != "0"]
    wk = m.proj[m.week]

    def flag(slot, p):
        """'swap' if p should replace a current starter for a real gain, 'coin' if it is a toss-up."""
        if not cur or p in cur or wk.get(p, 0) <= 0:
            return None
        out = [c for c in cur if c not in starting and m.pos(c) in ELIG[slot]]
        return "swap" if not out or wk.get(p, 0) - max(wk.get(c, 0) for c in out) >= 0.5 else "coin"

    rows = [card(m, p, slot=s, change=flag(s, p)) if p
            else {"slot": s, "name": "EMPTY — add a player", "pos": s, "wk": 0, "change": "swap"} for s, p, _ in slots]
    bench = sorted((p for p in me["players"] if p not in starting), key=lambda p: -m.proj[m.week].get(p, 0))
    safe = 1.0
    for _, p, _ in slots:
        safe *= 1 - (m.bust.get(p, 1.0) if p else 1.0)
    return {"starters": rows, "total": round(total, 1), "any_bust": round(1 - safe, 2) if m.bust else None,
            "bench": [card(m, p, slot="IR" if p in me["reserve"] else "BN",
                           change="sit" if p in cur and m.pos(p) in ELIG else None) for p in bench]}


def matchup(m, me, opp):
    if not opp:
        return None
    a, b = m.lineup(m.active(me), m.week)[1], m.lineup(m.active(opp), m.week)[1]
    return {"opp": opp["name"], "me": round(a, 1), "them": round(b, 1),
            "win": round(0.5 * (1 + math.erf((a - b) / (30 * math.sqrt(2)))), 2)}  # ~30pt sd on the margin


def _pct(d_ros, d_wk):
    return min(0.5, 0.012 * max(d_ros, 0) + 0.004 * max(d_wk, 0))


def waivers(m, me, trending, opp=None, top=12):
    mine = m.active(me)
    rivals = []
    for t in m.lg["teams"]:
        if t["id"] == me["id"]:
            continue
        act = m.active(t)
        base = m.team_value(act, m.week + 1)
        full = len(act) >= len(m.lg["slots"]) + m.lg["bench"]
        # what it costs them to clear a roster spot
        cut = min((base - m.team_value([p for p in act if p != d], m.week + 1) for d in act if m.pos(d) in ELIG),
                  default=0) if full else 0
        rivals.append((t, act, base + cut))
    urgency = 1 + (m.week - 1) / 17  # unspent budget is worth nothing after the season
    opp_now = m.lineup(m.active(opp), m.week)[1] if opp else 0
    nxt = m.week + 1
    base_wk, base_ros = m.lineup(mine, m.week)[1], m.team_value(mine, nxt)
    open_spot = len(mine) < len(m.lg["slots"]) + m.lg["bench"]
    cands = set()
    for pos in ELIG_POS:
        fa = [p for p in m.free if m.pos(p) == pos]
        cands.update(sorted(fa, key=lambda p: -m.ros.get(p, 0))[:8])
        cands.update(sorted(fa, key=lambda p: -m.proj[m.week].get(p, 0))[:5])
    cands.update(p for p in sorted(trending, key=lambda p: -trending[p])[:25] if p in m.free)
    hot = {p: i for i, p in enumerate(sorted((p for p in trending if p in m.free), key=lambda p: -trending[p])[:15])}
    out = []
    for fa in cands:
        best_drop, best_val = None, m.team_value(mine + [fa], nxt) if open_spot else -1e9
        if not open_spot:
            for d in mine:
                if m.pos(d) not in ELIG:
                    continue  # never suggest dropping a player the model cannot value
                v = m.team_value([p for p in mine if p != d] + [fa], nxt)
                if v > best_val:
                    best_drop, best_val = d, v
        new = [p for p in mine if p != best_drop] + [fa]
        d_ros, d_wk = best_val - base_ros, m.lineup(new, m.week)[1] - base_wk
        if d_ros < 0.5 and d_wk < 0.5:
            continue
        cheap = m.pos(fa) in ("K", "DEF")  # never pay up for kickers or defences
        cap = lambda pct: min(pct, 0.02) if cheap else pct
        # who else wants him, and what they can afford
        want, rival, rival_bid = 0, None, 0
        for t, act, base in rivals:
            g = m.team_value(act + [fa], nxt) - base
            if g >= 3:
                want += 1
                est = round(0.4 * cap(_pct(g, 0) * urgency) * max(t["faab_left"], 0))  # managers shade bids well below full value if m.lg["faab"] else 0
                if rival is None or est > rival_bid:
                    rival, rival_bid = t["name"], est
        bid, outbid = None, False
        if m.lg["faab"]:
            ceiling = max(1, round(cap(_pct(d_ros, d_wk) * urgency * (1.25 if fa in hot else 1)) * me["faab_left"])) if me["faab_left"] > 0 else 0
            target = round(rival_bid * 1.15) + 1 if want else 1  # pay just enough to clear the top rival
            bid, outbid = min(ceiling, target), target > ceiling and not cheap
        block = round(m.lineup(m.active(opp) + [fa], m.week)[1] - opp_now, 1) if opp else 0
        out.append(card(m, fa, d_ros=round(d_ros, 1), d_wk=round(d_wk, 1), bid=bid, hot=fa in hot, want=want,
                        rival=rival, rival_bid=rival_bid if m.lg["faab"] else None, outbid=outbid,
                        block=block if block >= 2 else None,
                        drop=m.name(best_drop) if best_drop else None,
                        kind="Season upgrade" if d_ros >= 5 else ("Streamer" if d_wk >= 0.5 else "Depth")))
    pen = (m.lg["rules"].get("low_score_rule") or {}).get("penalty_pts", 0)
    out.sort(key=lambda r: -(r["d_ros"] + 0.5 * r["d_wk"] - pen * (r["bust"] or 0)))
    keep, n = [], {}
    for r in out:
        n[r["pos"]] = n.get(r["pos"], 0) + 1
        if n[r["pos"]] <= (2 if r["pos"] in ("K", "DEF") else 4):
            keep.append(r)
    return keep[:top]


ELIG_POS = ("QB", "RB", "WR", "TE", "K", "DEF")


def trades(m, me, top=8):
    mine = m.active(me)
    my_base = m.team_value(mine)
    my_assets = [p for p in mine if m.pos(p) in SKILL and m.value(p) > 0 and p not in m.unprojected]
    best_fa = sorted((p for p in m.free if m.pos(p) in SKILL), key=lambda p: -m.value(p))[:3]
    ideas = []
    for t in m.lg["teams"]:
        if t["id"] == me["id"]:
            continue
        theirs = m.active(t)
        t_base = m.team_value(theirs)
        t_assets = [p for p in theirs if m.pos(p) in SKILL and m.value(p) > 0 and p not in m.unprojected]
        t_cut = min((p for p in theirs if m.pos(p) in SKILL), key=m.value, default=None)
        found = []
        for give in [(a,) for a in my_assets] + list(combinations(my_assets, 2)):
            gv = sum(m.value(a) for a in give)
            for get in t_assets:
                rv = m.value(get)
                if rv < max(m.value(a) for a in give) and len(give) == 2:
                    continue  # 2-for-1 only makes sense when consolidating into a better player
                if rv < 10 or not (0.85 * rv <= gv <= 1.5 * rv):
                    continue  # must look fair on paper or it will not be accepted
                my_new = [p for p in mine if p not in give] + [get]
                t_new = [p for p in theirs if p != get] + list(give)
                if len(give) == 2:
                    my_new = max(([*my_new, f] for f in best_fa), key=m.team_value, default=my_new)
                    t_new = [p for p in t_new if p != t_cut]
                my_gain, t_gain = m.team_value(my_new) - my_base, m.team_value(t_new) - t_base
                if my_gain >= 4 and t_gain >= 1:
                    found.append({"partner": t["name"], "give": [card(m, a) for a in give], "get": [card(m, get)],
                                  "my_gain": round(my_gain, 1), "their_gain": round(t_gain, 1),
                                  "give_val": round(gv, 1), "get_val": round(rv, 1)})
        seen = set()
        for f in sorted(found, key=lambda f: -f["my_gain"]):
            if f["get"][0]["id"] not in seen and len(seen) < 2:
                seen.add(f["get"][0]["id"])
                ideas.append(f)
    return sorted(ideas, key=lambda f: -f["my_gain"])[:top]


def buy_sell(m, me):
    """Projection vs recent production gaps. Buy = others' players producing below their outlook."""
    owner = {p: t["name"] for t in m.lg["teams"] for p in t["players"]}
    buy, sell = [], []
    for pid, who in owner.items():
        if m.pos(pid) not in SKILL or m.recent_gp.get(pid, 0) < 2 or len(m.weeks) < 2:
            continue
        fut = [m.base[w].get(pid, 0) for w in m.weeks if m.base[w].get(pid, 0) > 0]
        if not fut:
            continue
        gap = sum(fut) / len(fut) - m.recent[pid]
        if who != me["name"] and gap >= 2.5 and m.value(pid) > 0:
            buy.append(card(m, pid, owner=who, gap=round(gap, 1)))
        if who == me["name"] and gap <= -2.5:
            sell.append(card(m, pid, owner=who, gap=round(gap, 1)))
    return sorted(buy, key=lambda r: -r["gap"])[:8], sorted(sell, key=lambda r: r["gap"])[:5]


def breakouts(m, me, n=8):
    """Role growth: snap share or touches/targets jumping over the last two games."""
    owner = {p: t["name"] for t in m.lg["teams"] for p in t["players"]}
    rows = []
    for pid, u in m.usage.items():
        if m.pos(pid) not in ("RB", "WR", "TE") or not (u["d_snap"] >= 0.12 or u["d_opp"] >= 4) or u["snap"] < 0.35 or u["opp"] < 5:
            continue
        who = owner.get(pid)
        if who and who != me["name"]:
            continue  # only actionable names: free agents and your own roster
        rows.append(card(m, pid, status="Your roster" if who else "Free agent", snap=round(u["snap"] * 100),
                         d_snap=round(u["d_snap"] * 100), opps=round(u["opp"], 1), d_opp=round(u["d_opp"], 1)))
    return sorted(rows, key=lambda r: -(r["d_snap"] + 3 * r["d_opp"]))[:n]


def power(m, sm):
    rows = []
    for t in m.lg["teams"]:
        act = m.active(t)
        rows.append({"name": t["name"], "me": t["id"] == m.lg["my_team"], "rec": f"{t['wins']}-{t['losses']}",
                     "pf": round(t["pf"], 1), "wk": round(m.lineup(act, m.week)[1], 1),
                     "ros": round(sum(m.lineup(act, w, floor=True)[1] for w in m.weeks) / len(m.weeks), 1),
                     "faab": t["faab_left"], "odds": round(sm["odds"][t["id"]], 2), "seed": round(sm["seed"][t["id"]], 1),
                     "vp": sm["now"][t["id"]]["vp"] if sm["vp"] else None})
    return sorted(rows, key=lambda r: (-r["odds"], r["seed"]))


def movers(m, me, n=8):
    """Where the betting markets disagree most with the baseline projection."""
    mine = set(me["players"])
    rows = [card(m, p, mine=p in mine, free=p in m.free) for p in m.mkt_delta if p in mine or p in m.free]
    return sorted(rows, key=lambda r: -abs(r["mkt"]))[:n]


def build(m, trending, current_starters, sm):
    me = next((t for t in m.lg["teams"] if t["id"] == m.lg["my_team"]), None)
    if not me:
        return {"error": "Could not find your team in this league."}
    opp = next((t for t in m.lg["teams"] if t["id"] == m.lg["opponents"].get(me["id"])), None)
    buy, sell = buy_sell(m, me)
    dl = m.lg.get("trade_deadline")
    return {
        "league": m.lg["name"], "platform": m.lg["platform"], "team": me["name"], "record": f"{me['wins']}-{me['losses']}",
        "faab": me["faab_left"] if m.lg["faab"] else None, "week": m.week,
        "deadline": dl if dl and 0 < dl < 99 else None, "trades_open": not dl or dl >= m.week or dl >= 99,
        "matchup": matchup(m, me, opp), "lineup": lineup_advice(m, me, current_starters),
        "waivers": waivers(m, me, trending, opp), "trades": trades(m, me), "buy": buy, "sell": sell,
        "power": power(m, sm), "breakouts": breakouts(m, me),
        "playoff_odds": round(sm["odds"][me["id"]], 2), "seed": round(sm["seed"][me["id"]], 1), "playoff_teams": m.lg["playoff_teams"],
        "playoff_start": m.lg["playoff_start"], "playoff_weight": round(m.week_w.get(m.lg["playoff_start"], 1.0), 2), "week_sim": sm["week"],
        "vp": sm["now"][me["id"]]["vp"] if sm["vp"] else None, "vp_rules": m.lg["rules"].get("victory_points"),
        "bust_rule": m.lg["rules"].get("low_score_rule"), "movers": movers(m, me), "market_players": len(m.mkt_delta),
    }
