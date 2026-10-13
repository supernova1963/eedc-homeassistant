"""
CSV Import/Export Operations

Template-Generierung, CSV-Import und CSV-Export.
"""

import csv
from collections import Counter
from dataclasses import dataclass, field
from io import StringIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_jetzt, sort_investitionen_nach_typ
from backend.services.wetter.monatswerte import loese_monats_wetter
from backend.utils.sonstige_positionen import berechne_sonstige_summen, get_sonstige_positionen
from backend.api.routes.strompreise import lade_tarife_fuer_anlage
from backend.core.field_definitions import (
    basis_feld_key,
    get_alle_felder_fuer_investition,
    get_felder_fuer_investition,
    innengeraet_id_von_feld,
)
from backend.services.provenance import seed_provenance, write_with_provenance
from backend.core.berechnungen.preis_reihe import ist_dynamisch

from .schemas import ImportResult, CSVTemplateInfo
from .helpers import (
    LEGACY_GERAETE_SPALTEN,
    V09_BASIS_SPALTEN,
    _sanitize_column_name,
    _normalize_for_matching,
    _spalte_traegt_suffix,
    _import_investition_monatsdaten_v09,
    _import_investition_monatsdaten_legacy,
    _distribute_legacy_pv_to_modules,
    _distribute_legacy_battery_to_storages,
    _speicher_nullen_verteilen,
)

router = APIRouter()


@router.get("/template/{anlage_id}", response_model=CSVTemplateInfo)
async def get_csv_template_info(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt Informationen über das personalisierte CSV-Template für eine Anlage zurück.

    v0.9: Template basiert auf angelegten Investitionen mit deren Bezeichnungen.
    Spalten werden dynamisch generiert, z.B. "Speicher_Keller_Ladung_kWh".
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise not_found("Anlage")

    # Basis-Spalten (nur Zählerwerte!)
    spalten = ["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh"]
    beschreibung = {
        "Jahr": "Jahr (z.B. 2024)",
        "Monat": "Monat (1-12)",
        "Einspeisung_kWh": "Ins Netz eingespeiste Energie (Zählerwert)",
        "Netzbezug_kWh": "Aus dem Netz bezogene Energie (Zählerwert)",
    }

    # Bei dynamischem Tarif: Durchschnittspreis-Spalte
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    if ist_dynamisch(allgemein_tarif):
        spalten.append("Durchschnittspreis_Cent")
        beschreibung["Durchschnittspreis_Cent"] = "Ø Strompreis bei dynamischem Tarif (ct/kWh)"

    # #392: bei variabler Einspeisevergütung die Monatssatz-Spalte
    if allgemein_tarif and getattr(allgemein_tarif, "einspeisung_variabel", False):
        spalten.append("Einspeiseverguetung_Cent")
        beschreibung["Einspeiseverguetung_Cent"] = (
            "Vergütungssatz des Monats bei variabler Einspeisevergütung (ct/kWh)"
        )

    # Investitionen laden, nach Typ und ID sortiert
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id, aktiv_jetzt())
        .order_by(Investition.id)
    )
    investitionen = sort_investitionen_nach_typ(inv_result.scalars().all())

    # Personalisierte Spalten je nach Investition (v0.9)
    #
    # ⚠ **Der SPALTENNAME kommt aus der Registry** (`csv_suffix` am Feld) — aus
    # derselben Quelle wie Export (unten) und Import (`helpers.py`). Diese
    # Tabelle löst nur noch die **Beschreibungstexte** auf.
    #
    # Bis v4.0.23 baute die Vorlage ihren Spaltennamen aus einer zweiten,
    # handgepflegten Liste. Die beiden liefen auseinander (F-55): drei Werte
    # gingen beim eigenen Rundlauf schweigend verloren — `ladung_netz_kwh` am
    # Speicher (`_Ladung_Netz_kWh` statt `_Netzladung_kWh`, das Literal führte
    # den Key zweimal), `einspeise_erloes_euro` und `zaehlerstand` unter
    # *Sonstiges* (roher Key statt Registry-Suffix; letzterer seit v4.0.23,
    # #377 — der Verbrauchszähler war über die Vorlage nie importierbar).
    # Beim BKW rettete nur `csv_suffix_alt` den Namen. Gemerkt hat es niemand,
    # weil der Export dieselbe Quelle wie der Import liest: ein Test auf
    # Export→Import ist grün und beweist nichts. Der Wächter fährt deshalb den
    # **Rundlauf** (`test_csv_vorlage_rundlauf_f55.py`).
    CSV_SPALTEN_BESCHREIBUNG = {
        "pv_erzeugung_kwh":       "{label} {bez} (kWh)",
        "ladung_kwh":             "Ladung {bez} (kWh)",
        "entladung_kwh":          "Entladung {bez} (kWh)",
        "speicher_ladepreis_cent":"Ø Ladepreis {bez} (ct/kWh) - Arbitrage",
        "stromverbrauch_kwh":     "Stromverbrauch {bez} (kWh)",
        "strom_heizen_kwh":       "Strom Heizen {bez} (kWh)",
        "strom_warmwasser_kwh":   "Strom Warmwasser {bez} (kWh)",
        "heizenergie_kwh":        "Heizenergie {bez} (kWh)",
        "warmwasser_kwh":         "Warmwasser {bez} (kWh)",
        "km_gefahren":            "Gefahrene km {bez}",
        "verbrauch_kwh":          "Verbrauch {bez} (kWh)",
        "ladung_pv_kwh":          "PV-Ladung {bez} (kWh)",
        "ladung_extern_kwh":      "Externe Ladung {bez} (kWh)",
        "ladung_extern_euro":     "Externe Ladekosten {bez} (€)",
        "v2h_entladung_kwh":      "V2H-Entladung {bez} (kWh)",
        "ladevorgaenge":          "Ladevorgänge {bez}",
        "eigenverbrauch_kwh":     "Eigenverbrauch {bez} (kWh)",
        "speicher_ladung_kwh":    "Speicher-Ladung {bez} (kWh)",
        "speicher_entladung_kwh": "Speicher-Entladung {bez} (kWh)",
        "erzeugung_kwh":          "Erzeugung {bez} (kWh)",
        "verbrauch_sonstig_kwh":  "Verbrauch {bez} (kWh)",
        "bezug_pv_kwh":           "Bezug PV {bez} (kWh)",
        "bezug_netz_kwh":         "Bezug Netz {bez} (kWh)",
        "einspeisung_kwh":        "Einspeisung {bez} (kWh)",
        "einspeise_erloes_euro":  "Einspeise-Erlös {bez} (€)",
        "zaehlerstand":           "{label} {bez}",
    }
    # `ladung_netz_kwh` trägt zwei Bedeutungen an zwei Gerätetypen: beim
    # Speicher Arbitrage-Netzladung, beim E-Auto die Netz-Heimladung. Der
    # **Name** unterscheidet sie schon (Registry: `Netzladung_kWh` vs.
    # `Ladung_Netz_kWh`) — hier braucht es nur noch zwei Texte, nach Typ
    # getrennt statt als zweiter Eintrag im selben Dict (dort gewann bisher
    # still der spätere).
    BESCHREIBUNG_JE_TYP = {
        ("speicher", "ladung_netz_kwh"): "Netzladung {bez} (kWh) - Arbitrage",
        ("e-auto",   "ladung_netz_kwh"): "Netz-Ladung {bez} (kWh)",
    }
    # #263 — die Betriebsart-Zähler einer Split-Klimaanlage: Text aus den
    # Modus-Konstanten statt hier ein zehntes Mal getippt.
    from backend.core.betriebsmodus import (
        BETRIEBSART_LABEL as _BA_LABEL,
        BETRIEBSART_NUTZENERGIE_FELD as _BA_NUTZ,
        BETRIEBSART_STROM_FELD as _BA_STROM,
        MESSBARE_MODI as _BA_MODI,
    )
    for _modus in _BA_MODI:
        for _feld, _was in ((_BA_STROM[_modus], "Strom"),
                            (_BA_NUTZ[_modus], "Nutzenergie")):
            CSV_SPALTEN_BESCHREIBUNG[_feld] = (
                f"{_was} {_BA_LABEL[_modus]} {{bez}} (kWh)"
            )

    for inv in investitionen:
        if inv.typ in ("wechselrichter",):
            continue
        prefix = _sanitize_column_name(inv.bezeichnung)
        bez = inv.bezeichnung

        # N-302 — `anlage_investitionen` durchreichen, damit die Vorlage
        # dieselben Felder anbietet wie der Monatsabschluss. Ohne das bot sie
        # die E-Auto-Heimladung an, obwohl eine Wallbox sie als kanonische
        # Quelle verdrängt (`bedingung_anlage: keine_wallbox`) — eine Spalte,
        # die das Formular ausblendet. Der **Import** wertet `bedingung_anlage`
        # bewusst weiter nicht aus: er darf nie still etwas wegwerfen, und
        # genau das ist die F-55-Lehre.
        felder = get_felder_fuer_investition(
            inv.typ, inv.parameter, anlage_investitionen=investitionen
        )
        for feld_def in felder:
            feld = feld_def["feld"]
            # Der Name: Registry-Suffix, sonst der rohe Key — identisch zur
            # Zeile im Export unten. Bei je-Innengerät-Feldern trägt der
            # Registry-Suffix das `_IG{id}` bereits (`_mit_innengeraeten`).
            suffix = feld_def.get("csv_suffix", feld)
            # Der Text: über das Basis-Feld, damit die Innengerät-Kopien den
            # Text ihres Basis-Felds erben; den Raumnamen stellen wir voran.
            basis = basis_feld_key(feld)
            desc_tmpl = BESCHREIBUNG_JE_TYP.get(
                (inv.typ, basis),
                CSV_SPALTEN_BESCHREIBUNG.get(basis, f"{feld_def['label']} {{bez}}"),
            )
            col = f"{prefix}_{suffix}"
            spalten.append(col)
            desc = desc_tmpl.format(bez=bez, label=feld_def["label"])
            if innengeraet_id_von_feld(feld) is not None:
                raum = feld_def.get("innengeraet_bezeichnung")
                if raum:
                    desc = f"{raum}: {desc}"
            beschreibung[col] = desc

        # Sonderkosten für alle Investitionen (optional)
        col_sk = f"{prefix}_Sonderkosten_Euro"
        col_skn = f"{prefix}_Sonderkosten_Notiz"
        spalten.extend([col_sk, col_skn])
        beschreibung[col_sk] = f"Sonderkosten {bez} (€) - Reparatur, Wartung, etc."
        beschreibung[col_skn] = f"Sonderkosten-Beschreibung {bez}"

    spalten.append("Notizen")
    beschreibung["Notizen"] = "Notizen (optional)"

    return CSVTemplateInfo(spalten=spalten, beschreibung=beschreibung)


