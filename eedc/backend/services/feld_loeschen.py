"""Die Daten EINES Felds vor einem Zeitpunkt löschen — der eine Baustein für «Daten vor der Änderung löschen» beim
Sensorwechsel (Weg B, Entscheid Gernot 21.11.2026, Bauplan Sensorwechsel Nr. 174–180) und die Werkbank-Operation «Werte vor
dem Sensorbeginn verwerfen» teilt die Bausteine der Kanal- und Bestandsschicht (``kanal/verwerfen``,
``verwerfen_vor_quellbeginn.leere_bestand``), läuft aber seit dem Rückbau des Korrektur-Kerns (Weg B, Sitzung B3a) wieder auf
ihrem eigenen Weg wie in v4.3.1 (sie löscht keine Zählerstände, füllt nichts nach und bildet keine Tage neu).

**Was weg ist** (nur dieses Feld, nur vor ``t``):

* **Kanal:** die Zeilen vor ``t`` (``kanal/verwerfen.loesche_zeilen``). Mit ``zum_platzhalter`` werden die bisherigen Quellen
  zu EINER verworfenen Quelle ohne Entity zusammengefasst (``kanal/verwerfen.zum_platzhalter``) und die Nachfüll-Marke
  gelöscht: die Zeit davor ist bewusst leer (die übrigen Felder behalten ihre Kanal-Deckung, ``bilanz_adapter.BewusstLeer``),
  und das Nachfüllen holt die Geschichte des neuen Sensors, soweit Home Assistant sie führt (``nachfuellen._erste_ohne_platzhalter``)
  — das Feld verhält sich, als wäre der neue Sensor von Anfang an zugeordnet. Ohne: die Quellen bekommen die Marke «verworfen
  am» (Werkbank-Form, ein Halt fürs Nachfüllen). Mit ``teilen`` (Werkbank «Werte eines Felds vor einem Zeitpunkt verwerfen»,
  ``services/verwerfen_vor_zeitpunkt.py``, Fund-Päckchen H): die bei ``t`` geltende Quelle wird geteilt
  (``kanal/verwerfen.teile_quelle``), die Nachfüll-Marke bleibt — das Feld verhält sich, als wäre seine Quelle erst ab ``t``
  zugeordnet.
* **Zählerstände** (``sensor_snapshots``) und **MQTT-Rohstände** des Schlüssels vor ``t`` (``verwerfe_staende``).
* **Wechsel-Zeilen** des Schlüssels (nur mit ``zum_platzhalter``; ``loesche_wechsel``): ohne sie gilt für jede Zeit die heutige
  Zuordnung. Die Werkbank löscht über denselben Baustein die Wechsel bis zum Ende der ersten Stunde ab ihrem Zeitpunkt, einen
  «Zähler getauscht» nur bis zu ihrem Zeitpunkt.
* **Bestand:** der Feld-Schlüssel in Stunden- und Tageszeilen bis zum Bestandstag von ``t``
  (``verwerfen_vor_quellbeginn.leere_bestand``) — mit ``auch_abschluss`` in **allen** Monaten, sonst ohne Monate mit
  Abschluss.
* **Abgeleitete Kanäle** der Familien dieses Felds (PV-Anteil der Heimladung, Strom je Betriebsart, Kosten —
  ``kanal/korrektur.abhaengige_abgeleitete``) ab dem ersten gelöschten Stand; der Lauf schreibt sie neu.

**Was bleibt:** jedes andere Feld (an den neu gebildeten Tagen ändert der Neu-Aufbau nur, was auch «Tag neu aggregieren» dort
ändert); die **gespeicherten Monatswerte** (Monatsabschluss, Handeingabe — eedc kann beide nicht
unterscheiden; der Dialog nennt die Monate und den Weg zur Handkorrektur).

**Danach im Hintergrund** (``korrektur_lauf`` mit Art ``loeschen``; ``nachlauf``): mit Home Assistant zuerst die Geschichte des
neuen Sensors nachfüllen (scheitert es — Home Assistant nicht erreichbar —, bleibt der Lauf offen und der Stundenlauf holt es
nach), dann die abgeleiteten Kanäle neu schreiben, dann die Tage neu bilden, deren Tageszeile das Feld trug, und den Tag von ``t``.
**Nicht rücknehmbar** — der Rückweg ist eine Sicherung.

Schwesterdateien: ``services/kanal/verwerfen.py`` (Kanal-Schicht), ``services/verwerfen_vor_quellbeginn.py`` (Bestand),
``services/zuordnung_wechsel/abfrage.py`` (Dialog), ``services/zuordnung_wechsel/korrektur_lauf.py`` (Lauf),
``services/daten_checker/datenquelle/geloescht.py`` (Auskunft).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.zuordnung_wechsel.korrektur_lauf import ART_LOESCHEN as ART  # noqa: E402 — Art des Laufs und des Nachlaufs


@dataclass
class Geloescht:
    """Was ``loesche_vor`` getan hat — Aktivität, Antwort der Route, Proben."""

    key: str
    t: datetime
    kanal_id: Optional[int] = None
    kanalzeilen: int = 0
    quellen: int = 0
    staende: int = 0
    rohstaende: int = 0
    wechsel: int = 0
    bestand: dict = field(default_factory=dict)
    #: Erster gelöschter Kanal-Stand (``start_ts``) — ab dort werden die abhängigen abgeleiteten Kanäle neu geschrieben.
    w0: Optional[int] = None
    abgeleitet_familien: Optional[frozenset] = None
    abgeleitet_verworfen: int = 0
    #: H1 (Werkbank «vor einem Zeitpunkt»): 1, wenn die bei ``t`` geltende Quelle geteilt wurde.
    geteilt: int = 0
    #: Die Tage, die der Lauf neu bildet (Tageszeile trug das Feld, dazu der Tag von ``t``).
    tage: list[date] = field(default_factory=list)


async def verwerfe_staende(db: AsyncSession, anlage_id: int, key: str, bis: datetime,
                           von: Optional[datetime] = None) -> tuple[int, int]:
    """Zählerstände (``sensor_snapshots``) und MQTT-Rohstände des Schlüssels in ``[von, bis)`` löschen (``von`` ``None`` =
    von Beginn an). Returns: ``(Zählerstände, Rohstände)``."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.snapshot.keys import _sensor_key_to_mqtt_key

    bed = [SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key, SensorSnapshot.zeitpunkt < bis]
    if von is not None:
        bed.append(SensorSnapshot.zeitpunkt >= von)
    zs = int((await db.execute(delete(SensorSnapshot).where(and_(*bed)))).rowcount or 0)
    mk = _sensor_key_to_mqtt_key(key)
    rs = 0
    if mk:
        bed = [MqttEnergySnapshot.anlage_id == anlage_id, MqttEnergySnapshot.energy_key == mk,
               MqttEnergySnapshot.timestamp < bis]
        if von is not None:
            bed.append(MqttEnergySnapshot.timestamp >= von)
        rs = int((await db.execute(delete(MqttEnergySnapshot).where(and_(*bed)))).rowcount or 0)
    return zs, rs


