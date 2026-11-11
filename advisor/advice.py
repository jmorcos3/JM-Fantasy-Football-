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
        stream = m.stream and m.pos(fa) in ("K", "DEF")
        same = [p for p in mine if m.pos(p) == m.pos(fa)]
        if stream and any(p in m.hold for p in same):
            continue  # you already hold a top-tier one: keep it, do not stream
        if not open_spot:
            for d in (same if stream and same else mine):  # a streamer replaces the one you have
                if m.pos(d) not in ELIG:
                    continue  # never suggest dropping a player the model cannot value
                v = m.team_value([p for p in mine if p != d] + [fa], nxt)
                if v > best_val:
                    best_drop, best_val = d, v
        new = [p for p in mine if p != best_drop] + [fa]
        d_ros, d_wk = best_val - base_ros, m.lineup(new, m.week)[1] - base_wk
        if (d_ros < 0.5 and d_wk < 0.5) or (stream and d_wk < 0.5):
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
                        drop=m.name(best_drop) if best_drop else None, drop_id=best_drop,
                        drop_ppg=round(m.ppg(best_drop), 1) if best_drop else None,
                        kind="Streamer" if stream else ("Season upgrade" if d_ros >= 5 else ("Streamer" if d_wk >= 0.5 else "Depth"))))
    pen = (m.lg["rules"].get("low_score_rule") or {}).get("penalty_pts", 0)
    def rank(r):
        if r["pos"] in ("K", "DEF"):  # streamable positions: this week is what counts
            return r["d_wk"] + (0 if m.stream else 0.3 * r["d_ros"]) - pen * (r["bust"] or 0)
        return r["d_ros"] + 0.5 * r["d_wk"] - pen * (r["bust"] or 0)

    out.sort(key=lambda r: -rank(r))
    keep, n = [], {}
    for r in out:
        n[r["pos"]] = n.get(r["pos"], 0) + 1
        if n[r["pos"]] <= (2 if r["pos"] in ("K", "DEF") else 4):
            keep.append(r)
    return keep[:top]


ELIG_POS = ("QB", "RB", "WR", "TE", "K", "DEF")


def move_plan(m, me, trending, opp, max_moves=4):
    """The actual claims to put in, in priority order. Each move is chosen after applying the ones
    before it, so the list is a consistent set of adds and drops rather than overlapping alternatives."""
    pen = (m.lg["rules"].get("low_score_rule") or {}).get("penalty_pts", 0)
    team, free0, moves = dict(me, players=list(me["players"])), list(m.free), []
    try:
        for _ in range(max_moves):
            rows = [r for r in waivers(m, team, trending, opp, top=30)
                    if (r["d_wk"] - pen * (r["bust"] or 0) * (r["d_wk"] > 0) >= (1.0 if r["pos"] in ("K", "DEF") else 1.5)
                        or (r["d_ros"] >= 4 and not (m.stream and r["pos"] in ("K", "DEF"))))
                    and not (r["pos"] in ("K", "DEF") and r["pos"] in {x["pos"] for x in moves})]  # one streamer per spot
            if not rows:
                break
            r = rows[0]
            slots, _ = m.lineup(m.active(team), m.week)
            hole = next((s for s, p, pts in slots if r["pos"] in ELIG[s] and len(ELIG[s]) == 1 and pts <= 0), None)
            why = []
            if hole:
                why.append(f"your {hole} slot scores nothing this week without him")
            if r["d_wk"] >= 0.5:
                why.append(f"+{r['d_wk']} pts this week")
            if r["d_ros"] >= 0.5 and not (m.stream and r["pos"] in ("K", "DEF")):
                why.append(f"+{r['d_ros']} pts over the rest of the season")
            if r.get("block"):
                why.append("keeps him away from this week's opponent")
            r["why"] = "; ".join(why)
            r["starts"] = r["d_wk"] >= 0.5
            if r["drop_id"]:
                d = r["drop_id"]
                gone = "on bye and not needed" if m.proj[m.week].get(d, 0) <= 0 and m.ppg(d) > 0 else "least useful roster spot"
                r["drop_why"] = f"{gone}; projects {r['drop_ppg']}/gm from here"
            moves.append(r)
            team["players"] = [p for p in team["players"] if p != r["drop_id"]] + [r["id"]]
            m.free = [p for p in m.free if p != r["id"]]
    finally:
        m.free = free0
    return moves


