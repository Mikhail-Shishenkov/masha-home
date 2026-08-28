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
from backend.llm.model_roles import ModelRoleProfileStore
from backend.memory.confirmed_memory_service import ConfirmedMemoryService
from backend.memory.memory_management import MemoryManagementService
from backend.memory.candidate_lifecycle import PassiveMemoryService
from backend.memory.passive_detection import PassiveMemoryCandidateDetector
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.reflection import ReflectionService
from backend.memory.shared_continuity import SharedContinuityService
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.working_memory import WorkingMemory
from backend.runtime.health import RuntimeHealthService
from backend.runtime.daily_runtime import DailyRuntime, DailyRuntimeJournal
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.backup.recovery_journal import RecoveryJournal
from backend.external_observation import (
    DDGSWebSearchProvider,
    ExternalObservationService,
    ExternalObservationStore,
    InternetAccessPolicyStore,
    LocalExternalQueryPlanner,
    LocalSourceSelector,
)
from backend.document_read import DocumentReadStore, DocumentReader, LocalDocumentInputService
from backend.connectors.google_calendar import (
    CalendarCreateReceiptStore, GoogleCalendarConfigStore,
    GoogleCalendarConversationService, GoogleCalendarCreateConversationService,
    GoogleCalendarReader, GoogleCalendarWriter,
    CalendarUpdateReceiptStore, GoogleCalendarUpdater, GoogleCalendarUpdateConversationService,
)
from backend.connectors.google_drive import (
    DriveDocumentCreateReceiptStore, GoogleDriveConfigStore,
    GoogleDriveConversationService, GoogleDriveDocumentCreateConversationService,
    GoogleDriveDocumentWriter, GoogleDriveReader, LocalDocumentDraftBuilder,
)
from backend.connectors.yandex_mail import YandexMailConfigStore, YandexMailConversationService, YandexMailReader
from backend.connectors.yandex_disk import YandexDiskConfigStore, YandexDiskConversationService, YandexDiskReader
from backend.connectors.presented_read_sets import PresentedReadSetRegistry
from backend.secrets import WindowsCredentialManagerSecretStore
from backend.skills.agent_loop import AgentRunStore
from backend.skills.autonomy import ActionAutonomyPolicyStore, ActionAutonomyService
from backend.skills.installer import SkillInstallProposalStore, SkillInstallerService
from backend.skills.permissions import PermissionControlService, PermissionsSnapshot
from backend.skills.registry import SkillRegistry
from backend.temporal.proactive import ProactivePolicyStore
from backend.temporal.proactive_daemon import ProactiveDaemon, request_proactive_wakeup
from backend.temporal.proactive_interaction import ProactiveInteractionStore
from backend.temporal.reminder_trace import ReminderDeliveryTrace
from backend.temporal.temporal_engine import TemporalEngine
from backend.temporal.timezone_provider import HomeTimeZoneProvider, HomeTimeZoneStore
from backend.conversation.response_expression import (
    ResponseExpressionClassifier,
)
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import CapabilityCandidateDiscovery
from backend.conversation.pending_resolution import PendingResolutionStore
from backend.conversation.resolution_coordinator import (
    NaturalLanguageResolutionCoordinator,
    ResolvedCapabilityAdapterRegistry,
    V2LiveAdoptionPolicy,
)
from backend.conversation.semantic_resolver import (
    HybridCapabilityCandidateDiscovery,
    LocalSemanticResolver,
    SemanticProposalValidator,
)

from .application import MashaApplication
from .activities import ActivityApplicationService
from .conversation import ConversationApplicationService
from .commitments import CommitmentApplicationService
from .continuity import ContinuityApplicationService
from .home_snapshot import HomeSnapshotService
from .human_information import HumanInformationService
from .external_context import LocalExternalContextHintProvider
from .external_connections import ExternalConnectionApplicationService
from .home_capabilities import HomeCapabilityApplicationService, default_home_capability_catalog
from .model_settings import ModelSettingsService
from .local_documents import LocalDocumentTurnService
from .memory_candidates import MemoryCandidateApplicationService
from .proactive import ProactiveApplicationService
from .reflections import ReflectionApplicationService
from .status import MashaStatusService
from .visual_assets import VisualIdentityResolver
from .workbench import WorkbenchApplicationService
from .resolved_capabilities import (
    CalendarCreateHandoffAdapter,
    TimedCommitmentHandoffAdapter,
)


@dataclass(frozen=True)
class _Core:
    project_root: Path
    conversation: ConversationService
    repository: MemorySqliteRepository
    identity: IdentityKernel
    profiles: ModelProfileStore
    router: ModelRouter
    human_information: HumanInformationService
    reflection: ReflectionService