async def _tage_mit_feld(db: AsyncSession, anlage_id: int, ziele, bis_tag: date) -> list[date]:
    """Die Tage bis ``bis_tag``, deren Tageszeile einen Schlüssel des Felds trägt (alle Monate) — vor dem Leeren gelesen."""
    from backend.services.verwerfen_vor_quellbeginn import _tz_zeilen, tz_keys_der_zeile

    return sorted({row.datum for row in await _tz_zeilen(db, anlage_id, bis_tag, ziele) if tz_keys_der_zeile(row, ziele)})


async def _kanal(db: AsyncSession, g: Geloescht, anlage_id: int, t_ts: int, jetzt_ts: int, zum_platzhalter: bool,
                 teilen: bool = False) -> None:
    from backend.models.kanal import Kanal, KanalNachfuellung, KanalStatistik
    from backend.services.kanal import verwerfen as kv
    from backend.services.kanal.abgeleitet import verwerfe_ab
    from backend.services.kanal.korrektur import abhaengige_abgeleitete, gehoert_zu

    k = (await db.execute(select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.key == g.key)))).scalar_one_or_none()
    if k is None:
        return
    g.kanal_id = k.id
    g.w0 = (await db.execute(select(func.min(KanalStatistik.start_ts)).where(and_(
        KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts < t_ts)))).scalar_one_or_none()
    g.kanalzeilen = await kv.loesche_zeilen(db, k.id, t_ts)
    if zum_platzhalter:
        g.quellen = await kv.zum_platzhalter(db, k.id, t_ts, jetzt_ts)
        await db.execute(delete(KanalNachfuellung).where(KanalNachfuellung.kanal_id == k.id))
    elif teilen:                     # H1: Quelle bei t teilen, die Nachfüll-Marke bleibt (nichts vor t kommt zurück)
        g.quellen, g.geteilt = await kv.teile_quelle(db, k.id, t_ts, jetzt_ts)
    else:
        g.quellen = await kv.markiere_quellen(db, k.id, t_ts, jetzt_ts)
    if g.w0 is not None:
        g.abgeleitet_familien = await abhaengige_abgeleitete(db, anlage_id, g.key)
        g.abgeleitet_verworfen = await verwerfe_ab(db, anlage_id, g.w0,
                                                   nur=lambda key: gehoert_zu(g.abgeleitet_familien, key))


