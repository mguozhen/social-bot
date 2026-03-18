"""
Reddit reply automation via browse CLI (old.reddit.com).
No API key needed — uses the browser session logged in via Google OAuth.
"""
import re
import time
import logging
from typing import List, Tuple
from . import browser as B
from .ai_engine import generate_reply
from .db import log_reply, already_replied, get_today_count

logger = logging.getLogger(__name__)

LOGIN_URL  = "https://old.reddit.com/login"
BASE_URL   = "https://old.reddit.com"


# ── Login ─────────────────────────────────────────────────────────────────────

def _is_logged_in() -> bool:
    tree = B.snapshot()
    return "mguozhen" in tree or "logout" in tree.lower()


def _login_google():
    """Trigger Google OAuth login on old.reddit.com."""
    B.open_url(LOGIN_URL)
    B.wait_seconds(3)
    if _is_logged_in():
        return True

    # Click "Continue with Google" button
    tree = B.snapshot()
    google_refs = B.find_text_refs(tree, "Google")
    if not google_refs:
        # Try navigating directly to Google OAuth via new Reddit then come back
        B.open_url("https://www.reddit.com/login")
        B.wait_seconds(3)
        tree = B.snapshot()
        google_refs = B.find_text_refs(tree, "Continue as Hunter")
        if not google_refs:
            google_refs = B.find_text_refs(tree, "mguozhen")

    if google_refs:
        B.click(google_refs[0])
        B.wait_seconds(5)
        # May hit Google account chooser
        tree = B.snapshot()
        hunter_refs = B.find_text_refs(tree, "Hunter G")
        if not hunter_refs:
            hunter_refs = B.find_text_refs(tree, "mguozhen")
        if hunter_refs:
            B.click(hunter_refs[0])
            B.wait_seconds(5)

    # Verify login
    B.open_url(BASE_URL)
    B.wait_seconds(3)
    return _is_logged_in()


def _ensure_logged_in() -> bool:
    B.open_url(BASE_URL)
    B.wait_seconds(3)
    if _is_logged_in():
        logger.info("Reddit: already logged in")
        return True
    logger.info("Reddit: not logged in, attempting Google OAuth...")
    result = _login_google()
    if result:
        logger.info("Reddit: login successful")
    else:
        logger.error("Reddit: login failed")
    return result


# ── Post scraping ──────────────────────────────────────────────────────────────

def _get_subreddit_posts(subreddit: str) -> List[dict]:
    """
    Browse /r/subreddit/new/ and return list of post dicts.
    Each dict: {url, title, snippet}
    """
    B.open_url(f"{BASE_URL}/r/{subreddit}/new/")
    B.wait_seconds(3)

    tree = B.snapshot()
    posts = []

    # In old Reddit, post titles are links with sitelink class or plain links
    # Extract all post title links: pattern is "link: <Title>" followed by submission metadata
    title_pattern = r'\[(\d+-\d+)\] link: ([A-Z][^\n]{15,150})\n'
    matches = re.findall(title_pattern, tree)

    for ref, title in matches[:30]:
        # Skip sidebar/wiki links
        skip_words = ["Submit a new", "Welcome to Reddit", "How To Get", "FBA Prep",
                      "FBA Labeling", "FBA Packing", "Contacting Amazon", "Related Subs",
                      "About /r/", "wiki", "Discord", "BECOME A"]
        if any(s.lower() in title.lower() for s in skip_words):
            continue
        posts.append({"title_ref": ref, "title": title, "url": None})

    return posts[:20]


def _get_post_url_and_content(post: dict) -> Tuple[str, str]:
    """Click on a post title, return (url, selftext_snippet)."""
    B.click(post["title_ref"])
    B.wait_seconds(3)
    url = B.get_url()
    tree = B.snapshot()

    # Grab text content of the post body
    text_blocks = re.findall(r'StaticText: ([^\n]{20,})', tree)
    snippet = " ".join(text_blocks[:8])[:600]
    return url, snippet


# ── Commenting ─────────────────────────────────────────────────────────────────

