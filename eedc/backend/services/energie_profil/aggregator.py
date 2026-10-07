"""
Tag-Aggregator (Etappe 3c P3 Refactoring-Tail).

Aggregiert Energiedaten eines Tages und persistiert sie in 24 Zeilen
TagesEnergieProfil + 1 TagesZusammenfassung. Wird vom Scheduler täglich
für den Vortag, vom Reaggregat-Endpoint manuell und vom Vollbackfill
historisch aufgerufen.

Helper liegen in `backend.services.energie_profil._helpers` (`_tage_zurueck`,
`_get_wetter_ist`, `_get_soc_history`, `_get_strompreis_stunden`) und werden
hier lazy importiert.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
from backend.core.berechnungen.energie import PV_KOMPONENTEN_PREFIXE
from backend.core.berechnungen.performance_ratio import berechne_performance_ratio
from backend.core.berechnungen.slot_konvention import leistungspfad_slot
from backend.core.berechnungen.speicher import anlagen_soc_prozent
from backend.core.investition_kennwerte import get_speicher_nutzbare_kapazitaet_kwh
from backend.core.source_priority import SOURCE_LABELS
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil._helpers import _speicher_investitionen
from backend.services.energie_profil._provenance_helpers import (
    seed_tep_provenance,
    seed_tz_provenance,
)
from backend.services.energie_profil.source import Source
from backend.services.provenance import write_with_provenance
from backend.utils.investition_filter import aktiv_am_tag

logger = logging.getLogger(__name__)


# Prognose-Felder, die der Wetter-Endpoint (`_speichere_prognose` in
# api/routes/live_wetter.py) asynchron in TagesZusammenfassung schreibt.
# `aggregate_day` macht ein Delete-and-Recreate der Tageszeile und MUSS
# diese Felder daher explizit retten — die Liste MUSS alle Prognose-Felder
# spiegeln, die `_speichere_prognose` schreibt. Sonst gehen sie still
# verloren: `pv_prognose_stundenprofil` fehlte hier bis 2026-05-21, dadurch
# wurde der Day-Ahead-Snapshot jede Nacht gelöscht und die Korrekturprofil-
# Heatmap blieb dauerhaft leer (0 Bins).
_PROGNOSE_FELDER_RETTEN: tuple[str, ...] = (
    "pv_prognose_kwh",
    "pv_prognose_final_kwh",
    "pv_prognose_final_at",
    "sfml_prognose_kwh",
    "solcast_prognose_kwh",
    "solcast_p10_kwh",
    "solcast_p90_kwh",
    "pv_prognose_stundenprofil",
    "solcast_prognose_stundenprofil",
    "sfml_prognose_stundenprofil",
    # N-547: Lern-SOLL des Korrekturprofils — dieselbe Verlustklasse wie
    # `pv_prognose_stundenprofil` oben, nur mit anderem Inhalt.
    "lern_soll_stundenprofil_kwh",
    "lern_soll_kwh",
)


# Extern-additiv befüllte TZ-Felder, die NICHT vom Wetter-Endpoint, sondern von
# einem anderen additiven Schreiber stammen und beim Delete-and-Recreate genau
# so verloren gehen wie die Prognose-Felder (#190-Verlustklasse). Sie gehören
# bewusst NICHT in `_PROGNOSE_FELDER_RETTEN`: Konformitäts-Test K1 koppelt jene
# Liste exklusiv an die Wetter-Endpoint-Schreibfelder (`_TZ_SCHREIBFELDER_PROGNOSE`),
# `kraftstoffpreis_euro` würde sie out-of-sync brechen. Eigene Liste = gleiche
# Mechanik, ehrliche Semantik. Befüllt via `kraftstoff_preis_service.fill_tagesdaten`
# (additiv, `is None`-Filter). Issue #319, PLAN §8.1, Audit §10.4
# (K2-Allowlist-Folge-Diskussion).
_EXTERN_BEFUELLT_FELDER_RETTEN: tuple[str, ...] = (
    "kraftstoffpreis_euro",
)


# N-595 (#422): Stundenfelder, deren Quelle VERFÄLLT — gerettet, wenn der neue Lauf
# für die Stunde nichts liefert. Dieselbe Verlustklasse wie die beiden Listen oben,
# eine Ebene tiefer (Stundenzeile statt Tageszeile), aber ein anderer Grund: Die
# Felder oben schreibt ein ZWEITER Schreiber, diese hier schreibt `aggregate_day`
# selbst — aus Home Assistants Recorder-Verlauf, den HA nach `purge_keep_days`
# (Standard 10 Tage) löscht.
#
# * `betriebsmodus_je_wp` — **immer** nur Recorder (`climate` hat keine LTS,
#   Konzept 263 D9). Bis N-596 schrieb ein Monatsabschluss am Monatsersten damit
#   rund zwei Drittel des Monats ohne Betriebsart neu; die Aufteilung Heizen/Kühlen
#   fiel auf „nicht aufgeteilt". Seit N-596 lässt er Tage, deren Leistungskurve
#   keinen Wert mehr trägt, stehen (``hole_tagesverlauf``); die Rettung hier greift
#   weiter, wo ein solcher Tag doch neu geschrieben wird — Werkbank aus der
#   Langzeitstatistik (die keine Betriebsart kennt) und Tage ohne Gerätewerte.
# * `soc_prozent` / `soc_je_speicher` / `strompreis_cent` — nur dann, wenn ihr
#   Sensor keine Langzeitstatistik hat und der History-Fallback greift.
#
# ⚠ NICHT `boersenpreis_cent`: externe Quelle, rückwirkend abrufbar — dort gewinnt
# immer der neue Abruf, auch ein leerer.
#
# Regel: **die Quelle gewinnt, wo sie liefert**; gerettet wird nur, was sonst leer
# bliebe, und nur in Stunden, die der neue Lauf ohnehin schreibt (keine Zeile wird
# erfunden). Wächter: `test_konformitaet_tep_felder.py` (K3) liest DIESE Konstante.
_STUNDEN_FELDER_RETTEN: tuple[str, ...] = (
    "betriebsmodus_je_wp",
    "soc_prozent",
    "soc_je_speicher",
    "strompreis_cent",
)

# Provenance-Fallback einer geretteten Stunde ohne verwertbaren alten Eintrag —
# dasselbe Label/derselbe Writer wie der Restore der Tageszeile (#299).
_PRESERVE_QUELLE = "auto:preserve_restore"
_PRESERVE_WRITER = "aggregator-preserve"


# ═══════════════════════════════════════════════════════════════════════════
#  Zwei Rundungs-REGELN, die heute gleich aussehen und es nicht sind
# ═══════════════════════════════════════════════════════════════════════════
#
# In der Stundenzeile ist 0 ein Messwert: nachts liefert die PV 0 kW, und das ist keine
# Lücke — genau die Projektregel „`is not None`, nicht `if val`". In der Tageszeile heißt 0
# dagegen *keine Aussage*: ein Überschuss von 0 kWh, ein Peak von 0 kW oder eine
# Strahlungssumme von 0 Wh/m² entsteht nur, wenn nie etwas gemessen wurde — dort wäre eine
# gespeicherte 0 eine Behauptung, NULL ist die Lücke. Die Helfer benennen den Unterschied,
# statt ihn 25-mal als wortgleiches Ternär zu wiederholen (18 × `rund`/`ganz` in der
# Stundenzeile, 7 × `nur_positiv` in der Tageszeile).


def rund(wert, stellen: int):
    """0 ist ein Wert, ``None`` ist die Lücke (Stundenzeile)."""
    return None if wert is None else round(wert, stellen)


def ganz(wert):
    """Wie ``rund``, aber ganzzahlig (``wetter_code``)."""
    return None if wert is None else int(wert)


def nur_positiv(wert, stellen: int):
    """0 ist hier KEINE Aussage, sondern die Lücke (Tageszeile: Summen und Peaks).

    Alle Aufrufer übergeben mit ``0.0`` initialisierte Summen bzw. Peaks — ``None`` kann
    dort nicht ankommen, deshalb genügt der Vergleich ``> 0``.
    """
    return round(wert, stellen) if wert > 0 else None


# ═══════════════════════════════════════════════════════════════════════════
#  Stunden-Schleife — zwei Traeger und sieben Phasen
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class StundenKontext:
    """Alles, was die Stunden-Schleife LIEST. Einmal vor der Schleife gefuellt.

    ``sonderschluessel`` wird bewusst hier gehalten und nicht je Stunde gebaut: es ist eine
    Vereinigung von sechs Kategorie-Mengen, die sich innerhalb eines Tages nicht aendert.
    """
    anlage: Anlage
    datum: date
    netz_keys: set
    pv_keys: set
    sonderschluessel: set
    kwh_pro_stunde: dict
    kwh_source_label: str
    wetter_stunden: dict
    soc_stunden: dict
    soc_je_stunde: dict
    betriebsmodus_je_stunde: dict
    strompreis_stunden: object
    wp_starts_pro_stunde: dict
    wp_betriebsstunden_pro_stunde: dict
    # N-595: je Slot die Felder, die ganz aus der Rettung stammen, mit ihrem ALTEN
    # Provenance-Eintrag (``None`` = keiner verwertbar ⇒ ``auto:preserve_restore``).
    gerettete_herkunft: dict = field(default_factory=dict)


@dataclass
class TagesAkkumulator:
    """Alles, was die Stunden-Schleife SCHREIBT und die Tages-Phasen danach lesen.

    ⛔ Bewusst NICHT ``frozen`` und bewusst nicht der Rueckgabewert einer Phase: zwei seiner
    Felder werden NACH der Schleife noch ueberschrieben — ``komponenten_summen`` vom
    Komponenten-Tagesgesamt (Boundary-Diff gewinnt ueber die Live-Sigma) und die drei Peaks vom
    HA-LTS-Override (Min/Max gewinnt ueber die W-Integration). Ein unveraenderlicher Traeger
    erzwaenge an dieser Stelle einen Kopier-Schritt, den man beim Lesen fuer eine
    Rechenaenderung haelt. Die Reihenfolge Schleife -> Tagesgesamt -> Peak-Override ist
    tragend, nicht zufaellig.
    """
    tages_ueberschuss: float = 0.0
    tages_defizit: float = 0.0
    peak_pv: float = 0.0
    peak_bezug: float = 0.0
    peak_einspeisung: float = 0.0
    temp_values: list = field(default_factory=list)
    strahlung_summe: float = 0.0
    pv_ertrag_summe: float = 0.0
    # mind. eine Stunde mit gemessener PV — s. Performance Ratio
    pv_ertrag_erfasst: bool = False
    gti_summe: float = 0.0          # kWp-gewichtete GTI (Wh/m²) über den Tag — für PR (#139)
    gti_stunden_count: int = 0
    soc_values: list = field(default_factory=list)
    stunden_count: int = 0
    # Per-Komponenten Tages-kWh
    komponenten_summen: dict = field(default_factory=dict)
    # h → kWh (für Negativpreis-Berechnung)
    einspeisung_pro_stunde: dict = field(default_factory=dict)
    # Eingänge für die Ableitung des PV-Anteils der Heimladung (N-141 Weg c).
    # Hier gesammelt statt nachträglich aus `TagesEnergieProfil` gelesen:
    # Rahmenbedingung 2 („Rechnung im Aggregator") — die Größen liegen in
    # dieser Schleife ohnehin vor, ein zweiter Lesepfad wäre eine zweite
    # Wahrheit.
    lade_stunden: list = field(default_factory=list)


@dataclass(frozen=True)
class Leistungsspitzen:
    """Momentanwerte der Stunde aus dem Leistungspfad (W) — nur fuer die Tages-Peaks."""
    pv_kw_w: float
    netzbezug_kw_w: float
    einspeisung_kw_w: float


@dataclass(frozen=True)
class Zaehlerstunde:
    """Die kWh-Werte einer Stunde aus dem Zaehlerpfad. ``None`` heisst: kein Zaehler."""
    pv_kw: Optional[float]
    sonstige_erz_kw: Optional[float]
    einspeisung_kw: Optional[float]
    netzbezug_kw: Optional[float]
    verbrauch_kw: Optional[float]
    waermepumpe_kw: Optional[float]
    wallbox_kw: Optional[float]
    batterie_kw: Optional[float]
    # Zählerlücken wie HA (R2): {achse: n} nur für n > 1, sonst None.
    spannen: Optional[dict] = None


@dataclass(frozen=True)
class Wetterstunde:
    """Die Wetter-IST-Werte einer Stunde."""
    temperatur: Optional[float]
    strahlung: Optional[float]
    gti: Optional[float]
    bewoelkung: Optional[float]
    niederschlag: Optional[float]
    wcode: Optional[float]


def leistungsspitzen_der_stunde(werte: dict, kontext: StundenKontext) -> Leistungsspitzen:
    # ── Leistungs-Spitzen aus Tagesverlauf (W-Integration nur für Peaks) ──
    # kW-Peaks brauchen keine kWh-Präzision; Zähler liefern keine Momentanwerte.
    netz_val = sum(werte.get(k, 0) for k in kontext.netz_keys)
    einspeisung_kw_w = abs(netz_val) if netz_val < 0 else 0.0
    netzbezug_kw_w = netz_val if netz_val > 0 else 0.0

    pv_kw_w = sum(v for k in kontext.pv_keys
                  if (v := werte.get(k, 0)) > 0)
    for k, v in werte.items():
        if v is None or k in kontext.sonderschluessel:
            continue
        if v > 0:
            pv_kw_w += v
    return Leistungsspitzen(
        pv_kw_w=pv_kw_w,
        netzbezug_kw_w=netzbezug_kw_w,
        einspeisung_kw_w=einspeisung_kw_w,
    )


def zaehlerwerte_der_stunde(h: int, kontext: StundenKontext) -> Zaehlerstunde:
    # ── kWh-Werte aus Zähler-Snapshots (Issue #135) ───────────────────
    # Fehlt der Zähler einer Kategorie, bleibt der Wert None.
    # Konvention für Batterie: positiv=Ladung, negativ=Entladung (netto).
    from backend.core.berechnungen import batterie_kw_spalte

    snap_h = kontext.kwh_pro_stunde.get(h, {}) if kontext.kwh_pro_stunde else {}
    return Zaehlerstunde(
        pv_kw=snap_h.get("pv"),  # inkl. Sonstiges-Erzeuger (für die Bilanz)
        sonstige_erz_kw=snap_h.get("erzeugung_sonstiges"),  # für PV-reine PR
        einspeisung_kw=snap_h.get("einspeisung"),
        netzbezug_kw=snap_h.get("netzbezug"),
        verbrauch_kw=snap_h.get("verbrauch"),
        waermepumpe_kw=snap_h.get("wp"),
        wallbox_kw=snap_h.get("wallbox"),
        # Spalten-Konvention: ENTLADUNG positiv, LADUNG negativ (= Negation des
        # Bilanz-Netto `ladung − entladung`). batt_netto bleibt für die Bilanz-
        # Formel unten (verbrauch) erhalten. SoT: core.berechnungen.batterie_kw_spalte.
        batterie_kw=batterie_kw_spalte(snap_h.get("batterie_netto")),
        spannen=snap_h.get("spannen") or None,
    )


def wetter_der_stunde(h: int, kontext: StundenKontext) -> Wetterstunde:
    wetter_h = kontext.wetter_stunden.get(h, {})
    return Wetterstunde(
        temperatur=wetter_h.get("temperatur_c"),
        strahlung=wetter_h.get("globalstrahlung_wm2"),
        gti=wetter_h.get("gti_wm2"),
        bewoelkung=wetter_h.get("bewoelkung_prozent"),
        niederschlag=wetter_h.get("niederschlag_mm"),
        wcode=wetter_h.get("wetter_code"),
    )


def verrechne_stunde(
    h: int,
    zaehler: Zaehlerstunde,
    wetter: Wetterstunde,
    kontext: StundenKontext,
    akku: TagesAkkumulator,
) -> tuple:
    """Schreibt die Stunde in den Tages-Akkumulator.

    Returns:
        (ueberschuss, defizit, soc, strompreis, boersenpreis) — die fuenf Groessen, die
        ausserdem in der Stundenzeile stehen.
    """
    from backend.core.berechnungen.pv_anteil_ladung import stunde_aus_bilanzwerten

    # Einspeisung pro Stunde für Negativpreis-Analyse (§51 EEG)
    if zaehler.einspeisung_kw is not None and zaehler.einspeisung_kw > 0:
        akku.einspeisung_pro_stunde[h] = zaehler.einspeisung_kw

    # Eingänge für die PV-Anteils-Ableitung der Heimladung (N-141 Weg c).
    # Die Vorzeichen-Übersetzung macht der Layer-Helfer — sie ist die eine
    # Stelle, an der man sich hier vertun könnte (s. seinen Docstring).
    #
    # ⚠ Der Nenner ist bewusst `wallbox_kw`, also GENAU die Größe, aus der
    # auch die gespeicherte Wallbox-Spalte entsteht. Sie ist `ladung_wallbox
    # + verbrauch_eauto` und gegen Doppelzählung nur über
    # `parent_investition_id` geschützt (N-196, dieselbe Masche wie F-14 im
    # Leistungspfad). Das hier ist Absicht: eine eigene Sonderregel wäre
    # eine zweite Wahrheit über dieselbe Ladung, und wird N-196 behoben,
    # zieht diese Rechnung ohne Zutun mit.
    # ⭐ Zählerlücken wie HA (§2): trägt die Ladung, die PV oder der Netzbezug
    # dieser Zeile mehr als eine reale Stunde, wird die Stunde NICHT abgeleitet
    # — Netz/Einspeisung gehen als „nicht gedeckt" hinein, damit die Marke
    # `…teilweise` die Lücke ausweist (P4) statt eine n-Stunden-Menge mit der
    # Deckung einer einzigen Stunde zu bewerten.
    from backend.core.berechnungen.spannen import spanne as _spanne
    _gebuendelt = any(
        _spanne(zaehler.spannen, a) > 1 for a in ("wallbox", "pv", "netzbezug")
    )
    akku.lade_stunden.append(stunde_aus_bilanzwerten(
        ladung=zaehler.wallbox_kw,
        netzbezug=None if _gebuendelt else zaehler.netzbezug_kw,
        einspeisung=None if _gebuendelt else zaehler.einspeisung_kw,
        batterie_spalte=zaehler.batterie_kw,
    ))

    # Bilanz-Aggregate (nur wenn pv und verbrauch bekannt)
    if zaehler.pv_kw is not None and zaehler.verbrauch_kw is not None:
        ueberschuss = max(0.0, zaehler.pv_kw - zaehler.verbrauch_kw)
        defizit = max(0.0, zaehler.verbrauch_kw - zaehler.pv_kw)
        akku.tages_ueberschuss += ueberschuss
        akku.tages_defizit += defizit
    else:
        ueberschuss = None
        defizit = None

    if zaehler.pv_kw is not None:
        # Performance-Ratio = reine PV-Qualität (Ertrag vs. GTI) → den in `pv`
        # enthaltenen Sonstiges-Erzeuger-Anteil (BHKW, kein GTI-Bezug) abziehen.
        akku.pv_ertrag_summe += zaehler.pv_kw - (zaehler.sonstige_erz_kw or 0.0)
        akku.pv_ertrag_erfasst = True

    # Wetter
    if wetter.temperatur is not None:
        akku.temp_values.append(wetter.temperatur)
    if wetter.strahlung is not None:
        akku.strahlung_summe += wetter.strahlung  # W/m² × 1h = Wh/m²
    if wetter.gti is not None:
        akku.gti_summe += wetter.gti
        akku.gti_stunden_count += 1

    # SoC
    soc = kontext.soc_stunden.get(h)
    if soc is not None:
        akku.soc_values.append(soc)

    # Strompreis (Sensor-Endpreis + Börsenpreis getrennt)
    strompreis = kontext.strompreis_stunden.sensor.get(h)
    boersenpreis = kontext.strompreis_stunden.boerse.get(h)
    return ueberschuss, defizit, soc, strompreis, boersenpreis


def summiere_live_komponenten(
    werte: dict, kontext: StundenKontext, akku: TagesAkkumulator,
) -> None:
    # Per-Komponenten kWh akkumulieren (kW × 1h = kWh) — Live-Σ-Riemann.
    # Nur im Standalone-Fallback (kein HA-LTS) aktiv. Im HA-Add-on-Modus
    # ist diese Akkumulation redundant zum Boundary-Pfad (boundary_kwh
    # weiter unten) und war historische Drift-Quelle: bei Schema-Mismatch
    # zwischen Live-Service-Key und Boundary-Key (z.B. balkonkraftwerk
    # → Live `pv_<id>`, Boundary `bkw_<id>`) blieben beide Keys parallel
    # in `komponenten_summen` und wurden von Whitelist-Konsumenten
    # doppelt gezählt (BKW-Bug 2026-05-19, Rainer-PN).
    if werte and kontext.kwh_source_label != "external:ha_statistics:hourly":
        for komp_key, komp_kw in werte.items():
            if komp_kw is not None and komp_key != "strompreis":
                akku.komponenten_summen[komp_key] = (
                    akku.komponenten_summen.get(komp_key, 0.0) + komp_kw
                )


def baue_stundenzeile(
    h: int,
    werte: dict,
    zaehler: Zaehlerstunde,
    wetter: Wetterstunde,
    ueberschuss: Optional[float],
    defizit: Optional[float],
    soc: Optional[float],
    strompreis: Optional[float],
    boersenpreis: Optional[float],
    kontext: StundenKontext,
) -> TagesEnergieProfil:
    # is not None statt `if x` — echte 0-Werte (Nacht-PV) sind keine Lücke.
    return TagesEnergieProfil(
        anlage_id=kontext.anlage.id,
        datum=kontext.datum,
        stunde=h,
        pv_kw=rund(zaehler.pv_kw, 3),
        verbrauch_kw=rund(zaehler.verbrauch_kw, 3),
        einspeisung_kw=rund(zaehler.einspeisung_kw, 3),
        netzbezug_kw=rund(zaehler.netzbezug_kw, 3),
        batterie_kw=rund(zaehler.batterie_kw, 3),
        waermepumpe_kw=rund(zaehler.waermepumpe_kw, 3),
        wallbox_kw=rund(zaehler.wallbox_kw, 3),
        # Zählerlücken wie HA (R2): wie viele reale Stunden eine Achse trägt.
        spannen=zaehler.spannen,
        ueberschuss_kw=rund(ueberschuss, 3),
        defizit_kw=rund(defizit, 3),
        temperatur_c=rund(wetter.temperatur, 1),
        globalstrahlung_wm2=rund(wetter.strahlung, 0),
        bewoelkung_prozent=rund(wetter.bewoelkung, 0),
        niederschlag_mm=rund(wetter.niederschlag, 2),
        wetter_code=ganz(wetter.wcode),
        soc_prozent=rund(soc, 1),
        soc_je_speicher=(
            {str(k): round(v, 1) for k, v in kontext.soc_je_stunde[h].items()}
            if kontext.soc_je_stunde.get(h) else None
        ),
        # #263 K-2. `None` statt `{}` bei fehlendem Signal: die Spalte
        # unterscheidet „nicht hingesehen" (NULL) von „hingesehen, Seite
        # nicht zuordenbar" (Wert `unbestimmt`) — ein leeres Dict wäre
        # weder das eine noch das andere.
        betriebsmodus_je_wp=(
            {str(k): v for k, v in kontext.betriebsmodus_je_stunde[h].items()}
            if kontext.betriebsmodus_je_stunde.get(h) else None
        ),
        strompreis_cent=rund(strompreis, 2),
        boersenpreis_cent=rund(boersenpreis, 2),
        komponenten={k: v for k, v in werte.items() if k != "strompreis"} if werte else None,
        wp_starts_anzahl=kontext.wp_starts_pro_stunde.get(h),
        wp_betriebsstunden=kontext.wp_betriebsstunden_pro_stunde.get(h),
    )


def verarbeite_stunde(
    punkt: dict,
    kontext: StundenKontext,
    akku: TagesAkkumulator,
    db: AsyncSession,
    auto_writer: str,
) -> None:
    """Eine Stunde: Spitzen, Zaehlerwerte, Wetter, Verrechnung, Live-Σ, Zeile schreiben."""
    h = int(punkt["zeit"].split(":")[0])
    werte = punkt.get("werte", {})

    spitzen = leistungsspitzen_der_stunde(werte, kontext)
    zaehler = zaehlerwerte_der_stunde(h, kontext)
    wetter = wetter_der_stunde(h, kontext)
    ueberschuss, defizit, soc, strompreis, boersenpreis = verrechne_stunde(
        h, zaehler, wetter, kontext, akku,
    )

    # Peaks fortschreiben
    akku.peak_pv = max(akku.peak_pv, spitzen.pv_kw_w)
    akku.peak_bezug = max(akku.peak_bezug, spitzen.netzbezug_kw_w)
    akku.peak_einspeisung = max(akku.peak_einspeisung, spitzen.einspeisung_kw_w)

    summiere_live_komponenten(werte, kontext, akku)

    # TagesEnergieProfil speichern
    profil = baue_stundenzeile(
        h, werte, zaehler, wetter, ueberschuss, defizit, soc,
        strompreis, boersenpreis, kontext,
    )
    db.add(profil)
    seed_tep_provenance(profil, writer=auto_writer, source=kontext.kwh_source_label)
    # N-595 (S4): ein gerettetes Feld behält seine ALTE Herkunft — es wurde nicht in
    # diesem Lauf gemessen. Bewusst NACH dem Seed, der es sonst mit dem Lauf-Label
    # stempelte (dieselbe Reihenfolge-Regel wie der TZ-Restore, #299).
    herkunft = kontext.gerettete_herkunft.get(h)
    if herkunft:
        setze_gerettete_herkunft(profil, herkunft)
    akku.stunden_count += 1


def setze_gerettete_herkunft(profil: TagesEnergieProfil, herkunft: dict) -> None:
    """Je gerettetem Feld den alten Provenance-Eintrag einsetzen (N-595, S4).

    ``herkunft`` = ``{feld: alter_eintrag | None}``. Ohne verwertbaren alten Eintrag
    (keiner, oder eine Quelle, die ``SOURCE_LABELS`` nicht kennt) steht dort
    ``auto:preserve_restore`` — wie beim Restore der Tageszeile. Kein Audit-Log je
    Feld: dieselbe Abwägung wie ``seed_tep_provenance`` (24 Zeilen × n Felder je Tag).
    """
    from backend.services.provenance import seed_provenance

    for feld, eintrag in herkunft.items():
        if getattr(profil, feld, None) is None:
            continue
        if eintrag is None:
            seed_provenance(
                profil, source=_PRESERVE_QUELLE, writer=_PRESERVE_WRITER, fields=[feld],
            )
            continue
        provenance = dict(profil.source_provenance or {})
        provenance[feld] = dict(eintrag)
        profil.source_provenance = provenance


#: Schlüssel einer Tageskurve, die KEINE Leistung sind (N-596). Der Börsenpreis-Rückfall in
#: ``get_tagesverlauf`` schreibt ``strompreis`` in jeden Punkt — auch für einen Tag, den Home
#: Assistant längst gepurgt hat (aWATTar liefert rückwirkend; gemessen 02.10.2026: 150 von 150
#: Punkten des 30.08. tragen ihn). Ausdrücklich genannt, weil die Serie dazu nur angehängt wird,
#: wenn ein Punkt ihn trägt; alle weiteren Overlays erkennt ``kurve_traegt_leistung`` an
#: ``serien[*].seite == "overlay"``.
_KURVEN_OVERLAY_SCHLUESSEL: frozenset[str] = frozenset({"strompreis"})


def kurve_traegt_leistung(
    punkte_raw: Optional[list],
    vortagsrand_raw: Optional[list],
    serien: Optional[list],
) -> bool:
    """Trägt die Kurve irgendwo einen Leistungswert? (N-596)

    ``True``, sobald ein Punkt aus ``punkte_raw`` oder ``vortagsrand_raw`` für einen Schlüssel,
    der kein Overlay ist, einen Wert ``≠ None`` trägt — auch ``0.0`` (ein Sensor, der null
    meldet, hat gemessen).

    ⚠ „Liste leer" ist NICHT die Frage: Der HA-Zweig von ``get_tagesverlauf`` liefert für einen
    vergangenen Tag immer das volle Raster — 144 Punkte und 6 Vortagsrand-Punkte —, auch wenn
    Home Assistant für den Tag nichts mehr hat. Bis N-596 prüfte ``hole_tagesverlauf`` nur die
    Länge und schrieb solche Tage mit leerer Kurve neu.
    """
    overlay = set(_KURVEN_OVERLAY_SCHLUESSEL) | {
        s.get("key") for s in (serien or []) if s.get("seite") == "overlay"
    }
    for punkt in (*(punkte_raw or ()), *(vortagsrand_raw or ())):
        for schluessel, wert in ((punkt or {}).get("werte") or {}).items():
            if schluessel not in overlay and wert is not None:
                return True
    return False


async def _tag_hat_geraetewerte(anlage: Anlage, datum: date, db: AsyncSession) -> bool:
    """Trägt mindestens eine gespeicherte Stundenzeile des Tages Gerätewerte (``komponenten``)?

    Leeres Dict und ``NULL`` zählen beide als „keine" — eine Zählerzeile ohne Leistungspunkt
    schreibt ``{}`` (nur Börsenpreis in ``werte``) bzw. ``NULL`` (``werte`` leer).
    """
    zeilen = await db.execute(
        select(TagesEnergieProfil.komponenten).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == datum,
            )
        )
    )
    return any(bool(k) for (k,) in zeilen.all())


async def hole_tagesverlauf(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
    prefetched_tagesverlauf: Optional[dict],
    *,
    source: Optional[Source] = None,
    leere_kurve_erlaubt: bool = False,
    nur_mit_verlauf: bool = False,
) -> Optional[tuple]:
    """Eingang und Rohverlauf — Prefetch-Zweig, Live-Zweig, synthetische Slots.

    ⚠ Die beiden fruehen ``return None`` sind Vertrag, nicht Formsache: F-26 (Forum T89667 #142,
    IdleBit) ist an ihrem Verhalten gebaut worden. Sie bleiben hier und werden vom Orchestrator
    als ``None`` weitergereicht.

    ⭐ Dritter früher Ausstieg, dieselbe Semantik (N-596, #422): **Eine Kurve ohne einen
    einzigen Leistungswert überschreibt keine gespeicherten Gerätewerte.** Nur im Live-Zweig
    (nicht Prefetch, nicht synthetische Slots, nicht MQTT-Energie ohne Leistungszuordnung);
    die Kurve trägt keine Leistung, wenn ``kurve_traegt_leistung`` nein sagt — typisch, weil
    Home Assistant den Tag aus dem Verlauf gelöscht hat (``purge_keep_days``). Dann:

    a) Werkbank (``source.is_manual_repair()``) ohne ``leere_kurve_erlaubt`` ⇒ ``None``: sie
       versucht zuerst ihren LTS-Rückfall (``repair_orchestrator._reparatur_aggregat``) — auch
       für einen Tag, der schon leer geschrieben ist (Rückweg).
    b) sonst, wenn eine gespeicherte Stundenzeile des Tages ``komponenten`` trägt ⇒ ``None``:
       der Tag bleibt stehen (Monatsabschluss, Scheduler, Archiv-Nachzug, Werkbank nach
       leerem LTS-Rückfall).
    c) sonst weiter wie bisher: der Tag wird aus den Zählern geschrieben (N-563 O1). Ein Tag
       ohne Gerätewerte hat nichts zu verlieren, und eine Anlage, deren Leistungssensoren
       keine Historie haben (Recorder-Ausschluss, umbenannte Entity), friert sonst nach dem
       ersten Lauf des Tages ein.

    ⭐ HA-Bauform E4f (Bauplan §9 B1, R-13): mit ``nur_mit_verlauf`` gilt c) NICHT — eine Kurve
    ohne Leistungswert liefert ``None``, auch für einen Tag ohne Zeilen. Das ist die Grenze der
    Recorder-Aufbewahrung von Home Assistant, an DERSELBEN Stelle wie N-596 erkannt (kein fester
    Tageswert, ``purge_keep_days`` ist je Installation anders): Der Monatsabschluss-Nachlauf legt
    einen fehlenden Tag nur an, solange HA ihn noch im Verlauf hat. MQTT-Energie ohne
    Leistungszuordnung und die synthetischen Slots berührt das nicht — dort gibt es keinen
    Verlauf, der verfallen könnte.

    Returns:
        ``(serien, punkte_raw, vortagsrand_raw, synthetische_slots)`` oder ``None``.
    """
    from backend.services.energie_profil._helpers import _tage_zurueck

    if prefetched_tagesverlauf is not None:
        # Vollbackfill-Pfad: historische Stunden-Daten sind bereits gebündelt
        # vorgeholt. Sensor-Konfig wurde vom Caller validiert, get_tagesverlauf
        # (HA-History, ~10 Tage) würde für alte Tage ohnehin leer liefern.
        tv_data = prefetched_tagesverlauf
    else:
        from backend.services.live_power_service import get_live_power_service

        service = get_live_power_service()

        # Sensor-Mapping prüfen — im Standalone-/Docker-Modus sind die
        # `live`-Einträge oft leer (MQTT liefert direkt Topics). Der Lauf darf
        # trotzdem laufen, wenn MQTT-Energy-Snapshots vorliegen; der Zähler-Pfad
        # braucht kein leistung_w (Issue #135 Blocker 2). Die Bedingung steht
        # seit v4.0.10 an EINER Stelle — Daten-Checker und Tages-Begründung lesen
        # dieselbe, statt sie zu kopieren.
        from backend.services.energie_profil.aggregations_quelle import (
            ermittle_aggregations_quelle,
        )

        quelle = await ermittle_aggregations_quelle(db, anlage, datum)
        has_mqtt_energy = quelle.mqtt_energie
        if not quelle.vorhanden:
            logger.debug(f"Anlage {anlage.id}: Keine Live-Sensoren konfiguriert")
            return None

        # ── Tagesverlauf-Daten holen ──────────────────────────────────────
        try:
            tv_data = await service.get_tagesverlauf(
                anlage, db, tage_zurueck=_tage_zurueck(datum),
                mit_vortagsrand=True,
            )
        except Exception as e:
            logger.warning(f"Anlage {anlage.id}, {datum}: Tagesverlauf-Fehler: {type(e).__name__}: {e}")
            tv_data = {"serien": [], "punkte": []}

    serien = tv_data.get("serien", [])
    punkte_raw = tv_data.get("punkte", [])
    # [Vortag 23:00, 00:00) — das physische Intervall des Backward-Slots 0.
    # Getrennte Liste, weil ein Punkt nur seine Uhrzeit trägt, nicht sein Datum
    # (s. `get_tagesverlauf`). Der Vollbackfill reicht sie ebenso durch.
    vortagsrand_raw = tv_data.get("vortagsrand", [])

    # Wenn keine leistung_w-Daten vorliegen aber MQTT-Energy da ist → synthetisches
    # punkte-Array mit leeren werte-Dicts, damit die Stunden-Schleife 24x läuft
    # und die Zähler-Snapshot-Werte in TagesEnergieProfil landen können.
    # (Im Vollbackfill-Pfad mit prefetched_tagesverlauf liefert der Caller die
    # punkte bereits; `has_mqtt_energy` ist dort nicht definiert — die explizite
    # `is None`-Prüfung short-circuited davor.)
    if not punkte_raw and prefetched_tagesverlauf is None and has_mqtt_energy:
        punkte_raw = [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)]
        vortagsrand_raw = []
        synthetische_slots = True
    elif not punkte_raw:
        logger.debug(f"Anlage {anlage.id}, {datum}: Keine Tagesverlauf-Daten")
        return None
    else:
        synthetische_slots = False

    # ── N-596: Kurve ohne Leistungswert (s. Docstring a/b/c) ──────────────
    # Nicht bei MQTT-Energie ohne Leistungszuordnung (`has_mqtt_energy` ist nur
    # dann wahr, s. `ermittle_aggregations_quelle`): dort gibt es keine
    # Leistungsquelle, die verfallen könnte — die Kurve ist immer leer, und der
    # Tag kommt wie bisher aus den Zählern (dieselbe Lage wie die synthetischen
    # Slots, nur dass die Punkte schon da sind).
    if (
        prefetched_tagesverlauf is None
        and not synthetische_slots
        and not has_mqtt_energy
        and not kurve_traegt_leistung(punkte_raw, vortagsrand_raw, serien)
    ):
        if nur_mit_verlauf:
            logger.info(
                f"Anlage {anlage.id}, {datum}: Leistungskurve ohne Wert (außerhalb der Recorder-"
                "Aufbewahrung) — fehlender Tag wird nicht angelegt"
            )
            return None
        if source is not None and source.is_manual_repair() and not leere_kurve_erlaubt:
            logger.info(
                f"Anlage {anlage.id}, {datum}: Leistungskurve ohne Wert "
                "(HA-Verlauf vermutlich gepurgt) — Werkbank versucht die Langzeitstatistik"
            )
            return None
        if await _tag_hat_geraetewerte(anlage, datum, db):
            logger.info(
                f"Anlage {anlage.id}, {datum}: Leistungskurve ohne Wert (HA-Verlauf vermutlich "
                "gepurgt) — gespeicherte Gerätewerte bleiben stehen, Tag nicht neu geschrieben"
            )
            return None

    return serien, punkte_raw, vortagsrand_raw, synthetische_slots


def bucket_nach_slot(
    punkte_raw: list, vortagsrand_raw: list, synthetische_slots: bool,
) -> dict:
    """Sub-stündliche Punkte auf BACKWARD-Slots bucketen (N-382)."""
    #
    # SoT: `core/berechnungen/slot_konvention.py` — **Slot h = Energie
    # [h-1, h)**, Slot 0 = [Vortag 23:00, 00:00). Der Leistungspfad
    # beschriftet seine Punkte mit dem Slot-BEGINN (`live_tagesverlauf_service`
    # nennt das Raster wörtlich `h_start <= p < h_end`), ein Punkt „05:00"
    # deckt also [05:00, 06:00) und gehört damit in **Slot 6**.
    #
    # ⛔ Bis 2026-09-04 landete er in Slot 5 — dieselbe Zeile trug damit im
    # JSON `[h, h+1)` und in ihren Spalten (Zählerpfad) `[h-1, h)`, also zwei
    # verschiedene Stunden. Über 24 Slots hebt sich das auf, weshalb
    # Tagessummen, Monat und ROI unauffällig blieben; pro Stunde nicht:
    # `TagVerlaufChart` subtrahierte quer über den Versatz und zeichnete daraus
    # ein Phantom-Band „PV (übrige)" bzw. — auf steigender Kurve — einen
    # Quellenstapel ÜBER der Erzeugung (BMeyendriesch, #405). An einer echten
    # Anlage mit EINEM PV-Erzeuger gemessen: 5,09 kWh Überhang an einem Tag.
    #
    # Zwei Kanten gehören dazu:
    #  • Slot 0 kommt aus dem VORTAG (`vortagsrand_raw`). Fehlt er, bleibt der
    #    Slot ohne `komponenten` — die Zeile wird trotzdem geschrieben, sonst
    #    verlöre sie auch ihre Zähler- und Wetterwerte.
    #  • Bucket 23 des Tages ([23:00, 24:00)) gehört in Slot 0 des FOLGETAGS
    #    und fällt hier weg — er kommt dort über dessen `vortagsrand` an.
    stunden_buckets: dict[int, list[dict]] = {}
    if synthetische_slots:
        # MQTT-Energie ohne Leistungskurve: 24 leere Slots, damit die Schleife
        # 24× läuft und die Zähler-Werte ihre Zeile bekommen. Hier wird nichts
        # verschoben — es gibt keine Leistungspunkte, die eine Stunde meinen.
        stunden_buckets = {h: [] for h in range(24)}
    else:
        for p in vortagsrand_raw:
            stunden_buckets.setdefault(0, []).append(p)
        for p in punkte_raw:
            slot = leistungspfad_slot(int(p["zeit"].split(":")[0]))
            if slot is None:
                continue          # gehört in Slot 0 des Folgetags
            stunden_buckets.setdefault(slot, []).append(p)
        # Slot 0 existiert auch ohne Vortagsrand — als leerer Bucket. Ohne ihn
        # schriebe die Schleife die Zeile 0 gar nicht, und mit ihr fielen
        # `pv_kw`, Wetter und Preis dieser Stunde aus (sie kommen NICHT aus dem
        # Leistungspfad und wären unschuldig mitbetroffen).
        if stunden_buckets and 0 not in stunden_buckets:
            stunden_buckets[0] = []

    return stunden_buckets


def ergaenze_zaehlerslots(punkte: list, kwh_pro_stunde: Optional[dict]) -> list:
    """Zählerlücken wie HA (Vorlage §10, O1 → Option A): **jeder Slot mit
    Zählerwert bekommt eine Stundenzeile**, auch ohne Leistungspunkt.

    Die Stunden-Schleife lief bisher nur über die Slots des Leistungspfads. Hatte
    die Leistungskurve eine Lücke, der Zähler aber einen Wert (typisch: das
    Bündel nach einer HA-Lücke, R2), fehlte die Zeile — die Energie stand im
    Tageswert (`komponenten_kwh`), aber in keiner Stunde, und G1 (Σ Stunden =
    Tag) hielt in den Zeilen nicht (Lab Anlage 902, 06.11.2025: 4,0 kWh
    Netzbezug im Tag, 0 in den Stunden). Der ergänzte Punkt trägt leere
    ``werte`` ⇒ keine Leistungs-`komponenten`, keine Spitze; die kWh-Spalten
    kommen wie in jeder Zeile aus `kwh_pro_stunde`.
    """
    if not kwh_pro_stunde:
        return punkte
    vorhanden = {int(p["zeit"].split(":")[0]) for p in punkte}
    neu = [
        {"zeit": f"{h:02d}:00", "werte": {}}
        for h, werte in kwh_pro_stunde.items()
        if 0 <= h <= 23 and h not in vorhanden
        and any(v is not None for k, v in (werte or {}).items() if k != "spannen")
    ]
    if not neu:
        return punkte
    return sorted(punkte + neu, key=lambda p: int(p["zeit"].split(":")[0]))


def mittel_je_stunde(stunden_buckets: dict) -> list:
    """Je Slot den Mittelwert jedes Schluessels — das Ergebnis sind die 24 Stundenpunkte."""
    punkte = []
    for h in sorted(stunden_buckets):
        bucket = stunden_buckets[h]
        alle_keys = {k for p in bucket for k in p.get("werte", {})}
        gemittelt: dict[str, float] = {}
        for k in alle_keys:
            vals = [p["werte"][k] for p in bucket if k in p.get("werte", {})]
            if vals:
                gemittelt[k] = sum(vals) / len(vals)
        punkte.append({"zeit": f"{h:02d}:00", "werte": gemittelt})

    return punkte


async def lade_stammdaten(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
    serien: list,
    sensor_mapping: dict,
) -> tuple:
    """Serien-Kategorien indexieren und die fuenf Stammdaten-Quellen holen.

    Returns:
        ``(pv_keys, netz_keys, sonderschluessel, wetter_stunden, soc_je_stunde,
        soc_stunden, betriebsmodus_je_stunde, strompreis_stunden)``
    """
    from backend.services.energie_profil._helpers import (
        _get_betriebsmodus_history,
        _get_soc_history,
        _get_strompreis_stunden,
        _get_wetter_ist,
    )

    # Serien-Kategorien indexieren (vorzeichenbasiert, zukunftssicher)
    pv_keys = {s["key"] for s in serien if s["kategorie"] == "pv"}
    batterie_keys = {s["key"] for s in serien if s["kategorie"] == "batterie"}
    # ⛔ Hier stand bis 2026-08-29 ein `v2h_keys`-Set plus eine Ausnahme
    # `and not s["key"].startswith("v2h_")` in `wallbox_keys` — beides ein
    # TOTER ZWEIG (F-69): Der Präfix `v2h_` wird nirgends erzeugt und wurde es
    # nie. Beide Zeilen waren wirkungslos, weil ein V2H-Auto die Kategorie
    # `eauto` trägt und über `wallbox_keys` ohnehin schon in
    # `_sonderschluessel` landet. Ersatzlos gestrichen, statt eine Konvention
    # zu behaupten, die es nicht gibt.
    #
    # ⚠ Die Tages-Ebene kennt V2H damit weiterhin NICHT — das ist die in #110
    # geführte, bewusst zurückgestellte Zeile „V2H-Lücken schließen" und wird
    # hier nicht nebenbei gebaut.
    netz_keys = {s["key"] for s in serien if s["kategorie"] == "netz"}
    wp_keys = {s["key"] for s in serien if s["kategorie"] == "waermepumpe"}
    wallbox_keys = {s["key"] for s in serien
                    if s["kategorie"] in ("wallbox", "eauto")}
    sonstige_keys = {s["key"] for s in serien if s["kategorie"] == "sonstige"}
    # Alle Schlüssel die separat behandelt werden (nicht in generischer Summe)
    # "strompreis" und "haushalt" sind keine Energieflüsse und dürfen nicht in pv_kw/verbrauch_kw einfließen
    _sonderschluessel = batterie_keys | netz_keys | pv_keys | wp_keys | wallbox_keys | sonstige_keys | {"strompreis", "haushalt"}

    # ── PV-Module für GTI-Gruppierung holen (Issue #139) ──────────────────
    # Nur am `datum` aktive Module — sonst verzerrt ein erst später
    # angeschafftes oder schon stillgelegtes Modul die GTI-Referenz und damit
    # die Performance Ratio (v3.34.2 Phase B: aktiv_am_tag-Schnitt, Audit §6.4;
    # zuvor lud aggregate_day ALLE Module, der Vollbackfill filterte sie per Tag).
    pv_module_result = await db.execute(
        select(Investition).where(
            and_(
                Investition.anlage_id == anlage.id,
                Investition.typ.in_(("pv-module", "balkonkraftwerk")),
                aktiv_am_tag(datum),
            )
        )
    )
    pv_module_list = list(pv_module_result.scalars().all())

    # ── Wetter-IST-Daten holen (inkl. GTI für PR-Berechnung) ──────────────
    wetter_stunden = await _get_wetter_ist(anlage, datum, pv_module=pv_module_list)

    # ── SoC-History holen ─────────────────────────────────────────────────
    # N-239: `{stunde: {investition_id: soc}}` — JEDES Gerät, nicht nur das
    # erste. Der Anlagenwert entsteht darunter kapazitätsgewichtet.
    soc_je_stunde = await _get_soc_history(anlage, sensor_mapping, datum, db)
    speicher_kapazitaeten = {
        inv.id: get_speicher_nutzbare_kapazitaet_kwh(inv)
        for inv in await _speicher_investitionen(db, anlage.id)
    }
    soc_stunden = {
        h: wert
        for h, je_geraet in soc_je_stunde.items()
        if (wert := anlagen_soc_prozent(je_geraet, speicher_kapazitaeten)) is not None
    }

    # ── Betriebsmodus je Wärmepumpe holen (#263 K-2) ──────────────────────
    # `{stunde: {investition_id: "heizen"|...}}`. Leer, solange kein Anwender
    # einen Modus-Sensor zugeordnet hat — das Feld ist optional, und ohne es
    # bleibt alles unverändert (die Menge steht weiter in `komponenten`).
    #
    # ⚠ Hier und NICHT im Snapshot-Job: Der 5-Minuten-Snapshot steht hinter
    # `LIVE_SNAPSHOT_5MIN_ENABLED` (Default aus, `run.sh`) und liest HA
    # short_term_statistics — dort existiert ein `climate`-Zustand nicht. Die
    # `:05`/`:55`-Jobs wiederum schreiben `sensor_snapshots` (kumulative
    # kWh-Zählerstände), nicht diese Tabelle. Der Modus gehört dorthin, wo die
    # Stundenmenge entsteht, und das ist diese Funktion — genau wie beim SoC.
    betriebsmodus_je_stunde = await _get_betriebsmodus_history(
        anlage, sensor_mapping, datum, db
    )

    # ── Strompreis-Stundenwerte holen ─────────────────────────────────────
    strompreis_stunden = await _get_strompreis_stunden(anlage, sensor_mapping, datum)

    return (
        pv_keys, netz_keys, _sonderschluessel, wetter_stunden,
        soc_je_stunde, soc_stunden, betriebsmodus_je_stunde, strompreis_stunden,
    )


async def lade_zaehler_und_counter(
    anlage: Anlage, datum: date, db: AsyncSession,
) -> tuple:
    """Zaehler-kWh je Stunde (HA-LTS mit Snapshot-Fallback) und die Stunden-Counter.

    Returns:
        ``(invs, invs_by_id, kwh_pro_stunde, kwh_source_label, wp_starts_pro_stunde,
        wp_betriebsstunden_pro_stunde, komponenten_starts, tages_tabelle)`` —
        ``tages_tabelle`` ist die `TagesTabelle` des HA- bzw. Snapshot-Pfads
        (dieselbe Rechnung, `snapshot/tages_tabelle.py`) oder ``None``.
    """
    # ── Zähler-basierte Stunden-kWh (Issue #135 / Etappe 4 v3.31.0) ──────
    # Etappe 4: HA-Statistics-LTS ist Source-of-Truth, wenn verfügbar
    # (HA-Add-on oder Docker mit HA-Recorder-URL). Snapshot-Variante bleibt
    # als Standalone-Fallback (MQTT-Energy-Snapshots).
    # Provenance-Source wird je nach Pfad gesetzt (siehe seed_*_provenance
    # unten) — `external:ha_statistics:hourly` vs `auto:monatsabschluss`.
    kwh_pro_stunde: dict[int, dict[str, Optional[float]]] = {}
    kwh_source_label: str  # für seed_*_provenance
    # Nur am `datum` aktive Investitionen — Per-Tag-Aktiv-Filter (v3.34.2
    # Phase B, Audit §6.4). Vorher lud aggregate_day ALLE Investitionen der
    # Anlage; für historische Tage mit zwischenzeitlich stillgelegter
    # Investition wich das vom Vollbackfill-Pfad (`aktiv_im_zeitraum`) ab.
    # `aktiv_am_tag` ist die per-Tag-Variante und prüft auch das `aktiv`-Flag
    # (aktiv=False = wie gelöscht → nirgends, auch historisch, bis reaktiviert;
    # Gernot 2026-06-05). Bereits aggregierte Tage einer danach deaktivierten
    # Komponente per Werkbank neu rechnen, damit sie aus den Tagessummen fallen.
    # Für den Scheduler (heute/gestern) praktisch ein No-Op: am laufenden Tag
    # aktive Investitionen erfüllen den Filter ohnehin.
    inv_result = await db.execute(
        select(Investition).where(
            and_(
                Investition.anlage_id == anlage.id,
                aktiv_am_tag(datum),
            )
        )
    )
    invs = inv_result.scalars().all()
    invs_by_id = {str(inv.id): inv for inv in invs}
    # ⭐ Zählerlücken wie HA (R5): EIN HA-Lesezugriff je Tag — die Slot-Tabelle
    # trägt die Stundenachsen, `komponenten_kwh` (Σ derselben Werte) und die
    # verworfenen Mengen. Bis zum Umbau las `komponenten_tagesgesamt_und_peaks`
    # HA ein zweites Mal über `get_komponenten_tageskwh_lts`.
    lts_tabelle = None
    # N-555 Stufe 3 (Konzept 7.2 Anhang D, D-6): die Heimlade-Zähler je Auto werden im
    # SELBEN Lesezugriff mitgelesen (`zusatz_slots`) — kein zweiter HA-Zugriff. Die
    # Rechnung der Tabelle sieht sie nicht; der Ladeblock-Hook in `aggregate_day` liest sie.
    from backend.services import emob_ladebloecke_speicher as _ladebloecke
    try:
        from backend.services.snapshot import lts_aggregator
        # Ohne Fahrzeug-Zähler ruft der Aggregator die Tabelle genau wie vorher auf.
        _zusatz_lts = _ladebloecke.fahrzeug_zaehler_lts(anlage, invs_by_id, datum)
        lts_tabelle = await lts_aggregator.lts_tagestabelle(
            anlage, invs_by_id, datum,
            **({"zusatz_schluessel": _zusatz_lts} if _zusatz_lts else {}),
        )
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: HA-LTS-Pfad fehlgeschlagen: "
            f"{type(e).__name__}: {e}"
        )
        lts_tabelle = None
    kwh_pro_stunde = lts_tabelle.stunden if lts_tabelle is not None else {}

    if kwh_pro_stunde:
        kwh_source_label = "external:ha_statistics:hourly"
        tages_tabelle = lts_tabelle
    else:
        # Fallback auf Snapshot-Variante (MQTT-/sensor_snapshots-Pfad).
        # Gleicher Output-Vertrag — nur die Quelle ändert sich. Seit
        # „Zählerlücken wie HA" liefert auch sie die ganze Tagestabelle
        # (Stunden, `komponenten_kwh` im Stundenfenster, verworfene Mengen — E5).
        tages_tabelle = None
        try:
            from backend.services.snapshot import aggregator as snapshot_aggregator
            try:
                _zusatz_snap = {
                    k: v[1] for k, v in (await _ladebloecke.fahrzeug_zaehler_snapshot(
                        db, anlage, invs_by_id, datum,
                    )).items()
                }
            except Exception:
                _zusatz_snap = {}  # ohne Fahrzeug-Zähler rechnet der Tag wie vorher
            tages_tabelle = await snapshot_aggregator.snapshot_tagestabelle(
                db, anlage, invs_by_id, datum,
                **({"zusatz_schluessel": _zusatz_snap} if _zusatz_snap else {}),
            )
        except Exception as e:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Snapshot-Fallback fehlgeschlagen: "
                f"{type(e).__name__}: {e}"
            )
            tages_tabelle = None
        kwh_pro_stunde = tages_tabelle.stunden if tages_tabelle is not None else {}
        kwh_source_label = "auto:monatsabschluss"

    # ── Stunden-Counter (Issue #136/#238: WP-Starts + Betriebsstunden pro Stunde) ──
    wp_starts_pro_stunde: dict[int, Optional[int]] = {}
    wp_betriebsstunden_pro_stunde: dict[int, Optional[float]] = {}
    try:
        from backend.services.sensor_snapshot_service import get_hourly_counter_sum_by_feld
        wp_starts_pro_stunde = await get_hourly_counter_sum_by_feld(
            db, anlage, invs_by_id, datum, "wp_starts_anzahl",
        )
        wp_betriebsstunden_pro_stunde = await get_hourly_counter_sum_by_feld(
            db, anlage, invs_by_id, datum, "wp_betriebsstunden",
        )
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: WP-Counter-Stunden-Aggregation fehlgeschlagen: "
            f"{type(e).__name__}: {e}"
        )

    # ── Counter-Tagesdifferenzen (Issue #136: WP-Kompressor-Starts) ──────
    # Boundary-Diff über das Tagesfenster. Wird hier — vor der Stunden-Schleife —
    # geholt, weil die Stunden-Σ aus diesem Tageswert ABGELEITET wird (Counter-
    # Daily-Drift Variante 2-light, KONZEPT-COUNTER-DAILY-DRIFT.md): eine Quelle
    # pro Tag. {feld: {inv_id: wert}}, z.B. {"wp_starts_anzahl": {"5": 12}}.
    komponenten_starts: dict = {}
    try:
        from backend.services.sensor_snapshot_service import get_daily_counter_deltas_by_inv
        komponenten_starts = await get_daily_counter_deltas_by_inv(
            db, anlage, invs_by_id, datum,
        )
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: Counter-Aggregation fehlgeschlagen: "
            f"{type(e).__name__}: {e}"
        )

    # Stunden-Σ aus dem Boundary-Diff ableiten (SoT pro Tag). Bei sauberen
    # Snapshots verhaltensneutral; bei NULL-Slots/Lücken wird die Stunden-Σ so
    # reskaliert, dass Σ_h == Σ_inv komponenten_starts gilt. Nur wenn der
    # Boundary-Diff für das Feld einen Wert lieferte — sonst bleibt die
    # eigenständig gerechnete Stunden-Σ als Fallback erhalten (kein Datenverlust,
    # wenn ausgerechnet die Tages-Boundary-Snapshots fehlen).
    from backend.core.berechnungen import verteile_counter_auf_stunden

    def _counter_aus_boundary(feld: str, stunden: dict, *, as_float: bool) -> dict:
        je_inv = komponenten_starts.get(feld)
        if not je_inv:
            return stunden
        return verteile_counter_auf_stunden(
            stunden, float(sum(je_inv.values())), as_float=as_float
        )

    wp_starts_pro_stunde = _counter_aus_boundary(
        "wp_starts_anzahl", wp_starts_pro_stunde, as_float=False
    )
    wp_betriebsstunden_pro_stunde = _counter_aus_boundary(
        "wp_betriebsstunden", wp_betriebsstunden_pro_stunde, as_float=True
    )

    return (
        invs, invs_by_id, kwh_pro_stunde, kwh_source_label,
        wp_starts_pro_stunde, wp_betriebsstunden_pro_stunde, komponenten_starts,
        tages_tabelle,
    )


@dataclass
class GerettetStunden:
    """Was die alten Stundenzeilen eines Tages vor dem Delete trugen (N-595, S2).

    ``je_feld`` = ``{feld: {slot: wert}}`` für die Felder aus
    ``_STUNDEN_FELDER_RETTEN``, bereits auf den **Ziel-Slot** des neu geschriebenen
    Tages gelegt (Betriebsart über ``betriebsmodus_ziel_slot``, die übrigen
    zeilengleich). ``herkunft`` = ``{(slot, feld): alter_eintrag | None}``.
    """
    je_feld: dict = field(default_factory=dict)
    herkunft: dict = field(default_factory=dict)

    def _slots(self, feld: str) -> dict:
        return self.je_feld.get(feld, {})

    @property
    def modus_je_slot(self) -> dict:
        return self._slots("betriebsmodus_je_wp")

    @property
    def soc_je_slot(self) -> dict:
        return self._slots("soc_prozent")

    @property
    def soc_je_speicher_je_slot(self) -> dict:
        return self._slots("soc_je_speicher")

    @property
    def preis_je_slot(self) -> dict:
        return self._slots("strompreis_cent")


def _alter_provenance_eintrag(provenance, feld: str) -> Optional[dict]:
    """Der alte Eintrag eines Feldes — nur, wenn seine Quelle bekannt ist (#299-Regel)."""
    eintrag = (provenance or {}).get(feld) if isinstance(provenance, dict) else None
    if isinstance(eintrag, dict) and eintrag.get("source") in SOURCE_LABELS:
        return dict(eintrag)
    return None


async def lese_gerettete_stunden(
    anlage: Anlage, datum: date, db: AsyncSession,
) -> GerettetStunden:
    """Die Stundenfelder lesen, deren Quelle verfällt — VOR dem Delete (N-595, S2).

    Gelesen werden die Zeilen des Tages und **Zeile 23 des Vortags**. Letztere nur für
    die Betriebsart und nur, wenn sie noch **forward** liegt (Altbestand vor N-382):
    dann meint sie ``[23, 24)`` des Vortags = Slot 0 dieses Tages. Eine backward
    liegende Zeile 23 des Vortags meint ``[22, 23)`` und gehört nicht hierher —
    ``betriebsmodus_ziel_slot`` legt sie auf den Vortag, und der wird verworfen.

    Für einen Ziel-Slot, auf den sowohl die Vortagszeile 23 (forward) als auch die
    eigene Zeile 0 (backward) zeigen — beide meinen ``[Vortag 23, 00)`` —, gewinnt
    die eigene Zeile: sie gehört zu diesem Tag und ist die jüngere Messung.

    Nur Spalten-Projektion, keine ORM-Objekte: die Zeilen werden gleich danach
    gelöscht und sollen nicht in der Identity-Map stehen.

    ⚠ **Bekannte Grenze, gemessen (N-595-Bau, 02.10.2026):** Ein Bereichslauf
    (``backfill_range``, aufsteigend) schreibt Zeile 23 von Tag D neu, bevor Tag D+1
    sie liest. Liegt sie forward (``created_at`` 19.08.–03.09., Forward-Ära der
    Betriebsart), fehlt Tag D+1 danach die Betriebsart in **Slot 0** — eine Stunde je
    Tag ab dem zweiten des Bereichs, höchstens die 16 Tage dieser Ära. Hingenommen
    und benannt: ein Schreiben über die Tagesgrenze oder ein absteigender Lauf
    kostete mehr, als die eine Stunde wert ist.
    """
    from backend.core.berechnungen.slot_konvention import betriebsmodus_ziel_slot

    tep = TagesEnergieProfil
    spalten = [getattr(tep, f) for f in _STUNDEN_FELDER_RETTEN]
    ergebnis = await db.execute(
        select(
            tep.datum, tep.stunde, tep.created_at, tep.source_provenance, *spalten,
        ).where(
            tep.anlage_id == anlage.id,
            (tep.datum == datum)
            | ((tep.datum == datum - timedelta(days=1)) & (tep.stunde == 23)),
        )
    )
    # Vortag zuerst, damit die eigene Zeile denselben Ziel-Slot überschreibt.
    zeilen = sorted(ergebnis.all(), key=lambda z: (z.datum, z.stunde))

    gerettet = GerettetStunden()
    for zeile in zeilen:
        for feld in _STUNDEN_FELDER_RETTEN:
            wert = getattr(zeile, feld)
            if wert is None or wert == {}:
                continue
            if feld == "betriebsmodus_je_wp":
                ziel = betriebsmodus_ziel_slot(zeile)
            elif zeile.datum == datum:
                ziel = (zeile.datum, zeile.stunde)   # forward bleibt forward (N-387)
            else:
                ziel = None                          # Vortag nur für die Betriebsart
            if ziel is None or ziel[0] != datum:
                continue
            slot = ziel[1]
            gerettet.je_feld.setdefault(feld, {})[slot] = wert
            gerettet.herkunft[(slot, feld)] = _alter_provenance_eintrag(
                zeile.source_provenance, feld,
            )
    return gerettet


def fuehre_gerettete_stunden_zusammen(
    gerettet: GerettetStunden,
    *,
    betriebsmodus_je_stunde: dict,
    soc_je_stunde: dict,
    soc_stunden: dict,
    strompreis_stunden,
    invs_by_id: dict,
) -> tuple:
    """Rettung und neuer Lauf zusammenführen — **die Quelle gewinnt, wo sie liefert** (N-595, S3).

    * Betriebsart je Slot **je Wärmepumpe**: ``{**alt, **neu}`` — liefert der
      Verlauf nur für ein Gerät, bleibt das andere stehen (Entscheid Gernot
      02.10.: die Betriebsart ist eine Messung der Vergangenheit und bleibt auch
      ohne Zuordnung stehen). Alte Schlüssel nur für Geräte, die an diesem Tag
      noch als ``waermepumpe`` in der Anlage stehen (``invs_by_id``) — keine
      Waisen einer gelöschten Wärmepumpe.
    * SoC (Anlagenwert + je Speicher) als **Paar**, Endkundenpreis allein: nur für
      Slots, in denen der neue Lauf **nichts** hat.
    * ``boerse`` bleibt unberührt.

    Gibt neue Dicts zurück und verändert die Eingänge nicht. Ein Slot, zu dem die
    Rettung nichts beiträgt, behält das Objekt des neuen Laufs.

    Returns:
        ``(betriebsmodus_je_stunde, soc_je_stunde, soc_stunden, strompreis_stunden,
        gerettete_herkunft)`` — ``gerettete_herkunft`` = ``{slot: {feld: eintrag}}``
        nur für Felder, die **ganz** aus der Rettung stammen. Ein gemischter
        Betriebsart-Eintrag (neu + alt) trägt das Label des Laufs.
    """
    from backend.services.energie_profil._helpers import StrompreisStunden

    herkunft: dict[int, dict] = {}

    def _merke(slot: int, feld: str) -> None:
        herkunft.setdefault(slot, {})[feld] = gerettet.herkunft.get((slot, feld))

    # ── Betriebsart ─────────────────────────────────────────────────────────
    wp_ids = {
        iid for iid, inv in invs_by_id.items()
        if (getattr(inv, "typ", None) or "") == "waermepumpe"
    }
    modus = dict(betriebsmodus_je_stunde)
    for slot, alt in gerettet.modus_je_slot.items():
        # Schlüsseltyp angleichen: der Kontext führt die Investitions-ID als int,
        # die Spalte als str.
        alt_gueltig = {
            int(k): v for k, v in (alt or {}).items()
            if str(k).isdigit() and str(k) in wp_ids
        }
        if not alt_gueltig:
            continue
        neu = modus.get(slot) or {}
        zusammen = {**alt_gueltig, **{_inv_schluessel(k): v for k, v in neu.items()}}
        if zusammen == neu:
            continue
        modus[slot] = zusammen
        if not neu:
            _merke(slot, "betriebsmodus_je_wp")

    # ── SoC (Paar) ──────────────────────────────────────────────────────────
    soc_je = dict(soc_je_stunde)
    soc = dict(soc_stunden)
    for slot in set(gerettet.soc_je_slot) | set(gerettet.soc_je_speicher_je_slot):
        if soc_je.get(slot) or soc.get(slot) is not None:
            continue                                  # der neue Lauf hat den Slot
        alt_soc = gerettet.soc_je_slot.get(slot)
        if alt_soc is not None:
            soc[slot] = alt_soc
            _merke(slot, "soc_prozent")
        alt_je = gerettet.soc_je_speicher_je_slot.get(slot)
        if alt_je:
            soc_je[slot] = {_inv_schluessel(k): v for k, v in alt_je.items()}
            _merke(slot, "soc_je_speicher")

    # ── Endkundenpreis (Sensor) — Börse nie ─────────────────────────────────
    sensor = dict(strompreis_stunden.sensor)
    for slot, alt_preis in gerettet.preis_je_slot.items():
        if slot in sensor or alt_preis is None:
            continue
        sensor[slot] = alt_preis
        _merke(slot, "strompreis_cent")
    if sensor != strompreis_stunden.sensor:
        strompreis_stunden = StrompreisStunden(
            sensor=sensor, boerse=strompreis_stunden.boerse,
        )

    return modus, soc_je, soc, strompreis_stunden, herkunft


def _inv_schluessel(k):
    """Investitions-ID als int, wo sie eine ist — die Konvention der Kontext-Dicts
    (``_get_betriebsmodus_history`` / ``_get_soc_history`` führen int, die Spalten str)."""
    return int(k) if isinstance(k, str) and k.isdigit() else k


async def rette_und_loesche(
    anlage: Anlage, datum: date, db: AsyncSession,
) -> tuple:
    """Extern befuellte Felder retten, dann Delete-and-Recreate der beiden Tageszeilen.

    ⚠ EIN Schreibpfad: Rettung und Delete gehoeren zusammen und duerfen nicht getrennt
    werden — zwischen beiden darf nichts stehen, was die alte Zeile noch liest.

    Returns:
        ``(preserved_felder, preserved_quellen, preserved_komponenten_kwh,
        preserved_komponenten_starts, gerettet_stunden)`` — der fuenfte Wert (N-595)
        traegt die Stundenfelder aus ``_STUNDEN_FELDER_RETTEN``.
    """
    # N-595: die Stundenzeilen VOR dem Delete lesen (Rettung + Delete = ein Pfad).
    gerettet_stunden = await lese_gerettete_stunden(anlage, datum, db)

    # ── Alte Daten für diesen Tag löschen (Upsert) ────────────────────────
    # Extern befüllte Felder vor dem Delete-and-Recreate retten — sie werden
    # nicht vom Aggregator gesetzt, sondern asynchron/additiv von anderen
    # Schreibern: Prognose-Felder vom Wetter-Endpoint (_PROGNOSE_FELDER_RETTEN),
    # Kraftstoffpreis vom kraftstoff_preis_service (_EXTERN_BEFUELLT_FELDER_RETTEN,
    # #319). Ohne Rettung gingen sie bei jedem Recreate verloren (#190-Klasse).
    existing_tz = await db.execute(
        select(TagesZusammenfassung).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum == datum,
            )
        )
    )
    existing_tz_row = existing_tz.scalar_one_or_none()
    preserved_felder = {}
    # #299: pro gerettetem Feld die Ursprungsquelle aus der alten Row-Provenance
    # mitnehmen, damit der Restore-Schreiber unten das Audit-Log mit der echten
    # Herkunft (external:openmeteo / external:fuel_price / …) statt mit einem
    # generischen Aggregator-Label füllt. Wert hier einfrieren, bevor der
    # Delete-and-Recreate die alte Row aus der Session entfernt.
    preserved_quellen: dict[str, str] = {}
    # #290 detLAN: bei manueller Reaggregation ohne Stunden-Daten retten wir
    # zusätzlich Komponenten-Aggregate, damit bestehende gute Werte nicht
    # durch eine evtl. falsche Snapshot-Boundary-Diff überschrieben werden
    # (Beispiel: HA-LTS nicht erreichbar + alte Snapshots in DB inkonsistent
    # → Boundary-Diff liefert Müll, Σ-Hourly liefert 0).
    preserved_komponenten_kwh = (
        dict(existing_tz_row.komponenten_kwh)
        if existing_tz_row and existing_tz_row.komponenten_kwh else None
    )
    preserved_komponenten_starts = (
        dict(existing_tz_row.komponenten_starts)
        if existing_tz_row and existing_tz_row.komponenten_starts else None
    )
    if existing_tz_row:
        alte_provenance = existing_tz_row.source_provenance or {}
        for field in (*_PROGNOSE_FELDER_RETTEN, *_EXTERN_BEFUELLT_FELDER_RETTEN):
            val = getattr(existing_tz_row, field, None)
            if val is not None:
                preserved_felder[field] = val
                quelle = (alte_provenance.get(field) or {}).get("source")
                if quelle in SOURCE_LABELS:
                    preserved_quellen[field] = quelle

    await db.execute(
        delete(TagesEnergieProfil).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == datum,
            )
        )
    )
    await db.execute(
        delete(TagesZusammenfassung).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum == datum,
            )
        )
    )

    return (
        preserved_felder, preserved_quellen,
        preserved_komponenten_kwh, preserved_komponenten_starts,
        gerettet_stunden,
    )


