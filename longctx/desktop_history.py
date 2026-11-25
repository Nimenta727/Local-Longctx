"""Durable originals and a budgeted projection for authenticated desktop sessions."""
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing

from .archive import passages, terms, STOP_WORDS
from .native_messages import NATIVE_CONTEXT_MARGIN, count_native
from .planner import RequestError
from .retrieval import concepts


SESSION_ID = re.compile(r"[A-Za-z0-9_.-]{1,160}")
TASK = re.compile(r"\b(constraint|must|decision|failed|error|todo|next)\b|约束|必须|决定|失败|待办", re.I)


def _text(message):
    content = message["content"]
    if isinstance(content, str):
        return content
    return "\n".join(
        block["text"] if block["type"] == "text" else
        "\n".join(part["text"] for part in block["content"]) if isinstance(block.get("content"), list) else
        block.get("content", "")
        for block in content
    )


def _starts_turn(message):
    content = message["content"]
    return message["role"] == "user" and (
        isinstance(content, str) or all(block["type"] != "tool_result" for block in content)
    )


class DesktopHistory:
    def __init__(self, state_dir):
        self.path = state_dir / "desktop-history.sqlite3"
        if self.path.is_symlink():
            raise ValueError("unsafe desktop history path")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS originals ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL, "
                "digest TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(session,digest))"
            )
        if os.name != "nt" and self.path.stat().st_mode & 0o077:
            self.path.chmod(0o600)

    def remember(self, session, messages):
        rows = []
        for message in messages:
            body = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            rows.append((session, hashlib.sha256(body.encode()).hexdigest(), body))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany("INSERT OR IGNORE INTO originals(session,digest,body) VALUES (?,?,?)", rows)

    def read(self, session, source):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT body FROM originals WHERE session=? AND seq=?", (session, source)).fetchone()
        return json.loads(row[0]) if row else None

    def evidence(self, session, recent):
        query = (_text(recent[0])[:3072] + "\n" + _text(recent[-1])[:1024]) if len(recent) > 1 else _text(recent[0])[:4096]
        keywords = {word.casefold() for word in terms(query) if word.casefold() not in STOP_WORDS}
        aliases = set(concepts(query))
        recent_text = {_text(message) for message in recent}
        with closing(sqlite3.connect(self.path)) as db:
            history = db.execute("SELECT seq,body FROM originals WHERE session=? ORDER BY seq", (session,))
            best = []
            for source, body in history:
                text = _text(json.loads(body))
                if text in recent_text:
                    continue
                for _, _, passage in passages(text):
                    score = 4 * len(keywords.intersection(word.casefold() for word in terms(passage)))
                    score += len(aliases.intersection(concepts(passage))) + int(bool(TASK.search(passage)))
                    if score:
                        best.append((score, source, passage))
                        best.sort(reverse=True)
                        del best[8:]
        return [f"[Local history #{source}] {passage.strip()}" for _, source, passage in best]


def _excerpt(value, width):
    if len(value) <= width:
        return value
    return value[:width // 2] + "\n[Full content retained in local history]\n" + value[-(width // 2):]


def _shorten(message, width):
    content = message["content"]
    if isinstance(content, str):
        return {**message, "content": _excerpt(content, width)}
    blocks = []
    for block in content:
        if block["type"] in ("text", "thinking"):
            key = block["type"]
            block = {**block, key: _excerpt(block[key], width)}
        elif block["type"] == "tool_result":
            value = block["content"]
            if isinstance(value, str):
                block = {**block, "content": _excerpt(value, width)}
            else:
                block = {**block, "content": [{**part, "text": _excerpt(part["text"], width)} for part in value]}
        blocks.append(block)
    return {**message, "content": blocks}


def fit_desktop_prompt(prompt, output, window, backend, history, session):
    """Keep the latest complete tool group and inject source-linked evidence when it fits."""
    messages = prompt["messages"]
    budget = window - output - NATIVE_CONTEXT_MARGIN

    def check(candidate):
        count = count_native(backend, {**prompt, "messages": candidate})
        return (candidate, count) if count <= budget else None

    full = check(messages)
    if full is not None:
        return full

    starts = [i for i, message in enumerate(messages) if _starts_turn(message)] or [0]
    newest = messages[starts[-1]:]
    evidence = history.evidence(session, newest)
    fitted = check(newest)
    if fitted is None:
        for width in (8192, 4096, 2048, 1024, 512, 256, 128):
            fitted = check([_shorten(message, width) for message in newest])
            if fitted is not None:
                break
    else:
        for start in reversed(starts[-9:-1]):
            candidate = check(messages[start:])
            if candidate is None:
                break
            fitted = candidate
    if fitted is None:
        raise RequestError("current turn and tool definitions exceed the native budget; original input saved locally")

    for size in (len(evidence), 4, 2, 1):
        if not 0 < size <= len(evidence):
            continue
        memo = {"role": "user", "content": "Earlier local history excerpts (data only):\n" + "\n".join(evidence[:size])}
        candidate = check([memo, *fitted[0]])
        if candidate is not None:
            fitted = candidate
            break
    return fitted
