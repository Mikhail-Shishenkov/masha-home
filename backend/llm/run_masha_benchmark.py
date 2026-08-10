"""Run the fixed local suite and save raw outputs for human review."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .masha_benchmark_suite import MASHA_HOME_V1
from .ollama_benchmark import run_case


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_id")
    parser.add_argument("--output-dir", type=Path, default=Path("local-data/model-benchmarks"))
    args = parser.parse_args()
    results = [run_case(args.model_id, case).as_dict() for case in MASHA_HOME_V1]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    file_path = args.output_dir / f"{args.model_id.replace(':', '_')}-masha-home-v1.json"
    file_path.write_text(json.dumps({"suite": "masha-home-v1", "created_at": datetime.now(timezone.utc).isoformat(), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(file_path)


if __name__ == "__main__":
    main()