def positional(m, me, wv):
    """Per position: how your starters rank in the league, and whether the waiver wire can fix it."""
    n_teams, out = len(m.lg["teams"]), []
    for pos in SKILL:
        n = sum(1 for s in m.lg["slots"] if s == pos)
        if not n:
            continue

        def strength(t):
            top = sorted((m.ppg(p) for p in m.active(t) if m.pos(p) == pos), reverse=True)[:n]
            return sum(top) / n if top else 0

        mine = strength(me)
        rank = 1 + sum(1 for t in m.lg["teams"] if t["id"] != me["id"] and strength(t) > mine)
        best = max((r for r in wv if r["pos"] == pos), key=lambda r: r["d_ros"], default=None)
        fix = best["d_ros"] if best else 0
        weak, strong = rank > n_teams * 2 / 3, rank <= n_teams / 3
        if weak and fix >= 4:
            verdict = "Fix on waivers first"
        elif weak:
            verdict = "Trade for an upgrade"
        elif strong:
            verdict = "Strength: trade from here"
        else:
            verdict = "Fine"
        out.append({"pos": pos, "ppg": round(mine, 1), "rank": rank, "teams": n_teams, "weak": weak, "strong": strong,
                    "fa": best["name"] if best else None, "fa_ppg": best["ppg"] if best else None,
                    "fa_gain": round(fix, 1), "verdict": verdict})
    return out


def trades(m, me, needs=(), top=8, skip=()):
    need = {n["pos"]: n for n in needs}
    mine = m.active(me)
    my_base = m.team_value(mine)
    my_assets = [p for p in mine if m.pos(p) in SKILL and m.value(p) > 0 and p not in m.unprojected]
    best_fa = sorted((p for p in m.free if m.pos(p) in SKILL), key=lambda p: -m.value(p))[:3]
    ideas = []
    for t in m.lg["teams"]:
        if t["id"] == me["id"] or t["id"] in skip:
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
                nd = need.get(m.pos(get), {})
                wire = max(nd.get("fa_gain", 0), 0)  # what a free pickup at that position already gets you
                edge = my_gain - wire
                if edge >= (2 if nd.get("weak") else 3) and t_gain >= 1:
                    gp = {m.pos(a) for a in give}
                    score = edge * (1.6 if nd.get("weak") else 1) * (1.15 if any(need.get(p, {}).get("strong") for p in gp) else 1) \
                        * (0.4 if any(need.get(p, {}).get("weak") for p in gp - {m.pos(get)}) else 1)
                    found.append({"partner": t["name"], "give": [card(m, a) for a in give], "get": [card(m, get)],
                                  "edge": round(edge, 1), "wire": round(wire, 1), "wire_name": nd.get("fa") if wire >= 1 else None,
                                  "fixes": m.pos(get) if nd.get("weak") else None, "score": score,
                                  "from_strength": sorted(p for p in gp if need.get(p, {}).get("strong")),
                                  "opens_hole": sorted(p for p in gp - {m.pos(get)} if need.get(p, {}).get("weak")),
                                  "my_gain": round(my_gain, 1), "their_gain": round(t_gain, 1),
                                  "give_val": round(gv, 1), "get_val": round(rv, 1)})
        seen = set()
        for f in sorted(found, key=lambda f: -f["score"]):
            if f["get"][0]["id"] not in seen and len(seen) < 3:
                seen.add(f["get"][0]["id"])
                ideas.append(f)
    return sorted(ideas, key=lambda f: -f["score"])[:top]


def buy_sell(m, me, skip=()):
    """Projection vs recent production gaps. Buy = others' players producing below their outlook."""
    owner = {p: t["name"] for t in m.lg["teams"] if t["id"] not in skip for p in t["players"]}
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
    # leagues where teams out of the playoff race are off limits as trade partners
    floor = m.lg["rules"].get("min_partner_playoff_odds")
    skip = {i for i, o in sm["odds"].items() if floor and o < floor}
    buy, sell = buy_sell(m, me, skip)
    needs = positional(m, me, waivers(m, me, trending, opp, top=60))
    dl = m.lg.get("trade_deadline")
    return {
        "league": m.lg["name"], "platform": m.lg["platform"], "team": me["name"], "record": f"{me['wins']}-{me['losses']}",
        "faab": me["faab_left"] if m.lg["faab"] else None, "week": m.week,
        "deadline": dl if dl and 0 < dl < 99 else None, "trades_open": not dl or dl >= m.week or dl >= 99,
        "matchup": matchup(m, me, opp), "lineup": lineup_advice(m, me, current_starters),
        "moves": (mv := move_plan(m, me, trending, opp)),
        "waivers": [r for r in waivers(m, me, trending, opp, top=12 + len(mv)) if r["id"] not in {x["id"] for x in mv}][:10], "trades": trades(m, me, needs, skip=skip), "needs": needs, "buy": buy, "sell": sell,
        "power": power(m, sm), "breakouts": breakouts(m, me),
        "playoff_odds": round(sm["odds"][me["id"]], 2), "seed": round(sm["seed"][me["id"]], 1), "playoff_teams": m.lg["playoff_teams"],
        "playoff_start": m.lg["playoff_start"], "playoff_weight": round(m.week_w.get(m.lg["playoff_start"], 1.0), 2), "week_sim": sm["week"],
        "vp": sm["now"][me["id"]]["vp"] if sm["vp"] else None, "vp_rules": m.lg["rules"].get("victory_points"),
        "bust_rule": m.lg["rules"].get("low_score_rule"), "movers": movers(m, me), "market_players": len(m.mkt_delta),
    }
