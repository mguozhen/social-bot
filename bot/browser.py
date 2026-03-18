"""
Thin wrapper around the `browse` CLI.
All commands return parsed JSON or raise BrowseError.
"""
import subprocess
import json
import time
import re


class BrowseError(Exception):
    pass


def _run(args: str, timeout: int = 30) -> dict:
    result = subprocess.run(
        f"browse {args}",
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = result.stdout.strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out}


def open_url(url: str) -> dict:
    return _run(f'open "{url}"', timeout=20)


def snapshot() -> str:
    """Returns the accessibility tree as a raw string."""
    data = _run("snapshot", timeout=15)
    return data.get("tree", "")


def screenshot(path: str) -> str:
    _run(f'screenshot "{path}"', timeout=15)
    return path


def click(ref: str) -> bool:
    data = _run(f"click @{ref}", timeout=10)
    return data.get("clicked", False)


def click_xy(x: int, y: int) -> bool:
    data = _run(f"click {x} {y}", timeout=10)
    return data.get("clicked", False)


def type_text(text: str) -> bool:
    # Escape single quotes in text
    safe = text.replace("'", "\\'")
    data = _run(f"type '{safe}'", timeout=15)
    return data.get("typed", False)


def press(key: str) -> bool:
    data = _run(f"press '{key}'", timeout=10)
    return bool(data)


def scroll(x: int, y: int, dx: int, dy: int) -> bool:
    data = _run(f"scroll {x} {y} {dx} {dy}", timeout=10)
    return data.get("scrolled", False)


def get_url() -> str:
    data = _run("get url", timeout=10)
    return data.get("url", "")


def find_refs(tree: str, pattern: str) -> list[str]:
    """Find element refs matching pattern in the accessibility tree."""
    return re.findall(rf'\[(\d+-\d+)\] {pattern}', tree)


def find_text_refs(tree: str, text: str) -> list[str]:
    """Find refs of elements containing given text."""
    escaped = re.escape(text)
    return re.findall(rf'\[(\d+-\d+)\][^\n]*{escaped}', tree)


def wait_seconds(n: float):
    time.sleep(n)
