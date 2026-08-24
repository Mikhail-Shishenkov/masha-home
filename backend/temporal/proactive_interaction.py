"""Local, policy-authorised proactive interaction; no scheduler or fallback."""
from __future__ import annotations

from datetime import datetime, timezone, tzinfo

from backend.conversation.context_compiler import ConversationContextCompiler
from backend.identity.identity_kernel import IdentityKernel
from backend.llm.model_models import ModelMessage
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError
from backend.llm.model_router import ModelRouter
from backend.llm.model_profiles import ModelProfileStore

from .proactive_events import ProactiveEventState, ProactiveEventStore
from .temporal_engine import FixedClock, TemporalEngine
from .timezone_provider import HomeTimeZoneConfig, HomeTimeZoneProvider
from .temporal_models import CheckInCandidate, ProactiveCandidate, ProactiveDecision


class ProactiveInteractionUnavailableError(RuntimeError):
    pass


class ProactiveInteractionStore:
    def __init__(self, repository, *, home_timezone: tzinfo | None = None):
        self.repository = repository
        self.home_timezone = home_timezone or datetime.now().astimezone().tzinfo

    def ensure_candidate(self, candidate: ProactiveCandidate | CheckInCandidate):
        is_checkin = isinstance(candidate, CheckInCandidate)
        event_id = candidate.event_id if is_checkin else candidate.event.event_id
        generated_at = candidate.current_local_time if is_checkin else candidate.generated_at
        now = generated_at.astimezone(timezone.utc).isoformat()
        with self.repository._connection() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute("""INSERT OR IGNORE INTO proactive_interactions(
                    event_id,temporal_event_id,proactive_event_id,decision,state,created_at
                ) VALUES (?,?,?,?,?,?)""", (event_id, None if is_checkin else event_id, event_id if is_checkin else None, candidate.decision.value, "candidate", now))
                row = c.execute("SELECT * FROM proactive_interactions WHERE event_id=?", (event_id,)).fetchone()
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK"); raise
        return dict(row)

    def mark_delivered(self, event_id: str, message: str, now: datetime):
        result = self._transition(event_id, "delivered", "delivered_at", now, message)
        if result.get("proactive_event_id"):
            ProactiveEventStore(self.repository).update_state(event_id, ProactiveEventState.DELIVERED, now)
        return result

    def acknowledge(self, event_id: str, now: datetime): return self._terminal_transition(event_id, "acknowledged", "acknowledged_at", ProactiveEventState.ACKNOWLEDGED, now)
    def dismiss(self, event_id: str, now: datetime): return self._terminal_transition(event_id, "dismissed", "dismissed_at", ProactiveEventState.DISMISSED, now)

    def dismiss_delivered_reminders_for_commitment(self, commitment_id: str, now: datetime):
        """Close only delivered commitment reminders; check-ins remain untouched."""
        with self.repository._connection() as c:
            rows = c.execute("""SELECT pi.event_id FROM proactive_interactions pi
                JOIN temporal_events te ON te.id=pi.temporal_event_id
                WHERE pi.state='delivered' AND te.source_type='commitment' AND te.source_id=?""", (commitment_id,)).fetchall()
        return tuple(self.dismiss(row["event_id"], now) for row in rows)

    def _terminal_transition(self, event_id, state, field, event_state, now):
        result = self._transition(event_id, state, field, now)
        if result.get("proactive_event_id"):
            ProactiveEventStore(self.repository).update_state(event_id, event_state, now)
        return result

    def _transition(self, event_id, state, field, now, message=None):
        with self.repository._connection() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                row = c.execute("SELECT * FROM proactive_interactions WHERE event_id=?", (event_id,)).fetchone()
                if row is None: raise KeyError(event_id)
                if row["state"] in {"acknowledged", "dismissed"}: result = dict(row)
                else:
                    sql = f"UPDATE proactive_interactions SET state=?, {field}=?, message_text=COALESCE(?, message_text) WHERE event_id=?"
                    c.execute(sql, (state, now.astimezone(timezone.utc).isoformat(), message, event_id))
                    result = dict(c.execute("SELECT * FROM proactive_interactions WHERE event_id=?", (event_id,)).fetchone())
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK"); raise
        return result

    def get(self, event_id: str):
        with self.repository._connection() as c:
            row = c.execute("SELECT * FROM proactive_interactions WHERE event_id=?", (event_id,)).fetchone()
        return None if row is None else dict(row)

    def list(self):
        with self.repository._connection() as c:
            rows = c.execute("SELECT * FROM proactive_interactions ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def delivery_stats(self, now: datetime) -> tuple[int, datetime | None]:
        """Return today's delivered count and latest local delivery timestamp."""
        start = now.astimezone(self.home_timezone).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        with self.repository._connection() as c:
            rows = c.execute(
                "SELECT delivered_at FROM proactive_interactions WHERE delivered_at IS NOT NULL"
            ).fetchall()
        delivered = [datetime.fromisoformat(row["delivered_at"]) for row in rows]
        today = [item for item in delivered if item >= start]
        return len(today), max(delivered, default=None)

    def resolve_check_ins_for_user_message(self, message_at: datetime):
        with self.repository._connection() as c:
            rows = c.execute("""SELECT pi.event_id FROM proactive_interactions pi
                JOIN proactive_events pe ON pe.event_id=pi.proactive_event_id
                WHERE pe.event_type='check_in' AND pi.state='delivered'
                  AND pi.delivered_at < ?""", (message_at.astimezone(timezone.utc).isoformat(),)).fetchall()
        resolved = []
        for row in rows:
            resolved.append(self._transition(row["event_id"], "resolved", "resolved_at", message_at))
            ProactiveEventStore(self.repository).update_state(row["event_id"], ProactiveEventState.RESOLVED, message_at)
        return tuple(resolved)


class ProactiveInteractionService:
    def __init__(self, *, store, identity_kernel: IdentityKernel, router: ModelRouter, model_profiles: ModelProfileStore, compiler: ConversationContextCompiler | None = None):
        self.store, self.identity_kernel, self.router, self.model_profiles = store, identity_kernel, router, model_profiles
        self.compiler = compiler or ConversationContextCompiler()

    def formulate(self, candidate: ProactiveCandidate | CheckInCandidate) -> dict:
        if candidate.decision not in {ProactiveDecision.REMIND, ProactiveDecision.CHECK_IN}:
            raise ValueError("only an authorised proactive candidate can be formulated")
        interaction = self.store.ensure_candidate(candidate)
        if interaction["state"] in {"delivered", "acknowledged", "dismissed", "resolved", "expired"}:
            return interaction
        profile = self.model_profiles.get_active_profile()
        is_checkin = isinstance(candidate, CheckInCandidate)
        temporal_context = candidate.current_local_time if is_checkin else candidate.temporal_context
        if is_checkin:
            offset = candidate.current_local_time.utcoffset()
            if offset is None:
                raise ValueError("check-in timezone must be resolved")
            engine = TemporalEngine(
                FixedClock(candidate.current_local_time),
                HomeTimeZoneProvider(
                    HomeTimeZoneConfig(
                        timezone=candidate.timezone,
                        fallback_utc_offset_minutes=int(offset.total_seconds() // 60),
                    ),
                    zone_loader=lambda _name: candidate.current_local_time.tzinfo,
                ),
            )
            temporal_context = engine.context(candidate.last_message_at)
        request = self.compiler.compile(
            messages=(ModelMessage(role="user", content=("Сформулируй одно короткое тёплое человеческое сообщение Мише. Это разрешённый check-in после отсутствия, не диагноз. Не дави, не требуй ответа и не придумывай причины отсутствия." if is_checkin else "Сформулируй одно короткое тёплое напоминание только по разрешённому событию. Не заявляй о выполнении действий.")),),
            identity_context=self.identity_kernel.build_context(), working_memory=[],
            temporal_context=temporal_context, execution_model_id=profile.model_id,
            execution_think=profile.think, execution_timeout_seconds=profile.timeout_seconds,
        ).model_copy(update={"private_context": {"proactive_candidate": candidate.model_dump(mode="json"), "authorised_decision": candidate.decision.value}})
        try:
            response = self.router.generate(request)
        except (ModelProviderUnavailableError, ModelTimeoutError) as error:
            raise ProactiveInteractionUnavailableError("local formulation model is unavailable") from error
        event_id = candidate.event_id if is_checkin else candidate.event.event_id
        delivered_at = candidate.current_local_time if is_checkin else candidate.generated_at
        return self.store.mark_delivered(event_id, response.text, delivered_at)
