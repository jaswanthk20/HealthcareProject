"""Build a portable dashboard and static hosting output from validated official data."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    payload = json.loads((ROOT / "outputs/dashboard_data.json").read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not payload.get("source", {}).get("source_sha256"):
        raise ValueError("Only validated official-source data can be published")
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = (ROOT / "dashboard/template.html").read_text(encoding="utf-8")
    if template.count("__HELIOS_DATA__") != 1:
        raise ValueError("Dashboard requires one data placeholder")
    html = template.replace("__HELIOS_DATA__", blob)
    (ROOT / "dashboard/helios_dashboard.html").write_text(html, encoding="utf-8")
    dist = ROOT.parent / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text(html, encoding="utf-8")
    print("Built dashboard using", len(payload["rows"]), "published aggregate cells")

if __name__ == "__main__":
    main()
