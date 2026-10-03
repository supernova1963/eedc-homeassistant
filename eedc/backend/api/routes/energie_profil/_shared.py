"""
Energie-Profil Routes — gemeinsame Helper, Konstanten, Pydantic-Models.

Wird von views.py (Read-Endpoints) und repair.py (Repair-Endpoints) genutzt.
"""

import logging
import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from backend.services.waerme_klima_block import (
    WpGeraetZeile,
    WpMoeglichZeile,
)

from backend.core.field_definitions import SONSTIGES_KATEGORIE_UNGEPFLEGT
from backend.models.investition import Investition

logger = logging.getLogger(__name__)


# seite je Investitionstyp
_TYP_SEITE: dict[str, str] = {
    "pv-module":       "quelle",
    "balkonkraftwerk": "quelle",
    "wechselrichter":  "quelle",
    "speicher":        "bidirektional",
    "e-auto":          "bidirektional",
    "wallbox":         "senke",
    "waermepumpe":     "senke",
}

# Virtuelle Serien (kein Investment dahinter)
# `netz` = Alt-Konvention (kombinierter, vorzeichenbehafteter Live-Σ-Key).
# `netzbezug`/`einspeisung` = Neu-Konvention seit Phase B / v3.34.2 (positiver
# Split aus dem Boundary-Pfad, komponenten_beitraege). Alle drei Kategorie
# "netz" → werden in der Energieprofil-Auswertung gleich (BIDI) behandelt; ohne
# die beiden Split-Keys fielen Neu-Tage in Geräteliste/Diagnose-Serien still
# durch `_key_to_serie_info → None` (Achse-3-Konsument-Robustheit, #316).
_VIRTUAL_SERIEN: dict[str, dict] = {
    "haushalt":    {"label": "Restverbrauch", "typ": "virtual", "kategorie": "haushalt", "seite": "senke"},
    "netz":        {"label": "Stromnetz",   "typ": "virtual", "kategorie": "netz",     "seite": "bidirektional"},
    "netzbezug":   {"label": "Netzbezug",   "typ": "virtual", "kategorie": "netz",     "seite": "bidirektional"},
    "einspeisung": {"label": "Einspeisung", "typ": "virtual", "kategorie": "netz",     "seite": "bidirektional"},
    "pv_gesamt":   {"label": "PV Gesamt",   "typ": "virtual", "kategorie": "pv",       "seite": "quelle"},
}

# Optionale Suffixe bei WP-Serien (waermepumpe_{id}_heizen).
# ⚠ Die Menge ist der **Rückweg** zu `live_sensor_config.baue_investitions_serien`
# — wer dort ein Suffix ergänzt und hier nicht, bekommt im Tag-Stundenverlauf
# zwei Flächen mit demselben blanken Gerätenamen (Wächter:
# `test_serien_aufbau_symmetrie_m1.py::test_split_keys_loesen_zurueck_*`).
_SUFFIX_LABELS = {"heizen": " Heizen", "warmwasser": " Warmwasser", "kuehlen": " Kühlen"}

# Kategorien die bereits in dedizierten Spalten landen (kein Extra-Tracking nötig)
_DEDIZIERTE_KATEGORIEN = {"pv", "batterie", "netz", "haushalt", "waermepumpe", "wallbox", "eauto"}


def _key_to_serie_info(
    key: str, inv_map: dict[int, "Investition"]
) -> Optional[dict]:
    """Löst einen Komponenten-Key zu Label + Typ auf."""
    if key in _VIRTUAL_SERIEN:
        return {"key": key, **_VIRTUAL_SERIEN[key]}

    m = re.match(r'^([a-z]+)_(\d+)(?:_([a-z]+))?$', key)
    if not m:
        return None

    inv_id = int(m.group(2))
    suffix = m.group(3)
    inv = inv_map.get(inv_id)
    if not inv:
        return None

    label = inv.bezeichnung
    if suffix and suffix in _SUFFIX_LABELS:
        label += _SUFFIX_LABELS[suffix]

    # seite bestimmen
    seite = _TYP_SEITE.get(inv.typ, "senke")
    if inv.typ == "sonstiges" and isinstance(inv.parameter, dict):
        kat = inv.parameter.get("kategorie", SONSTIGES_KATEGORIE_UNGEPFLEGT)
        if kat == "erzeuger":
            seite = "quelle"
        elif kat == "speicher":
            seite = "bidirektional"
        elif kat == "abgabe":
            # §9.2: Energie verlässt das Haus — eigene Seite, damit der Tag sie
            # weder als Verbrauch noch als Erzeugung liest.
            seite = "abgabe"

    return {
        "key": key,
        "label": label,
        "typ": inv.typ,
        "kategorie": m.group(1),
        "seite": seite,
    }


def detail_kategorie(info: dict, inv: Optional["Investition"]) -> str:
    """Feinere Anzeige-Kategorie eines Komponenten-Keys (Monats-Auswertung).

    Aus views.py extrahiert (ADR-001 testbar). Netz-Erkennung läuft über die
    `kategorie` (nicht den Roh-Key), damit BEIDE Netz-Konventionen — Alt-`netz`
    und Neu-Split `netzbezug`/`einspeisung` — auf dieselbe Detail-Kategorie
    `netz` fallen (Achse-3-Konsument-Robustheit, #316). Sonst landete ein
    Neu-Split-Key über die Fallthrough-Logik fälschlich in
    `sonstige_verbraucher`.
    """
    kat = info.get("kategorie", "sonstige")
    typ = info.get("typ", "")
    if kat == "netz":
        return "netz"
    if typ == "pv-module":
        return "pv_module"
    if typ == "balkonkraftwerk":
        return "bkw"
    if typ == "speicher":
        return "speicher"
    if typ == "waermepumpe":
        return "waermepumpe"
    if typ in ("wallbox", "e-auto"):
        return "wallbox_eauto"
    if kat == "haushalt":
        return "haushalt"
    if typ == "sonstiges" and inv and isinstance(inv.parameter, dict):
        unterkat = inv.parameter.get("kategorie", SONSTIGES_KATEGORIE_UNGEPFLEGT)
        if unterkat == "erzeuger":
            return "sonstige_erzeuger"
        if unterkat == "speicher":
            return "speicher"
        if unterkat == "abgabe":
            return "sonstige_abgabe"
        return "sonstige_verbraucher"
    if kat == "pv":
        return "pv_module"
    return "sonstige_verbraucher"


# ── Response Models ──────────────────────────────────────────────────────────

class SerieInfo(BaseModel):
    """Metadaten einer Komponenten-Serie (für Label-Auflösung im Frontend)."""
    key: str
    label: str
    typ: str        # z.B. "sonstiges", "pv-module", "virtual"
    kategorie: str  # z.B. "sonstige", "pv", "netz"
    seite: str      # "quelle" | "senke" | "bidirektional"