async def schreibe_provenance_und_restore(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
    zusammenfassung: TagesZusammenfassung,
    *,
    auto_writer: str,
    tz_source_label: str,
    lade_anteil,
    pv_marken: dict,
    preserved_felder: dict,
    preserved_quellen: dict,
) -> None:
    """Provenance saeen, danach die geretteten Felder zurueckschreiben.

    ⛔ Die Reihenfolge ist tragend (#299): ``seed_tz_provenance`` laeuft VOR dem Restore,
    damit ``write_with_provenance`` je gerettetem Feld die echte Ursprungsquelle statt des
    Aggregator-Labels eintraegt. Wer die beiden Bloecke tauscht, dreht das um.
    """
    from backend.services.provenance import (
        ABGELEITET_EINSPEISE_DECKUNG,
        ABGELEITET_EINSPEISE_DECKUNG_TEILWEISE,
    )

    db.add(zusammenfassung)
    # Die beiden Ladeanteils-Spalten tragen eine eigene Herkunfts-Marke: der
    # Source-Tag beschreibt den LAUF (HA-LTS/Snapshot), die Marke die HERKUNFT
    # der Zahl. Ohne sie sähe eine Schätzung aus wie eine Messung — und war
    # nicht jede Ladestunde gedeckt, sagt die Marke auch das (P4).
    abgeleitet_marken: dict[str, str] = {}
    if lade_anteil is not None:
        marke = (
            ABGELEITET_EINSPEISE_DECKUNG
            if lade_anteil.vollstaendig
            else ABGELEITET_EINSPEISE_DECKUNG_TEILWEISE
        )
        abgeleitet_marken["emob_ladung_pv_abgeleitet_kwh"] = marke
        abgeleitet_marken["emob_ladung_netz_abgeleitet_kwh"] = marke
    seed_tz_provenance(
        zusammenfassung,
        writer=auto_writer,
        source=tz_source_label,
        abgeleitet_je_feld=abgeleitet_marken or None,
        # #406: je `komponenten_kwh`-Sub-Key, wo der Wert aus dem Anlagen-
        # Aggregat zerlegt wurde statt gemessen zu sein.
        abgeleitet_je_subkey=pv_marken or None,
    )

    # Gerettete extern-befüllte Felder wiederherstellen (Prognose + Kraftstoffpreis).
    # #299: bewusst NACH seed_tz_provenance und über write_with_provenance statt
    # per setattr — so entsteht ein Audit-Log-Eintrag pro Restore und die
    # Provenance trägt die echte Ursprungsquelle statt des Aggregator-Labels.
    # Die Felder sind beim Seed noch None (frische Row → der Seed-Loop überspringt
    # sie), also greift hier kein Hierarchie-Konflikt; der Restore wird angewandt.
    for field, val in preserved_felder.items():
        restore_source = preserved_quellen.get(field, "auto:preserve_restore")
        ergebnis = await write_with_provenance(
            db, zusammenfassung, field, val,
            source=restore_source, writer="aggregator-preserve",
        )
        if not ergebnis.applied:
            # Darf nicht passieren (frische Row, existing=None) — wenn doch,
            # ginge der gerettete Wert still verloren. Sichtbar machen statt
            # schlucken (feedback_silent_except_logs).
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Restore von '{field}' "
                f"nicht angewandt ({ergebnis.decision}: {ergebnis.reason}) — "
                f"geretteter Wert ginge verloren."
            )
            setattr(zusammenfassung, field, val)