def _post_comment(reply_text: str) -> bool:
    """
    Assumes we're already on an old.reddit.com post page.
    Finds the comment textarea, types the reply, clicks save.
    """
    tree = B.snapshot()

    # Find comment textarea ref
    textarea_refs = re.findall(r'\[(\d+-\d+)\] textbox(?!\: search)', tree)
    if not textarea_refs:
        # Fallback: look for any textarea near "save" button
        save_refs = re.findall(r'\[(\d+-\d+)\] button: save', tree, re.I)
        if not save_refs:
            logger.warning("Reddit: no comment form found")
            return False
        # Find textarea before save button in tree
        save_idx = tree.find(save_refs[0])
        chunk = tree[max(0, save_idx - 2000):save_idx]
        textarea_refs = re.findall(r'\[(\d+-\d+)\] textbox', chunk)

    if not textarea_refs:
        return False

    B.click(textarea_refs[-1])
    B.wait_seconds(1)

    # Type reply paragraph by paragraph
    paragraphs = reply_text.split("\n\n")
    for i, para in enumerate(paragraphs):
        # Remove dollar signs to avoid shell variable expansion
        safe = para.replace("$", "").strip()
        if safe:
            B.type_text(safe)
        if i < len(paragraphs) - 1:
            B.press("Enter")
            B.press("Enter")

    B.wait_seconds(1)

    # Find and click save button
    tree = B.snapshot()
    save_refs = re.findall(r'\[(\d+-\d+)\] button: save', tree, re.I)
    if not save_refs:
        return False

    B.click(save_refs[0])
    B.wait_seconds(4)

    # Verify: comment should appear with "mguozhen" and "just now"
    confirm_tree = B.snapshot()
    return "mguozhen" in confirm_tree and (
        "just now" in confirm_tree or "1 minute ago" in confirm_tree
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def run(config: dict) -> dict:
    """
    Main entry point. Returns summary dict.
    config: from config.json["reddit"]
    """
    target     = config["daily_target"]
    subreddits = config["subreddits"]
    delay      = config["min_delay_seconds"]

    summary = {"posted": 0, "failed": 0, "skipped": 0, "target": target}

    if not _ensure_logged_in():
        logger.error("Reddit: cannot proceed without login")
        return summary

    today_count = get_today_count("reddit")
    if today_count >= target:
        logger.info(f"Reddit: already hit target ({today_count}/{target})")
        summary["posted"] = today_count
        return summary

    for subreddit in subreddits:
        if get_today_count("reddit") >= target:
            break

        logger.info(f"Reddit: scanning r/{subreddit}")
        posts = _get_subreddit_posts(subreddit)

        for post in posts:
            if get_today_count("reddit") >= target:
                break

            # Open post and get URL + content
            try:
                post_url, snippet = _get_post_url_and_content(post)
            except Exception as e:
                logger.warning(f"Reddit: failed to open post — {e}")
                B.press("Alt+Left")
                B.wait_seconds(2)
                summary["skipped"] += 1
                continue

            if already_replied(post_url):
                B.press("Alt+Left")
                B.wait_seconds(1)
                summary["skipped"] += 1
                continue

            # Generate reply
            reply_text, product = generate_reply(
                post_title=post["title"],
                post_content=snippet,
                platform="reddit"
            )

            if not reply_text:
                B.press("Alt+Left")
                B.wait_seconds(1)
                summary["skipped"] += 1
                continue

            # Post comment
            success = _post_comment(reply_text)

            if success:
                log_reply("reddit", post_url, post["title"],
                          snippet[:200], reply_text, product, "posted")
                summary["posted"] += 1
                logger.info(f"Reddit: posted #{summary['posted']} — {post['title'][:60]}")
                B.press("Alt+Left")
                B.wait_seconds(delay)
            else:
                log_reply("reddit", post_url, post["title"],
                          snippet[:200], reply_text, product, "failed",
                          "comment not confirmed")
                summary["failed"] += 1
                logger.warning(f"Reddit: comment failed — {post['title'][:60]}")
                B.press("Alt+Left")
                B.wait_seconds(15)

    return summary
