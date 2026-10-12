"""
Custom-Import — gemeinsame Models, Parser-Helpers, Konstanten.

Genutzt von analyze.py, preview.py, apply.py und templates.py.
Alle Sub-Slices teilen sich die Datei-Lese- und Number-Parsing-
Pipeline; Mapping-Schemas (`MappingConfig`/`FieldMapping`) sind in
mehreren Endpoints im Body-Schema.
"""

import csv
import hashlib
import io
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ─── EEDC-Zielfelder ─────────────────────────────────────────────────────────

EEDC_FIELDS = [
    {"id": "jahr", "label": "Jahr", "required": True, "group": "zeit"},
    {"id": "monat", "label": "Monat", "required": True, "group": "zeit"},
    {"id": "pv_erzeugung_kwh", "label": "PV-Erzeugung (kWh)", "required": False, "group": "energie"},
    {"id": "einspeisung_kwh", "label": "Einspeisung (kWh)", "required": False, "group": "energie"},
    {"id": "netzbezug_kwh", "label": "Netzbezug (kWh)", "required": False, "group": "energie"},
    {"id": "eigenverbrauch_kwh", "label": "Eigenverbrauch (kWh)", "required": False, "group": "energie"},
    {"id": "batterie_ladung_kwh", "label": "Batterie Ladung (kWh)", "required": False, "group": "batterie"},
    {"id": "batterie_entladung_kwh", "label": "Batterie Entladung (kWh)", "required": False, "group": "batterie"},
    {"id": "wallbox_ladung_kwh", "label": "Wallbox Ladung (kWh)", "required": False, "group": "wallbox"},
    {"id": "wallbox_ladung_pv_kwh", "label": "Wallbox PV-Ladung (kWh)", "required": False, "group": "wallbox"},
    {"id": "wallbox_ladevorgaenge", "label": "Wallbox Ladevorgänge", "required": False, "group": "wallbox"},
    {"id": "eauto_km_gefahren", "label": "E-Auto Gefahrene km", "required": False, "group": "eauto"},
]

SETTINGS_KEY = "custom_import_templates"


# ─── Mapping-Models — gemeinsam zwischen preview, apply, templates ──────────

class FieldMapping(BaseModel):
    spalte: str
    eedc_feld: str
    invertieren: bool = False  # Vorzeichen invertieren (negative → positive)


class MappingConfig(BaseModel):
    mappings: list[FieldMapping]
    einheit: str = "kwh"  # "wh", "kwh", "mwh"
    dezimalzeichen: str = "auto"  # "auto", "punkt", "komma"
    datum_spalte: Optional[str] = None  # Falls Jahr+Monat in einer Spalte
    datum_format: Optional[str] = None  # z.B. "YYYY-MM", "MM/YYYY"


# ─── Datei-/Parser-Helpers ──────────────────────────────────────────────────

def _read_file_content(content_bytes: bytes) -> str:
    """Datei als Text lesen (UTF-8 oder Latin-1)."""
    try:
        return content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return content_bytes.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(400, "Datei konnte nicht gelesen werden. Bitte UTF-8 oder Latin-1 verwenden.")


def _detect_csv_dialect(content: str) -> csv.Dialect:
    """Erkennt CSV-Trennzeichen automatisch."""
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(content[:4096], delimiters=";,\t")
        return dialect
    except csv.Error:
        # Fallback: Semikolon (deutsch) oder Komma
        if ";" in content[:1000]:
            csv.register_dialect("fallback", delimiter=";", quoting=csv.QUOTE_MINIMAL)
            return csv.get_dialect("fallback")
        csv.register_dialect("fallback_comma", delimiter=",", quoting=csv.QUOTE_MINIMAL)
        return csv.get_dialect("fallback_comma")