class StundenWertResponse(BaseModel):
    """Stündlicher Energiewert eines Tages."""
    stunde: int
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    batterie_kw: Optional[float] = None
    waermepumpe_kw: Optional[float] = None
    wallbox_kw: Optional[float] = None
    ueberschuss_kw: Optional[float] = None
    defizit_kw: Optional[float] = None
    temperatur_c: Optional[float] = None
    globalstrahlung_wm2: Optional[float] = None
    soc_prozent: Optional[float] = None
    komponenten: Optional[dict] = None  # Rohwerte aller Serien (key → kW)
    # WP-Kompressor-Starts in dieser Stunde, summiert über alle WPs (Issue #136).
    # Pro-Investitions-Aufschlüsselung lebt auf Tagesebene in TagesZusammenfassung.komponenten_starts.
    wp_starts_anzahl: Optional[int] = None
    # WP-Betriebsstunden in dieser Stunde, summiert über alle WPs (Issue #238).
    wp_betriebsstunden: Optional[float] = None
    # Zählerlücken wie HA (R2): ``{achse: n}`` nur für Achsen, deren Menge in
    # dieser Zeile ``n > 1`` reale Stunden trägt (HA hatte die Stunden davor
    # nicht geschrieben; die Energie steht hier wie im HA-Dashboard). ``None``
    # im Regelfall. Die Stundentabelle beschriftet die Zeile damit
    # („enthält n Stunden"), statt sie als Spitze zu zeigen.
    spannen: Optional[dict[str, int]] = None


class StundenAntwort(BaseModel):
    """Tagesdetail-Antwort: Stundenwerte + aufgelöste Serie-Labels."""
    stunden: list[StundenWertResponse]
    serien: list[SerieInfo]  # alle in komponenten vorkommenden Serien mit Label
    # N-553: der **jüngste gemessene** Ladestand des Tages, ungepaart.
    #
    # ⚠ Das ist bewusst **nicht** `stunden[-1].soc_prozent`. Dort steht seit
    # N-553 der Ladestand, der zur Backward-Stunde der Zeile gehört (also aus
    # ihrer Vorzeile) — richtig für „welcher Stand gehört zu dieser Stunde",
    # falsch für „wie voll ist der Speicher zuletzt gewesen". Die letzte
    # gemessene Stunde des Tages trägt ihr Mittel über `[s, s+1)`; dieses
    # Intervall liegt im Backward-Raster schon im Folgetag und fällt aus der
    # Liste. `None` heißt „an diesem Tag wurde kein Ladestand gemessen".
    soc_zuletzt_prozent: Optional[float] = None


class WochenmusterPunkt(BaseModel):
    """Durchschnittlicher Stundenwert pro Wochentag."""
    wochentag: int      # 0=Mo, 1=Di, …, 6=So
    stunde: int         # 0–23
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    batterie_kw: Optional[float] = None
    anzahl_tage: int = 0


class HeatmapZelle(BaseModel):
    """Eine Zelle der Monats-Heatmap (Tag × Stunde)."""
    tag: int          # 1..31
    stunde: int       # 0..23
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    ueberschuss_kw: Optional[float] = None  # pv − verbrauch


class PeakStunde(BaseModel):
    """Eine einzelne Peak-Stunde im Monat."""
    datum: date
    stunde: int
    wert_kw: float


class TagesprofilStunde(BaseModel):
    """Ein Stundenpunkt im typischen Tagesprofil (Ø über Monat)."""
    stunde: int
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None


class KomponentenEintrag(BaseModel):
    """Ein einzelnes Gerät mit Monatssumme."""
    key: str
    label: str
    kategorie: str       # "pv", "waermepumpe", "wallbox", "eauto", "sonstiges", …
    typ: str             # z.B. "pv-module", "balkonkraftwerk", "waermepumpe", "sonstiges"
    seite: str           # "quelle" | "senke" | "bidirektional"
    kwh: float           # positiv = Erzeugung, negativ = Verbrauch
    anteil_prozent: Optional[float] = None  # vom Gesamt-PV bzw. Gesamt-Verbrauch


class KategorieSumme(BaseModel):
    """Monatssumme pro Kategorie (für KPI-Strip)."""
    kategorie: str       # "pv_module", "bkw", "sonstige_erzeuger", "waermepumpe", "wallbox_eauto", "sonstige_verbraucher", "haushalt"
    kwh: float
    anteil_prozent: Optional[float] = None


class MonatsAuswertungResponse(BaseModel):
    """Monatsauswertung aus TagesEnergieProfil + TagesZusammenfassung."""
    jahr: int
    monat: int
    tage_im_monat: int
    tage_mit_daten: int

    # Energie-Summen (kWh)
    pv_kwh: float
    verbrauch_kwh: float
    einspeisung_kwh: float
    netzbezug_kwh: float
    ueberschuss_kwh: float
    defizit_kwh: float

    # Kennzahlen
    autarkie_prozent: Optional[float] = None
    eigenverbrauch_prozent: Optional[float] = None
    performance_ratio_avg: Optional[float] = None
    #: Anzahl der Tage, über die `performance_ratio_avg` gemittelt ist (A6: ein Ø
    #: ohne genannte Grundgesamtheit ist keine Auskunft). ⛔ NICHT `tage_mit_daten`
    #: — das sind die Tage mit irgendwelchen Daten; hier zählen nur die Tage mit
    #: einer Performance Ratio, also mit Einstrahlungsdaten.
    performance_ratio_tage: Optional[int] = None
    batterie_vollzyklen_summe: Optional[float] = None

    # Erweiterte Analyse-KPIs
    grundbedarf_kw: Optional[float] = None          # Ø Verbrauch Nachtstunden 0–5 Uhr
    batterie_ladung_kwh: Optional[float] = None      # Σ Energie in die Batterie
    batterie_entladung_kwh: Optional[float] = None   # Σ Energie aus der Batterie
    batterie_wirkungsgrad: Optional[float] = None    # Entladung / Ladung
    direkt_eigenverbrauch_kwh: Optional[float] = None  # Σ min(pv, verbrauch) je Stunde
    pv_tag_best_kwh: Optional[float] = None
    pv_tag_schnitt_kwh: Optional[float] = None
    pv_tag_schlecht_kwh: Optional[float] = None

    # Typisches Tagesprofil (24 Punkte, Ø über Monat)
    typisches_tagesprofil: list[TagesprofilStunde] = []

    # Per-Komponente Aggregation
    kategorien: list[KategorieSumme] = []
    komponenten: list[KomponentenEintrag] = []

    # Peaks (Top-N Stunden)
    peak_netzbezug: list[PeakStunde] = []
    peak_einspeisung: list[PeakStunde] = []
    peak_pv: Optional[PeakStunde] = None

    # Heatmap-Matrix
    heatmap: list[HeatmapZelle] = []

    # Börsenpreis / Negativpreis (§51 EEG)
    boersenpreis_avg_cent: Optional[float] = None
    negative_preis_stunden: Optional[int] = None
    einspeisung_neg_preis_kwh: Optional[float] = None

    # Datenqualität (Issue #135): Anteil der Stunden ohne gemappten Zähler
    # Ermöglicht dem Frontend, Warnhinweise zu Datenlücken anzuzeigen.
    stunden_fehlend_pv: int = 0
    stunden_fehlend_verbrauch: int = 0


