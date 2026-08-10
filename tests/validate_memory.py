import json
from pathlib import Path

from jsonschema import Draft202012Validator


BASE_DIR = Path(__file__).parent

schema_path = BASE_DIR / "memory_schema.json"
memory_path = BASE_DIR / "test_memory.json"


with open(schema_path, "r", encoding="utf-8") as file:
    schema = json.load(file)

with open(memory_path, "r", encoding="utf-8") as file:
    memory = json.load(file)


validator = Draft202012Validator(schema)

errors = sorted(
    validator.iter_errors(memory),
    key=lambda error: list(error.path)
)


if not errors:
    print("Memory is valid.")
else:
    print("Memory is INVALID.")

    for error in errors:
        path = ".".join(str(item) for item in error.path)
        print(f"- {path}: {error.message}")