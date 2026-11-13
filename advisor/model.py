"""Projection model: league-specific scoring, market blend, recent form, usage trends, lineup optimiser."""
import math

from . import markets

ELIG = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "DEF": {"DEF"},
        "FLEX": {"RB", "WR", "TE"}, "WRRB_FLEX": {"RB", "WR"}, "REC_FLEX": {"WR", "TE"},
        "SUPER_FLEX": {"QB", "RB", "WR", "TE"}}


def score(stats, scoring):
    return sum(v * stats[k] for k, v in scoring.items() if v and k in stats)


class Model:
    def __init__(self, league, data, cfg):
        self.lg, self.players, self.week = league, data["players"], data["week"]
        self.photo = data.get("photo") or (lambda pid: None)
        self.weeks = list(range(self.week, cfg["last_week_of_season"] + 1))
        self.lines = data["lines"]
        sc = league["scoring"]
        mw, rf = cfg["market_weight"], cfg["recent_form_weight"]

        # recent form: actual points per game over the last 4 weeks
        self.recent, self.recent_gp = {}, {}
        for w, rows in data["stats"].items():
            if w < self.week - 4:
                continue
            for pid, r in rows.items():
                st = r["stats"]
                if st.get("gp") or st.get("off_snp") or self.pos(pid) == "DEF":
                    self.recent[pid] = self.recent.get(pid, 0) + score(st, sc)
                    self.recent_gp[pid] = self.recent_gp.get(pid, 0) + 1
        self.recent = {p: v / self.recent_gp[p] for p, v in self.recent.items()}

        # usage trend: snap share and opportunities (carries + targets), last 2 games vs the 2 before
        self.usage = {}
        hist = {}
        for w in sorted(data["stats"]):
            if w < self.week - 4:
                continue
            for pid, r in data["stats"][w].items():
                st = r["stats"]
                if st.get("off_snp") and st.get("tm_off_snp"):
                    hist.setdefault(pid, []).append((st["off_snp"] / st["tm_off_snp"],
                                                     (st.get("rush_att") or 0) + (st.get("rec_tgt") or 0)))
        for pid, h in hist.items():
            if len(h) >= 3:
                new, old = h[-2:], h[:-2]
                avg = lambda rows, i: sum(r[i] for r in rows) / len(rows)
                self.usage[pid] = {"snap": avg(new, 0), "d_snap": avg(new, 0) - avg(old, 0),
                                   "opp": avg(new, 1), "d_opp": avg(new, 1) - avg(old, 1)}

        self.base, self.proj, self.mkt_delta, self.opp = {}, {}, {}, {}
        name_idx = {}
        for w in self.weeks:
            self.base[w] = {pid: score(r["stats"], sc) for pid, r in data["proj"][w].items()}
        for pid, r in data["proj"][self.week].items():
            self.opp[pid] = r.get("opp")
            p = self.players.get(pid) or {}
            if p.get("position") in ("QB", "RB", "WR", "TE") and p.get("full_name"):
                name_idx.setdefault(markets.norm_name(p["full_name"]), []).append(pid)

        # this week: blend baseline with market-implied stat lines
        cur = dict(self.base[self.week])
        for name, mk in data["props"].items():
            cands = name_idx.get(name)
            if not cands:
                continue
            pid = max(cands, key=lambda c: self.base[self.week].get(c, 0))
            stats, n = markets.apply_market(data["proj"][self.week][pid]["stats"], mk)
            if n:
                implied = score(stats, sc)
                cur[pid] = (1 - mw) * cur[pid] + mw * implied
                self.mkt_delta[pid] = cur[pid] - self.base[self.week][pid]
        self.proj[self.week] = cur
        # games already under way: those players are locked. Finished games use the real score.
        self.locked_teams = {t for t, l in self.lines.items() if l.get("started")}
        self.final, self.actual = set(), {}
        live = data.get("live") or {}
        for pid in list(cur):
            line = self.lines.get(self.team(pid)) or {}
            if line.get("started"):  # points banked so far + projection for the time left
                self.actual[pid] = score(live[pid]["stats"], sc) if pid in live else 0.0
                cur[pid] = self.actual[pid] + cur[pid] * line.get("left", 0.0)
                if line.get("done"):
                    self.final.add(pid)
        self.fixed = {}  # locked current starters -> the lineup slot they are stuck in
        for t in league["teams"]:
            for i, pid in enumerate(t.get("starters") or []):
                if pid and pid != "0" and i < len(league["slots"]) and self.is_locked(pid):
                    self.fixed[pid] = i
        # injuries: Rotowire does not always zero out inactive players
        hurt = {pid: (self.players.get(pid) or {}).get("injury_status") for pid in cur}
        for pid, stt in hurt.items():
            if stt in ("Out", "IR", "PUP", "Sus", "NFI", "DNR", "COV"):
                cur[pid] = 0.0
        # future weeks: baseline nudged toward recent actual production
        for w in self.weeks[1:]:
            self.proj[w] = {}
            for pid, v in self.base[w].items():
                if v > 0 and self.recent_gp.get(pid, 0) >= 2:
                    v = (1 - rf) * v + rf * self.recent[pid]
                u = self.usage.get(pid)
                if u and self.pos(pid) in ("RB", "WR", "TE"):
                    v *= 1 + max(-0.1, min(0.1, 0.5 * u["d_snap"]))  # role growing or shrinking
                if hurt.get(pid) in ("IR", "PUP", "NFI"):
                    v *= 0.5  # return date unknown: haircut the rest-of-season outlook
                self.proj[w][pid] = v

        # producing players with no published projection (status in limbo): carry recent form at a haircut
        # so they are never treated as worthless drop/trade fodder
        projected = {pid for w in self.weeks for pid, v in self.base[w].items() if v > 0}
        self.unprojected = {pid for pid, n in self.recent_gp.items() if n >= 2 and pid not in projected
                            and self.recent[pid] >= 6 and (self.players.get(pid) or {}).get("team")}
        for pid in self.unprojected:
            for w in self.weeks[1:]:
                self.proj[w][pid] = 0.7 * self.recent[pid]

        self.ros, self.games = {}, {}
        for w in self.weeks:
            for pid, v in self.proj[w].items():
                if v > 0:
                    self.ros[pid] = self.ros.get(pid, 0) + v
                    self.games[pid] = self.games.get(pid, 0) + 1

        # streaming rule for kickers / defences: only this week counts unless the one you hold is elite
        self.hold = set()
        n = (cfg.get("stream_k_def") or {}).get("hold_top_n")
        self.stream = n is not None
        for pos in ("K", "DEF"):
            ranked = sorted((p for p in self.ros if self.pos(p) == pos), key=lambda p: -self.ros[p])
            self.hold.update(ranked[:n or 0])
        self.week_w = {w: 1.0 for w in self.weeks}  # playoff weighting, set after the season simulation

        # chance of a dud (score at or below a threshold) this week, for leagues that punish it
        self.bust, self.pick = {}, {}
        rule = league.get("rules", {}).get("low_score_rule")
        if rule:
            thr, bad, gp = rule["threshold"], {}, {}
            for w, rows in data["stats"].items():
                for pid, r in rows.items():
                    st = r["stats"]
                    if st.get("gp") or st.get("off_snp") or self.pos(pid) == "DEF":
                        gp[pid] = gp.get(pid, 0) + 1
                        bad[pid] = bad.get(pid, 0) + (score(st, sc) <= thr)
            scale = {"DEF": 3.5, "K": 2.5}
            for pid, mu in self.proj[self.week].items():
                if mu <= 0:
                    self.bust[pid] = 1.0
                    continue
                prior = math.exp(-max(mu - thr, 0) / scale.get(self.pos(pid), 3.0))
                if self.pos(pid) == "DEF":
                    tot = (self.lines.get(self.opp.get(pid) or "") or {}).get("implied")
                    if tot:
                        prior = min(0.9, prior * (tot / 22) ** 2)  # tougher offence -> more blow-up risk
                self.bust[pid] = (bad.get(pid, 0) + 4 * prior) / (gp.get(pid, 0) + 4)
            self.pick = {pid: mu - self.bust.get(pid, 0) * rule["penalty_pts"] for pid, mu in self.proj[self.week].items()}

        self.rostered = {pid for t in league["teams"] for pid in t["players"]}
        self.free = [pid for pid in self.ros if pid not in self.rostered and self.pos(pid) in ELIG
                     and ((self.players.get(pid) or {}).get("team") or self.pos(pid) == "DEF")]
        # replacement level = what the waiver wire offers at each position in THIS league
        self.repl = {}
        for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
            top = sorted((self.ppg(p) for p in self.free if self.pos(p) == pos), reverse=True)[:3]
            self.repl[pos] = sum(top) / len(top) if top else 0

    # --- helpers
    def pos(self, pid):
        p = self.players.get(pid) or {}
        return "DEF" if p.get("position") == "DEF" or (pid.isalpha() and len(pid) <= 3) else p.get("position")

    def is_locked(self, pid):
        return self.team(pid) in self.locked_teams

    def name(self, pid):
        p = self.players.get(pid) or {}
        if self.pos(pid) == "DEF":
            return f"{pid} D/ST"
        return p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or pid

    def team(self, pid):
        return pid if self.pos(pid) == "DEF" else (self.players.get(pid) or {}).get("team") or "FA"

    def injury(self, pid):
        return (self.players.get(pid) or {}).get("injury_status") or ""

    def ppg(self, pid):
        return self.ros.get(pid, 0) / self.games[pid] if self.games.get(pid) else 0

    def value(self, pid):
        """Trade value: rest-of-season points above waiver-wire replacement."""
        return max(0.0, (self.ppg(pid) - self.repl.get(self.pos(pid), 0)) * self.games.get(pid, 0))

    def lineup(self, pids, week, floor=False):
        """Optimal lineup for one week. Returns [(slot, pid, pts)] and total.
        floor=True credits every slot with at least a waiver-wire streamer, so bye-week
        holes are not over-valued when pricing trades and pickups."""
        pts = self.proj[week]
        rank = self.pick if week == self.week and self.pick else pts  # dud-risk adjusted ordering
        pool = sorted(pids, key=lambda p: -rank.get(p, 0))
        used, out, total = set(), [], 0.0
        order = sorted(range(len(self.lg["slots"])), key=lambda i: len(ELIG.get(self.lg["slots"][i], ())))
        picks = {}
        if week == self.week and self.locked_teams:
            pre = {self.fixed[p]: p for p in pids if p in self.fixed}  # cannot be moved out
            pool = [p for p in pool if not self.is_locked(p)]  # cannot be moved in
        else:
            pre = {}
        for i in order:
            elig = ELIG.get(self.lg["slots"][i], set())
            pick = pre[i] if i in pre else next((p for p in pool if p not in used and self.pos(p) in elig), None)
            got = pts.get(pick, 0) if pick else 0
            if pick:
                used.add(pick)
            if floor:
                got = max(got, 0.85 * max(self.repl.get(p, 0) for p in elig))
            total += got
            picks[i] = pick
        for i, slot in enumerate(self.lg["slots"]):
            out.append((slot, picks[i], pts.get(picks[i], 0) if picks[i] else 0))
        return out, total

    def team_value(self, pids, floor_from=None):
        """Sum of optimal-lineup points over the remaining weeks."""
        f = self.week if floor_from is None else floor_from
        return sum(self.week_w[w] * self.lineup(pids, w, floor=w >= f)[1] for w in self.weeks)

    def active(self, team):
        return [p for p in team["players"] if p not in team["reserve"]]
