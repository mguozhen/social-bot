"""
Reddit reply automation via browse CLI (old.reddit.com).
No API key needed — uses the browser session logged in via Google OAuth.
"""
import re
import time
import logging
from typing import List, Tuple
from . import browser as B
from .ai_engine import generate_reply, analyze_lead
from .db import log_reply, already_replied, get_today_count, save_lead

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
    Browse /r/subreddit/new/ and collect (title, comment_count) for each post.
    Returns list of dicts with {title, comment_count}. No navigation needed.
    """
    B.open_url(f"{BASE_URL}/r/{subreddit}/new/")
    B.wait_seconds(3)

    tree = B.snapshot()
    posts = []

    # In old Reddit each post row has: title link followed by "submitted X ago" then "N comments"
    # Pair title links with comment links by scanning "submitted" anchors
    submitted_positions = [m.start() for m in re.finditer(r'\bsubmitted\b', tree)]
    comment_positions = [(m.start(), m.group(1)) for m in
                         re.finditer(r'\[(\d+-\d+)\] link: (\d+ comments?)', tree)]

    seen_titles = set()
    for pos in submitted_positions[:30]:
        # Title link: last link before 'submitted'
        chunk_before = tree[max(0, pos - 1500):pos]
        links_before = re.findall(r'\[(\d+-\d+)\] link: ([^\n]{15,200})', chunk_before)
        if not links_before:
            continue
        _ref, title = links_before[-1]
        title = title.strip()

        skip_words = ["Submit a new", "Welcome to", "How To Get", "Contacting Amazon",
                      "About /r/", "wiki", "Discord", "/r/", "http", "View Poll"]
        if any(s.lower() in title.lower() for s in skip_words):
            continue
        if title in seen_titles:
            continue

        # Comment count: first comment link after 'submitted'
        comment_count = 0
        for cpos, cref in comment_positions:
            if cpos > pos:
                m = re.search(r'(\d+)', tree[cpos:cpos+100])
                comment_count = int(m.group(1)) if m else 0
                break

        seen_titles.add(title)
        posts.append({"title": title, "comment_count": comment_count})

    return posts[:20]


def _navigate_and_get_content(post_index: int, subreddit: str) -> Tuple[str, str]:
    """
    From the subreddit listing, click the Nth comment link to open post.
    Returns (url, snippet).
    """
    tree = B.snapshot()
    comment_links = re.findall(r'\[(\d+-\d+)\] link: \d+ comments?', tree)
    if post_index >= len(comment_links):
        return "", ""
    B.click(comment_links[post_index])
    B.wait_seconds(3)
    url = B.get_url()
    tree2 = B.snapshot()
    text_blocks = re.findall(r'StaticText: ([^\n]{20,})', tree2)
    snippet = " ".join(text_blocks[:10])[:700]
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
        # We're now on the subreddit listing page

        visited = 0
        for post in posts:
            if get_today_count("reddit") >= target:
                break

            # From listing, click Nth comment link (fresh snapshot each time)
            try:
                tree = B.snapshot()
                comment_links = re.findall(r'\[(\d+-\d+)\] link: \d+ comments?', tree)
                if visited >= len(comment_links):
                    break
                B.click(comment_links[visited])
                B.wait_seconds(3)
                post_url = B.get_url()
            except Exception as e:
                logger.warning(f"Reddit: nav failed — {e}")
                B.open_url(f"{BASE_URL}/r/{subreddit}/new/")
                B.wait_seconds(3)
                visited += 1
                summary["skipped"] += 1
                continue

            visited += 1

            if already_replied(post_url):
                B.open_url(f"{BASE_URL}/r/{subreddit}/new/")
                B.wait_seconds(2)
                summary["skipped"] += 1
                continue

            # Get post content — skip sidebar, anchor on post title
            tree = B.snapshot()
            title_idx = tree.find(post["title"][:40])
            if title_idx > 0:
                # Extract StaticText after the title (post body + comments)
                chunk = tree[title_idx:title_idx + 3000]
            else:
                chunk = tree[len(tree) // 2:]  # fallback: second half of tree
            text_blocks = re.findall(r'StaticText: ([^\n]{15,})', chunk)
            # Skip meta lines (submitted, by, share, save, etc.)
            meta = {"submitted", "by", "share", "save", "hide", "report",
                    "crosspost", "sorted by:", "best", "formatting help"}
            clean = [t for t in text_blocks if t.strip().lower() not in meta]
            snippet = " ".join(clean[:12])[:700]

            reply_text, product = generate_reply(
                post_title=post["title"],
                post_content=snippet,
                platform="reddit"
            )
            if not reply_text:
                B.open_url(f"{BASE_URL}/r/{subreddit}/new/")
                B.wait_seconds(2)
                summary["skipped"] += 1
                continue

            success = _post_comment(reply_text)

            if success:
                log_reply("reddit", post_url, post["title"],
                          snippet[:200], reply_text, product, "posted")
                summary["posted"] += 1
                logger.info(f"Reddit: posted #{summary['posted']} — {post['title'][:60]}")
                # Lead analysis
                lead = analyze_lead(post["title"], snippet, post_url, "reddit")
                if lead:
                    save_lead(lead)
                    logger.info(f"Reddit: 🎯 lead saved score={lead.get('lead_score')} urgency={lead.get('urgency')}")
            else:
                log_reply("reddit", post_url, post["title"],
                          snippet[:200], reply_text, product, "failed",
                          "comment not confirmed")
                summary["failed"] += 1
                logger.warning(f"Reddit: comment failed — {post['title'][:60]}")

            B.open_url(f"{BASE_URL}/r/{subreddit}/new/")
            B.wait_seconds(delay if success else 10)

    return summary
