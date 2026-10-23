"""Daten-Checker — Zählersprung in der HA-Langzeitstatistik (N-586, HA-Bauform E4a-2, Auftrag Punkt 5).

**Warum es das gibt.** Seit E4a-2 rechnet eedc die Bilanz-Gruppe aus dem Spiegel der HA-Statistik wie das
HA-Energie-Dashboard — ohne Deckel und ohne Rücksprung-Verwurf (R-5, HA-Teil). Meldet ein Sensor für kurze Zeit 0
(„nicht verfügbar", Neustart des Wechselrichters) und kehrt dann zu seinem alten Stand zurück, hält HA das für einen
Reset und bucht beim Zurückkehren den ganzen Zählerstand als Zuwachs: ein Phantomsprung in ``sum``. eedc nennt ihn
jetzt in Tag UND Monat — genau wie HA; früher hat der Deckel ihn verschluckt (und mit ihm gelegentlich echte Energie).

**Das Muster** (Bauplan §7 N-586): in ``state`` ein Reset (der Stand fällt auf höchstens ``RESET_ANTEIL`` des
vorigen), danach innerhalb ``RUECKKEHR_STUNDEN`` die Rückkehr auf etwa den alten Stand (mindestens
``RUECKKEHR_ANTEIL``) — und zwar **zwischen zwei benachbarten Zeilen**: die Zeile davor steht noch unten, die Zeile
selbst wieder oben. HAs Phantom entsteht nur, wenn der Stand in EINER Stunde zurückspringt; ein Zähler, der nach dem
Reset hochzählt (ein täglich zurückgesetzter Helfer, ein neuer Zähler nach einem Tausch), erzeugt in ``sum`` keinen
Sprung und ist kein Befund (Nachmessung E4a-2, Punkt 6). Ein **Tageszähler** (PV-Tagesertrag, Utility-Meter „heute")
ist es auch dann nicht, wenn seine erste helle Stunde nach einem schwachen Vortag den Vortagsstand schon fast erreicht:
geht derselbe Sensor an mindestens ``TAGESZAEHLER_MIN_TAGE`` Tagen des Fensters zu Beginn seines Tages auf 0, sind
diese Tagesbeginn-Resets Zyklen (N-764, #436); ein einzelner Tag im Fenster bleibt ununterscheidbar. «Tagesbeginn» ist
die erste Zeile ihres lokalen Kalendertags in der Zeilenfolge — die 00:00-Zeile, oder bei einem nachts abgeschalteten
Wechselrichter (HA schreibt ohne Zustand keine Statistikzeile) die erste Morgenzeile (N-765, #436). Die Phantommenge ist der Zuwachs von ``sum`` über die Strecke abzüglich dessen, was der Zähler
selbst zeigt (``state`` vorher → nachher). Gelesen wird der Spiegel (``kanal_statistik``, Familie ``spiegel``) der
letzten ``FENSTER_TAGE`` — keine HA-Abfrage.

⛔ **Kein Reparatur-Knopf in eedc.** Die Quelle ist HAs Statistik; korrigiert wird dort (Entwicklerwerkzeuge →
Statistik → „Wert anpassen"), und eedc zieht über den nächtlichen Konsistenzlauf (``kanal/konsistenz.py``, 02:45)
selbst nach — oder sofort über „HA-Spiegel jetzt abgleichen" in der Reparatur-Werkbank (MartyBr, simon42 #429:
derselbe Lauf, von Hand; er korrigiert nichts in eedc, er übernimmt HAs Korrektur). Monate, die mit dem Sprung schon gespeichert wurden („Aus HA laden", Sammelimport — Entscheid D3),
bleiben gespeichert, bis der Anwender sie neu übernimmt; der Text sagt es.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import text

from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import (
    LINK_ENERGIEPROFIL,
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
)

#: Prüffenster in Tagen — ein Monat, die Frage, um die es geht (wie ``ruecksprung.RUECKSPRUNG_FENSTER_TAGE``).
FENSTER_TAGE = 30
#: Ein Reset: der Stand fällt auf höchstens diesen Anteil des vorigen.
RESET_ANTEIL = 0.1
#: Eine Rückkehr: der Stand erreicht wieder mindestens diesen Anteil des Stands vor dem Reset.
RUECKKEHR_ANTEIL = 0.9
#: So lange darf der Zähler zwischen Reset und Rückkehr schweigen.
RUECKKEHR_STUNDEN = 72
#: Unterhalb dieses Stands (kWh) ist ein „Reset" nicht von einem echten Neubeginn zu unterscheiden.
MIN_STAND_KWH = 1.0
#: Wie viele Funde die Meldung beim Namen nennt.
BEISPIELE = 5
#: Ab so vielen Tagen im Fenster mit einem Reset in der ersten Zeile des Tages ist der Sensor ein Tageszähler (N-764,
#: N-765, #436): PV-Tagesertrag, Utility-Meter „heute" gehen zu Beginn jedes Tages auf 0 — um Mitternacht oder, ohne
#: Nachtzeilen, in der ersten Morgenzeile; ein nächtlich abgeschalteter Lebenszeitzähler (das N-586-Muster) fällt in
#: der letzten Zeile des Abends. Ein einzelner Tag reicht nicht (benannte Grenze).
TAGESZAEHLER_MIN_TAGE = 2


@dataclass(frozen=True)
class Sprung:
    statistic_id: str
    #: ``start_ts`` der Zeile, mit der der Stand zurückkehrt (dort steht der Sprung in ``sum``).
    rueckkehr_ts: int
    menge_kwh: float
    stand_vorher: float
    stand_reset: float


def _ist_reset(st0: Optional[float], st: Optional[float], su0: Optional[float]) -> bool:
    """Fällt der Stand von ``st0`` auf höchstens ``RESET_ANTEIL`` davon?"""
    return (st0 is not None and st is not None and su0 is not None and st0 >= MIN_STAND_KWH
            and st <= RESET_ANTEIL * st0)


def _ist_tagesbeginn(ts0: int, ts: int) -> bool:
    """Ist die Zeile ``ts`` die erste ihres lokalen Kalendertags (Prozess-Zeitzone = HA) — liegt die Vorzeile ``ts0``
    an einem anderen Tag? Die 00:00-Zeile ist der Sonderfall; ohne Nachtzeilen ist es die erste Morgenzeile (N-765)."""
    return datetime.fromtimestamp(ts).date() != datetime.fromtimestamp(ts0).date()


def _tagesbeginn_reset_tage(zeilen: Sequence[tuple[int, Optional[float], Optional[float]]]) -> set:
    """Kalendertage (Prozess-Zeitzone = HA), an denen der Reset in der ersten Zeile des Tages liegt."""
    tage = set()
    for (ts0, st0, su0), (ts, st, _su) in zip(zeilen, zeilen[1:]):
        if _ist_reset(st0, st, su0) and _ist_tagesbeginn(ts0, ts):
            tage.add(datetime.fromtimestamp(ts).date())
    return tage


def finde_spruenge(statistic_id: str, zeilen: Sequence[tuple[int, Optional[float], Optional[float]]]) -> list[Sprung]:
    """Reine Funktion: ``zeilen`` = ``(start_ts, state, sum)`` aufsteigend. Je Reset mit Rückkehr ein ``Sprung``.

    N-764/N-765 (#436): ein Reset in der ersten Zeile eines Tages (00:00, oder ohne Nachtzeilen die erste
    Morgenzeile) eines Sensors, der an mindestens ``TAGESZAEHLER_MIN_TAGE`` Tagen des Fensters zu Tagesbeginn
    zurückgeht, ist der Zyklus eines Tageszählers und kein Befund — auch wenn die erste helle Stunde nach einem
    schwachen Vortag schon ``RUECKKEHR_ANTEIL`` des Vortagsstands erreicht (dann sähe er sonst wie eine Rückkehr in
    EINER Stunde aus). Alle anderen Resets wie bisher.
    """
    out: list[Sprung] = []
    tageszaehler = len(_tagesbeginn_reset_tage(zeilen)) >= TAGESZAEHLER_MIN_TAGE
    i = 1
    while i < len(zeilen):
        ts0, st0, su0 = zeilen[i - 1]
        ts, st, _su = zeilen[i]
        if (_ist_reset(st0, st, su0)
                and not (tageszaehler and _ist_tagesbeginn(ts0, ts))):
            for j in range(i + 1, len(zeilen)):
                tsj, stj, suj = zeilen[j]
                if tsj - ts > RUECKKEHR_STUNDEN * 3600 or stj is None:
                    break
                if stj <= RESET_ANTEIL * st0:
                    continue                      # noch unten
                # Die erste Zeile über dem Reset-Band: Rückkehr nur, wenn sie in EINER Stunde (von der unteren
                # Nachbarzeile) auf den alten Stand springt — sonst zählt der Zähler hoch (Tagesreset, Tausch).
                if stj >= RUECKKEHR_ANTEIL * st0 and suj is not None:
                    menge = (suj - su0) - (stj - st0)
                    if menge > 0:
                        out.append(Sprung(statistic_id, int(tsj), menge, st0, st))
                i = j
                break
        i += 1
    return out


_SQL = """
SELECT q.statistic_id, s.start_ts, s.state, s.sum
FROM kanal k
JOIN kanal_quelle q ON q.kanal_id = k.id
JOIN kanal_statistik s ON s.kanal_id = k.id AND s.start_ts >= q.gueltig_ab
WHERE k.anlage_id = :a AND k.art = 'sum' AND q.familie = 'spiegel' AND s.start_ts >= :von AND s.start_ts < :bis
  AND NOT EXISTS (SELECT 1 FROM kanal_quelle q2 WHERE q2.kanal_id = k.id AND q2.gueltig_ab > q.gueltig_ab
                  AND q2.gueltig_ab <= s.start_ts)
