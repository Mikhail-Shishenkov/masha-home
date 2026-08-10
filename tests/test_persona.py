from backend.persona.masha_persona import MashaPersona


print("NAME:")
print(MashaPersona.name)

print("\nPERSONALITY:")
for item in MashaPersona.personality:
    print("-", item)

print("\nVISUAL IDENTITY:")
print(MashaPersona.visual_identity.description)

print("\nREFERENCE:")
print(MashaPersona.visual_identity.reference_image)