class TagesZusammenfassungResponse(BaseModel):
    """Tageszusammenfassung mit Per-Komponenten-kWh."""
    datum: date
    ueberschuss_kwh: Optional[float] = None
    defizit_kwh: Optional[float] = None
    peak_pv_kw: Optional[float] = None
    peak_netzbezug_kw: Optional[float] = None
    peak_einspeisung_kw: Optional[float] = None
    batterie_vollzyklen: Optional[float] = None
    temperatur_min_c: Optional[float] = None
    temperatur_max_c: Optional[float] = None
    strahlung_summe_wh_m2: Optional[float] = None
    # N-384: der NENNER der Performance Ratio (Modulebene, kWp-gewichtet). Ohne ihn
    # war die Kennzahl nicht nachrechenbar — angezeigt wurde `strahlung_summe_wh_m2`,
    # also die HORIZONTALE Strahlung, die nicht in ihrer Formel steht. `None` bei
    # Bestandszeilen von vor der Spalte: „nicht erhoben", keine 0.
    gti_summe_wh_m2: Optional[float] = None
    performance_ratio: Optional[float] = None
    stunden_verfuegbar: int = 0
    datenquelle: Optional[str] = None
    komponenten_kwh: Optional[dict] = None
    # Per-Komponenten Counter-Werte pro Tag (z.B. WP-Kompressor-Starts, Issue #136)
    # Form: {"wp_starts_anzahl": {"<inv_id>": <int>}}
    komponenten_starts: Optional[dict] = None
    # Börsenpreis-Aggregation (§51 EEG)
    boersenpreis_avg_cent: Optional[float] = None
    boersenpreis_min_cent: Optional[float] = None
    negative_preis_stunden: Optional[int] = None
    einspeisung_neg_preis_kwh: Optional[float] = None


class WaermeVerlaufTagResponse(BaseModel):
    """Eine Tageszeile des Wärme/Klima-Verlaufs (Konzept §8, Bauschnitt 4).

    **Warum ein eigenes Schema und nicht ``TagWerteResponse``.** Die Feldnamen
    sind hier bewusst **deckungsgleich mit der Jahres-Reihe** — der Client baut
    beide über dieselbe reine Funktion (``v4/waermeVerlauf.ts``), Jahr liefert
    Monate, Monat liefert Tage. ``TagWerteResponse`` dagegen ist an die
    Frontend-**Registry** gekoppelt (`lib/werte`), und ihr ``wp_strom`` ist die
    Σ der Stundenspalte ``waermepumpe_kw``. ⚠ Hier stand bis 11.09.2026
    „Leistungspfad" — falsch: die Spalte kommt aus dem **Zählerpfad** im
    Rückwärts-Raster (LTS bzw. Snapshot-Slots). Der Unterschied zu
    ``komponenten_kwh`` ist das Fenster, nicht die Quelle (N-434). Der Verlauf
    nimmt ``komponenten_kwh``, weil die Aufteilung darunter damit rechnet
    (W-17b).

    ⚠ **Kein ``wp_waerme_abgeleitet_kwh``.** Auf Tagesebene gibt es keine
    abgeleitete Wärme: Sie entsteht aus ``Strom × Arbeitszahl`` an den
    Monatszeilen. Was hier steht, ist gemessen — oder es fehlt.
    """

    datum: date
    #: Der gesamte Wärmepumpen-Strom des Tages (Zählerpfad).
    wp_strom_kwh: Optional[float] = None
    #: Σ der **gemessenen** Wärme (Heizung + Warmwasser). ``None`` = keine
    #: Aussage; der Verlauf lässt die Linie dort aussetzen, statt sie auf 0 zu
    #: ziehen.
    wp_waerme_kwh: Optional[float] = None
    #: Σ der **gemessenen Kälte** des Tages (Bauschnitt 6b) — eine eigene Rolle,
    #: nie in ``wp_waerme_kwh`` (Konzept §8). ``None`` = keine Aussage.
    wp_kaelte_kwh: Optional[float] = None
    #: Tagesmittel der Außentemperatur (°C) — zweite Achse.
    temperatur_c: Optional[float] = None
    # ── Der Betriebsart-Stapel; ``None``, wo der Tag keine Aufteilung trägt ──
    wp_modus_strom_heizen_kwh: Optional[float] = None
    wp_modus_strom_warmwasser_kwh: Optional[float] = None
    wp_modus_strom_kuehlen_kwh: Optional[float] = None
    wp_modus_strom_lueften_kwh: Optional[float] = None
    wp_modus_strom_entfeuchten_kwh: Optional[float] = None
    wp_modus_nicht_aufgeteilt_kwh: Optional[float] = None
    #: ⚠ **Die Grundmenge des Stapels** — Σ der Bezugsmengen der Geräte **mit**
    #: Aufteilung, nicht der gesamte WP-Strom. Die Differenz benennt der Client
    #: mit derselben Zeile wie der Balken darunter (W-17b).
    wp_modus_strom_bezug_kwh: Optional[float] = None
    wp_modus_abdeckung_h: Optional[float] = None
    #: Kam die Aufteilung aus **gemessenen** Betriebsart-Zählern?
    wp_modus_gemessen: Optional[bool] = None


class WaermeVerlaufStundeResponse(BaseModel):
    """Eine Stunde des Wärme/Klima-Verlaufs in *Cockpit → Tag* (Bauschnitt 5).

    **Dieselben Feldnamen wie die Tageszeile** (``WaermeVerlaufTagResponse``) —
    der Client baut Jahr, Monat und Tag über dieselbe reine Funktion. Statt
    ``datum`` trägt die Zeile ihren Slot (Rückwärts-Raster, Slot h = [h−1, h)).

    ⚠ **Das Tor ist das Tor des Tages:** ``wp_modus_gemessen`` und
    ``wp_modus_abdeckung_h`` stehen in jeder Stunde so, wie sie für den Tag
    gelten. Hat der Tag eine Aufteilung, gilt sie für jede Stunde — eine Stunde,
    die nur Rest trägt, bleibt sichtbar, sonst verlöre die Zeichnung ihre Summe.

    ⚠ **Keine Temperatur** — sie steht schon in der Stundenantwort des Tages.
    """

    stunde: int
    #: Der Wärmepumpen-Strom des Slots — die Zählerspalte, deren Summe die
    #: Kachel „Strom verbraucht" ist.
    wp_strom_kwh: Optional[float] = None
    #: Gemessene Wärme des Slots (Heizung + Warmwasser), **je Gerät** nach der
    #: Stundenform seiner Zähler verteilt (N-437); ``None`` = keine Aussage.
    wp_waerme_kwh: Optional[float] = None
    #: Gemessene **Kälte** des Slots (Bauschnitt 6b), dieselbe Verteilung — eine
    #: eigene Rolle, nie in ``wp_waerme_kwh``.
    wp_kaelte_kwh: Optional[float] = None
    wp_modus_strom_heizen_kwh: Optional[float] = None
    wp_modus_strom_warmwasser_kwh: Optional[float] = None
    wp_modus_strom_kuehlen_kwh: Optional[float] = None
    wp_modus_strom_lueften_kwh: Optional[float] = None
    wp_modus_strom_entfeuchten_kwh: Optional[float] = None
    wp_modus_nicht_aufgeteilt_kwh: Optional[float] = None
    wp_modus_strom_bezug_kwh: Optional[float] = None
    wp_modus_abdeckung_h: Optional[float] = None
    wp_modus_gemessen: Optional[bool] = None
    # ── Der Funktions-Stapel (WK-09 B2, SOLL §3.3/S2a) ────────────────────
    #
    # ⭐ **Eine andere Familie, deshalb eigene Feldnamen** (SOLL §3.2): Die
    # `wp_modus_*`-Felder darüber sind **Teilmengen** des Stroms (Betriebsart,
    # Rest heißt *nicht aufgeteilt*); diese hier sind **Summanden** aus den
    # Funktions-Zählern `strom_heizen_kwh`/`strom_warmwasser_kwh`. Sie dürfen
    # nie im selben Stapel liegen — der Verlauf schaltet um (S2a).
    wp_funktion_strom_heizen_kwh: Optional[float] = None
    wp_funktion_strom_warmwasser_kwh: Optional[float] = None
    #: Der Rest des Wärmepumpen-Stroms dieses Slots, der zu keiner Funktion
    #: gehört (Standby, Geräte ohne Funktions-Zähler). Er hält die Stapelhöhe
    #: auf dem Gesamtstrom (K1) und heißt, was er ist.
    wp_funktion_uebrige_kwh: Optional[float] = None


