from dataclasses import dataclass, field


@dataclass
class VisualIdentity:
    name: str
    description: str
    reference_image: str | None = None
    generation_notes: list[str] = field(default_factory=list)


@dataclass
class Persona:
    id: str
    name: str
    description: str
    personality: list[str] = field(default_factory=list)
    communication_style: list[str] = field(default_factory=list)
    visual_identity: VisualIdentity | None = None