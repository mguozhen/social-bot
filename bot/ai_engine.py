import os
import anthropic
import json
from pathlib import Path
from typing import Optional, Tuple

CONFIG = json.loads((Path(__file__).parent.parent / "config.json").read_text())


def detect_product(text: str) -> Optional[str]:
    """Return 'Solvea', 'VOC.ai', or None based on keyword match."""
    text_lower = text.lower()
    scores = {}
    for product, data in CONFIG["products"].items():
        score = sum(1 for kw in data["trigger_keywords"] if kw in text_lower)
        if score > 0:
            scores[product] = score
    if not scores:
        return None
    return max(scores, key=scores.get)


def generate_reply(post_title: str, post_content: str, platform: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (reply_text, product_mentioned) or (None, None) if should skip.
    """
    product = detect_product(f"{post_title} {post_content}")
    if not product:
        return None, None

    product_desc = CONFIG["products"][product]["description"]
    style_rules = "\n".join(f"- {r}" for r in CONFIG["reply_style"]["rules"])
    max_len = (CONFIG["reply_style"]["max_length_x"] if platform == "x"
               else CONFIG["reply_style"]["max_length_reddit"])

    system_prompt = f"""You are a hands-on Amazon/Shopify seller and builder who has been selling for 5+ years.
You reply to social media posts with genuine insights from your own experience.
You sometimes mention {product} ({product_desc}) as a tool you personally use — but only when it's directly relevant.

Reply style rules:
{style_rules}

Max length: {max_len} characters for {platform}. Be concise."""

    user_prompt = f"""Post title: {post_title}

Post content:
{post_content[:800]}

Write a reply that adds real value. Mention {product} only if it fits naturally.
If it doesn't fit, reply with just: SKIP
Output only the reply text, nothing else."""

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
    )
    reply = message.content[0].text.strip()

    if reply.upper().startswith("SKIP") or len(reply) < 20:
        return None, None

    # Trim to platform max
    if len(reply) > max_len + 50:
        reply = reply[:max_len].rsplit(" ", 1)[0] + "..."

    return reply, product


def analyze_lead(post_title: str, post_content: str, post_url: str, platform: str) -> Optional[dict]:
    """
    判断发帖人是否是 Solvea 的潜在客户，并提取关键信息。
    返回 dict 或 None（不是潜在客户）。
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_prompt = f"""Analyze this social media post and determine if the author is a potential customer for Solvea.

Solvea is an AI customer support agent for Shopify/ecommerce stores that:
- Autonomously handles support tickets (tracking, returns, product questions)
- Integrates directly with Shopify to take actions (process returns, update shipping)
- Provides a unified inbox for human handoff

Post URL: {post_url}
Platform: {platform}
Title: {post_title}
Content: {post_content[:600]}

Respond in JSON only:
{{
  "is_lead": true/false,
  "lead_score": 1-10,
  "pain_points": ["list of pain points mentioned"],
  "business_type": "shopify store / amazon seller / saas / other / unknown",
  "urgency": "high / medium / low",
  "reason": "one sentence why they are or aren't a lead"
}}

Only return JSON, nothing else."""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = msg.content[0].text.strip()
        # Extract JSON
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if not json_match:
            return None
        data = json.loads(json_match.group())
        if not data.get("is_lead"):
            return None
        data["post_url"] = post_url
        data["platform"] = platform
        data["post_title"] = post_title
        return data
    except Exception:
        return None