async def _boerse_vortag_23(db, anlage_id: int, datum: date) -> Optional[float]:
    """Boersenpreis der Forward-Stunde 23 des Vortags — der Preis zu Slot 0 (N-387).

    Slot 0 des Tages traegt die Einspeisung von ``[Vortag 23:00, 00:00)``; ihr
    Preis steht in der **Zeile 23 des Vortags** (``boersenpreis_cent``, forward).
    Dieselbe Zeile, die ``ha_export_bezugspreis._boerse_slot_null`` fuer die
    Bezugspreis-Reihe liest — dort ueber ``preis_tag.persistierte_preise``.

    Eine fehlende Vortagszeile ist der Normalfall am ersten Tag einer Anlage und
    kein Fehler: Slot 0 bleibt dann unbewertet, statt den Preis der falschen
    Stunde zu nehmen.
    """
    from backend.models.tages_energie_profil import TagesEnergieProfil as _TEP

    res = await db.execute(
        select(_TEP.boersenpreis_cent).where(
            _TEP.anlage_id == anlage_id,
            _TEP.datum == datum - timedelta(days=1),
            _TEP.stunde == 23,
        )
    )
    return res.scalar_one_or_none()


def tages_kennzahlen(
    anlage: Anlage, datum: date, invs, akku: TagesAkkumulator, strompreis_stunden,
    boerse_vortag_23: Optional[float] = None,
) -> tuple:
    """Boersenpreis-Tagesaggregation (§51 EEG), Batterie-Vollzyklen, Performance Ratio.

    Args:
        boerse_vortag_23: Boersenpreis der **forward**-Stunde 23 des Vortags —
            der Preis, der zur Einspeisung des Backward-Slots 0 gehoert
            (s. §51 unten). ``None``, wenn der Vortag keine Zeile hat.

    Returns:
        ``(boersenpreis_avg, boersenpreis_min, neg_stunden, einsp_neg_kwh, vollzyklen,
        performance_ratio)``
    """
    # ── Börsenpreis-Tagesaggregation ────────────────────────────────────
    # ⚠ Diese drei Kennzahlen beschreiben den **Preistag** `[00:00, 24:00)` und
    # werden deshalb NICHT verschoben: `boerse` liegt forward, die Stunden 0..23
    # sind genau der Kalendertag. Verschieben hieße, den Tages-Ø über
    # `[Vortag 23, 23)` zu bilden — eine andere Aussage.
    boersen_values = [v for v in (strompreis_stunden.boerse.get(h) for h in range(24)) if v is not None]
    boersenpreis_avg = round(sum(boersen_values) / len(boersen_values), 2) if boersen_values else None
    boersenpreis_min = round(min(boersen_values), 2) if boersen_values else None
    neg_stunden = sum(1 for v in boersen_values if v < 0) if boersen_values else None

    # Einspeisung bei negativem Börsenpreis (§51 EEG)
    #
    # ⭐ **N-387: hier wird gepaart, also wird umgerechnet.** `einspeisung_pro_stunde[h]`
    # ist die Energie des Backward-Slots `[h-1, h)`; `boerse[h]` ist der Preis der
    # Forward-Stunde `[h, h+1)`. Zusammen gehören Slot `h` und Preis `h-1` —
    # dieselbe Verschiebung wie in `slot_konvention.forward_werte_je_backward_zeile`,
    # hier nur auf einem Stunden-Dict statt auf Zeilen. Für Slot 0 liefert der
    # Aufrufer die Stunde 23 des Vortags nach; fehlt sie, bleibt Slot 0 außen vor
    # (keine stille Nachbar-Übernahme).
    #
    # ⚠ **Ohne Bestandsgrenze — und das ist hier richtig.** Der Zeilen-Helfer
    # prüft je Zeile an ihrer `created_at`, ob sie schon die Backward-Mengen
    # trägt (`SLOT_PAARUNG_VORZEILE_AB`, für Zeilen vor dem 04.06.2026 gilt die
    # Zeilen-Paarung). Diese Stelle rechnet dagegen **während** der Aggregation
    # auf Stunden-Dicts: die Zeilen, die zu dieser Zahl gehören, entstehen im
    # selben Lauf und tragen damit **immer** die heutige Konvention. Ein
    # Alt-Wert kann hier gar nicht auftreten — er steckt allenfalls in einer
    # **persistierten** `einspeisung_neg_preis_kwh` von früher, und die wird
    # nicht umgerechnet, sondern beim Neu-Aggregieren des Tages neu gebildet
    # (derselbe Reparaturweg, den CHANGELOG und BERECHNUNGEN nennen).
    einsp_neg = 0.0
    for h in range(24):
        bp = boerse_vortag_23 if h == 0 else strompreis_stunden.boerse.get(h - 1)
        if bp is not None and bp < 0:
            einsp_neg += akku.einspeisung_pro_stunde.get(h, 0.0)
    einsp_neg_kwh = round(einsp_neg, 3) if einsp_neg > 0 else None

    # ── Batterie-Vollzyklen berechnen ─────────────────────────────────────
    vollzyklen = None
    if len(akku.soc_values) >= 2:
        delta_sum = sum(abs(akku.soc_values[i] - akku.soc_values[i - 1])
                        for i in range(1, len(akku.soc_values)))
        # Ein Vollzyklus = ΔSoC von 100% (0→100→0 = 200% ΔSoC → 1 Zyklus)
        vollzyklen = round(delta_sum / 200.0, 2)

    # ── Performance Ratio ─────────────────────────────────────────────────
    # Referenz-Einstrahlung: GTI (modul-gewichtet) statt horizontaler GHI.
    # Bei steilen Modulen + tiefstehender Wintersonne ist GTI bis 3× höher
    # als GHI — mit GHI liefen PR-Werte im Winter künstlich auf 1.5–2.8
    # (Issue #139). Ohne GTI (keine PV-Module, API-Fehler) bleibt PR = None
    # statt einen physikalisch unsinnigen Wert zu liefern.
    # Zweiter Fall derselben Regel: ohne EINE gemessene PV-Stunde ist der
    # Zähler dieses Bruchs kein Ertrag, sondern eine Lücke — die PR liefe sonst
    # auf 0,0 und der Daten-Checker meldete „auffällig niedrig" für eine Anlage,
    # die schlicht keinen PV-Zähler je Erzeuger hat (Forum kaba-kakao 2026-08-07).
    # F-58: Nenner ist die Σ der an DIESEM Tag aktiven Erzeuger. Der gepflegte
    # `Anlage.leistung_kwp` ist ein zeitloser Skalar — er kennt weder Zubau noch
    # Stilllegung, und seit dem Wegfall des Summenvergleichs (N-76 Stufe 1) hielt
    # ihn nichts mehr gegen die Investitionen. Eine zu kleine kWp macht den
    # Nenner zu klein und die PR zu groß; genau das meldet der Daten-Checker
    # dann als Doppelerfassungs-Verdacht.
    # Die Formel selbst lebt im Layer (`core/berechnungen/performance_ratio.py`),
    # weil der Wetter-Nachzug für den Altbestand (N-388) sie ohne Neu-
    # Aggregation braucht — dieselbe Rechnung an zwei Orten wäre Drift.
    kwp = anlagen_kwp(
        invs, datum, mit_bkw=True, referenzwert=anlage.leistung_kwp,
    )
    performance_ratio = berechne_performance_ratio(
        akku.pv_ertrag_summe if akku.pv_ertrag_erfasst else None, akku.gti_summe, kwp,
    )

    return (
        boersenpreis_avg, boersenpreis_min, neg_stunden, einsp_neg_kwh,
        vollzyklen, performance_ratio,
    )