@router.get("/template/{anlage_id}/download")
async def download_csv_template(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """Lädt ein CSV-Template für eine Anlage herunter."""
    template_info = await get_csv_template_info(anlage_id, db)

    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(template_info.spalten)

    # Beispielzeile
    beispiel = []
    for spalte in template_info.spalten:
        if spalte == "Jahr":
            beispiel.append("2024")
        elif spalte == "Monat":
            beispiel.append("1")
        elif "kWh" in spalte:
            beispiel.append("0")
        elif spalte == "Notizen":
            beispiel.append("")
        else:
            beispiel.append("0")
    writer.writerow(beispiel)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=eedc_template_{anlage_id}.csv"}
    )


# ── CSV-Import (Backup-Restore) — Zustand und Phasen (RF-14, Serie „Funktion vor Datei") ───────────────────────
#
# `import_csv` ist der Orchestrator: Anlage, Kontext, Datei, Zeilenschleife, Abschluss. Der Schleifenkörper ist
# `_importiere_zeile`; er ruft die Phasen in der Schreib-Reihenfolge des HEAD (je Zeile):
#   SELECT monatsdaten → Geräte-Spalten v09 (Upserts je Gerät) → PV-Verteilung → Speicher-Verteilung + Speicher-0
#   → Monatszeile (UPDATE per write_with_provenance in fester Feldfolge bzw. INSERT + seed_provenance)
#   → Legacy-Gerätespalten (E-Auto, Wallbox, Speicher, WP) — nur auf das EINE Gerät eines Typs (N-747, `_alt_spalten_ziele`).
# ⛔ Je Zeile ganz oder gar nicht (N-748): die Schreibphasen laufen in einem SAVEPOINT je Zeile (`_schreibe_zeile`), ein
#    äußerer SAVEPOINT klammert die Schleife — dieselbe Bauform wie der eigene Import (`custom_import/apply.py`, N-704).
# ⛔ Die drei Legacy-Spalten (PV, Ladung, Entladung) werden VOR der PV-Verteilung gelesen: eine unlesbare
#    Batterie-Zelle bricht die Zeile ab, bevor die PV verteilt ist.


@dataclass
class _ImportKontext:
    """Was jede Zeile des Backup-Imports liest (RF-14): Anlage, Optionen, aktive Investitionen, Spalten-Art.

    `inv_by_type` ist das Ziel der Alt-Spalten je Typ, `alt_spalten_gesperrt` die Warnung je Typ ohne Ziel (N-747,
    beide aus `_alt_spalten_ziele`, sobald die Kopfzeile gelesen ist)."""
    anlage: Anlage
    anlage_id: int
    ueberschreiben: bool
    auto_wetter: bool
    investitionen: list[Investition]
    pv_module_vorhanden: bool
    speicher_vorhanden: bool
    has_personalized_columns: bool = False
    inv_by_type: dict[str, Investition] = field(default_factory=dict)
    alt_spalten_gesperrt: dict[str, str] = field(default_factory=dict)


