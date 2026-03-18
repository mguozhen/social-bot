---
name: social-reply-bot
description: "Auto-reply bot for Reddit and X/Twitter. Searches relevant posts about ecommerce/Amazon seller topics and posts AI-generated replies mentioning Solvea or VOC.ai naturally. Triggers: social reply bot, reddit auto reply, twitter auto reply, x auto reply, social media bot, amazon seller engagement, ecommerce social engagement"
allowed-tools: Bash
metadata:
  openclaw:
    homepage: https://github.com/mguozhen/social-bot
---

# Social Reply Bot

Automatically finds and replies to relevant Reddit and X/Twitter posts about ecommerce, Amazon FBA, and customer service AI — posting as your configured accounts.

## Usage

```
Run both platforms (daily targets from config):
social reply bot

Run X only:
social reply bot x only

Run Reddit only:
social reply bot reddit only

Check today's stats:
social reply bot stats

Open dashboard:
social reply bot dashboard
```

## Setup (first time)

```bash
cd ~/social-bot
cp .env.template .env
# Edit .env and set ANTHROPIC_API_KEY
nano .env

# Install dependencies and init DB
bash setup.sh
```

## Requirements

- `browse` CLI installed (`npm install -g @browserbasehq/browse-cli`)
- Browser sessions logged in to Reddit and X
- `ANTHROPIC_API_KEY` in `.env`

## What it does

1. Searches configured subreddits / X queries for relevant posts
2. Uses Claude AI to generate genuine, on-topic replies
3. Mentions Solvea or VOC.ai naturally when relevant
4. Posts via browser automation (no platform API needed)
5. Tracks all replies in SQLite with dedup
6. Dashboard at `http://localhost:5050`

## Configuration

Edit `~/social-bot/config.json` to change:
- Target subreddits and X search queries
- Daily reply targets per platform
- Product descriptions and trigger keywords
- Reply tone and style rules
