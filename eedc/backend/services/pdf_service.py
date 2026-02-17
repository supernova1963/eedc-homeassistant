"""
PDF Service - Generiert vollstaendige PDF-Jahresberichte fuer PV-Anlagen.

Verwendet reportlab fuer die PDF-Erstellung inkl. Charts.
"""

from io import BytesIO
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether, Image
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.graphics.shapes import Drawing, String, Line
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.widgets.markers import makeMarker

from pathlib import Path

from backend.core.config import APP_VERSION

# Pfad zum Icon (relativ zum Backend-Verzeichnis)
ICON_PATH = Path(__file__).parent.parent.parent / "icon.png"


# =============================================================================
# Datenklassen
# =============================================================================

@dataclass
class AnlagenDokumentation:
    """Vollstaendige Anlagen-Stammdaten."""
    name: str
    leistung_kwp: float
    installationsdatum: Optional[date] = None
    mastr_id: Optional[str] = None
    wetter_provider: Optional[str] = None
    # Standort
    standort_plz: Optional[str] = None
    standort_ort: Optional[str] = None
    standort_strasse: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Versorger
    versorger_daten: Optional[Dict] = None
    # HA-Integration
    ha_sensor_pv_erzeugung: Optional[str] = None
    ha_sensor_einspeisung: Optional[str] = None
    ha_sensor_netzbezug: Optional[str] = None
    ha_sensor_batterie_ladung: Optional[str] = None
    ha_sensor_batterie_entladung: Optional[str] = None


@dataclass
class StromtarifDaten:
    """Aktueller Stromtarif."""
    tarifname: Optional[str] = None
    anbieter: Optional[str] = None
    netzbezug_cent_kwh: float = 30.0
    einspeiseverguetung_cent_kwh: float = 8.2
    grundpreis_euro_monat: Optional[float] = None
    gueltig_ab: Optional[date] = None


@dataclass
class InvestitionDokumentation:
    """Vollstaendige Investitions-Dokumentation."""
    typ: str
    bezeichnung: str
    anschaffungsdatum: Optional[date] = None
    anschaffungskosten: Optional[float] = None
    alternativkosten: Optional[float] = None
    betriebskosten_jahr: Optional[float] = None
    leistung_kwp: Optional[float] = None
    ausrichtung: Optional[str] = None
    neigung_grad: Optional[float] = None
    parent_bezeichnung: Optional[str] = None
    # Technische Parameter
    parameter: Dict = field(default_factory=dict)
    # Stammdaten
    stamm_hersteller: Optional[str] = None
    stamm_modell: Optional[str] = None
    stamm_seriennummer: Optional[str] = None
    stamm_garantie_bis: Optional[str] = None
    stamm_mastr_id: Optional[str] = None
    # Ansprechpartner
    ansprechpartner_firma: Optional[str] = None
    ansprechpartner_name: Optional[str] = None
    ansprechpartner_telefon: Optional[str] = None
    ansprechpartner_email: Optional[str] = None
    ansprechpartner_kundennummer: Optional[str] = None
    # Wartung
    wartung_vertragsnummer: Optional[str] = None
    wartung_anbieter: Optional[str] = None
    wartung_gueltig_bis: Optional[str] = None
    wartung_leistungsumfang: Optional[str] = None


@dataclass
class JahresKPIs:
    """Aggregierte Jahres-KPIs."""
    # Energie
    pv_erzeugung_kwh: float = 0
    eigenverbrauch_kwh: float = 0
    einspeisung_kwh: float = 0
    netzbezug_kwh: float = 0
    gesamtverbrauch_kwh: float = 0
    autarkie_prozent: float = 0
    eigenverbrauch_quote_prozent: float = 0
    spezifischer_ertrag_kwh_kwp: Optional[float] = None
    # Speicher
    hat_speicher: bool = False
    speicher_kapazitaet_kwh: float = 0
    speicher_ladung_kwh: float = 0
    speicher_entladung_kwh: float = 0
    speicher_vollzyklen: Optional[float] = None
    speicher_effizienz_prozent: Optional[float] = None
    # Waermepumpe
    hat_waermepumpe: bool = False
    wp_waerme_kwh: float = 0
    wp_heizung_kwh: float = 0
    wp_warmwasser_kwh: float = 0
    wp_strom_kwh: float = 0
    wp_cop: Optional[float] = None
    wp_ersparnis_euro: float = 0
    # E-Mobilitaet
    hat_emobilitaet: bool = False
    emob_km: float = 0
    emob_ladung_kwh: float = 0
    emob_pv_kwh: float = 0
    emob_netz_kwh: float = 0
    emob_v2h_kwh: float = 0
    emob_pv_anteil_prozent: Optional[float] = None
    emob_ersparnis_euro: float = 0
    # Finanzen
    einspeise_erloes_euro: float = 0
    ev_ersparnis_euro: float = 0
    netto_ertrag_euro: float = 0
    jahres_rendite_prozent: Optional[float] = None
    investition_gesamt_euro: float = 0
    investition_mehrkosten_euro: float = 0
    # CO2
    co2_pv_kg: float = 0
    co2_wp_kg: float = 0
    co2_emob_kg: float = 0
    co2_gesamt_kg: float = 0


@dataclass
class MonatsZeile:
    """Eine Zeile fuer die Monatstabellen."""
    monat: int
    monat_name: str
    jahr: Optional[int] = None  # Fuer Gesamtzeitraum-Ansicht
    # Energie
    pv_erzeugung_kwh: float = 0
    eigenverbrauch_kwh: float = 0
    einspeisung_kwh: float = 0
    netzbezug_kwh: float = 0
    autarkie_prozent: float = 0
    spezifischer_ertrag: float = 0
    # Speicher
    speicher_ladung_kwh: float = 0
    speicher_entladung_kwh: float = 0
    speicher_effizienz_prozent: float = 0
    speicher_vollzyklen: float = 0
    # Waermepumpe
    wp_waerme_kwh: float = 0
    wp_heizung_kwh: float = 0
    wp_warmwasser_kwh: float = 0
    wp_strom_kwh: float = 0
    wp_cop: Optional[float] = None
    wp_pv_anteil_prozent: float = 0
    # E-Mobilitaet
    emob_km: float = 0
    emob_ladung_kwh: float = 0
    emob_pv_kwh: float = 0
    emob_netz_kwh: float = 0
    emob_v2h_kwh: float = 0
    emob_pv_anteil_prozent: float = 0
    # Finanzen
    einsp_erloes_euro: float = 0
    ev_ersparnis_euro: float = 0
    wp_ersparnis_euro: float = 0
    emob_ersparnis_euro: float = 0
    netto_ertrag_euro: float = 0
    # Prognose
    pvgis_prognose_kwh: Optional[float] = None


@dataclass
class FinanzPrognose:
    """Finanz-Prognose und Amortisation."""
    investition_mehrkosten_euro: float = 0
    bisherige_ertraege_euro: float = 0
    amortisations_fortschritt_prozent: float = 0
    amortisation_erreicht: bool = False
    amortisation_prognose_jahr: Optional[int] = None
    restlaufzeit_monate: Optional[int] = None
    jahres_ertrag_prognose_euro: float = 0
    jahres_rendite_prognose_prozent: Optional[float] = None


@dataclass
class StringVergleich:
    """PV-String SOLL vs. IST Vergleich."""
    bezeichnung: str
    leistung_kwp: float
    ausrichtung: Optional[str] = None
    neigung_grad: Optional[float] = None
    prognose_kwh: float = 0
    ist_kwh: float = 0
    abweichung_kwh: float = 0
    abweichung_prozent: float = 0
    spezifischer_ertrag: float = 0