@dataclass
class _ImportStand:
    """Zähler und Meldungen über alle Zeilen (RF-14). `warnungen` ist EINE Liste über die ganze Datei — die
    `… not in warnungen`-Prüfungen der Phasen lesen sie live, nicht eine Kopie je Zeile."""
    importiert: int = 0
    uebersprungen: int = 0
    fehler: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)


@dataclass
class _ZeilenWerte:
    """Die Werte einer Zeile für die Monatszeile (RF-14); Namen wie die Locals am HEAD — bewusst ohne `_kwh`
    (der P7-Wächter liest die Attributform `x.pv_erzeugung_kwh`)."""
    einspeisung_raw: Optional[float]
    netzbezug_raw: Optional[float]
    einspeisung: float
    netzbezug: float
    durchschnittspreis: Optional[float]
    einspeise_preis: Optional[float]
    globalstrahlung: Optional[float]
    sonnenstunden: Optional[float]
    notizen: Optional[str]
    pv_erzeugung: Optional[float] = None
    batterie_ladung: Optional[float] = None
    batterie_entladung: Optional[float] = None
    direktverbrauch: Optional[float] = None
    eigenverbrauch: Optional[float] = None
    gesamtverbrauch: Optional[float] = None


@router.post("/csv/{anlage_id}", response_model=ImportResult)
async def import_csv(
    anlage_id: int,
    file: UploadFile = File(...),
    ueberschreiben: bool = Query(False, description="Existierende Monate überschreiben"),
    auto_wetter: bool = Query(True, description="Wetterdaten automatisch abrufen wenn leer"),
    db: AsyncSession = Depends(get_db, scope="function")
):
    """
    Importiert Monatsdaten aus einer CSV-Datei.

    v0.9: Unterstützt personalisierte Spalten basierend auf Investitions-Bezeichnungen.
    """
    # Anlage prüfen und laden
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    kontext = await _lade_kontext(db, anlage, anlage_id, ueberschreiben, auto_wetter)
    reader = await _lies_csv(file)

    # Prüfen ob personalisierte Spalten vorhanden
    fieldnames = reader.fieldnames or []
    kontext.has_personalized_columns = _hat_personalisierte_spalten(kontext.investitionen, fieldnames)
    kontext.inv_by_type, kontext.alt_spalten_gesperrt = _alt_spalten_ziele(
        kontext.investitionen, fieldnames, kontext.has_personalized_columns,
    )

    stand = _ImportStand()

    # ⛔ Kein Schutz-Zaehler auf diesem Weg (N-538, gemessen 20.09.2026): die Quelle
    # ist `manual:*`, und eine manuelle Quelle schreibt seit #251 (`f0b45bcc`)
    # UNBEDINGT — `provenance._decide` kennt fuer sie kein `rejected_lower_priority`.
    # Ohne Haken wird ein bestehender Monat oben uebersprungen, mit Haken gewinnt
    # der letzte Schreiber (MANUAL gegen MANUAL). Der Zaehler samt Hinweis
    # „X Felder geschuetzt" lief hier deshalb nie und ist entfernt; er lebt nur
    # im Portal-Import (`data_import.py`, Quelle `external:*`, geraetegebunden).

    # ⛔ **Äußerer SAVEPOINT — nicht weglassen (N-748).** Jede Zeile schreibt in einem eigenen SAVEPOINT. SQLite beginnt mit
    # einem SAVEPOINT außerhalb einer Transaktion SELBST die Transaktion, und dessen RELEASE COMMITTET sie (bis hier liefen
    # nur SELECTs) — ohne diese Klammer wäre jede Zeile sofort dauerhaft. Dieselbe Bauform wie `custom_import/apply.py`.
    async with db.begin_nested():
        for i, row in enumerate(reader, start=2):
            await _importiere_zeile(db, kontext, stand, i, row)

        await db.flush()

    return ImportResult(
        erfolg=len(stand.fehler) == 0,
        importiert=stand.importiert,
        uebersprungen=stand.uebersprungen,
        fehler=stand.fehler[:20],
        warnungen=stand.warnungen[:10],
    )


async def _lade_kontext(
    db: AsyncSession, anlage: Anlage, anlage_id: int, ueberschreiben: bool, auto_wetter: bool,
) -> _ImportKontext:
    """Phase E1 (RF-14): aktive Investitionen, PV-/Speicher-Vorhandensein (das Ziel der Alt-Spalten: `_alt_spalten_ziele`)."""
    # Investitionen laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id, aktiv_jetzt())
    )
    investitionen = list(inv_result.scalars().all())

    return _ImportKontext(
        anlage=anlage,
        anlage_id=anlage_id,
        ueberschreiben=ueberschreiben,
        auto_wetter=auto_wetter,
        investitionen=investitionen,
        pv_module_vorhanden=any(inv.typ == "pv-module" for inv in investitionen),
        speicher_vorhanden=any(inv.typ == "speicher" for inv in investitionen),
    )


async def _lies_csv(file: UploadFile) -> csv.DictReader:
    """Phase E2 (RF-14): Datei lesen (Fehler ⇒ 400), Trennzeichen aus der ersten Zeile."""
    # CSV lesen
    try:
        content = await file.read()
        text = content.decode("utf-8-sig")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fehler beim Lesen der Datei: {e}")

    # CSV parsen
    first_line = text.split('\n')[0] if text else ''
    delimiter = ';' if ';' in first_line else ','
    return csv.DictReader(StringIO(text), delimiter=delimiter)


def _hat_personalisierte_spalten(investitionen: list[Investition], fieldnames: list[str]) -> bool:
    """Phase E3 (RF-14): trägt die Kopfzeile eine Spalte, die einer Investitions-Bezeichnung folgt?"""
    has_personalized_columns = False

    for inv in investitionen:
        sanitized = _sanitize_column_name(inv.bezeichnung)
        normalized = _normalize_for_matching(inv.bezeichnung)

        for col in fieldnames:
            if sanitized in col:
                has_personalized_columns = True
                break
            col_normalized = _normalize_for_matching(col)
            if col_normalized.startswith(normalized) and len(normalized) >= 3:
                has_personalized_columns = True
                break

        if has_personalized_columns:
            break

    return has_personalized_columns


#: N-747: Muster und Mehrzahl der Alt-Spalten je Typ ohne Verteilschlüssel — für die Warnung, wenn sie kein Ziel haben.
_ALT_SPALTEN_WORTE = {
    "e-auto": ("EAuto_*", "E-Autos"),
    "wallbox": ("Wallbox_*", "Wallboxen"),
    "waermepumpe": ("WP_*", "Wärmepumpen"),
}