class WaermeVerlaufStundenResponse(BaseModel):
    """Die 24 Stunden eines Tages — und was sich keiner Stunde zuordnen ließ."""

    stunden: list[WaermeVerlaufStundeResponse]
    #: Menge der Aufteilung (**Strom**-Stapel), für die es keine Stundenform
    #: gab (P4: nicht gleichmäßig verteilt, sondern genannt). ``None`` = alles
    #: zugeordnet.
    ohne_stundenform_kwh: Optional[float] = None
    #: Dasselbe für die **Wärme**- und die **Kälte**-Linie (N-437, E6 (a)) — je
    #: Gerät gegen den Tageswert gemessen, wie beim Stapel.
    waerme_ohne_stundenform_kwh: Optional[float] = None
    kaelte_ohne_stundenform_kwh: Optional[float] = None
    #: Gibt es an diesem Tag überhaupt gepflegte **Funktions**-Zähler? Nur dann
    #: hat die Sicht „nach Funktion" etwas zu sagen und der Umschalter erscheint
    #: (SOLL §3.3/S2a). ``False`` heißt „nicht erfasst", nicht „alles null".
    funktions_stapel_verfuegbar: bool = False
    #: Menge der **Funktions**-Zähler ohne Stundenform (P4, wie oben).
    funktion_ohne_stundenform_kwh: Optional[float] = None


# ── Verteilung & Verlauf (WK-16c) ────────────────────────────────────────────
#
# ⭐ **Ein Antworttyp für alle drei Stufen.** Was sich zwischen *Tag*, *Monat*
# und *Jahr* ändert, ist allein die Auflösung der Perioden (Stunden · Tage ·
# Monate) — die Segmente, die Kosten und die Temperatur-Linie sind dieselben.
# Drei Typen wären drei Stellen, an denen dieselbe Regel driftet.


class VerteilungSegmentResponse(BaseModel):
    """Ein Segment der Verteilung — **ein Gerät, eine Funktion**."""

    #: ``"<investition_id>:<funktion>"`` — der Schlüssel, unter dem die Perioden
    #: ihre Mengen tragen.
    schluessel: str
    #: ``heizen`` · ``warmwasser`` · ``kuehlen`` · ``lueften`` · ``entfeuchten``
    #: · ``system`` (Zähler-Rest) · ``ohne_modus`` (Modus-Rest).
    funktion: str
    funktion_label: str
    geraet: str
    investition_id: int
    kwh: float
    #: Anteil an der **aufgeteilten** Menge, nicht an der Gesamtmenge (W-17b).
    anteil_prozent: float
    #: ``gemessen`` · ``abgeleitet`` · ``rest``.
    herkunft: str
    #: Der Arbeitspreis, mit dem gerechnet wurde (ct/kWh) — über mehrere Monate
    #: mengengewichtet, damit ``kwh × preis = kosten`` aufgeht (A6).
    preis_cent: Optional[float] = None
    kosten_euro: Optional[float] = None


class VerteilungPeriodeResponse(BaseModel):
    """Eine Periode des Verlaufs."""

    schluessel: str
    label: str
    #: ``{Segment-Schlüssel: kWh}`` — nur Segmente mit Menge. Eine Periode ohne
    #: Aufteilung trägt ein leeres Objekt, **keine** Reihe von Nullen (P4).
    kwh_je_segment: dict[str, float] = {}
    temperatur_c: Optional[float] = None
    #: Symbol-Name des Live-Dashboards (``sunny`` · ``cloudy`` · …). ``None``,
    #: wo kein WMO-Code vorliegt — kein Symbol statt eines erfundenen.
    wetter_symbol: Optional[str] = None


class VerteilungVerlaufResponse(BaseModel):
    """Die Verteilung eines Zeitraums **und** ihr Verlauf (WK-16c)."""

    #: ``tag`` · ``monat`` · ``jahr`` — die angefragte Cockpit-Sicht.
    sicht: str
    #: ``stunde`` · ``tag`` · ``monat`` — die Auflösung der Perioden.
    stufe: str
    segmente: list[VerteilungSegmentResponse] = []
    perioden: list[VerteilungPeriodeResponse] = []
    #: Der **gesamte** Wärme/Klima-Strom des Zeitraums (K1).
    menge_kwh: float = 0.0
    #: Σ der Segmente. Die Differenz zu ``menge_kwh`` nennt der Client als
    #: *„Aufgeteilte Menge X von Y kWh"* — sie wird nicht hineingerechnet.
    aufgeteilt_kwh: float = 0.0
    kosten_gesamt_euro: Optional[float] = None
    #: Σ aller Perioden — bei *Monat* und *Tag* **nicht** ``aufgeteilt_kwh``
    #: (andere Quelle, anderes Fenster). Der Client nennt die Differenz.
    verlauf_kwh: float = 0.0
    #: Nur bei ``stufe == "stunde"``: was sich keiner Stunde zuordnen ließ (P4).
    ohne_stundenform_kwh: Optional[float] = None


