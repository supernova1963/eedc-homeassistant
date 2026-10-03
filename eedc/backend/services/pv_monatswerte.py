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

from typing import Mapping, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.erzeuger_traeger import (
    BKW_TYP,
    PV_MODUL_TYP,
    abgetretene_bkw_ids,
    erzeuger_traeger,
)
from backend.core.berechnungen import (
    PvModul,
    PvModulWert,
    ist_vollstaendig,
    resolve_pv_je_modul,
)
from backend.core.field_definitions import get_pv_erzeugung_kwh
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
    *,
    investitionen: Optional[Sequence[Investition]] = None,
) -> PvMonate:
    """Aufgelöste Pro-Modul-PV je Monat — Messwerte + Aggregat-Lückenfüllung.

    Args:
        db: Session.
        anlage_id: Anlage.
        pv_module: PV-Erzeuger der Anlage. **Der Typ-Filter ist Sache des
            Aufrufers**, und das ist eine Entscheidung, keine Nachlässigkeit:
            die Monats-Fakten und der HA-Statistik-Import übergeben nur
            ``pv-module``, weil das Balkonkraftwerk dort eine eigene Zeile hat
            (``bkw_erzeugung``) bzw. kein Empfänger des Zählers ist und sonst
            doppelt zählte. Die String-Sichten
            (``cockpit/pv_strings.py``), der Daten-Checker und
            ``GET /monatsdaten/{id}`` übergeben seit F-10 bzw. N-386 **beide**
            Erzeuger-Typen — dort ist das BKW eine Erzeuger-Zeile wie ein
            String, und ohne es bliebe eine reine BKW-Anlage leer.
            Die Auflösung selbst ist typ-blind und bleibt es: sie kennt nur
            „hat einen eigenen Wert" gegen „bekommt einen Anteil am Rest".
            **Was der Aufrufer weglässt, verschwindet trotzdem nicht aus dem
            Anlagenwert (N-611):** der steht für ALLE PV-Quellen der Anlage.
            Ein Balkonkraftwerk, das in diesem Monat selbst trägt und hier
            nicht übergeben ist, mindert den Anlagenwert um seinen eigenen
            Wert, bevor der Rest die Modul-Lücken füllt — siehe unten.
        jahr: optional auf ein Jahr einschränken.
        investitionen: alle Investitionen der Anlage, **ungefiltert** (kein
            Aktiv-, Datums- oder Abtretungsfilter — den Zeitfilter und die
            Abtretung entscheidet dieser Pfad je Monat, ADR-002/P11). Nur
            gebraucht, wenn ein Monat einen Anlagenwert trägt; wer sie schon
            geladen hat (die Monats-Fakten), reicht sie durch und spart die
            Abfrage. ``None`` = der Pfad lädt sie bei Bedarf selbst.

    Returns:
        ``{(jahr, monat): {inv_id: PvModulWert}}``. Monate ohne jede PV-Quelle
        und Monate ohne aktives Modul fehlen. Module, die im Monat nicht aktiv
        waren, tauchen im Monat nicht auf (#236).

    **N-266/E4 — die P7-Leserichtung bekommt eine dritte Stufe.** Hängen
    `pv-module` unter einem `balkonkraftwerk`, ist der BKW-Monatswert für sie
    genau das, was ``Monatsdaten.pv_erzeugung_kwh`` für die ganze Anlage ist:
    ein **Aggregat, das nur die Lücken seiner Kinder füllt**. Die Präzedenz
    lautet damit — vom Nächsten zum Entferntesten:

    1. eigener Messwert des Moduls,
    2. der Wert **seines** Balkonkraftwerks (verteilt nach kWp auf dessen
       lückenhafte Kinder),
    3. das Anlagen-Aggregat für alles, was danach noch offen ist.

    Das ist keine neue Regel, sondern dieselbe Regel eine Ebene tiefer, und sie
    ist der Grund, warum ``monats_fakten/roh.py`` das abtretende BKW aus
    ``bkw_erzeugung`` herausnehmen kann, ohne einen gepflegten Wert zu
    verlieren: er wirkt weiter, nur an der richtigen Stelle. Ohne diese Hälfte
    stünde ``pv_kwh = pv_modul_summe + bkw_erzeugung`` auf der doppelten
    Erzeugung — mit Folgen für Autarkie, Eigenverbrauchsquote, CO₂, Finanzen,
    Community-Payload und HA-Export.

    **N-611 — der Anlagenwert steht für alle PV-Quellen.** Stufe 3 bekommt
    nicht den rohen ``Monatsdaten.pv_erzeugung_kwh``, sondern
    ``max(0, Anlagenwert − Σ eigene Werte der Balkonkraftwerke)`` — gezählt
    werden die BKW, die im Monat aktiv sind, selbst tragen (nicht an Kinder
    abgetreten) und vom Aufrufer **nicht** übergeben wurden (übergebene stehen
    mit ihrem Wert schon in der Auflösung). Gelesen wird ihr Wert genau wie in
    ``monats_fakten/roh.py::falte`` (``get_pv_erzeugung_kwh``, beide
    Schreibweisen), denn genau diese Zahl addiert ``monats_fakten/bau.py``
    danach als ``bkw_erzeugung`` wieder dazu: ``pv_kwh = Module + BKW`` ergibt
    so den Anlagenwert und nicht Anlagenwert + BKW. Ohne Abzug zählte das BKW
    doppelt — einmal als Anteil, den der Anlagenwert auf die Module verteilt,
    einmal als eigene Zeile. Ein BKW **ohne** eigenen Wert bekommt keinen
    Anteil am Rest (der bliebe ein Faktenfeld ohne Speicherort; die Familie
    geht an HA-Bauform S1). **Ohne Anlagenwert läuft nichts davon** — keine
    zusätzliche Abfrage, jede Zahl wie vorher.
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

    # N-611: die eigenen Monatswerte der Balkonkraftwerke, die der Aufrufer NICHT
    # übergeben hat — nur geladen, wenn überhaupt ein Monat einen Anlagenwert
    # trägt (sonst bleibt der Pfad Abfrage für Abfrage, was er war).
    pv_quellen_anlage: list[Investition] = []
    bkw_daten: dict[tuple[int, int], dict[int, Optional[dict]]] = {}
    if any(v is not None for v in aggregat.values()):
        if investitionen is None:
            investitionen = (await db.execute(
                select(Investition).where(Investition.anlage_id == anlage_id)
            )).scalars().all()
        pv_quellen_anlage = [
            i for i in investitionen
            if i.typ in (PV_MODUL_TYP, BKW_TYP)
        ]
        # Übergebene BKW stehen mit ihrem Wert schon in der Auflösung — nur die übrigen.
        bkw_ids = [i.id for i in pv_quellen_anlage if i.typ == BKW_TYP and i.id not in pv_ids]
        if bkw_ids:
            bkw_query = select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(bkw_ids)
            )
            if jahr is not None:
                bkw_query = bkw_query.where(InvestitionMonatsdaten.jahr == jahr)
            for imd in (await db.execute(bkw_query)).scalars().all():
                bkw_daten.setdefault((imd.jahr, imd.monat), {})[imd.investition_id] = imd.verbrauch_daten

    # N-266/E4 — Stufe 2 der Präzedenz: die Monatswerte der Balkonkraftwerke,
    # unter denen Module hängen. Sie werden hier NICHT summiert, sondern als
    # Aggregat je Elternteil vorgehalten.
    bkw_aggregate = await _lade_bkw_aggregate(db, anlage_id, pv_module, jahr=jahr)

    out: PvMonate = {}
    kandidaten = (
        set(roh.keys())
        | {k for k, v in aggregat.items() if v is not None}
        | set(bkw_aggregate.keys())
    )
    for (j, monat) in sorted(kandidaten):
        # #236: nur im Monat aktive Module — sonst verteilt das Aggregat auf
        # Module, die es damals noch nicht gab.
        aktive = [m for m in pv_module if m.ist_aktiv_im_monat(j, monat)]
        # ADR-002/P11, Reihenfolge Zeitfilter → Selektor (N-386): Die Abtretung
        # gilt **je Monat**, nicht für die Anlage. Ein Balkonkraftwerk, dessen
        # Modul-Kinder in diesem Monat noch gar nicht angeschafft waren, trägt
        # seine Erzeugung hier noch selbst — genau so macht es
        # `summe_erzeuger_kwp` auf der kWp-Achse seit N-266.
        # ⛔ Bis 2026-09-04 entschied das der Aufrufer, einmal für alle Monate.
        # Wer seinem bestehenden BKW Module zuordnete, verlor dessen Erzeugung
        # damit **rückwirkend** in jedem Vormonat — und weil alle Sichten
        # denselben zu kleinen Wert nannten, gab es keinen Widerspruch zu sehen.
        aktive = erzeuger_traeger(aktive)
        if not aktive:
            continue
        roh_monat = dict(roh.get((j, monat), {}))
        abgeleitet_monat = abgeleitet.get((j, monat), set())

        # Stufe 2 VOR Stufe 3: jedes BKW verteilt seinen Monatswert auf die
        # Lücken seiner eigenen Kinder. Ergebnis geht als *Messwert-Ersatz* in
        # `roh_monat` — damit greift darunter Stufe 3 (Anlagen-Aggregat) nur
        # noch für Module, die auch dann noch offen sind. Die Reihenfolge ist
        # die Aussage: das nähere Aggregat gewinnt.
        for bkw_id, bkw_kwh in bkw_aggregate.get((j, monat), {}).items():
            kinder = [m for m in aktive if m.parent_investition_id == bkw_id]
            luecken = [k for k in kinder if k.id not in roh_monat]
            if not luecken:
                continue
            # ⚠ **ALLE** Kinder übergeben, nicht nur die lückenhaften: der
            # verteilte Rest ist `Aggregat − Σ der gemessenen Werte`, und ohne
            # die gemessenen Geschwister wäre diese Σ 0. Bei 100 kWh am BKW und
            # 70 kWh gemessen am ersten Modul bekäme das zweite dann 100 statt
            # 30 — die Anlagensumme stünde auf 170. Beim Bau tatsächlich so
            # gebaut und von `test_gemessener_modulwert_gewinnt_gegen_den_bkw_wert`
            # gefangen.
            verteilt = resolve_pv_je_modul(
                aggregat_kwh=bkw_kwh,
                module=[
                    PvModul(
                        inv_id=k.id,
                        leistung_kwp=get_inv_value(k, "leistung_kwp"),
                        eigen_kwh=roh_monat.get(k.id),
                        eigen_ist_abgeleitet=k.id in abgeleitet_monat,
                    )
                    for k in kinder
                ],
            )
            for k in luecken:
                wert = verteilt.get(k.id)
                if wert is None:
                    continue
                roh_monat[k.id] = wert.pv_erzeugung_kwh
                # Der Wert ist eine kWp-Zerlegung, keine Messung (#352): sonst
                # kürt das String-Ranking einen „besten String" aus Zahlen, die
                # per Konstruktion proportional zur kWp sind.
                abgeleitet_monat = abgeleitet_monat | {k.id}

        anlagenwert = aggregat.get((j, monat))
        if anlagenwert is not None and bkw_daten.get((j, monat)):
            anlagenwert = max(0.0, anlagenwert - eigene_bkw_erzeugung_kwh(
                [i for i in pv_quellen_anlage if i.ist_aktiv_im_monat(j, monat)],
                bkw_daten[(j, monat)],
            ))
        out[(j, monat)] = resolve_pv_je_modul(
            aggregat_kwh=anlagenwert,
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


def eigene_bkw_erzeugung_kwh(
    aktive: Sequence[Investition],
    daten_je_investition: Mapping[int, Optional[dict]],
) -> float:
    """Σ der eigenen Monatswerte der Balkonkraftwerke, die selbst tragen (N-611).

    Der Abzug, der aus dem Anlagenwert den Rest für die Modul-Lücken macht —
    an EINER Stelle, weil Leseseite (``lade_pv_je_monat``), Schreibweg
    (``ha_statistics._verteile_anlagen_pv``) und Import-Vorschau dieselbe Zahl
    brauchen.

    Args:
        aktive: die im Monat **aktiven** Investitionen (Zeitfilter beim
            Aufrufer). Sie müssen die `pv-module` mit enthalten, sonst ist die
            Abtretung nicht zu erkennen (ADR-002/P11, Zeitfilter → Selektor).
        daten_je_investition: ``{inv_id: verbrauch_daten}`` des Monats. Ein BKW,
            das schon selbst in einer Auflösung steht, gehört NICHT hinein —
            sein Wert wäre sonst zweimal abgezogen (``lade_pv_je_monat`` lädt
            deshalb nur die Zeilen der nicht übergebenen BKW).

    Ein abtretendes BKW (N-266) zählt nicht — sein Wert füllt schon die Lücken
    seiner Kinder. Gelesen wird über ``get_pv_erzeugung_kwh`` wie in
    ``monats_fakten/roh.py::falte``; ein BKW ohne Wert trägt 0 bei.
    """
    abgetreten = abgetretene_bkw_ids(aktive)
    return sum(
        get_pv_erzeugung_kwh(daten_je_investition.get(i.id) or {})
        for i in aktive
        if i.typ == BKW_TYP and i.id not in abgetreten
    )


async def _lade_bkw_aggregate(
    db: AsyncSession,
    anlage_id: int,
    pv_module: list[Investition],
    jahr: Optional[int] = None,
) -> dict[tuple[int, int], dict[int, float]]:
    """``{(jahr, monat): {bkw_id: kwh}}`` für Balkonkraftwerke MIT Modul-Kindern.

    Nur die abtretenden BKW (N-266): ohne Modul-Kinder ist der Wert die
    Erzeugung des Geräts selbst und wird in ``monats_fakten/bau.py`` als eigener
    Summand geführt — hier wäre er dann ein zweites Mal drin.

    ``{}``, wenn kein Modul der übergebenen Menge einen BKW-Parent hat. Das ist
    der Normalfall jeder Bestandsanlage; die Funktion kostet dann **eine**
    zusätzliche, sehr kleine Query und ändert nichts.
    """
    parent_ids = {
        m.parent_investition_id
        for m in pv_module
        if m.typ == "pv-module" and m.parent_investition_id is not None
    }
    if not parent_ids:
        return {}

    bkws = (await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.id.in_(parent_ids))
        .where(Investition.typ == "balkonkraftwerk")
    )).scalars().all()
    if not bkws:
        return {}

    bkw_ids = [b.id for b in bkws]
    imd_query = select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id.in_(bkw_ids)
    )
    if jahr is not None:
        imd_query = imd_query.where(InvestitionMonatsdaten.jahr == jahr)

    out: dict[tuple[int, int], dict[int, float]] = {}
    for imd in (await db.execute(imd_query)).scalars().all():
        vd = imd.verbrauch_daten or {}
        # Beide Schreibweisen, wie `get_pv_erzeugung_kwh`: das BKW-Formular hat
        # historisch `erzeugung_kwh` geschrieben, der Kanon ist
        # `pv_erzeugung_kwh`. Wer nur den Kanon liest, verliert den Altbestand.
        wert = vd.get("pv_erzeugung_kwh")
        if wert is None:
            wert = vd.get("erzeugung_kwh")
        if wert is None:
            continue
        try:
            out.setdefault((imd.jahr, imd.monat), {})[imd.investition_id] = float(wert)
        except (TypeError, ValueError):
            continue
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
