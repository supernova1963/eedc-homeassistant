"""
HA-Statistik-Sammelimport — der Schreibweg (Serie „Funktion vor Datei", RF-5).

Die Route `POST /api/ha-statistics/import/{anlage_id}` steht in `api/routes/ha_statistics.py::import_ha_statistics`
und ruft je Monat den HA-Leser (Recorder-Aufrufe bleiben in jener Datei — `test_ha_last_und_index.py` führt sie
datei-genau als Restschuld); was danach in die Datenbank geht, steht hier. Dazu der eine Helfer, den Vorschau und
Import teilen (`ha_geraetewerte`): die Vorschau muss dieselbe Menge zeigen wie der Import schreibt.
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.field_definitions import FELD_LABELS
from backend.core.field_definitions import basis_feld_key, ist_heimlade_mengen_feld, ist_zaehler_differenz_feld
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.provenance import ABGELEITET_KWP_ANTEIL
from backend.services.provenance import (
    remove_json_subkey_with_provenance,
    seed_provenance,
    write_json_subkey_with_provenance,
    write_with_provenance,
)

# HA Long-Term Statistics ist eine externe autoritative Quelle
# (Source `external:ha_statistics`, Stufe 2). Manuelle Form-Werte (Stufe 1)
# überleben den Import strukturell — der Resolver weist HA-Stats-
# Schreibversuche auf manual:form-Felder mit rejected_lower_priority ab.
_HA_STATS_SOURCE = "external:ha_statistics"
_HA_STATS_WRITER = "ha_statistics_import"


@dataclass
class ImportBilanz:
    """Zähler und Sammellisten eines Import-Laufs (vorher lokale Variablen der Route)."""
    importiert: int = 0
    uebersprungen: int = 0
    ueberschrieben: int = 0
    fehler: list[str] = field(default_factory=list)
    # N-240: Monate, die nur Gerätewerte bekommen haben — gesammelt statt je
    # Monat gemeldet, sonst stünde derselbe Satz zwölfmal im Ergebnis.
    monate_ohne_zaehlerwerte: list[tuple[int, int]] = field(default_factory=list)
    # E4b Teil A, Entscheid H-A1: Monate, deren PV-Gesamtzähler mangels Zählerzeile nicht gespeichert wurde.
    pv_ohne_zeile_monate: list[tuple[int, int]] = field(default_factory=list)


@dataclass(frozen=True)
class _BasisWerte:
    """Die Basis-Zählerwerte eines Monats nach der Feld-Auswahl."""
    import_einspeisung: bool
    import_netzbezug: bool
    einspeisung: Optional[float]
    netzbezug: Optional[float]
    pv_gesamt: Optional[float]

    @property
    def hat_zaehlerwert(self) -> bool:
        # ⚠ **Die zweite Bedingung ist neu (13.08., N-240) und korrigiert eine
        # erfundene Messung.** Ohne sie legte der Import bei aktiven, aber
        # NICHT zugeordneten Basis-Feldern eine Zeile mit `0/0` an (an echten
        # Objekten gemessen): eine Einspeisung und ein Netzbezug von exakt
        # null, die niemand gemessen hat — und die der Plausibilitäts-Check
        # prompt als „beide 0" meldete. `is not None` statt truthiness, damit
        # ein echt gemessener 0-Wert weiterhin durchkommt.
        return (
            (self.import_einspeisung and self.einspeisung is not None)
            or (self.import_netzbezug and self.netzbezug is not None)
        )


async def _entferne_eigene_zerlegung(db: AsyncSession, anlage_id: int, jahr: int, monat: int) -> int:
    """Entfernt die Modulwerte eines Monats, die DIESER Import früher als Zerlegung des Anlagen-PV-Zählers
    geschrieben hat (HA-Bauform E4b Teil A, Entscheid H-A2).

    Bis E4b verteilte der Sammelimport den Zähler auf die Module ohne eigenen Wert (N-533, ``_verteile_anlagen_pv``)
    und speicherte ihn selbst nicht. Seit E4b steht er als Anlagenwert in der Zählerzeile — eine alte Zerlegung daneben
    wäre derselbe Zähler ein zweites Mal: die Leseseite behält einen gespeicherten Wert MIT Marke als Zahl (#352,
    ``resolve_pv_je_modul``), der Anlagenwert füllte nur noch, was übrig bleibt (gemessen: Ost/West 60/40 + BKW 4,5
    ⇒ Monat 104,5 statt 100; ein Balkonkraftwerk ohne Wert behielt 0).

    Entfernt wird nur, was BEIDES trägt: Schreiber ``ha_statistics_import`` UND Marke ``kwp_anteil``. Messwerte
    (ohne Marke — auch die früheren Ein-Empfänger-Werte, die sich von einer Messung nicht unterscheiden lassen),
    Handeingaben und Werte anderer Schreiber bleiben. Der Aufrufer ruft nur mit „überschreiben" (der Anwender hat
    den Monat ausdrücklich neu angefordert). Liefert die Zahl der entfernten Werte.
    """
    zeilen = (await db.execute(
        select(InvestitionMonatsdaten).join(Investition, Investition.id == InvestitionMonatsdaten.investition_id).where(
            and_(
                Investition.anlage_id == anlage_id,
                Investition.typ == "pv-module",
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
    )).scalars().all()
    entfernt = 0
    for imd in zeilen:
        eintrag = (imd.source_provenance or {}).get("verbrauch_daten.pv_erzeugung_kwh")
        if not isinstance(eintrag, dict):
            continue
        if eintrag.get("writer") != _HA_STATS_WRITER or eintrag.get("abgeleitet") != ABGELEITET_KWP_ANTEIL:
            continue
        if await remove_json_subkey_with_provenance(
            db, imd, "verbrauch_daten", "pv_erzeugung_kwh",
            source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
            decision_reason=(
                "Zerlegung des Anlagen-PV-Zählers entfernt (HA-Bauform E4b) — der Zähler steht jetzt als Anlagenwert "
                "in der Zählerzeile, die Leseseite verteilt ihn"
            ),
        ) is not None:
            entfernt += 1
    return entfernt


def _hat_anlagenwert(vorbestand: Monatsdaten) -> bool:
    """Trägt die Zählerzeile schon einen Anlagen-PV-Wert? (E4b Teil A — Vorbestands-Regel des Sammelimports.)

    Liest die Rohspalte ``Monatsdaten.pv_erzeugung_kwh`` bewusst: die Frage handelt VOM gespeicherten Feld („steht
    dort schon etwas, das ohne ‚überschreiben' bleiben muss?"), nicht von der Anlagen-PV — ein aufgelöster Wert
    (P7) beantwortete sie nicht. Dieselbe Schwelle wie bei Einspeisung und Netzbezug (0,1 kWh)."""
    return (vorbestand.pv_erzeugung_kwh or 0) > 0.1


# =============================================================================
# Gemeinsamer Helfer von Vorschau und Import
# =============================================================================

def ha_geraetewerte(felder: dict, sensor_values: dict, erlaubte_felder: Optional[list] = None) -> dict:
    """Die HA-Monatswerte der Zählerfelder EINES Geräts — `{feld: differenz}` in der Reihenfolge des Mappings.

    Vorschau und Sammelimport fragen dieselbe Menge: die Vorschau muss zeigen, was der Import schreibt, sonst steht
    dort ein Wert, der nie ankommt. ``erlaubte_felder`` ist die Feld-Auswahl des Imports (``None`` = alle).
    """
    inv_werte = {}
    for feld, feld_config in felder.items():
        # Nur importieren wenn Feld erlaubt
        # erlaubte_felder kann raw Keys ("pv_erzeugung_kwh") ODER Labels ("PV Erzeugung") enthalten
        if erlaubte_felder is not None:
            feld_label = FELD_LABELS.get(feld, feld)
            if feld not in erlaubte_felder and feld_label not in erlaubte_felder:
                continue

        # `sensor_values` sind Zählerdifferenzen (MAX−MIN). Bei
        # einem Preis-/Kosten-Feld wäre das die Monats-Spreizung —
        # und die landete hier persistent in `verbrauch_daten`.
        # N-666: Innengeräte-Keys (`…_kwh-3`) über `basis_feld_key`.
        if not ist_zaehler_differenz_feld(basis_feld_key(feld)):
            continue

        if not (feld_config and feld_config.get("sensor_id")):
            continue
        sensor_id = feld_config["sensor_id"]
        if sensor_id in sensor_values:
            inv_werte[feld] = sensor_values[sensor_id]
    return inv_werte


# =============================================================================
# Ein Monat des Sammelimports
# =============================================================================

def _basis_aktiv(raw_key: str, basis_felder_auswahl: Optional[list]) -> bool:
    # Prüfen ob Basis-Felder importiert werden sollen.
    # basis_felder_auswahl kann raw Keys ("einspeisung") ODER Labels
    # ("Einspeisung") enthalten, je nachdem was die Vorschau geliefert hat.
    if basis_felder_auswahl is None:
        return True
    label = FELD_LABELS.get(raw_key, raw_key)
    return raw_key in basis_felder_auswahl or label in basis_felder_auswahl


def _basis_wert(basis_mapping: dict, sensor_values: dict, key: str, aktiv: bool) -> Optional[float]:
    if aktiv and basis_mapping.get(key, {}).get("sensor_id"):
        return sensor_values.get(basis_mapping[key]["sensor_id"])
    return None


def _waehle_basiswerte(sensor_mapping: dict, sensor_values: dict, basis_felder_auswahl: Optional[list]) -> _BasisWerte:
    # Basis-Werte extrahieren (nur wenn nicht explizit ausgeschlossen)
    import_einspeisung = _basis_aktiv("einspeisung", basis_felder_auswahl)
    import_netzbezug = _basis_aktiv("netzbezug", basis_felder_auswahl)

    basis_mapping = sensor_mapping.get("basis", {})
    einspeisung = _basis_wert(basis_mapping, sensor_values, "einspeisung", import_einspeisung)
    netzbezug = _basis_wert(basis_mapping, sensor_values, "netzbezug", import_netzbezug)
    # HA-Bauform E4b Teil A: der Anlagen-PV-Zähler (`basis.pv_gesamt`) gehört in die Zählerzeile — als
    # Anlagenwert `Monatsdaten.pv_erzeugung_kwh`, genau wie „Aus HA laden" ihn seit N-622 über das Formular
    # speichert. Er ist dort EINGANG der P7-Auflösung (`resolve_pv_je_modul`): Geräte mit eigenem Wert
    # behalten ihn, der Rest geht nach kWp auf Module UND Balkonkraftwerke ohne eigenen Wert (N-611/N-621).
    pv_gesamt = _basis_wert(
        basis_mapping, sensor_values, "pv_gesamt", _basis_aktiv("pv_gesamt", basis_felder_auswahl),
    )
    return _BasisWerte(import_einspeisung, import_netzbezug, einspeisung, netzbezug, pv_gesamt)


async def _lege_zaehlerzeile_an(db: AsyncSession, anlage_id: int, jahr: int, monat: int, basis: _BasisWerte) -> Monatsdaten:
    # Neu erstellen — fresh row, kein Hierarchie-Konflikt möglich
    md = Monatsdaten(
        anlage_id=anlage_id,
        jahr=jahr,
        monat=monat,
        einspeisung_kwh=basis.einspeisung if basis.import_einspeisung else 0,
        netzbezug_kwh=basis.netzbezug if basis.import_netzbezug else 0,
        pv_erzeugung_kwh=basis.pv_gesamt,
        datenquelle="ha_statistics"
    )
    db.add(md)
    await db.flush()
    # N-740: gestempelt wird, was geliefert wurde (wie der Update-Zweig) — ein gewähltes Feld ohne Sensorwert
    # bleibt DB-Default 0 ohne Herkunft, also «nicht erfasst» (N-734), statt als gemessene 0 zu gelten.
    fresh_fields = [
        f for f in ("einspeisung_kwh", "netzbezug_kwh")
        if (f == "einspeisung_kwh" and basis.import_einspeisung and basis.einspeisung is not None)
        or (f == "netzbezug_kwh" and basis.import_netzbezug and basis.netzbezug is not None)
    ] + (["pv_erzeugung_kwh"] if basis.pv_gesamt is not None else [])
    if fresh_fields:
        seed_provenance(
            md, source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
            fields=fresh_fields,
        )
    return md


async def _schreibe_basisfeld(db: AsyncSession, md: Monatsdaten, feld: str, wert: float, *, vorbestand: bool,
                              ueberschreiben: bool) -> bool:
    """Ein Basis-Feld einer vorhandenen Zeile — Vorbestand bleibt ohne „überschreiben"; True, wenn geschrieben."""
    if vorbestand and not ueberschreiben:
        return False
    result = await write_with_provenance(
        db, md, feld, wert,
        source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
    )
    return result.applied


async def _schreibe_zaehlerzeile(db: AsyncSession, md: Monatsdaten, basis: _BasisWerte, ueberschreiben: bool) -> bool:
    # Existiert - selektiv via Resolver. Manuelle Werte (manual:form,
    # Stufe 1) gewinnen automatisch gegen HA-Stats (Stufe 2).
    # Das `ueberschreiben`-Flag steuert nur die Same-Source-Logik
    # bei bereits importierten HA-Stats-Werten.
    basis_importiert = False
    hat_einspeisung = (md.einspeisung_kwh or 0) > 0.1
    hat_netzbezug = (md.netzbezug_kwh or 0) > 0.1

    if basis.import_einspeisung and basis.einspeisung is not None:
        if await _schreibe_basisfeld(db, md, "einspeisung_kwh", basis.einspeisung,
                                     vorbestand=hat_einspeisung, ueberschreiben=ueberschreiben):
            basis_importiert = True

    if basis.import_netzbezug and basis.netzbezug is not None:
        if await _schreibe_basisfeld(db, md, "netzbezug_kwh", basis.netzbezug,
                                     vorbestand=hat_netzbezug, ueberschreiben=ueberschreiben):
            basis_importiert = True

    # E4b Teil A: ein gespeicherter Anlagenwert bleibt ohne „überschreiben" stehen — dieselbe
    # Vorbestands-Regel wie Einspeisung und Netzbezug darüber (Schwelle 0,1 kWh).
    if basis.pv_gesamt is not None:
        if await _schreibe_basisfeld(db, md, "pv_erzeugung_kwh", basis.pv_gesamt,
                                     vorbestand=_hat_anlagenwert(md), ueberschreiben=ueberschreiben):
            basis_importiert = True

    if basis_importiert:
        md.datenquelle = "ha_statistics"
    return basis_importiert


async def _importiere_basis(db: AsyncSession, anlage_id: int, jahr: int, monat: int, basis: _BasisWerte,
                            ueberschreiben: bool) -> tuple[bool, bool]:
    """Zählerzeile des Monats: laden, anlegen oder selektiv schreiben. → (basis_importiert, pv_ohne_zeile)."""
    # Monatsdaten laden oder erstellen — nur wenn Basis-Felder importiert
    # werden UND tatsächlich ein Zählerwert vorliegt.
    #
    # E4b Teil A: der Anlagenwert allein legt keine Zeile an (er hat keine Einspeisung und keinen Netzbezug,
    # N-240) — er wird aber in eine VORHANDENE Zeile geschrieben, auch wenn nur er ausgewählt ist.
    hat_zaehlerwert = basis.hat_zaehlerwert
    md = None
    if hat_zaehlerwert or basis.pv_gesamt is not None:
        result = await db.execute(
            select(Monatsdaten).where(
                and_(
                    Monatsdaten.anlage_id == anlage_id,
                    Monatsdaten.jahr == jahr,
                    Monatsdaten.monat == monat
                )
            )
        )
        md = result.scalar_one_or_none()
    pv_ohne_zeile = basis.pv_gesamt is not None and md is None and not hat_zaehlerwert
    basis_importiert = False
    if md is None and hat_zaehlerwert:
        md = await _lege_zaehlerzeile_an(db, anlage_id, jahr, monat, basis)
        basis_importiert = True
    elif md is not None:
        basis_importiert = await _schreibe_zaehlerzeile(db, md, basis, ueberschreiben)

    # E4b Teil A, Entscheid H-A2: mit „überschreiben" fällt die frühere Zerlegung desselben Zählers weg — der
    # Anlagenwert steht jetzt in der Zeile, die Leseseite verteilt ihn (sonst bliebe ein Altbestand-Monat wie
    # er war: Module mit dem ganzen Zähler, ein BKW ohne Wert bei 0, ein BKW mit Wert doppelt).
    if ueberschreiben and basis.pv_gesamt is not None and md is not None and _hat_anlagenwert(md):
        if await _entferne_eigene_zerlegung(db, anlage_id, jahr, monat):
            basis_importiert = True
    return basis_importiert, pv_ohne_zeile


def _feldauswahl_der_investition(inv_id_str: str, inv_felder_auswahl: Optional[dict]) -> tuple[bool, Optional[list]]:
    """(nimmt teil?, erlaubte Felder — None = alle)."""
    # Prüfen ob diese Investition importiert werden soll
    if inv_felder_auswahl is None:
        return True, None  # Alle Felder
    if inv_id_str not in inv_felder_auswahl:
        return False, None  # Diese Investition überspringen
    erlaubte_felder = inv_felder_auswahl[inv_id_str]
    if not erlaubte_felder:
        return False, None  # Keine Felder für diese Investition
    return True, erlaubte_felder


async def _schreibe_geraetewerte(db: AsyncSession, inv_id: int, inv_typ: Optional[str], jahr: int, monat: int,
                                 inv_werte: dict, ueberschreiben: bool) -> bool:
    """Die Gerätezeile des Monats laden oder anlegen und die Werte einbuchen; True, wenn geschrieben."""
    # InvestitionMonatsdaten laden oder erstellen
    imd_result = await db.execute(
        select(InvestitionMonatsdaten).where(
            and_(
                InvestitionMonatsdaten.investition_id == inv_id,
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat
            )
        )
    )
    imd = imd_result.scalar_one_or_none()

    if imd is None:
        imd = InvestitionMonatsdaten(
            investition_id=inv_id,
            jahr=jahr,
            monat=monat,
            verbrauch_daten=inv_werte
        )
        db.add(imd)
        await db.flush()
        if inv_werte:
            seed_provenance(
                imd, source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
                json_subkeys={"verbrauch_daten": list(inv_werte.keys())},
            )
        return True

    # Merge mit existierenden Daten — Per-Sub-Key durch Resolver.
    # manual:form-Sub-Keys überleben den Import (Hierarchie greift).
    if imd.verbrauch_daten is None:
        imd.verbrauch_daten = {}

    inv_importiert = False
    for feld, wert in inv_werte.items():
        vorhandener_wert = imd.verbrauch_daten.get(feld)
        # N-555 Regel 4 (E1 eng): bei einem Heimlade-Mengenfeld ist
        # eine gespeicherte 0 ein Wert („die Wallbox hat nicht
        # geladen") und wird — wie jeder andere Wert — nur mit
        # „überschreiben" ersetzt. Überall sonst gilt die 0 weiter
        # als leer (PV-Module: eine eingefrorene Quelle ergäbe 0).
        leer = vorhandener_wert is None or (
            vorhandener_wert == 0
            and not ist_heimlade_mengen_feld(inv_typ, feld)
        )
        if not (leer or ueberschreiben):
            continue
        result = await write_json_subkey_with_provenance(
            db, imd, "verbrauch_daten", feld, wert,
            source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
        )
        if result.applied:
            inv_importiert = True
    return inv_importiert


async def _importiere_geraete(db: AsyncSession, anlage_id: int, jahr: int, monat: int, sensor_mapping: dict,
                              sensor_values: dict, inv_felder_auswahl: Optional[dict], ueberschreiben: bool) -> bool:
    # InvestitionMonatsdaten verarbeiten
    inv_mapping = sensor_mapping.get("investitionen", {})
    inv_importiert = False

    # Gültige Investitions-IDs laden (verwaiste Mapping-Einträge ignorieren)
    inv_result = await db.execute(
        select(Investition.id, Investition.typ).where(Investition.anlage_id == anlage_id)
    )
    # N-555: der Typ je Investition für die Heimlade-Regel unten (Regel 4).
    inv_typ_je_id = {str(r[0]): r[1] for r in inv_result.all()}
    gueltige_inv_ids = set(inv_typ_je_id)

    for inv_id_str, inv_config in inv_mapping.items():
        if inv_id_str not in gueltige_inv_ids:
            continue  # Verwaister sensor_mapping-Eintrag
        inv_id = int(inv_id_str)
        teilnehmen, erlaubte_felder = _feldauswahl_der_investition(inv_id_str, inv_felder_auswahl)
        if not teilnehmen:
            continue

        felder = inv_config.get("felder", {})

        # Werte aus HA extrahieren (nur erlaubte Felder)
        inv_werte = ha_geraetewerte(felder, sensor_values, erlaubte_felder)

        if not inv_werte:
            continue

        if await _schreibe_geraetewerte(db, inv_id, inv_typ_je_id.get(inv_id_str), jahr, monat, inv_werte,
                                        ueberschreiben):
            inv_importiert = True
    return inv_importiert


async def _schliesse_monat_ab(db: AsyncSession, bilanz: ImportBilanz, anlage_id: int, jahr: int, monat: int, *,
                              basis_importiert: bool, inv_importiert: bool, hat_zaehlerwert: bool,
                              pv_ohne_zeile: bool) -> None:
    # E4b Teil A, Entscheid H-A1: ohne Zählerzeile hat der Anlagenwert keinen Ort (Einspeisung/Netzbezug sind
    # Pflicht, eine 0/0-Zeile wäre erfunden — N-240). Er wird NICHT gespeichert und nicht auf Module verteilt
    # (bis E4b: `_verteile_anlagen_pv`); der Monat steht in der Warnung.
    if pv_ohne_zeile:
        bilanz.pv_ohne_zeile_monate.append((jahr, monat))

    # N-240: Gerätewerte angekommen, aber keine Zählerzeile für den Monat
    # — der Zustand aus #349, hier auf dem HA-Weg. Geprüft wird die
    # ZEILE, nicht die Zuordnung: existiert sie aus einem früheren Lauf
    # oder aus dem Monatsabschluss, ist alles in Ordnung.
    if inv_importiert and not hat_zaehlerwert:
        vorhandene = await db.execute(
            select(Monatsdaten.id).where(
                and_(
                    Monatsdaten.anlage_id == anlage_id,
                    Monatsdaten.jahr == jahr,
                    Monatsdaten.monat == monat,
                )
            )
        )
        if vorhandene.scalar_one_or_none() is None:
            bilanz.monate_ohne_zaehlerwerte.append((jahr, monat))

    # Zähler aktualisieren
    if basis_importiert or inv_importiert:
        bilanz.importiert += 1
    else:
        bilanz.uebersprungen += 1


async def importiere_monat(db: AsyncSession, anlage_id: int, sensor_mapping: dict, monat_req, ha_response,
                           ueberschreiben: bool, bilanz: ImportBilanz) -> None:
    """Schreibt EINEN Monat aus der HA-Antwort; Ausnahmen fängt der Aufrufer je Monat (`fehler`)."""
    jahr = monat_req.jahr
    monat = monat_req.monat

    # Sensor-Werte zu Dict mappen
    sensor_values = {s.sensor_id: s.differenz for s in ha_response.sensoren}

    basis = _waehle_basiswerte(sensor_mapping, sensor_values, monat_req.basis_felder)  # None = alle, [] = keine
    basis_importiert, pv_ohne_zeile = await _importiere_basis(db, anlage_id, jahr, monat, basis, ueberschreiben)
    inv_importiert = await _importiere_geraete(
        db, anlage_id, jahr, monat, sensor_mapping, sensor_values,
        monat_req.investition_felder,  # None = alle, {} = keine
        ueberschreiben,
    )
    await _schliesse_monat_ab(
        db, bilanz, anlage_id, jahr, monat, basis_importiert=basis_importiert, inv_importiert=inv_importiert,
        hat_zaehlerwert=basis.hat_zaehlerwert, pv_ohne_zeile=pv_ohne_zeile,
    )