async def loesche_wechsel(db: AsyncSession, anlage_id: int, key: str, *, bis: Optional[datetime] = None,
                          gleiche_quelle_bis: Optional[datetime] = None) -> int:
    """Die verzeichneten Wechsel des Schlüssels löschen — alle («löschen»), mit ``bis`` die mit ``ab_ts ≤ bis`` (Werkbank «Werte
    vor dem Sensorbeginn verwerfen», Bauplan Sensorwechsel Nr. 184/2); ohne sie gilt dort die heutige Zuordnung (B-0). Mit
    ``gleiche_quelle_bis`` (der Zeitpunkt der Werkbank) eine Zeile derselben Quelle («Zähler getauscht») nur mit ``ab_ts`` bis
    dorthin — ein Tausch in der ersten Stunde ab dem Zeitpunkt bleibt verzeichnet, sonst zählte sein Sprung wieder als Menge
    (Korrekturrunde WEGB-K, Nachmessung B1). In der Sitzung des Aufrufers, ohne Commit. Returns: Zahl der gelöschten Zeilen."""
    from backend.models.zuordnung_wechsel import ZuordnungWechsel
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss

    bed = await _wechsel_bedingung(db, anlage_id, key, bis, gleiche_quelle_bis)
    n = int((await db.execute(delete(ZuordnungWechsel).where(and_(*bed)))).rowcount or 0)
    vergiss(db, anlage_id)
    return n


async def zaehle_wechsel(db: AsyncSession, anlage_id: int, key: str, *, bis: Optional[datetime] = None,
                         gleiche_quelle_bis: Optional[datetime] = None) -> int:
    """Wie viele Wechsel ``loesche_wechsel`` mit denselben Angaben löschen würde (Vorschau, Fund-Päckchen H)."""
    from backend.models.zuordnung_wechsel import ZuordnungWechsel

    bed = await _wechsel_bedingung(db, anlage_id, key, bis, gleiche_quelle_bis)
    return int((await db.execute(select(func.count()).select_from(ZuordnungWechsel).where(and_(*bed)))).scalar_one())


