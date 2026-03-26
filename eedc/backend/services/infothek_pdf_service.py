"""
Infothek PDF-Export Service

Exportiert Infothek-Einträge als PDF (alle oder gefiltert nach Kategorie).
Nutzt das gleiche Design wie der Jahresbericht (PDFService).
"""

from io import BytesIO
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image,
)

from pathlib import Path
from backend.core.config import APP_VERSION
from backend.services.pdf_service import NumberedCanvas

ICON_PATH = Path(__file__).parent.parent.parent / "icon.png"

# EEDC Farbschema (identisch mit PDFService)
PRIMARY_COLOR = colors.HexColor('#00008B')
ACCENT_COLOR = colors.HexColor('#FF4500')
TEXT_COLOR = colors.HexColor('#1F2937')
LIGHT_TEXT = colors.HexColor('#6B7280')
LIGHT_BG = colors.HexColor('#F3F4F6')
WHITE = colors.white

# Kategorie-Labels (Kurzform für PDF)
KATEGORIE_LABELS = {
    "stromvertrag": "Stromvertrag",
    "einspeisevertrag": "Einspeisevertrag",
    "gasvertrag": "Gasvertrag",
    "wasservertrag": "Wasservertrag",
    "fernwaerme": "Fernwärme",
    "brennstoff": "Brennstoff",
    "versicherung": "Versicherung",
    "ansprechpartner": "Vertragspartner",
    "wartungsvertrag": "Wartungsvertrag",
    "marktstammdatenregister": "Marktstammdatenregister",
    "foerderung": "Förderung",
    "garantie": "Garantie",
    "steuerdaten": "Steuerdaten",
    "sonstiges": "Sonstiges",
}


