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
aus der Tageszeile, dort stimmte «zu hoch / fehlt» nicht). Ein Befund entsteht nur, wenn an mindestens einem Rand-Tag (Tag des
ersten Sprungs, Tag des letzten Rückgangs) die Gruppe des Felds nicht aus den Kanälen kommt
(``kanal_stunden.kanal_schluessel_des_tages``, dieselbe Wahl wie ``tages_eingaenge``). Sind beide Rand-Tage Kanal-Tage für das
Feld, schweigt die Prüfung.

**Zwei Lagen, ein Code:**

* **heilbar** (WARNING, Aktion «Tage neu aufbauen» = ``reaggregate_range`` über ``Tag des Sprungs … Tag des Rückgangs``,
  höchstens ``REAGGREGATE_RANGE_MAX_DAYS`` Tage ab dem Sprung, höchstens bis gestern): Home Assistant ist erreichbar, das
  Feld hat einen Spiegel, und die Stände **außerhalb** des Abschnitts (die Zeile vor dem ersten Sprung, die Zeile nach dem
  letzten Rückgang) stimmen mit ihm überein — ``summe + offset`` der zum Zeitpunkt gültigen Quelle. ⚑ Enger als der
  Auftrag: die gültige Quelle muss die **heute zugeordnete** Entität sein und ihr ``offset`` 0 — denn der Lauf holt die
  Stände mit der heutigen Zuordnung ohne Versatz neu (``writer.snapshot_anlage``); stünde dort eine ältere Entität oder ein
  Versatz, entstünde der Sprung nur an anderer Stelle (gemessen an ``inv:2:ladung_kwh``, Bericht N803-HANDGRIFF).
  Ein Abschnitt über 31 Tage braucht mehrere Klicks: nach dem ersten Lauf nennt der Befund den Rest.
* **sonst** (INFO, Auskunft «Was gilt», kein Knopf, der etwas schreibt): ohne Home Assistant, Stände außerhalb passen
  nicht, oder der Abschnitt endet heute.

Schwesterdateien: ``ruecksprung.py``, ``ha_sprung.py``, ``ha_rueckgang.py``; Proben ``tests/test_daten_checker_zaehler_versatz.py``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, text

from backend.core.berechnungen.zaehler_versatz import (
    SPIEGEL_TOLERANZ_KWH, VersatzLauf, finde_versatz_laeufe, stand_passt_zum_spiegel,
)
from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import Aktion, CheckErgebnis, CheckKategorie, CheckSeverity

#: Lage des Befunds (``werte.lage``) und der Grund, warum es keinen Knopf gibt.
LAGE_HEILBAR = "heilbar"
GRUND_OHNE_HA = "ohne_home_assistant"
GRUND_STAENDE_PASSEN_NICHT = "staende_passen_nicht"
GRUND_ENDET_HEUTE = "endet_heute"

_SQL_SCHLUESSEL = "SELECT DISTINCT sensor_key FROM sensor_snapshots WHERE anlage_id = :a AND quelle = :q"
_SQL_REIHE = ("SELECT zeitpunkt, wert_kwh FROM sensor_snapshots WHERE anlage_id = :a AND sensor_key = :k AND quelle = :q "
              "ORDER BY zeitpunkt")

_SATZ_OHNE_KNOPF = {
    GRUND_OHNE_HA: (
        "Ohne Verbindung zu Home Assistant kann eedc die Zählerstände dieses Abschnitts nicht neu holen; die Tageswerte "
        "bleiben, wie sie sind."),
    GRUND_STAENDE_PASSEN_NICHT: (
        "Die Stände vor oder nach dem Abschnitt passen nicht zu dem, was Home Assistant für den heute zugeordneten Sensor "
        "führt — neu geholt, entstünde der Versatz nur an anderer Stelle. eedc stellt diese Tageswerte deshalb nicht selbst "
        "richtig; sie bleiben, wie sie sind."),
    GRUND_ENDET_HEUTE: (
        "Der Abschnitt endet heute; neu aufbauen lässt sich ein Tag erst, wenn er vorbei ist. Ab morgen steht hier der Knopf "
        "„Tage neu aufbauen“."),
}