def build_conversation_service(*, project_root: Path, router: ModelRouter | None = None) -> ConversationService:
    """Compatibility composition for CLI/runtime callers."""
    return _build_core(Path(project_root), router=router).conversation


def build_masha_application(*, project_root: Path, router: ModelRouter | None = None) -> MashaApplication:
    """Build the public local facade without importing or invoking CLI code."""
    core = _build_core(Path(project_root), router=router)
    models = ModelSettingsService(profiles=core.profiles, router=core.router)
    config = core.project_root / "local-data" / "config"
    runtime = core.project_root / "local-data" / "runtime"
    proactive_policy = ProactivePolicyStore(config / "proactive-policy.json")
    runtime_journal = DailyRuntimeJournal(runtime / "daily-runtime-receipts.json")
    daemon = ProactiveDaemon(core.project_root)
    connector_secret_store = WindowsCredentialManagerSecretStore()
    connector_config_stores = {
        "google-calendar": GoogleCalendarConfigStore(config / "google-calendar.json"),
        "google-drive": GoogleDriveConfigStore(config / "google-drive.json"),
        "yandex-mail": YandexMailConfigStore(config / "yandex-mail.json"),
        "yandex-disk": YandexDiskConfigStore(config / "yandex-disk.json"),
    }
    safety = AutonomySafetyService(store=AutonomySafetyStore(config / "autonomy-safety.json"))
    interactions = ProactiveInteractionStore(
        core.repository,
        home_timezone=core.conversation.temporal_engine.home_timezone.tzinfo,
    )
    reminder_trace = ReminderDeliveryTrace(runtime / "reminder-delivery-trace.json")

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
    internet_policy = InternetAccessPolicyStore(config / "internet-access.json")
    connections = ExternalConnectionApplicationService(
        config_stores=connector_config_stores,
        secret_store=connector_secret_store,
    )
    capability_catalog = default_home_capability_catalog()
    capabilities = HomeCapabilityApplicationService(
        connections=connections,
        internet_policy=internet_policy,
        safety_store=safety.store,
        proactive_policy=proactive_policy,
        catalog=capability_catalog,
    )
    core.conversation.home_capability_provider = capabilities.snapshot
    core.conversation.google_calendar_create_service = GoogleCalendarCreateConversationService(
        proposal_store=core.conversation.memory_intent_handler.proposal_store,
        writer=GoogleCalendarWriter(
            config_store=connector_config_stores["google-calendar"],
            secret_store=connector_secret_store,
            receipt_store=CalendarCreateReceiptStore(runtime / "google-calendar-create-receipts.json"),
            policy_store=internet_policy,
            safety_store=safety.store,
            recovery_journal=RecoveryJournal(core.project_root),
            clock=core.conversation.temporal_engine.clock.now_utc,
        ),
    )
    core.conversation.google_calendar_update_service = GoogleCalendarUpdateConversationService(
        proposal_store=core.conversation.memory_intent_handler.proposal_store,
        updater=GoogleCalendarUpdater(
            config_store=connector_config_stores["google-calendar"],
            secret_store=connector_secret_store,
            receipt_store=CalendarUpdateReceiptStore(runtime / "google-calendar-update-receipts.json"),
            policy_store=internet_policy,
            safety_store=safety.store,
            recovery_journal=RecoveryJournal(core.project_root),
            clock=core.conversation.temporal_engine.clock.now_utc,
        ),
    )
    core.conversation.google_drive_document_create_service = GoogleDriveDocumentCreateConversationService(
        proposal_store=core.conversation.memory_intent_handler.proposal_store,
        writer=GoogleDriveDocumentWriter(
            config_store=connector_config_stores["google-drive"], secret_store=connector_secret_store,
            receipt_store=DriveDocumentCreateReceiptStore(runtime / "google-drive-document-create-receipts.json"),
            policy_store=internet_policy, safety_store=safety.store,
            recovery_journal=RecoveryJournal(core.project_root), clock=core.conversation.temporal_engine.clock.now_utc,
        ),
        draft_builder=LocalDocumentDraftBuilder(router=core.router, identity_kernel=core.identity, model_profiles=core.profiles),
    )
    pending_resolutions = PendingResolutionStore(
        runtime / "pending-resolutions.json",
        clock=core.conversation.temporal_engine.clock.now_utc,
    )
    adoption = V2LiveAdoptionPolicy()
    deterministic_discovery = CapabilityCandidateDiscovery(catalog=capability_catalog)
    semantic_validator = SemanticProposalValidator(
        catalog=capability_catalog,
        specifications=deterministic_discovery.specifications,
        allowed_operation_ids=adoption.supported_operation_ids,
    )
    semantic_discovery = HybridCapabilityCandidateDiscovery(
        deterministic=deterministic_discovery,
        resolver=LocalSemanticResolver(
            router=core.router,
            role_profiles=ModelRoleProfileStore(
                config / "model-roles.json",
                profiles=core.profiles,
            ),
        ),
        validator=semantic_validator,
    )
    core.conversation.natural_language_coordinator = NaturalLanguageResolutionCoordinator(
        discovery=semantic_discovery,
        builder=DeterministicClarificationBuilder(
            catalog=capability_catalog,
            clock=core.conversation.temporal_engine.clock.now_utc,
        ),
        engine=FollowUpResolutionEngine(),
        store=pending_resolutions,
        adoption=adoption,
    )
    core.conversation.resolved_capability_adapters = ResolvedCapabilityAdapterRegistry((
        CalendarCreateHandoffAdapter(core.conversation.google_calendar_create_service),
        TimedCommitmentHandoffAdapter(core.conversation.memory_intent_handler),
    ))
    document_store = DocumentReadStore(runtime / "document-read-receipts.json")
    core.conversation.external_observation_service = ExternalObservationService(
        provider=DDGSWebSearchProvider(
            timeout_seconds=internet_policy.load().provider_timeout_seconds,
            clock=core.conversation.temporal_engine.clock.now_utc,
        ),
        policy_store=internet_policy,
        safety_store=safety.store,
        registry=registry,
        planner=LocalExternalQueryPlanner(
            router=core.router,
            identity_kernel=core.identity,
            model_profiles=core.profiles,
        ),
        source_selector=LocalSourceSelector(
            router=core.router,
            identity_kernel=core.identity,
            model_profiles=core.profiles,
        ),
        context_hint_provider=LocalExternalContextHintProvider(
            human_information=core.human_information,
            reflections=core.reflection,
        ),
        store=ExternalObservationStore(runtime / "external-observations.json"),
        document_store=document_store,
        clock=core.conversation.temporal_engine.clock.now_utc,
    )
    application_conversation = ConversationApplicationService(
        conversation=core.conversation,
        models=models,
        expression_classifier=ResponseExpressionClassifier(
            router=core.router,
            identity_kernel=core.identity,
            model_profiles=core.profiles,
        ),
        local_documents=LocalDocumentTurnService(
            inputs=LocalDocumentInputService(),
            reader=DocumentReader(),
            store=document_store,
            registry=registry,
            clock=core.conversation.temporal_engine.clock.now_utc,
        ),
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
        home_snapshot=HomeSnapshotService(
            status=status,
            models=models,
            visuals=visuals,
            clock=core.conversation.temporal_engine.now_local,
        ),
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
            hold_checker=RecoveryJournal(core.project_root).is_hold,
            wake_path=runtime / "proactive-daemon.wake",
            trace=reminder_trace,
            runtime=DailyRuntime(
                history=core.conversation.history,
                temporal_engine=core.conversation.temporal_engine,
                repository=core.repository,
                identity_kernel=core.identity,
                router=core.router,
                model_profiles=core.profiles,
                safety_store=safety.store,
                trace=reminder_trace,
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
            connections=connections,
        ),
        memory_candidates=MemoryCandidateApplicationService(
            core.conversation.passive_memory_service
        ),
        human_information=core.human_information,
    )