# =============================================================================
# =============================================================================
# Numbered Canvas fuer "Seite X von Y"
# =============================================================================

class NumberedCanvas(canvas.Canvas):
    """Canvas-Klasse, die die Gesamtseitenzahl ermittelt."""

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """Fuegt Seitenzahlen hinzu und speichert das Dokument."""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        """Zeichnet 'Seite X von Y' in die Fusszeile."""
        page_width, page_height = A4
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor('#6B7280'))  # LIGHT_TEXT
        page_num = self._pageNumber
        self.drawRightString(
            page_width - 1.5*cm,
            1.0*cm,
            f"Seite {page_num} von {page_count}"
        )


# =============================================================================
# PDF Service
# =============================================================================

class PDFService:
    """Service zur Generierung von PDF-Jahresberichten."""

    # EEDC Farbschema
    PRIMARY_COLOR = colors.HexColor('#00008B')      # Darkblue - Hauptfarbe fuer Ueberschriften-Hintergrund
    ACCENT_COLOR = colors.HexColor('#FF4500')       # Orangered - Akzentfarbe fuer Kapitel-Titel
    SECONDARY_COLOR = colors.HexColor('#10B981')    # Emerald-500
    WARNING_COLOR = colors.HexColor('#F59E0B')      # Amber-500
    DANGER_COLOR = colors.HexColor('#EF4444')       # Red-500
    TEXT_COLOR = colors.HexColor('#1F2937')         # Gray-800
    LIGHT_TEXT = colors.HexColor('#6B7280')         # Gray-500
    LIGHT_BG = colors.HexColor('#F3F4F6')           # Gray-100
    WHITE = colors.white

    # Monatsnamen
    MONATSNAMEN = [
        "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]
    MONATSNAMEN_KURZ = ["", "Jan", "Feb", "Mar", "Apr", "Mai", "Jun",
                        "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Definiert benutzerdefinierte Styles."""
        # Titel
        self.styles.add(ParagraphStyle(
            name='MainTitle',
            parent=self.styles['Heading1'],
            fontSize=22,
            spaceAfter=6,
            textColor=self.ACCENT_COLOR,  # Orangered fuer Haupttitel
            alignment=TA_CENTER,
        ))
        # Untertitel
        self.styles.add(ParagraphStyle(
            name='Subtitle',
            parent=self.styles['Normal'],
            fontSize=14,
            spaceAfter=4,
            textColor=self.TEXT_COLOR,
            alignment=TA_CENTER,
        ))
        # Section Header (Kapitel-Ueberschriften) - Weiss auf Darkblue
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=16,
            spaceAfter=8,
            textColor=self.WHITE,
            backColor=self.PRIMARY_COLOR,  # Darkblue Hintergrund
            borderPadding=6,
        ))
        # Subsection Header
        self.styles.add(ParagraphStyle(
            name='SubsectionHeader',
            parent=self.styles['Heading3'],
            fontSize=11,
            spaceBefore=10,
            spaceAfter=4,
            textColor=self.ACCENT_COLOR,  # Orangered fuer Unterkapitel
        ))
        # Normal Text
        self.styles.add(ParagraphStyle(
            name='EEDCBody',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=self.TEXT_COLOR,
            spaceAfter=4,
        ))
        # Footer
        self.styles.add(ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=self.LIGHT_TEXT,
            alignment=TA_CENTER,
        ))

    def _safe_str(self, value: Any, default: str = "-") -> str:
        """Konvertiert Wert zu String, None wird zu default."""
        if value is None:
            return default
        if isinstance(value, float):
            return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if isinstance(value, date):
            return value.strftime("%d.%m.%Y")
        return str(value)

    def _format_kwh(self, value: Optional[float], decimals: int = 0) -> str:
        """Formatiert kWh-Werte."""
        if value is None:
            return "-"
        if decimals == 0:
            return f"{value:,.0f}".replace(",", ".")
        return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _format_euro(self, value: Optional[float]) -> str:
        """Formatiert Euro-Werte."""
        if value is None:
            return "-"
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _format_percent(self, value: Optional[float], decimals: int = 1) -> str:
        """Formatiert Prozent-Werte."""
        if value is None:
            return "-"
        return f"{value:.{decimals}f}%"

    # =========================================================================
    # Hauptmethode
    # =========================================================================

    def generate_jahresbericht(
        self,
        anlage: AnlagenDokumentation,
        stromtarif: StromtarifDaten,
        investitionen: List[InvestitionDokumentation],
        jahres_kpis: JahresKPIs,
        monats_daten: List[MonatsZeile],
        finanz_prognose: Optional[FinanzPrognose],
        string_vergleiche: List[StringVergleich],
        jahr: Optional[int] = None,
        start_jahr: Optional[int] = None,
        end_jahr: Optional[int] = None,
    ) -> BytesIO:
        """
        Generiert einen vollstaendigen Bericht als PDF.

        Args:
            jahr: Einzelnes Jahr (fuer Jahresbericht)
            start_jahr/end_jahr: Zeitraum (fuer Gesamtbericht)

        Returns:
            BytesIO: PDF-Datei als ByteStream
        """
        buffer = BytesIO()

        # Zeitraum-Anzeige fuer Titel und Kopfzeile
        if jahr:
            zeitraum_text = str(jahr)
        elif start_jahr and end_jahr:
            if start_jahr == end_jahr:
                zeitraum_text = str(start_jahr)
            else:
                zeitraum_text = f"{start_jahr} - {end_jahr}"
        else:
            zeitraum_text = "Gesamtzeitraum"

        # Metadaten fuer Kopf-/Fusszeile speichern
        self._doc_anlagenname = anlage.name
        self._doc_zeitraum = zeitraum_text
        self._doc_erstellungsdatum = datetime.now().strftime('%d.%m.%Y')

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2.5*cm,   # Mehr Platz fuer Kopfzeile
            bottomMargin=2.0*cm,  # Mehr Platz fuer Fusszeile
        )

        story = []

        # Titelseite
        story.extend(self._build_header(anlage.name, zeitraum_text))

        # Teil 1: Anlagen-Dokumentation
        story.extend(self._build_anlagen_dokumentation(anlage, stromtarif))

        # Teil 2: Investitionen
        story.append(PageBreak())
        story.extend(self._build_investitionen(investitionen))

        # Teil 3: Jahresuebersicht
        story.append(PageBreak())
        story.extend(self._build_jahresuebersicht(jahres_kpis, anlage.leistung_kwp))

        # Teil 4: Charts
        story.extend(self._build_charts(monats_daten, jahres_kpis))

        # Teil 5: Monatsuebersicht
        story.append(PageBreak())
        story.extend(self._build_monatsuebersicht(monats_daten, jahres_kpis))

        # Teil 6: Prognosen & Finanzen
        if finanz_prognose:
            story.extend(self._build_finanz_prognose(finanz_prognose))

        # Teil 7: String-Vergleich
        if string_vergleiche:
            story.extend(self._build_string_vergleich(string_vergleiche))

        # Footer (Abschluss im Content)
        story.extend(self._build_footer())

        # PDF mit Kopf-/Fusszeilen generieren
        # NumberedCanvas sorgt fuer "Seite X von Y"
        doc.build(
            story,
            onFirstPage=self._draw_first_page,
            onLaterPages=self._draw_later_pages,
            canvasmaker=NumberedCanvas,
        )
        buffer.seek(0)
        return buffer

    def _draw_first_page(self, canvas_obj: canvas.Canvas, doc):
        """Zeichnet Fusszeile auf der ersten Seite (keine Kopfzeile)."""
        canvas_obj.saveState()
        self._draw_footer(canvas_obj, doc)
        canvas_obj.restoreState()

    def _draw_later_pages(self, canvas_obj: canvas.Canvas, doc):
        """Zeichnet Kopf- und Fusszeile ab Seite 2."""
        canvas_obj.saveState()
        self._draw_header(canvas_obj, doc)
        self._draw_footer(canvas_obj, doc)
        canvas_obj.restoreState()

    def _draw_header(self, canvas_obj: canvas.Canvas, doc):
        """Zeichnet die Kopfzeile ab Seite 2."""
        page_width, page_height = A4

        # Kopfzeile Y-Position (oben)
        y = page_height - 1.2*cm

        # Linke Seite: Anlagenname
        canvas_obj.setFont("Helvetica-Bold", 9)
        canvas_obj.setFillColor(self.TEXT_COLOR)
        canvas_obj.drawString(1.5*cm, y, self._doc_anlagenname)

        # Mitte: EEDC Anlagenbericht [Zeitraum]
        titel = f"EEDC Anlagenbericht {self._doc_zeitraum}"
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(self.ACCENT_COLOR)
        text_width = canvas_obj.stringWidth(titel, "Helvetica", 9)
        canvas_obj.drawString((page_width - text_width) / 2, y, titel)

        # Rechte Seite: EEDC Icon
        if ICON_PATH.exists():
            # Icon rechts ausrichten (ca. 0.8cm hoch, Seitenverhaeltnis 1:1)
            icon_height = 0.8*cm
            icon_width = icon_height  # quadratisch
            canvas_obj.drawImage(
                str(ICON_PATH),
                page_width - 1.5*cm - icon_width,
                y - 0.15*cm,  # leicht nach unten versetzt fuer Ausrichtung
                width=icon_width,
                height=icon_height,
                preserveAspectRatio=True,
                mask='auto'
            )
        else:
            # Fallback: Text wenn Icon nicht gefunden
            canvas_obj.setFont("Helvetica-Bold", 9)
            canvas_obj.setFillColor(self.PRIMARY_COLOR)
            canvas_obj.drawRightString(page_width - 1.5*cm, y, "eedc")

        # Trennlinie unter Kopfzeile
        canvas_obj.setStrokeColor(self.LIGHT_BG)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(1.5*cm, y - 0.3*cm, page_width - 1.5*cm, y - 0.3*cm)

    def _draw_footer(self, canvas_obj: canvas.Canvas, doc):
        """Zeichnet die Fusszeile auf jeder Seite (ohne Seitenzahl - das macht NumberedCanvas)."""
        page_width, page_height = A4

        # Fusszeile Y-Position (unten)
        y = 1.0*cm

        # Trennlinie ueber Fusszeile
        canvas_obj.setStrokeColor(self.LIGHT_BG)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(1.5*cm, y + 0.5*cm, page_width - 1.5*cm, y + 0.5*cm)

        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.setFillColor(self.LIGHT_TEXT)

        # Linke Seite: Erstellungsdatum
        canvas_obj.drawString(1.5*cm, y, f"Erstellt am {self._doc_erstellungsdatum}")

        # Mitte: GitHub Repository
        github_url = "github.com/supernova1963/eedc-homeassistant"
        text_width = canvas_obj.stringWidth(github_url, "Helvetica", 8)
        canvas_obj.drawString((page_width - text_width) / 2, y, github_url)

        # Rechte Seite: Seitenzahl wird von NumberedCanvas gezeichnet ("Seite X von Y")

    # =========================================================================
    # Header
    # =========================================================================

    def _build_header(self, anlagen_name: str, zeitraum: str) -> List:
        """Erstellt den Header mit Titel."""
        elements = []

        # Bei Gesamtzeitraum: "Anlagenbericht", bei Jahr: "Jahresbericht"
        if "-" in zeitraum or zeitraum == "Gesamtzeitraum":
            titel = f"EEDC Anlagenbericht {zeitraum}"
        else:
            titel = f"EEDC Jahresbericht {zeitraum}"

        elements.append(Paragraph(
            titel,
            self.styles['MainTitle']
        ))
        elements.append(Paragraph(
            f"<b>{anlagen_name}</b>",
            self.styles['Subtitle']
        ))
        elements.append(Paragraph(
            f"Erstellt am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}",
            self.styles['Footer']
        ))
        elements.append(Spacer(1, 15))
        elements.append(HRFlowable(width="100%", thickness=2, color=self.PRIMARY_COLOR))
        elements.append(Spacer(1, 15))

        return elements

    # =========================================================================
    # Teil 1: Anlagen-Dokumentation
    # =========================================================================

    def _build_anlagen_dokumentation(
        self,
        anlage: AnlagenDokumentation,
        stromtarif: StromtarifDaten
    ) -> List:
        """Erstellt die vollstaendige Anlagen-Dokumentation."""
        elements = []

        elements.append(Paragraph("1. Anlagen-Dokumentation", self.styles['SectionHeader']))

        # 1.1 Grunddaten
        elements.append(Paragraph("1.1 Grunddaten", self.styles['SubsectionHeader']))
        grunddaten = [
            ["Anlagenname:", anlage.name],
            ["Gesamtleistung:", f"{anlage.leistung_kwp:.1f} kWp"],
            ["Inbetriebnahme:", self._safe_str(anlage.installationsdatum)],
            ["MaStR-ID:", self._safe_str(anlage.mastr_id)],
            ["Wetter-Provider:", self._get_provider_name(anlage.wetter_provider)],
        ]
        elements.append(self._create_key_value_table(grunddaten))

        # 1.2 Standort
        elements.append(Paragraph("1.2 Standort", self.styles['SubsectionHeader']))
        adresse = ""
        if anlage.standort_strasse:
            adresse = anlage.standort_strasse
        if anlage.standort_plz or anlage.standort_ort:
            if adresse:
                adresse += ", "
            adresse += f"{anlage.standort_plz or ''} {anlage.standort_ort or ''}".strip()

        koordinaten = "-"
        if anlage.latitude and anlage.longitude:
            koordinaten = f"{anlage.latitude:.4f}° N, {anlage.longitude:.4f}° O"

        standort = [
            ["Adresse:", adresse or "-"],
            ["Koordinaten:", koordinaten],
        ]
        elements.append(self._create_key_value_table(standort))

        # 1.3 Stromversorger
        elements.append(Paragraph("1.3 Stromversorger", self.styles['SubsectionHeader']))
        if anlage.versorger_daten and anlage.versorger_daten.get("strom"):
            strom = anlage.versorger_daten["strom"]
            versorger = [
                ["Anbieter:", self._safe_str(strom.get("name"))],
                ["Kundennummer:", self._safe_str(strom.get("kundennummer"))],
                ["Portal:", self._safe_str(strom.get("portal_url"))],
            ]
            elements.append(self._create_key_value_table(versorger))

            # Zaehler
            zaehler = strom.get("zaehler", [])
            if zaehler:
                elements.append(Paragraph("<b>Zaehler:</b>", self.styles['EEDCBody']))
                for z in zaehler:
                    bez = z.get("bezeichnung", "Zaehler")
                    nr = z.get("nummer", "-")
                    elements.append(Paragraph(f"  - {bez}: {nr}", self.styles['EEDCBody']))
        else:
            elements.append(Paragraph("Keine Versorger-Daten erfasst.", self.styles['EEDCBody']))

        # 1.4 Stromtarif
        elements.append(Paragraph("1.4 Stromtarif (aktuell)", self.styles['SubsectionHeader']))
        tarif = [
            ["Tarifname:", self._safe_str(stromtarif.tarifname)],
            ["Anbieter:", self._safe_str(stromtarif.anbieter)],
            ["Netzbezug:", f"{stromtarif.netzbezug_cent_kwh:.2f} ct/kWh"],
            ["Einspeiseverguetung:", f"{stromtarif.einspeiseverguetung_cent_kwh:.2f} ct/kWh"],
            ["Grundpreis:", f"{self._format_euro(stromtarif.grundpreis_euro_monat)} EUR/Monat" if stromtarif.grundpreis_euro_monat else "-"],
            ["Gueltig ab:", self._safe_str(stromtarif.gueltig_ab)],
        ]
        elements.append(self._create_key_value_table(tarif))

        # 1.5 Home Assistant Integration (nur anzeigen wenn Sensoren konfiguriert)
        ha_sensoren_configured = [
            ("PV-Erzeugung:", anlage.ha_sensor_pv_erzeugung),
            ("Einspeisung:", anlage.ha_sensor_einspeisung),
            ("Netzbezug:", anlage.ha_sensor_netzbezug),
            ("Batterie-Ladung:", anlage.ha_sensor_batterie_ladung),
            ("Batterie-Entladung:", anlage.ha_sensor_batterie_entladung),
        ]
        # Nur nicht-leere Sensoren
        ha_sensoren_filled = [(label, sensor) for label, sensor in ha_sensoren_configured if sensor]

        if ha_sensoren_filled:
            elements.append(Paragraph("1.5 Home Assistant Integration", self.styles['SubsectionHeader']))
            ha_sensoren = [[label, self._safe_str(sensor)] for label, sensor in ha_sensoren_filled]
            elements.append(self._create_key_value_table(ha_sensoren))

        return elements

    def _get_provider_name(self, provider: Optional[str]) -> str:
        """Konvertiert Provider-ID zu lesbarem Namen."""
        names = {
            "auto": "Automatisch",
            "brightsky": "Bright Sky (DWD)",
            "open-meteo": "Open-Meteo",
            "open-meteo-solar": "Open-Meteo Solar",
        }
        return names.get(provider or "auto", provider or "-")

    # =========================================================================
    # Teil 2: Investitionen
    # =========================================================================

    def _build_investitionen(self, investitionen: List[InvestitionDokumentation]) -> List:
        """Erstellt die Investitionen-Dokumentation."""
        elements = []

        elements.append(Paragraph("2. Investitionen & Komponenten", self.styles['SectionHeader']))

        if not investitionen:
            elements.append(Paragraph("Keine Investitionen erfasst.", self.styles['EEDCBody']))
            return elements

        typ_labels = {
            "wechselrichter": "Wechselrichter",
            "pv-module": "PV-Module",
            "speicher": "Speicher",
            "waermepumpe": "Waermepumpe",
            "e-auto": "E-Auto",
            "wallbox": "Wallbox",
            "balkonkraftwerk": "Balkonkraftwerk",
            "sonstiges": "Sonstiges",
        }

        gesamt_kosten = 0
        gesamt_mehrkosten = 0

        for inv in investitionen:
            typ_label = typ_labels.get(inv.typ, inv.typ)
            elements.append(Paragraph(
                f"<b>{typ_label}: {inv.bezeichnung}</b>",
                self.styles['SubsectionHeader']
            ))

            # Technische Daten
            tech_daten = []
            if inv.leistung_kwp:
                if inv.typ == "speicher":
                    tech_daten.append(["Kapazitaet:", f"{inv.leistung_kwp:.1f} kWh"])
                elif inv.typ == "wechselrichter":
                    tech_daten.append(["AC-Leistung:", f"{inv.leistung_kwp:.1f} kW"])
                else:
                    tech_daten.append(["Leistung:", f"{inv.leistung_kwp:.1f} kWp"])

            if inv.ausrichtung:
                tech_daten.append(["Ausrichtung:", inv.ausrichtung])
            if inv.neigung_grad is not None:
                tech_daten.append(["Neigung:", f"{inv.neigung_grad:.0f}°"])
            if inv.parent_bezeichnung:
                tech_daten.append(["Wechselrichter:", inv.parent_bezeichnung])

            tech_daten.append(["Anschaffung:", self._safe_str(inv.anschaffungsdatum)])
            if inv.anschaffungskosten:
                tech_daten.append(["Kosten:", f"{self._format_euro(inv.anschaffungskosten)} EUR"])
                gesamt_kosten += inv.anschaffungskosten
            if inv.alternativkosten:
                tech_daten.append(["Alternativkosten:", f"{self._format_euro(inv.alternativkosten)} EUR"])
                mehrkosten = (inv.anschaffungskosten or 0) - inv.alternativkosten
                tech_daten.append(["Mehrkosten:", f"{self._format_euro(mehrkosten)} EUR"])
                gesamt_mehrkosten += mehrkosten
            else:
                gesamt_mehrkosten += inv.anschaffungskosten or 0

            if tech_daten:
                elements.append(self._create_key_value_table(tech_daten))

            # Stammdaten (Geraetedaten)
            stamm_daten = []
            if inv.stamm_hersteller:
                stamm_daten.append(["Hersteller:", inv.stamm_hersteller])
            if inv.stamm_modell:
                stamm_daten.append(["Modell:", inv.stamm_modell])
            if inv.stamm_seriennummer:
                stamm_daten.append(["Seriennummer:", inv.stamm_seriennummer])
            if inv.stamm_garantie_bis:
                stamm_daten.append(["Garantie bis:", inv.stamm_garantie_bis])
            if inv.stamm_mastr_id:
                stamm_daten.append(["MaStR-ID:", inv.stamm_mastr_id])

            if stamm_daten:
                elements.append(Paragraph("<i>Geraetedaten:</i>", self.styles['EEDCBody']))
                elements.append(self._create_key_value_table(stamm_daten))

            # Ansprechpartner
            if inv.ansprechpartner_firma or inv.ansprechpartner_name:
                elements.append(Paragraph("<i>Ansprechpartner:</i>", self.styles['EEDCBody']))
                ap_daten = []
                if inv.ansprechpartner_firma:
                    ap_daten.append(["Firma:", inv.ansprechpartner_firma])
                if inv.ansprechpartner_name:
                    ap_daten.append(["Kontakt:", inv.ansprechpartner_name])
                if inv.ansprechpartner_telefon:
                    ap_daten.append(["Telefon:", inv.ansprechpartner_telefon])
                if inv.ansprechpartner_email:
                    ap_daten.append(["E-Mail:", inv.ansprechpartner_email])
                if inv.ansprechpartner_kundennummer:
                    ap_daten.append(["Kundennr.:", inv.ansprechpartner_kundennummer])
                elements.append(self._create_key_value_table(ap_daten))

            # Wartung
            if inv.wartung_vertragsnummer or inv.wartung_anbieter:
                elements.append(Paragraph("<i>Wartungsvertrag:</i>", self.styles['EEDCBody']))
                w_daten = []
                if inv.wartung_vertragsnummer:
                    w_daten.append(["Vertragsnr.:", inv.wartung_vertragsnummer])
                if inv.wartung_anbieter:
                    w_daten.append(["Anbieter:", inv.wartung_anbieter])
                if inv.wartung_gueltig_bis:
                    w_daten.append(["Gueltig bis:", inv.wartung_gueltig_bis])
                if inv.wartung_leistungsumfang:
                    w_daten.append(["Leistungen:", inv.wartung_leistungsumfang])
                elements.append(self._create_key_value_table(w_daten))

            elements.append(Spacer(1, 6))

        # Zusammenfassung
        elements.append(Paragraph("<b>Investitions-Zusammenfassung</b>", self.styles['SubsectionHeader']))
        summe = [
            ["Gesamtkosten:", f"{self._format_euro(gesamt_kosten)} EUR"],
            ["ROI-Basis (Mehrkosten):", f"{self._format_euro(gesamt_mehrkosten)} EUR"],
        ]
        elements.append(self._create_key_value_table(summe))

        return elements

    # =========================================================================
    # Teil 3: Jahresuebersicht
    # =========================================================================

    def _build_jahresuebersicht(self, kpis: JahresKPIs, leistung_kwp: float) -> List:
        """Erstellt die Jahresuebersicht mit allen KPIs."""
        elements = []

        elements.append(Paragraph("3. Jahresuebersicht", self.styles['SectionHeader']))

        # 3.1 Energie-Bilanz
        elements.append(Paragraph("3.1 Energie-Bilanz", self.styles['SubsectionHeader']))
        energie = [
            ["PV-Erzeugung:", f"{self._format_kwh(kpis.pv_erzeugung_kwh)} kWh",
             "Autarkie:", self._format_percent(kpis.autarkie_prozent)],
            ["Eigenverbrauch:", f"{self._format_kwh(kpis.eigenverbrauch_kwh)} kWh",
             "EV-Quote:", self._format_percent(kpis.eigenverbrauch_quote_prozent)],
            ["Einspeisung:", f"{self._format_kwh(kpis.einspeisung_kwh)} kWh",
             "Spez. Ertrag:", f"{self._format_kwh(kpis.spezifischer_ertrag_kwh_kwp)} kWh/kWp"],
            ["Netzbezug:", f"{self._format_kwh(kpis.netzbezug_kwh)} kWh",
             "Anlagenleistung:", f"{leistung_kwp:.1f} kWp"],
        ]
        elements.append(self._create_grid_table(energie, col_widths=[3*cm, 3.5*cm, 3*cm, 3.5*cm]))

        # 3.2 Finanzen
        elements.append(Paragraph("3.2 Finanzen", self.styles['SubsectionHeader']))
        finanzen = [
            ["Einspeise-Erloes:", f"{self._format_euro(kpis.einspeise_erloes_euro)} EUR"],
            ["EV-Ersparnis:", f"{self._format_euro(kpis.ev_ersparnis_euro)} EUR"],
        ]
        if kpis.hat_waermepumpe:
            finanzen.append(["WP-Ersparnis:", f"{self._format_euro(kpis.wp_ersparnis_euro)} EUR"])
        if kpis.hat_emobilitaet:
            finanzen.append(["E-Auto-Ersparnis:", f"{self._format_euro(kpis.emob_ersparnis_euro)} EUR"])
        finanzen.append(["Netto-Jahresertrag:", f"{self._format_euro(kpis.netto_ertrag_euro)} EUR"])
        if kpis.jahres_rendite_prozent:
            finanzen.append(["Jahres-Rendite:", f"{kpis.jahres_rendite_prozent:.1f}% p.a."])
        elements.append(self._create_key_value_table(finanzen))

        # 3.3 Speicher (falls vorhanden)
        if kpis.hat_speicher:
            elements.append(Paragraph("3.3 Speicher", self.styles['SubsectionHeader']))
            speicher = [
                ["Kapazitaet:", f"{self._format_kwh(kpis.speicher_kapazitaet_kwh, 1)} kWh"],
                ["Ladung gesamt:", f"{self._format_kwh(kpis.speicher_ladung_kwh)} kWh"],
                ["Entladung gesamt:", f"{self._format_kwh(kpis.speicher_entladung_kwh)} kWh"],
                ["Vollzyklen:", self._format_kwh(kpis.speicher_vollzyklen, 0) if kpis.speicher_vollzyklen else "-"],
                ["Effizienz:", self._format_percent(kpis.speicher_effizienz_prozent)],
            ]
            elements.append(self._create_key_value_table(speicher))

        # 3.4 Waermepumpe (falls vorhanden)
        if kpis.hat_waermepumpe:
            elements.append(Paragraph("3.4 Waermepumpe", self.styles['SubsectionHeader']))
            wp = [
                ["Waerme gesamt:", f"{self._format_kwh(kpis.wp_waerme_kwh)} kWh"],
                ["davon Heizung:", f"{self._format_kwh(kpis.wp_heizung_kwh)} kWh"],
                ["davon Warmwasser:", f"{self._format_kwh(kpis.wp_warmwasser_kwh)} kWh"],
                ["Stromverbrauch:", f"{self._format_kwh(kpis.wp_strom_kwh)} kWh"],
                ["Jahres-COP:", f"{kpis.wp_cop:.1f}" if kpis.wp_cop else "-"],
            ]
            elements.append(self._create_key_value_table(wp))

        # 3.5 E-Mobilitaet (falls vorhanden)
        if kpis.hat_emobilitaet:
            elements.append(Paragraph("3.5 E-Mobilitaet", self.styles['SubsectionHeader']))
            emob = [
                ["Gefahrene km:", f"{self._format_kwh(kpis.emob_km, 0)} km"],
                ["Ladung gesamt:", f"{self._format_kwh(kpis.emob_ladung_kwh)} kWh"],
                ["davon PV:", f"{self._format_kwh(kpis.emob_pv_kwh)} kWh ({self._format_percent(kpis.emob_pv_anteil_prozent)})"],
                ["davon Netz:", f"{self._format_kwh(kpis.emob_netz_kwh)} kWh"],
                ["V2H-Rueckspeisung:", f"{self._format_kwh(kpis.emob_v2h_kwh)} kWh"],
            ]
            elements.append(self._create_key_value_table(emob))

        # 3.6 CO2-Bilanz
        elements.append(Paragraph("3.6 CO2-Bilanz", self.styles['SubsectionHeader']))
        co2 = [
            ["Einsparung PV:", f"{self._format_kwh(kpis.co2_pv_kg, 0)} kg CO2"],
        ]
        if kpis.hat_waermepumpe:
            co2.append(["Einsparung WP:", f"{self._format_kwh(kpis.co2_wp_kg, 0)} kg CO2"])
        if kpis.hat_emobilitaet:
            co2.append(["Einsparung E-Auto:", f"{self._format_kwh(kpis.co2_emob_kg, 0)} kg CO2"])
        co2.append(["GESAMT:", f"{self._format_kwh(kpis.co2_gesamt_kg, 0)} kg CO2"])

        # Aequivalente
        baeume = int(kpis.co2_gesamt_kg / 20) if kpis.co2_gesamt_kg > 0 else 0
        auto_km = int(kpis.co2_gesamt_kg / 0.12) if kpis.co2_gesamt_kg > 0 else 0
        co2.append(["Entspricht:", f"~{baeume} Baeume oder ~{auto_km:,} Auto-km".replace(",", ".")])

        elements.append(self._create_key_value_table(co2))

        return elements

    # =========================================================================
    # Teil 4: Charts
    # =========================================================================

    def _build_charts(self, monats_daten: List[MonatsZeile], kpis: JahresKPIs) -> List:
        """Erstellt die Diagramme."""
        elements = []

        elements.append(Spacer(1, 15))
        elements.append(Paragraph("4. Diagramme", self.styles['SectionHeader']))

        # Chart 1: PV-Erzeugung (Balken + PVGIS Linie)
        elements.append(Paragraph("4.1 Monatliche PV-Erzeugung", self.styles['SubsectionHeader']))
        elements.append(self._create_pv_erzeugung_chart(monats_daten))
        elements.append(Spacer(1, 10))

        # Chart 2: Energie-Fluss (gestapelt)
        elements.append(Paragraph("4.2 Energie-Fluss", self.styles['SubsectionHeader']))
        elements.append(self._create_energie_fluss_chart(monats_daten))
        elements.append(Spacer(1, 10))

        # Chart 3: Autarkie-Verlauf
        elements.append(Paragraph("4.3 Autarkie-Verlauf", self.styles['SubsectionHeader']))
        elements.append(self._create_autarkie_chart(monats_daten))

        return elements

    def _create_pv_erzeugung_chart(self, monats_daten: List[MonatsZeile]) -> Drawing:
        """Erstellt das PV-Erzeugung Balkendiagramm mit PVGIS-Vergleich."""
        drawing = Drawing(480, 200)

        # Daten vorbereiten
        ist_werte = [m.pv_erzeugung_kwh for m in monats_daten]
        prognose_werte = [m.pvgis_prognose_kwh or 0 for m in monats_daten]
        hat_prognose = any(p > 0 for p in prognose_werte)

        # Balkendiagramm
        chart = VerticalBarChart()
        chart.x = 50
        chart.y = 30
        chart.width = 380
        chart.height = 140
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(max(ist_werte), max(prognose_werte)) * 1.1 if ist_werte else 100

        if hat_prognose:
            chart.data = [ist_werte, prognose_werte]
            chart.bars[0].fillColor = self.PRIMARY_COLOR
            chart.bars[1].fillColor = self.LIGHT_BG
            chart.bars[1].strokeColor = self.SECONDARY_COLOR
            chart.bars[1].strokeWidth = 1
        else:
            chart.data = [ist_werte]
            chart.bars[0].fillColor = self.PRIMARY_COLOR

        chart.categoryAxis.categoryNames = self.MONATSNAMEN_KURZ[1:13]
        chart.categoryAxis.labels.fontSize = 8
        chart.valueAxis.labels.fontSize = 8
        chart.barWidth = 8 if hat_prognose else 12
        chart.groupSpacing = 8

        drawing.add(chart)

        # Legende
        legend = Legend()
        legend.x = 60
        legend.y = 185
        legend.alignment = 'right'
        legend.columnMaximum = 1
        legend.fontName = 'Helvetica'
        legend.fontSize = 8

        if hat_prognose:
            legend.colorNamePairs = [
                (self.PRIMARY_COLOR, 'IST-Erzeugung'),
                (self.SECONDARY_COLOR, 'PVGIS-Prognose'),
            ]
        else:
            legend.colorNamePairs = [(self.PRIMARY_COLOR, 'PV-Erzeugung')]

        drawing.add(legend)

        # Y-Achsen-Label
        drawing.add(String(10, 100, 'kWh', fontSize=8, fillColor=self.TEXT_COLOR))

        return drawing

    def _create_energie_fluss_chart(self, monats_daten: List[MonatsZeile]) -> Drawing:
        """Erstellt das gestapelte Energie-Fluss Diagramm."""
        drawing = Drawing(480, 200)

        # Daten
        eigenverbrauch = [m.eigenverbrauch_kwh for m in monats_daten]
        einspeisung = [m.einspeisung_kwh for m in monats_daten]
        netzbezug = [m.netzbezug_kwh for m in monats_daten]

        chart = VerticalBarChart()
        chart.x = 50
        chart.y = 30
        chart.width = 380
        chart.height = 140
        chart.valueAxis.valueMin = 0

        max_val = max(
            max(e + i for e, i in zip(eigenverbrauch, einspeisung)),
            max(netzbezug)
        ) if eigenverbrauch else 100
        chart.valueAxis.valueMax = max_val * 1.1

        chart.data = [eigenverbrauch, einspeisung, netzbezug]
        chart.bars[0].fillColor = self.SECONDARY_COLOR  # Eigenverbrauch - gruen
        chart.bars[1].fillColor = self.WARNING_COLOR    # Einspeisung - gelb
        chart.bars[2].fillColor = self.DANGER_COLOR     # Netzbezug - rot

        chart.categoryAxis.categoryNames = self.MONATSNAMEN_KURZ[1:13]
        chart.categoryAxis.labels.fontSize = 8
        chart.valueAxis.labels.fontSize = 8
        chart.barWidth = 6
        chart.groupSpacing = 6

        drawing.add(chart)

        # Legende
        legend = Legend()
        legend.x = 60
        legend.y = 185
        legend.columnMaximum = 1
        legend.fontName = 'Helvetica'
        legend.fontSize = 8
        legend.colorNamePairs = [
            (self.SECONDARY_COLOR, 'Eigenverbrauch'),
            (self.WARNING_COLOR, 'Einspeisung'),
            (self.DANGER_COLOR, 'Netzbezug'),
        ]
        drawing.add(legend)

        drawing.add(String(10, 100, 'kWh', fontSize=8, fillColor=self.TEXT_COLOR))

        return drawing

    def _create_autarkie_chart(self, monats_daten: List[MonatsZeile]) -> Drawing:
        """Erstellt das Autarkie-Liniendiagramm."""
        drawing = Drawing(480, 180)

        autarkie = [m.autarkie_prozent for m in monats_daten]

        chart = HorizontalLineChart()
        chart.x = 50
        chart.y = 30
        chart.width = 380
        chart.height = 120
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = 100
        chart.data = [autarkie]

        chart.categoryAxis.categoryNames = self.MONATSNAMEN_KURZ[1:13]
        chart.categoryAxis.labels.fontSize = 8
        chart.valueAxis.labels.fontSize = 8

        chart.lines[0].strokeColor = self.PRIMARY_COLOR
        chart.lines[0].strokeWidth = 2
        chart.lines[0].symbol = makeMarker('FilledCircle')
        chart.lines[0].symbol.fillColor = self.PRIMARY_COLOR
        chart.lines[0].symbol.size = 4

        drawing.add(chart)

        # Durchschnittslinie
        avg = sum(autarkie) / len(autarkie) if autarkie else 0
        y_pos = 30 + (avg / 100) * 120
        drawing.add(Line(50, y_pos, 430, y_pos,
                        strokeColor=self.SECONDARY_COLOR,
                        strokeWidth=1,
                        strokeDashArray=[4, 2]))
        drawing.add(String(435, y_pos - 3, f'{avg:.0f}%',
                          fontSize=8, fillColor=self.SECONDARY_COLOR))

        drawing.add(String(10, 90, '%', fontSize=8, fillColor=self.TEXT_COLOR))

        return drawing

    # =========================================================================
    # Teil 5: Monatsuebersicht
    # =========================================================================

    def _build_monatsuebersicht(self, monats_daten: List[MonatsZeile], kpis: JahresKPIs) -> List:
        """Erstellt die erweiterten Monatstabellen."""
        elements = []

        elements.append(Paragraph("5. Monatsuebersicht", self.styles['SectionHeader']))

        # 5.1 Energie-Tabelle
        elements.append(Paragraph("5.1 Energie", self.styles['SubsectionHeader']))
        elements.append(self._create_energie_monatstabelle(monats_daten))

        # 5.2 Speicher-Tabelle (falls vorhanden)
        if kpis.hat_speicher:
            elements.append(Paragraph("5.2 Speicher", self.styles['SubsectionHeader']))
            elements.append(self._create_speicher_monatstabelle(monats_daten))

        # 5.3 Waermepumpe-Tabelle (falls vorhanden)
        if kpis.hat_waermepumpe:
            elements.append(Paragraph("5.3 Waermepumpe", self.styles['SubsectionHeader']))
            elements.append(self._create_wp_monatstabelle(monats_daten))

        # 5.4 E-Mobilitaet-Tabelle (falls vorhanden)
        if kpis.hat_emobilitaet:
            elements.append(Paragraph("5.4 E-Mobilitaet", self.styles['SubsectionHeader']))
            elements.append(self._create_emob_monatstabelle(monats_daten))

        # 5.5 Finanzen-Tabelle
        elements.append(Paragraph("5.5 Finanzen", self.styles['SubsectionHeader']))
        elements.append(self._create_finanzen_monatstabelle(monats_daten, kpis))

        return elements

    def _create_energie_monatstabelle(self, monats_daten: List[MonatsZeile]) -> Table:
        """Erstellt die Energie-Monatstabelle."""
        header = ["Monat", "PV kWh", "EV kWh", "Einsp.", "Netz", "Autarkie", "Spez."]
        data = [header]

        totals = [0, 0, 0, 0]
        for m in monats_daten:
            data.append([
                self.MONATSNAMEN_KURZ[m.monat],
                self._format_kwh(m.pv_erzeugung_kwh),
                self._format_kwh(m.eigenverbrauch_kwh),
                self._format_kwh(m.einspeisung_kwh),
                self._format_kwh(m.netzbezug_kwh),
                self._format_percent(m.autarkie_prozent, 0),
                f"{m.spezifischer_ertrag:.0f}",
            ])
            totals[0] += m.pv_erzeugung_kwh
            totals[1] += m.eigenverbrauch_kwh
            totals[2] += m.einspeisung_kwh
            totals[3] += m.netzbezug_kwh

        # Summenzeile
        avg_autarkie = sum(m.autarkie_prozent for m in monats_daten) / len(monats_daten) if monats_daten else 0
        avg_spez = sum(m.spezifischer_ertrag for m in monats_daten) if monats_daten else 0
        data.append([
            "SUMME",
            self._format_kwh(totals[0]),
            self._format_kwh(totals[1]),
            self._format_kwh(totals[2]),
            self._format_kwh(totals[3]),
            self._format_percent(avg_autarkie, 0),
            f"{avg_spez:.0f}",
        ])

        return self._create_data_table(data)

    def _create_speicher_monatstabelle(self, monats_daten: List[MonatsZeile]) -> Table:
        """Erstellt die Speicher-Monatstabelle."""
        header = ["Monat", "Ladung", "Entlad.", "Effiz.", "Zyklen"]
        data = [header]

        total_ladung = 0
        total_entladung = 0
        total_zyklen = 0

        for m in monats_daten:
            data.append([
                self.MONATSNAMEN_KURZ[m.monat],
                self._format_kwh(m.speicher_ladung_kwh),
                self._format_kwh(m.speicher_entladung_kwh),
                self._format_percent(m.speicher_effizienz_prozent, 0),
                f"{m.speicher_vollzyklen:.1f}",
            ])
            total_ladung += m.speicher_ladung_kwh
            total_entladung += m.speicher_entladung_kwh
            total_zyklen += m.speicher_vollzyklen

        avg_eff = (total_entladung / total_ladung * 100) if total_ladung > 0 else 0
        data.append([
            "SUMME",
            self._format_kwh(total_ladung),
            self._format_kwh(total_entladung),
            self._format_percent(avg_eff, 0),
            f"{total_zyklen:.1f}",
        ])

        return self._create_data_table(data)

    def _create_wp_monatstabelle(self, monats_daten: List[MonatsZeile]) -> Table:
        """Erstellt die Waermepumpe-Monatstabelle."""
        header = ["Monat", "Waerme", "Heiz.", "WW", "Strom", "COP"]
        data = [header]

        totals = [0, 0, 0, 0]
        for m in monats_daten:
            data.append([
                self.MONATSNAMEN_KURZ[m.monat],
                self._format_kwh(m.wp_waerme_kwh),
                self._format_kwh(m.wp_heizung_kwh),
                self._format_kwh(m.wp_warmwasser_kwh),
                self._format_kwh(m.wp_strom_kwh),
                f"{m.wp_cop:.1f}" if m.wp_cop else "-",
            ])
            totals[0] += m.wp_waerme_kwh
            totals[1] += m.wp_heizung_kwh
            totals[2] += m.wp_warmwasser_kwh
            totals[3] += m.wp_strom_kwh

        avg_cop = totals[0] / totals[3] if totals[3] > 0 else 0
        data.append([
            "SUMME",
            self._format_kwh(totals[0]),
            self._format_kwh(totals[1]),
            self._format_kwh(totals[2]),
            self._format_kwh(totals[3]),
            f"{avg_cop:.1f}",
        ])

        return self._create_data_table(data)

    def _create_emob_monatstabelle(self, monats_daten: List[MonatsZeile]) -> Table:
        """Erstellt die E-Mobilitaet-Monatstabelle."""
        header = ["Monat", "km", "Ladung", "PV", "Netz", "V2H", "PV%"]
        data = [header]

        totals = [0, 0, 0, 0, 0]
        for m in monats_daten:
            data.append([
                self.MONATSNAMEN_KURZ[m.monat],
                f"{m.emob_km:.0f}",
                self._format_kwh(m.emob_ladung_kwh),
                self._format_kwh(m.emob_pv_kwh),
                self._format_kwh(m.emob_netz_kwh),
                self._format_kwh(m.emob_v2h_kwh),
                self._format_percent(m.emob_pv_anteil_prozent, 0),
            ])
            totals[0] += m.emob_km
            totals[1] += m.emob_ladung_kwh
            totals[2] += m.emob_pv_kwh
            totals[3] += m.emob_netz_kwh
            totals[4] += m.emob_v2h_kwh

        avg_pv = (totals[2] / totals[1] * 100) if totals[1] > 0 else 0
        data.append([
            "SUMME",
            f"{totals[0]:.0f}",
            self._format_kwh(totals[1]),
            self._format_kwh(totals[2]),
            self._format_kwh(totals[3]),
            self._format_kwh(totals[4]),
            self._format_percent(avg_pv, 0),
        ])

        return self._create_data_table(data)

    def _create_finanzen_monatstabelle(self, monats_daten: List[MonatsZeile], kpis: JahresKPIs) -> Table:
        """Erstellt die Finanzen-Monatstabelle."""
        header = ["Monat", "Einsp.", "EV-Ersp."]
        if kpis.hat_waermepumpe:
            header.append("WP")
        if kpis.hat_emobilitaet:
            header.append("E-Auto")
        header.append("Netto")

        data = [header]

        totals = {"einsp": 0, "ev": 0, "wp": 0, "emob": 0, "netto": 0}
        for m in monats_daten:
            row = [
                self.MONATSNAMEN_KURZ[m.monat],
                self._format_euro(m.einsp_erloes_euro),
                self._format_euro(m.ev_ersparnis_euro),
            ]
            if kpis.hat_waermepumpe:
                row.append(self._format_euro(m.wp_ersparnis_euro))
            if kpis.hat_emobilitaet:
                row.append(self._format_euro(m.emob_ersparnis_euro))
            row.append(self._format_euro(m.netto_ertrag_euro))
            data.append(row)

            totals["einsp"] += m.einsp_erloes_euro
            totals["ev"] += m.ev_ersparnis_euro
            totals["wp"] += m.wp_ersparnis_euro
            totals["emob"] += m.emob_ersparnis_euro
            totals["netto"] += m.netto_ertrag_euro

        # Summenzeile
        summe_row = [
            "SUMME",
            self._format_euro(totals["einsp"]),
            self._format_euro(totals["ev"]),
        ]
        if kpis.hat_waermepumpe:
            summe_row.append(self._format_euro(totals["wp"]))
        if kpis.hat_emobilitaet:
            summe_row.append(self._format_euro(totals["emob"]))
        summe_row.append(self._format_euro(totals["netto"]))
        data.append(summe_row)

        return self._create_data_table(data)

    # =========================================================================
    # Teil 6: Finanz-Prognose
    # =========================================================================

    def _build_finanz_prognose(self, fp: FinanzPrognose) -> List:
        """Erstellt die Finanz-Prognose Sektion."""
        elements = []

        elements.append(Paragraph("6. Finanz-Prognose & Amortisation", self.styles['SectionHeader']))

        prognose = [
            ["Investition (Mehrkosten):", f"{self._format_euro(fp.investition_mehrkosten_euro)} EUR"],
            ["Bisherige Ertraege:", f"{self._format_euro(fp.bisherige_ertraege_euro)} EUR"],
            ["Amortisations-Fortschritt:", f"{fp.amortisations_fortschritt_prozent:.1f}%"],
        ]
        if fp.amortisation_erreicht:
            prognose.append(["Status:", "Amortisation erreicht!"])
        elif fp.amortisation_prognose_jahr:
            prognose.append(["Prognose Amortisation:", f"{fp.amortisation_prognose_jahr}"])
            if fp.restlaufzeit_monate:
                prognose.append(["Restlaufzeit:", f"~{fp.restlaufzeit_monate} Monate"])

        prognose.append(["Erwarteter Jahresertrag:", f"~{self._format_euro(fp.jahres_ertrag_prognose_euro)} EUR"])
        if fp.jahres_rendite_prognose_prozent:
            prognose.append(["Erwartete Rendite:", f"~{fp.jahres_rendite_prognose_prozent:.1f}% p.a."])

        elements.append(self._create_key_value_table(prognose))

        # Fortschrittsbalken als Text
        filled = int(fp.amortisations_fortschritt_prozent / 2.5)  # 40 Zeichen = 100%
        bar = "█" * filled + "░" * (40 - filled)
        elements.append(Paragraph(
            f"<font face='Courier'>[{bar}] {fp.amortisations_fortschritt_prozent:.1f}%</font>",
            self.styles['EEDCBody']
        ))

        return elements

    # =========================================================================
    # Teil 7: String-Vergleich
    # =========================================================================

    def _build_string_vergleich(self, strings: List[StringVergleich]) -> List:
        """Erstellt den PV-String SOLL-IST Vergleich."""
        elements = []

        elements.append(Paragraph("7. PV-String Vergleich (SOLL vs. IST)", self.styles['SectionHeader']))

        if not strings:
            elements.append(Paragraph("Keine PV-Strings mit Prognose vorhanden.", self.styles['EEDCBody']))
            return elements

        # Gesamtsummen
        total_prognose = sum(s.prognose_kwh for s in strings)
        total_ist = sum(s.ist_kwh for s in strings)
        total_abw = total_ist - total_prognose
        total_abw_pct = (total_abw / total_prognose * 100) if total_prognose > 0 else 0

        summe = [
            ["PVGIS-Prognose gesamt:", f"{self._format_kwh(total_prognose)} kWh"],
            ["IST-Erzeugung gesamt:", f"{self._format_kwh(total_ist)} kWh"],
            ["Abweichung:", f"{self._format_kwh(total_abw)} kWh ({total_abw_pct:+.1f}%)"],
        ]
        elements.append(self._create_key_value_table(summe))
        elements.append(Spacer(1, 10))

        # Einzelne Strings
        for s in strings:
            info = f"{s.bezeichnung} ({s.leistung_kwp:.1f} kWp"
            if s.ausrichtung:
                info += f", {s.ausrichtung}"
            if s.neigung_grad:
                info += f" {s.neigung_grad:.0f}°"
            info += ")"
            elements.append(Paragraph(f"<b>{info}</b>", self.styles['EEDCBody']))

            abw_text = f"{s.abweichung_kwh:+.0f} kWh ({s.abweichung_prozent:+.1f}%)"
            string_daten = [
                ["PVGIS:", f"{self._format_kwh(s.prognose_kwh)} kWh",
                 "IST:", f"{self._format_kwh(s.ist_kwh)} kWh",
                 "Abw.:", abw_text],
            ]
            elements.append(self._create_grid_table(string_daten, col_widths=[1.5*cm, 2.5*cm, 1*cm, 2.5*cm, 1*cm, 3.5*cm]))
            elements.append(Spacer(1, 4))

        return elements

    # =========================================================================
    # Footer
    # =========================================================================

    def _build_footer(self) -> List:
        """Erstellt den Footer."""
        elements = []

        elements.append(Spacer(1, 20))
        elements.append(HRFlowable(width="100%", thickness=1, color=self.LIGHT_TEXT))
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(
            f"Generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')} "
            f"mit EEDC v{APP_VERSION}",
            self.styles['Footer']
        ))
        elements.append(Paragraph(
            "https://github.com/supernova1963/eedc-homeassistant",
            self.styles['Footer']
        ))

        return elements

    # =========================================================================
    # Hilfsmethoden fuer Tabellen
    # =========================================================================

    def _create_key_value_table(self, data: List[List[str]]) -> Table:
        """Erstellt eine Key-Value Tabelle."""
        table = Table(data, colWidths=[4.5*cm, 13*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.TEXT_COLOR),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
        ]))
        return table

    def _create_grid_table(self, data: List[List[str]], col_widths: List) -> Table:
        """Erstellt eine mehrspaltige Grid-Tabelle."""
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.TEXT_COLOR),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return table

    def _create_data_table(self, data: List[List[str]], repeat_header: bool = True) -> Table:
        """Erstellt eine Daten-Tabelle mit Header und Summenzeile.

        Args:
            data: Tabellendaten mit Header in Zeile 0
            repeat_header: Kopfzeile bei Seitenumbruch wiederholen (default: True)
        """
        num_cols = len(data[0]) if data else 0
        col_width = 17*cm / num_cols if num_cols > 0 else 2*cm
        col_widths = [col_width] * num_cols

        # repeatRows=1 wiederholt die erste Zeile (Header) bei Seitenumbruch
        table = Table(data, colWidths=col_widths, repeatRows=1 if repeat_header else 0)
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), self.PRIMARY_COLOR),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            # Summenzeile
            ('BACKGROUND', (0, -1), (-1, -1), self.LIGHT_BG),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            # Content
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, self.LIGHT_TEXT),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        return table
