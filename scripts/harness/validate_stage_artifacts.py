from __future__ import annotations

import argparse

from harness_common import get_stage_config, stage_dir, validate_expected_artifacts, write_json


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validate expected artifacts for one harness stage.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stage-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    config = get_stage_config(args.stage_id)
    result = validate_expected_artifacts(args.run_id, args.stage_id, config)
    out = stage_dir(args.run_id, args.stage_id) / "artifact_validation.json"
    write_json(out, result)
    print(f"status={result['status']} artifact_validation={out}")


if __name__ == "__main__":
    main()
