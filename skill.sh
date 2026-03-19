#!/bin/bash
# social-reply-bot skill entry point
# Called by openclaw with user's prompt as $*

set -e

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPT="$(echo "$*" | tr '[:upper:]' '[:lower:]')"

# Load env
if [ -f "$BOT_DIR/.env" ]; then
    set -a
    source "$BOT_DIR/.env"
    set +a
fi

# Check ANTHROPIC_API_KEY
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ERROR: ANTHROPIC_API_KEY not set. Edit $BOT_DIR/.env"
    exit 1
fi

# Check browse CLI
if ! command -v browse &>/dev/null; then
    echo "ERROR: browse CLI not found. Run: npm install -g @browserbasehq/browse-cli"
    exit 1
fi

cd "$BOT_DIR"

# Route by prompt keywords
if echo "$PROMPT" | grep -qE "warmup|warm up|karma|养号"; then
    COUNT=8
    if echo "$PROMPT" | grep -qE "[0-9]+"; then
        COUNT=$(echo "$PROMPT" | grep -oE "[0-9]+" | head -1)
    fi
    echo "Running Reddit warmup — target ${COUNT} comments..."
    python3 "$BOT_DIR/warmup_reddit.py" "$COUNT"
elif echo "$PROMPT" | grep -qE "leads|客户|potential customer"; then
    echo "=== Solvea Leads ==="
    python3 -c "
import sys, json; sys.path.insert(0, '.')
from bot.db import get_leads
leads = get_leads(7)
if not leads:
    print('No leads found in last 7 days.')
else:
    print(f'Found {len(leads)} leads in last 7 days:\n')
    for l in leads:
        pain = json.loads(l.get('pain_points','[]'))
        print(f\"[{l['lead_score']}/10] [{l['urgency'].upper()}] {l['platform'].upper()}\")
        print(f\"  Title: {l['post_title']}\")
        print(f\"  Type:  {l['business_type']}\")
        print(f\"  Pain:  {', '.join(pain[:2])}\")
        print(f\"  Why:   {l['reason']}\")
        print(f\"  URL:   {l['post_url']}\")
        print()
"
elif echo "$PROMPT" | grep -qE "stat|count|how many|report"; then
    echo "=== Social Bot Stats ==="
    python3 -c "
import sys; sys.path.insert(0, '.')
from bot.db import get_stats, get_today_count
print('Today: X=%d  Reddit=%d' % (get_today_count('x'), get_today_count('reddit')))
stats = get_stats(7)
if stats:
    print('\nLast 7 days:')
    for s in stats[:14]:
        print('  %s [%s] posted=%d failed=%d' % (s['day'], s['platform'], s['posted'], s['failed']))
else:
    print('No data yet.')
"
elif echo "$PROMPT" | grep -qE "dashboard|ui|open|browser"; then
    echo "Starting dashboard at http://localhost:5050 ..."
    python3 "$BOT_DIR/dashboard/app.py" &
    sleep 2
    open http://localhost:5050
    echo "Dashboard opened."
elif echo "$PROMPT" | grep -qE "x only|twitter only|tweet only"; then
    echo "Running X/Twitter bot..."
    python3 "$BOT_DIR/run_daily.py" --x-only
elif echo "$PROMPT" | grep -qE "reddit only"; then
    echo "Running Reddit bot..."
    python3 "$BOT_DIR/run_daily.py" --reddit-only
else
    echo "Running both X and Reddit bots..."
    python3 "$BOT_DIR/run_daily.py"
fi