def _alt_spalten_ziele(
    investitionen: list[Investition], fieldnames: list[str], has_personalized_columns: bool,
) -> tuple[dict[str, Investition], dict[str, str]]:
    """Phase E4 (N-747): wohin die Alt-Spalten (`LEGACY_GERAETE_SPALTEN`) einer Datei gehen — je Typ ein Ziel oder keins.

    Eine Alt-Spalte trägt den Wert des ganzen Typs. Er geht nur auf ein Gerät, wenn es das **einzige aktive** seines Typs
    ist und — bei E-Auto, Wallbox, Wärmepumpe — **keine Geräte-Spalte** dieses Typs in der Datei steht. Sonst schreibt der
    Import ihn nicht und sagt es (zweites Ergebnis: Warnung je Typ). Eine Verteilung gibt es für diese drei Typen nicht
    (km, Ladevorgänge, Heizenergie haben keinen Anteilsschlüssel wie kWp oder Kapazität) — erfundene Anteile wären
    Gerätewerte, die niemand gemessen hat.

    Der Speicher hat einen Verteiler (`_batterie`, proportional nach Kapazität): bei mehreren Speichern ist dessen Ergebnis
    das Ergebnis, der Legacy-Block schreibt nichts darüber (bis 13.10.2026 überschrieb er mit Haken das erste Gerät mit dem
    vollen Wert). Ob eine Speicher-Geräte-Spalte die Zeile trägt, entscheidet `_batterie` je Zeile
    (`_alt_spalten_ziele_der_zeile`); seine Warnungen sagen es schon, hier steht für den Speicher keine.
    """
    anzahl = Counter(inv.typ for inv in investitionen)
    mit_geraete_spalte = _typen_mit_geraete_spalte(investitionen, fieldnames) if has_personalized_columns else set()

    ziele: dict[str, Investition] = {}
    gesperrt: dict[str, str] = {}
    for typ in LEGACY_GERAETE_SPALTEN:
        n = anzahl.get(typ, 0)
        if n == 1 and (typ == "speicher" or typ not in mit_geraete_spalte):
            ziele[typ] = next(inv for inv in investitionen if inv.typ == typ)
        elif n >= 1 and typ in _ALT_SPALTEN_WORTE:
            muster, mehrzahl = _ALT_SPALTEN_WORTE[typ]
            if n > 1:
                gesperrt[typ] = (
                    f"Alt-Spalten {muster} nicht zugeordnet: {n} {mehrzahl} angelegt — "
                    f"die Werte gehören in die Spalten der einzelnen Geräte (siehe CSV-Vorlage)."
                )
            else:
                gesperrt[typ] = (
                    f"Alt-Spalten {muster} nicht zugeordnet: Geräte-Spalte vorhanden — es gelten die Werte der Geräte-Spalte."
                )
    return ziele, gesperrt


def _typen_mit_geraete_spalte(investitionen: list[Investition], fieldnames: list[str]) -> set[str]:
    """N-747: die Typen, für die die Kopfzeile eine Geräte-Spalte trägt — dieselben Treffer-Wege wie v09
    (`<Bezeichnung>` allein, `_spalte_traegt_suffix` über Haupt- und Alt-Suffix der Registry). Basis- und Alt-Spalten zählen
    nie (eine Alt-Spalte ist ein Typ-Sammelwert, auch wenn ein Gerät so heißt, dass v09 sie trifft)."""
    alt = {s for spalten in LEGACY_GERAETE_SPALTEN.values() for s in spalten}
    kandidaten = [c for c in fieldnames if c not in V09_BASIS_SPALTEN and c not in alt]
    typen: set[str] = set()
    for inv in investitionen:
        sanitized = _sanitize_column_name(inv.bezeichnung)
        normalized = _normalize_for_matching(inv.bezeichnung)
        suffixe = [
            s for feld in get_alle_felder_fuer_investition(inv.typ, inv.parameter)
            for s in (feld.get("csv_suffix"), feld.get("csv_suffix_alt")) if s
        ]
        if suffixe and any(
            col == sanitized or any(_spalte_traegt_suffix(col, sanitized, normalized, s) for s in suffixe)
            for col in kandidaten
        ):
            typen.add(inv.typ)
    return typen


# Werte parsen
def _parse_float(val: str) -> Optional[float]:
    if not val or not val.strip():
        return None
    val = val.strip().replace(",", ".")
    return float(val)


def _parse_float_positive(val: str, feldname: str) -> Optional[float]:
    result = _parse_float(val)
    if result is not None and result < 0:
        raise ValueError(f"{feldname} darf nicht negativ sein ({result})")
    return result


async def _importiere_zeile(
    db: AsyncSession, kontext: _ImportKontext, stand: _ImportStand, i: int, row: dict,
) -> None:
    """Eine CSV-Zeile = ein Monat (RF-14, der Schleifenkörper am HEAD). `return` steht für das `continue` am HEAD.

    ⛔ **Ganz oder gar nicht (N-748).** Bis 13.10.2026 blieb, was eine Zeile vor ihrem Fehler geschrieben hatte, in der
    Sitzung stehen: `Sueddach_kWh` 300 neben `PV_Erzeugung_kWh` «abc» ergab «Zeile 2: Ungültiger Wert», «0 importiert» —
    und einen Gerätewert 300 ohne Monatszeile, den ein zweiter Import ohne Haken nicht mehr ersetzte. Jetzt schreibt die
    Zeile in einem eigenen SAVEPOINT (`_schreibe_zeile`); ein Fehler rollt genau diese Zeile zurück und zählt in
    `stand.fehler` (Antwort unverändert). Dieselbe Bauform wie der eigene Import (`custom_import/apply.py::_importiere_monat`)."""
    try:
        # Pflichtfelder
        jahr = int(row.get("Jahr", "").strip())
        monat = int(row.get("Monat", "").strip())

        if not (2000 <= jahr <= 2100):
            stand.fehler.append(f"Zeile {i}: Ungültiges Jahr {jahr}")
            return
        if not (1 <= monat <= 12):
            stand.fehler.append(f"Zeile {i}: Ungültiger Monat {monat}")
            return

        # Existierenden Eintrag prüfen
        existing = await db.execute(
            select(Monatsdaten).where(
                Monatsdaten.anlage_id == kontext.anlage_id,
                Monatsdaten.jahr == jahr,
                Monatsdaten.monat == monat
            )
        )
        existing_md = existing.scalar_one_or_none()

        if existing_md and not kontext.ueberschreiben:
            stand.uebersprungen += 1
            return

        async with db.begin_nested():
            await _schreibe_zeile(db, kontext, stand, i, row, jahr, monat, existing_md)

        stand.importiert += 1

    except ValueError as e:
        stand.fehler.append(f"Zeile {i}: Ungültiger Wert - {e}")
    except Exception as e:
        stand.fehler.append(f"Zeile {i}: Fehler - {e}")


