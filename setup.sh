#!/bin/bash
set -e

echo "========================================"
echo " Social Bot Setup"
echo "========================================"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 1. Python deps
echo "[1/5] Installing Python packages..."
pip3 install -r "$SCRIPT_DIR/requirements.txt" --quiet

# 2. browse CLI
echo "[2/5] Checking browse CLI..."
if ! command -v browse &>/dev/null; then
    echo "  Installing @browserbasehq/browse-cli..."
    npm install -g @browserbasehq/browse-cli
else
    echo "  browse CLI already installed: $(browse --version 2>/dev/null || echo 'ok')"
fi

# 3. .env file
echo "[3/5] Setting up .env..."
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.template" "$SCRIPT_DIR/.env"
    echo "  ⚠️  .env created — fill in your credentials:"
    echo "     nano $SCRIPT_DIR/.env"
else
    echo "  .env already exists"
fi

# 4. Init database
echo "[4/5] Initializing database..."
python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
from bot.db import init_db; init_db()
print('  DB initialized: $SCRIPT_DIR/logs/social_bot.db')
"

# 5. LaunchAgent install
echo "[5/5] Installing LaunchAgent (daily 10:05 AM)..."
PLIST_SRC="$SCRIPT_DIR/launchd/com.socialbot.daily.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.socialbot.daily.plist"

# Update Python path in plist to current python3
PYTHON_PATH="$(which python3)"
sed "s|/usr/bin/python3|$PYTHON_PATH|g" "$PLIST_SRC" > "$PLIST_DST"

# Unload if already loaded
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "  LaunchAgent loaded — next run: tomorrow 10:05 AM"

echo ""
echo "========================================"
echo " Setup complete!"
echo ""
echo " Next steps:"
echo " 1. Fill in Anthropic key: nano $SCRIPT_DIR/.env"
echo " 2. Test run:              python3 $SCRIPT_DIR/run_daily.py"
echo "    (first run: browser opens for X/Reddit login — log in once)"
echo " 3. Start dashboard:       python3 $SCRIPT_DIR/dashboard/app.py"
echo " 4. Open dashboard:        http://localhost:5050"
echo ""
echo " For another Mac: scp -r $SCRIPT_DIR/ user@newmac:~/social-bot/"
echo "                  then run setup.sh + log in once on that machine"
echo "========================================"
