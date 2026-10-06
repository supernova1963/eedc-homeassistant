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
from backend.core.berechnungen.pv_verteilung import QUELLE_FEHLT, bkw_kinder_luecken_kwh
from backend.core.field_definitions import get_pv_erzeugung_kwh
from backend.core.investition_kennwerte import get_erzeuger_kwp
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.utils.investition_value import get_inv_value

# {(jahr, monat): {inv_id: PvModulWert}}
PvMonate = dict[tuple[int, int], dict[int, PvModulWert]]

#: {(jahr, monat): {bkw_id: kWh}} — der Anteil am gespeicherten Anlagenwert, den ein selbst tragendes
#: Balkonkraftwerk OHNE eigenen Wert in diesem Monat bekommt (N-621). Nur Monate mit Anlagenwert und
#: nur BKW, die der Aufrufer NICHT selbst in die Auflösung gegeben hat.
BkwAnteile = dict[tuple[int, int], dict[int, float]]


async def lade_pv_je_monat(
    db: AsyncSession,
    anlage_id: int,
    pv_module: list[Investition],
    jahr: Optional[int] = None,
    *,
    investitionen: Optional[Sequence[Investition]] = None,
    bkw_anteile: Optional[BkwAnteile] = None,
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
        bkw_anteile: **Ausgabe-Dict** (N-621). Wer es mitgibt, bekommt darin
            je Monat den Anteil am Anlagenwert, den ein nicht übergebenes,
            selbst tragendes Balkonkraftwerk ohne eigenen Wert bekommt
            (``BkwAnteile``). Die Modul-Einträge des Rückgabewerts sind mit und
            ohne Argument dieselben — der Anteil ist eine Eigenschaft der
            Auflösung, nicht des Aufrufers; das Argument entscheidet nur, ob der
            Aufrufer ihn auch zu sehen bekommt. Warum ein Ausgabe-Parameter und
            kein zweiter Rückgabewert: die Signatur ``-> PvMonate`` hat sieben
            Produktiv-Aufrufer, gebraucht wird der Anteil von zweien (Monats-
            Fakten, Import-Vorschau) — dieselbe Bauform wie ``kontext_out`` in
            ``ha_export/anlage_sensoren.py::calculate_anlage_sensors``.

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
    einmal als eigene Zeile. **Ohne Anlagenwert läuft nichts davon** — keine
    zusätzliche Abfrage, jede Zahl wie vorher.

    **N-621 — ein Balkonkraftwerk ohne eigenen Wert bekommt seinen Anteil.**
    Trägt ein Monat einen Anlagenwert, ist ein selbst tragendes BKW ohne
    eigenen Wert eine Lücke wie ein Modul ohne Wert: die Auflösung läuft über
    die Module UND diese BKW, der Rest (Anlagenwert − Σ eigene Werte aller
    Quellen, nie unter 0) geht nach kWp auf alle Quellen ohne eigenen Wert.
    Zurück kommen die Modul-Einträge wie bisher (``pv_je_modul`` enthält nur
    ``pv-module``, F-10) und der BKW-Anteil getrennt in ``bkw_anteile``.
    Vorher bekam das BKW nichts — hatte kein Modul eine Lücke, fiel sein
    Anteil aus der Monatssumme (gespeicherter Anlagenwert 1000, Strings
    550 + 380 ⇒ 930), während PV-Strings und der Monat ohne Abschluss 1000
    nannten. **Kandidatenregel:** ohne Anlagenwert gibt es keine Lücke, die
    ein BKW füllen könnte — der Pfad läuft dann exakt wie vorher, und ein BKW
    öffnet nie einen Monat in ``pv_je_modul``. Seit HA-Bauform E4b (Teil A)
    speichert auch der HA-Statistik-Sammelimport den Zähler als Anlagenwert
    (wie „Aus HA laden", N-622) — bis dahin verteilte er ihn selbst auf die
    Module, und ein BKW ohne Wert bekam dort 0.

    **Gewicht:** ein Balkonkraftwerk wird über ``get_erzeuger_kwp`` gewichtet
    (Spalte → ``parameter`` → ``leistung_wp × anzahl``), Module wie bisher über
    ``get_inv_value`` (``_kwp_gewicht``). Bis N-621 las auch das BKW
    ``get_inv_value`` — bei ``leistung_wp × anzahl`` 0 kWp, es bekam vom Rest
    nichts, obwohl die String-Sicht es als „geschätzt" auswies.
    """
    if not pv_module and bkw_anteile is None:
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
    # N-621: ohne Module (reine BKW-Anlage, nur mit `bkw_anteile`) gibt es nichts zu laden.
    for imd in ((await db.execute(imd_query)).scalars().all() if pv_ids else ()):
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
        anlagenwert = aggregat.get((j, monat))
        # N-621: ohne Anlagenwert keine BKW-Lücke — `bkw_empfaenger` bleibt leer und der Monat läuft wie vorher.
        bkw_empfaenger: list[Investition] = []
        daten_monat = bkw_daten.get((j, monat), {})
        bkw_eigen = 0.0
        if anlagenwert is not None:
            alle_aktiv = [i for i in pv_quellen_anlage if i.ist_aktiv_im_monat(j, monat)]
            if daten_monat:
                bkw_eigen = eigene_bkw_erzeugung_kwh(alle_aktiv, daten_monat)
                anlagenwert = max(0.0, anlagenwert - bkw_eigen)
            bkw_empfaenger = bkw_ohne_eigenen_wert(alle_aktiv, daten_monat, uebergeben=pv_ids)
        if not aktive and not bkw_empfaenger:
            continue
        roh_monat = dict(roh.get((j, monat), {}))
        abgeleitet_monat = abgeleitet.get((j, monat), set())

        # Stufe 2 VOR Stufe 3: jedes BKW verteilt seinen Monatswert auf die
        # Lücken seiner eigenen Kinder. Ergebnis geht als *Messwert-Ersatz* in
        # `roh_monat` — damit greift darunter Stufe 3 (Anlagen-Aggregat) nur
        # noch für Module, die auch dann noch offen sind. Die Reihenfolge ist
        # die Aussage: das nähere Aggregat gewinnt.
        # Die Formel ist seit N-627 die Layer-Funktion `bkw_kinder_luecken_kwh` — dieselbe, die
        # Cockpit → Monat im Monat ohne Abschluss ruft (vorher stand sie nur hier, inline).
        # ⚠ **ALLE** Kinder übergeben, nicht nur die lückenhaften: der verteilte Rest ist
        # `Aggregat − Σ der gemessenen Werte`, und ohne die gemessenen Geschwister wäre diese Σ 0.
        # Bei 100 kWh am BKW und 70 kWh gemessen am ersten Modul bekäme das zweite dann 100 statt
        # 30 — die Anlagensumme stünde auf 170. Beim Bau tatsächlich so gebaut und von
        # `test_gemessener_modulwert_gewinnt_gegen_den_bkw_wert` gefangen.
        for bkw_id, bkw_kwh in bkw_aggregate.get((j, monat), {}).items():
            kinder = [m for m in aktive if m.parent_investition_id == bkw_id]
            for k_id, kwh in bkw_kinder_luecken_kwh(
                bkw_kwh=bkw_kwh,
                kinder=[
                    PvModul(
                        inv_id=k.id,
                        leistung_kwp=_kwp_gewicht(k),
                        eigen_kwh=roh_monat.get(k.id),
                        eigen_ist_abgeleitet=k.id in abgeleitet_monat,
                    )
                    for k in kinder
                ],
            ).items():
                roh_monat[k_id] = kwh
                # Der Wert ist eine kWp-Zerlegung, keine Messung (#352): sonst
                # kürt das String-Ranking einen „besten String" aus Zahlen, die
                # per Konstruktion proportional zur kWp sind.
                abgeleitet_monat = abgeleitet_monat | {k_id}

        # Stufe 3: der Anlagenwert (schon um die eigenen BKW-Werte gemindert, N-611) füllt die Lücken —
        # die der Module UND, seit N-621, die der Balkonkraftwerke ohne eigenen Wert. EINE Auflösung, damit
        # beide denselben Rest nach kWp teilen (Σ-Invariante über alle Quellen).
        aufgeloest = resolve_pv_je_modul(
            aggregat_kwh=anlagenwert,
            module=[
                PvModul(
                    inv_id=m.id,
                    leistung_kwp=_kwp_gewicht(m),
                    eigen_kwh=roh_monat.get(m.id),
                    eigen_ist_abgeleitet=m.id in abgeleitet_monat,
                )
                for m in aktive
            ] + [
                PvModul(inv_id=b.id, leistung_kwp=_kwp_gewicht(b), eigen_kwh=None)
                for b in bkw_empfaenger
            ],
        )
        if aktive:
            out[(j, monat)] = {m.id: aufgeloest[m.id] for m in aktive}
        if bkw_empfaenger and bkw_anteile is not None:
            anteile = {b.id: aufgeloest[b.id].pv_erzeugung_kwh for b in bkw_empfaenger}
            # Rundungsrest (Nacharbeit nach der Nachmessung N-621): drei Teile nach kWp ergeben in
            # Gleitkomma oft nicht exakt den Anlagenwert (gemessen 999,9999999999998 statt 1000;
            # `int()` in `cockpit/nachhaltigkeit.py` rundet so etwas nach unten ab). Der letzte
            # BKW-Empfänger bekommt deshalb die Differenz — in derselben Summenfolge, in der
            # `monats_fakten/bau.py` die Monatssumme bildet (Module, eigene BKW-Werte, Anteile).
            # Nur wenn der Rest > 0 ist (sonst sind alle Anteile 0) und nur hier, nicht in
            # `resolve_pv_je_modul`: die P7-Formel und ihre übrigen Aufrufer bleiben, wie sie sind.
            brutto = aggregat.get((j, monat))
            if anlagenwert and brutto is not None:
                letzter = bkw_empfaenger[-1].id
                davor = sum(w.pv_erzeugung_kwh for w in out.get((j, monat), {}).values()) + bkw_eigen
                andere = sum(v for k, v in anteile.items() if k != letzter)
                anteile[letzter] = max(0.0, brutto - davor - andere)
            bkw_anteile[(j, monat)] = anteile
    return out


def _kwp_gewicht(inv: Investition) -> float:
    """kWp-Gewicht einer PV-Quelle in der Auflösung (N-621).

    Ein Balkonkraftwerk über den Typ-Dispatcher ``get_erzeuger_kwp`` — er kennt
    auch die dritte Pflegeform ``leistung_wp × anzahl``. ``get_inv_value`` kennt
    sie nicht und lieferte dort 0: das BKW bekam in der String-Sicht vom Rest
    nichts (gemessen Balkon 68 statt 192,7 kWh). Module bleiben bei
    ``get_inv_value`` — für sie ändert sich keine Zahl.
    """
    if inv.typ == BKW_TYP:
        return get_erzeuger_kwp(inv)
    return get_inv_value(inv, "leistung_kwp")


def _bkw_hat_eigenen_wert(daten: Optional[dict]) -> bool:
    """Trägt die Monatszeile eines Balkonkraftwerks eine eigene Erzeugung — auch 0?

    Beide Schreibweisen wie ``get_pv_erzeugung_kwh`` (Kanon ``pv_erzeugung_kwh``,
    Altbestand ``erzeugung_kwh``); eine gepflegte 0 ist ein Wert (``is not None``).
    Eine Zeile nur mit Eigenverbrauch ist **keine** Erzeugung — genau die
    Datenlücke, für die P9 den Ersatzträger kennt.
    """
    d = daten or {}
    return d.get("pv_erzeugung_kwh") is not None or d.get("erzeugung_kwh") is not None


def bkw_ohne_eigenen_wert(
    aktive: Sequence[Investition],
    daten_je_investition: Mapping[int, Optional[dict]],
    *,
    uebergeben: Sequence[int] = (),
) -> list[Investition]:
    """Die Balkonkraftwerke, die im Monat einen Anteil am Anlagenwert bekommen (N-621).

    Selbst tragend (nicht an Modul-Kinder abgetreten, ADR-002/P11 — der
    Aufrufer übergibt dafür die im Monat **aktiven** Investitionen samt
    `pv-module`), nicht schon vom Aufrufer in die Auflösung gegeben
    (``uebergeben``) und ohne eigenen Wert in ``daten_je_investition``
    (``_bkw_hat_eigenen_wert``). Ein BKW ganz ohne Monatszeile gehört dazu.
    """
    abgetreten = abgetretene_bkw_ids(aktive)
    return [
        i for i in aktive
        if i.typ == BKW_TYP
        and i.id not in abgetreten
        and i.id not in uebergeben
        and not _bkw_hat_eigenen_wert(daten_je_investition.get(i.id))
    ]


def eigene_bkw_erzeugung_kwh(
    aktive: Sequence[Investition],
    daten_je_investition: Mapping[int, Optional[dict]],
) -> float:
    """Σ der eigenen Monatswerte der Balkonkraftwerke, die selbst tragen (N-611).

    Der Abzug, der aus dem Anlagenwert den Rest für die Modul-Lücken macht —
    an EINER Stelle, weil Leseseite (``lade_pv_je_monat``) und Import-Vorschau
    dieselbe Zahl brauchen (der Verteil-Schreibweg ``_verteile_anlagen_pv`` des
    Sammelimports ist mit HA-Bauform E4b entfallen).

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
    Das ist die Summe der **Prüf-Leser** (Daten-Checker-PV-Map, Import-Vorschau):
    gegen eine Teilsumme geprüft, meldeten sie Abweichungen, die es nicht gibt (N42).
    Die **Anzeige-Summe** eines solchen Monats ist seit N-626
    ``pv_teilsumme_je_monat`` (die vorhandenen Werte).
    """
    return {
        key: (sum(w.pv_erzeugung_kwh for w in werte.values())
              if ist_vollstaendig(werte) else None)
        for key, werte in monate.items()
    }


def pv_teilsumme_je_monat(monate: PvMonate) -> dict[tuple[int, int], Optional[float]]:
    """Σ der **vorhandenen** Modulwerte je Monat — die Anzeige-Summe (N-626, Gernot 04.10.2026).

    Neben ``pv_summe_je_monat``, nicht statt ihrer: Fehlt einem Modul der Wert und
    gibt es keinen Anlagenwert, trägt es hier nichts bei, und die übrigen Werte
    bleiben stehen — ein Modul-Ausfall kann auch korrekt sein; dass ein Wert fehlt,
    sagt der Daten-Checker („PV-Erzeugung unvollständig …", mit Reparaturweg) und
    das Flag ``pv_vollstaendig=False`` der Monats-Fakten. Bis dahin fiel die ganze
    Modulsumme weg (N42 „Teillücke ohne Aggregat ist Lücke, keine Teilsumme"), und
    der Monat zeigte nur das Balkonkraftwerk (90 statt 450, Eigenverbrauch 0).

    **Prüf-Leser bleiben bei ``pv_summe_je_monat``** (Daten-Checker-PV-Map,
    Import-Vorschau, ``gesamt_pv_kwh``): eine Prüfung gegen eine Teilsumme meldete
    Abweichungen, die es nicht gibt.

    ``None``, wo kein Modul einen Wert hat (alle ``fehlt``) — dann gibt es nichts
    anzuzeigen, wie bisher.
    """
    return {
        key: (sum(w.pv_erzeugung_kwh for w in werte.values() if w.quelle != QUELLE_FEHLT)
              if any(w.quelle != QUELLE_FEHLT for w in werte.values()) else None)
        for key, werte in monate.items()
    }
