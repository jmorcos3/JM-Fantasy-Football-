# Fantasy War Room

Pulls your Sleeper and ESPN leagues, projects every player under each league's own scoring, and writes one
page of decisions: optimal lineup, waiver targets with FAAB bids, trade offers, buy-low / sell-high, power rankings.

## Run it

    python3 run.py        # no installs needed; writes site/index.html
    python3 run.py --embed   # also inlines headshots into site/artifact.html, for hosts that block external images

## How the numbers are built

| Layer | Source |
|---|---|
| Rosters, scoring, matchups | Sleeper API, ESPN fantasy API |
| Baseline stat projections (this week through week 17) | Rotowire, via Sleeper |
| Player props | Kalshi prediction markets (yardage, receptions, TDs), converted to expected stat lines |
| Game environment | DraftKings spread and total, converted to implied team totals |
| Recent form | Last four weeks of actual points |
| Headshots | nflverse player file (official NFL photos, resized), Sleeper thumbnails and team logos as fallback |

- **This week** = 50% baseline + 50% market-implied, where a liquid market exists (`market_weight`).
- **Future weeks** = 70% baseline + 30% recent form (`recent_form_weight`).
- **Waiver / trade gain** = change in your optimal-lineup points over the rest of the season, net of what a
  free streamer would score in that slot. Trades must also help the other team and be close on player value.

## Season layer

- **Playoff odds**: 4,000 simulations of the remaining schedule using each team's weekly optimal-lineup projection.
- **Playoff weighting**: playoff weeks count 0.5x to 2.0x in waiver and trade values, scaled by your odds of being there.
- **Role growth**: snap share and touches + targets, last two games versus the two before; also nudges future projections up to 10%.
- **Rival-aware FAAB**: bid = the lower of your own ceiling and what clears the most motivated rival's estimated bid.
  Free agents who would improve this week's opponent are tagged as blocks.

## League-specific rules (per league in `config.json`)

- `victory_points`: `{win, top3, top6}`. Standings, playoff odds and the weekly outlook use VP instead of record.
- `min_partner_playoff_odds`: teams below this playoff probability are excluded as trade partners.
- `low_score_rule`: `{threshold, penalty_pts}`. Shows each player's chance of scoring at or below the threshold and
  docks that risk from lineup choices (`penalty_pts` = how many points one dud costs you).

## Sportsbook props (optional)

Add an `ODDS_API_KEY` repository secret (the-odds-api.com). Player props from US books are then averaged with the
Kalshi markets. A pull costs about 90 credits, so it only runs on `odds_api_days` (Sunday by default) to stay inside
the free 500/month tier. This path has not been exercised with a live key yet.

## Settings: `config.json`

`stream_k_def.hold_top_n`: kickers and defences are picked on this week's projection only and replace the one you hold,
unless yours is top-N for the rest of the season, in which case it is kept.


Leagues are listed in priority order. For ESPN, `my_team` is any part of your team name.

## Private ESPN leagues

Add two repository secrets (Settings → Secrets and variables → Actions): `ESPN_S2` and `ESPN_SWID`.
Both are cookies on espn.com once you are logged in (browser dev tools → Application → Cookies).

## Auto-refresh

`.github/workflows/update.yml` rebuilds the page eight times a week (including right after Wednesday waivers clear) and publishes it with GitHub Pages
(Settings → Pages → Source: GitHub Actions). Pages sites are public even when the repo is private.
The page's **Refresh now** button opens the workflow on GitHub; tap *Run workflow* for an on-demand rebuild.

## Known gaps

- Individual defensive player (IDP) slots are not modelled.
- Injured-reserve players get a flat 50% haircut on future weeks; return dates are not modelled.
- FAAB bids are a heuristic sized to lineup gain, not a model of what league-mates will bid.
