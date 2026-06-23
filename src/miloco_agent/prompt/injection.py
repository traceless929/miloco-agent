"""Home profile file helpers + pending habit suggestion injection."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from miloco_agent.config import miloco_home

_SH_TZ = timezone(timedelta(hours=8))


def home_profile_path() -> Path:
    return miloco_home() / "home-profile" / "profile.md"


def habit_suggestions_path() -> Path:
    return miloco_home() / "home-profile" / "task-suggestions.json"


def load_home_profile_markdown() -> str:
    path = home_profile_path()
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def build_home_profile_block() -> str:
    md = load_home_profile_markdown()
    if not md or md == "(暂无内容)":
        return ""
    demoted = []
    for line in md.splitlines():
        if line.startswith("#"):
            demoted.append("#" + line)
        else:
            demoted.append(line)
    body = "\n".join(demoted)
    return body if body.startswith("## 家庭档案") else f"## 家庭档案\n\n{body}"


def _parse_iso(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_open_questions(*, stale_days: int = 7) -> list[dict[str, Any]]:
    path = habit_suggestions_path()
    if not path.is_file():
        return []
    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    now = datetime.now(_SH_TZ)
    open_items: list[dict[str, Any]] = []
    for entry in store.get("entries") or []:
        if entry.get("status") != "asked":
            continue
        asked_at = _parse_iso(str(entry.get("asked_at") or ""))
        if asked_at and (now - asked_at.astimezone(_SH_TZ)) > timedelta(days=stale_days):
            continue
        open_items.append(entry)
    return open_items


def build_pending_suggestion_block() -> str:
    open_q = load_open_questions()
    if not open_q:
        return ""
    items = "\n".join(
        f"- [{e.get('key', '')}] {e.get('title', '')}：{e.get('suggestion', '')}"
        for e in open_q
    )
    return f"""## 等用户回应的习惯建议

你此前主动向用户推荐过把下面的习惯设成任务，正在等用户回应（**请勿重复推送同一条**）：

{items}

**如何处理用户这条消息：**
- 若是肯定/选择/否定语气且**没有**其它明确意图 → 这是对上面建议的答复：
  - 同意 → 先复述命中哪条，再加载 **miloco-create-task** skill 建任务；**拿到 task_id 后** `miloco_habit_suggest(action="resolve", key, outcome="created", task_id="<新任务id>")`
  - 拒绝 → `miloco_habit_suggest(action="resolve", key="<对应 key>", outcome="rejected")`
- 若用户消息**与这些建议无关** → 忽略本段，不要 resolve。"""