async def _wechsel_bedingung(db: AsyncSession, anlage_id: int, key: str, bis: Optional[datetime],
                             gleiche_quelle_bis: Optional[datetime]) -> list:
    """Die eine Auswahl der Wechsel für ``loesche_wechsel`` und ``zaehle_wechsel``."""
    from backend.models.zuordnung_wechsel import ZuordnungWechsel
    from backend.services.zuordnung_wechsel.zeitpunkt import gleiche_quelle

    bed = [ZuordnungWechsel.anlage_id == anlage_id, ZuordnungWechsel.sensor_key == key]
    if bis is not None:
        bed.append(ZuordnungWechsel.ab_ts <= bis)
    if gleiche_quelle_bis is not None:
        bleibt = [w.id for w in (await db.execute(select(ZuordnungWechsel).where(and_(*bed)))).scalars().all()
                  if w.ab_ts > gleiche_quelle_bis and gleiche_quelle(w.vorher, w.nachher)]
        bed.append(ZuordnungWechsel.id.not_in(bleibt))
    return bed


async def loesche_vor(db: AsyncSession, anlage, key: str, t: datetime, *, auch_abschluss: bool, zum_platzhalter: bool,
                      jetzt: Optional[datetime] = None, teilen: bool = False) -> Geloescht:
    """Die Daten des Felds ``key`` vor ``t`` löschen (Modul-Docstring), in der Sitzung des Aufrufers, ohne Commit.

    ``teilen`` (Werkbank «Werte eines Felds vor einem Zeitpunkt verwerfen», Fund-Päckchen H): statt Platzhalter bzw. Marke
    wird die bei ``t`` geltende Quelle geteilt (``kanal/verwerfen.teile_quelle``), die Nachfüll-Marke bleibt, und die
    verzeichneten Wechsel gehen wie in der Werkbank-Form nur bis zum Ende der ersten Stunde ab ``t`` (``loesche_wechsel``
    mit ``bis``/``gleiche_quelle_bis``) — das Feld verhält sich, als wäre seine Quelle erst ab ``t`` zugeordnet."""
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.kanal import merken
    from backend.services.kanal.abgeleitet import tag_der_stunde

    jetzt = (jetzt or datetime.now()).replace(microsecond=0)
    t_ts = int(t.timestamp())
    g = Geloescht(key=key, t=t)
    ziele = await vq.bestand_ziele(db, anlage, key)
    bis_tag = tag_der_stunde(t_ts)
    g.tage = sorted(set(await _tage_mit_feld(db, anlage.id, ziele, bis_tag)) | {bis_tag})
    await _kanal(db, g, anlage.id, t_ts, int(jetzt.timestamp()), zum_platzhalter, teilen)
    g.staende, g.rohstaende = await verwerfe_staende(db, anlage.id, key, t)
    if zum_platzhalter:
        g.wechsel = await loesche_wechsel(db, anlage.id, key)
    elif teilen:
        g.wechsel = await loesche_wechsel(db, anlage.id, key, bis=datetime.fromtimestamp(t_ts + 3600),
                                          gleiche_quelle_bis=t)
    abschluss = frozenset() if auch_abschluss else await vq.abschluss_monate(db, anlage.id)
    g.bestand = await vq.leere_bestand(db, anlage.id, ziele, bis_tag, abschluss)
    merken.invalidiere(anlage.id, db=db)
    return g


# ── Dialog: was «löschen» tut (Wortlaute, Weg B) ────────────────────────────────────────────────────────────────────────

#: Teil 3 Fund-Päckchen H (Entscheid Master 24.11.2026): der Lauf bildet die Tage mit dem Neu-Aufbau von «Tag neu aggregieren»
#: neu (``korrektur_lauf._ein_tag``) — was der an anderen Feldern ändert, ändert er auch hier (Produktiv-Kopie: 01.11.2024
#: Wallbox 0,0 → «—», Speicher-Wirkungsgrad 02.–09.11.2024; gemessen an der Werkbank-Operation, derselbe Baustein).
SATZ_NUR_DIESES = ("Gelöscht werden nur die Daten dieses Felds vor der Änderung; die anderen Felder bleiben — an den Tagen, die "
                   "eedc danach neu bildet, ändert der Neu-Aufbau an ihnen nur, was dort auch «Tag neu aggregieren» ändern "
                   "würde.")
SATZ_DANACH_HA = ("Danach verhält sich das Feld, als wäre der neue Sensor von Anfang an zugeordnet: Was Home Assistant für ihn "
                  "führt, übernimmt eedc, für die Zeit davor zeigt das Feld «—».")