async def _schreibe_zeile(
    db: AsyncSession,
    kontext: _ImportKontext,
    stand: _ImportStand,
    i: int,
    row: dict,
    jahr: int,
    monat: int,
    existing_md: Optional[Monatsdaten],
) -> None:
    """Die Schreibphasen einer Zeile (Z4–Z11), im SAVEPOINT des Aufrufers — eine Ausnahme verwirft alles davon (N-748)."""
    werte = _lies_basiswerte(row, i, stand.warnungen)
    werte.globalstrahlung, werte.sonnenstunden = await _wetter_nachholen(
        db, kontext.anlage, kontext.auto_wetter, werte.globalstrahlung, werte.sonnenstunden, jahr, monat,
    )
    summen = await _summen_aus_geraete_spalten(db, kontext, row, jahr, monat)

    # Legacy-Spalten Validierung
    pv_erzeugung_explicit = _parse_float(row.get("PV_Erzeugung_kWh", ""))
    batterie_ladung_explicit = _parse_float(row.get("Batterie_Ladung_kWh", ""))
    batterie_entladung_explicit = _parse_float(row.get("Batterie_Entladung_kWh", ""))

    werte.pv_erzeugung = await _pv_erzeugung(
        db, kontext, stand.warnungen, summen, pv_erzeugung_explicit, jahr, monat,
    )
    werte.batterie_ladung, werte.batterie_entladung = await _batterie(
        db, kontext, stand.warnungen, summen, batterie_ladung_explicit, batterie_entladung_explicit, jahr, monat,
    )
    werte.direktverbrauch, werte.eigenverbrauch, werte.gesamtverbrauch = _bilanz(
        werte.pv_erzeugung, werte.einspeisung, werte.netzbezug,
        werte.batterie_ladung, werte.batterie_entladung, summen,
    )
    await _schreibe_monatszeile(db, kontext.anlage_id, jahr, monat, existing_md, werte)

    # Legacy Investitions-Spalten — nur auf das EINE Gerät eines Typs (N-747)
    ohne_ziel = await _import_investition_monatsdaten_legacy(
        db, row, _parse_float, _alt_spalten_ziele_der_zeile(kontext, summen), jahr, monat, kontext.ueberschreiben,
        source="manual:csv_backup", writer="csv_backup_restore",
    )
    for typ in ohne_ziel:
        warnung = kontext.alt_spalten_gesperrt.get(typ)
        if warnung is not None and warnung not in stand.warnungen:
            stand.warnungen.append(warnung)


def _alt_spalten_ziele_der_zeile(kontext: _ImportKontext, summen: dict) -> dict[str, Investition]:
    """Phase Z11 (N-747): die Ziele der Datei, ohne den Speicher, wenn die Zeile Speicher-Werte aus Geräte-Spalten trägt —
    dieselbe Bedingung, unter der `_batterie` «Speicher-Werte werden verwendet» sagt (bis 13.10.2026 schrieb der
    Legacy-Block dann trotzdem `Batterie_Ladung_kWh` 80 über `Akku_Ladung_kWh` 30)."""
    if _speicher_werte_aus_geraete_spalten(summen):
        return {typ: inv for typ, inv in kontext.inv_by_type.items() if typ != "speicher"}
    return kontext.inv_by_type


def _lies_basiswerte(row: dict, i: int, warnungen: list[str]) -> _ZeilenWerte:
    """Phase Z4 (RF-14): Netz-, Preis-, Wetter- und Notiz-Spalten der Zeile; Plausibilitäts-Warnungen."""
    # Basis-Felder
    einspeisung_raw = _parse_float_positive(row.get("Einspeisung_kWh", ""), "Einspeisung_kWh")
    netzbezug_raw = _parse_float_positive(row.get("Netzbezug_kWh", ""), "Netzbezug_kWh")
    einspeisung = einspeisung_raw or 0
    netzbezug = netzbezug_raw or 0

    durchschnittspreis = _parse_float(row.get("Durchschnittspreis_Cent", ""))
    # #392: Monatssatz der variablen Einspeisevergütung
    einspeise_preis = _parse_float(row.get("Einspeiseverguetung_Cent", ""))
    globalstrahlung = _parse_float_positive(row.get("Globalstrahlung_kWh_m2", ""), "Globalstrahlung")
    sonnenstunden = _parse_float_positive(row.get("Sonnenstunden", ""), "Sonnenstunden")
    notizen = row.get("Notizen", "").strip() or None

    # Plausibilitäts-Warnungen
    if sonnenstunden is not None and sonnenstunden > 400:
        warnungen.append(f"Zeile {i}: Sonnenstunden ({sonnenstunden}) ungewöhnlich hoch")
    if globalstrahlung is not None and globalstrahlung > 250:
        warnungen.append(f"Zeile {i}: Globalstrahlung ({globalstrahlung}) ungewöhnlich hoch")

    return _ZeilenWerte(
        einspeisung_raw=einspeisung_raw,
        netzbezug_raw=netzbezug_raw,
        einspeisung=einspeisung,
        netzbezug=netzbezug,
        durchschnittspreis=durchschnittspreis,
        einspeise_preis=einspeise_preis,
        globalstrahlung=globalstrahlung,
        sonnenstunden=sonnenstunden,
        notizen=notizen,
    )


async def _wetter_nachholen(
    db: AsyncSession,
    anlage: Anlage,
    auto_wetter: bool,
    globalstrahlung: Optional[float],
    sonnenstunden: Optional[float],
    jahr: int,
    monat: int,
) -> tuple[Optional[float], Optional[float]]:
    """Phase Z5 (RF-14): beide Wetterzellen leer ⇒ Monatswerte über die Auflösung des Monatsformulars."""
    import logging
    logger = logging.getLogger(__name__)

    # Wetterdaten automatisch abrufen — über DIESELBE Auflösung wie das
    # Monatsformular (`services/wetter/monatswerte.py`).
    #
    # ⛔ Hier stand bis zum Paket „Wetterreihe geradeziehen" ein Aufruf
    # von `get_wetterdaten`: eine zweite Kaskade **ohne Bright-Sky-Zweig**,
    # also immer Open-Meteo — gegen die Zusage der eigenen Oberfläche
    # („Automatische Auswahl: Bright Sky für DE"). Wer Monate nachträglich
    # importierte, bekam sie auf einem anderen Lineal als die Monate, die
    # er im Formular geholt hatte: bei den Sonnenstunden Faktor 1,6–2,0
    # (2025-06 gemessen: 380 h gegen 231,8 h). Eine Jahresreihe aus beiden
    # Quellen beantwortet „war mein Jahr schwach?" falsch.
    if auto_wetter and globalstrahlung is None and sonnenstunden is None:
        if anlage.latitude and anlage.longitude:
            try:
                wetter = await loese_monats_wetter(db, anlage, jahr, monat)
                globalstrahlung = wetter.get("globalstrahlung_kwh_m2")
                sonnenstunden = wetter.get("sonnenstunden")
            except Exception as e:
                logger.warning(f"Wetterdaten für {monat}/{jahr} nicht abrufbar: {type(e).__name__}: {e}")

    return globalstrahlung, sonnenstunden


