"""PV-Monatswerte je Modul — der EINE Ladepfad vor ``resolve_pv_je_modul``.

**Warum es diesen Service gibt.** Die Präzedenz (Messwert → Aggregat füllt die
Lücke → fehlt) steht als Formel in ``core/berechnungen/pv_verteilung.py``
(ADR-001). Sie ist aber nur so gut wie ihre Eingabe, und die musste bisher jede
Read-Site selbst zusammensuchen: IMD-Zeilen laden, Anlagen-Aggregat laden, nach
Anschaffungs-/Stilllegungsdatum filtern. Drei Stellen taten das, und **zwei
davon sind an der Formel vorbeigelaufen**:

- ``api/routes/ha_export.py`` und ``api/routes/cockpit/uebersicht.py`` bildeten
  eine **rohe IMD-Summe** je Monat und schalteten über ein globales Flag
  (``use_inv_pv``) zwischen ihr und dem Aggregat um. Zwei Fehler daraus:
  (a) messen in einem Monat nur MANCHE Strings, ging die rohe Teilsumme in
  Finanzen und spezifischen Ertrag; (b) hat irgendein Monat IMD-Werte, lieferte
  ``.get(key, 0.0)`` für **alle anderen Monate 0** — auch dort, wo ein Aggregat
  vorlag. Eine Anlage, die mitten in der Historie auf Pro-String-Messung
  umgestellt hat, verlor damit ihre komplette Vorgeschichte in diesen Sichten.

Der Service lädt einmal und gibt die aufgelöste Pro-Modul-Sicht je Monat zurück;
die Summenbildung läuft über ``pv_summe_je_monat``, das Unvollständigkeit als
``None`` durchreicht statt als Teilsumme ([[feedback_aggregations_drift]]).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    PvModul,
    PvModulWert,
    ist_vollstaendig,
    resolve_pv_je_modul,
)
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.utils.investition_value import get_inv_value

# {(jahr, monat): {inv_id: PvModulWert}}
PvMonate = dict[tuple[int, int], dict[int, PvModulWert]]


async def lade_pv_je_monat(
    db: AsyncSession,
    anlage_id: int,
    pv_module: list[Investition],
    jahr: Optional[int] = None,
) -> PvMonate:
    """Aufgelöste Pro-Modul-PV je Monat — Messwerte + Aggregat-Lückenfüllung.

    Args:
        db: Session.
        anlage_id: Anlage.
        pv_module: PV-Erzeuger der Anlage. **Der Typ-Filter ist Sache des
            Aufrufers**, und das ist eine Entscheidung, keine Nachlässigkeit:
            die meisten Aufrufer übergeben nur ``pv-module``, weil das
            Balkonkraftwerk dort eine eigene Zeile hat und sonst doppelt zählte
            (so etwa ``investitionen/crud.py::berechne_pv_einsparung…``). Die
            String-Sichten (``cockpit/pv_strings.py``) übergeben seit F-10
            **beide** Erzeuger-Typen — dort ist das BKW eine Erzeuger-Zeile wie
            ein String, und ohne es bliebe eine reine BKW-Anlage leer.
            Die Auflösung selbst ist typ-blind und bleibt es: sie kennt nur
            „hat einen eigenen Wert" gegen „bekommt einen Anteil am Rest".
        jahr: optional auf ein Jahr einschränken.

    Returns:
        ``{(jahr, monat): {inv_id: PvModulWert}}``. Monate ohne jede PV-Quelle
        und Monate ohne aktives Modul fehlen. Module, die im Monat nicht aktiv
        waren, tauchen im Monat nicht auf (#236).
    """
    if not pv_module:
        return {}

    pv_ids = [m.id for m in pv_module]
    imd_query = select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id.in_(pv_ids)
    )
    md_query = select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    if jahr is not None:
        imd_query = imd_query.where(InvestitionMonatsdaten.jahr == jahr)
        md_query = md_query.where(Monatsdaten.jahr == jahr)

    roh: dict[tuple[int, int], dict[int, float]] = {}
    # #352: Werte, die selbst schon eine kWp-Zerlegung sind (Import oder
    # übernommener Connector-/Cloud-Vorschlag). Die Markierung steht je Feld in
    # DERSELBEN Zeile (`source_provenance`) — kein zusätzlicher Query, die Row
    # liegt hier ohnehin vor.
    abgeleitet: dict[tuple[int, int], set[int]] = {}
    for imd in (await db.execute(imd_query)).scalars().all():
        wert = (imd.verbrauch_daten or {}).get("pv_erzeugung_kwh")
        if wert is None:
            continue
        roh.setdefault((imd.jahr, imd.monat), {})[imd.investition_id] = wert
        eintrag = (imd.source_provenance or {}).get("verbrauch_daten.pv_erzeugung_kwh")
        if isinstance(eintrag, dict) and eintrag.get("abgeleitet"):
            abgeleitet.setdefault((imd.jahr, imd.monat), set()).add(imd.investition_id)

    # Anlagen-Aggregat (manuell/importiert, NIE programmatisch gefüllt).
    aggregat: dict[tuple[int, int], Optional[float]] = {
        (md.jahr, md.monat): md.pv_erzeugung_kwh
        for md in (await db.execute(md_query)).scalars().all()
    }

    out: PvMonate = {}
    kandidaten = set(roh.keys()) | {k for k, v in aggregat.items() if v is not None}
    for (j, monat) in sorted(kandidaten):
        # #236: nur im Monat aktive Module — sonst verteilt das Aggregat auf
        # Module, die es damals noch nicht gab.
        aktive = [m for m in pv_module if m.ist_aktiv_im_monat(j, monat)]
        if not aktive:
            continue
        roh_monat = roh.get((j, monat), {})
        abgeleitet_monat = abgeleitet.get((j, monat), set())
        out[(j, monat)] = resolve_pv_je_modul(
            aggregat_kwh=aggregat.get((j, monat)),
            module=[
                PvModul(
                    inv_id=m.id,
                    leistung_kwp=get_inv_value(m, "leistung_kwp"),
                    eigen_kwh=roh_monat.get(m.id),
                    eigen_ist_abgeleitet=m.id in abgeleitet_monat,
                )
                for m in aktive
            ],
        )
    return out


def pv_summe_je_monat(monate: PvMonate) -> dict[tuple[int, int], Optional[float]]:
    """Anlagen-PV je Monat — ``None``, wo die Auflösung unvollständig ist.

    ``None`` heißt „mindestens ein aktives Modul ohne Wert und ohne Aggregat".
    Eine Teilsumme wäre als Anlagenerzeugung irreführend (N42); der Aufrufer
    entscheidet, ob er den Monat auslässt oder ihn als Lücke ausweist — er darf
    ihn nur nicht als 0 verrechnen.
    """
    return {
        key: (sum(w.pv_erzeugung_kwh for w in werte.values())
              if ist_vollstaendig(werte) else None)
        for key, werte in monate.items()
    }
