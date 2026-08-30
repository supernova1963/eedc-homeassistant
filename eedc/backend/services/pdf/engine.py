"""
WeasyPrint-Wrapper für die neue PDF-Pipeline.

Lädt Jinja2-Templates aus `pdf/templates/`, löst CSS/Logo-Pfade über
eine feste `base_url` auf und rendert HTML → PDF-Bytes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.services.pdf.formatierung import JINJA_FORMATIERER

_PDF_DIR = Path(__file__).parent
_TEMPLATE_DIR = _PDF_DIR / "templates"
_STATIC_DIR = _PDF_DIR / "static"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
# N-234: die deutsche Zahlenschreibweise erreicht ALLE Templates, nicht nur
# jenes, das die Makros zufällig selbst definiert. Jinja vererbt Makros nicht
# über `{% extends %}` — deshalb schrieben Finanzbericht und
# Anlagendokumentation englisch. Als Globals **und** als Filter registriert,
# damit `{{ fmt_eur(v) }}` und `{{ v|fmt_eur }}` beide tragen.
_env.globals.update(JINJA_FORMATIERER)
_env.filters.update(JINJA_FORMATIERER)


def render_html(template_name: str, context: dict[str, Any]) -> str:
    """Dieselbe Renderkette wie `render_document`, nur ohne WeasyPrint.

    N-234: Es gab drei Jinja-Umgebungen im Baum, und eine davon war eine
    **Nachbildung in einer Probe** — sie hätte einen Formatierer-Fehler in der
    echten Umgebung nie gesehen. Wer das HTML prüfen will, nimmt diese Funktion;
    sie trägt Filter, Globals und `static_dir` genau wie der PDF-Weg.
    """
    return _env.get_template(template_name).render(**context, static_dir=str(_STATIC_DIR))


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
