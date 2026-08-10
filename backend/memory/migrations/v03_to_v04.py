import argparse
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.memory.memory_models import MemoryDocument


TARGET_VERSION = "0.4"


def _source(value: str | None) -> str:
    if value in {
        "explicit_user_input",
        "conversation",
        "system",
        "inference",
    }:
        return value
    return "system"


def _timestamps(data: dict[str, Any]) -> list[str]:
    result: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key.endswith("_at") and isinstance(nested, str):
                    try:
                        parsed = datetime.fromisoformat(nested)
                    except ValueError:
                        continue
                    if parsed.tzinfo is None:
                        continue
                    result.append(nested)
                else:
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(data)
    return result


def _earliest(values: list[str]) -> str:
    if not values:
        raise ValueError("v0.3 document has no usable timezone-aware timestamps")
    return min(values, key=datetime.fromisoformat)


def _latest(values: list[str]) -> str:
    if not values:
        raise ValueError("v0.3 document has no usable timezone-aware timestamps")
    return max(values, key=datetime.fromisoformat)


def _episode_links(data: dict[str, Any], item_type: str, item_id: str) -> list[str]:
    links: list[str] = []
    collection = {
        "fact": "facts",
        "decision": "decisions",
        "commitment": "commitments",
    }[item_type]
    for episode in data.get("episodes", []):
        for section in ("produced", "updated", "superseded"):
            if item_id in episode.get(section, {}).get(collection, []):
                links.append(episode["id"])
    return list(dict.fromkeys(links))


def _follow_ups(working_memory: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    groups = (
        ("current_blockers", "blocker", "Вернуться к препятствию", 0.9),
        ("next_actions", "next_action", "Продолжить намеченное действие", 0.8),
        ("open_questions", "open_question", "Найти ответ на открытый вопрос", 0.7),
    )
    for field, topic, reason, priority in groups:
        for index, summary in enumerate(working_memory.get(field, []), start=1):
            result.append(
                {
                    "id": f"followup_migrated_{topic}_{index:03d}",
                    "topic": topic,
                    "summary": summary,
                    "reason_to_return": reason,
                    "priority": priority,
                    "status": "open",
                    "source_memory_ids": [],
                    "revisit_after": None,
                }
            )
    return result


def migrate_v03_to_v04(source: dict[str, Any]) -> dict[str, Any]:
    """Return a validated v0.4 copy without mutating the v0.3 input."""
    data = copy.deepcopy(source)
    if data.get("schema_version") == TARGET_VERSION:
        return MemoryDocument.model_validate(data).model_dump(mode="json")

    old_project = data["project"]
    project_id = old_project["id"]
    timestamps = _timestamps(data)
    created_at = old_project.get("created_at") or _earliest(timestamps)
    updated_at = old_project.get("updated_at") or _latest(timestamps)
    status = {
        "paused": "dormant",
        "archived": "completed",
    }.get(old_project.get("status"), old_project.get("status", "active"))
    completed_at = old_project.get("archived_at") if status == "completed" else None

    working_memory = old_project.get("working_memory", {})
    continuity_id = "continuity_masha_misha"
    continuity_states: list[dict[str, Any]] = []
    if working_memory:
        episode_ids = [episode["id"] for episode in data.get("episodes", [])]
        continuity_states.append(
            {
                "id": continuity_id,
                "relationship_key": "masha:misha",
                "last_interaction_at": _latest(timestamps),
                "affective_record_ids": [],
                "current_focus": working_memory.get("architecture_notes", []),
                "intended_follow_ups": _follow_ups(working_memory),
                "based_on_episode_ids": episode_ids,
                "updated_at": updated_at,
            }
        )

    facts = []
    for old in data.get("facts", []):
        item = copy.deepcopy(old)
        item["source"] = _source(item.get("source"))
        item.setdefault("visibility", "visible")
        item.setdefault("project_ids", [project_id])
        item["source_episode_ids"] = _episode_links(data, "fact", item["id"])
        facts.append(item)

    decisions = []
    for old in data.get("decisions", []):
        item = copy.deepcopy(old)
        old_source_episode = item.pop("source_episode", None)
        episode_ids = _episode_links(data, "decision", item["id"])
        if old_source_episode:
            episode_ids.insert(0, old_source_episode)
        item["source"] = _source(item.get("source") or "conversation")
        item["source_episode_ids"] = list(dict.fromkeys(episode_ids))
        item.setdefault("visibility", "visible")
        decisions.append(item)

    commitments = []
    for old in data.get("commitments", []):
        item = copy.deepcopy(old)
        old_source_episode = item.pop("source_episode", None)
        episode_ids = _episode_links(data, "commitment", item["id"])
        if old_source_episode:
            episode_ids.insert(0, old_source_episode)
        if item.get("status") == "active":
            item["status"] = "open"
        item["source"] = _source(item.get("source") or "conversation")
        item["source_episode_ids"] = list(dict.fromkeys(episode_ids))
        item.setdefault("visibility", "visible")
        item.setdefault("replaces_id", None)
        commitments.append(item)

    episodes = []
    old_episodes = data.get("episodes", [])
    latest_episode_id = None
    if old_episodes:
        latest_episode_id = max(
            old_episodes,
            key=lambda episode: datetime.fromisoformat(episode["occurred_at"]),
        )["id"]
    for old in old_episodes:
        item = copy.deepcopy(old)
        context = item.pop("context", {})
        item["source"] = _source(item.get("source"))
        item["importance"] = min(1.0, max(0.0, float(item.get("importance", 0.0))))
        item["visibility"] = "visible"
        item["project_ids"] = context.get("projects", [project_id])
        item["participants"] = context.get("participants", [])
        item["topics"] = context.get("topics", [])
        item.setdefault("related_memory_ids", [])
        item.setdefault("superseded", {"facts": [], "decisions": [], "commitments": []})
        item["produced"].setdefault("reflections", [])
        item["produced"].setdefault("relationship_memories", [])
        item["produced"].setdefault("affective_records", [])
        item["updated"].setdefault("decisions", [])
        item["updated"].setdefault("continuity_states", [])
        if continuity_states and item["id"] == latest_episode_id:
            item["updated"]["continuity_states"].append(continuity_id)
            item["updated"]["continuity_states"] = list(
                dict.fromkeys(item["updated"]["continuity_states"])
            )
        episodes.append(item)

    migrated = {
        "schema_version": TARGET_VERSION,
        "identity_version": "masha-0.1",
        "projects": [
            {
                "id": project_id,
                "name": old_project["name"],
                "description": old_project.get("description"),
                "status": status,
                "created_at": created_at,
                "updated_at": updated_at,
                "completed_at": completed_at,
            }
        ],
        "facts": facts,
        "decisions": decisions,
        "commitments": commitments,
        "episodes": episodes,
        "memory_candidates": [],
        "reflections": [],
        "relationship_memories": [],
        "affective_records": [],
        "continuity_states": continuity_states,
    }
    return MemoryDocument.model_validate(migrated).model_dump(mode="json")


def migrate_file(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8") as file:
        source = json.load(file)
    migrated = migrate_v03_to_v04(source)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(migrated, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate memory JSON from v0.3 to v0.4")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    migrate_file(args.input, args.output)


if __name__ == "__main__":
    main()
