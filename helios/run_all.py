"""Refresh official public healthcare data, validate, export, and rebuild the dashboard."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from helios import public_data
from helios.agent import ask
from helios.llm import get_planner


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="use the previously downloaded official archive")
    ap.add_argument("--ask", help="ask about a published indicator")
    ap.add_argument("--planner", choices=("deterministic", "model"), default=None)
    args = ap.parse_args()
    try:
        raw, metadata = public_data.download(ROOT / "data" / "official", args.offline)
        payload = public_data.build_payload(raw, metadata)
        output = ROOT / "outputs" / "dashboard_data.json"
        changed = True
        if output.exists():
            old = json.loads(output.read_text(encoding="utf-8"))
            comparable = dict(payload)
            comparable["source"] = dict(payload["source"], retrieved_at=old.get("source", {}).get("retrieved_at"))
            changed = old != comparable
            if not changed:
                payload = old
        if args.ask:
            print(ask(payload, args.ask, get_planner(args.planner))["text"])
            return 0
        if changed:
            public_data.atomic_json(output, payload)
        subprocess.run([sys.executable, str(ROOT / "dashboard" / "build_dashboard.py")], check=True)
        subprocess.run([sys.executable, str(ROOT / "docs" / "generate_docs.py")], check=True)
        print("Official source:", payload["source"]["title"])
        print("Published:", payload["source"]["release_date"], "Latest observations:", payload["source"]["latest_year"])
        print("Validated cells:", len(payload["rows"]), "Quality:", payload["quality"])
        print("Updated" if changed else "No source changes; existing verified snapshot retained")
        return 0
    except Exception as exc:
        print("Refresh failed; existing dashboard was not replaced with fabricated data:", str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
