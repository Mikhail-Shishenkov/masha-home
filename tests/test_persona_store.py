from backend.persona.persona_store import PersonaStore


store = PersonaStore("persona/masha.json")

persona = store.get_persona("masha")

print("NAME:")
print(persona.name)

print("\nDESCRIPTION:")
print(persona.description)

print("\nPERSONALITY:")
for item in persona.personality:
    print("-", item)

print("\nCOMMUNICATION:")
for item in persona.communication_style:
    print("-", item)

print("\nUNKNOWN PERSONA:")
print(store.get_persona("unknown"))