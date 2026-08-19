"""Das PVGIS-SOLL je Monat — die eine Rechenstelle für den *Maßstab*.

**Anlass: eedc #387 (azywietz-web, 2026-08-19).** Der Community-Server rechnete
Teiljahre flach auf zwölf Monate hoch (``Σ ÷ n × 12``) und stellte das Ergebnis
neben echte Jahreswerte. Die Behebung braucht einen **Maßstab**: wie viel wäre
in genau diesen Monaten an genau dieser Anlage zu erwarten gewesen?

⚑ **Warum der Maßstab aus dem Client kommt und nicht vom Server** (Gernots
Rückfrage, Sitzung 70): Ein serverseitiges PVGIS wäre eine **zweite
Konstruktionsstelle** für dieselbe Größe — die Klasse von F-47. Und der Client
weiß mehr: exakte Koordinaten samt DEM-Horizont und eigenem Horizontprofil
statt einer Landesmitte, je Modulgruppe eigene Ausrichtung und Neigung,
AC-Kappung und Wechselrichtergrenze bereits enthalten — und vor allem den
**tagesgenau gekürzten Anschaffungsmonat**.

**Warum diese Datei überhaupt existiert.** ``pvgis.monatswerte`` wurde bisher an
mindestens drei Stellen inline entpackt (``api/routes/aussichten.py`` 545 · 678 ·
1203, jedes Mal dieselbe ``{monat: e_m}``-Schleife) — und **keine** davon kürzt
den Anschaffungsmonat; das tut nur ``cockpit/pv_strings.py``. Eine vierte Kopie
für den Gemeinschaftsdatensatz wäre genau die Bauform, an der #387 hing (dort
stand die Rechnung sechsmal im Baum). Deshalb: eine Stelle, hier.

**Die zwei Größen und ihr Verhältnis — das ist der Kern:**

- ``soll_je_monat`` ist **gekürzt**: der Anschaffungsmonat trägt nur seine Tage.
- ``soll_jahr_kwh`` ist **ungekürzt**: die volle Jahres-Erwartung der Anlage.

Der Server bildet daraus ``Σ soll_je_monat(vorhandene Monate) ÷ soll_jahr_kwh``
als Periodenanteil. Weil der Zähler gekürzt ist und der Nenner nicht, fällt der
Anteil kleiner aus — die Hochrechnung also höher, und genau das ist richtig:
gemessen wurden ja auch nur die Tage, die es gab. An azywietz' März (19.–31.3.,
13 Tage) hängt der Unterschied zwischen **832,1** und **348,6** kWh/kWp.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import anteilig, monatsfenster_investition
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.berechnungen.spez_ertrag import PV_ERZEUGER_TYPEN
from backend.models.investition import Investition
from backend.services.prognose_auswahl import lade_aktive_prognose


@dataclass(frozen=True)
class SollQuelle:
    """Die aktive PVGIS-Prognose, so weit sie für den Maßstab gebraucht wird."""

    #: Ungekürztes Anlagen-SOLL je Kalendermonat ``{1..12: kWh}``.
    anlage_je_monat: dict[int, float]
    #: Ungekürztes SOLL je Modul ``{investition_id: {1..12: kWh}}`` — leer,
    #: wenn die Prognose keine Modulauflösung trägt.
    modul_je_monat: dict[int, dict[int, float]]
    #: Volle Jahres-Erwartung der Anlage in kWh.
    jahr_kwh: Optional[float]


def _monatsmap(eintraege) -> dict[int, float]:
    """PVGIS-``monatswerte`` → ``{monat: e_m}``; unbrauchbare Einträge fallen weg."""
    werte: dict[int, float] = {}
    for eintrag in eintraege or []:
        try:
            m = int(eintrag.get("monat"))
            e = float(eintrag.get("e_m") or 0.0)
        except (TypeError, ValueError, AttributeError):
            continue
        if 1 <= m <= 12 and e > 0:
            werte[m] = e
    return werte


async def lade_soll_quelle(db: AsyncSession, anlage_id: int) -> Optional[SollQuelle]:
    """Die **aktive** Prognose der Anlage (P5) — oder ``None``.

    ``None`` heißt „kein Maßstab", **kein** Rückfall auf eine inaktive Prognose:
    wer alle deaktiviert hat, will keine SOLL-Werte sehen. Der Datensatz trägt
    dann keine SOLL-Felder, und der Server fällt auf seine eigene Kaskade zurück.
    """
    prognose = await lade_aktive_prognose(db, anlage_id)
    if prognose is None:
        return None

    modul_je_monat: dict[int, dict[int, float]] = {}
    for inv_id_str, monatsdaten in (prognose.module_monatswerte or {}).items():
        try:
            modul_je_monat[int(inv_id_str)] = _monatsmap(monatsdaten)
        except (TypeError, ValueError):
            continue

    return SollQuelle(
        anlage_je_monat=_monatsmap(prognose.monatswerte),
        modul_je_monat={k: v for k, v in modul_je_monat.items() if v},
        jahr_kwh=float(prognose.jahresertrag_kwh) if prognose.jahresertrag_kwh else None,
    )


def soll_fuer_monat(
    quelle: Optional[SollQuelle],
    erzeuger: Sequence[Investition],
    jahr: int,
    monat: int,
) -> Optional[float]:
    """SOLL dieses Monats in kWh — mit tagesgenau gekürzten Geräte-Kanten.

    Args:
        quelle: aus :func:`lade_soll_quelle`. ``None`` ⇒ Ergebnis ``None``.
        erzeuger: die Investitionen der Anlage (gefiltert wird hier auf
            ``PV_ERZEUGER_TYPEN``, damit ein BHKW den PV-Maßstab nicht anhebt —
            dieselbe Achse wie ``ertrag_kwh`` im Gemeinschaftsdatensatz).
        jahr, monat: der Monat.

    Returns:
        kWh oder ``None``, wenn es keinen Maßstab für diesen Monat gibt.

    **Zwei Wege, und der zweite ist eine benannte Näherung:**

    1. **Je Modul** (``module_monatswerte`` vorhanden): jedes Modul bringt seine
       eigene Ausrichtung mit, gekürzt mit **seinen** Kanten
       (``anschaffungsdatum``/``stilllegungsdatum``). Das ist der genaue Weg.
    2. **Anlagenweit**: das Anlagen-SOLL wird mit dem Fenster gekürzt, das der
       **früheste** Erzeuger aufspannt — also dem Anlagenstart. Wer mitten im
       Monat einen zweiten String dazustellt, bekommt dessen Anteil hier nicht
       tagesgenau abgezogen; der Fehler wirkt nur im Zubau-Monat und nur nach
       oben (das SOLL fällt eher zu hoch aus, die Anlage sieht sich also eher
       schlechter). Die genaue Zerlegung existiert nur mit Modulauflösung, und
       eine erfundene wäre schlechter als eine benannte Näherung.

    ⚠ Bewusst **nur** die Geräte-Kanten, nicht der laufende Monat: das ist die
    andere Datums-Ebene (``monatsfenster``, N-69), und der Gemeinschaftsdatensatz
    enthält seit F-48 ohnehin keinen unfertigen Monat mehr.
    """
    if quelle is None:
        return None

    # ADR-002/P11 (N-266): Seit ein Balkonkraftwerk `pv-module` als Kinder
    # tragen darf, liegen Eltern und Kind in DERSELBEN Typ-Menge. Ein BKW mit
    # Modul-Kindern hat kWp, Ausrichtung — und damit sein SOLL — an die Kinder
    # abgetreten; ohne den Selektor stünde es hier ein zweites Mal und der
    # Maßstab wäre zu groß. **Der Selektor läuft NACH dem Zeitfilter:** in
    # einem Monat vor der Anschaffung der Module trägt das BKW seine Größen
    # noch selbst. Der baumweite Wächter ist
    # `test_wurzelmuster_konformitaet.py::test_p11_*` — er hat genau diesen
    # Fehler beim ersten Entwurf dieser Datei gefangen.
    im_monat = [
        inv for inv in erzeuger
        if inv.typ in PV_ERZEUGER_TYPEN and inv.ist_aktiv_im_monat(jahr, monat)
    ]
    pv = list(erzeuger_traeger(im_monat))
    if not pv:
        return None

    if quelle.modul_je_monat:
        summe = 0.0
        getroffen = False
        for inv in pv:
            roh = quelle.modul_je_monat.get(inv.id, {}).get(monat)
            if roh is None:
                continue
            fenster = monatsfenster_investition(
                jahr, monat,
                ab=getattr(inv, "anschaffungsdatum", None),
                bis=getattr(inv, "stilllegungsdatum", None),
            )
            if fenster.tage == 0:
                continue
            summe += (anteilig(roh, fenster) or 0.0) if fenster.ist_angefangen else roh
            getroffen = True
        return round(summe, 1) if getroffen else None

    roh = quelle.anlage_je_monat.get(monat)
    if roh is None:
        return None

    ab_kandidaten = [
        inv.anschaffungsdatum for inv in pv
        if getattr(inv, "anschaffungsdatum", None) is not None
    ]
    if not ab_kandidaten:
        return round(roh, 1)

    fenster = monatsfenster_investition(jahr, monat, ab=min(ab_kandidaten))
    if fenster.tage == 0:
        return None
    if not fenster.ist_angefangen:
        return round(roh, 1)
    return round(anteilig(roh, fenster) or 0.0, 1)


async def lade_erzeuger(db: AsyncSession, anlage_id: int) -> list[Investition]:
    """Die Erzeuger-Investitionen der Anlage — ohne ``aktiv``-Filter.

    Wie in ``lade_monats_fakten``: historische Monate dürfen eine später
    deaktivierte Komponente nicht rückwirkend verlieren (#123). Die Sichtbarkeit
    je Monat entscheiden die Datums-Kanten in :func:`soll_fuer_monat`.
    """
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ.in_(PV_ERZEUGER_TYPEN),
        )
    )
    return list(result.scalars().all())
