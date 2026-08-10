import argparse
import json
from pathlib import Path

from backend.memory.memory_models import MemoryDocument


def build_schema() -> dict:
    schema = MemoryDocument.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema


def write_schema(output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(build_schema(), file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the memory JSON Schema")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_schema(args.output)


if __name__ == "__main__":
    main()