class TagWerteResponse(BaseModel):
    """Tageszeile für die Werte/Tabelle-Embed-Sicht in Tagesgranularität
    (IA v4 E3, Cockpit/Monat). Feldnamen sind **deckungsgleich mit den
    Frontend-Registry-Keys** (`lib/werte`), damit der Tag-Accessor `getTagWert`
    — wie `getMonatWert` — direkt `row[key]` lesen kann.

    Energie-Bilanz + Quoten + Speicher/WP stammen aus `bilanz_aus_stundenrows`
    (Σ stündl. TEP-Rows, identische Semantik wie `get_monatsauswertung` →
    additive Symmetrie). Finanzen über den `baue_finanz_zeile`-SoT (#326,
    je-Monat-Tarif). Die `*_kw`/PR/Börsenpreis-Felder sind tag-native (kein
    Monats-Pendant).
    """
    datum: date
    stunden_verfuegbar: int = 0
    datenquelle: Optional[str] = None
    # Zählerlücken wie HA (R4/R9): ``{achse: kWh}`` einer Achse, auf der ein
    # Stunden-Slot gedeckelt oder ein negatives Zähler-Delta verworfen wurde —
    # das Einzige, was eedc an einem Tag markiert. ``{}`` heißt: nach der
    # neuen Regel gerechnet, nichts verworfen; ``None``: Tag von vor dem Umbau
    # (rechnet N-92, bis er neu aggregiert wird). Der Client zeigt den Hinweis
    # „Verfügbare Energie" (N-94) nur, wenn hier eine Achse steht.
    verworfen: Optional[dict[str, float]] = None
    # N-567: ``{achse: kWh}`` der Stunden, die der Deckel nur dank seines Fensters
    # durchgelassen hat (Nachtrag nach Nullstunden) — IN den Summen enthalten, eedc folgt
    # HA. ``None``: kein Nachtrag (oder Tag von vor N-567). Keine Anzeigeregel; der
    # Daten-Checker nennt die Tage.
    nachtrag: Optional[dict[str, float]] = None
    # Energie (additive kWh) — Registry-Keys.
    # `erzeugung`/`eigenverbrauch` sind `None`, wenn für den Tag keine einzige
    # Stunde einen PV-Wert trug (kein kWh-Zähler je Erzeuger — z. B. wenn die PV
    # nur als Anlagen-Aggregat gepflegt ist, das den Monat versorgt und nicht die
    # Tagesebene). Eine 0 wäre dort eine Behauptung; beim Eigenverbrauch entstand
    # daraus sogar ein negativer Wert. SoT der Regel:
    # `docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`, Träger `TagesBilanz.pv_erfasst`.
    erzeugung: Optional[float] = None
    # R17/Verlauf-Vergleich: PV-Anlage vs. BKW getrennt (Σ == PV+BKW-Anteil der
    # Erzeugung; ein evtl. sonstiger Erzeuger/BHKW steckt zusätzlich in `erzeugung`).
    pv_anlage: float = 0.0
    bkw: float = 0.0
    eigenverbrauch: Optional[float] = None
    # Ebenfalls `None`, wenn die jeweilige Achse an keiner Stunde des Tages
    # einen Wert trug (Träger `TagesBilanz.einspeisung_erfasst` /
    # `netzbezug_erfasst` / `verbrauch_erfasst`). Bis 15.08.2026 waren diese
    # vier `float = 0.0` und konnten „nicht gemessen" gar nicht ausdrücken —
    # neben einem korrekten „—" der PV-Spalte stand dann „0 kWh Netzbezug"
    # (Striker, T89667 #162). `direktverbrauch` braucht beide Achsen.
    einspeisung: Optional[float] = None
    netzbezug: Optional[float] = None
    gesamtverbrauch: Optional[float] = None
    direktverbrauch: Optional[float] = None
    # Quoten (%)
    autarkie: Optional[float] = None
    evQuote: Optional[float] = None
    spezErtrag: Optional[float] = None
    # Speicher
    speicher_ladung: Optional[float] = None
    speicher_entladung: Optional[float] = None
    speicher_effizienz: Optional[float] = None
    # Worauf der η beruht — dasselbe Vokabular wie im Monat
    # (`soc_korrigiert` · `roh-unkorrigiert` · `keine-ladung` ·
    # `nicht-ermittelbar`, Layer-SoT `core/berechnungen/speicher_wirkungsgrad`).
    # Ohne dieses Feld stand der Tageswert ohne jede Einordnung da, und ein Tag
    # ist — anders als ein Monat — kein geschlossenes System (T89667 #163).
    speicher_effizienz_quelle: Optional[str] = None
    # Vollzyklen des Tages = Entladung ÷ Kapazität (Kanon, Layer-SoT
    # `core/berechnungen/speicher.vollzyklen`). Bis 2026-07-28 zeigte die
    # Tages-Kachel stattdessen `batterie_vollzyklen` (ΔSoC ÷ 200) — eine
    # andere Größe unter demselben Namen, die sich über Tage nicht zum
    # Monatswert aufsummiert.
    speicher_vollzyklen: Optional[float] = None
    # Wärmepumpe (nur Strom je Tag ableitbar; Wärme/COP bleiben monat-only)
    wp_strom: Optional[float] = None
    # Sonstiges (BHKW, Heizstab, Pool …) — Richtung aus der gepflegten
    # Kategorie, Menge als Betrag (Layer-SoT `sonstiges_kwh_je_richtung`).
    # ⚠ Andere Quelle als im Monat: hier zählt nur, was einen **eigenen
    # Sensor/Zähler** hat (Komponenten-JSON des Tages). Ein Gerät, das nur
    # monatlich von Hand gepflegt wird, hat keine Tageszahl — die Spalte bleibt
    # dann leer, während die Monatsspalte danebensteht. `None` heißt deshalb
    # „für diesen Tag nicht gemessen", nicht 0.
    sonstiges_erzeugung: Optional[float] = None
    sonstiges_verbrauch: Optional[float] = None
    #: §9.2 — Abgabe an Dritte des Tages (nur mit eigenem Zähler); vom
    #: Eigenverbrauch des Tages abgezogen.
    sonstiges_abgabe: Optional[float] = None
    # Finanzen (€) — einfaches lineares Modell wie createMonatsZeitreihe.
    # `None`, wenn die Menge fehlt, auf der der Betrag steht: `ev_ersparnis`
    # ohne erfassten Eigenverbrauch, `netzbezug_kosten` ohne erfassten
    # Netzbezug, und die beiden Summen erben die Lücke ihres Summanden. Der
    # Einspeise-Erlös steht dagegen auf einer gemessenen Menge und bleibt.
    einspeise_erloes: float = 0.0
    ev_ersparnis: Optional[float] = None
    netzbezug_kosten: Optional[float] = None
    netto_ertrag: Optional[float] = None
    netto_bilanz: Optional[float] = None
    # CO₂ — der **PV-Anteil** der kanonischen Bilanz (`berechne_co2_bilanz`,
    # ADR-001/DI-2): Eigenverbrauch × Strommix-Faktor. WP-Wärme und
    # E-Mobilitäts-Kilometer sind Monatsgrößen (`InvestitionMonatsdaten`) und auf
    # Tagesebene nicht gemessen — dieser Wert enthält sie deshalb **nicht**.
    # Bis 2026-07-31 stand hier `erzeugung × Faktor` (F-6): das schrieb auch der
    # eingespeisten kWh die volle Netzstrom-Vermeidung gut.
    # None, wenn der Eigenverbrauch nicht erfasst ist (s. `eigenverbrauch`) —
    # ohne ihn gibt es keine CO₂-Aussage, keine 0.
    co2_einsparung: Optional[float] = None
    # ── Tag-native Zusatzmetriken (kein Monats-Registry-Pendant) ──
    ueberschuss_kwh: Optional[float] = None
    defizit_kwh: Optional[float] = None
    peak_pv_kw: Optional[float] = None
    peak_netzbezug_kw: Optional[float] = None
    peak_einspeisung_kw: Optional[float] = None
    # Grundlast DIESER Nacht — Median der Stunden 0–4 mit `verbrauch_kw > 0`,
    # dieselbe Formel und derselbe Filter wie die Monats-/Jahres-Kachel
    # (`core/berechnungen/grundlast.py`, `_load_grundlast_nacht_kw`), nur über
    # einen Tag statt über einen Monat.
    #
    # ⚠ Es ist NICHT der Monatswert je Tag: der Monat bildet den Median über
    # ALLE Nachtstunden des Monats, nicht den Durchschnitt der Tagesmediane.
    # Beide sind richtig und beantworten verschiedene Fragen. Damit daraus keine
    # zweite Wahrheit wird, trägt die Spalte `aggregation: 'none'` (wie die
    # Peaks) — über einen Zeitraum wird sie gar nicht erst zusammengefasst.
    #
    # ⛔ Bewusst NUR die Leistung. `grundlast_kwh` und der Anteil, die
    # `berechne_grundlast` daneben liefert, haetten hier keinen Leser — ein
    # exportiertes Feld ohne Konsumenten ist genau das, was der
    # Dead-Export-Waechter verhindern soll.
    grundlast_kw: Optional[float] = None
    performance_ratio: Optional[float] = None
    batterie_vollzyklen: Optional[float] = None
    temperatur_min_c: Optional[float] = None
    temperatur_max_c: Optional[float] = None
    strahlung_summe_wh_m2: Optional[float] = None
    # N-384: der NENNER der Performance Ratio (Modulebene, kWp-gewichtet). Ohne ihn
    # war die Kennzahl nicht nachrechenbar — angezeigt wurde `strahlung_summe_wh_m2`,
    # also die HORIZONTALE Strahlung, die nicht in ihrer Formel steht. `None` bei
    # Bestandszeilen von vor der Spalte: „nicht erhoben", keine 0.
    gti_summe_wh_m2: Optional[float] = None
    boersenpreis_avg_cent: Optional[float] = None
    boersenpreis_min_cent: Optional[float] = None
    negative_preis_stunden: Optional[int] = None
    einspeisung_neg_preis_kwh: Optional[float] = None
    # Erzeugung je Erzeuger-Investition (#350, Rainer): Schlüssel ist die
    # **Investitions-ID als String**, Wert die Tages-kWh. Nur belegt, wenn der
    # Erzeuger einen eigenen Sensor hat — auf Tagesebene wird **nichts** nach
    # kWp verteilt (anders als die Monatswerte, `resolve_pv_je_modul`). Ein
    # leeres Dict heißt deshalb „keine Messung je Gerät", nicht „kein Ertrag".
    erzeuger_kwh: Optional[dict[str, float]] = None
    # #377 — Zählerstand je Verbrauchszähler (Gas/Wasser/Öl), Schlüssel ist die
    # **Investitions-ID als String**. Der Wert ist der **Stand am Ende des
    # Tages**, keine Tagesmenge: Ein Zählerstand ist eine Bestandsgröße.
    #
    # ⚠ Er wird in dieser Zeile **nirgends mitsummiert** und geht in keine
    # Bilanzgröße ein — die Spalten tragen `aggregation: 'none'`.
    zaehler_stand: Optional[dict[str, float]] = None


