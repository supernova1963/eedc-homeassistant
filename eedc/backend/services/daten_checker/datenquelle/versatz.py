"""Daten-Checker — Zählerstände: versetzter Abschnitt in eedcs eigener Standreihe (Verdacht N-803, Go Gernot 16.11.2026).

**Warum es das gibt.** eedc schreibt je Stunde den Stand jedes zugeordneten Zählers in die Standreihe
(``sensor_snapshots``) — mit der Entität, die **heute** zugeordnet ist (``snapshot/writer.py``); eine geänderte Zuordnung
ändert nur ``sensor_mapping`` (``api/routes/datenquellen.py``), die alten Zeilen bleiben. Der HA-Spiegel fängt einen
Wechsel über ``kanal_quelle.gueltig_ab`` + ``offset`` ab, die Standreihe nicht: läuft ein Abschnitt mit den Ständen eines
anderen Sensors, springt sie um +X und fällt später um ≈ −X zurück (an der Produktiv-Anlage die Wallbox, 1.7.–10.8.2026).
An den Rand-Tagen ist der Tageswert, den eedc aus zwei Ständen bildet, falsch. Kein anderer Befund deckt das:
``zaehler_ruecksprung`` liest nur MQTT-Reihen, ``ha_zaehlersprung``/``ha_zaehler_rueckgang`` den Spiegel,
``zaehlerstand_reihe_bruch`` nur Gas-, Wasser- und Ölzähler, die Drift 90 Tage auf der Tageszeile.

**Erkennung** über die ganze Standreihe je Schlüssel, nur Zeilen mit ``quelle = ha_statistics`` (MQTT-Reihen bleiben bei
``zaehler_ruecksprung``) — die Regel steht im Layer (``core/berechnungen/zaehler_versatz.py``). Gelesen wird je Schlüssel
eine Reihe (``_reihe``), nie die ganze Tabelle auf einmal.

**Nur bei Wirkung:** geprüft werden nur Felder, deren Tageswert die Tagesansicht aus der Standreihe zeigt
(``in_tagesansicht`` = ``TAGESDETAIL_AUSGABE``, Entscheid Master 16.11.2026 — «Ladung gesamt» der Wallbox liest die Tagesansicht
aus der Tageszeile, dort stimmte «zu hoch / fehlt» nicht). Je Sprung und je Rückgang des Abschnitts (auch die inneren Schritte
eines zerteilten Laufs, Bauplan «Zu §14» Nr. 91 b) wird geprüft, ob er den Tageswert eines Tages trifft: der Tag ist der, dessen
Tagesfenster ``(a, b]`` den späteren Stand des Schritts enthält (``kanal/feld_leser.tagesfenster_am_tag`` — ein Bestandstag
rückwärts beginnt um 23:00 des Vortags, ein Kanal-Tag um Mitternacht; liegt der frühere Stand hinter einer Datenlücke vor dem
Fenster, rückt der Rand der Tagesansicht auf ihn zurück — der Schritt gehört trotzdem diesem Tag), und an diesem Tag kommt die
Gruppe des Felds nicht aus den Kanälen (``kanal_stunden.kanal_schluessel_des_tages``) und trägt der eigene Kanal des Felds den
Tag nicht (Sensorwechsel B-5 «Kanal vor Reihe», ``kanal/feld_leser.feld_aus_kanal_am_tag``). Ein Schritt an einer verzeichneten
Fortsetzung oder am Rand einer Lücke ist ohne Wirkung — dort bilden die Leser keine Differenz (Bauplan §13 Nr. 71). **Kein
Saldo** (Bauplan «Zu §14» Nr. 100): ein Tag mit einem Rückgang im Fenster hat in der Tagesansicht keinen Wert («Zähler
zurückgesprungen»), auch wenn im selben Fenster ein Sprung liegt; ein Tag nur mit Sprüngen ist zu hoch. Ein Befund entsteht,
wenn mindestens ein Schritt wirkt; Meldung, Details und ``werte`` nennen die Tage der wirkenden Schritte.

**Ein Handgriff, «Grund nachtragen»** (Bauplan «Zu §14» Nr. 95 (2), Nr. 98; WARNING): ein Sprung in die Datenquellen
(``stueck=<schlüssel>~<sprung>~<rückgang>``), dort derselbe Dialog wie beim Wechsel der Quelle, nur mit «Korrektur» über das
Stück ``[Sprung, Rückgang)`` (``services/zuordnung_wechsel/stueck.py``, Vorschau = Lauf). ``werte.lage`` sagt, was die
Korrektur tun wird — mit derselben Prüfung wie der Dienst (``stueck.ist_fuellbar``):

* ``fuellbar`` — Home Assistant erreichbar, beide Rand-Stände sind HAs Rohsumme der Quelle davor und danach: die Stände des
  Stücks werden verworfen und aus dieser Quelle neu gelesen. Führt Home Assistant die Quelle erst ab einer Zeit im Stück, nennt
  der Satz diese Zeit und was für die Zeit davor gilt (``_SATZ_FUELLBAR_AB``; dieselbe Vorschau wie der Dialog,
  ``korrektur.lage`` — U2 Lauf b).
* ``ohne_home_assistant`` · ``staende_passen_nicht`` (die Rand-Stände passen zu keiner Summe, die Home Assistant für die Quelle
  führt) — die Stände werden verworfen und nicht neu gelesen; da davor und danach dieselbe Quelle gilt, rechnen die Leser über
  die leere Zeit wie über jede Zählerlücke (Sensorwechsel U1, ``zeitpunkt.ohne_hoehenwechsel``): die Menge steht am Tag, an dem
  das Stück endet. Liegt zwischen den Ständen davor und danach ein eingetragener Zählertausch, bilden die Leser über die leere
  Zeit keine Differenz — der Befund fragt dieselbe Regel wie die Vorschau (``_versatz_tausch``, Korrekturrunde U1-K S2) und
  sagt es (``_SATZ_LAGE_TAUSCH``).
* ``verschiedene_quellen`` — vor und nach dem Abschnitt gelten verschiedene Quellen; die Korrektur ist gesperrt: eine Auskunft
  ohne Knopf (INFO, Bauplan «Zu §14» Nr. 104).
* ``ha_nicht_erreichbar`` — Home Assistant ist eingerichtet, aber gerade nicht erreichbar (oder sein Abruf scheitert): die
  Korrektur startet in diesem Augenblick nicht — eine Auskunft ohne Knopf (INFO, Nr. 104); beim nächsten Lauf mit erreichbarem
  Home Assistant steht wieder der Handgriff.

Home Assistant wird nur für einen gefundenen Abschnitt mit Wirkung gefragt, nie für die OK-Zeile.

Schwesterdateien: ``ruecksprung.py``, ``ha_sprung.py``, ``ha_rueckgang.py``; Proben ``tests/test_daten_checker_zaehler_versatz.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, text

from backend.core.berechnungen.zaehler_versatz import VersatzLauf, finde_versatz_laeufe
from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

logger = logging.getLogger(__name__)

#: Lage des Befunds (``werte.lage``): was «Grund nachtragen → Korrektur» tun wird.
LAGE_FUELLBAR = "fuellbar"
GRUND_OHNE_HA = "ohne_home_assistant"
GRUND_STAENDE_PASSEN_NICHT = "staende_passen_nicht"
GRUND_VERSCHIEDENE_QUELLEN = "verschiedene_quellen"
GRUND_HA_NICHT_ERREICHBAR = "ha_nicht_erreichbar"
#: Lagen ohne wirksamen Handgriff in diesem Augenblick — Auskunft (INFO, ohne Sprung), Bauplan «Zu §14» Nr. 104.
LAGEN_OHNE_HANDGRIFF = frozenset({GRUND_VERSCHIEDENE_QUELLEN, GRUND_HA_NICHT_ERREICHBAR})

_SQL_SCHLUESSEL = "SELECT DISTINCT sensor_key FROM sensor_snapshots WHERE anlage_id = :a AND quelle = :q"
_SQL_REIHE = ("SELECT zeitpunkt, wert_kwh FROM sensor_snapshots WHERE anlage_id = :a AND sensor_key = :k AND quelle = :q "
              "ORDER BY zeitpunkt")

#: Was «Grund nachtragen» je Lage tut (Wortlaute Sitzung 4b-1; gehen vor dem Commit an Gernot).
_SATZ_LAGE = {
    LAGE_FUELLBAR: (
        "Die Stände davor und danach sind die, die Home Assistant für {quelle} führt. „Grund nachtragen“ verwirft die "
        "Zählerstände des Abschnitts; eedc liest sie danach aus Home Assistant neu, auf derselben Höhe wie davor und danach."),
    GRUND_OHNE_HA: (
        "Ohne Verbindung zu Home Assistant kann eedc die Zählerstände dieses Abschnitts nicht neu holen. „Grund nachtragen“ "
        "verwirft sie; da davor und danach dieselbe Quelle gilt, rechnet eedc über die leere Zeit wie über jede Zählerlücke: "
        "die Menge des Abschnitts steht an dem Tag, an dem er endet, die Tage davor zeigen für diese Zeit keinen Wert."),
    GRUND_STAENDE_PASSEN_NICHT: (
        "Die Stände davor oder danach passen zu keiner Summe, die Home Assistant für {quelle} führt — neu holen lassen sich "
        "die Zählerstände des Abschnitts nicht. „Grund nachtragen“ verwirft sie; da davor und danach dieselbe Quelle gilt, "
        "rechnet eedc über die leere Zeit wie über jede Zählerlücke: die Menge des Abschnitts steht an dem Tag, an dem er "
        "endet, die Tage davor zeigen für diese Zeit keinen Wert."),
    GRUND_VERSCHIEDENE_QUELLEN: (
        "Vor und nach dem Abschnitt gelten verschiedene Quellen ({quelle} und {quelle_nach}) — eedc weiß nicht, welche hier "
        "die richtige ist, und korrigiert ihn deshalb nicht; die Tageswerte bleiben, wie sie sind."),
    GRUND_HA_NICHT_ERREICHBAR: (
        "Home Assistant ist gerade nicht erreichbar — ob eedc die Zählerstände dieses Abschnitts neu holen kann, lässt sich "
        "jetzt nicht prüfen, und eine Korrektur startet erst, wenn eedc die Langzeitstatistik wieder lesen kann. Dann steht "
        "hier der Knopf „Grund nachtragen“."),
}
#: ``fuellbar``, wenn Home Assistant die Quelle erst ab einer Zeit im Abschnitt führt (U2 Lauf b; dieselbe Zeit wie
#: ``korrektur.SATZ_STAENDE_AB`` in der Vorschau des Dialogs).
_SATZ_FUELLBAR_AB = (
    "Die Stände davor und danach sind die, die Home Assistant für {quelle} führt. „Grund nachtragen“ verwirft die "
    "Zählerstände des Abschnitts; Home Assistant führt {quelle} aber erst ab {ab} Uhr — von dort an liest eedc sie neu, auf "
    "derselben Höhe wie davor und danach. ")
_SATZ_FUELLBAR_AB_LUECKE = ("Über die Zeit davor rechnet eedc wie über jede Zählerlücke: ihre Menge steht an dem Tag, an dem "
                            "sie endet.")
_SATZ_FUELLBAR_AB_KEINE = ("Über die Zeit davor bildet eedc keine Differenz zweier Zählerstände: die Tage darin zeigen keinen "
                           "Wert, die Tage an ihrem Rand nur ihren Teil.")
#: Dieselben Lagen, wenn zwischen den Ständen davor und danach ein Zählertausch eingetragen ist (Korrekturrunde U1-K S2: der
#: Befund fragt dieselbe Regel wie die Leser, ``zeitpunkt.ohne_hoehenwechsel`` über die Vorschau der Korrektur).
_SATZ_TAUSCH = ("„Grund nachtragen“ verwirft sie; da zwischen den Ständen davor und danach ein Zählertausch eingetragen ist, "
                "bildet eedc über die leere Zeit keine Differenz zweier Zählerstände: die Tage darin zeigen keinen Wert, die "
                "Tage an ihrem Rand nur ihren Teil.")
_SATZ_LAGE_TAUSCH = {
    GRUND_OHNE_HA: ("Ohne Verbindung zu Home Assistant kann eedc die Zählerstände dieses Abschnitts nicht neu holen. "
                    + _SATZ_TAUSCH),
    GRUND_STAENDE_PASSEN_NICHT: (
        "Die Stände davor oder danach passen zu keiner Summe, die Home Assistant für {quelle} führt — neu holen lassen sich "
        "die Zählerstände des Abschnitts nicht. " + _SATZ_TAUSCH),
}


def _datum(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _tage_text(tage: list[date]) -> str:
    """``[a]`` → «a»; ``[a, b, c]`` → «a, b und c»."""
    teile = [_datum(d) for d in tage]
    return teile[0] if len(teile) == 1 else f"{', '.join(teile[:-1])} und {teile[-1]}"


def _texte(name: str, lauf: VersatzLauf, wirkung: "Wirkung", lage: str, quellen: tuple[str, str],
           tausch: bool = False, fuellbar_ab: Optional[tuple[datetime, bool]] = None) -> tuple[str, str]:
    """Meldung und Details in Anwender-Sprache (keine Mechanik-Wörter, kein Menüweg — der Handgriff ist der Weg); genannt
    werden nur die Tage der Schritte mit Wirkung (Bauplan «Zu §14» Nr. 91 b)."""
    # Die Tage des ersten und des letzten versetzten Stands (Bauplan «Zu §14» Nr. 108, S11: ein Sprung mit der Zeile 00:00
    # gehört zum Abschnitt dieses Tages, nicht zum Vortag); welcher Tageswert falsch ist, sagen die Details.
    von, bis = lauf.beginn.bis.date(), lauf.ende.von.date()
    versatz = fmt_zahl(lauf.versatz_kwh, 1)
    meldung = (f"{name}: Zählerstände vom {_datum(von)} bis {_datum(bis)} um {versatz} kWh versetzt — "
               "Tageswerte an den Rändern falsch")
    folgen = []
    if wirkung.tage_zu_hoch:
        folgen.append(f"am {_tage_text(wirkung.tage_zu_hoch)} ist er deshalb zu hoch")
    if wirkung.tage_ohne_wert:
        folgen.append(f"am {_tage_text(wirkung.tage_ohne_wert)} fehlt er („Zähler zurückgesprungen“)")
    details = (
        f"Vom {_datum(von)} bis {_datum(bis)} liegen die gespeicherten Zählerstände dieses Felds um {versatz} kWh neben "
        "denen davor und danach — so sieht es aus, wenn eine Zeit lang die Stände eines anderen Sensors gespeichert wurden, "
        f"etwa nach einem Wechsel der Zuordnung. eedc bildet einen Tageswert aus zwei Zählerständen: {', '.join(folgen)}. "
        "Gespeicherte Monatswerte ändert das nicht. "
    )
    if lage == LAGE_FUELLBAR and fuellbar_ab is not None:
        ab, wie_luecke = fuellbar_ab
        satz = _SATZ_FUELLBAR_AB.format(quelle=quellen[0], ab=ab.strftime("%d.%m.%Y %H:%M")) + (
            _SATZ_FUELLBAR_AB_LUECKE if wie_luecke else _SATZ_FUELLBAR_AB_KEINE)
        return meldung, details + satz
    satz = _SATZ_LAGE_TAUSCH[lage] if tausch and lage in _SATZ_LAGE_TAUSCH else _SATZ_LAGE[lage]
    return meldung, details + satz.format(quelle=quellen[0], quelle_nach=quellen[1])


def in_tagesansicht(invs: dict, key: str) -> bool:
    """Zeigt eine Sicht den Tageswert dieses Felds aus der Standreihe? Genau die Felder der Tagesansicht
    (``snapshot/aggregator.TAGESDETAIL_AUSGABE``: Wärmepumpen-Felder, Speicher-Netzladung, PV-/Netz-Ladung von Wallbox und
    E-Auto, Netzbezug zum eigenen Tarif) — Entscheid Master 16.11.2026: ein Feld, dessen Tageswert die Sichten aus der
    Tageszeile oder den Kanälen nehmen (etwa «Ladung gesamt» der Wallbox, die Bilanz-Zähler), bekommt keinen Befund, denn
    dort stimmt der Satz «zu hoch / fehlt» nicht (gemessen an ``tag-detail`` der Produktiv-Sicherung)."""
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE

    teile = key.split(":")
    if len(teile) != 3 or teile[0] != "inv" or teile[1] not in invs:
        return False
    return (invs[teile[1]].typ, teile[2]) in TAGESDETAIL_AUSGABE


def _feld_name(invs: dict, key: str) -> str:
    """``inv:2:ladung_pv_kwh`` → «<Gerät> – Ladung PV» (Namen der Oberfläche)."""
    from backend.core.field_definitions import feld_label_fuer_investition

    _, inv_id, feld = key.split(":", 2)
    inv = invs[inv_id]
    return f"{inv.bezeichnung} – {feld_label_fuer_investition(inv, feld)}"


class ZaehlerVersatzChecks:
    """Prüfung: versetzter Abschnitt in der Standreihe eines Zählerfelds (Sprung um +X, später Rückgang um ≈ −X)."""

    async def _check_zaehler_versatz(self, anlage: Anlage, jetzt: Optional[datetime] = None) -> list[CheckErgebnis]:
        """Je versetztem Abschnitt mit Wirkung ein Befund mit dem Handgriff «Grund nachtragen» (Sprung in die Datenquellen).

        Args:
            jetzt: bleibt für die Aufrufer (bis Sitzung 4b-1 die Uhr des Knopfs «Tage neu aufbauen»); die Prüfung braucht
                keine Uhr mehr — das Stück endet mit dem Rückgang, auch am laufenden Tag.
        """
        invs = await self._versatz_geraete(anlage.id)
        funde = await self._versatz_funde(anlage.id, invs)
        if not funde:
            return [_versatz_ok()]
        out: list[CheckErgebnis] = []
        for key, lauf in funde:
            wirkung = await self._versatz_wirkt(anlage, key, lauf, invs)
            if not wirkung:
                continue
            lage, quellen = await self._versatz_lage(anlage, key, lauf)
            tausch = lage in _SATZ_LAGE_TAUSCH and await self._versatz_tausch(anlage, key, lauf, quellen)
            ab = await self._versatz_fuellbar_ab(anlage, key, lauf) if lage == LAGE_FUELLBAR else None
            out.append(self._versatz_befund(_feld_name(invs, key), key, lauf, wirkung, lage, quellen, tausch, ab))
        return out or [_versatz_ok()]

    async def _versatz_funde(self, anlage_id: int, invs: dict) -> list[tuple[str, VersatzLauf]]:
        """Je Schlüssel mit HA-Ständen, dessen Tageswert die Tagesansicht aus der Standreihe zeigt
        (``in_tagesansicht``), die versetzten Abschnitte — eine Reihe nach der anderen gelesen (Index
        ``ix_sensor_snapshot_lookup``), nie die ganze Tabelle auf einmal. Gemessen an der Produktiv-Sicherung
        (164 742 Zeilen, 13 Reihen, 3 davon in der Tagesansicht): 0,07 s; alle 13 gelesen: 0,45 s, Spitze 6,8 MB."""
        from backend.services.snapshot.source import SnapshotSource

        keys = (await self.db.execute(text(_SQL_SCHLUESSEL), {
            "a": anlage_id, "q": SnapshotSource.HA_STATISTICS})).scalars().all()
        funde: list[tuple[str, VersatzLauf]] = []
        for key in sorted(k for k in keys if in_tagesansicht(invs, k)):
            funde += [(key, lauf) for lauf in finde_versatz_laeufe(await self._reihe(anlage_id, key))]
        return funde

    async def _reihe(self, anlage_id: int, key: str) -> list[tuple[datetime, float]]:
        return await lade_reihe(self.db, anlage_id, key)

    async def _versatz_wirkt(self, anlage, key: str, lauf: VersatzLauf, invs: dict) -> "Wirkung":
        """Die Schritte des Abschnitts (jeder Sprung, jeder Rückgang — auch innen in einem zerteilten Lauf), deren Tageswert
        die Tagesansicht über die Standreihe bildet, je mit seinem Tag (Bauplan «Zu §14» Nr. 91 b). Ohne Wirkung: ein
        Schritt an einer verzeichneten Fortsetzung oder am Rand einer Lücke (``zaehler_naht.ueber_naht``), ein Schritt, den
        kein Tagesfenster ganz enthält, und ein Tag, den die Tagesansicht aus den Kanälen liest (Gruppe aus den Kanälen oder
        eigener Kanal, Sensorwechsel B-5)."""
        from backend.core.berechnungen.zaehler_naht import ueber_naht
        from backend.services.zuordnung_wechsel.zeitpunkt import fortsetzungs_naehte

        typ = getattr(invs.get(key.split(":")[1]), "typ", None)
        naehte = await fortsetzungs_naehte(self.db, anlage.id, key)
        hoch: set[date] = set()
        ohne: set[date] = set()
        for schritt, tage, rueck in [(s, hoch, False) for s in lauf.spruenge] + [(r, ohne, True) for r in lauf.rueckgaenge]:
            if ueber_naht(schritt.von, schritt.bis, naehte):
                continue
            tag = await self._tag_des_schritts(anlage, typ, key, schritt, rueck)
            if tag is not None:
                tage.add(tag)
        # Kein Saldo (Nr. 100): ein Rückgang im Fenster nimmt dem Tag den Wert, auch neben einem Sprung.
        return Wirkung(sorted(hoch - ohne), sorted(ohne))

    async def _tag_des_schritts(self, anlage, typ: Optional[str], key: str, schritt, rueckgang: bool) -> Optional[date]:
        """Der Tag, dessen Tageswert der Schritt trifft und den die Tagesansicht aus der Reihe bildet — ``None``, wenn der Tag
        aus den Kanälen kommt. In der Regel der Tag, dessen Tagesfenster ``(a, b]`` den späteren Stand enthält (Kalendertag
        oder, im Fenster ab 23:00 des Vortags, der Folgetag; Messblatt 4b-0 h). Liegt der frühere Stand hinter einer
        Datenlücke in einem früheren Fenster, rückt ohne Home Assistant der Rand der Tagesansicht auf ihn zurück (Lückenanker)
        — derselbe Tag; mit Home Assistant heilt sie den Rand dazwischen auf das Niveau außerhalb des Abschnitts, und ein
        Rückgang trifft dann den Tag des früheren Stands (Bauplan «Zu §14» Nr. 100, Probe «Rückgang hinter einer Datenlücke»)."""
        from backend.services.energie_profil.kanal_stunden import kanal_schluessel_des_tages
        from backend.services.kanal.feld_leser import feld_aus_kanal_am_tag

        tag = await self._tag_im_fenster(anlage.id, typ, schritt.bis, links_offen=True)
        if rueckgang and tag is not None:
            vorher = await self._tag_im_fenster(anlage.id, typ, schritt.von, links_offen=False)
            if vorher is not None and vorher != tag and _heilt_raender():
                tag = vorher
        if tag is None or key in await kanal_schluessel_des_tages(self.db, anlage.id, tag):
            return None
        return None if await feld_aus_kanal_am_tag(self.db, anlage, typ, key, tag) else tag

    async def _tag_im_fenster(self, anlage_id: int, typ: Optional[str], t: datetime, *, links_offen: bool) -> Optional[date]:
        """Der Tag, dessen Tagesfenster ``t`` enthält — ``(a, b]`` für den späteren Stand eines Schritts, ``[a, b)`` für den
        früheren."""
        from backend.services.kanal.feld_leser import tagesfenster_am_tag

        for tag in (t.date() - timedelta(days=1), t.date(), t.date() + timedelta(days=1)):
            a, b = await tagesfenster_am_tag(self.db, anlage_id, typ, tag)
            if (a < t <= b) if links_offen else (a <= t < b):
                return tag
        return None

    async def _versatz_lage(self, anlage, key: str, lauf: VersatzLauf) -> tuple[str, tuple[str, str]]:
        """Was «Grund nachtragen → Korrektur» tun wird — dieselbe Prüfung wie der Dienst (``stueck.ist_fuellbar``) — und die
        Quellen davor und danach (Text). Home Assistant eingerichtet, aber nicht erreichbar, oder sein Abruf scheitert ⇒
        ``ha_nicht_erreichbar`` (der Daten-Checker antwortet trotzdem, Bauplan «Zu §14» Nr. 104)."""
        from backend.services.ha_statistics_service import get_ha_statistics_service
        from backend.services.zuordnung_wechsel.korrektur import ha_eingerichtet
        from backend.services.zuordnung_wechsel.nachtrag import quelle_text
        from backend.services.zuordnung_wechsel.stueck import StueckLage, ist_fuellbar, quelle_am_rand
        from backend.services.zuordnung_wechsel.stueck import _gleiche_quelle

        vor = await quelle_am_rand(self.db, anlage, key, lauf.beginn.von)
        nach = await quelle_am_rand(self.db, anlage, key, lauf.ende.bis)
        quellen = (quelle_text(vor), quelle_text(nach))
        if not _gleiche_quelle(vor, nach):
            return GRUND_VERSCHIEDENE_QUELLEN, quellen
        svc = get_ha_statistics_service()
        if not svc.is_available:
            return (GRUND_HA_NICHT_ERREICHBAR if ha_eingerichtet() else GRUND_OHNE_HA), quellen
        a = StueckLage(key, lauf.beginn.bis, lauf.ende.bis, "", quelle=vor).auftrag(anlage.id, lauf.ende.bis)
        try:
            fuellbar = await ist_fuellbar(self.db, a, svc)
        except Exception as e:  # noqa: BLE001 — ein Abruf-Fehler von Home Assistant ist keine Antwort des Befunds
            logger.warning("zaehler_versatz %s: Abruf aus Home Assistant gescheitert: %s: %s", key, type(e).__name__, e)
            return GRUND_HA_NICHT_ERREICHBAR, quellen
        return (LAGE_FUELLBAR if fuellbar else GRUND_STAENDE_PASSEN_NICHT), quellen

    async def _versatz_tausch(self, anlage, key: str, lauf: VersatzLauf, quellen) -> bool:
        """Liegt zwischen den Ständen davor und danach ein Höhenwechsel (Zählertausch), über den die Leser nach der Korrektur
        keine Differenz bilden? Dieselbe Frage wie die Vorschau der Korrektur (``korrektur._wie_zaehlerluecke`` an den Zeilen,
        wie sie danach stehen) — Korrekturrunde U1-K S2."""
        from backend.services.zuordnung_wechsel.korrektur import _wie_zaehlerluecke
        from backend.services.zuordnung_wechsel.stueck import StueckLage, quelle_am_rand

        vor = await quelle_am_rand(self.db, anlage, key, lauf.beginn.von)
        a = StueckLage(key, lauf.beginn.bis, lauf.ende.bis, "", quelle=vor).auftrag(anlage.id, lauf.ende.bis)
        return not await _wie_zaehlerluecke(self.db, a, a.falsch_seit, a.ab, a.ab)

    async def _versatz_fuellbar_ab(self, anlage, key: str, lauf: VersatzLauf) -> Optional[tuple[datetime, bool]]:
        """Führt Home Assistant die Quelle erst ab einer Zeit im Abschnitt? ``(Zeit, wie eine Zählerlücke?)`` aus derselben
        Vorschau wie der Dialog (``korrektur.lage`` am Auftrag über das Stück, ``SATZ_STAENDE_AB``) — sonst ``None``."""
        from backend.services.ha_statistics_service import get_ha_statistics_service
        from backend.services.zuordnung_wechsel import korrektur as kr
        from backend.services.zuordnung_wechsel.stueck import StueckLage, quelle_am_rand

        vor = await quelle_am_rand(self.db, anlage, key, lauf.beginn.von)
        a = StueckLage(key, lauf.beginn.bis, lauf.ende.bis, "", quelle=vor).auftrag(anlage.id, lauf.ende.bis)
        try:
            la = await kr.lage(self.db, a, ha_svc=get_ha_statistics_service())
        except Exception as e:  # noqa: BLE001 — der Befund nennt dann den gewöhnlichen Satz
            logger.warning("zaehler_versatz %s: Vorschau nicht lesbar: %s: %s", key, type(e).__name__, e)
            return None
        if not kr._staende_ab(la):
            return None
        return kr._staende_ab_zeit(la), bool(la.zaehlerluecke)

    async def _versatz_geraete(self, anlage_id: int) -> dict:
        """Die Geräte der Anlage je Id (Text) — für Namen und die Frage, welches Feld die Tagesansicht zeigt."""
        from backend.models.investition import Investition

        return {str(i.id): i for i in (await self.db.execute(
            select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all()}

    def _versatz_befund(self, name: str, key: str, lauf: VersatzLauf, wirkung: "Wirkung", lage: str,
                        quellen: tuple[str, str], tausch: bool = False,
                        fuellbar_ab: Optional[tuple[datetime, bool]] = None) -> CheckErgebnis:
        from backend.services.daten_checker.ziele import stueck_parameter

        meldung, details = _texte(name, lauf, wirkung, lage, quellen, tausch, fuellbar_ab)
        sprung, rueckgang = lauf.beginn.bis.isoformat(timespec="minutes"), lauf.ende.bis.isoformat(timespec="minutes")
        ohne_handgriff = lage in LAGEN_OHNE_HANDGRIFF
        # E1 (Diagnose-Paket): die Zahlen der Meldung strukturiert, ohne neue Rechnung.
        return _versatz_zeile(CheckSeverity.INFO if ohne_handgriff else CheckSeverity.WARNING, meldung, details, {
            "schluessel": key, "lage": lage, "versatz_kwh": round(lauf.versatz_kwh, 3),
            "sprung": sprung, "rueckgang": rueckgang,
            "tage_zu_hoch": [d.isoformat() for d in wirkung.tage_zu_hoch],
            "tage_ohne_wert": [d.isoformat() for d in wirkung.tage_ohne_wert],
        }, stueck=None if ohne_handgriff else stueck_parameter(key, sprung, rueckgang))


def _heilt_raender() -> bool:
    """Heilt die Tagesansicht einen fehlenden Fensterrand aus Home Assistant? (``snapshot/reader.get_snapshot``: nur mit
    erreichbarer Langzeitstatistik.) Kein Abruf — nur die Erreichbarkeit."""
    from backend.services.ha_statistics_service import get_ha_statistics_service

    return bool(get_ha_statistics_service().is_available)


@dataclass
class Wirkung:
    """Die Tage, deren Tageswert ein Schritt des Abschnitts trifft (nur Schritte mit Wirkung, ``_versatz_wirkt``)."""
    tage_zu_hoch: list[date] = field(default_factory=list)
    tage_ohne_wert: list[date] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.tage_zu_hoch or self.tage_ohne_wert)


async def lade_reihe(db, anlage_id: int, key: str) -> list[tuple[datetime, float]]:
    """Die Standreihe eines Schlüssels (nur HA-Stände), aufsteigend — die Reihe der Erkennung (Befund und Routen am Befund,
    ``zuordnung_wechsel/stueck.finde_lauf``). Roh gelesen und mit ``fromisoformat`` gewandelt — halb so lang wie die
    ORM-Spalte (gemessen 0,22 statt 0,42 s über die Produktiv-Sicherung)."""
    from backend.services.snapshot.source import SnapshotSource

    return [(datetime.fromisoformat(z), w) for z, w in (await db.execute(text(_SQL_REIHE), {
        "a": anlage_id, "k": key, "q": SnapshotSource.HA_STATISTICS})).all()]


#: OK-Zeile (N-799 S3, K7 — Entscheid Master 16.11.2026): ohne Fund steht der Befund unter den bestandenen Prüfungen, damit
#: ein Link mit ``befund=zaehler_versatz`` (``DatenCheckerTeile.tsx``) immer eine Zeile mit dem Lösungsweg findet.
OK_MELDUNG = "Kein versetzter Abschnitt in den gespeicherten Zählerständen"
OK_DETAILS = ("eedc prüft die gespeicherten Zählerstände der Felder, deren Tageswert die Tagesansicht aus ihnen bildet, auf "
              "einen Abschnitt, der um einen festen Betrag neben den Ständen davor und danach liegt — etwa nach einem Wechsel "
              "der Zuordnung. Gefunden wurde keiner; es ist nichts zu tun.")


def _versatz_ok() -> CheckErgebnis:
    return _versatz_zeile(CheckSeverity.OK, OK_MELDUNG, OK_DETAILS, {"funde": 0})


def _versatz_zeile(schwere: str, meldung: str, details: str, werte: dict, stueck: Optional[str] = None) -> CheckErgebnis:
    """Die eine Erzeuger-Stelle des Codes (W-1) — Fund (WARNING mit dem Sprung «Grund nachtragen» an das Stück
    ``stueck=<schlüssel>~<sprung>~<rückgang>``; in einer Lage ohne wirksamen Handgriff INFO ohne Sprung) oder OK-Zeile."""
    from backend.services.daten_checker.ziele import ziel_datenquelle_schluessel

    return CheckErgebnis(
        kategorie=CheckKategorie.ZAEHLER_VERSATZ.value,
        schwere=schwere,
        meldung=meldung,
        details=details,
        code="zaehler_versatz",
        werte=werte,
        ziel=ziel_datenquelle_schluessel(werte["schluessel"], stueck=stueck) if stueck else None,
    )


__all__ = ["GRUND_HA_NICHT_ERREICHBAR", "GRUND_OHNE_HA", "GRUND_STAENDE_PASSEN_NICHT", "GRUND_VERSCHIEDENE_QUELLEN", "LAGE_FUELLBAR", "OK_MELDUNG",
           "Wirkung", "ZaehlerVersatzChecks", "in_tagesansicht", "lade_reihe"]
