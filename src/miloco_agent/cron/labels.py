"""Human-readable cron schedule labels for admin UI."""

from __future__ import annotations

# Known managed jobs — extend when HOME_PROFILE_JOBS grows.
_CRON_LABELS: dict[str, str] = {
    "*/15 * * * *": "每 15 分钟",
    "*/30 * * * *": "每 30 分钟",
    "0 0 * * *": "每天 00:00",
    "0 10 * * *": "每天 10:00",
}


def cron_schedule_label(cron_expr: str) -> str:
    expr = (cron_expr or "").strip()
    if expr in _CRON_LABELS:
        return _CRON_LABELS[expr]
    return expr


MANAGED_CRON_PIPELINE_INTRO = (
    "四条受管任务组成「家庭记忆管线」，按数据流协作："
    "摄像头感知 → digest 摘要成记忆 → patrol 巡检行动 → dreaming 夜间沉淀档案 → habit-suggest 推荐自动化。"
    "需在上方开启 Cron 后才会按周期执行；也可点「立即执行」手动验证。"
)
