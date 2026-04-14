"""
WeasyPrint-Wrapper für die neue PDF-Pipeline.

Lädt Jinja2-Templates aus `pdf/templates/`, löst CSS/Logo-Pfade über
eine feste `base_url` auf und rendert HTML → PDF-Bytes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PDF_DIR = Path(__file__).parent
_TEMPLATE_DIR = _PDF_DIR / "templates"
_STATIC_DIR = _PDF_DIR / "static"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_document(template_name: str, context: dict[str, Any]) -> bytes:
    """
    Rendert ein Jinja2-Template zu PDF-Bytes.

    Args:
        template_name: Datei unter `pdf/templates/`, z.B. "selftest.html"
        context: Variablen, die das Template referenzieren darf

    Returns:
        PDF-Datei als bytes
    """
    # Lazy-Import: WeasyPrint zieht beim Modul-Load Pango/Cairo,
    # damit fällt der Backend-Start nicht um, falls die Libs fehlen.
    from weasyprint import HTML

    template = _env.get_template(template_name)
    html_str = template.render(**context, static_dir=str(_STATIC_DIR))

    return HTML(string=html_str, base_url=str(_PDF_DIR)).write_pdf()
