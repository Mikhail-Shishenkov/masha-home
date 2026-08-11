from datetime import datetime, time, timezone
from pathlib import Path

from backend.temporal.proactive import ProactiveDecisionEngine, ProactiveEventOrigin, ProactivePolicy, ProactivePolicyStore
from backend.temporal.temporal_models import CommitmentDueEvent, ProactiveDecision

NOW=datetime(2026,8,11,12,tzinfo=timezone.utc)
EVENT=CommitmentDueEvent(event_id='e',source_commitment_id='c',due_at=NOW,detected_at=NOW)

def test_policy_persists_and_default_is_conservative(tmp_path):
    store=ProactivePolicyStore(tmp_path/'proactive-policy.json')
    assert store.load().enabled is False and store.load().proactive_level==0
    store.save(ProactivePolicy(enabled=True,proactive_level=1,allow_commitment_reminders=True,maximum_reminders=2,daily_message_limit=2))
    assert ProactivePolicyStore(store.path).load().proactive_level==1

def test_levels_checkins_and_limits_are_deterministic():
    engine=ProactiveDecisionEngine()
    assert engine.decide(EVENT,ProactivePolicy(enabled=True,proactive_level=0,allow_commitment_reminders=True,maximum_reminders=1,daily_message_limit=1),now=NOW) is ProactiveDecision.SUPPRESS
    assert engine.decide(EVENT,ProactivePolicy(enabled=True,proactive_level=1,allow_commitment_reminders=True,maximum_reminders=1,daily_message_limit=1),now=NOW) is ProactiveDecision.REMIND
    assert engine.decide(EVENT,ProactivePolicy(enabled=True,proactive_level=1,allow_commitment_reminders=True,maximum_reminders=1,daily_message_limit=1),now=NOW,reminders_sent=1) is ProactiveDecision.SUPPRESS
    assert engine.decide_checkin(ProactivePolicy(enabled=True,proactive_level=2,allow_checkins=True,daily_message_limit=1,absence_threshold_seconds=60),absence_seconds=61,now=NOW) is ProactiveDecision.CHECK_IN
    assert engine.decide_checkin(ProactivePolicy(enabled=True,proactive_level=2,allow_checkins=True,daily_message_limit=1,absence_threshold_seconds=60,quiet_hours_start=time(15),quiet_hours_end=time(16)),absence_seconds=61,now=NOW) is ProactiveDecision.SUPPRESS


def test_external_events_are_suppressed_at_explicit_trust_boundary():
    assert ProactiveDecisionEngine.external_boundary(ProactiveEventOrigin.EXTERNAL_EVENT) == (
        ProactiveDecision.SUPPRESS,
        "external_event_not_implemented",
    )
    assert ProactiveDecisionEngine.external_boundary(ProactiveEventOrigin.LOCAL_TEMPORAL_EVENT) == (
        None,
        "local_temporal_event",
    )
