"""Production composition root independent of every CLI entry point."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.conversation.conversation_service import ConversationService
from backend.conversation.conversation_store import ConversationStore
from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
from backend.conversation.capability_router import LocalSemanticIntentClassifier, NaturalLanguageCapabilityRouter
from backend.conversation.reflection_intent import ReflectionIntentHandler
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.model_router import ModelRouter
from backend.llm.ollama_provider import OllamaProvider
from backend.llm.model_profiles import ModelProfileStore
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.reflection import ReflectionService
from backend.memory.shared_continuity import SharedContinuityService
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory
from backend.runtime.health import RuntimeHealthService
from backend.runtime.daily_runtime import DailyRuntime, DailyRuntimeJournal
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.skills.agent_loop import AgentRunStore
from backend.skills.autonomy import ActionAutonomyPolicyStore, ActionAutonomyService
from backend.skills.installer import SkillInstallProposalStore, SkillInstallerService
from backend.skills.permissions import PermissionControlService, PermissionsSnapshot
from backend.skills.registry import SkillRegistry
from backend.temporal.proactive import ProactivePolicyStore
from backend.temporal.proactive_daemon import ProactiveDaemon
from backend.temporal.proactive_interaction import ProactiveInteractionStore

from .application import MashaApplication
from .activities import ActivityApplicationService
from .conversation import ConversationApplicationService
from .commitments import CommitmentApplicationService
from .continuity import ContinuityApplicationService
from .home_snapshot import HomeSnapshotService
from .model_settings import ModelSettingsService
from .proactive import ProactiveApplicationService
from .reflections import ReflectionApplicationService
from .status import MashaStatusService
from .visual_assets import VisualIdentityResolver
from .workbench import WorkbenchApplicationService


@dataclass(frozen=True)
class _Core:
    project_root: Path
    conversation: ConversationService
    repository: MemorySqliteRepository
    identity: IdentityKernel
    profiles: ModelProfileStore
    router: ModelRouter


def build_conversation_service(*, project_root: Path, router: ModelRouter | None = None) -> ConversationService:
    """Compatibility composition for CLI/runtime callers."""
    return _build_core(Path(project_root), router=router).conversation


def build_masha_application(*, project_root: Path, router: ModelRouter | None = None) -> MashaApplication:
    """Build the public local facade without importing or invoking CLI code."""
    core = _build_core(Path(project_root), router=router)
    models = ModelSettingsService(profiles=core.profiles, router=core.router)
    application_conversation = ConversationApplicationService(
        conversation=core.conversation,
        models=models,
    )
    config = core.project_root / "local-data" / "config"
    runtime = core.project_root / "local-data" / "runtime"
    proactive_policy = ProactivePolicyStore(config / "proactive-policy.json")
    runtime_journal = DailyRuntimeJournal(runtime / "daily-runtime-receipts.json")
    daemon = ProactiveDaemon(core.project_root)
    safety = AutonomySafetyService(store=AutonomySafetyStore(config / "autonomy-safety.json"))
    interactions = ProactiveInteractionStore(core.repository)

    registry = SkillRegistry(
        skills_root=core.project_root / "local-data" / "skills",
        bundled_skills_root=core.project_root / "skills",
        state_path=config / "skills.json",
    )
    action_policy_store = ActionAutonomyPolicyStore(config / "action-autonomy.json")
    install_store = SkillInstallProposalStore(config / "skill-installs.json")
    autonomy = ActionAutonomyService(store=action_policy_store, registry=registry)
    installer = SkillInstallerService(
        registry=registry,
        autonomy=autonomy,
        proposal_store=install_store,
        runtime_root=runtime / "skill-installs",
    )

    def permissions_snapshot() -> PermissionsSnapshot:
        return PermissionControlService(
            registry=registry,
            action_policy_store=action_policy_store,
            safety=safety,
            run_store=AgentRunStore(runtime / "agent-runs.json"),
            install_store=install_store,
            proactive_policy=proactive_policy.load(),
            background_runtime_running=daemon.is_running(),
        ).snapshot()

    health = RuntimeHealthService(
        service=core.conversation,
        project_root=core.project_root,
        daemon=daemon,
    )
    status = MashaStatusService(
        health=health,
        models=models,
        proactive_policy=proactive_policy,
        daemon=daemon,
        safety=safety,
        permissions=permissions_snapshot,
        proactive_interactions=interactions,
        proactive_journal=runtime_journal,
    )
    visuals = VisualIdentityResolver(project_root=core.project_root, identity_kernel=core.identity)
    return MashaApplication(
        conversation=application_conversation,
        status=status,
        visuals=visuals,
        models=models,
        home_snapshot=HomeSnapshotService(status=status, models=models, visuals=visuals),
        commitments=CommitmentApplicationService(conversation=core.conversation),
        activities=ActivityApplicationService(
            store=AgentRunStore(runtime / "agent-runs.json")
        ),
        proactive=ProactiveApplicationService(
            store=interactions,
            clock=core.conversation.temporal_engine.clock,
            policy_store=proactive_policy,
            journal=runtime_journal,
            daemon=daemon,
            runtime=DailyRuntime(
                history=core.conversation.history,
                temporal_engine=core.conversation.temporal_engine,
                repository=core.repository,
                identity_kernel=core.identity,
                router=core.router,
                model_profiles=core.profiles,
                safety_store=safety.store,
            ),
        ),
        continuity=ContinuityApplicationService(
            continuity=core.conversation.shared_continuity,
            memory_management=MemoryManagementService(core.repository),
        ),
        reflections=ReflectionApplicationService(
            reflections=core.conversation.reflection_service,
            history=core.conversation.history,
        ),
        workbench=WorkbenchApplicationService(
            models=models,
            permissions=permissions_snapshot,
            installer=installer,
        ),
    )


def _build_core(project_root: Path, *, router: ModelRouter | None) -> _Core:
    root = Path(project_root)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    identity = IdentityKernel(IdentityStore(root / "identity" / "masha.identity.json"))
    identity.validate_memory_identity(repository)
    memory_management = MemoryManagementService(repository)
    shared_continuity = SharedContinuityService(repository)
    profiles = ModelProfileStore(root / "local-data" / "config" / "models.json")
    selected_router = router or ModelRouter([OllamaProvider()])
    reflection = ReflectionService(
        repository=repository,
        identity_kernel=identity,
        memory_retriever=MemoryRetriever(repository),
        router=selected_router,
        model_profiles=profiles,
    )
    conversation = ConversationService(
        identity_kernel=identity,
        memory_retriever=MemoryRetriever(repository),
        working_memory=WorkingMemory(max_items=6),
        router=selected_router,
        history=ConversationStore(root / "local-data" / "conversations" / "history.json"),
        memory_intent_handler=MemoryIntentHandler(
            proposal_store=MemoryProposalStore(root / "local-data" / "memory-proposals.json"),
            confirmed_memory=ConfirmedMemoryService(repository),
            memory_management=memory_management,
            shared_continuity=shared_continuity,
            capability_router=NaturalLanguageCapabilityRouter(
                LocalSemanticIntentClassifier(
                    router=selected_router,
                    identity_kernel=identity,
                    model_profiles=profiles,
                )
            ),
        ),
        model_profiles=profiles,
        proactive_interactions=ProactiveInteractionStore(repository),
        shared_continuity=shared_continuity,
        reflection_intent_handler=ReflectionIntentHandler(reflection),
        reflection_service=reflection,
    )
    return _Core(
        project_root=root,
        conversation=conversation,
        repository=repository,
        identity=identity,
        profiles=profiles,
        router=selected_router,
    )
