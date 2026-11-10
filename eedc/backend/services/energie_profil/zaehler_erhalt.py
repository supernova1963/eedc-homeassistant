"""N-791 (Melder ottokar, simon42 PN T95600): Werkbank-Lauf «Zähler neu, Leistungsverlauf bleibt».

**Wozu.** Hat Home Assistant für einen Tag keine Leistungskurve mehr (Verlauf ohne W-Werte oder gepurgt, keine Kurve in
der Langzeitstatistik), stieg «Tag reparieren» bis N-791 am N-596-Schutz aus, sobald der Tag gespeicherte Gerätewerte
trug — auch wenn die Zählerstatistik des Tages in HA inzwischen korrigiert war (Erstwert-Sprung 123.909,6 kWh). Der Schutz
gilt dem «leer ersetzen»; die Zählerstatistik ersetzt nicht leer.

**Die Regel** (``aggregate_day(zaehler_erhalt=True)``, nur Stufe 3 der Werkbank, ``repair_orchestrator._reparatur_aggregat``):

* geschrieben wird nur, wenn die **Zählertabelle des Tages aus der HA-Langzeitstatistik** Werte trägt
  (``external:ha_statistics:hourly``) — eedcs eigene Stände (Snapshot-Rückfall) nicht: sie tragen genau den Sprung, den
  der Anwender in HA korrigiert hat (Nachstellung, Lauf S); sonst bleibt der Tag stehen wie bisher (N-596-Satz);
* die zählerbasierten Größen kommen aus dem Lauf (Stunden-kWh, Bilanz, ``komponenten_kwh`` der Zähler — G1 über
  ``baue_tagestabelle``), der **Leistungsverlauf bleibt stehen**: ``TagesEnergieProfil.komponenten`` je Stunde mit seiner
  alten Herkunft und die drei Tages-Peaks, wo der Lauf keinen eigenen hat (die Quelle gewinnt, wo sie liefert — N-595).

``aggregate_day`` bleibt der einzige Schreiber; hier stehen nur die Lese- und Einsetz-Schritte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.source_priority import SOURCE_LABELS
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

#: Die Kennung der Zählertabelle aus der HA-Langzeitstatistik (``aggregator.lade_zaehler_und_counter``).
HA_ZAEHLERTABELLE = "external:ha_statistics:hourly"

#: Die Tagesgrößen der Tageszeile, die nur aus dem Leistungsverlauf entstehen.
PEAK_FELDER = ("peak_pv_kw", "peak_netzbezug_kw", "peak_einspeisung_kw")

#: Der Anwender-Satz der Rückmeldung (Werkbank, «Tag reparieren», «Aus Home Assistant neu übernehmen»).
SATZ_ZAEHLER_ERHALT = (
    "Gerätewerte aus der Home-Assistant-Statistik neu geschrieben; der gespeicherte Leistungsverlauf blieb stehen."
)


@dataclass
class Leistungserhalt:
    """Der gespeicherte Leistungsverlauf eines Tages, gelesen vor dem Delete.

    ``komponenten`` = ``{stunde: komponenten}`` (W-Verlauf), ``herkunft`` = ``{stunde: {"komponenten.<k>": eintrag}}``,
    ``peaks`` = ``{feld: wert}`` und ``peak_quellen`` = ``{feld: source}`` aus der alten Tageszeile.
    """

    komponenten: dict = field(default_factory=dict)
    herkunft: dict = field(default_factory=dict)
    peaks: dict = field(default_factory=dict)
    peak_quellen: dict = field(default_factory=dict)


def zaehlertabelle_traegt(kwh_source_label: str, kwh_pro_stunde: dict) -> bool:
    """Trägt die Zählertabelle des Tages Werte aus der HA-Langzeitstatistik (nicht aus eedcs eigenen Ständen)?"""
    return kwh_source_label == HA_ZAEHLERTABELLE and bool(kwh_pro_stunde)


async def lese_leistungsbahnen(anlage_id: int, datum: date, db: AsyncSession) -> Leistungserhalt:
    """Den gespeicherten Leistungsverlauf des Tages lesen — Spalten-Projektion, keine ORM-Objekte (die Zeilen werden
    gleich danach gelöscht, ``rette_und_loesche``)."""
    tep, tz = TagesEnergieProfil, TagesZusammenfassung
    erhalt = Leistungserhalt()
    zeilen = await db.execute(select(tep.stunde, tep.komponenten, tep.source_provenance).where(
        tep.anlage_id == anlage_id, tep.datum == datum))
    for stunde, komponenten, provenance in zeilen.all():
        if not komponenten:
            continue
        erhalt.komponenten[stunde] = dict(komponenten)
        erhalt.herkunft[stunde] = {k: dict(v) for k, v in (provenance or {}).items()
                                   if k.startswith("komponenten.") and isinstance(v, dict)}
    alt = (await db.execute(select(*(getattr(tz, f) for f in PEAK_FELDER), tz.source_provenance).where(
        tz.anlage_id == anlage_id, tz.datum == datum))).first()
    if alt is not None:
        provenance = alt[-1] or {}
        for feld, wert in zip(PEAK_FELDER, alt[:-1]):
            if wert is None:
                continue
            erhalt.peaks[feld] = wert
            quelle = (provenance.get(feld) or {}).get("source")
            if quelle in SOURCE_LABELS:   # #299-Regel wie ``rette_und_loesche``
                erhalt.peak_quellen[feld] = quelle
    return erhalt


def setze_leistungsverlauf(profil: TagesEnergieProfil, erhalt: "Leistungserhalt | None") -> None:
    """Die Stunde ohne eigenen Leistungswert trägt den gespeicherten Verlauf mit seiner alten Herkunft — nach dem
    Provenance-Seed des Laufs (dieselbe Reihenfolge-Regel wie N-595 S4). Ohne ``erhalt`` (jeder andere Lauf) nichts."""
    if erhalt is None or profil.komponenten or profil.stunde not in erhalt.komponenten:
        return
    from sqlalchemy.orm.attributes import flag_modified

    profil.komponenten = dict(erhalt.komponenten[profil.stunde])
    profil.source_provenance = {**(profil.source_provenance or {}), **erhalt.herkunft.get(profil.stunde, {})}
    flag_modified(profil, "source_provenance")


def peaks_erhalten(erhalt: "Leistungserhalt | None", akku, preserved_felder: dict, preserved_quellen: dict) -> None:
    """Die Peaks, für die der Lauf keinen Wert hat (``akku.peak_* == 0`` ⇒ ``None`` in der Tageszeile), gehen über den
    Restore der Tageszeile zurück (``schreibe_provenance_und_restore``, alte Herkunft, #299)."""
    if erhalt is None:
        return
    lauf = {"peak_pv_kw": akku.peak_pv, "peak_netzbezug_kw": akku.peak_bezug,
            "peak_einspeisung_kw": akku.peak_einspeisung}
    for feld, wert in erhalt.peaks.items():
        if lauf[feld] > 0:
            continue
        preserved_felder[feld] = wert
        if feld in erhalt.peak_quellen:
            preserved_quellen[feld] = erhalt.peak_quellen[feld]
