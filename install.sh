#!/bin/bash
# ============================================================
#  Social Reply Bot — One-command installer
#  Works on any macOS with Homebrew + Python 3
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/mguozhen/social-bot/main/install.sh | bash
#  Or after cloning:
#    bash install.sh
# ============================================================

set -e

REPO_URL="https://github.com/mguozhen/social-bot.git"
INSTALL_DIR="$HOME/social-bot"
PYTHON="python3"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     Social Reply Bot Installer       ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Clone or update repo ──────────────────────────────────
echo "[1/6] Getting latest code..."
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"
    git pull --ff-only
    echo "  Updated existing repo at $INSTALL_DIR"
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    echo "  Cloned to $INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# ── 2. Python dependencies ───────────────────────────────────
echo "[2/6] Installing Python packages..."
$PYTHON -m pip install -r requirements.txt --quiet
echo "  Done: anthropic, flask, flask-cors, python-dotenv"

# ── 3. browse CLI ────────────────────────────────────────────
echo "[3/6] Checking browse CLI..."
if ! command -v browse &>/dev/null; then
    if command -v npm &>/dev/null; then
        npm install -g @browserbasehq/browse-cli --silent
        echo "  Installed browse CLI"
    else
        echo "  WARNING: npm not found. Install Node.js then run:"
        echo "    npm install -g @browserbasehq/browse-cli"
    fi
else
    echo "  browse CLI already installed ($(browse --version 2>/dev/null || echo 'ok'))"
fi

# ── 4. .env file ─────────────────────────────────────────────
echo "[4/6] Setting up credentials..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.template" "$INSTALL_DIR/.env"
    echo ""
    echo "  ┌─────────────────────────────────────────────┐"
    echo "  │  ACTION REQUIRED: Add your API key          │"
    echo "  │                                             │"
    echo "  │  nano $INSTALL_DIR/.env    │"
    echo "  │  Set: ANTHROPIC_API_KEY=sk-ant-...          │"
    echo "  └─────────────────────────────────────────────┘"
    echo ""
    read -p "  Press Enter after editing .env to continue..." _
else
    echo "  .env already configured"
fi

# ── 5. Database init ─────────────────────────────────────────
echo "[5/6] Initializing database..."
$PYTHON -c "
import sys; sys.path.insert(0, '$INSTALL_DIR')
from bot.db import init_db; init_db()
print('  DB ready: $INSTALL_DIR/logs/social_bot.db')
"

# ── 6. LaunchAgent ───────────────────────────────────────────
echo "[6/6] Installing LaunchAgent (daily 10:05 AM)..."
PLIST_SRC="$INSTALL_DIR/launchd/com.socialbot.daily.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.socialbot.daily.plist"
mkdir -p "$HOME/Library/LaunchAgents"

# Inject real python3 path and API key
PYTHON_PATH="$(which $PYTHON)"
API_KEY="$(grep ANTHROPIC_API_KEY "$INSTALL_DIR/.env" | cut -d= -f2 | tr -d ' ')"

sed \
    -e "s|/usr/bin/python3|$PYTHON_PATH|g" \
    -e "s|FILL_IN|$API_KEY|g" \
    -e "s|/Users/guozhen|$HOME|g" \
    "$PLIST_SRC" > "$PLIST_DST"

launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "  LaunchAgent loaded — will run daily at 10:05 AM"

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Installation complete!                              ║"
echo "║                                                      ║"
echo "║  Next steps:                                         ║"
echo "║  1. Open browser and log in to Reddit + X manually  ║"
echo "║     (just visit the sites — sessions are shared)    ║"
echo "║  2. Test run:                                        ║"
echo "║     cd $HOME/social-bot                             ║"
echo "║     python3 run_daily.py --x-only                   ║"
echo "║  3. Dashboard: python3 dashboard/app.py             ║"
echo "║     Open: http://localhost:5050                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
