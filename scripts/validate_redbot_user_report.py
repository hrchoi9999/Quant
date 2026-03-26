from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reporting.redbot_user_report_schema import validate_report_dict
from src.reporting.render_redbot_user_report import build_report, load_mapping, render_markdown



def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Redbot user-facing report structure and sample rendering")
    parser.add_argument("--asof", default="2026-03-18")
    args = parser.parse_args()

    mapping = load_mapping()
    rendered = []
    for user_model in mapping["user_models"]:
        report, json_path, md_path = build_report(user_model["user_model_name"], None, args.asof)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
        errors = validate_report_dict(report)
        if errors:
            raise SystemExit(f"Validation failed for {user_model['user_model_name']}: {errors}")
        rendered.append((user_model["user_model_name"], json_path, md_path))

    doc_paths = [
        ROOT / "docs" / "REDBOT_USER_REPORT_STRUCTURE.md",
        ROOT / "docs" / "REDBOT_REPORT_COPY_GUIDE.md",
        ROOT / "data" / "configs" / "redbot_user_report_schema.json",
    ]
    missing = [str(path) for path in doc_paths if not path.exists()]
    if missing:
        raise SystemExit("Missing required TASK 11 files: " + ", ".join(missing))

    print("validated_reports=", len(rendered))
    for user_model_name, json_path, md_path in rendered:
        safe_name = str(user_model_name).encode("unicode_escape").decode()
        print(f"{safe_name}: {json_path.name} | {md_path.name}")


if __name__ == "__main__":
    main()
