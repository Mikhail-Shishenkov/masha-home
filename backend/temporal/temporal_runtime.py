"""Offline occurrence/recovery runtime; it never delivers notifications."""
from __future__ import annotations
import sqlite3, uuid
from datetime import timezone


class TemporalRuntime:
    def __init__(self, repository, engine): self.repository, self.engine = repository, engine
    def sync_commitments(self):
        document=self.repository.read_document()
        if document is None: return []
        created=[]
        with self.repository._connection() as c:
            for item in document.commitments:
                if item.status.value != "open" or item.due_at is None: continue
                due=item.due_at.astimezone(timezone.utc).isoformat()
                row=c.execute("SELECT id FROM temporal_events WHERE event_type='commitment_due' AND source_type='commitment' AND source_id=? AND due_at=?",(item.id,due)).fetchone()
                if row is None:
                    event_id=str(uuid.uuid4()); c.execute("INSERT INTO temporal_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",(event_id,'commitment_due','commitment',item.id,due,self.engine.clock.now_utc().isoformat(),'scheduled',None,None,document.identity_version)); created.append(event_id)
        return created
    def tick(self): return self._advance(missed=False)
    def recover_missed_events(self): return self._advance(missed=True)
    def _advance(self, missed):
        now=self.engine.clock.now_utc().isoformat(); changed=[]
        with self.repository._connection() as c:
            rows=c.execute("SELECT id,due_at FROM temporal_events WHERE status='scheduled' AND due_at<=?",(now,)).fetchall()
            for row in rows:
                status='missed' if missed else 'due'; c.execute("UPDATE temporal_events SET status=?,occurred_at=?,recovery_at=? WHERE id=?",(status,row['due_at'],now if missed else None,row['id'])); changed.append(row['id'])
        return changed
    def _events(self, statuses):
        with self.repository._connection() as c: return [dict(row) for row in c.execute(f"SELECT * FROM temporal_events WHERE status IN ({','.join('?'*len(statuses))}) ORDER BY due_at",tuple(statuses))]
    def upcoming_events(self): return self._events(('scheduled',))
    def due_events(self): return self._events(('due',))
    def missed_events(self): return self._events(('missed',))
