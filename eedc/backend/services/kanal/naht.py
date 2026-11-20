"""Fortsetzung bei MQTT — die Naht als neue Kanal-Quelle (Sensorwechsel mit Grund, Bauplan B-4, S-3; Sitzung 2).

**Was sie tut.** Der Kanal «Eigene Summe» (``kanal/schreiber._eigene_summe``) bildet aus den MQTT-Rohständen je Stunde HAs
Summe (``core/berechnungen/ha_summe.ha_summe_der_periode``). Ein anderer Publisher auf anderem Niveau zählte dort heute als
Zuwachs (Sprung nach oben ganz, Rückgang unter 90 % als Reset ab 0 — Messblatt Konzept §10 M6). Ist der Wechsel mit Grund
**«Fortsetzung»** verzeichnet (``zuordnung_wechsel``), behandelt der Lauf ihn wie eine neue Quelle (``neue_quelle``): die
Stände **vor** ``erklaert_ts`` schließen die alte Periode, ab da beginnt eine neue Periode (``vorher = None``, der erste
Stand ist der Nullpunkt) mit einer neuen ``kanal_quelle`` (``gueltig_ab`` = ihre erste Stunde, ``offset`` = Kanalwert der
alten Periode am Schluss). Die Summenregel selbst (``ha_summe_der_periode``) bleibt unverändert.

**Wann ein Lauf die Naht anwendet:** wenn ein Stand ab ``erklaert_ts`` in diesem Lauf liegt **und** kein früherer Lauf einen
Rohstand ab ``erklaert_ts`` schon verbraucht hat (kein Rohstand in ``[erklaert_ts, von)``) — ein Publisher, der erst nach dem
Stundenende wieder sendet, bekommt die Naht im nächsten Lauf. Gesucht wird ab einem Tag vor dem Laufbeginn.
**Benannte Grenze:** schweigt der neue Publisher länger als einen Tag, oder hat der Lauf die Naht-Stunde vor der Erklärung
schon geschrieben, trägt der Kanal den Sprung — dann gilt der Nachtrag. **U3 b (G5):** wendet der Lauf eine Naht an, bekommt
die Wechsel-Zeile (MQTT davor und danach, noch ohne Rand-Stände) ``stand_alt_ende``/``stand_neu_null`` aus denselben
Rohständen (``zuordnung_wechsel/rohstand.rand_im_stundenlauf``) — die Reihe hebt dann um denselben Unterschied, den der Kanal
mit der Teilung schon zählt.

**Nachtrag** (``nachtrag_fortsetzung``; Aufrufer: Einstieg «Zähler getauscht» und «Grund nachtragen», Sitzung 4 — auch im
Nachbau-Abschnitt vor der HA-Statistik, Familie Mitschrift, ``nachfuellen._rohstaende``): für schon geschriebene
Zeilen eine Quellzeile mit ``gueltig_ab = H`` und ``offset = offset_alt − (wert(H) − wert(vorige Zeile))`` — die
Naht-Stunde trägt danach keinen Zuwachs, keine Kanalzeile wird umgeschrieben (Rohstände braucht er nicht; sie reichen nur
31 Tage); spätere Quellzeilen rücken um dieselbe Verschiebung mit. Beginnt an der Naht schon eine Quelle, tut er nichts
(zweimal = einmal).

Schwesterdateien: ``schreiber.py`` (der Stundenlauf), ``core/berechnungen/zaehler_naht.py`` (die Regel der Reihe, B-3).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Awaitable, Callable, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

_STUNDE = 3600
#: Wie weit vor dem Laufbeginn eine noch offene Naht gesucht wird.
NAHT_SUCHE = timedelta(days=1)

Zeilen = Callable[..., Awaitable[list[dict]]]


async def _rohstand_seit(db: AsyncSession, anlage_id: int, mqtt_key: str, ab: datetime, bis: datetime) -> bool:
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    return bool((await db.execute(select(func.count()).select_from(MqttEnergySnapshot).where(and_(
        MqttEnergySnapshot.anlage_id == anlage_id, MqttEnergySnapshot.energy_key == mqtt_key,
        MqttEnergySnapshot.timestamp >= ab, MqttEnergySnapshot.timestamp < bis,
    )))).scalar_one())


async def offene_naehte(db: AsyncSession, anlage_id: int, sensor_key: str, mqtt_key: str, von: datetime,
                        letzter: datetime) -> list[datetime]:
    """Die ``erklaert_ts`` der Fortsetzungs-Wechsel des Schlüssels, die dieser Lauf (Stände ab ``von`` bis ``letzter``)
    anwendet — aufsteigend."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

    kand = sorted(w.erklaert_ts for w in (await lade_wechsel(db, anlage_id)).get(sensor_key, ())
                  if w.grund == GRUND_FORTSETZUNG and w.aufgehoben_durch is None and w.erklaert_ts is not None
                  and von - NAHT_SUCHE <= w.erklaert_ts <= letzter)
    return [e for e in kand if e >= von or not await _rohstand_seit(db, anlage_id, mqtt_key, e, von)]


