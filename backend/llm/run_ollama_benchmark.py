"""Run a built-in local benchmark with UTF-8 prompts safely stored in code."""

from __future__ import annotations

import argparse
import json

from .ollama_benchmark import IDENTITY_TONE_V1, run_case


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_id")
    args = parser.parse_args()
    result = run_case(args.model_id, IDENTITY_TONE_V1)
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