class TagStatusResponse(BaseModel):
    """Warum ist die Tagessicht leer — und was hilft? (F-2, 2026-08-06)

    Wird **nur** abgefragt, wenn Cockpit/Tag für den gewählten Tag keine Werte
    bekommen hat. Der Grund kommt aus dem Backend statt aus einer Client-eigenen
    Ableitung; die Lagen und ihre Texte stehen in
    `services/energie_profil/tag_status.py`.

    `aktion_kind` ist gesetzt, **wo die Handlung wirkt** — bei einem Tag vor der
    Inbetriebnahme, ohne Zuordnung oder ohne HA-Werte bleibt es leer, und der
    Text sagt die Absage offen.
    """
    datum: date
    lage: str
    meldung: str
    details: Optional[str] = None
    link: Optional[str] = None
    aktion_kind: Optional[str] = None
    aktion_label: Optional[str] = None


class TagDetailResponse(BaseModel):
    """Tages-Detail-Werte für Cockpit/Tag, die NICHT in der Tages-Bilanz/
    `TagWerteResponse` stehen, aber aus Snapshots/TEP tagesgenau erhebbar sind
    (D1 „maximal erheben", SPEC-COCKPIT-TAG-JAHR Abschnitt F). Pro gewähltem Tag
    EIN Aufruf (anders als die 90-Tage-Werte-Spanne — diese Felder sind
    snapshot-teuer). Felder sind `None`, wenn der jeweilige Sensor nicht gemappt
    ist bzw. keine Snapshot-/TEP-Daten vorliegen → das Frontend lässt sie weg.
    """
    datum: date
    # WP-Strom-Split (getrennte Strommessung) — Tages-Boundary-Diff.
    wp_strom_heizen_kwh: Optional[float] = None
    wp_strom_warmwasser_kwh: Optional[float] = None
    #: **Was dieser Tag wirklich abdeckt** (R-4/N-491) — der fertige Satz
    #: *„gemessen ab 11:00 Uhr"*, ``None`` am vollen Tag. Er entsteht am ersten
    #: Tag nach einer Zuordnung und am laufenden Tag, wenn ein Tagesrand fehlt
    #: und eedc deshalb ab dem ersten bzw. bis zum letzten Stand misst.
    #:
    #: ⛔ **Der Satz kommt aus dem Layer** (``core/tageswert_grund.py``), nicht
    #: aus dem Client — dieselbe Regel 3 wie bei den drei W-18-Gründen: eine
    #: TS-Kopie der Textliste wäre eine zweite Wahrheit über denselben
    #: Sachverhalt.
    wp_abdeckung_hinweis: Optional[str] = None
    # WP-Wärme (thermisch, nur mit Wärmemengenzähler-Sensor) — Tages-Boundary-Diff.
    # Ermöglicht Tages-JAZ (= Wärme ÷ Strom) und Wärme-Aufteilung.
    wp_heizung_kwh: Optional[float] = None
    wp_warmwasser_kwh: Optional[float] = None
    # ── Wärme gesamt + Arbeitszahl, beide aus dem Layer (W-9 · W-3) ─────────
    #
    # ⛔ **Beides rechnete bis 2026-08-26 der Client.** `wp_waerme_kwh` als
    # `heizung + warmwasser` (`v4/TagKomponenten.tsx`, seit der ersten Fassung
    # der Datei) und die JAZ als Quotient **ohne** die Belastbarkeits-Sperre.
    # Zwei Regeln des Layers, im Client nachgebaut — ADR-001/S1.
    #
    # Der Tag hat keine gepflegte Gesamtwärme, also ist die Summe hier der
    # einzige Zweig des Kanons. Er wird trotzdem über den SoT gebildet
    # (`waermepumpe_kennzahl.waerme_gesamt_kwh`): Eine Regel, die an zwei
    # Stellen steht, driftet — auch wenn eine davon nur die halbe Regel kennt.
    wp_waerme_kwh: Optional[float] = None
    wp_jaz: Optional[float] = None
    #: Warum es keine Arbeitszahl gibt — nie ein „—" ohne Grund (S3).
    wp_jaz_grund: Optional[str] = None
    #: Fall H-B: die Zahl ist richtig und erklärungsbedürftig (Heizstab).
    wp_jaz_hinweis: Optional[str] = None
    #: Die beiden Zahlen, aus denen die Arbeitszahl **tatsächlich** entstanden
    #: ist (kWh) — für die Herleitung an der Kachel.
    #:
    #: ⚠ ``wp_jaz_nenner_kwh`` ist **nicht** ``wp_strom_kwh``: der funktions-
    #: fremde Anteil (Kühlen, Lüften, Entfeuchten) ist abgezogen. Wer die
    #: Herleitung im Client aus den Anzeigefeldern nachbaut, zeigt bei jeder
    #: Anlage mit erfasstem Betriebsmodus eine Rechnung, die nicht auf die Zahl
    #: daneben führt. Deshalb kommen beide aus dem Layer — wie ``grund`` und
    #: ``hinweis`` (W-3: dieselbe Regel an drei Stellen war der teure Fall).
    wp_jaz_zaehler_kwh: Optional[float] = None
    wp_jaz_nenner_kwh: Optional[float] = None
    # ── Arbeitszahl JE FUNKTION (N-348) ────────────────────────────────────
    #
    # ⛔ **Der Tag hat diese drei Zeilen bis 2026-08-29 ERSATZLOS weggelassen.**
    # Nicht als „—", sondern gar nicht: die geteilte Blockfabrik rendert eine
    # Zeile erst, wenn Wert **oder** Grund gesetzt ist, und der Tag setzte
    # keines von beidem. Der Monat ruft `arbeitszahl_je_funktion` dagegen
    # **unbedingt** (`aktueller_monat.py:2103`) und liefert immer beide Hälften
    # — dieselbe Anlage, dieselbe Datenlage, zwei Auskünfte. Genau das verbietet
    # S3 (SOLL §3.3): *„Eine Sicht, die weniger zeigt als die Nachbarsicht, sagt
    # warum."*
    #
    # ⚠ **Ein Begründungssatz allein wäre KEIN Fix gewesen.** „Liegt nur
    # monatlich vor" ist für Heizen/Warmwasser unwahr — §3.3 stellt den Tag auf
    # *„alles, was aus stündlichen Zählern entsteht"*, und alle vier Eingänge
    # stehen unten in dieser Antwort. Die ehrliche Auskunft ist die Rechnung,
    # und sie kostet einen dritten Aufruf eines vorhandenen SoT.
    wp_jaz_heizen: Optional[float] = None
    wp_jaz_heizen_grund: Optional[str] = None
    wp_jaz_warmwasser: Optional[float] = None
    wp_jaz_warmwasser_grund: Optional[str] = None
    #: Kältemenge ÷ Kühlstrom des Tages — **seit Bauschnitt 6** (11.09.2026)
    #: mit einem Tagespfad für den Zähler (`wp_kaelte_kwh` in
    #: `snapshot/aggregator.py::TAGESDETAIL_AUSGABE`, Gerätefeld oder Σ
    #: Innengeräte). Bis dahin stand hier nie ein Wert, nur der Grund „nur im
    #: Monat". Derselbe Layer-Aufruf wie im Monat; die Geräte-Deckung prüft der
    #: Tag selbst, weil er beide Seiten je Gerät kennt.
    wp_jaz_kuehlen: Optional[float] = None
    wp_jaz_kuehlen_grund: Optional[str] = None
    #: **E1b:** ``wp_jaz`` ist eine untere **Schranke** („≥ 3,0") — im Nenner
    #: steht Strom ohne gemessene Wärme. Gleiche Bedeutung und gleiche Quelle
    #: wie im Monat (``AktuellerMonatResponse.wp_jaz_ist_schranke``); der Tages-
    #: Grund *„nicht alle Geräte melden Wärme"* ist damit dieselbe Schranke
    #: statt eines Strichs.
    wp_jaz_ist_schranke: bool = False
    wp_jaz_schranke_hinweis: Optional[str] = None
    #: **D-Sicht 3:** die Kennzahlen je Gerät — aus derselben Rechenstelle wie
    #: Hub, Monat und Jahr (``services/waermepumpe_kennzahlen_je_geraet.py``),
    #: nur mit der Tages-Herkunft der Mengen.
    wp_geraete: list[WpGeraetZeile] = Field(default_factory=list)
    #: **D-Sicht 1:** was die Ausstattung nicht hergibt, einmal je Sicht.
    wp_moeglich: list[WpMoeglichZeile] = Field(default_factory=list)
    #: Die Kältemenge des Tages — der Zähler der Kühlzahl darüber, als Zeile
    #: „Kälte" der Gruppe Kühlen (Bauschnitt 8, 11.09.2026). Bis dahin stand sie
    #: nur lokal in der Route. **> 0, sonst `None`** — dieselbe Regel wie Monat und
    #: Jahr; eine gemessene 0 erklärt die Kühlzahl-Zeile mit ihrem Grund.
    wp_kaelte_kwh: Optional[float] = None
    # Speicher-Netzladung (Arbitrage) — Tages-Boundary-Diff.
    speicher_ladung_netz_kwh: Optional[float] = None
    # Speicher effektiver Netz-Ladepreis (stundengewichtet, Tagesspanne).
    speicher_effektiver_ladepreis_cent: Optional[float] = None
    speicher_effektiver_ladepreis_quelle: Optional[str] = None
    # E-Mobilität PV-/Netz-Anteil der Ladung — Tages-Boundary-Diff (nur bei Sensor).
    emob_ladung_pv_kwh: Optional[float] = None
    emob_ladung_netz_kwh: Optional[float] = None
    # Aufteilung Heizen/Kühlen des Tages (#263/T2) — anlagenweite Σ über alle
    # Wärmepumpen, wie die übrigen WP-Felder hier. `None` heißt „kein
    # Modus-Signal an diesem Tag": der Block erscheint dann gar nicht, statt
    # mit Nullen dazustehen (ADR-002/P4, die F-42-Klasse).
    #
    # ⚠ `wp_modus_nicht_aufgeteilt_kwh` kommt **aus dem Backend**, nicht aus einer
    # Client-Subtraktion: es ist `Bezug − Heizen − Kühlen`, und welcher Bezug
    # gilt, entscheidet die Faltung (Tages-Zählersumme, sonst Roh-Summe des
    # Leistungspfads). Zwei Stellen, die denselben Rest rechnen, driften.
    wp_modus_strom_heizen_kwh: Optional[float] = None
    wp_modus_strom_kuehlen_kwh: Optional[float] = None
    #: N-336: nur aus dem **abgeleiteten** Split — die Gegenrichtung zu den
    #: zwei Feldern darunter, die nur der gemessene Zweig fuellen kann.
    wp_modus_strom_warmwasser_kwh: Optional[float] = None
    #: E4 (Konzept §2.3): nur aus **gemessenen** Betriebsart-Zählern — der
    #: abgeleitete Split kann sie nicht. Dieselben Felder wie in der
    #: Monatssicht, damit dieselbe Blockfabrik beide Sichten bedienen kann.
    wp_modus_strom_lueften_kwh: Optional[float] = None
    wp_modus_strom_entfeuchten_kwh: Optional[float] = None
    wp_modus_nicht_aufgeteilt_kwh: Optional[float] = None
    wp_modus_abdeckung_h: Optional[float] = None
    #: **W-17b** — die Grundmenge, auf die sich die Aufteilung bezieht.
    #: Bewusst **nicht** `wp_strom_kwh`: dort steckt auch der Strom von Geraeten
    #: ohne Modus-Signal. Der Balken steht sonst unter einer Kachel mit einer
    #: groesseren Zahl, ohne dass die Differenz irgendwo benannt waere
    #: (dietmar1968, T89667 #210: Balken 30 kWh unter Kachel 284 kWh).
    wp_modus_strom_bezug_kwh: Optional[float] = None
    #: Herkunft der Aufteilung: `True` = aus **gemessenen** Betriebsart-Zählern,
    #: `False` = aus dem Betriebsmodus abgeleitet. Spiegelt `wp_modus_gemessen`
    #: der Monatssicht (`aktueller_monat.py`) — dieselbe Blockfabrik im Frontend
    #: liest beide Felder, und ohne dieses hier blieb der Block für gemessene
    #: Geräte im Tag **unsichtbar**, während Monat und Jahr ihn zeigten.
    #: Bei einem Betriebsart-Zähler gibt es keine „Stunden mit Signal";
    #: `wp_modus_abdeckung_h` ist dann 0, ohne dass etwas fehlt.
    wp_modus_gemessen: Optional[bool] = None
    #: **W-18** — warum die Tages-Wärme fehlt, als fertiger Satz. Nur gesetzt,
    #: wenn `wp_waerme_kwh` `None` ist; nie beides zugleich.
    #:
    #: ⛔ Er ersetzt einen fest verdrahteten Client-Satz, der **einen** von drei
    #: Zuständen beschrieb und dietmar1968 aufforderte, einen Sensor zuzuordnen,
    #: den er zugeordnet hatte (T89667 #210).
    wp_waerme_grund: Optional[str] = None
    #: **W-18**, dieselbe Klasse an der E-Mobilität.
    emob_ladung_pv_grund: Optional[str] = None
    # PV Tages-SOLL = OM-Tagesprognose × eedc-Lernfaktor (wie Genauigkeits-Tracking).
    soll_pv_kwh: Optional[float] = None
    # Tages-Tarif — für Wirkungsverluste € + Tarif-Zeile.
    einspeise_preis_cent: Optional[float] = None
    #: ⭐ **Seit 17.09.2026 der Preis DIESES Tages**, nicht mehr der des Monats
    #: (SOLL Flex-Tarife **P-2**, Entscheid Gernot): Wo Slot-Preise
    #: mitgeschrieben sind, ist ihr über den Netzbezug gewichteter Tages-Ø die
    #: feinere Quelle. Ohne Mitschrift bleibt es der Monatswert — dann sagt
    #: `netzbezug_preis_herkunft` es auch.
    netzbezug_preis_cent: Optional[float] = None
    #: Woher der Preis daneben stammt: ``gemessen`` (Slot-Preise dieses Tages) ·
    #: ``gemischt`` · ``abgerechnet`` (über den Monat verteilt) · ``vertrag`` ·
    #: ``keine``. **H-1:** Eine Preiszahl ohne ihre Herkunft ist keine Aussage —
    #: ein gemessener Tages-Ø und ein verteilter Monatswert sehen sonst gleich
    #: aus.
    netzbezug_preis_herkunft: Optional[str] = None
    #: Welche **Geräte** hinter den anlagenweiten Summen dieses Tages stecken,
    #: je Typ und beim Namen genannt — dieselbe Form wie in der Monatssicht
    #: (`aktueller_monat.py`), damit die geteilte Blockfabrik im Frontend sie
    #: ohne Sonderweg liest.
    #:
    #: ⛔ **Warum sie hier bis zum 28.08.2026 fehlten — und was das anrichtete.**
    #: Der `GeraeteHinweis` („Aggregiert aus: …") hängt an diesem Feld und
    #: erscheint ab **zwei** Geräten. Monat und Jahr füllten es, der Tag **gar
    #: nicht** — also blieb der Hinweis dort stumm, obwohl derselbe Balken
    #: dieselben Geräte summierte. Betroffen ist nicht nur die Wärmepumpe:
    #: Speicher und E-Mobilität lesen dasselbe Feld.
    #:
    #: ⭐ **Real gemeldet** (dietmar1968, T89667 #221/#226/#237): Er betreibt
    #: eine Luft-Wasser-Wärmepumpe **und** eine Split-Klimaanlage. Beide sind
    #: `typ="waermepumpe"`, beide zählen in denselben Tagesbalken. Sein Satz
    #: dazu lautete *„er vermengt die Anlagen"* — und in der Tagessicht stand
    #: nirgends, dass zwei Geräte darin stecken. Er verglich einen Balken über
    #: **beide** Geräte (11 kWh) mit dem Zähler **einer** Anlage (8,71 kWh).
    #:
    #: ⚠ **Der Balken wird dadurch nicht getrennt, und das ist Absicht**
    #: (SOLL §5): Mengen verschiedener Bauart dürfen nebeneinander stehen, nur
    #: eine gemeinsame *Kennzahl* darf es nicht geben — die sperrt R2.
    komponenten_geraete: dict[str, list[str]] = {}


