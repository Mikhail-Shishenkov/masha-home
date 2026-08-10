from backend.context import ContextBuilder


builder = ContextBuilder(
    "tests/fixtures/test_memory.json",
    "persona/masha.json"
)

context = builder.build(
    persona_id="masha",
    project_id="project_masha_home"
)


print("PERSONA:")
print(context.persona.name)

print("\nPROJECT:")
print(context.project.name)

print("\nFACTS:")

for fact in context.facts:
    print("-", fact.key, "=", fact.value)

print("\nDECISIONS:")

for decision in context.decisions:
    print("-", decision.title)
    print(" ", decision.decision)
    print(" ", decision.reason)

print("\nCOMMITMENTS:")

for commitment in context.commitments:
    print("-", commitment.text)
    print("  owner:", commitment.owner)
    print("  status:", commitment.status)

print("\nEPISODES:")

for episode in context.episodes:
    print("-", episode.title)
    print(" ", episode.summary)