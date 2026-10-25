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
ist es auch dann nicht, wenn seine erste helle Stunde nach einem schwachen Vortag den Vortagsstand schon fast erreicht.
Tageszähler erkennt die Regel an zwei Merkmalen (eines genügt): (A) der Sensor geht an mindestens ``TAGESZAEHLER_MIN_TAGE``
Tagen des Fensters in der ersten Zeile seines lokalen Kalendertags auf 0 (N-764/N-765, #436 — die 00:00-Zeile, oder bei
einem nachts abgeschalteten Wechselrichter die erste Morgenzeile); (B) sein Stand vor dem Reset ist höchstens
``TAGESZAEHLER_FAKTOR`` × sein größter Tageszuwachs im Fenster (N-768, #436) — ein Tageszähler kommt nie über einen Tag
hinaus, ein Gesamtzähler liegt weit darüber, gleich wo seine 0 in der Zeilenfolge steht (Abendzeile, Nachtzeile 01:00,
Weckwert). An einem Tageszähler ist nur noch der **Aussetzer** ein Befund: eine 0 mitten im Tag, auf die der alte Stand in
der unmittelbar nächsten Zeile zurückkommt (HA bucht den Tag doppelt); jede andere 0 ist sein Zyklus. Die Phantommenge ist der Zuwachs von ``sum`` über die Strecke abzüglich dessen, was der Zähler
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
#: Merkmal (A) eines Tageszählers (N-764, N-765, #436): an so vielen Tagen des Fensters steht ein Reset in der ersten
#: Zeile des Tages — um Mitternacht oder, ohne Nachtzeilen, in der ersten Morgenzeile. Ein nächtlich abgeschalteter
#: Gesamtzähler (N-586-Muster) fällt in der letzten Zeile des Abends und erfüllt (A) nicht.
TAGESZAEHLER_MIN_TAGE = 2
#: Merkmal (B) eines Tageszählers (N-768, #436): sein Stand vor dem Reset ist höchstens dieses Vielfache seines größten
#: Tageszuwachses im Fenster (Zuwachs des ``state`` je Kalendertag, ohne die Rückkehr-Zeilen der Kandidaten). Ein
#: Tageszähler liegt bei ≈ 1, ein Gesamtzähler bei Hunderten. Benannte Grenze: ein Gesamtzähler mit weniger als drei Tagen
#: eigener Historie (oder ein Monatszähler in seinen ersten drei Tagen) gilt als Tageszähler; sein Phantom wäre entsprechend klein.
TAGESZAEHLER_FAKTOR = 3.0


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
    """Kalendertage (Prozess-Zeitzone = HA), an denen der Reset in der ersten Zeile des Tages liegt (Merkmal A)."""
    tage = set()
    for (ts0, st0, su0), (ts, st, _su) in zip(zeilen, zeilen[1:]):
        if _ist_reset(st0, st, su0) and _ist_tagesbeginn(ts0, ts):
            tage.add(datetime.fromtimestamp(ts).date())
    return tage


def _kandidaten(zeilen: Sequence[tuple[int, Optional[float], Optional[float]]]) -> list[tuple[int, int, float]]:
    """Das N-586-Muster, roh: je Reset mit Rückkehr in EINER Zeile ``(reset_i, rueckkehr_j, menge_kwh)``.

    Die erste Zeile über dem Reset-Band entscheidet: springt sie (von der unteren Nachbarzeile) auf mindestens
    ``RUECKKEHR_ANTEIL`` des alten Stands, ist das die Rückkehr; sonst zählt der Zähler hoch (Tagesreset, Tausch) und
    die Suche endet dort."""
    out: list[tuple[int, int, float]] = []
    i = 1
    while i < len(zeilen):
        _ts0, st0, su0 = zeilen[i - 1]
        ts, st, _su = zeilen[i]
        if _ist_reset(st0, st, su0):
            for j in range(i + 1, len(zeilen)):
                tsj, stj, suj = zeilen[j]
                if tsj - ts > RUECKKEHR_STUNDEN * 3600 or stj is None:
                    break
                if stj <= RESET_ANTEIL * st0:
                    continue                      # noch unten
                if stj >= RUECKKEHR_ANTEIL * st0 and suj is not None:
                    menge = (suj - su0) - (stj - st0)
                    if menge > 0:
                        out.append((i, j, menge))
                i = j
                break
        i += 1
    return out


def _groesster_tageszuwachs(zeilen: Sequence[tuple[int, Optional[float], Optional[float]]], ohne: set) -> float:
    """Größter Zuwachs des Stands (``state``) je lokalem Kalendertag — ohne die Rückkehr-Zeilen ``ohne`` (Indizes),
    deren Zuwachs beim Gesamtzähler das Phantom selbst wäre. Rückgänge (Resets) zählen nicht."""
    je_tag: dict = {}
    for k in range(1, len(zeilen)):
        if k in ohne:
            continue
        st0, st = zeilen[k - 1][1], zeilen[k][1]
        if st0 is None or st is None or st < st0:
            continue
        tag = datetime.fromtimestamp(zeilen[k][0]).date()
        je_tag[tag] = je_tag.get(tag, 0.0) + (st - st0)
    return max(je_tag.values(), default=0.0)


def finde_spruenge(statistic_id: str, zeilen: Sequence[tuple[int, Optional[float], Optional[float]]]) -> list[Sprung]:
    """Reine Funktion: ``zeilen`` = ``(start_ts, state, sum)`` aufsteigend. Je Reset mit Rückkehr ein ``Sprung``.

    Kandidaten liefert ``_kandidaten`` (N-586-Form). Ein Kandidat ist der Zyklus eines **Tageszählers** und kein Befund,
    wenn der Sensor Merkmal (A) erfüllt (``_tagesbeginn_reset_tage`` ≥ ``TAGESZAEHLER_MIN_TAGE``, N-764/N-765) oder sein
    Stand vor dem Reset Merkmal (B) erfüllt (≤ ``TAGESZAEHLER_FAKTOR`` × größter Tageszuwachs, N-768) — es sei denn, es
    ist ein **Aussetzer**: die 0 steht nicht in der ersten Zeile ihres Tages UND der alte Stand kommt in der unmittelbar
    nächsten Zeile zurück (HA bucht den Tag doppelt, N-764-Gegenprobe). Ein Gesamtzähler (weder A noch B) wird wie bisher
    bei jeder Rückkehr gemeldet.
    """
    kandidaten = _kandidaten(zeilen)
    if not kandidaten:
        return []
    tagesform_a = len(_tagesbeginn_reset_tage(zeilen)) >= TAGESZAEHLER_MIN_TAGE
    tageszuwachs = _groesster_tageszuwachs(zeilen, {j for _i, j, _m in kandidaten})
    out: list[Sprung] = []
    for i, j, menge in kandidaten:
        ts0, st0, _su0 = zeilen[i - 1]
        ts, st, _su = zeilen[i]
        tagesform = tagesform_a or st0 <= TAGESZAEHLER_FAKTOR * tageszuwachs
        aussetzer = not _ist_tagesbeginn(ts0, ts) and j == i + 1
        if tagesform and not aussetzer:
            continue
        out.append(Sprung(statistic_id, int(zeilen[j][0]), menge, st0, st))
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


__all__ = ["BEISPIELE", "FENSTER_TAGE", "TAGESZAEHLER_FAKTOR", "TAGESZAEHLER_MIN_TAGE", "HaZaehlersprungChecks",
           "Sprung", "finde_spruenge"]