async def komponenten_tagesgesamt_und_peaks(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
    invs_by_id: dict,
    kwh_source_label: str,
    akku: TagesAkkumulator,
    tages_tabelle=None,
) -> dict:
    """Tagesgesamt je Komponente (HA-LTS -> Snapshot-Fallback) und der Peak-Override aus HA-LTS.

    ⛔ Beide Bloecke ueberschreiben Werte, die die Stunden-Schleife gefuellt hat, und die
    Reihenfolge ist die Praezedenz: Boundary-Diff gewinnt ueber die Live-Σ, HA-LTS-Min/Max
    gewinnt ueber die W-Integration. Wer einen der beiden vor die Schleife zieht, dreht sie um.

    Returns:
        ``pv_marken`` — die #406-Herkunftsmarken je ``komponenten_kwh``-Sub-Key.
    """
    # Counter-Tagesdifferenzen (`komponenten_starts`) wurden bereits vor der
    # Stunden-Schleife geholt — die Stunden-Σ wird daraus abgeleitet (Counter-
    # Daily-Drift Variante 2-light). Hier nur noch weiterverwenden.

    # ── Tagesgesamt pro Komponente (Etappe 3c P3 + Etappe 4 v3.31.0) ─────
    # Etappe 4: wenn der Stunden-Pfad aus HA-LTS gespeist wurde, nutzen wir
    # auch für die Tages-Komponenten-Summe den HA-LTS-Pfad — damit gilt
    # Σ Hourly == Daily per Konstruktion und die Drift zwischen
    # TagesEnergieProfil.*_kw und TagesZusammenfassung.komponenten_kwh
    # verschwindet (Rainer-PN 2026-05-16).
    # Fallback: Snapshot-Boundary-Diff (HA-konformes Tagesfenster).
    # Live-Σ aus der Stunden-Schleife (Riemann) bleibt nur für Keys, die
    # weder LTS noch Snapshot abdecken — z.B. WP-Suffix-Keys aus dem
    # Tagesverlauf-Service ohne separates Counter-Mapping.
    #
    # Zukunfts-Tage (datum > today): SKIP bleibt — keine sinnvolle
    # Aggregation möglich, weder LTS noch Snapshot haben Daten.
    #
    # Heutiger Tag (datum == today): seit B-clean v3.34.1 erlaubt für den
    # LTS-Pfad (Audit §5.1.1 / MartyBr #620 simon42). Hintergrund: bis v3.34.0
    # war der SKIP auf `datum >= today` formuliert und bildete im HA-Add-on
    # zusammen mit vier weiteren Schutzmaßnahmen einen Dead-Spot —
    # komponenten_kwh war strukturell None für den laufenden Tag, 641 Drift-
    # Warnings/Tag im Daten-Checker. Die ursprüngliche Begründung (Self-
    # Healing aus HA-history liefert für `snap[Folgetag 00:00]` den AKTUELLEN
    # Counter-Stand statt sauberen Tagesgrenz-Wert) trifft NUR die Snapshot-
    # Variante `get_komponenten_tageskwh` (Boundary-Diff `snap[Folgetag 00:00]
    # - snap[Tag 00:00]`). Die LTS-Variante `get_komponenten_tageskwh_lts`
    # ist slot-basiert: sie ruft `get_hourly_kwh_deltas_for_day` auf, das
    # pro Stunden-Slot `boundary[h+1] - boundary[h]` aus HA-Statistics-Rows
    # berechnet und für noch nicht geschriebene Boundaries `None` liefert.
    # `get_komponenten_tageskwh_lts` summiert dann nur die valide-Slots —
    # für `datum == today` ergibt sich eine saubere Teilsumme der schon
    # abgelaufenen Stunden, kein Self-Heal-Inflationsrisiko. Edge-Case
    # 00:05-Scheduler: noch keine Stunde des neuen Tages vorhanden →
    # leeres Dict → komponenten_kwh = None (unverändertes Verhalten).
    #
    # Vier andere Schutzmaßnahmen aus Audit §5.1.1 bewusst UNANGETASTET:
    #   1. BKW-Bug-Fix Live-Σ-Bypass (Z. 403) — schützt vor BKW-Schema-
    #      Mismatch-Doppelzählung (Rainer-PN 2026-05-19).
    #   2. Snapshot-Fallback bleibt an `datum < today` gekoppelt (Z. 531) —
    #      #290 Bug B Schutz für die Snapshot-Variante bleibt aktiv.
    #   3. `live_snapshot_if_missing` im HA-Add-on deaktiviert (#184).
    #   4. LTS-Statistics-Lag (Stunde verfügbar ~5 min nach voller Stunde).
    #
    # #290 Bug A (Symptompatch v3.32.4, mit v3.33.0 OBSOLET): der frühere
    # generische Skip bei `datenquelle == "manuell"` war eine Notbremse
    # gegen den LTS-Aggregator-Drift — Boundary-Diff lieferte buggy Werte
    # (alle Sensoren einer Investition aufsummiert). Mit dem strukturellen
    # Fix in `services.snapshot.komponenten_beitraege` liefert Boundary-Diff
    # jetzt die korrekten Per-Typ-Werte. Skip entfernt, damit die
    # Reparatur-Werkbank ihren eigentlichen Zweck erfüllt: User klickt
    # "Tag neu aggregieren" → komponenten_kwh wird aktualisiert.
    # Schutz für die seltene Konstellation "HA-LTS weg + Snapshots korrupt"
    # bleibt über die preserve-Logik unten (greift wenn boundary leer).
    boundary_kwh: dict[str, float] = {}
    # #406: die Herkunfts-Marken der PV-Auflösung. Ein Erzeuger ohne eigenen
    # Tageswert bekommt seinen kWp-Anteil am Aggregat — der Wert ist dann eine
    # ZERLEGUNG, keine Messung, und muss das in `source_provenance` sagen
    # (dieselbe Marke wie im Monatspfad, #352).
    pv_marken: dict[str, str] = {}
    if datum > date.today():
        logger.debug(
            f"Anlage {anlage.id}, {datum}: Boundary-Diff übersprungen für "
            f"Zukunfts-Tag — keine Daten verfügbar."
        )
    elif tages_tabelle is not None and (
        kwh_source_label == "external:ha_statistics:hourly" or datum < date.today()
    ):
        # Zählerlücken wie HA (R5b/E5): Σ der in den Stunden verwendeten
        # Gerätewerte aus DERSELBEN Tagestabelle — kein zweiter Lesezugriff, und
        # im Snapshot-Pfad dasselbe Stundenfenster wie im HA-Pfad. Der
        # Snapshot-Pfad bleibt an `datum < heute` gekoppelt (#290 Bug B).
        boundary_kwh = dict(tages_tabelle.komponenten_kwh)
        pv_marken.update(tages_tabelle.pv_marken)
    if not boundary_kwh and datum < date.today() and kwh_source_label == "external:ha_statistics:hourly":
        # HA-Stunden da, aber kein Tageswert (z. B. PV-Aggregat ohne Erzeuger-
        # Investition): Rückfall auf die Snapshot-Tabelle — ebenfalls im
        # Stundenfenster, damit die Regelmarke dieser Zeile stimmt (E5).
        try:
            from backend.services.snapshot import aggregator as snapshot_aggregator
            snap = await snapshot_aggregator.snapshot_tagestabelle(db, anlage, invs_by_id, datum)
            if snap is not None:
                boundary_kwh = dict(snap.komponenten_kwh)
                pv_marken.update(snap.pv_marken)
        except Exception as e:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Komponenten-Tagesgesamt aus Snapshots "
                f"fehlgeschlagen, Σ-Hourly-Fallback aktiv: {type(e).__name__}: {e}"
            )
    for key, val in boundary_kwh.items():
        akku.komponenten_summen[key] = val
    # N-625: liefert die Zählertabelle die PV-Achse des Tages, stehen in
    # `komponenten_kwh` NUR ihre PV-Keys. Ohne HA-Stundenwerte summiert
    # `summiere_live_komponenten` die Leistungs-Serien der Kurve als kWh — die
    # Gesamtleistung `pv_gesamt`, aber auch eine Einzel-Serie `pv_<bkw>` neben dem
    # Zähler-Key `bkw_<bkw>`; das Überschreiben oben trifft nur gleiche Keys, der Rest
    # blieb daneben stehen und `lade_monats_summen_aus_tagen` zählte ihn mit (laufender
    # Monat 126 statt 63). Die Stundenachse kommt nur aus Zählern (Σ Stunden == Σ Keys);
    # eine Leistungs-Serie, die die Zähler nicht kennen, ist dort keine Erzeugung,
    # sondern eine zweite Fassung derselben. Ohne PV-Key der Zählertabelle bleibt
    # alles wie bisher (reine Leistungs-Anlage).
    if any(str(k).startswith(PV_KOMPONENTEN_PREFIXE) for k in boundary_kwh):
        for key in [k for k in akku.komponenten_summen
                    if str(k).startswith(PV_KOMPONENTEN_PREFIXE) and k not in boundary_kwh]:
            del akku.komponenten_summen[key]

    # ── Peak-Werte aus HA-LTS-Min/Max (Etappe 5 v3.31.0) ─────────────────
    # HA-Recorder schreibt für has_mean=True-Sensoren die im 5-Sekunden-Bucket
    # beobachteten Extremwerte pro Stunde. Das ist die richtige Quelle für
    # Tages-Peaks — die Berechnung aus 10-Min-Mittelwerten unterschätzt sie
    # systematisch. Fallback bleibt die Tagesverlauf-Berechnung oben.
    try:
        from backend.services.energie_profil._helpers import _get_tagespeaks_aus_ha_lts
        lts_peaks = await _get_tagespeaks_aus_ha_lts(anlage, datum, db)
        if lts_peaks.pv is not None:
            akku.peak_pv = lts_peaks.pv
        if lts_peaks.netzbezug is not None:
            akku.peak_bezug = lts_peaks.netzbezug
        if lts_peaks.einspeisung is not None:
            akku.peak_einspeisung = lts_peaks.einspeisung
    except Exception as e:
        logger.debug(f"Peak-HA-LTS-Override für {datum}: {e}")

    return pv_marken


