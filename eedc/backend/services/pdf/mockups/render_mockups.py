"""
Rendert die Anlagendokumentations-Mockups gegen das Demo-Fixture.

Aufruf:
    backend/venv/bin/python -m backend.services.pdf.mockups.render_mockups

Schreibt:
    /tmp/eedc_anlagenpass_v4_streifen.pdf

V4 ist der aktuelle Stand für Issue #121 (von @rapahl bestätigt).
Die Verworfenen Varianten V1 (Urkunde), V2 (Modern Hero) und
V3 (Minimal) wurden in v3.13.3 entfernt.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from .demo_data import investitionen_demo, musteranlage

_HERE = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(str(_HERE)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_name: str, out_path: Path) -> None:
    ctx = {
        "a": musteranlage(),
        "investitionen": investitionen_demo(),
        "erzeugt_am": datetime.now().strftime("%d.%m.%Y"),
    }
    html_str = _env.get_template(template_name).render(**ctx)
    pdf = HTML(string=html_str, base_url=str(_HERE)).write_pdf()
    out_path.write_bytes(pdf)
    print(f"  {out_path}  ({len(pdf):,} bytes)")


def main() -> None:
    out_dir = Path("/tmp")
    print("Rendere Anlagendokumentations-Mockups:")
    render("anlagenpass_v4_streifen.html", out_dir / "eedc_anlagenpass_v4_streifen.pdf")
    print("Fertig.")


if __name__ == "__main__":
    main()
