"""Export a new, private provisional paper-performance view."""
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.quant2.adapters.quant25_reconstructed_mock_export import export_view  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    export_view(args.run_dir, expected_manifest_sha256=args.manifest_sha256, output_dir=args.output_dir)
    print(hashlib.sha256((args.output_dir / "manifest.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