def _parse_csv_rows(content: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parst CSV und gibt (header, rows) zurück."""
    dialect = _detect_csv_dialect(content)
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)

    if not reader.fieldnames:
        raise HTTPException(400, "Keine Spaltenüberschriften in der CSV-Datei gefunden.")

    headers = [h.strip() for h in reader.fieldnames if h and h.strip()]
    rows = []
    for row in reader:
        cleaned = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k and k.strip()}
        if any(v for v in cleaned.values()):
            rows.append(cleaned)

    return headers, rows


def _parse_json_rows(content: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parst JSON-Array und gibt (header, rows) zurück."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Ungültiges JSON-Format: {e}")

    if isinstance(data, dict):
        # Mögliches Wrapper-Objekt — nach Array suchen
        for key in data:
            if isinstance(data[key], list) and len(data[key]) > 0:
                data = data[key]
                break
        else:
            raise HTTPException(400, "JSON enthält kein Array mit Datensätzen.")

    if not isinstance(data, list) or len(data) == 0:
        raise HTTPException(400, "JSON enthält keine Datensätze.")

    if not isinstance(data[0], dict):
        raise HTTPException(400, "JSON-Einträge müssen Objekte mit Key-Value-Paaren sein.")

    # Alle Keys sammeln
    all_keys: set[str] = set()
    for item in data:
        if isinstance(item, dict):
            all_keys.update(item.keys())

    headers = sorted(all_keys)
    rows = [{k: str(v) if v is not None else "" for k, v in item.items()} for item in data if isinstance(item, dict)]

    return headers, rows


def _parse_number(value: str, dezimalzeichen: str = "auto") -> Optional[float]:
    """Parst einen Zahlenwert mit konfigurierbarem Dezimalzeichen."""
    if not value or value.strip() in ("", "-", "–", "n/a", "N/A"):
        return None

    value = value.strip()

    if dezimalzeichen == "komma":
        value = value.replace(".", "").replace(",", ".")
    elif dezimalzeichen == "punkt":
        value = value.replace(",", "")
    else:
        # Auto-Detect
        if "," in value and "." in value:
            # 1.234,56 (deutsch) oder 1,234.56 (englisch)
            if value.rfind(",") > value.rfind("."):
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        elif "," in value:
            value = value.replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def _convert_unit(value: Optional[float], einheit: str) -> Optional[float]:
    """Konvertiert Wh/MWh zu kWh."""
    if value is None:
        return None
    if einheit == "wh":
        return round(value / 1000, 2)
    if einheit == "mwh":
        return round(value * 1000, 2)
    return round(value, 2)


def _registry_feld(feld_name: str) -> Optional[dict]:
    """Das Registry-Feld zu einem Feldnamen, über alle Investitionstypen.

    ⛔ *Sonstiges* führt seine Felder **je Kategorie** (dict statt Liste). Bis 12.10.2026 lief die Suche hier flach
    über `INVESTITION_FELDER.values()` und iterierte bei Sonstiges die Kategorie-Namen — `AttributeError` für 11 von
    12 Sonstiges-Feldern, Vorschau 500 (N-704). Ein Feldname trägt in der Registry überall dieselbe Einheit
    (gemessen 12.10.), die erste Fundstelle genügt also.
    """
    from backend.core.field_definitions import INVESTITION_FELDER
    for typ_felder in INVESTITION_FELDER.values():
        listen = list(typ_felder.values()) if isinstance(typ_felder, dict) else [typ_felder]
        for liste in listen:
            for f in liste:
                if f.get("feld") == feld_name:
                    return f
    return None


def _is_energy_target(eedc_feld: str) -> bool:
    """True wenn das Mapping-Target eine Energie-Größe (Wh/kWh/MWh) ist und
    damit `_convert_unit` greifen soll. km, Anzahl, € sollten unkonvertiert
    durchgereicht werden.
    """
    if eedc_feld in {"jahr", "monat", "eauto_km_gefahren", "wallbox_ladevorgaenge"}:
        return False
    if eedc_feld.startswith("inv:"):
        parts = eedc_feld.split(":", 2)
        if len(parts) < 3:
            return False
        f = _registry_feld(parts[2])
        if f is None:
            return False
        einheit = (f.get("einheit") or "").lower()
        return einheit in {"kwh", "wh", "mwh"}
    return True


def _maybe_convert(value: Optional[float], einheit: str, eedc_feld: str) -> Optional[float]:
    """Wendet `_convert_unit` nur an, wenn das Target eine Energie-Größe ist."""
    if value is None:
        return None
    if _is_energy_target(eedc_feld):
        return _convert_unit(value, einheit)
    return round(value, 2)


def _parse_date_column(value: str, fmt: str) -> tuple[Optional[int], Optional[int]]:
    """Extrahiert Jahr und Monat aus einer kombinierten Datumsspalte."""
    value = value.strip()
    if not value:
        return None, None

    from datetime import datetime

    # Vordefinierte Formate probieren
    formats = [fmt] if fmt else []
    formats.extend([
        "%Y-%m", "%m/%Y", "%Y/%m", "%m-%Y",
        "%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y",
        "%Y%m",
    ])

    for f in formats:
        try:
            dt = datetime.strptime(value, f)
            return dt.year, dt.month
        except (ValueError, TypeError):
            continue

    # Fallback: Nur Zahl = evtl. YYYYMM
    try:
        num = int(value)
        if 190001 <= num <= 210012:
            return num // 100, num % 100
    except ValueError:
        pass

    return None, None


# ─── Zeilen-Kern: was Vorschau UND Import aus der Datei lesen (N-706) ─────────
#
# ⛔ **Warum es diesen Kern gibt.** Bis 12.10.2026 lasen `preview.py::_apply_mapping` und `apply.py` dieselbe Zeile
# mit zwei Handschriften (RF-10 §4.6): die Vorschau rechnete automatisch erkannte Geräte-Spalten in Wh um, der
# Import schrieb sie roh (Vorschau 300, Cockpit 500 000 kWh); die Vorschau bot «Jahr 0» an, der Import übersprang es
# still; Tageszeilen wurden im Import zum ersten bzw. letzten Tag des Monats. Seitdem gilt: **dieser Kern liefert je
# Monat, was geschrieben wird — die Vorschau zeigt es, der Import schreibt es** (Prinzip N-666).
#
# Regeln (Entscheide Master 12.10.):
# * Geräte-Spalten (automatisch erkannt, `<Bezeichnung>_<Suffix>`) tragen ihre Einheit im Namen (`_kWh`, `_km`) und
#   werden NICHT umgerechnet; die globale Einheit (Wh/MWh) gilt nur für Spalten ohne Einheit im Namen (B4).
# * Mehrere Zeilen desselben Monats (Tageszeilen) werden **summiert** — Vorbild Portal-Import (die Parser in
#   `services/import_parsers/` summieren Tageswerte je Monat). Summiert wird nur, was ein Mengenwert ist
#   (Registry `ist_zaehler_differenz_feld`: der Monatswert ist die Differenz eines Zählers = Summe der Tage); ein
#   Stand, ein Preis, ein €-Betrag oder Sonderkosten in mehreren Zeilen eines Monats ⇒ Zeilenfehler des Monats.
# * Jahr/Monat: gültig ist, was der Import immer nahm — Jahr ≠ 0, Monat 1…12 (V5).
# * Eine ausdrückliche `inv:`-Zuordnung muss zur Anlage gehören und ein Feld der Investition treffen, sonst wird sie
#   ignoriert und gemeldet (N-705); eine ausdrücklich zugeordnete Spalte oder ein ausdrücklich belegtes Ziel wird
#   nicht zusätzlich aus der automatischen Erkennung geschrieben (N-702, «nie doppelt»).

#: Die Werte, die der Import aus den generischen Spalten kennt (alle Mengen — summierbar).
_GENERISCHE_FELDER = (
    "pv_erzeugung_kwh", "einspeisung_kwh", "netzbezug_kwh", "eigenverbrauch_kwh",
    "batterie_ladung_kwh", "batterie_entladung_kwh",
    "wallbox_ladung_kwh", "wallbox_ladung_pv_kwh", "wallbox_ladevorgaenge", "eauto_km_gefahren",
)


@dataclass
class ZeilenPosition:
    """Jahr und Monat einer Zeile, schrittweise erkannt."""

    jahr: Optional[int] = None
    monat: Optional[int] = None


def _lies_jahr_monat(
    row: dict[str, str], config: MappingConfig, field_map: dict[str, str], pos: ZeilenPosition,
) -> None:
    """Jahr und Monat der Zeile: zuerst die kombinierte Datumsspalte, dann die Jahr-/Monat-Spalten.

    Schreibt schrittweise in `pos` — die Fehlermeldung der Zeile nennt, was bis zu einem Fehler erkannt war.
    """
    if config.datum_spalte and config.datum_spalte in row:
        j, m = _parse_date_column(row[config.datum_spalte], config.datum_format or "")
        if j and m:
            pos.jahr, pos.monat = j, m

    for spalte, eedc_feld in field_map.items():
        raw = row.get(spalte, "")
        if not raw:
            continue
        if eedc_feld == "jahr" and pos.jahr is None:
            try:
                pos.jahr = int(float(raw))
            except (ValueError, TypeError):
                pass
        elif eedc_feld == "monat" and pos.monat is None:
            try:
                pos.monat = int(float(raw))
            except (ValueError, TypeError):
                pass


def _ist_menge(feld: Optional[dict]) -> bool:
    """Darf dieser Wert über mehrere Zeilen eines Monats summiert werden? Nur ein Mengenwert (Registry)."""
    if feld is None:
        return False
    from backend.core.field_definitions import basis_feld_key, ist_zaehler_differenz_feld
    return ist_zaehler_differenz_feld(basis_feld_key(feld["feld"]))


def _als_zelle(wert, dezimalzeichen: str) -> str:
    """Eine Summe als Zelle, die `_parse_number` mit demselben Dezimalzeichen exakt zurückliest (für v09)."""
    if isinstance(wert, int):
        return str(wert)
    text = repr(float(wert))
    return text.replace(".", ",") if dezimalzeichen == "komma" else text


@dataclass
class ZuordnungsPlan:
    """Was das Mapping für jede Zeile bedeutet — einmal je Datei bestimmt, für Vorschau und Import gleich."""

    config: MappingConfig
    field_map: dict[str, str]
    invert_map: dict[str, bool]
    #: Gültige `inv:`-Slots: Spalte → (Investitions-ID, Feldname, Registry-Feld), Reihenfolge des Mappings.
    inv_slots: dict[str, tuple[int, str, Optional[dict]]]
    #: Automatisch erkannte Geräte-Spalten, die v09 schreibt: Spalte → Registry-Feld (None = Sonderkosten).
    geraete_spalten: dict[str, Optional[dict]]
    #: Erkannte Spalten, die v09 NICHT bekommt: eine ausdrückliche `inv:`-Zuordnung belegt die Spalte oder ihr Ziel.
    ausgenommen: set[str]
    #: Wallboxen der Anlage (Ziel der Anlagen-Wallbox-Menge, wie im Portal-Import die erste); None = keine Anlage
    #: bekannt, nicht prüfbar.
    wallboxen: Optional[list]
    warnungen: list[str] = field(default_factory=list)
    #: N-710: Geräte-Spalten, die ihr Feld nur über den Alt-Suffix tragen → die Haupt-Spalten desselben Feldes in der
    #: Datei. Eine solche Spalte gilt nur, wo keine Haupt-Spalte einen Wert hat (`helpers.ist_alt_spalte`, wie v09).
    alt_spalten: dict[str, list[str]] = field(default_factory=dict)

    def parse_float(self, val: str) -> Optional[float]:
        return _parse_number(val, self.config.dezimalzeichen)

    def parse_float_inv(self, val: str, spalte: str) -> Optional[float]:
        """parse_float + Vorzeichen-Inversion wenn konfiguriert."""
        num = _parse_number(val, self.config.dezimalzeichen)
        if num is not None and self.invert_map.get(spalte):
            num = abs(num)
        return num


def plane_zuordnung(
    config: MappingConfig,
    investitionen: Optional[Sequence],
    erkannte: "Mapping[str, tuple[Optional[int], Optional[dict]]] | Iterable[str]" = (),
) -> ZuordnungsPlan:
    """Den Plan einer Datei bestimmen.

    `investitionen` sind die der Ziel-Anlage; `None` heißt «keine Anlage bekannt» (Vorschau ohne Anlage) — dann
    wird eine `inv:`-Zuordnung nicht geprüft. `erkannte` sind die automatisch erkannten Geräte-Spalten
    (`analyze._erkenne_investitions_spalten`) als Spalte → (Investitions-ID, Registry-Feld); ein bloßes Namens-Set
    ist erlaubt (ohne Ziel-Abgleich).
    """
    from backend.api.routes.import_export.helpers import V09_BASIS_SPALTEN
    from backend.core.field_definitions import get_alle_felder_fuer_investition

    field_map: dict[str, str] = {m.spalte: m.eedc_feld for m in config.mappings}
    invert_map: dict[str, bool] = {m.spalte: True for m in config.mappings if m.invertieren}
    je_id = None if investitionen is None else {inv.id: inv for inv in investitionen}

    inv_slots: dict[str, tuple[int, str, Optional[dict]]] = {}
    warnungen: list[str] = []
    for spalte, eedc_feld in field_map.items():
        if not eedc_feld.startswith("inv:"):
            continue
        parts = eedc_feld.split(":", 2)
        try:
            inv_id = int(parts[1]) if len(parts) == 3 else None
        except ValueError:
            inv_id = None
        if inv_id is None:
            continue  # unlesbare Zuordnung — wie vor dem Kern ohne Wirkung (kommt aus der Fläche nicht vor)
        feld_name = parts[2]
        if je_id is None:
            inv_slots[spalte] = (inv_id, feld_name, _registry_feld(feld_name))
            continue
        inv = je_id.get(inv_id)
        if inv is None:
            warnungen.append(
                f"Spalte '{spalte}' ist einer Investition zugeordnet, die es in dieser Anlage nicht gibt "
                f"(ID {inv_id}, z. B. aus einer gespeicherten Vorlage) — die Zuordnung wird ignoriert."
            )
            continue
        feld = next(
            (f for f in get_alle_felder_fuer_investition(inv.typ, inv.parameter) if f.get("feld") == feld_name),
            None,
        )
        if feld is None:
            warnungen.append(
                f"Spalte '{spalte}': '{inv.bezeichnung}' führt kein Feld '{feld_name}' — die Zuordnung wird ignoriert."
            )
            continue
        inv_slots[spalte] = (inv_id, feld_name, feld)

    ziele = {(inv_id, feld_name) for inv_id, feld_name, _ in inv_slots.values()}
    if not isinstance(erkannte, Mapping):
        erkannte = {spalte: (None, None) for spalte in erkannte}
    geraete_spalten: dict[str, Optional[dict]] = {}
    ausgenommen: set[str] = set()
    for spalte, (inv_id, feld) in erkannte.items():
        if spalte in V09_BASIS_SPALTEN:
            continue  # v09 überspringt sie — die Vorschau zeigt sie dann auch nicht als Geräte-Spalte
        belegt = feld is not None and (inv_id, feld.get("feld")) in ziele
        if spalte in inv_slots or belegt:
            ausgenommen.add(spalte)
            continue
        geraete_spalten[spalte] = feld

    # N-710: eine Alt-Suffix-Spalte neben der Haupt-Spalte desselben Geräte-Feldes (alte Vorlage + neuer Name).
    from backend.api.routes.import_export.helpers import ist_alt_spalte

    alt_spalten: dict[str, list[str]] = {}
    for spalte, feld in geraete_spalten.items():
        if feld is None or not ist_alt_spalte(spalte, feld):
            continue
        inv_id = erkannte[spalte][0]
        haupt = [
            s2 for s2, f2 in geraete_spalten.items()
            if f2 is not None and erkannte[s2][0] == inv_id and f2.get("feld") == feld.get("feld")
            and not ist_alt_spalte(s2, f2)
        ]
        if haupt:
            alt_spalten[spalte] = haupt

    wallboxen = None if investitionen is None else [i for i in investitionen if i.typ == "wallbox"]
    return ZuordnungsPlan(
        config=config, field_map=field_map, invert_map=invert_map, inv_slots=inv_slots,
        geraete_spalten=geraete_spalten, ausgenommen=ausgenommen, wallboxen=wallboxen,
        warnungen=warnungen, alt_spalten=alt_spalten,
    )


@dataclass
class ZeilenAbsturz:
    """Eine Zeile, deren Jahr/Monat-Lesung wirft (`inf`, B7 — verworfen). Sie wirft dort, wo sie steht, wie bisher."""

    pos: ZeilenPosition
    fehler: BaseException


@dataclass
class MonatsWerte:
    """Was der Import für einen Monat schreibt — Summe aller Zeilen dieses Monats."""

    jahr: int
    monat: int
    zeilen: list[dict[str, str]] = field(default_factory=list)
    #: Generische Felder (Anlagen-Ebene): eedc_feld → Wert.
    generisch: dict[str, float] = field(default_factory=dict)
    #: Gültige `inv:`-Slots: Spalte → Wert (umgerechnet wie geschrieben).
    inv_werte: dict[str, float] = field(default_factory=dict)
    #: Geräte-Spalten für v09: Spalte → Zellen (roh) und Wert (wie v09 ihn schreibt; None = nicht gezeigt).
    geraete_roh: dict[str, list[str]] = field(default_factory=dict)
    geraete_werte: dict[str, float] = field(default_factory=dict)
    #: Fehler der einzelnen Zeilen (in Zeilen-Reihenfolge) und des Monats (Summe, Wallbox).
    fehler_zeilen: list[str] = field(default_factory=list)
    fehler_monat: list[str] = field(default_factory=list)

    @property
    def fehler(self) -> list[str]:
        """Alle Gründe, aus denen der Monat nicht geschrieben wird — der erste ist der Zeilenfehler des Imports."""
        return self.fehler_zeilen + self.fehler_monat

    def nicht_summierbar(self, spalte: str) -> None:
        self.fehler_monat.append(
            f"Spalte '{spalte}' ist kein Mengenwert und steht in mehreren Zeilen dieses Monats — "
            "er lässt sich nicht summieren (bitte eine Zeile je Monat)"
        )

    def geraete_zeile(self, plan: ZuordnungsPlan) -> dict[str, str]:
        """Die Zeile, die v09 bekommt. Eine Zeile im Monat ⇒ die Zeile selbst (ohne ausgenommene Spalten);
        mehrere ⇒ je Geräte-Spalte die eine Zelle bzw. die Summe als Zelle."""
        if len(self.zeilen) == 1:
            return {k: v for k, v in self.zeilen[0].items() if k not in plan.ausgenommen}
        zeile: dict[str, str] = {}
        for spalte, roh in self.geraete_roh.items():
            zeile[spalte] = roh[0] if len(roh) == 1 else _als_zelle(
                self.geraete_werte[spalte], plan.config.dezimalzeichen,
            )
        return zeile


def _addiere(ziel: dict, schluessel: str, wert, summierbar: bool, spalte: str, monat: MonatsWerte) -> None:
    """Einen Zeilenwert in den Monat übernehmen: erste Zeile setzt, weitere addieren (nur Mengen)."""
    if schluessel not in ziel:
        ziel[schluessel] = wert
    elif summierbar:
        summe = ziel[schluessel] + wert
        ziel[schluessel] = summe if isinstance(summe, int) else round(summe, 2)
    else:
        monat.nicht_summierbar(spalte)


def _lies_zeilenwerte(row: dict[str, str], plan: ZuordnungsPlan, monat: MonatsWerte) -> None:
    """Die Werte EINER Zeile lesen und in ihren Monat übernehmen.

    Fehler-Reihenfolge wie der Schreibweg vor dem Kern: Geräte-Spalten (v09, in Zeilen-Reihenfolge), dann
    `inv:`-Slots, dann die generischen Felder. Der Import meldet den ersten als Zeilenfehler.
    """
    from backend.api.routes.import_export.helpers import lies_geraete_wert, pruefe_nicht_negativ

    monat.zeilen.append(row)
    fehler_geraete: list[str] = []
    fehler_inv: list[str] = []
    fehler_generisch: list[str] = []

    # Geräte-Spalten (v09): Einheit steht im Namen, keine Umrechnung, keine Inversion.
    for spalte, raw in row.items():
        if spalte not in plan.geraete_spalten or not raw or not raw.strip():
            continue
        feld = plan.geraete_spalten[spalte]
        # N-710: die Alt-Suffix-Spalte zählt nicht, wenn die Zeile das Feld unter seinem Haupt-Suffix trägt — wie v09
        # (`helpers._import_investition_monatsdaten_v09`), auch ungelesen.
        if any((row.get(h) or "").strip() for h in plan.alt_spalten.get(spalte, ())):
            continue
        if feld is None:
            # Sonderkosten (`<Bezeichnung>_Sonderkosten_Euro/_Notiz`): v09 schreibt den Betrag, wenn > 0.
            if spalte in monat.geraete_roh:
                monat.nicht_summierbar(spalte)
                continue
            monat.geraete_roh[spalte] = [raw]
            betrag = plan.parse_float(raw)
            if betrag is not None and betrag > 0:
                monat.geraete_werte[spalte] = betrag
            continue
        try:
            wert = lies_geraete_wert(raw, feld, spalte, plan.parse_float)
        except (ValueError, OverflowError) as e:
            fehler_geraete.append(str(e))
            continue
        if wert is None:
            continue
        monat.geraete_roh.setdefault(spalte, []).append(raw)
        _addiere(monat.geraete_werte, spalte, wert, _ist_menge(feld), spalte, monat)

    # Ausdrückliche `inv:`-Slots: globale Einheit nach Registry-Einheit, Vorzeichen wie v09 (N-708).
    for spalte, (_inv_id, feld_name, feld) in plan.inv_slots.items():
        raw = row.get(spalte, "")
        if not raw:
            continue
        val = _maybe_convert(plan.parse_float_inv(raw, spalte), plan.config.einheit, plan.field_map[spalte])
        if val is None:
            continue
        try:
            if feld_name == "ladevorgaenge":
                val = int(val)
            elif (feld or {}).get("typ", "float") != "int":
                pruefe_nicht_negativ(val, spalte)
        except (ValueError, OverflowError) as e:
            fehler_inv.append(str(e))
            continue
        _addiere(monat.inv_werte, spalte, val, _ist_menge(feld), spalte, monat)

    # Generische Felder: je Zeile gewinnt die letzte Spalte eines Feldes, über Zeilen wird summiert.
    zeile_generisch: dict[str, float] = {}
    for spalte, eedc_feld in plan.field_map.items():
        raw = row.get(spalte, "")
        if not raw or eedc_feld in ("jahr", "monat") or eedc_feld.startswith("inv:"):
            continue
        val = _maybe_convert(plan.parse_float_inv(raw, spalte), plan.config.einheit, eedc_feld)
        if val is None:
            continue
        if eedc_feld == "wallbox_ladevorgaenge":
            try:
                val = int(val)
            except OverflowError as e:
                fehler_generisch.append(str(e))
                continue
        zeile_generisch[eedc_feld] = val
    for eedc_feld, val in zeile_generisch.items():
        _addiere(monat.generisch, eedc_feld, val, True, eedc_feld, monat)

    monat.fehler_zeilen.extend(fehler_geraete + fehler_inv + fehler_generisch)


def _pruefe_wallbox(monat: MonatsWerte, plan: ZuordnungsPlan) -> None:
    """Die Anlagen-Wallbox-Menge geht auf die Wallbox (Konzept Wallbox/E-Auto: die Wallbox ist die Quelle, Vorbild
    Portal-Import). Was nicht geschrieben werden kann, ist ein Zeilenfehler — nie still verworfen (N-703, N-302)."""
    ladung = monat.generisch.get("wallbox_ladung_kwh")
    ladung_pv = monat.generisch.get("wallbox_ladung_pv_kwh")
    if ladung_pv is not None and ladung_pv > 0 and not (ladung is not None and ladung > 0):
        monat.fehler_monat.append(
            "Wallbox PV-Ladung ohne Wallbox-Ladung (gesamt) — der PV-Anteil braucht die Gesamtmenge"
        )
    if ladung is not None and ladung > 0 and plan.wallboxen is not None and not plan.wallboxen:
        monat.fehler_monat.append(
            "Wallbox-Ladung angegeben, aber keine Wallbox als Investition angelegt — "
            "bitte zuerst eine Wallbox unter Investitionen anlegen"
        )


def lies_monate(
    rows: list[dict[str, str]], plan: ZuordnungsPlan,
) -> tuple[list["MonatsWerte | ZeilenAbsturz"], int]:
    """Alle Zeilen → Monate, in der Reihenfolge ihres ersten Auftretens. Zweiter Wert: Zeilen ohne gültiges
    Jahr/Monat (übersprungen)."""
    monate: dict[tuple[int, int], MonatsWerte] = {}
    eintraege: list[MonatsWerte | ZeilenAbsturz] = []
    ungueltig = 0
    for row in rows:
        pos = ZeilenPosition()
        try:
            _lies_jahr_monat(row, plan.config, plan.field_map, pos)
        except Exception as e:  # noqa: BLE001 — wie vor dem Kern: die Zeile wirft an ihrer Stelle
            eintraege.append(ZeilenAbsturz(pos=pos, fehler=e))
            continue
        jahr, monat = pos.jahr, pos.monat
        if not jahr or not monat or monat < 1 or monat > 12:
            ungueltig += 1
            continue
        mw = monate.get((jahr, monat))
        if mw is None:
            mw = monate[(jahr, monat)] = MonatsWerte(jahr=jahr, monat=monat)
            eintraege.append(mw)
        _lies_zeilenwerte(row, plan, mw)
    for mw in monate.values():
        _alt_spalten_im_monat(mw, plan)
        _pruefe_wallbox(mw, plan)
    return eintraege, ungueltig


def _alt_spalten_im_monat(monat: MonatsWerte, plan: ZuordnungsPlan) -> None:
    """N-710 über mehrere Zeilen eines Monats: v09 bekommt die Monatssumme als EINE Zeile (`geraete_zeile`) — trägt
    sie die Haupt-Spalte, zählt die Alt-Spalte dort nicht. Die Vorschau zeigt dann ebenfalls nur die Haupt-Spalte."""
    for alt, haupt in plan.alt_spalten.items():
        if alt in monat.geraete_roh and any(h in monat.geraete_roh for h in haupt):
            monat.geraete_roh.pop(alt, None)
            monat.geraete_werte.pop(alt, None)


# ─── Temporärer Speicher für Upload-Sessions ─────────────────────────────────
# In-Memory Cache für die aktuelle Upload-Session (zwischen Analyze und Preview)
# Key: session_id (filename hash), Value: (headers, rows, filename)
_upload_cache: dict[str, tuple[list[str], list[dict[str, str]], str]] = {}


def _cache_key(filename: str, content: str) -> str:
    """Erzeugt einen Cache-Key aus Dateiname und Content-Hash."""
    h = hashlib.md5(content[:2048].encode()).hexdigest()[:12]
    return f"{filename}_{h}"
