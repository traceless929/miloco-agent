"""Home-profile cron definitions — aligned with plugins/openclaw/.../scheduler.ts."""

from __future__ import annotations

from dataclasses import dataclass

MANAGED_TAG = "[miloco:home-profile]"


@dataclass(frozen=True)
class CronJob:
    name: str
    description: str
    summary: str
    detail: str
    cron_expr: str
    message: str
    timeout_ms: int = 300_000

    @property
    def session_key(self) -> str:
        return f"cron:{self.name}"

    @property
    def lane(self) -> str:
        return f"cron:{self.name}"

    def prefixed_message(self) -> str:
        return f"[cron:{self.name} {self.name}] {self.message}"


_HOME_DREAMING_MESSAGE = """执行 home-dreaming 流程。依次完成以下步骤：
1. **Observe** — 加载 miloco-home-observe skill，从感知/交互记忆中提取新知识写入候选区
2. **Promote** — 加载 miloco-home-promote skill，将候选区中达到条件的知识提升到正式档案
3. **Prune** — 加载 miloco-home-prune skill，统一主体命名、清理过期数据、提交持久化

执行规则：按顺序依次执行不可跳过。Step 1 没有新知识时仍需执行 Step 2（处理已有候选的提升）。"""


HOME_PROFILE_JOBS: tuple[CronJob, ...] = (
    CronJob(
        name="miloco-perception-digest",
        description=f"{MANAGED_TAG} miloco-perception-digest",
        summary="感知日志摘要",
        detail="每 15 分钟读取摄像头感知增量日志，提炼「谁/何时/何地/做了什么」写入今日感知记忆文件，是家庭记忆的原材料。",
        cron_expr="*/15 * * * *",
        message="执行感知日志摘要。加载 miloco-perception-digest skill 进行处理。",
    ),
    CronJob(
        name="miloco-home-patrol",
        description=f"{MANAGED_TAG} miloco-home-patrol",
        summary="家庭巡检",
        detail="每 30 分钟结合家庭档案与今日感知记忆，按档案依据自动控设备或发关怀提醒；无匹配场景则静默。",
        cron_expr="*/30 * * * *",
        message="执行家庭巡检。加载 miloco-home-patrol skill 进行巡检。",
    ),
    CronJob(
        name="miloco-home-dreaming",
        description=f"{MANAGED_TAG} miloco-home-dreaming",
        summary="夜间整理档案",
        detail="每天 0 点执行 Observe→Promote→Prune：从记忆提取候选知识、晋升正式档案、清理过期并渲染 profile.md。",
        cron_expr="0 0 * * *",
        message=_HOME_DREAMING_MESSAGE,
        timeout_ms=600_000,
    ),
    CronJob(
        name="miloco-habit-suggest",
        description=f"{MANAGED_TAG} miloco-habit-suggest",
        summary="习惯洞察推荐",
        detail="每天 10 点扫描档案中可自动化的习惯，至多 IM 推荐 1 条「要不要设成任务」；用户同意后再建任务。",
        cron_expr="0 10 * * *",
        message=(
            "执行每日习惯洞察。加载 miloco-habit-suggest skill，按【路径 A · 扫描推荐】处理："
            "从家庭档案识别值得建成任务的习惯，至多主动推荐一条。"
        ),
    ),
)
