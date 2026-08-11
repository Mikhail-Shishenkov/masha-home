from copy import deepcopy
from datetime import datetime, timedelta, timezone

from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_router import ModelRouter
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.proactive import ProactiveDecisionEngine, ProactivePolicy
from backend.temporal.proactive_interaction import ProactiveInteractionService, ProactiveInteractionStore
from backend.temporal.proactive_interaction import ProactiveInteractionUnavailableError
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.temporal_models import ProactiveDecision
from backend.temporal.temporal_runtime import TemporalRuntime

ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)

def _candidate(tmp_path, canonical_memory):
    data=deepcopy(canonical_memory); data['commitments'][0]['due_at']=(NOW-timedelta(minutes=1)).isoformat()
    repo=MemorySqliteRepository(tmp_path/'memory.sqlite3'); repo.replace_document(data); engine=TemporalEngine(FixedClock(NOW)); event=TemporalRuntime(repo,engine).recover().events[0]
    decision=ProactiveDecisionEngine().decide(event,ProactivePolicy(enabled=True, proactive_level=1, allow_commitment_reminders=True,maximum_reminders=1),now=NOW)
    return repo, ProactiveDecisionEngine.candidate(event,commitment_text='Отправить отчёт',temporal_context=engine.context(None),decision=decision,generated_at=NOW)

def test_authorised_candidate_delivers_once_and_acknowledges_without_memory_mutation(tmp_path, canonical_memory):
    repo,candidate=_candidate(tmp_path,canonical_memory); before=repo.read_document().model_dump(mode='json'); provider=FakeProvider(provider_id='ollama-local',response_text='Миша, напомню про отчёт.')
    service=ProactiveInteractionService(store=ProactiveInteractionStore(repo),identity_kernel=IdentityKernel(IdentityStore(ROOT/'identity'/'masha.identity.json')),router=ModelRouter([provider]),model_profiles=ModelProfileStore(tmp_path/'models.json'))
    first=service.formulate(candidate); second=service.formulate(candidate); acknowledged=service.store.acknowledge(candidate.event.event_id,NOW)
    assert first['state']=='delivered' and second['message_text']==first['message_text'] and acknowledged['state']=='acknowledged'
    assert provider.last_request.private_context['authorised_decision']=='remind'
    assert repo.read_document().model_dump(mode='json')==before
    assert ProactiveInteractionStore(MemorySqliteRepository(repo.database_path)).get(candidate.event.event_id)['state']=='acknowledged'

def test_dismiss_blocks_reformulation_and_suppressed_candidate_never_reaches_model(tmp_path, canonical_memory):
    repo,candidate=_candidate(tmp_path,canonical_memory); store=ProactiveInteractionStore(repo); store.ensure_candidate(candidate); store.dismiss(candidate.event.event_id,NOW)
    provider=FakeProvider(provider_id='ollama-local'); service=ProactiveInteractionService(store=store,identity_kernel=IdentityKernel(IdentityStore(ROOT/'identity'/'masha.identity.json')),router=ModelRouter([provider]),model_profiles=ModelProfileStore(tmp_path/'models.json'))
    assert service.formulate(candidate)['state']=='dismissed' and provider.last_request is None
    assert ProactiveDecisionEngine().decide(candidate.event,ProactivePolicy(),now=NOW) is ProactiveDecision.SUPPRESS

def test_local_model_error_keeps_candidate_without_memory_mutation(tmp_path, canonical_memory):
    repo,candidate=_candidate(tmp_path,canonical_memory); before=repo.read_document().model_dump(mode='json'); store=ProactiveInteractionStore(repo)
    service=ProactiveInteractionService(store=store,identity_kernel=IdentityKernel(IdentityStore(ROOT/'identity'/'masha.identity.json')),router=ModelRouter([FakeProvider(provider_id='ollama-local',available=False)]),model_profiles=ModelProfileStore(tmp_path/'models.json'))
    import pytest
    with pytest.raises(ProactiveInteractionUnavailableError): service.formulate(candidate)
    assert store.get(candidate.event.event_id)['state']=='candidate'
    assert repo.read_document().model_dump(mode='json')==before


def test_delivery_stats_are_local_and_restart_safe(tmp_path, canonical_memory):
    repo, candidate = _candidate(tmp_path, canonical_memory)
    store = ProactiveInteractionStore(repo)
    store.ensure_candidate(candidate)
    store.mark_delivered(candidate.event.event_id, 'local reminder', NOW)

    count, latest = ProactiveInteractionStore(MemorySqliteRepository(repo.database_path)).delivery_stats(NOW)

    assert count == 1
    assert latest == NOW
