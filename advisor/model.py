"""Projection model: league-specific scoring, market blend, recent form, lineup optimiser."""
from . import markets

ELIG = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "DEF": {"DEF"},
        "FLEX": {"RB", "WR", "TE"}, "WRRB_FLEX": {"RB", "WR"}, "REC_FLEX": {"WR", "TE"},
        "SUPER_FLEX": {"QB", "RB", "WR", "TE"}}


def score(stats, scoring):
    return sum(v * stats[k] for k, v in scoring.items() if v and k in stats)


class Model:
    def __init__(self, league, data, cfg):
        self.lg, self.players, self.week = league, data["players"], data["week"]
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
        pool = sorted(pids, key=lambda p: -pts.get(p, 0))
        used, out, total = set(), [], 0.0
        order = sorted(range(len(self.lg["slots"])), key=lambda i: len(ELIG.get(self.lg["slots"][i], ())))
        picks = {}
        for i in order:
            elig = ELIG.get(self.lg["slots"][i], set())
            pick = next((p for p in pool if p not in used and self.pos(p) in elig), None)
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
        return sum(self.lineup(pids, w, floor=w >= f)[1] for w in self.weeks)

    def active(self, team):
        return [p for p in team["players"] if p not in team["reserve"]]