def _wert(zeile, art: str) -> Optional[float]:
    from backend.models.kanal import ART_STAND

    roh = (zeile.get if isinstance(zeile, dict) else lambda k: getattr(zeile, k))("state" if art == ART_STAND else "sum")
    return None if roh is None else float(roh)


async def zeilen_mit_naehten(db: AsyncSession, k, st, sensor_key: str, mqtt_key: str,
                             staende: list[tuple[datetime, float]], von: datetime, zeilen_der_periode: Zeilen) -> list[dict]:
    """Die Zeilen eines Laufs für einen Schlüssel — an jeder offenen Fortsetzungs-Naht geteilt (B-4). Ohne Naht wörtlich
    ``zeilen_der_periode(db, k, st, sensor_key, mqtt_key, staende)``."""
    from backend.services.kanal.schreiber import _KanalStand, _stunden_start_ts, aktuelle_quellen

    naehte = await offene_naehte(db, k.anlage.id, sensor_key, mqtt_key, von, staende[-1][0])
    if not naehte:
        return await zeilen_der_periode(db, k, st, sensor_key, mqtt_key, staende)
    from backend.services.zuordnung_wechsel.rohstand import rand_im_stundenlauf

    art, out = st.kanal.art, []
    for e in naehte:
        await rand_im_stundenlauf(db, k.anlage.id, sensor_key, mqtt_key, e)     # U3 b (G5): die Rand-Stände dieser Naht
        alt, staende = [x for x in staende if x[0] < e], [x for x in staende if x[0] >= e]
        zeilen = await zeilen_der_periode(db, k, st, sensor_key, mqtt_key, alt) if alt else []
        quelle = (await aktuelle_quellen(db, [st.kanal.id])).get(st.kanal.id)
        letzte = SimpleNamespace(**zeilen[-1]) if zeilen else st.letzte
        roh = _wert(letzte, art) if letzte is not None else None
        bisher = None if roh is None else roh + (float(quelle.offset) if quelle is not None else 0.0)
        # Die alte Periode endet in der Naht-Stunde: ihre Zeile dieser Stunde trägt die neue Periode (Wert = bisher + Zuwachs
        # ab dem ersten neuen Stand) — die Menge der alten Periode steht im Versatz der neuen Quelle.
        if zeilen and zeilen[-1]["start_ts"] == _stunden_start_ts(staende[0][0]):
            zeilen = zeilen[:-1]
            if quelle is not None and quelle.gueltig_ab == _stunden_start_ts(staende[0][0]):
                await db.delete(quelle)      # die alte Periode begann erst in dieser Stunde: ihre Quellzeile weicht
                await db.flush()
        out.extend(zeilen)
        st = _KanalStand(st.kanal, None if bisher is None else SimpleNamespace(
            sum=bisher, state=bisher, start_ts=letzte.start_ts), None)
    out.extend(await zeilen_der_periode(db, k, st, sensor_key, mqtt_key, staende))
    return out


def _menge(naht_zeile, davor_zeile, rand: Optional[tuple[float, float]]) -> Optional[float]:
    """Die Menge der Naht-Stunde aus den Rand-Ständen (U3 b, G5); ``None`` ohne ``rand`` oder ohne Stand an den Zeilen."""
    from backend.core.berechnungen.rohstand_rand import menge_der_naht

    if rand is None or naht_zeile.state is None or davor_zeile.state is None:
        return None
    return menge_der_naht(float(rand[0]), float(davor_zeile.state), float(naht_zeile.state), float(rand[1]))


async def menge_mit_rand(db: AsyncSession, kanal_id: int, stunde_ts: int, rand: tuple[float, float]) -> Optional[float]:
    """Was die Naht-Stunde ``stunde_ts`` nach dem Nachtrag mit ``rand`` zählt (Vorschau = Lauf: dieselbe ``_menge`` wie
    ``nachtrag_fortsetzung``); ``None`` ohne die zwei Zeilen."""
    from backend.models.kanal import KanalStatistik

    zeilen = (await db.execute(select(KanalStatistik).where(and_(
        KanalStatistik.kanal_id == kanal_id, KanalStatistik.start_ts <= stunde_ts,
    )).order_by(KanalStatistik.start_ts.desc()).limit(2))).scalars().all()
    if len(zeilen) < 2 or zeilen[0].start_ts != stunde_ts:
        return None
    return _menge(zeilen[0], zeilen[1], rand)


