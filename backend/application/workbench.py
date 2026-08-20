"""Bounded UI projection for local execution profiles, skills and permissions."""

from __future__ import annotations

from backend.skills.permissions import PermissionsSnapshot

from .contracts import (
    PermissionGrantView,
    PermissionPendingView,
    SkillWorkbenchView,
    SkillInstallPreviewView,
    SkillInstallResultView,
    WorkbenchView,
)


class WorkbenchApplicationService:
    """Read existing operating controls without turning the Home into an admin API."""

    def __init__(self, *, models, permissions, installer=None):
        self._models = models
        self._permissions = permissions
        self._installer = installer

    def view(self, *, profile_limit: int = 4, skill_limit: int = 6, grant_limit: int = 6) -> WorkbenchView:
        snapshot: PermissionsSnapshot = self._permissions()
        profiles = self._models.list_profiles()[:profile_limit]
        skills = tuple(
            SkillWorkbenchView(
                skill_id=item.skill_id,
                name=item.name,
                version=item.version,
                integrity=item.integrity.value,
                capabilities=tuple(capability.value for capability in item.capabilities),
                runtime_supported=item.runtime_supported,
                **self._human_skill(item.skill_id),
                scopes=item.scopes,
                risk=None if item.risk is None else item.risk.value,
            )
            for item in snapshot.skills[:skill_limit]
        )
        actual_grants = {(item.skill_id, item.capability.value, item.scope): item for item in snapshot.grants}
        grant_rows = []
        for skill in snapshot.skills:
            for capability in skill.capabilities:
                matching = [item for key, item in actual_grants.items() if key[:2] == (skill.skill_id, capability.value)]
                if matching:
                    for item in matching:
                        grant_rows.append(PermissionGrantView(
                            skill_id=item.skill_id, capability=item.capability.value, scope=item.scope,
                            effective=item.effective,
                            label="Могу сама" if item.effective else "Запрещено текущими настройками",
                            mode="self" if item.effective else "forbidden",
                        ))
                else:
                    grant_rows.append(PermissionGrantView(
                        skill_id=skill.skill_id, capability=capability.value,
                        scope=skill.scopes[0] if skill.scopes else "без разрешённой области",
                        effective=False, label="Сначала спрошу", mode="ask",
                    ))
        grants = tuple(grant_rows[:grant_limit])
        pending = tuple(
            PermissionPendingView(
                kind=item.kind.value,
                title=item.title,
                status=item.status,
            )
            for item in snapshot.pending[:grant_limit]
        )
        return WorkbenchView(
            profiles=profiles,
            skills=skills,
            grants=grants,
            pending=pending,
            emergency_stop_engaged=snapshot.safety.emergency_stop_engaged,
            action_autonomy_enabled=snapshot.action_autonomy.enabled,
            action_autonomy_level=snapshot.action_autonomy.maximum_autonomy_level,
            active_agent_runs=snapshot.active_agent_runs,
        )

    @staticmethod
    def _human_skill(skill_id: str) -> dict:
        cards = {
            "project_observer": {
                "summary": "Смотрит на разрешённую часть локального проекта.",
                "usage": "Только по твоей просьбе",
                "can": ("читать ограниченные локальные материалы",),
                "cannot": ("менять файлы", "выходить в интернет"),
            },
            "web_search": {
                "summary": "Ищет актуальную публичную информацию в интернете.",
                "usage": "Только по твоей просьбе",
                "can": ("искать сайты и свежую информацию", "возвращать проверяемые источники"),
                "cannot": ("читать страницу целиком", "входить на сайты", "отправлять или менять данные"),
            },
            "web_fetch": {
                "summary": "Читает одну публичную веб-страницу.",
                "usage": "Только по твоей просьбе",
                "can": ("читать HTML", "читать обычный текст", "читать JSON"),
                "cannot": ("входить на сайты", "запускать JavaScript", "скачивать файлы", "читать PDF", "отправлять формы"),
            },
        }
        return cards.get(skill_id, {})

    def propose_install(self, source_path: str) -> SkillInstallPreviewView:
        if self._installer is None:
            raise RuntimeError("skill installer is unavailable")
        proposal = self._installer.propose(source_path)
        return self._install_preview(proposal)

    def resolve_install(self, proposal_id: str, decision: str) -> SkillInstallResultView:
        if self._installer is None or decision not in {"confirm", "reject"}:
            raise ValueError("unsupported skill install decision")
        proposal = self._installer.confirm(proposal_id) if decision == "confirm" else self._installer.reject(proposal_id)
        status = "confirmed" if decision == "confirm" else "rejected"
        return SkillInstallResultView(
            status=status,
            skill_id=proposal.skill_id,
            message=(f"Навык «{proposal.name}» установлен и проверен." if status == "confirmed" else "Установка навыка отменена."),
            workbench=self.view(),
        )

    @staticmethod
    def _install_preview(proposal) -> SkillInstallPreviewView:
        return SkillInstallPreviewView(
            proposal_id=proposal.proposal_id, action=proposal.action.value,
            skill_id=proposal.skill_id, name=proposal.name,
            proposed_version=proposal.proposed_version,
            capabilities=tuple(item.value for item in proposal.capabilities),
            requested_scopes=proposal.requested_scopes,
            risk_level=proposal.risk_level.value,
            maximum_autonomy_level=proposal.maximum_autonomy_level,
            permissions_to_revoke=proposal.permissions_to_revoke,
            runtime_supported=proposal.runtime_supported,
            files_added=len(proposal.files_added), files_changed=len(proposal.files_changed), files_removed=len(proposal.files_removed),
        )
