from backend.context import ContextBuilder


def test_context_builder_collects_project_context(
    memory_path: str,
    persona_path: str,
):
    context = ContextBuilder(
        memory_path=memory_path,
        persona_path=persona_path,
    ).build(
        persona_id="masha",
        project_id="project_masha_home",
    )

    assert context.persona.name == "Маша"
    assert context.project.name == "Masha Home"
    assert {fact.id for fact in context.facts} == {"fact_001", "fact_002"}
    assert [item.id for item in context.decisions] == ["decision_001"]
    assert [item.id for item in context.commitments] == ["commitment_001"]
    assert [item.id for item in context.episodes] == ["episode_001"]
    assert context.working_memory
    assert context.current_time