async def nachtrag_fortsetzung(db: AsyncSession, kanal_id: int, stunde_ts: int, versatz: Optional[float] = None,
                               rand: Optional[tuple[float, float]] = None) -> Optional[float]:
    """Nachtrag einer Fortsetzung für schon geschriebene Zeilen eines MQTT-Kanals (B-4): eine Quellzeile ab ``stunde_ts`` mit
    dem Versatz, der die Naht-Stunde ohne Zuwachs lässt (Kanalwert der Naht-Zeile = Kanalwert der vorigen Zeile). Keine
    Kanalzeile wird geändert; die abgeleiteten Kanäle, die aus dem Feld rechnen, werden ab der Stunde verworfen (der nächste
    Stundenlauf schreibt sie neu; Bauplan §10 Nr. 34 — die übrigen bleiben),
    gemerkte Tage ab dem Vortag.

    **Idempotent und über Quellgrenzen richtig** (Bauplan §9 Nr. 25): beginnt zwischen der vorigen Zeile und der Naht-Zeile
    schon eine Quelle (die Naht des Stundenlaufs, ein früherer Nachtrag, ein Quellwechsel), ist der Sprung dort schon
    überbrückt — nichts zu tun, der geltende Versatz bleibt. Spätere Quellzeilen tragen als Versatz den Kanalwert am Schluss
    ihrer Vorgängerin (``schreiber._eigene_summe_zeilen``); sie rücken um dieselbe Verschiebung mit, sonst käme der Sprung
    an ihrer Grenze zurück.

    **U2 a1 (F5):** ``versatz`` = der Versatz einer Naht mit Rand-Ständen (``stand_alt_ende − stand_neu_null``, Nachbau aus
    HA-Ständen): die neue Quellzeile hebt die Naht-Stunde dann um ihn statt sie ohne Zuwachs zu lassen — dieselbe Stunde wie
    die gehobene Reihe (die Naht-Zeile trägt den Stand des neuen, die vorige den des alten Sensors).

    **U3 b (Rechenweg G5):** ``rand`` = ``(stand_alt_ende, stand_neu_null)`` aus den MQTT-Rohständen — die Naht-Stunde trägt dann
    die Menge, die in den Rohständen steht (``core/berechnungen/rohstand_rand.menge_der_naht`` über die Stände der Zeile davor und
    der Naht-Zeile), statt ohne Zuwachs zu bleiben; der rohe Versatz allein wäre bei einem Neubeginn falsch (HAs Summenregel hat
    in der Stunde einen neuen Zyklus begonnen). Fehlt ein Stand an den Zeilen, gilt der Nachtrag ohne Zuwachs.

    Returns: der Versatz der Naht-Stunde (``None``: keine Zeile in der Stunde oder keine davor — nichts zu tun)."""
    from backend.models.kanal import FAMILIE_MITSCHRIFT, Kanal, KanalQuelle, KanalStatistik
    from backend.services.kanal import merken
    from backend.services.kanal.abgeleitet import verwerfe_ab
    from backend.services.kanal.korrektur import abhaengige_abgeleitete, gehoert_zu

    kanal = await db.get(Kanal, kanal_id)
    quellen = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == kanal_id)
                                .order_by(KanalQuelle.gueltig_ab))).scalars().all()
    quelle = next((q for q in reversed(quellen) if q.gueltig_ab <= stunde_ts), None)
    if kanal is None or quelle is None or quelle.familie != FAMILIE_MITSCHRIFT:
        raise ValueError("Nachtrag nur für einen Kanal der eigenen Summe (MQTT) mit geltender Quelle")
    zeilen = (await db.execute(select(KanalStatistik).where(and_(
        KanalStatistik.kanal_id == kanal_id, KanalStatistik.start_ts <= stunde_ts,
    )).order_by(KanalStatistik.start_ts.desc()).limit(2))).scalars().all()
    if len(zeilen) < 2 or zeilen[0].start_ts != stunde_ts:
        return None
    naht, davor = (_wert(z, kanal.art) for z in zeilen)
    if naht is None or davor is None:
        return None
    if quelle.gueltig_ab > zeilen[1].start_ts:
        return float(quelle.offset)          # an der Naht beginnt schon eine Quelle: der Sprung ist überbrückt
    verschiebung = -(naht - davor) if versatz is None else float(versatz)
    menge = _menge(zeilen[0], zeilen[1], rand)
    if menge is not None:
        from backend.core.berechnungen.rohstand_rand import verschiebung_der_naht

        verschiebung = verschiebung_der_naht(menge, naht, davor)
    for q in quellen:
        if q.gueltig_ab > stunde_ts:
            q.offset = float(q.offset) + verschiebung
    offset = float(quelle.offset) + verschiebung
    db.add(KanalQuelle(kanal_id=kanal_id, gueltig_ab=stunde_ts, familie=quelle.familie,
                       statistic_id=quelle.statistic_id, offset=offset))
    await db.flush()
    # Bauplan §10 Nr. 34: nur die abgeleiteten Kanäle, die aus diesem Feld rechnen (dieselbe Auskunft wie der Kanal-Schritt
    # der Korrektur, ``kanal/korrektur.abhaengige_abgeleitete``; unbekannter Schlüssel ⇒ alle).
    familien = await abhaengige_abgeleitete(db, kanal.anlage_id, kanal.key)
    await verwerfe_ab(db, kanal.anlage_id, stunde_ts, nur=lambda k: gehoert_zu(familien, k))
    for aid, tag in (await merken.tag_des_vorstands(db, [kanal_id], stunde_ts)).items():
        merken.invalidiere(aid, von=tag, db=db)
    return offset


__all__ = ["NAHT_SUCHE", "menge_mit_rand", "nachtrag_fortsetzung", "offene_naehte", "zeilen_mit_naehten"]
