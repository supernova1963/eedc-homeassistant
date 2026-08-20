"""Zählerstände unter *Sonstiges* — **der eine Leser** (#377 / N-294).

**Das Modell in fünf Sätzen** (Entscheid Gernot, 2026-08-20):

1. Ein *Sonstiges*-Gerät der Kategorie ``zaehler`` führt **eine einheitenlose
   Zahl**: den **Zählerstand**.
2. Die **einzige** Rechnung darauf ist **Ende − Anfang** des Zeitfensters.
3. Die **Einheit** steht in den Stammdaten des Geräts (``zaehler_einheit``) und
   wird **nur bei der Anzeige** geholt — nie zum Rechnen, nie zum Umrechnen.
4. Der Stand kommt aus einem Sensor (stündlich in ``sensor_snapshots``) **oder**
   wird im Monatsabschluss von Hand gepflegt — für den Gaszähler, den man
   abliest.
5. **Sonst wird die Zahl überall ignoriert:** keine Energiebilanz, keine
   Autarkie, kein ROI, kein CO₂, kein Community-Datensatz, keine Serie im
   Energiefluss.

---

**Warum ein einziger Leser und nicht vier.** Vier Anzeigen brauchen dieselbe
Auskunft — *Live/Auf einen Blick*, *Cockpit Tag/Monat/Jahr*,
*Komponenten/Sonstiges* und die Tabellen. Vier Kopien derselben Fensterlogik
wären die Klasse, gegen die ADR-002/P10 gebaut ist: Sechs Befunde der
Drift-Inventur vom 31.07. entstanden genau so, **ohne einen einzigen
Rechenfehler** — jede Read-Site faltete selbst, und die Faltungen liefen
auseinander.

---

⚠ **Ein Zählerstand ist eine BESTANDSgröße, keine Flussgröße.** Er summiert
sich über nichts: zwei Gaszähler mit 12.345 und 8.900 ergeben nicht 21.245,
auch nicht bei gleicher Einheit. Summierbar ist allein die **Differenz**, und
die ist eine andere Größe. Deshalb liefert dieses Modul **je Gerät** und niemals
eine Anlagensumme — und deshalb tragen die Tabellen-Spalten
``aggregation: 'none'``.

⚠ **Unvollständige Fenster sagen es** (ADR-002/P4). Beginnt die Aufzeichnung
erst **innerhalb** des Fensters, ist die Differenz nicht die Fenster-Differenz,
sondern nur der beobachtete Teil. Das steht als ``anfang_vollstaendig=False`` an
der Antwort, statt eine zu kleine Zahl kommentarlos hinzustellen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.field_definitions import (
    ZAEHLERSTAND_FELD,
    einheit_fuer,
    ist_zaehler_kategorie,
)
from backend.core.investition_parameter import PARAM_SONSTIGES, PARAM_SONSTIGES_DEFAULTS
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.sensor_snapshot import SensorSnapshot

#: Schlüssel eines Zählerstands in `sensor_snapshots`.
def sensor_key_fuer(investition_id: int) -> str:
    """``inv:<id>:zaehlerstand`` — dasselbe Schema wie jeder andere Zähler."""
    return f"inv:{investition_id}:{ZAEHLERSTAND_FELD}"


@dataclass(frozen=True)
class VerlaufPunkt:
    """Ein abgelesener Stand zu einem Zeitpunkt."""

    zeitpunkt: datetime
    stand: float


@dataclass
class ZaehlerFenster:
    """Was ein Zähler über ein Zeitfenster zu sagen hat.

    ``differenz`` ist die **einzige** gerechnete Größe und bleibt ``None``,
    wenn einer der beiden Stände fehlt — nicht 0. Ein fehlender Stand ist keine
    Nullmenge (ADR-002/P4).
    """

    investition_id: int
    name: str
    art: str
    einheit: str
    stand_anfang: Optional[float] = None
    stand_ende: Optional[float] = None
    differenz: Optional[float] = None
    #: False, wenn der Anfangsstand **nach** dem Fensterbeginn liegt — dann
    #: deckt `differenz` nur einen Teil des Fensters ab.
    anfang_vollstaendig: bool = True
    verlauf: list[VerlaufPunkt] = field(default_factory=list)


def zaehler_art(inv: Investition) -> str:
    """Medium-Art des Geräts — Label und Symbol, sonst ohne Wirkung."""
    params = inv.parameter or {}
    return str(
        params.get(PARAM_SONSTIGES["ZAEHLER_ART"])
        or PARAM_SONSTIGES_DEFAULTS["zaehler_art"]
    )


def zaehler_einheit(inv: Investition) -> str:
    """Anzeige-Einheit des Geräts — **durchgereicht, nicht zweitgelesen**.

    Der eine Leser ist `field_definitions.einheit_fuer` (S5). Diese Funktion
    existiert nur als bequemer Name für den häufigsten Aufruf; sie darf die
    Auflösung **nicht** selbst nachbauen, sonst gäbe es zwei Antworten auf
    dieselbe Frage — genau die Klasse, gegen die S5 gebaut ist.

    ⚠ Die Einheit steht neben der Zahl und wird nie zum Rechnen benutzt: eedc
    rechnet Zählerstände grundsätzlich nicht um.
    """
    return einheit_fuer(ZAEHLERSTAND_FELD, inv)


def ist_zaehler_investition(inv: Investition) -> bool:
    """Ist das ein *Sonstiges*-Gerät der Kategorie ``zaehler``?"""
    if inv.typ != "sonstiges":
        return False
    return ist_zaehler_kategorie((inv.parameter or {}).get(PARAM_SONSTIGES["KATEGORIE"]))


async def lade_zaehler_investitionen(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: Optional[date] = None,
    bis: Optional[date] = None,
) -> list[Investition]:
    """Alle Zähler-Geräte einer Anlage, in stabiler Reihenfolge.

    ``von``/``bis`` filtern auf *im Fenster aktiv* — ein stillgelegter Zähler
    verschwindet damit aus den **laufenden** Sichten, bleibt aber in jeder
    Sicht erhalten, in deren Zeitraum er hineingemessen hat. Das ist der
    Unterschied, an dem der Zählerwechsel hängt (§4 des Konzepts): stilllegen
    bewahrt die Historie, ``aktiv=False`` löscht sie aus jeder Sicht.

    ⚠ **Das ganze Fenster zählt, nicht sein letzter Tag.** Ein am 15. Juni
    stillgelegter Zähler gehört in die Auswertung Januar–Juni; er hat sie
    schließlich mitgemessen. Ein Filter auf ``bis`` allein ließe ihn genau aus
    der Sicht fallen, für die er die Zahlen geliefert hat — gefangen von
    `test_377_zaehlerwechsel.py::test_stillgelegter_zaehler_bleibt_historisch_sichtbar`.
    """
    rows = (await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == "sonstiges")
        .order_by(Investition.anschaffungsdatum, Investition.id)
    )).scalars().all()
    zaehler = [inv for inv in rows if ist_zaehler_investition(inv)]
    if von is not None and bis is not None:
        zaehler = [inv for inv in zaehler if inv.ist_aktiv_im_zeitraum(von, bis)]
    return zaehler


async def _gepflegte_monatsstaende(
    db: AsyncSession, investition_ids: list[int]
) -> dict[int, list[VerlaufPunkt]]:
    """Von Hand gepflegte Monatsend-Stände je Investition.

    Sie ergänzen die Snapshots, statt mit ihnen zu konkurrieren: Wer seinen
    Gaszähler einmal im Monat abliest, hat gar keinen Sensor — und wer beides
    hat, bekommt den gepflegten Wert dort, wo der Sensor eine Lücke hat.
    Zeitpunkt ist das **Monatsende**, weil der Anwender genau das einträgt
    („Zählerstand am Monatsende").
    """
    if not investition_ids:
        return {}
    from calendar import monthrange

    rows = (await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(investition_ids))
    )).scalars().all()

    out: dict[int, list[VerlaufPunkt]] = {}
    for imd in rows:
        wert = (imd.verbrauch_daten or {}).get(ZAEHLERSTAND_FELD)
        if wert is None:
            continue
        try:
            stand = float(wert)
        except (TypeError, ValueError):
            continue
        letzter_tag = monthrange(imd.jahr, imd.monat)[1]
        ts = datetime(imd.jahr, imd.monat, letzter_tag, 23, 59, 59)
        out.setdefault(imd.investition_id, []).append(VerlaufPunkt(ts, stand))
    for punkte in out.values():
        punkte.sort(key=lambda p: p.zeitpunkt)
    return out


async def lade_zaehlerstaende(
    db: AsyncSession,
    anlage_id: int,
    von: datetime,
    bis: datetime,
    *,
    mit_verlauf: bool = True,
    nur_aktive: bool = True,
) -> list[ZaehlerFenster]:
    """Stand am Anfang, Stand am Ende, Differenz und Verlauf — je Gerät.

    Args:
        von: Beginn des Fensters (einschließlich).
        bis: Ende des Fensters (einschließlich).
        mit_verlauf: Punkte im Fenster mitliefern. Die Kacheln brauchen sie
            nicht, die Diagramme schon.
        nur_aktive: Geräte ausblenden, die am Fensterende bereits stillgelegt
            waren. Für die historischen Sichten auf ``False`` setzen — ein
            gewechselter Zähler gehört in die Vergangenheit, in die er
            hineingemessen hat.

    Returns:
        Ein Eintrag je Zähler-Gerät, auch wenn es für das Fenster **keinen**
        Wert gibt. Ein Gerät stillschweigend wegzulassen, sähe aus wie „es gibt
        keinen Zähler" statt „für diesen Zeitraum liegt nichts vor".
    """
    zaehler = await lade_zaehler_investitionen(
        db, anlage_id,
        von=von.date() if nur_aktive else None,
        bis=bis.date() if nur_aktive else None,
    )
    if not zaehler:
        return []

    ids = [inv.id for inv in zaehler]
    keys = {sensor_key_fuer(i): i for i in ids}

    # Alle Snapshots BIS zum Fensterende holen — der Anfangsstand kann älter
    # sein als `von` (der letzte bekannte Stand vor dem Fenster gilt fort).
    snap_rows = (await db.execute(
        select(SensorSnapshot.sensor_key, SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh)
        .where(SensorSnapshot.anlage_id == anlage_id)
        .where(SensorSnapshot.sensor_key.in_(list(keys)))
        .where(SensorSnapshot.zeitpunkt <= bis)
        .order_by(SensorSnapshot.zeitpunkt)
    )).all()

    punkte_je_inv: dict[int, list[VerlaufPunkt]] = {i: [] for i in ids}
    for key, ts, wert in snap_rows:
        if wert is None:
            continue
        punkte_je_inv[keys[key]].append(VerlaufPunkt(ts, float(wert)))

    # Gepflegte Monatsstände dazu — sie füllen Lücken und tragen den Fall
    # „gar kein Sensor" ganz allein.
    for inv_id, punkte in (await _gepflegte_monatsstaende(db, ids)).items():
        vorhanden = {p.zeitpunkt for p in punkte_je_inv[inv_id]}
        punkte_je_inv[inv_id].extend(
            p for p in punkte if p.zeitpunkt <= bis and p.zeitpunkt not in vorhanden
        )
        punkte_je_inv[inv_id].sort(key=lambda p: p.zeitpunkt)

    out: list[ZaehlerFenster] = []
    for inv in zaehler:
        alle = punkte_je_inv.get(inv.id) or []
        fenster = ZaehlerFenster(
            investition_id=inv.id,
            name=inv.bezeichnung,
            art=zaehler_art(inv),
            einheit=zaehler_einheit(inv),
        )
        if alle:
            # Anfang: der letzte Stand VOR dem Fenster gilt fort. Gibt es
            # keinen, beginnt die Aufzeichnung im Fenster — dann ist der erste
            # Wert darin der Anfang, und das Fenster ist unvollständig (P4).
            # `<=` beim Anfang, nicht `<`: Ein Stand **exakt zum Fensterbeginn**
            # IST der Anfangsstand — an der Dev-Box gemessen, wo der erste
            # Snapshot auf 01.08. 00:00 lag und das Fenster ebenfalls dort
            # begann. Mit `<` galt das Fenster als unvollständig, obwohl der
            # Wert genau an seiner Kante gemessen wurde.
            davor = [p for p in alle if p.zeitpunkt <= von]
            drin = [p for p in alle if von < p.zeitpunkt <= bis]
            if davor:
                fenster.stand_anfang = davor[-1].stand
            elif drin:
                fenster.stand_anfang = drin[0].stand
                fenster.anfang_vollstaendig = False
            if drin:
                fenster.stand_ende = drin[-1].stand
            elif davor:
                # Nichts Neues im Fenster: der Stand steht, wo er stand.
                # Differenz 0 ist hier die richtige Aussage, nicht „unbekannt".
                fenster.stand_ende = davor[-1].stand
            if fenster.stand_anfang is not None and fenster.stand_ende is not None:
                fenster.differenz = round(fenster.stand_ende - fenster.stand_anfang, 3)
            if mit_verlauf:
                fenster.verlauf = drin
        out.append(fenster)
    return out