def baue_zusammenfassung(
    anlage: Anlage,
    datum: date,
    akku: TagesAkkumulator,
    *,
    source: Source,
    kwh_source_label: str,
    komponenten_starts: dict,
    preserved_komponenten_kwh,
    preserved_komponenten_starts,
    boersenpreis_avg,
    boersenpreis_min,
    neg_stunden,
    einsp_neg_kwh,
    vollzyklen,
    performance_ratio,
    verworfen: Optional[dict] = None,
    nachtrag: Optional[dict] = None,
) -> tuple:
    """PV-Anteil der Heimladung ableiten, die Tageszeile bauen, das TZ-Quell-Label bestimmen.

    ``verworfen``: die verworfenen Mengen des Laufs (R4). ⭐ Die Tageszeile
    bekommt **immer** mindestens ``{}`` — das ist die Regelmarke (R9): sie
    sagt jedem Leser, dass dieser Tag nach „Zählerlücken wie HA" gerechnet ist.
    NULL trägt nur der Altbestand. ``nachtrag``: die Stunden, die nur dank des
    Deckel-Fensters passiert sind (N-567) — ``None``, wenn es keine gab.

    Returns:
        ``(zusammenfassung, lade_anteil, tz_source_label)``
    """
    # ── PV-Anteil der Heimladung ableiten (N-141 Weg c) ───────────────────
    # Eine Wallbox misst ihren PV-Anteil nicht; ohne evcc gab es dafür bisher
    # gar keine Quelle, und der Leser setzte ihn auf 0 — die ganze Heimladung
    # galt als Netzstrom. SoT der Regel: `core/berechnungen/pv_anteil_ladung.py`
    # (Regel „Einspeise-Deckung", am 2026-08-08 gegen evcc vermessen: −3,2 pp).
    #
    # `None` heißt „keine Aussage" und bleibt None — daraus 0 kWh PV zu machen
    # wäre genau die Behauptung, die dieser Fund auflöst. Der Wert ist eine
    # SCHÄTZUNG; die Provenance trägt Regel und Deckungsgrad, damit eine
    # Teilsumme sich als solche zu erkennen gibt (P4).
    from backend.core.berechnungen.pv_anteil_ladung import leite_pv_anteil_ab

    lade_anteil = leite_pv_anteil_ab(akku.lade_stunden)

    # ── TagesZusammenfassung speichern ────────────────────────────────────
    zusammenfassung = TagesZusammenfassung(
        anlage_id=anlage.id,
        datum=datum,
        ueberschuss_kwh=nur_positiv(akku.tages_ueberschuss, 2),
        defizit_kwh=nur_positiv(akku.tages_defizit, 2),
        peak_pv_kw=nur_positiv(akku.peak_pv, 2),
        peak_netzbezug_kw=nur_positiv(akku.peak_bezug, 2),
        peak_einspeisung_kw=nur_positiv(akku.peak_einspeisung, 2),
        batterie_vollzyklen=vollzyklen,
        temperatur_min_c=round(min(akku.temp_values), 1) if akku.temp_values else None,
        temperatur_max_c=round(max(akku.temp_values), 1) if akku.temp_values else None,
        strahlung_summe_wh_m2=nur_positiv(akku.strahlung_summe, 0),
        # N-384: der NENNER der Performance Ratio, damit sie nachrechenbar wird. Er
        # wurde hier schon immer gebildet (s. `akku.gti_summe` oben) — nur nie gespeichert,
        # während daneben die horizontale `akku.strahlung_summe` angezeigt wurde. `None`
        # statt 0, wenn es keine gab: 0 wäre eine Behauptung, NULL ist eine Lücke.
        gti_summe_wh_m2=nur_positiv(akku.gti_summe, 0),
        performance_ratio=performance_ratio,
        stunden_verfuegbar=akku.stunden_count,
        datenquelle=source.to_db_string(),
        boersenpreis_avg_cent=boersenpreis_avg,
        boersenpreis_min_cent=boersenpreis_min,
        negative_preis_stunden=neg_stunden,
        einspeisung_neg_preis_kwh=einsp_neg_kwh,
        # Zählerlücken wie HA (R4 + R9): nie NULL aus diesem Schreiber.
        verworfen=dict(verworfen or {}),
        # N-567: benannt, nicht abgezogen — die Menge steht in den Stunden wie in HA.
        nachtrag=dict(nachtrag) if nachtrag else None,
        emob_ladung_pv_abgeleitet_kwh=(
            lade_anteil.pv_kwh if lade_anteil is not None else None
        ),
        emob_ladung_netz_abgeleitet_kwh=(
            lade_anteil.netz_kwh if lade_anteil is not None else None
        ),
        # N-569-Ergänzung: davon aus dem Speicher (Teilmenge, nur Ausweis).
        emob_ladung_speicher_abgeleitet_kwh=(
            lade_anteil.speicher_kwh if lade_anteil is not None else None
        ),
        # Preserve-Logik nur bei manueller Reaggregation — Pattern-Adaption
        # v3.32.4 (#290, Audit §4.2). Ursprung: Monatsdaten-Kontext, wo
        # manuell editierte Werte vor Scheduler-Überschreibung geschützt
        # werden. In TZ gibt es keine manuelle Werteingabe; „manuell"
        # bedeutet hier „Werkbank-Trigger" (Source.MANUAL_REPAIR). Der Schutz
        # greift GENAU im else-Zweig unten, d. h. wenn `akku.komponenten_summen`
        # LEER ist (Σ-Hourly = 0, boundary leer) — ein versehentlicher
        # Werkbank-Klick bei nicht erreichbarem HA-LTS + fehlenden/korrupten
        # Snapshots würde sonst die alten korrekten Werte mit None
        # überschreiben. (NICHT geschützt: „Boundary-Diff liefert Müll" — Müll
        # ist nicht-leer, landet also im if-Zweig; dieses Szenario ist seit
        # v3.33.0 ohnehin strukturell entschärft, Per-Typ statt Alle-Sensoren-
        # Summe.) Der Scheduler ist absichtlich NICHT geschützt: ein legitim
        # leerer Tag (Sensor-Ausfall, Offline-Phase) soll nicht ewig die alte
        # Wahrheit weitertragen.
        #
        # Preserve-Asymmetrie-Prüfung (#318-Begleitung, 2026-06-03): geprüft, ob
        # das v3.33.0-Snapshot-Self-Healing den Schutz überflüssig macht —
        # ERGEBNIS: nein. Die Self-Healing-Kaskade in `reader.get_snapshot`
        # (DB → HA-Statistics → MQTT) heilt Stufe 2 NUR bei `ha_svc.is_available`;
        # in genau der geschützten Konstellation (HA unerreichbar) fällt sie aus
        # → ohne Preserve permanenter komponenten_kwh-Verlust eines Alttags.
        # Bekannte Grenze: der Schutz ist partiell (nur komponenten_kwh/_starts,
        # nicht ueberschuss/defizit/Peaks). Sauberere Lösung wäre, dass die
        # Werkbank quellenlose Tage überspringt statt zu überschreiben — eigener
        # Schnitt, bewusst nicht hier.
        #
        # ⛔ Hier stand bis 2026-09-04 zusätzlich „und für historische Tage läuft
        # der Scheduler nie nach". **Das gilt seit N-388 nicht mehr:**
        # `services/energie_profil/archiv_nachzug.py` lässt den Scheduler
        # nächtlich genau EINEN historischen Tag neu aggregieren — den, der die
        # Wetter-Archiv-Grenze gerade passiert hat. Der Satz war die Begründung
        # dafür, dass der Scheduler hier ungeschützt bleibt; er trägt sie nicht
        # mehr. Ersetzt ist er **nicht** durch ein Preserve für den Scheduler
        # (ein legitim leerer Tag soll weiterhin nicht ewig die alte Wahrheit
        # weitertragen), sondern durch den **Vorflug** dort: der Nachzug
        # überspringt einen Tag, dessen HA-Historie inzwischen weniger Stunden
        # deckt als die gespeicherte `stunden_verfuegbar`. Wer diesen
        # Preserve-Zweig ändert, liest den Vorflug mit.
        komponenten_kwh=(
            {k: round(v, 2) for k, v in akku.komponenten_summen.items()}
            if akku.komponenten_summen
            else (
                preserved_komponenten_kwh
                if source.is_manual_repair()
                else None
            )
        ),
        komponenten_starts=(
            komponenten_starts
            or (
                preserved_komponenten_starts
                if source.is_manual_repair()
                else None
            )
        ),
    )

    # Transienter Marker (nicht gemappt, nicht persistiert): hatte DIESER Lauf
    # frische Komponenten-Werte, oder stehen im Feld die alten aus der
    # Preserve-Logik oben? Der Unterschied ist von außen sonst nicht sichtbar —
    # in beiden Fällen trägt `komponenten_kwh` dieselben Keys. Die Tages-
    # Reparatur braucht ihn, um „geschrieben" nicht für einen Lauf zu behaupten,
    # der nur den Bestand stehen ließ (N-58, Forum simon42 #89667/83).
    zusammenfassung.komponenten_frisch = bool(akku.komponenten_summen)

    # Etappe 4: TagesZusammenfassung-Source spiegelt die Hauptquelle der
    # Daily-Werte. Wenn die Stunden aus HA-LTS kamen, ist auch die
    # Tagessumme aus HA-LTS-Daten konsistent (Σ Hourly = Daily).
    # N-434: Die Kennung ist eine geteilte Konstante — die Tagessichten lesen an
    # ihr ab, in welchem Fenster `komponenten_kwh` steht (Σ der LTS-Slots ⇒
    # [Vortag 23:00, 23:00)). Ein Literal hier und eines dort wäre F-56.
    from backend.services.snapshot.boundary_range import TZ_QUELLE_LTS
    tz_source_label = (
        TZ_QUELLE_LTS
        if kwh_source_label == "external:ha_statistics:hourly"
        else "auto:monatsabschluss"
    )
    return zusammenfassung, lade_anteil, tz_source_label