ORDER BY q.statistic_id, s.start_ts
"""


class HaZaehlersprungChecks:
    """Prüfung: Zählersprung in der HA-Statistik (Reset und Rückkehr)."""

    async def _check_ha_zaehlersprung(self, anlage: Anlage, jetzt: Optional[datetime] = None) -> list[CheckErgebnis]:
        """Benennt Phantomsprünge im Spiegel der HA-Statistik — Stunde, Sensor, Menge — mit dem Reparaturweg in HA.

        Args:
            jetzt: Ende des Prüffensters; eine Naht für die Proben (keine Prozessuhr im Rumpf, N-167).
        """
        bis = jetzt or datetime.now()
        von = bis - timedelta(days=FENSTER_TAGE)
        zeilen: dict[str, list] = {}
        for sid, ts, st, su in (await self.db.execute(text(_SQL), {
            "a": anlage.id, "von": int(von.timestamp()), "bis": int(bis.timestamp())})).all():
            zeilen.setdefault(sid, []).append((int(ts), st, su))
        funde: list[Sprung] = []
        for sid, z in zeilen.items():
            funde += finde_spruenge(sid, z)
        if not funde:
            return []
        funde.sort(key=lambda f: -f.menge_kwh)

        def _zeile(f: Sprung) -> str:
            stunde = datetime.fromtimestamp(f.rueckkehr_ts)
            return (f"{f.statistic_id} am {stunde.strftime('%d.%m.%Y')}, Stunde ab {stunde.strftime('%H:%M')}: "
                    f"+{fmt_zahl(f.menge_kwh, 1)} kWh (Stand {fmt_zahl(f.stand_vorher, 1)} → "
                    f"{fmt_zahl(f.stand_reset, 1)} → zurück)")

        namen = "; ".join(_zeile(f) for f in funde[:BEISPIELE])
        if len(funde) > BEISPIELE:
            namen += f" (+{len(funde) - BEISPIELE} weitere)"
        return [CheckErgebnis(
            kategorie=CheckKategorie.HA_ZAEHLERSPRUNG.value,
            schwere=CheckSeverity.WARNING,
            meldung=f"{len(funde)} Zählersprung/-sprünge in der Home-Assistant-Statistik — Tag und Monat zeigen sie mit",
            details=(
                "Ein Sensor hat kurz 0 gemeldet und ist danach auf seinen alten Stand zurückgekehrt. Home Assistant "
                "hält das für einen Neubeginn des Zählers und rechnet beim Zurückkehren den ganzen Zählerstand als "
                "Verbrauch bzw. Erzeugung dieser Stunde. eedc übernimmt die Statistik so, wie das Energie-Dashboard "
                "von Home Assistant sie zeigt — der Sprung steht deshalb in Tag, Monat und Jahr. "
                f"Gefunden in den letzten {FENSTER_TAGE} Tagen: {namen}. "
                "Lösung in Home Assistant: Entwicklerwerkzeuge → Statistik → den Sensor suchen → beim Symbol "
                "„Wert anpassen“ die genannte Stunde wählen und den Zuwachs auf die echte Menge setzen. eedc gleicht "
                "die korrigierte Statistik beim nächsten nächtlichen Abgleich von selbst ab — sofort geht es danach "
                "unter Einstellungen → Daten → Energieprofil-Pflege → Reparatur-Werkbank mit „HA-Spiegel jetzt "
                "abgleichen“. Hast du den Monat schon "
                "mit dem Sprung gespeichert („Aus HA laden“ oder Import), übernimm ihn danach im Monatsabschluss neu."
            ),
            # Der Knopf zeigt auf die Energieprofil-Pflege (MartyBr, simon42 #429): dort liegt seit Päckchen N
            # „HA-Spiegel jetzt abgleichen", der zweite Schritt nach der Korrektur in HA. ⛔ Nicht auf die
            # eedc-Datenquellen — das war bis zum Lab-Durchlauf 4.1.3-rc1 (07.10.2026) so und falsch, an der
            # Zuordnung ist nichts falsch. Auf HAs Werkzeug selbst kann der Knopf nicht zeigen
            # (`DatenCheckerTeile.tsx` navigiert nur innerhalb von eedc); der erste Schritt steht im Text.
            link=LINK_ENERGIEPROFIL,
        )]


__all__ = ["BEISPIELE", "FENSTER_TAGE", "HaZaehlersprungChecks", "Sprung", "finde_spruenge"]
