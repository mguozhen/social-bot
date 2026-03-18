#!/usr/bin/env python3
"""
Social Bot Dashboard — Flask web app.
Run: python dashboard/app.py
Open: http://localhost:5050
"""
import sys
import json
from pathlib import Path
from datetime import date, timedelta
from flask import Flask, render_template, jsonify
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent.parent))
from bot.db import get_stats, get_recent_replies, get_today_count, init_db

app = Flask(__name__)
CORS(app)

CONFIG = json.loads((Path(__file__).parent.parent / "config.json").read_text())


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/overview")
def api_overview():
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    stats = get_stats(days=30)
    today_stats  = [s for s in stats if s["day"] == today]
    ytd_stats    = [s for s in stats if s["day"] == yesterday]

    def sum_field(rows, field):
        return sum(r.get(field, 0) for r in rows)

    x_today     = next((s for s in today_stats if s["platform"] == "x"), {})
    r_today     = next((s for s in today_stats if s["platform"] == "reddit"), {})
    x_ytd       = next((s for s in ytd_stats  if s["platform"] == "x"), {})
    r_ytd       = next((s for s in ytd_stats  if s["platform"] == "reddit"), {})

    return jsonify({
        "today": {
            "x_posted":       x_today.get("posted", 0),
            "x_target":       CONFIG["x"]["daily_target"],
            "reddit_posted":  r_today.get("posted", 0),
            "reddit_target":  CONFIG["reddit"]["daily_target"],
            "total_posted":   x_today.get("posted", 0) + r_today.get("posted", 0),
        },
        "yesterday": {
            "x_posted":      x_ytd.get("posted", 0),
            "reddit_posted": r_ytd.get("posted", 0),
        },
        "total_all_time": sum_field(stats, "posted"),
        "solvea_mentions": _count_product("Solvea"),
        "voc_mentions":    _count_product("VOC.ai"),
    })


@app.route("/api/chart/daily")
def api_chart_daily():
    stats = get_stats(days=30)
    # Build per-day totals
    days = {}
    for s in stats:
        d = s["day"]
        if d not in days:
            days[d] = {"x": 0, "reddit": 0}
        days[d][s["platform"]] = s.get("posted", 0)

    labels = sorted(days.keys())
    return jsonify({
        "labels": labels,
        "x":      [days[d]["x"]      for d in labels],
        "reddit": [days[d]["reddit"] for d in labels],
    })


@app.route("/api/replies")
def api_replies():
    replies = get_recent_replies(limit=100)
    return jsonify(replies)


def _count_product(name: str) -> int:
    from bot.db import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM replies WHERE product=? AND status='posted'",
            (name,)
        ).fetchone()
        return row["cnt"] if row else 0


if __name__ == "__main__":
    init_db()
    print("Dashboard: http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False)