async def pruefe_invarianten(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
    zusammenfassung: TagesZusammenfassung,
    invs_by_id: dict,
) -> None:
    """``flush`` und die vier Pflicht-Invarianten (ADR-001 Berechnungs-Layer).

    Der ``flush`` gehoert hierher: die Invarianten lesen die eben geschriebenen
    ``TagesEnergieProfil``-Zeilen aus der Session zurueck, und dafuer muessen sie
    persistiert sein. Alle vier Pruefungen loggen nur — **kein Tag wird zurueckgehalten**,
    Drift soll sichtbar werden statt Daten zu kosten.
    """
    await db.flush()

    # Pflicht-Invariante (ADR-001 Berechnungs-Layer):
    # Σ pv_kw aus der Stunden-Schleife muss mit Σ PV+BKW aus dem
    # Tages-JSON übereinstimmen. Seit v3.33.0 (Issue #290) auf alle
    # Komponenten-Kategorien erweitert (WP, Wallbox+E-Auto, Batterie,
    # Basis-Einspeisung/-Netzbezug) — Drift bleibt nicht mehr unentdeckt.
    # Wir loggen Warning + speichern trotzdem — Drift soll sichtbar werden,
    # aber kein Tag soll wegen einer Invariante verloren gehen.
    from backend.core.berechnungen import (
        pruefe_tep_komponenten_intern_konsistenz,
        pruefe_tep_tz_komponenten_konsistenz,
        pruefe_tep_tz_konsistenz,
    )

    # TagesEnergieProfil-Rows aus der aktuellen Session ziehen (db.add wurde
    # in der Stunden-Schleife aufgerufen, db.flush hat sie persistiert).
    tep_rows_result = await db.execute(
        select(TagesEnergieProfil).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == datum,
            )
        )
    )
    tep_rows = tep_rows_result.scalars().all()
    invariante = pruefe_tep_tz_konsistenz(
        tep_rows, zusammenfassung.komponenten_kwh,
    )
    if not invariante.konsistent:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: Berechnungs-Layer-Invariante "
            f"verletzt — {invariante}"
        )
    for bericht in pruefe_tep_tz_komponenten_konsistenz(
        tep_rows, zusammenfassung.komponenten_kwh,
    ):
        if not bericht.konsistent:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Komponenten-Drift — {bericht}"
            )
    # Achse 2 (#315): Leistungspfad (TEP.komponenten-JSON) vs Zählerpfad
    # (TEP.*_kw-Spalten) derselben Stunden. Im HA-LTS-Modus ist das die einzige
    # Prüfung des Leistungs-JSON; im Standalone redundant zur TZ-Prüfung oben.
    # Warning-level — Step-Integrations-Drift sichtbar machen, kein Tag-Verlust.
    #
    # ⭐ Beide Seiten müssen dieselbe Grundgesamtheit führen (N-187): der
    # Leistungspfad kennt auch Geräte OHNE kWh-Zähler, der Zählerpfad nicht.
    # Ohne diese Einschränkung meldete ein E-Auto mit Leistungs-, aber ohne
    # Zählersensor Tag für Tag eine „Drift", die exakt seine eigene Σ war
    # (an Anlage 1 gemessen, 06.08.: 17,323 von 17,323). Die Menge kommt aus
    # der Zuordnung dieses Tages — demselben SoT, den Daten-Checker und
    # Tages-Reparatur benutzen.
    from backend.services.snapshot.komponenten_beitraege import (
        erwartete_komponenten_keys,
    )

    zaehler_gedeckte_keys = set(erwartete_komponenten_keys(
        anlage.sensor_mapping or {}, invs_by_id, datum,
    ))
    for bericht in pruefe_tep_komponenten_intern_konsistenz(
        tep_rows, zaehler_gedeckte_keys,
    ):
        if not bericht.konsistent:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Achse-2-Komponenten-Drift — {bericht}"
            )
        elif bericht.details:
            # Zählerlücken wie HA: toleriert, aber sichtbar (Log-Hinweis).
            logger.info(f"Anlage {anlage.id}, {datum}: {bericht}")

    # Counter-Daily-Drift (Variante 2-light, KONZEPT-COUNTER-DAILY-DRIFT.md):
    # Σ_h TagesEnergieProfil.<feld> muss dem Tages-Boundary-Diff
    # (TagesZusammenfassung.komponenten_starts) entsprechen. Die Stunden-Σ wird
    # oben aus dem Boundary-Diff abgeleitet — diese Invariante macht eine
    # verbleibende Drift sichtbar (analog kWh-Pfad, ADR-001). Warning, kein
    # Tag-Verlust.
    from backend.core.berechnungen import pruefe_counter_konsistent

    for feld in ("wp_starts_anzahl", "wp_betriebsstunden"):
        je_inv = (zusammenfassung.komponenten_starts or {}).get(feld)
        if not je_inv:
            continue
        stunden_map = {r.stunde: getattr(r, feld, None) for r in tep_rows}
        bericht = pruefe_counter_konsistent(
            stunden_map, float(sum(je_inv.values())),
            name=f"counter:{feld}", toleranz=0.5,
        )
        if not bericht.konsistent:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Counter-Drift — {bericht}"
            )