async def _summen_aus_geraete_spalten(
    db: AsyncSession, kontext: _ImportKontext, row: dict, jahr: int, monat: int,
) -> dict:
    """Phase Z6 (RF-14): personalisierte Geräte-Spalten (v09) schreiben; Summen für die Monatszeile."""
    # Personalisierte Spalten verarbeiten
    summen = {"pv_erzeugung_sum": 0.0, "batterie_ladung_sum": 0.0, "batterie_entladung_sum": 0.0}
    if kontext.has_personalized_columns and kontext.investitionen:
        summen = await _import_investition_monatsdaten_v09(
            db, row, _parse_float, kontext.investitionen, jahr, monat, kontext.ueberschreiben,
            source="manual:csv_backup", writer="csv_backup_restore",
        )
    return summen


async def _pv_erzeugung(
    db: AsyncSession,
    kontext: _ImportKontext,
    warnungen: list[str],
    summen: dict,
    pv_erzeugung_explicit: Optional[float],
    jahr: int,
    monat: int,
) -> Optional[float]:
    """Phase Z7 (RF-14): PV der Monatszeile — Modul-Summe vor Legacy-Spalte; Legacy-Wert auf die Module verteilen."""
    # PV-Erzeugung Validierung und Migration
    pv_erzeugung = None
    if summen["pv_erzeugung_sum"] > 0:
        # Individuelle PV-Modul-Spalten vorhanden
        pv_erzeugung = summen["pv_erzeugung_sum"]
        if pv_erzeugung_explicit is not None:
            if abs(pv_erzeugung_explicit - pv_erzeugung) <= 0.5:
                if "Legacy-Spalte 'PV_Erzeugung_kWh' ist redundant" not in warnungen:
                    warnungen.append(
                        "Legacy-Spalte 'PV_Erzeugung_kWh' ist redundant und wird ignoriert."
                    )
            else:
                # Abweichung: Legacy-Wert hat Vorrang, warnen statt Fehler
                if "Legacy 'PV_Erzeugung_kWh' weicht von Modul-Summe ab" not in warnungen:
                    warnungen.append(
                        f"Legacy 'PV_Erzeugung_kWh' weicht von Modul-Summe ab. "
                        f"Modul-Werte werden verwendet, Legacy-Wert ignoriert."
                    )
    elif pv_erzeugung_explicit is not None:
        if kontext.pv_module_vorhanden:
            # Legacy-Wert vorhanden, aber keine individuellen Spalten
            # -> Auf PV-Module verteilen
            pv_module_list = [inv for inv in kontext.investitionen if inv.typ == "pv-module"]
            migration_warnungen = await _distribute_legacy_pv_to_modules(
                db, pv_erzeugung_explicit, pv_module_list, jahr, monat, kontext.ueberschreiben,
                source="manual:csv_backup", writer="csv_backup_restore",
            )
            warnungen.extend(migration_warnungen)
            pv_erzeugung = pv_erzeugung_explicit
        else:
            # Keine PV-Module angelegt - Legacy akzeptieren
            pv_erzeugung = pv_erzeugung_explicit
            if "Keine PV-Module als Investitionen angelegt" not in warnungen:
                warnungen.append(
                    "Keine PV-Module als Investitionen angelegt. "
                    "Legacy-Spalte 'PV_Erzeugung_kWh' wird akzeptiert."
                )
    return pv_erzeugung


async def _batterie(
    db: AsyncSession,
    kontext: _ImportKontext,
    warnungen: list[str],
    summen: dict,
    batterie_ladung_explicit: Optional[float],
    batterie_entladung_explicit: Optional[float],
    jahr: int,
    monat: int,
) -> tuple[Optional[float], Optional[float]]:
    """Phase Z8 (RF-14): Batterie der Monatszeile — Speicher-Summe vor Legacy-Spalten; Legacy-Werte verteilen."""
    # Batterie Validierung und Migration
    batterie_ladung = None
    batterie_entladung = None

    if _speicher_werte_aus_geraete_spalten(summen):
        # Individuelle Speicher-Spalten vorhanden
        _batterie_legacy_gegen_speicher_summe(
            warnungen, summen, batterie_ladung_explicit, batterie_entladung_explicit,
        )

    elif batterie_ladung_explicit is not None or batterie_entladung_explicit is not None:
        if kontext.speicher_vorhanden:
            # Legacy-Werte vorhanden, aber keine individuellen Spalten
            # -> Auf Speicher verteilen
            speicher_list = [inv for inv in kontext.investitionen if inv.typ == "speicher"]
            migration_warnungen = await _distribute_legacy_battery_to_storages(
                db,
                batterie_ladung_explicit or 0,
                batterie_entladung_explicit or 0,
                speicher_list,
                jahr, monat, kontext.ueberschreiben,
                source="manual:csv_backup", writer="csv_backup_restore",
            )
            warnungen.extend(migration_warnungen)
            # N-722: die als 0 gelieferte Seite kommt ebenfalls an (wie N-718 am Portal); leer bleibt leer.
            await _speicher_nullen_verteilen(
                db, batterie_ladung_explicit, batterie_entladung_explicit, speicher_list,
                jahr, monat, kontext.ueberschreiben,
                source="manual:csv_backup", writer="csv_backup_restore",
            )
            # Für Legacy-Feld in Monatsdaten (Fallback)
            batterie_ladung = batterie_ladung_explicit
            batterie_entladung = batterie_entladung_explicit
        else:
            # Keine Speicher angelegt - Legacy akzeptieren
            batterie_ladung = batterie_ladung_explicit
            batterie_entladung = batterie_entladung_explicit
            if "Keine Speicher als Investitionen angelegt" not in warnungen:
                warnungen.append("Keine Speicher als Investitionen angelegt.")

    return batterie_ladung, batterie_entladung


def _speicher_werte_aus_geraete_spalten(summen: dict) -> bool:
    """Trägt die Zeile Speicher-Werte aus Geräte-Spalten (Speicher, BKW-Speicher)? Dann gelten sie, nicht die Alt-Spalten
    `Batterie_*` — eine Regel für `_batterie` (Monatszeile, Verteiler) und `_alt_spalten_ziele_der_zeile` (N-747)."""
    return summen["batterie_ladung_sum"] > 0 or summen["batterie_entladung_sum"] > 0


