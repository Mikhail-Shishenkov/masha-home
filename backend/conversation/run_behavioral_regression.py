"""Run CHAT-02 locally and retain raw responses for manual review."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.conversation.behavioral_regression import CHAT02_CASES, deterministic_flags, serializable_cases


def run(service, *, project_id: str, output_path: str | Path) -> Path:
    results = []
    for case in CHAT02_CASES:
        conversation_id, response = service.send(case.user_message, project_id=project_id)
        results.append({
            "case_id": case.id,
            "category": case.category,
            "conversation_id": conversation_id,
            "response": response,
            "deterministic_flags": deterministic_flags(response, case_id=case.id),
        })
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "suite": "chat-02",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cases": serializable_cases(),
        "results": results,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
