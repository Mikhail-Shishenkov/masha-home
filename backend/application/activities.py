"""Bounded human projection of existing local Agent Run receipts."""

from backend.skills.agent_loop import AgentRunStatus, AgentRunStore, AgentStepStatus

from .contracts import AgentRunListView, AgentRunView, AgentStepView


RUN_LABELS = {
    AgentRunStatus.RUNNING: "Маша работает",
    AgentRunStatus.AWAITING_CONFIRMATION: "Нужно твоё решение",
    AgentRunStatus.COMPLETED: "Завершено и проверено",
    AgentRunStatus.DENIED: "Остановлено правилами",
    AgentRunStatus.FAILED: "Не удалось завершить",
    AgentRunStatus.BUDGET_EXHAUSTED: "Остановлено по лимиту",
}


class ActivityApplicationService:
    """Read receipts without exposing tools, policy reasons or raw payloads."""

    def __init__(self, *, store: AgentRunStore):
        self._store = store

    def list(self, *, limit: int = 8) -> AgentRunListView:
        rows = sorted(self._store.list(), key=lambda item: item.updated_at, reverse=True)
        return AgentRunListView(items=tuple(self._view(item) for item in rows[:limit]))

    @staticmethod
    def _view(receipt) -> AgentRunView:
        steps = tuple(
            AgentStepView(
                title=step.title,
                status=step.status.value,
                result_summary=step.result_summary,
            )
            for step in receipt.steps
        )
        return AgentRunView(
            run_id=receipt.plan_id,
            goal=receipt.goal,
            status=receipt.status.value,
            started_at=receipt.started_at,
            updated_at=receipt.updated_at,
            finished_at=receipt.finished_at,
            completed_steps=sum(
                step.status is AgentStepStatus.VERIFIED for step in receipt.steps
            ),
            total_steps=len(receipt.steps),
            steps=steps,
            status_label=RUN_LABELS[receipt.status],
        )