def _batterie_legacy_gegen_speicher_summe(
    warnungen: list[str],
    summen: dict,
    batterie_ladung_explicit: Optional[float],
    batterie_entladung_explicit: Optional[float],
) -> None:
    """Phase Z8a (RF-14): Legacy-Batteriespalten neben Speicher-Spalten — nur Warnungen, die Speicher-Werte gelten."""
    if batterie_ladung_explicit is not None:
        if abs(batterie_ladung_explicit - summen["batterie_ladung_sum"]) <= 0.5:
            if "Legacy-Spalte 'Batterie_Ladung_kWh' ist redundant" not in warnungen:
                warnungen.append("Legacy-Spalte 'Batterie_Ladung_kWh' ist redundant.")
        else:
            # Abweichung: Speicher-Werte haben Vorrang
            if "Legacy 'Batterie_Ladung_kWh' weicht von Speicher-Summe ab" not in warnungen:
                warnungen.append(
                    "Legacy 'Batterie_Ladung_kWh' weicht von Speicher-Summe ab. "
                    "Speicher-Werte werden verwendet."
                )

    if batterie_entladung_explicit is not None:
        if abs(batterie_entladung_explicit - summen["batterie_entladung_sum"]) <= 0.5:
            if "Legacy-Spalte 'Batterie_Entladung_kWh' ist redundant" not in warnungen:
                warnungen.append("Legacy-Spalte 'Batterie_Entladung_kWh' ist redundant.")
        else:
            # Abweichung: Speicher-Werte haben Vorrang
            if "Legacy 'Batterie_Entladung_kWh' weicht von Speicher-Summe ab" not in warnungen:
                warnungen.append(
                    "Legacy 'Batterie_Entladung_kWh' weicht von Speicher-Summe ab. "
                    "Speicher-Werte werden verwendet."
                )