def _datum(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _tage_text(tage: list[date]) -> str:
    """``[a]`` → «a»; ``[a, b, c]`` → «a, b und c»."""
    teile = [_datum(d) for d in tage]
    return teile[0] if len(teile) == 1 else f"{', '.join(teile[:-1])} und {teile[-1]}"


def aktions_bereich(lauf: VersatzLauf, heute: date) -> tuple[date, date]:
    """Der Bereich des Knopfs: vom Tag des Sprungs bis zum Tag des Rückgangs, höchstens ``REAGGREGATE_RANGE_MAX_DAYS``
    Tage und höchstens bis gestern (der laufende Tag lässt sich nicht neu aufbauen, ``_plan_reaggregate_range``)."""
    from backend.services.repair_orchestrator import REAGGREGATE_RANGE_MAX_DAYS

    von = lauf.beginn.tag
    return von, min(lauf.ende.tag, von + timedelta(days=REAGGREGATE_RANGE_MAX_DAYS - 1), heute - timedelta(days=1))


def _texte(name: str, lauf: VersatzLauf, aktion: Optional[Aktion], grund: str) -> tuple[str, str]:
    """Meldung und Details in Anwender-Sprache (keine Mechanik-Wörter, kein Menüweg — der Knopf ist der Weg)."""
    von, bis = lauf.rand_tage
    versatz = fmt_zahl(lauf.versatz_kwh, 1)
    meldung = (f"{name}: Zählerstände vom {_datum(von)} bis {_datum(bis)} um {versatz} kWh versetzt — "
               "Tageswerte an den Rändern falsch")
    details = (
        f"Vom {_datum(von)} bis {_datum(bis)} liegen die gespeicherten Zählerstände dieses Felds um {versatz} kWh neben "
        "denen davor und danach — so sieht es aus, wenn eine Zeit lang die Stände eines anderen Sensors gespeichert wurden, "
        "etwa nach einem Wechsel der Zuordnung. eedc bildet einen Tageswert aus zwei Zählerständen: am "
        f"{_tage_text(lauf.tage_zu_hoch)} ist er deshalb zu hoch, am {_tage_text(lauf.tage_ohne_wert)} fehlt er "
        "(„Zähler zurückgesprungen“). Gespeicherte Monatswerte ändert das nicht. "
    )
    if aktion is None:
        return meldung, details + _SATZ_OHNE_KNOPF[grund]
    from backend.services.repair_orchestrator import REAGGREGATE_RANGE_MAX_DAYS

    a, b = (date.fromisoformat(aktion.params[k]) for k in ("von", "bis"))
    details += (
        "Die Stände vor und nach dem Abschnitt stimmen mit Home Assistant überein. „Tage neu aufbauen“ holt die "
        f"Zählerstände vom {_datum(a)} bis {_datum(b)} neu aus Home Assistant und baut diese Tage neu auf (höchstens "
        f"{REAGGREGATE_RANGE_MAX_DAYS} Tage je Lauf)."
    )
    if b < bis:
        details += f" Danach nennt dieser Befund den Rest bis {_datum(bis)} — dann noch einmal klicken."
    return meldung, details


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
        """Je versetztem Abschnitt mit Wirkung ein Befund — mit «Tage neu aufbauen», wo der Lauf ihn heilt.

        Args:
            jetzt: Uhr der Prüfung (nur «bis gestern» des Knopfs); eine Naht für die Proben (keine Prozessuhr im Rumpf, N-167).
        """
        invs = await self._versatz_geraete(anlage.id)
        funde = await self._versatz_funde(anlage.id, invs)
        if not funde:
            return []
        from backend.services.ha_statistics_service import get_ha_statistics_service
        from backend.services.snapshot.writer import _build_counter_map, _stillgelegte_inv_ids

        heute = (jetzt or datetime.now()).date()
        ha_da = get_ha_statistics_service().is_available
        zuordnung = _build_counter_map(anlage, await _stillgelegte_inv_ids(self.db, anlage.id)) if ha_da else {}
        out: list[CheckErgebnis] = []
        for key, lauf in funde:
            if not await self._versatz_wirkt(anlage.id, key, lauf):
                continue
            aktion, grund = await self._versatz_lage(anlage.id, key, lauf, heute, zuordnung.get(key) if ha_da else None,
                                                     ha_da)
            out.append(self._versatz_befund(_feld_name(invs, key), key, lauf, aktion, grund))
        return out

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
        """Die Standreihe eines Schlüssels (nur HA-Stände), aufsteigend. Roh gelesen und mit ``fromisoformat`` gewandelt —
        halb so lang wie die ORM-Spalte (gemessen 0,22 statt 0,42 s über die Produktiv-Sicherung)."""
        from backend.services.snapshot.source import SnapshotSource

        return [(datetime.fromisoformat(z), w) for z, w in (await self.db.execute(text(_SQL_REIHE), {
            "a": anlage_id, "k": key, "q": SnapshotSource.HA_STATISTICS})).all()]

    async def _versatz_wirkt(self, anlage_id: int, key: str, lauf: VersatzLauf) -> bool:
        """Rechnet der Tageswert des Felds an mindestens einem Rand-Tag über die Standreihe (Gruppe nicht ``kanal``)?"""
        from backend.services.energie_profil.kanal_stunden import kanal_schluessel_des_tages

        for tag in sorted(set(lauf.rand_tage)):
            if key not in await kanal_schluessel_des_tages(self.db, anlage_id, tag):
                return True
        return False

    async def _versatz_lage(self, anlage_id: int, key: str, lauf: VersatzLauf, heute: date, entitaet: Optional[str],
                            ha_da: bool) -> tuple[Optional[Aktion], str]:
        """Die Aktion der heilbaren Lage oder der Grund, warum es keine gibt."""
        if not ha_da:
            return None, GRUND_OHNE_HA
        if entitaet is None or not await self._raender_passen(anlage_id, key, lauf, entitaet):
            return None, GRUND_STAENDE_PASSEN_NICHT
        von, bis = aktions_bereich(lauf, heute)
        if bis < von:
            return None, GRUND_ENDET_HEUTE
        return Aktion("reaggregate_range", {"von": von.isoformat(), "bis": bis.isoformat()}), LAGE_HEILBAR

    async def _raender_passen(self, anlage_id: int, key: str, lauf: VersatzLauf, entitaet: str) -> bool:
        """Stimmen die Stände außerhalb des Abschnitts mit dem Spiegel der heute zugeordneten Entität überein?"""
        from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle

        quellen = (await self.db.execute(
            select(KanalQuelle.kanal_id, KanalQuelle.gueltig_ab, KanalQuelle.statistic_id, KanalQuelle.offset)
            .join(Kanal, Kanal.id == KanalQuelle.kanal_id).where(
                Kanal.anlage_id == anlage_id, Kanal.key == key, Kanal.art == ART_SUM,
                KanalQuelle.familie == FAMILIE_SPIEGEL,
            ).order_by(KanalQuelle.gueltig_ab))).all()
        raender = ((lauf.beginn.von, lauf.beginn.stand_vorher), (lauf.ende.bis, lauf.ende.stand_nachher))
        for zeitpunkt, stand in raender:
            if not await self._rand_passt(quellen, zeitpunkt, stand, entitaet):
                return False
        return True

    async def _rand_passt(self, quellen, zeitpunkt: datetime, stand: float, entitaet: str) -> bool:
        """Ein Stand zur vollen Stunde ``zeitpunkt`` gegen die Spiegelzeile der Stunde davor (HA: ``start_ts`` trägt den
        Stand am Ende der Stunde) der dann gültigen Quelle."""
        from backend.models.kanal import FAMILIE_SPIEGEL, KanalStatistik

        if zeitpunkt.minute or zeitpunkt.second:
            return False
        start_ts = int(zeitpunkt.timestamp()) - 3600
        gueltig = [q for q in quellen if q.gueltig_ab <= start_ts]
        if not gueltig or gueltig[-1].statistic_id != entitaet or abs(gueltig[-1].offset) > SPIEGEL_TOLERANZ_KWH:
            return False
        q = gueltig[-1]
        summe = (await self.db.execute(select(KanalStatistik.sum).where(
            KanalStatistik.kanal_id == q.kanal_id, KanalStatistik.start_ts == start_ts,
            KanalStatistik.familie == FAMILIE_SPIEGEL,
        ))).scalar_one_or_none()
        return stand_passt_zum_spiegel(stand, summe, q.offset)

    async def _versatz_geraete(self, anlage_id: int) -> dict:
        """Die Geräte der Anlage je Id (Text) — für Namen und die Frage, welches Feld die Tagesansicht zeigt."""
        from backend.models.investition import Investition

        return {str(i.id): i for i in (await self.db.execute(
            select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all()}

    def _versatz_befund(self, name: str, key: str, lauf: VersatzLauf, aktion: Optional[Aktion],
                        grund: str) -> CheckErgebnis:
        meldung, details = _texte(name, lauf, aktion, grund)
        return CheckErgebnis(
            kategorie=CheckKategorie.ZAEHLER_VERSATZ.value,
            schwere=CheckSeverity.WARNING if aktion is not None else CheckSeverity.INFO,
            meldung=meldung,
            details=details,
            action=aktion,
            code="zaehler_versatz",
            # E1 (Diagnose-Paket): die Zahlen der Meldung strukturiert, ohne neue Rechnung.
            werte={
                "schluessel": key, "lage": grund, "versatz_kwh": round(lauf.versatz_kwh, 3),
                "sprung": lauf.beginn.bis.isoformat(timespec="minutes"),
                "rueckgang": lauf.ende.bis.isoformat(timespec="minutes"),
                "tage_zu_hoch": [d.isoformat() for d in lauf.tage_zu_hoch],
                "tage_ohne_wert": [d.isoformat() for d in lauf.tage_ohne_wert],
            },
        )


__all__ = ["GRUND_ENDET_HEUTE", "GRUND_OHNE_HA", "GRUND_STAENDE_PASSEN_NICHT", "LAGE_HEILBAR", "ZaehlerVersatzChecks",
           "aktions_bereich", "in_tagesansicht"]