SATZ_DANACH_ANDERE = ("Danach verhält sich das Feld, als wäre die neue Quelle von Anfang an zugeordnet: eedc zählt ab ihrem "
                      "ersten Wert, für die Zeit davor zeigt das Feld «—».")
SATZ_MONAT = "Für {monate} ist ein Monatswert gespeichert. Er bleibt, wie er ist."
SATZ_MONATE = "Für {monate} sind Monatswerte gespeichert. Sie bleiben, wie sie sind."
SATZ_MONATE_WEG_HA = ("Soll ein Monat zum neuen Sensor passen, ändere den Wert unter Einstellungen → «Daten» → «Monatsdaten» von "
                      "Hand oder hole ihn dort mit «Aus HA laden». Führt Home Assistant den neuen Sensor nur für einen Teil des "
                      "Monats, schlägt «Aus HA laden» nur diesen Teil vor.")
SATZ_MONATE_WEG = "Soll ein Monat zur neuen Quelle passen, ändere den Wert unter Einstellungen → «Daten» → «Monatsdaten» von Hand."
SATZ_ENDGUELTIG = "Das lässt sich nicht rückgängig machen."


async def gespeicherte_monate(db: AsyncSession, anlage_id: int, von: Optional[datetime], bis: datetime) -> list[tuple[int, int]]:
    """Monate mit gespeichertem Monatswert (Monatsabschluss bzw. Handeingabe: eine ``Monatsdaten``-Zeile, dieselbe Weiche wie
    ``verwerfen_vor_quellbeginn.abschluss_monate``) vom Monat des ersten eigenen Werts bis zum Monat der Änderung. Benannte
    Grenze: eedc sieht den Monat, nicht ob er dieses Feld trägt."""
    from backend.services.verwerfen_vor_quellbeginn import abschluss_monate

    unten = (von.year, von.month) if von is not None else (0, 0)
    return sorted(m for m in await abschluss_monate(db, anlage_id) if unten <= m <= (bis.year, bis.month))


async def angaben(db: AsyncSession, anlage_id: int, nachher: Optional[dict], erster_wert: Optional[datetime],
                  jetzt: datetime) -> dict[str, Any]:
    """Was «Daten vor der Änderung löschen» tut, für den Dialog (``abfrage.antwort`` → ``loeschen``): Sätze und die Monate
    mit gespeichertem Monatswert (``YYYY-MM``). Der Client zeigt nur."""
    from backend.services.verwerfen_vor_quellbeginn import _monate_text

    mit_ha = isinstance(nachher, dict) and nachher.get("art") == "ha"
    saetze = [SATZ_NUR_DIESES, SATZ_DANACH_HA if mit_ha else SATZ_DANACH_ANDERE]
    monate = await gespeicherte_monate(db, anlage_id, erster_wert, jetzt)
    if monate:
        saetze.append((SATZ_MONAT if len(monate) == 1 else SATZ_MONATE).format(monate=_monate_text(monate)))
        saetze.append(SATZ_MONATE_WEG_HA if mit_ha else SATZ_MONATE_WEG)
    saetze.append(SATZ_ENDGUELTIG)
    return {"saetze": saetze, "monate": [f"{j}-{m:02d}" for j, m in monate]}


# ── Lauf: Nachfüllen, abgeleitete Kanäle, Tage (``korrektur_lauf``) ────────────────────────────────────────────────────


def nachlauf_auftrag(g: Geloescht, *, mit_ha: bool, jetzt: datetime) -> dict[str, Any]:
    """Der Nachlauf im Zustand des Laufs (``korrektur_lauf``: ``fuellen``) — wiederholbar, bis er gelingt."""
    return {"art": ART, "key": g.key, "kanal_id": g.kanal_id, "ha": bool(mit_ha and g.kanal_id is not None),
            "familien": None if g.abgeleitet_familien is None else sorted(g.abgeleitet_familien),
            "abgeleitet_verworfen": g.abgeleitet_verworfen, "jetzt": jetzt.isoformat(), "erledigt": False}


