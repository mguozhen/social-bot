"""
X/Twitter reply automation via browse CLI.
Searches for relevant posts and posts replies as @VocAiSage.
"""
import re
import time
import logging
from typing import List
from . import browser as B
from .ai_engine import generate_reply, analyze_lead
from .db import log_reply, already_replied, get_today_count, save_lead

logger = logging.getLogger(__name__)

LOGIN_URL  = "https://x.com/login"
SEARCH_URL = "https://x.com/search?q={query}&src=typed_query&f=live"


def _is_logged_in() -> bool:
    tree = B.snapshot()
    return "VocAiSage" in tree or "Hunter Guo" in tree


def _login_if_needed():
    """Open X and check login. If not logged in, open login page for manual auth."""
    B.open_url("https://x.com")
    B.wait_seconds(3)
    if _is_logged_in():
        logger.info("X: already logged in")
        return True
    logger.warning("X: not logged in — opening login page")
    B.open_url(LOGIN_URL)
    # Wait up to 60s for user to log in (for first-run setup)
    for _ in range(12):
        B.wait_seconds(5)
        if _is_logged_in():
            logger.info("X: login confirmed")
            return True
    logger.error("X: login timeout")
    return False


def _search_posts(query: str) -> List[dict]:
    """Search X and return list of {snippet, time_ref} dicts."""
    url = SEARCH_URL.format(query=query.replace(" ", "+"))
    B.open_url(url)
    B.wait_seconds(3)

    posts = []
    tree = B.snapshot()

    # Find article start positions in the full tree
    article_positions = [(m.start(), m.group(1)) for m in
                         re.finditer(r'\[(\d+-\d+)\] article:', tree)]

    for i, (pos, article_ref) in enumerate(article_positions[:15]):
        # Article block ends where next top-level sibling starts
        next_pos = article_positions[i + 1][0] if i + 1 < len(article_positions) else len(tree)
        block = tree[pos:next_pos]

        # Time link: [ref] link: Mar 16  OR  link: 5h  OR  link: just now
        time_match = re.search(
            r'\[(\d+-\d+)\] link: (?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+|\d+[hm]|just now)',
            block
        )
        if not time_match:
            continue

        time_ref = time_match.group(1)

        # Snippet from StaticText nodes (skip very short ones like emojis/counts)
        texts = re.findall(r'StaticText: ([^\n]{10,})', block)
        snippet = " ".join(texts[:6])[:350]

        posts.append({
            "article_ref": article_ref,
            "time_ref": time_ref,
            "snippet": snippet,
        })

    return posts


def _reply_current_page(reply_text: str) -> bool:
    """Type and submit a reply on the currently open tweet page."""
    tree = B.snapshot()

    # Find reply textbox
    boxes = re.findall(r'\[(\d+-\d+)\] textbox: Post text', tree)
    if not boxes:
        return False

    B.click(boxes[0])
    B.wait_seconds(1)

    # Type reply paragraph by paragraph
    paragraphs = reply_text.split("\n\n")
    for i, para in enumerate(paragraphs):
        safe_para = para.replace("$", "")
        B.type_text(safe_para)
        if i < len(paragraphs) - 1:
            B.press("Enter")
            B.press("Enter")

    B.wait_seconds(1)

    # Find and click reply button
    tree = B.snapshot()
    reply_btns = re.findall(r'\[(\d+-\d+)\] button: Reply', tree)
    if len(reply_btns) >= 2:
        B.click(reply_btns[-1])
        B.wait_seconds(3)
        confirm_tree = B.snapshot()
        return "Your post was sent" in confirm_tree or "post was sent" in confirm_tree.lower()

    return False


def run(config: dict) -> dict:
    """
    Main entry point. Returns summary dict.
    config: from config.json["x"]
    """
    target = config["daily_target"]
    queries = config["search_queries"]
    delay = config["min_delay_seconds"]

    summary = {"posted": 0, "failed": 0, "skipped": 0, "target": target}

    if not _login_if_needed():
        logger.error("X: cannot proceed without login")
        return summary

    today_count = get_today_count("x")
    if today_count >= target:
        logger.info(f"X: already hit target ({today_count}/{target})")
        summary["posted"] = today_count
        return summary

    for query in queries:
        if get_today_count("x") >= target:
            break

        logger.info(f"X: searching '{query}'")
        posts = _search_posts(query)

        for post in posts:
            if get_today_count("x") >= target:
                break

            snippet = post.get("snippet", "")
            if not snippet or len(snippet) < 30:
                continue

            # Build a fake URL key for dedup (we don't have URL yet)
            # We'll update after opening
            reply_text, product = generate_reply(
                post_title=query,
                post_content=snippet,
                platform="x"
            )

            if not reply_text:
                summary["skipped"] += 1
                continue

            # Open tweet, get real URL, dedup check, then reply (single open)
            if not post.get("time_ref"):
                summary["skipped"] += 1
                continue

            B.click(post["time_ref"])
            B.wait_seconds(3)
            real_url = B.get_url()

            if already_replied(real_url):
                B.press("Alt+Left")
                B.wait_seconds(2)
                summary["skipped"] += 1
                continue

            # Already on tweet page — reply directly
            success = _reply_current_page(reply_text)

            if success:
                log_reply("x", real_url, query, snippet, reply_text, product, "posted")
                summary["posted"] += 1
                logger.info(f"X: posted reply #{summary['posted']} — {real_url}")
                # Lead analysis
                lead = analyze_lead(query, snippet, real_url, "x")
                if lead:
                    save_lead(lead)
                    logger.info(f"X: 🎯 lead saved score={lead.get('lead_score')} urgency={lead.get('urgency')}")
                time.sleep(delay)
            else:
                log_reply("x", real_url, query, snippet, reply_text, product, "failed")
                summary["failed"] += 1
                logger.warning(f"X: failed to post — {real_url}")
                time.sleep(10)

    return summary
