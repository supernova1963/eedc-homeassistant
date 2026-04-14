"""
EEDC PDF-Modul (WeasyPrint + Jinja2).

Neue PDF-Pipeline für Issue #121. Siehe Plan unter
`/home/gernot/.claude/plans/sleepy-frolicking-cupcake.md`.

Öffentliche API:
    render_document(template_name, context) -> bytes
"""
from .engine import render_document

__all__ = ["render_document"]
