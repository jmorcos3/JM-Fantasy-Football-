# Fantasy War Room

- `python3 run.py` builds `site/index.html` (standalone) and `site/artifact.html` (fragment for publishing). Standard library only.
- The dashboard must look great on iPhone as well as desktop. After any change to `advisor/report.py`, check an
  iPhone-width render in light and dark: no horizontal scroll, no decision column hidden off-screen (tables become cards under 680px).
- League-specific rules (victory points, low-score rule) live per league in `config.json`; leagues are listed in the owner's priority order.