def _build_core(project_root: Path, *, router: ModelRouter | None) -> _Core:
    root = Path(project_root)
    RecoveryJournal(root).assert_runtime_start_allowed()
    timezone_provider = HomeTimeZoneProvider.from_store(
        HomeTimeZoneStore(root / "local-data" / "config" / "home-timezone.json")
    )
    temporal_engine = TemporalEngine(timezone_provider=timezone_provider)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    identity = IdentityKernel(IdentityStore(root / "identity" / "masha.identity.json"))
    identity.validate_memory_identity(repository)
    memory_management = MemoryManagementService(repository)
    proposal_store = MemoryProposalStore(root / "local-data" / "memory-proposals.json")
    conversation_retriever = MemoryRetriever(repository)
    human_information = HumanInformationService(
        repository,
        memory_management=memory_management,
        temporal_engine=temporal_engine,
        clock=temporal_engine.clock.now_utc,
        proposal_store=proposal_store,
        memory_retriever=conversation_retriever,
    )
    shared_continuity = SharedContinuityService(repository)
    profiles = ModelProfileStore(root / "local-data" / "config" / "models.json")
    selected_router = router or ModelRouter([OllamaProvider()])
    reflection = ReflectionService(
        repository=repository,
        identity_kernel=identity,
        memory_retriever=conversation_retriever,
        router=selected_router,
        model_profiles=profiles,
    )
    passive_memory = PassiveMemoryService(
        repository=repository,
        detector=PassiveMemoryCandidateDetector(temporal_engine),
        clock=temporal_engine.clock.now_utc,
    )
    presented_read_sets = PresentedReadSetRegistry()
    interactions = ProactiveInteractionStore(
        repository,
        home_timezone=temporal_engine.home_timezone.tzinfo,
    )
    reminder_trace = ReminderDeliveryTrace(root / "local-data" / "runtime" / "reminder-delivery-trace.json")
    conversation = ConversationService(
        identity_kernel=identity,
        memory_retriever=MemoryRetriever(repository),
        working_memory=WorkingMemory(max_items=6),
        router=selected_router,
        history=ConversationStore(
            root / "local-data" / "conversations" / "history.json",
            clock=temporal_engine.clock.now_utc,
        ),
        memory_intent_handler=MemoryIntentHandler(
            proposal_store=proposal_store,
            confirmed_memory=ConfirmedMemoryService(repository),
            memory_management=memory_management,
            shared_continuity=shared_continuity,
            temporal_engine=temporal_engine,
            capability_router=NaturalLanguageCapabilityRouter(
                LocalSemanticIntentClassifier(
                    router=selected_router,
                    identity_kernel=identity,
                    model_profiles=profiles,
                )
            ),
            human_information=human_information,
            on_commitment_terminal=lambda commitment_id: interactions.dismiss_delivered_reminders_for_commitment(
                commitment_id,
                temporal_engine.clock.now_utc(),
            ),
            on_timed_commitment_changed=lambda: (
                reminder_trace.record("commitment_due_changed"),
                request_proactive_wakeup(root, trace=reminder_trace),
            ),
        ),
        model_profiles=profiles,
        proactive_interactions=interactions,
        temporal_engine=temporal_engine,
        shared_continuity=shared_continuity,
        reflection_intent_handler=ReflectionIntentHandler(reflection),
        reflection_service=reflection,
        passive_memory_service=passive_memory,
        human_information=human_information,
        google_calendar_service=GoogleCalendarConversationService(
            reader=GoogleCalendarReader(
                config_store=GoogleCalendarConfigStore(root / "local-data" / "config" / "google-calendar.json"),
                secret_store=WindowsCredentialManagerSecretStore(),
                policy_store=InternetAccessPolicyStore(root / "local-data" / "config" / "internet-access.json"),
                safety_store=AutonomySafetyStore(root / "local-data" / "config" / "autonomy-safety.json"),
            )
        ),
        google_drive_service=GoogleDriveConversationService(
            reader=GoogleDriveReader(
                config_store=GoogleDriveConfigStore(root / "local-data" / "config" / "google-drive.json"),
                secret_store=WindowsCredentialManagerSecretStore(),
                document_store=DocumentReadStore(root / "local-data" / "runtime" / "document-read-receipts.json"),
                policy_store=InternetAccessPolicyStore(root / "local-data" / "config" / "internet-access.json"),
                safety_store=AutonomySafetyStore(root / "local-data" / "config" / "autonomy-safety.json"),
            ),
            presented_read_sets=presented_read_sets,
        ),
        yandex_mail_service=YandexMailConversationService(
            reader=YandexMailReader(
                config_store=YandexMailConfigStore(root / "local-data" / "config" / "yandex-mail.json"),
                secret_store=WindowsCredentialManagerSecretStore(),
                policy_store=InternetAccessPolicyStore(root / "local-data" / "config" / "internet-access.json"),
                safety_store=AutonomySafetyStore(root / "local-data" / "config" / "autonomy-safety.json"),
            ),
            presented_read_sets=presented_read_sets,
        ),
        yandex_disk_service=YandexDiskConversationService(
            reader=YandexDiskReader(
                config_store=YandexDiskConfigStore(root / "local-data" / "config" / "yandex-disk.json"),
                secret_store=WindowsCredentialManagerSecretStore(),
                document_store=DocumentReadStore(root / "local-data" / "runtime" / "document-read-receipts.json"),
                policy_store=InternetAccessPolicyStore(root / "local-data" / "config" / "internet-access.json"),
                safety_store=AutonomySafetyStore(root / "local-data" / "config" / "autonomy-safety.json"),
            ),
            presented_read_sets=presented_read_sets,
        ),
    )
    return _Core(
        project_root=root,
        conversation=conversation,
        repository=repository,
        identity=identity,
        profiles=profiles,
        router=selected_router,
        human_information=human_information,
        reflection=reflection,
    )