def _bilanz(
    pv_erzeugung: Optional[float],
    einspeisung: float,
    netzbezug: float,
    batterie_ladung: Optional[float],
    batterie_entladung: Optional[float],
    summen: dict,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Phase Z9 (RF-14): Direkt-, Eigen- und Gesamtverbrauch der Monatszeile (Bestand, Legacy-Trio)."""
    # Berechnungen
    batterie_ladung_for_calc = batterie_ladung if batterie_ladung is not None else summen["batterie_ladung_sum"] if summen["batterie_ladung_sum"] > 0 else 0
    batterie_entladung_for_calc = batterie_entladung if batterie_entladung is not None else summen["batterie_entladung_sum"] if summen["batterie_entladung_sum"] > 0 else 0

    direktverbrauch = None
    eigenverbrauch = None
    gesamtverbrauch = None
    if pv_erzeugung is not None:
        direktverbrauch = max(0, pv_erzeugung - einspeisung - batterie_ladung_for_calc)
        eigenverbrauch = direktverbrauch + batterie_entladung_for_calc
        gesamtverbrauch = eigenverbrauch + netzbezug
    elif einspeisung > 0 or netzbezug > 0:
        gesamtverbrauch = netzbezug + einspeisung
    return direktverbrauch, eigenverbrauch, gesamtverbrauch


async def _schreibe_monatszeile(
    db: AsyncSession,
    anlage_id: int,
    jahr: int,
    monat: int,
    existing_md: Optional[Monatsdaten],
    werte: _ZeilenWerte,
) -> None:
    """Phase Z10 (RF-14): Monatszeile — UPDATE je geliefertem Feld in fester Folge bzw. INSERT mit Stempeln."""
    # Etappe 3d Päckchen 2: Top-Level-Felder über write_with_provenance
    # bei UPDATE (Hierarchie + Audit-Log greifen), seed_provenance bei
    # frischer INSERT-Row (kein Audit-Spam — Backup-Restore kann hunderte
    # Zeilen × Felder umfassen).
    # N-740: die Netzfelder mit dem ROHWERT — eine leere Zelle liefert nichts und
    # bekommt keinen Stempel (die neue Zeile trägt die NOT-NULL-0 ohne Herkunft,
    # also «nicht erfasst», N-734; eine vorhandene Zeile behält ihren Wert).
    _CSV_BACKUP_FIELDS_TOP = [
        ("einspeisung_kwh", werte.einspeisung_raw),
        ("netzbezug_kwh", werte.netzbezug_raw),
        ("pv_erzeugung_kwh", werte.pv_erzeugung),
        ("direktverbrauch_kwh", werte.direktverbrauch),
        ("eigenverbrauch_kwh", werte.eigenverbrauch),
        ("gesamtverbrauch_kwh", werte.gesamtverbrauch),
        ("batterie_ladung_kwh", werte.batterie_ladung),
        ("batterie_entladung_kwh", werte.batterie_entladung),
        ("globalstrahlung_kwh_m2", werte.globalstrahlung),
        ("sonnenstunden", werte.sonnenstunden),
        ("netzbezug_durchschnittspreis_cent", werte.durchschnittspreis),
        ("einspeise_durchschnittspreis_cent", werte.einspeise_preis),
    ]
    if existing_md:
        # UPDATE: Hierarchie greift — manual:csv_backup ist MANUAL,
        # blockiert external:cloud_import:*, gleichauf mit manual:form
        # (Last-Writer-Wins).
        for field_name, value in _CSV_BACKUP_FIELDS_TOP:
            if value is not None:
                await write_with_provenance(
                    db, existing_md, field_name, value,
                    source="manual:csv_backup", writer="csv_backup_restore",
                )
        existing_md.notizen = werte.notizen
        existing_md.datenquelle = "csv"
    else:
        md = Monatsdaten(
            anlage_id=anlage_id,
            jahr=jahr,
            monat=monat,
            einspeisung_kwh=werte.einspeisung,
            netzbezug_kwh=werte.netzbezug,
            pv_erzeugung_kwh=werte.pv_erzeugung,
            direktverbrauch_kwh=werte.direktverbrauch,
            eigenverbrauch_kwh=werte.eigenverbrauch,
            gesamtverbrauch_kwh=werte.gesamtverbrauch,
            batterie_ladung_kwh=werte.batterie_ladung,
            batterie_entladung_kwh=werte.batterie_entladung,
            globalstrahlung_kwh_m2=werte.globalstrahlung,
            sonnenstunden=werte.sonnenstunden,
            netzbezug_durchschnittspreis_cent=werte.durchschnittspreis,
            einspeise_durchschnittspreis_cent=werte.einspeise_preis,
            notizen=werte.notizen,
            datenquelle="csv"
        )
        seed_provenance(
            md,
            source="manual:csv_backup",
            writer="csv_backup_restore",
            fields=[fn for fn, val in _CSV_BACKUP_FIELDS_TOP if val is not None],
        )
        db.add(md)


@router.get("/export/{anlage_id}")
async def export_csv(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Filter nach Jahr"),
    include_investitionen: bool = Query(True, description="Investitions-Monatsdaten einschließen"),
    db: AsyncSession = Depends(get_db)
):
    """Exportiert Monatsdaten als CSV."""
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    # Monatsdaten laden
    query = select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    if jahr:
        query = query.where(Monatsdaten.jahr == jahr)
    query = query.order_by(Monatsdaten.jahr, Monatsdaten.monat)

    result = await db.execute(query)
    monatsdaten = result.scalars().all()

    # Investitionen und deren Monatsdaten laden
    investitionen = []
    inv_monatsdaten_map: dict[tuple[int, int, int], dict] = {}

    if include_investitionen:
        # KEIN aktiv-Filter (Issue #123): Export historischer Daten soll
        # vollständig sein, auch für später stillgelegte Komponenten.
        inv_result = await db.execute(
            select(Investition)
            .where(Investition.anlage_id == anlage_id)
            .order_by(Investition.id)
        )
        investitionen = sort_investitionen_nach_typ(inv_result.scalars().all())

        for inv in investitionen:
            imd_query = select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == inv.id
            )
            if jahr:
                imd_query = imd_query.where(InvestitionMonatsdaten.jahr == jahr)

            imd_result = await db.execute(imd_query)
            for imd in imd_result.scalars().all():
                inv_monatsdaten_map[(inv.id, imd.jahr, imd.monat)] = imd.verbrauch_daten or {}

    # CSV erstellen
    output = StringIO()
    writer = csv.writer(output, delimiter=";")

    header = ["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh"]

    # Bei dynamischem Tarif: Durchschnittspreis-Spalte
    export_tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    export_allgemein = export_tarife.get("allgemein")
    hat_dynamisch_export = ist_dynamisch(export_allgemein)
    if hat_dynamisch_export:
        header.append("Durchschnittspreis_Cent")
    # #392: bei variabler Einspeisevergütung die Monatssatz-Spalte
    hat_variable_einspeisung_export = bool(
        export_allgemein and getattr(export_allgemein, "einspeisung_variabel", False)
    )
    if hat_variable_einspeisung_export:
        header.append("Einspeiseverguetung_Cent")

    inv_columns: list[tuple[Investition, str, str]] = []

    for inv in investitionen:
        if inv.typ in ("wechselrichter",):
            continue
        prefix = _sanitize_column_name(inv.bezeichnung)

        felder = get_felder_fuer_investition(inv.typ, inv.parameter)
        for feld_def in felder:
            csv_suffix = feld_def.get("csv_suffix", feld_def["feld"])
            inv_columns.append((inv, csv_suffix, feld_def["feld"]))
            header.append(f"{prefix}_{csv_suffix}")

        # Sonderkosten für alle Investitionen (nicht in Registry)
        inv_columns.append((inv, "Sonderkosten_Euro", "sonderkosten_euro"))
        inv_columns.append((inv, "Sonderkosten_Notiz", "sonderkosten_notiz"))
        header.extend([f"{prefix}_Sonderkosten_Euro", f"{prefix}_Sonderkosten_Notiz"])

    header.append("Notizen")
    writer.writerow(header)

    # Fallback-Keys: Manche Felder wurden unter verschiedenen Namen gespeichert
    FALLBACK_KEYS = {
        "pv_erzeugung_kwh": "erzeugung_kwh",  # BKW: MonatsdatenForm (alt) vs. Monatsabschluss
        "verbrauch_sonstig_kwh": "verbrauch_kwh",  # Sonstiges Verbraucher
        "ladung_netz_kwh": "speicher_ladung_netz_kwh",  # Speicher Arbitrage: kanonisch → Legacy
        "v2h_entladung_kwh": "entladung_v2h_kwh",  # E-Auto V2H: kanonisch → Legacy
    }

    # Hilfsfunktion: Dezimaltrennzeichen für deutsche CSV (Komma statt Punkt)
    def fmt(value):
        if value is None or value == "":
            return ""
        if isinstance(value, (int, float)):
            return str(value).replace(".", ",")
        return value

    for md in monatsdaten:
        row = [
            md.jahr,
            md.monat,
            fmt(md.einspeisung_kwh),
            fmt(md.netzbezug_kwh),
        ]
        if hat_dynamisch_export:
            # `is not None`, nicht truthy — ein Monats-Ø von 0,0 ct ist bei
            # dynamischem Tarif real (Negativpreis-Stunden) und ging beim
            # Export sonst als Leerfeld verloren (0-Werte-Regel, CLAUDE.md).
            row.append(
                fmt(md.netzbezug_durchschnittspreis_cent)
                if md.netzbezug_durchschnittspreis_cent is not None else ""
            )
        if hat_variable_einspeisung_export:
            # `is not None`, nicht truthy — 0 ct ist ein gepflegter Wert und
            # muss den Rundlauf überleben (dieselbe Regel wie der Resolver).
            row.append(
                fmt(md.einspeise_durchschnittspreis_cent)
                if md.einspeise_durchschnittspreis_cent is not None else ""
            )

        for inv, suffix, data_key in inv_columns:
            inv_data = inv_monatsdaten_map.get((inv.id, md.jahr, md.monat), {})
            # Sonstige Positionen: aus strukturiertem Array berechnen
            if data_key == "sonderkosten_euro":
                summen = berechne_sonstige_summen(inv_data)
                net = summen["ausgaben_euro"] - summen["ertraege_euro"]
                row.append(fmt(round(net, 2)) if net != 0 else "")
            elif data_key == "sonderkosten_notiz":
                positionen = get_sonstige_positionen(inv_data)
                if positionen:
                    row.append("; ".join(
                        f"{p.get('bezeichnung', '')}: {p.get('betrag', 0)}€ ({p.get('typ', '')})"
                        for p in positionen
                    ))
                else:
                    row.append("")
            else:
                value = inv_data.get(data_key, "")
                # Fallback-Key versuchen wenn primärer Key leer
                if value == "" and data_key in FALLBACK_KEYS:
                    value = inv_data.get(FALLBACK_KEYS[data_key], "")
                row.append(fmt(value) if value != "" else "")

        row.append(md.notizen or "")
        writer.writerow(row)

    output.seek(0)
    # Anlagenname sanitisieren (Umlaute → ae/oe/ue, Sonderzeichen → _) — HTTP-Header
    # erlaubt nur Latin-1, ungequoteted nur Token-Zeichen (kein Leerzeichen, kein ;, " etc.).
    # Ohne Sanitization kann der Header bei Sonderzeichen/Umlauten ungültig werden, was
    # HA-Ingress oder fetch() als Stream-Abbruch interpretiert ("Failed to fetch"; #220).
    safe_name = _sanitize_column_name(anlage.anlagenname) or "anlage"
    filename = f"eedc_export_{safe_name}_{jahr or 'alle'}.csv"

    # BOM für Excel/LibreOffice UTF-8-Erkennung
    csv_content = "\ufeff" + output.getvalue()

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