async def aggregate_day(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
    *,
    source: Source,
    prefetched_tagesverlauf: Optional[dict] = None,
    leere_kurve_erlaubt: bool = False,
    nur_mit_verlauf: bool = False,
) -> Optional[TagesZusammenfassung]:
    """
    Aggregiert Energiedaten eines Tages und speichert sie persistent.

    1. Holt Tagesverlauf-Daten (stündliche Butterfly-Daten)
    2. Holt Wetter-IST-Daten (Temperatur, Strahlung)
    3. Holt Batterie-SoC History
    4. Speichert 24 TagesEnergieProfil-Zeilen
    5. Berechnet + speichert TagesZusammenfassung

    Args:
        anlage: Die Anlage
        datum: Tag für den aggregiert wird
        db: DB-Session
        source: Trigger-Quelle dieses Aufrufs (Source-Enum, v3.34.0 Phase A).
            Steuert: (a) ``datenquelle``-Spaltenwert, (b) Provenance-Writer-
            Suffix, (c) Preserve-Logik bei manueller Reaggregation. Pflicht-
            Keyword-Parameter — kein Default, alle Aufrufer setzen ihn
            explizit (Audit §8.12, Plan v3.34 §3 Phase A E4).
        prefetched_tagesverlauf: Optionale vorgeholte Tagesverlauf-Daten in
            der ``get_tagesverlauf``-Form (``{"serien": [...], "punkte":
            [{"zeit", "werte"}]}``) für GENAU diesen Tag. Gesetzt vom
            Vollbackfill-Pfad (``backfill_from_statistics``, v3.34.2 Phase B),
            der die historischen Stunden-Leistungen gebündelt aus HA-LTS holt
            (`get_hourly_sensor_data` einmal pro Range) — `get_tagesverlauf`
            reicht nur ~10 Tage zurück, deshalb braucht der Backfill die
            Durchreichung. Wenn gesetzt, wird `get_tagesverlauf` NICHT
            aufgerufen; die kategorisierten Stunden-kWh, Boundary-kWh, Peaks,
            Strompreise usw. kommen weiterhin aus den regulären
            `aggregate_day`-Quellen (HA-LTS bevorzugt). Plan v3.34 §3 B.1 +
            B.3 (Pflicht-Mitigation gegen Per-Tag-Bulk-Read-Verlust).
            (Der Plan-Text nennt `dict[date, dict]`; da `aggregate_day`
            per-Tag arbeitet, wird die Per-Tag-Form übergeben — der Caller
            schleift über die Range.)
        leere_kurve_erlaubt: Nur für die Werkbank nach einem leeren LTS-Rückfall (N-596).
            Trägt die Leistungskurve keinen Wert, steigt ein ``MANUAL_REPAIR``-Lauf sonst
            immer aus (damit der Rückfall zuerst versucht wird); mit ``True`` gilt für ihn
            dieselbe Regel wie für alle anderen Aufrufer: Tag mit gespeicherten
            Gerätewerten bleibt stehen, Tag ohne wird aus den Zählern geschrieben.
        nur_mit_verlauf: HA-Bauform E4f, nur für den Monatsabschluss-Nachlauf (fehlende Tage):
            trägt die Leistungskurve keinen Wert — der Tag liegt außerhalb der
            Recorder-Aufbewahrung —, wird nichts geschrieben (``None``), auch nicht aus den
            Zählern (s. ``hole_tagesverlauf``).

    Returns:
        TagesZusammenfassung oder ``None`` — bei Fehler, ohne Quelle (F-26) oder wenn eine Kurve
        ohne Leistungswert den Tag stehen lässt (N-596, s. ``hole_tagesverlauf``).
    """
    # Provenance-Writer codiert die Trigger-Quelle (Scheduler / Monatsabschluss /
    # manuelles Reaggregate / Vollbackfill). Source bleibt einheitlich
    # `auto:monatsabschluss` (Stufe 3) — siehe seed_tz_provenance / seed_tep_provenance.
    auto_writer = source.to_writer()

    sensor_mapping = anlage.sensor_mapping or {}

    rohdaten = await hole_tagesverlauf(
        anlage, datum, db, prefetched_tagesverlauf,
        source=source, leere_kurve_erlaubt=leere_kurve_erlaubt,
        nur_mit_verlauf=nur_mit_verlauf,
    )
    if rohdaten is None:
        return None
    serien, punkte_raw, vortagsrand_raw, synthetische_slots = rohdaten

    stunden_buckets = bucket_nach_slot(punkte_raw, vortagsrand_raw, synthetische_slots)
    punkte = mittel_je_stunde(stunden_buckets)

    (
        pv_keys, netz_keys, _sonderschluessel, wetter_stunden,
        soc_je_stunde, soc_stunden, betriebsmodus_je_stunde, strompreis_stunden,
    ) = await lade_stammdaten(anlage, datum, db, serien, sensor_mapping)
    # HA-Bauform E1: die Betriebsart, wie die Quelle sie liefert — VOR der Rettung (N-595) unten,
    # damit die Kanal-Mitschrift nie einen geretteten Altwert als Messung übernimmt.
    betriebsmodus_aus_quelle = betriebsmodus_je_stunde

    (
        invs, invs_by_id, kwh_pro_stunde, kwh_source_label,
        wp_starts_pro_stunde, wp_betriebsstunden_pro_stunde, komponenten_starts,
        tages_tabelle,
    ) = await lade_zaehler_und_counter(anlage, datum, db)

    # ── N-555 Stufe 3: Ladeblöcke (Konzept 7.2 Regel 9, Anhang D) ──────────
    # Direkt nach der Slot-Tabelle des Tages: Blöcke der Sprünge an D bilden und in
    # `emob_ladebloecke` ersetzen (idempotent je Tag, P9). Die Stunden und Tage dieser
    # Aggregation berührt der Hook nicht; scheitert er, bleibt der Tag gerechnet und die
    # Monate rechnen nach Stufe 2 (W-C: ohne Blöcke kein Stufe-3-Wert).
    try:
        from backend.services.emob_ladebloecke_speicher import aktualisiere_ladebloecke_des_tages
        await aktualisiere_ladebloecke_des_tages(
            db, anlage, datum, invs_by_id, tages_tabelle, kwh_source_label,
        )
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: Ladeblöcke (N-555 Stufe 3) nicht gebildet: "
            f"{type(e).__name__}: {e}"
        )

    (
        preserved_felder, preserved_quellen,
        preserved_komponenten_kwh, preserved_komponenten_starts,
        gerettet_stunden,
    ) = await rette_und_loesche(anlage, datum, db)

    # O1 (Vorlage §10): Slots mit Zählerwert, aber ohne Leistungspunkt.
    punkte = ergaenze_zaehlerslots(punkte, kwh_pro_stunde)

    # ── N-595 (#422): gerettete Stundenfelder zusammenführen ──────────────
    # VOR dem Kontext, damit jeder Leser (Stundenzeile, Vollzyklen über
    # `akku.soc_values`) dieselben Werte sieht. Die Quelle gewinnt, wo sie
    # liefert; eine Zeile entsteht nur für Slots aus `punkte` — die Rettung
    # erfindet keine.
    (
        betriebsmodus_je_stunde, soc_je_stunde, soc_stunden, strompreis_stunden,
        gerettete_herkunft,
    ) = fuehre_gerettete_stunden_zusammen(
        gerettet_stunden,
        betriebsmodus_je_stunde=betriebsmodus_je_stunde,
        soc_je_stunde=soc_je_stunde,
        soc_stunden=soc_stunden,
        strompreis_stunden=strompreis_stunden,
        invs_by_id=invs_by_id,
    )

    # ── Stundenwerte berechnen + speichern ────────────────────────────────
    akku = TagesAkkumulator()
    kontext = StundenKontext(
        anlage=anlage,
        datum=datum,
        netz_keys=netz_keys,
        pv_keys=pv_keys,
        sonderschluessel=_sonderschluessel,
        kwh_pro_stunde=kwh_pro_stunde,
        kwh_source_label=kwh_source_label,
        wetter_stunden=wetter_stunden,
        soc_stunden=soc_stunden,
        soc_je_stunde=soc_je_stunde,
        betriebsmodus_je_stunde=betriebsmodus_je_stunde,
        strompreis_stunden=strompreis_stunden,
        wp_starts_pro_stunde=wp_starts_pro_stunde,
        wp_betriebsstunden_pro_stunde=wp_betriebsstunden_pro_stunde,
        gerettete_herkunft=gerettete_herkunft,
    )

    for punkt in punkte:
        verarbeite_stunde(punkt, kontext, akku, db, auto_writer)

    (
        boersenpreis_avg, boersenpreis_min, neg_stunden, einsp_neg_kwh,
        vollzyklen, performance_ratio,
    ) = tages_kennzahlen(
        anlage, datum, invs, akku, strompreis_stunden,
        await _boerse_vortag_23(db, anlage.id, datum),
    )

    pv_marken = await komponenten_tagesgesamt_und_peaks(
        anlage, datum, db, invs_by_id, kwh_source_label, akku, tages_tabelle,
    )

    zusammenfassung, lade_anteil, tz_source_label = baue_zusammenfassung(
        anlage, datum, akku,
        source=source,
        kwh_source_label=kwh_source_label,
        komponenten_starts=komponenten_starts,
        preserved_komponenten_kwh=preserved_komponenten_kwh,
        preserved_komponenten_starts=preserved_komponenten_starts,
        boersenpreis_avg=boersenpreis_avg,
        boersenpreis_min=boersenpreis_min,
        neg_stunden=neg_stunden,
        einsp_neg_kwh=einsp_neg_kwh,
        vollzyklen=vollzyklen,
        performance_ratio=performance_ratio,
        verworfen=(tages_tabelle.verworfen if tages_tabelle is not None else {}),
        nachtrag=(tages_tabelle.nachtrag if tages_tabelle is not None else None),
    )

    await schreibe_provenance_und_restore(
        anlage, datum, db, zusammenfassung,
        auto_writer=auto_writer,
        tz_source_label=tz_source_label,
        lade_anteil=lade_anteil,
        pv_marken=pv_marken,
        preserved_felder=preserved_felder,
        preserved_quellen=preserved_quellen,
    )

    await pruefe_invarianten(anlage, datum, db, zusammenfassung, invs_by_id)

    # HA-Bauform E1: Betriebsart-Mitschrift („Anteil der Stunde je Betriebsart") — NACH dem
    # Bestand, in derselben Sitzung, eigener SAVEPOINT; ein Fehler dort berührt keine Zeile oben.
    # Stand E1: wird geschrieben, von keiner Sicht gelesen.
    from backend.services.kanal.schreiber import schreibe_betriebsart_mitschrift_sicher
    await schreibe_betriebsart_mitschrift_sicher(db, anlage, datum, betriebsmodus_aus_quelle)

    logger.info(
        f"Anlage {anlage.id}, {datum}: {akku.stunden_count}h aggregiert, "
        f"Überschuss={akku.tages_ueberschuss:.1f}kWh, Defizit={akku.tages_defizit:.1f}kWh, "
        f"PR={performance_ratio or '-'}"
    )

    return zusammenfassung