def ist_nachlauf(f: Any) -> bool:
    return isinstance(f, dict) and f.get("art") == ART


async def _ist_nachgefuellt(sitzungen, kanal_id: int, anlage_id: int, key: str) -> bool:
    """Trägt der Kanal die Nachfüll-Marke der Entity, die das Feld heute zugeordnet hat?"""
    from backend.models.anlage import Anlage
    from backend.models.kanal import KanalNachfuellung
    from backend.services.kanal import schreiber as sch

    async with sitzungen() as db:
        anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
        eid = (await sch._kontext(db, anlage, datetime.now().replace(minute=0, second=0, microsecond=0))).counter_map.get(key)
        if eid is None:
            return True                       # keine HA-Entity mehr — nichts nachzufüllen
        return (await db.execute(select(KanalNachfuellung.statistic_id).where(
            KanalNachfuellung.kanal_id == kanal_id))).scalar_one_or_none() == eid


async def nachlauf(sitzungen, anlage_id: int, f: dict, *, ha_svc=None) -> dict[str, int]:
    """Den Nachlauf ausführen: mit Home Assistant die Geschichte des neuen Sensors nachfüllen (``nachfuellen_spiegel``, nur
    Kanäle ohne Marke) — ist Home Assistant nicht erreichbar oder bleibt der Kanal ohne Marke, wirft er (der Lauf bleibt
    offen, ``korrektur_lauf`` versucht es stündlich); danach die abgeleiteten Kanäle neu schreiben. Returns: die Mengen."""
    from backend.services.kanal.korrektur import KanalKorrektur, schreibe_abgeleitete_nach
    from backend.services.kanal.nachfuellen import nachfuellen_spiegel

    n: dict[str, int] = {"nachgefuellt": 0, "abgeleitet_neu": 0}
    if f.get("ha") and not await _ist_nachgefuellt(sitzungen, int(f["kanal_id"]), anlage_id, f["key"]):
        from backend.services.ha_statistics_service import get_ha_statistics_service
        from backend.services.zuordnung_wechsel.korrektur import KorrekturNichtStartbar, SATZ_NICHT_ERREICHBAR

        svc = ha_svc or get_ha_statistics_service()
        if not svc.is_available:
            raise KorrekturNichtStartbar(SATZ_NICHT_ERREICHBAR)
        erg = await nachfuellen_spiegel(sitzungen, anlage_id, jetzt=datetime.now(), ha_svc=svc, nur_vorhandene=True)
        n["nachgefuellt"] = erg.zeilen
        if not await _ist_nachgefuellt(sitzungen, int(f["kanal_id"]), anlage_id, f["key"]):
            raise KorrekturNichtStartbar(SATZ_NICHT_ERREICHBAR)
    kk = KanalKorrektur(f["key"], kanal_id=f.get("kanal_id"),
                        abgeleitet_familien=None if f.get("familien") is None else frozenset(f["familien"]),
                        abgeleitet_verworfen=int(f.get("abgeleitet_verworfen") or 0))
    n["abgeleitet_neu"] = await schreibe_abgeleitete_nach(sitzungen, anlage_id, kk, datetime.now()) or 0
    return n


async def lauf_anlegen(db: AsyncSession, anlage_id: int, g: Geloescht, *, mit_ha: bool, jetzt: datetime) -> str:
    """Den Lauf (``korrektur_lauf``, Art ``loeschen``) in der Transaktion des Löschens anlegen; nach dem Commit startet ihn
    ``korrektur_lauf.starten``. Returns: die Kennung des Laufs."""
    import uuid

    from backend.services.zuordnung_wechsel import korrektur_lauf

    lauf = uuid.uuid4().hex[:12]
    await korrektur_lauf.anlegen(db, lauf, anlage_id, g.key, g.tage, fuellen=nachlauf_auftrag(g, mit_ha=mit_ha, jetzt=jetzt),
                                 art=ART)
    return lauf
