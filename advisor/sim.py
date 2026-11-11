"""Monte Carlo of the remaining regular season -> playoff odds, plus this week's outlook.

Supports leagues ranked by victory points (win + weekly top-3 / top-6 bonuses)."""
import random


def _vp(rules, won, rank):
    if not rules:
        return 0
    bonus = rules["top3"] if rank < 3 else (rules["top6"] if rank < 6 else 0)
    return (rules["win"] if won else 0) + bonus


def standings_now(lg):
    """Current wins / points-for / victory points per team."""
    rules = lg.get("rules", {}).get("victory_points")
    st = {t["id"]: {"w": t["wins"], "pf": t["pf"], "vp": 0} for t in lg["teams"]}
    for week in lg["history"] if rules else []:
        scores = sorted((pts for a, pa, b, pb in week for pts in (pa, pb)), reverse=True)
        for a, pa, b, pb in week:
            for rid, mine, theirs in ((a, pa, pb), (b, pb, pa)):
                if rid in st:
                    st[rid]["vp"] += _vp(rules, mine > theirs, scores.index(mine))
    return st


def run(m, cfg):
    lg = m.lg
    rules = lg.get("rules", {}).get("victory_points")
    sd, n = cfg.get("weekly_score_sd", 24), cfg.get("sim_runs", 4000)
    weeks = sorted(w for w in lg["schedule"] if w in m.proj)
    ids = [t["id"] for t in lg["teams"]]
    mu = {t["id"]: {w: m.lineup(m.active(t), w, floor=w > m.week)[1] for w in weeks} for t in lg["teams"]}
    now = standings_now(lg)
    made = dict.fromkeys(ids, 0)
    seed_sum = dict.fromkeys(ids, 0)
    me = lg["my_team"]
    wk = {"win": 0, "top3": 0, "top6": 0, "vp": 0}
    rng = random.Random(7)
    for _ in range(n):
        st = {i: [now[i]["vp"], now[i]["w"], now[i]["pf"]] for i in ids}
        for w in weeks:
            sc = {i: rng.gauss(mu[i][w], sd) for i in ids}
            order = sorted(ids, key=lambda i: -sc[i])
            rank = {i: r for r, i in enumerate(order)}
            for a, b in lg["schedule"][w]:
                for x, y in ((a, b), (b, a)):
                    won = sc[x] > sc[y]
                    st[x][0] += _vp(rules, won, rank[x])
                    st[x][1] += won
                    st[x][2] += sc[x]
                    if w == m.week and x == me:
                        wk["win"] += won
                        wk["top3"] += rank[x] < 3
                        wk["top6"] += rank[x] < 6
                        wk["vp"] += _vp(rules, won, rank[x])
        final = sorted(ids, key=lambda i: tuple(-v for v in st[i]))
        for pos, i in enumerate(final):
            seed_sum[i] += pos + 1
            if pos < lg["playoff_teams"]:
                made[i] += 1
    return {"odds": {i: made[i] / n for i in ids}, "seed": {i: seed_sum[i] / n for i in ids},
            "now": now, "week": {k: v / n for k, v in wk.items()} if weeks and weeks[0] == m.week else None,
            "vp": bool(rules), "weeks_left": len(weeks)}