class ReaggregatePreviewBoundary(BaseModel):
    sensor_key: str
    kategorie: Optional[str] = None
    zeitpunkt: str
    alt_kwh: Optional[float] = None
    neu_kwh: Optional[float] = None


class ReaggregatePreviewSlot(BaseModel):
    stunde: int
    kategorie: str
    alt_kwh: Optional[float] = None
    neu_kwh: Optional[float] = None


class ReaggregatePreviewCounterTagesdelta(BaseModel):
    feld: str
    alt: Optional[int] = None
    neu: Optional[int] = None


class ReaggregatePreviewResponse(BaseModel):
    datum: str
    boundaries: list[ReaggregatePreviewBoundary]
    slot_deltas: list[ReaggregatePreviewSlot]
    tagesumme_alt: dict[str, Optional[float]]
    tagesumme_neu: dict[str, Optional[float]]
    ha_verfuegbar: bool
    counter_tagesdelta: list[ReaggregatePreviewCounterTagesdelta]


class StundenPrognose(BaseModel):
    """Prognose für eine Stunde: PV, Verbrauch, Netto-Bilanz, Batterie-SoC.

    Alles außer ``pv_kw`` hängt an der Verbrauchsprognose. Fehlt die (frische
    Installation ohne Historie, A28/N122), bleiben diese Felder ``None`` — eine
    0 stünde in der Tabelle wie ein Messwert „kein Verbrauch" (P4).
    """
    stunde: int
    pv_kw: float
    verbrauch_kw: Optional[float] = None
    netto_kw: Optional[float] = None       # pv - verbrauch (positiv=Überschuss)
    netzbezug_kw: Optional[float] = None   # max(0, Bedarf nach Batterie-Entladung)
    einspeisung_kw: Optional[float] = None  # max(0, Überschuss nach Batterie-Ladung)
    soc_prozent: Optional[float] = None  # Simulierter Batterie-SoC


