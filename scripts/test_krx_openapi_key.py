from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.collectors.krx_openapi import load_api_key
except Exception:
    load_api_key = None  # type: ignore


BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str


DEFAULT_ENDPOINTS = [
    Endpoint("kospi_stock", "/sto/stk_bydd_trd"),
    Endpoint("kosdaq_stock", "/sto/ksq_bydd_trd"),
    Endpoint("etf", "/etp/etf_bydd_trd"),
    Endpoint("kospi_index", "/idx/kospi_dd_trd"),
]


def _row_count(payload: dict[str, Any]) -> int:
    rows = payload.get("OutBlock_1") or payload.get("output") or payload.get("data") or []
    return len(rows) if isinstance(rows, list) else 0


def _sample_keys(payload: dict[str, Any]) -> list[str]:
    rows = payload.get("OutBlock_1") or payload.get("output") or payload.get("data") or []
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return list(rows[0].keys())[:20]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Test KRX OpenAPI endpoints without printing or storing the API key.")
    parser.add_argument("--bas-dd", required=True, help="YYYYMMDD")
    parser.add_argument("--api-key-env", default="KRX_OPENAPI_KEY")
    parser.add_argument("--api-key-file", default=r"D:\Quant\config\KRX_API_Key.json")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key and load_api_key is not None:
        api_key = load_api_key(args.api_key_file, env_name=args.api_key_env)
    if not api_key:
        raise SystemExit(f"missing environment variable or key file: {args.api_key_env}, {args.api_key_file}")

    headers = {"AUTH_KEY": api_key}
    results: dict[str, Any] = {}
    for endpoint in DEFAULT_ENDPOINTS:
        url = f"{BASE_URL}{endpoint.path}"
        try:
            response = requests.get(url, params={"basDd": args.bas_dd}, headers=headers, timeout=30)
            item: dict[str, Any] = {
                "status_code": response.status_code,
                "path": endpoint.path,
            }
            try:
                payload = response.json()
                item["resp_code"] = payload.get("respCode")
                item["resp_msg"] = payload.get("respMsg")
                item["row_count"] = _row_count(payload)
                item["sample_keys"] = _sample_keys(payload)
            except Exception:
                item["text_head"] = response.text[:300]
            results[endpoint.name] = item
        except Exception as exc:
            results[endpoint.name] = {"path": endpoint.path, "error": repr(exc)}

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