def generate_infothek_pdf(
    anlagen_name: str,
    eintraege: list[dict],
    vertragspartner_map: dict[int, str],
    kategorie_schemas: dict,
    filter_kategorie: Optional[str] = None,
) -> bytes:
    """
    Generiert ein PDF mit Infothek-Einträgen.

    Args:
        anlagen_name: Name der Anlage
        eintraege: Liste der Einträge als Dicts
        vertragspartner_map: {id: bezeichnung} für Ansprechpartner-Verknüpfungen
        kategorie_schemas: Kategorie-Feld-Definitionen
        filter_kategorie: Optional — nur diese Kategorie exportieren

    Returns:
        PDF als bytes
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=2.5 * cm,
        bottomMargin=2.0 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    _setup_styles(styles)

    elements = []

    # Header
    elements.extend(_build_header(styles, anlagen_name, filter_kategorie))

    # Vertragspartner-Sektion
    vp_eintraege = [e for e in eintraege if e["kategorie"] == "ansprechpartner"]
    andere_eintraege = [e for e in eintraege if e["kategorie"] != "ansprechpartner"]

    if vp_eintraege and not filter_kategorie:
        elements.extend(
            _build_sektion(styles, "Vertragspartner", vp_eintraege, kategorie_schemas, vertragspartner_map)
        )

    # Nach Kategorie gruppieren
    kategorien_order: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for e in andere_eintraege:
        kat = e["kategorie"]
        if kat not in grouped:
            kategorien_order.append(kat)
            grouped[kat] = []
        grouped[kat].append(e)

    for kat in kategorien_order:
        label = KATEGORIE_LABELS.get(kat, kat)
        elements.extend(
            _build_sektion(styles, label, grouped[kat], kategorie_schemas, vertragspartner_map)
        )

    # Footer
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_TEXT))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        f"Erstellt am {datetime.now().strftime('%d.%m.%Y %H:%M')} · EEDC v{APP_VERSION}",
        styles["SmallCenter"],
    ))

    doc.build(elements, canvasmaker=NumberedCanvas)
    return buf.getvalue()


def _setup_styles(styles):
    """Definiert benutzerdefinierte Styles."""
    styles.add(ParagraphStyle(
        name='MainTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=6,
        textColor=ACCENT_COLOR,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='Subtitle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=4,
        textColor=TEXT_COLOR,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading2'],
        fontSize=13,
        spaceBefore=14,
        spaceAfter=6,
        textColor=WHITE,
        backColor=PRIMARY_COLOR,
        borderPadding=5,
    ))
    styles.add(ParagraphStyle(
        name='EntryTitle',
        parent=styles['Heading3'],
        fontSize=11,
        spaceBefore=8,
        spaceAfter=4,
        textColor=PRIMARY_COLOR,
    ))
    styles.add(ParagraphStyle(
        name='FieldLabel',
        parent=styles['Normal'],
        fontSize=8,
        textColor=LIGHT_TEXT,
    ))
    styles.add(ParagraphStyle(
        name='FieldValue',
        parent=styles['Normal'],
        fontSize=9,
        textColor=TEXT_COLOR,
    ))
    styles.add(ParagraphStyle(
        name='Notizen',
        parent=styles['Normal'],
        fontSize=9,
        textColor=TEXT_COLOR,
        spaceBefore=4,
        leftIndent=10,
        rightIndent=10,
        backColor=LIGHT_BG,
        borderPadding=6,
    ))
    styles.add(ParagraphStyle(
        name='SmallCenter',
        parent=styles['Normal'],
        fontSize=8,
        textColor=LIGHT_TEXT,
        alignment=TA_CENTER,
    ))


def _build_header(styles, anlagen_name: str, filter_kategorie: Optional[str]) -> list:
    """Baut den PDF-Header mit Titel und Untertitel."""
    elements = []

    # Icon
    if ICON_PATH.exists():
        try:
            img = Image(str(ICON_PATH), width=1.5 * cm, height=1.5 * cm)
            img.hAlign = 'CENTER'
            elements.append(img)
            elements.append(Spacer(1, 6))
        except Exception:
            pass

    elements.append(Paragraph("Infothek", styles["MainTitle"]))

    subtitle = anlagen_name
    if filter_kategorie:
        label = KATEGORIE_LABELS.get(filter_kategorie, filter_kategorie)
        subtitle += f" — {label}"
    elements.append(Paragraph(subtitle, styles["Subtitle"]))

    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=2, color=PRIMARY_COLOR))
    elements.append(Spacer(1, 10))

    return elements


def _build_sektion(
    styles,
    titel: str,
    eintraege: list[dict],
    kategorie_schemas: dict,
    vertragspartner_map: dict[int, str],
) -> list:
    """Baut eine Kategorie-Sektion mit allen Einträgen."""
    elements = []
    elements.append(Paragraph(titel, styles["SectionHeader"]))

    for eintrag in eintraege:
        elements.extend(
            _build_eintrag(styles, eintrag, kategorie_schemas, vertragspartner_map)
        )

    return elements


def _build_eintrag(
    styles,
    eintrag: dict,
    kategorie_schemas: dict,
    vertragspartner_map: dict[int, str],
) -> list:
    """Baut einen einzelnen Eintrag als KeepTogether-Block."""
    parts = []
    bezeichnung = eintrag.get("bezeichnung", "")
    kategorie = eintrag.get("kategorie", "")
    parameter = eintrag.get("parameter") or {}
    notizen = eintrag.get("notizen")
    ansprechpartner_id = eintrag.get("ansprechpartner_id")

    # Titel
    parts.append(Paragraph(bezeichnung, styles["EntryTitle"]))

    # Vertragspartner-Verknüpfung
    if ansprechpartner_id and ansprechpartner_id in vertragspartner_map:
        parts.append(Paragraph(
            f"Vertragspartner: {vertragspartner_map[ansprechpartner_id]}",
            styles["FieldValue"],
        ))

    # Parameter als Tabelle
    schema_felder = kategorie_schemas.get(kategorie, {}).get("felder", {})
    rows = []
    for key, feld_def in schema_felder.items():
        val = parameter.get(key)
        if val is not None and val != "":
            label = feld_def.get("label", key)
            rows.append([
                Paragraph(label, styles["FieldLabel"]),
                Paragraph(str(val), styles["FieldValue"]),
            ])

    # Unbekannte Parameter-Keys die nicht im Schema sind
    for key, val in parameter.items():
        if key not in schema_felder and val is not None and val != "":
            rows.append([
                Paragraph(key.replace("_", " ").title(), styles["FieldLabel"]),
                Paragraph(str(val), styles["FieldValue"]),
            ])

    if rows:
        page_width = A4[0] - 3 * cm
        t = Table(rows, colWidths=[page_width * 0.35, page_width * 0.65])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#E5E7EB')),
        ]))
        parts.append(t)

    # Notizen (einfaches Markdown → Reportlab)
    if notizen:
        parts.extend(_markdown_to_paragraphs(notizen, styles))

    parts.append(Spacer(1, 6))

    return [KeepTogether(parts)]


import re

def _markdown_to_paragraphs(text: str, styles) -> list:
    """
    Konvertiert einfaches Markdown zu Reportlab-Paragraphs.

    Unterstützt: **bold**, *italic*, - Listen, [text](url)
    """
    result = []
    lines = text.split("\n")
    list_items: list[str] = []

    def flush_list():
        if list_items:
            bullet_text = "<br/>".join(f"\u2022 {item}" for item in list_items)
            result.append(Paragraph(bullet_text, styles["Notizen"]))
            list_items.clear()

    for line in lines:
        stripped = line.strip()

        # Listenpunkt
        if stripped.startswith("- ") or stripped.startswith("* "):
            list_items.append(_inline_markdown(stripped[2:]))
            continue

        flush_list()

        if not stripped:
            continue

        # Normaler Absatz
        result.append(Paragraph(_inline_markdown(stripped), styles["Notizen"]))

    flush_list()
    return result


def _inline_markdown(text: str) -> str:
    """Konvertiert Inline-Markdown zu Reportlab-XML (bold, italic, links)."""
    # Links: [text](url) → <a href="url">text</a>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" color="#00008B">\1</a>', text)
    # Bold: **text** → <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Italic: *text* → <i>text</i>
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    return text
