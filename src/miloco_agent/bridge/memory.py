"""memory_search bridge — OpenClaw prompt references this for perception memory."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from miloco_agent.config import miloco_home


def memory_search(query: str, *, days: int = 7) -> dict[str, object]:
    """Search recent perception memory markdown files under $MILOCO_HOME/memory."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "query required"}

    mem_dir = miloco_home() / "memory"
    if not mem_dir.is_dir():
        return {"ok": True, "hits": [], "message": "no memory directory"}

    pattern = re.compile(re.escape(q), re.IGNORECASE)
    hits: list[dict[str, str]] = []
    today = date.today()
    for offset in range(max(days, 1)):
        day = today - timedelta(days=offset)
        path = mem_dir / f"{day.isoformat()}-miloco-perception.md"
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                hits.append(
                    {
                        "day": day.isoformat(),
                        "line": str(line_no),
                        "text": line.strip(),
                    }
                )

    return {"ok": True, "query": q, "days": days, "hits": hits[:50]}