class TagesPrognoseResponse(BaseModel):
    """Kombinierte Verbrauchs- + PV- + Batterie-Prognose für einen Tag.

    **Die PV-Hälfte steht immer** (sie braucht nur Wetterdienst + kWp). Die
    verbrauchsabhängige Hälfte — Bilanz, Netzbezug, Einspeisung, Eigenverbrauch,
    Autarkie, Speicher-Simulation, `verbrauch_basis`/`daten_tage` — ist
    ``None``, solange keine Verbrauchsprognose vorliegt (< 3 vollständige Tage
    Energieprofil). Vor A28 gab es in dem Fall HTTP 422 für den ganzen
    Endpoint, also auch für das PV-Profil, das gar keine Historie braucht.
    Warum ``None`` statt 0: eine 0 ist eine Aussage („Verbrauch = 0 kWh",
    „Autarkie = 0 %"), die Anzeige zeigt darauf ein „—" (P4, ADR-002).
    """
    datum: str
    stunden: list[StundenPrognose]
    # Zusammenfassung
    pv_summe_kwh: float
    verbrauch_summe_kwh: Optional[float] = None
    netzbezug_summe_kwh: Optional[float] = None
    einspeisung_summe_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    autarkie_prozent: Optional[float] = None
    # Speicher (optional)
    speicher_kapazitaet_kwh: Optional[float] = None
    speicher_voll_um: Optional[str] = None
    speicher_leer_um: Optional[str] = None
    # Meta
    verbrauch_basis: Optional[str] = None  # "gleicher_wochentag", "tagestyp", "alle"
    pv_quelle: str              # "openmeteo" oder "solcast"
    daten_tage: Optional[int] = None
    # P4 (N78/N79): Unvollständigkeit gehört in die ANTWORT, nicht ins Log.
    # Liefert dieser Endpoint ein PV-Profil, das nicht das ist, was der Name
    # verspricht — 24 Nullen weil jeder Prognose-Pfad ausgefallen ist, oder das
    # Stundenprofil von HEUTE als Näherung für morgen —, dann sagt er es hier.
    # Eine 0 kWh ohne Kennzeichnung ist die Aussage „die Anlage erzeugt morgen
    # nichts"; die Speicher-Simulation daneben rechnet damit weiter („Speicher
    # lädt nicht"). Der Wert wird nicht ersetzt, nur beschriftet.
    hinweise: list[str] = []
