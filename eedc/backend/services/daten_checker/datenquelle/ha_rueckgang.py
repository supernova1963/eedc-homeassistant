"""Daten-Checker — Rückgang in der HA-Langzeitstatistik (N-639, Melder Frank85, 08.10.2026).

**Warum es das gibt.** Seit HA-Bauform E4a-2 liest eedc die Bilanz-Gruppe aus dem Spiegel der HA-Statistik
(``kanal_statistik``, Familie ``spiegel``, Art ``sum``) wie das HA-Energie-Dashboard — ohne Deckel und **ohne
Rücksprung-Verwurf** (R-5, HA-Teil; ``services/kanal/lesen.py``: Δ = Σ HA-``change``). Fällt HAs ``sum`` in einer
Stunde — der Wert wurde in HA nachträglich nach unten angepasst („Wert anpassen" mit einer zu großen Korrektur oder
an der falschen Stunde), oder ein Sensor mit ``state_class: total`` meldet ein negatives Delta —, dann steht diese
Stunde als **negative Menge** in Tag, Monat und Jahr, in eedc wie in HA. Vor 4.1.3 verschluckte die Regel R4 den
Rückgang still; jetzt ist eedc HA-konform, aber ohne diese Prüfung stumm (Frank85: Netzbezug 05.06.2025 −540 kWh,
„Aus HA laden" Juni −321,1). Die Schwester ``ha_sprung.py`` kennt nur das Phantom-Muster (Reset + Rückkehr — dort
STEIGT ``sum``); ein Rückgang ist der zweite Fall derselben Klasse (Entscheid N-586: wie HA rechnen, benennen).

**Das Muster:** je Kanal jede Zeile, deren Kanalwert (``sum + offset`` der für die Stunde geltenden Quelle — derselbe
Wert, den ``lesen.py`` differenziert) unter dem der Vorzeile liegt, um mehr als ``TOLERANZ_KWH``. Gezählt wird die
Zeile nur, wenn ihre geltende Quelle der Spiegel ist. Ein täglich zurückgesetzter Helfer (utility_meter) ist KEIN
Befund: sein ``state`` fällt, HAs ``sum`` zählt weiter (Reset = neuer Zyklus). Ein Phantomsprung ebenso wenig — dort
springt ``sum`` nach oben (``ha_sprung``).

**Fenster: der ganze Spiegel, nicht 30 Tage** (anders als ``ha_sprung.FENSTER_TAGE``). Ein Rückgang ist kein
Ereignis der letzten Wochen, sondern eine Eigenschaft der Statistik, die eedc in JEDEM Zeitraum liest, der ihn
enthält: „Aus HA laden" und der Sammelimport holen jeden alten Monat, Cockpit → Tag/Monat/Jahr rechnen jeden
gedeckten Zeitraum aus dem Spiegel. Ein Rückgang von vor 16 Monaten (Frank: Juni 2025, gemeldet am 08.10.2026) wäre
mit einem 30-Tage-Fenster nie benannt worden — genau der Fall, der ihn ausgelöst hat. Die Abfrage liest nur die
Zeilen unter der Toleranz zurück (Fensterfunktion ``LAG`` in SQLite, über den Primärschlüssel-Index
``(kanal_id, start_ts)``), nicht den ganzen Spiegel nach Python.

**Toleranz** ``TOLERANZ_KWH`` = 1e-6 kWh: nur Rundungsrauschen der Gleitkomma-Summe (HA führt ``sum`` als
``double``; bei Ständen bis 1e6 kWh liegt der Rundungsfehler einer Addition bei etwa 1e-10 kWh, der von
``sum + offset`` ebenso). Jede größere Abnahme ist eine Abnahme, die HA gebucht hat und die Tag und Monat zeigen —
auch eine kleine (ein ``total``-Sensor mit Messrauschen): eedc rechnet sie mit, also benennt der Checker sie.

**Tag** = der Tag, in dem Cockpit → Tag die Menge zeigt. Die Zeilen, die der Checker liest, sind Kanal-Zeilen, und
ein Kanal-Tag ist seit HA-Bauform S4 (R-3, E-S4-1) der **Kalendertag** ``[D 00:00, D+1 00:00)`` (``kanal/fenster.tagesfenster``,
wie das HA-Energie-Dashboard): eine Zeile ``start_ts = H`` gehört zum Tag ihres Beginns ``H`` (Prozesszone), auch die
Stunde ab 23:00. Bis E-S4-4 nannte der Checker den Tag des Bestandsfensters ``[Vortag 23:00, 23:00)`` (``H + 1 h``) —
Cockpit → Tag zeigte die Zeile 23:00 dann am Tag D, die Meldung am Tag D+1 (Nachmessung E-S4-1 M-3). Die Rechnung steht
hier selbst (gleich ``fenster.kalendertag_der_stunde``; ``fenster`` gehört zur Lese-Schicht, deren Importeure
``test_kanal_lesen_waechter`` festhält — die Probe vergleicht beide). Die Stunde für HAs „Wert anpassen" ist der Beginn
der Zeile, ``H``.

⛔ **Kein Reparatur-Knopf, kein Verwerfen in eedc.** Die Quelle ist HAs Statistik; korrigiert wird dort
(Entwicklerwerkzeuge → Statistik → „Wert anpassen"), und eedc zieht über den nächtlichen Konsistenzlauf
(``kanal/konsistenz.py``, 02:45) selbst nach — seine Prüfstelle vergleicht ab dem Abschnittsbeginn und halbiert
über den ganzen Abschnitt, ein alter Monat ist also eingeschlossen (gelesen im Code; im Lab belegt ist eine Korrektur
vom Vortag, Journal 08.10.2026 05:40). Monate, die mit dem Rückgang schon gespeichert wurden („Aus HA laden",
Sammelimport — Entscheid D3), bleiben gespeichert, bis der Anwender sie neu übernimmt; der Text sagt es. Kein Link
(wie ``ha_sprung``, Lab 4.1.3-rc1): die Checker-Links navigieren nur innerhalb von eedc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Optional

from sqlalchemy import text

from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
)

#: Unterhalb dieser Abnahme (kWh) ist ein fallender Kanalwert Rundungsrauschen der Gleitkomma-Summe (Docstring).
TOLERANZ_KWH = 1e-6
#: Wie viele Tage die Meldung beim Namen nennt.
BEISPIELE = 5


@dataclass
class Rueckgang:
    """Ein Sensor an einem Tag: Σ der negativen Stunden-Mengen (positiv angegeben), die Stunden selbst."""

    statistic_id: str
    tag: date
    menge_kwh: float = 0.0
    #: ``(start_ts, Menge)`` je Stunde mit Rückgang, Menge positiv.
    stunden: list[tuple[int, float]] = field(default_factory=list)
    #: #429 (16.10.2026): Ende der Quelle (``gueltig_ab`` der Nachfolgerin, Unix-Sekunden), wenn der Sensor nicht mehr
    #: die jüngste Quelle seines Kanals ist (Sensortausch) — ``None`` für den aktuellen Sensor. Die Zeilen zählen weiter
    #: (eedc liest sie), nur der Text nennt den Vorgänger.
    zugeordnet_bis: Optional[int] = None

    @property
    def groesste_stunde(self) -> int:
        return max(self.stunden, key=lambda s: s[1])[0]


def tag_der_zeile(start_ts: int) -> date:
    """Der Tag, in dem eine Zeile ``start_ts`` zählt — der Kalendertag ihres Beginns (Kanal-Tag, S4-R-3a; Docstring)."""
    return datetime.fromtimestamp(start_ts).date()


def gruppiere(zeilen: Iterable[tuple]) -> list[Rueckgang]:
    """Reine Funktion: ``(statistic_id, start_ts, delta[, gueltig_bis])`` mit ``delta < 0`` → je Sensor und Tag ein
    ``Rueckgang``, größte Menge zuerst. ``gueltig_bis`` (#429): Ende der Quelle der Zeile, ``None`` = jüngste Quelle."""
    je: dict[tuple[str, date], Rueckgang] = {}
    for sid, ts, delta, *rest in zeilen:
        tag = tag_der_zeile(int(ts))
        r = je.setdefault((sid, tag), Rueckgang(sid, tag))
        r.menge_kwh += -float(delta)
        r.stunden.append((int(ts), -float(delta)))
        bis = rest[0] if rest else None
        if bis is not None:
            r.zugeordnet_bis = max(int(bis), r.zugeordnet_bis or 0)
    return sorted(je.values(), key=lambda r: (-r.menge_kwh, r.statistic_id, r.tag))


# Je Kanal die Kanalwerte (`sum + offset` der für die Stunde geltenden Quelle, wie `lesen.py`) in Zeitfolge, daneben
# der Wert der Vorzeile (`LAG`). Zurück kommen nur die Zeilen mit Abnahme, deren geltende Quelle der Spiegel ist. Die
# Quelle einer Zeile ist die mit dem größten `gueltig_ab <= start_ts` — als Bereich `[gueltig_ab, nächstes gueltig_ab)`
# über `LEAD`, damit der Verbund den Primärschlüssel-Index nutzt statt je Zeile eine Unterabfrage. Eine Zeile vor der
# ersten Quelle hat keinen Kanalwert und zählt nicht (wie `lesen.py`); eine Zeile ohne `sum` ist kein Stand.
_SQL = """
WITH q AS (
    SELECT kanal_id, gueltig_ab, familie, statistic_id, "offset" AS versatz,
           LEAD(gueltig_ab) OVER (PARTITION BY kanal_id ORDER BY gueltig_ab) AS gueltig_bis
    FROM kanal_quelle
),
z AS (
    SELECT q.statistic_id, q.familie, q.gueltig_bis, s.start_ts,
           s.sum + q.versatz AS wert,
           LAG(s.sum + q.versatz) OVER (PARTITION BY k.id ORDER BY s.start_ts) AS vorher
    FROM kanal k
    JOIN q ON q.kanal_id = k.id
    JOIN kanal_statistik s ON s.kanal_id = k.id AND s.start_ts >= q.gueltig_ab
                          AND (q.gueltig_bis IS NULL OR s.start_ts < q.gueltig_bis)
    WHERE k.anlage_id = :a AND k.art = 'sum' AND s.sum IS NOT NULL
)
SELECT statistic_id, start_ts, wert - vorher AS delta, gueltig_bis
FROM z
WHERE familie = 'spiegel' AND vorher IS NOT NULL AND wert - vorher < -:tol
ORDER BY statistic_id, start_ts
"""


def _menge(kwh: float) -> str:
    # Eine Abnahme unter 0,05 kWh läse sich mit einer Nachkommastelle als „0,0" — dann drei.
    return fmt_zahl(kwh, 1 if kwh >= 0.05 else 3)


def _zeile(r: Rueckgang) -> str:
    # Die Stunde liegt im Tag der Zeile (Kalendertag ihres Beginns) — die Uhrzeit genügt, auch für 23:00.
    ab = datetime.fromtimestamp(r.groesste_stunde).strftime("%H:%M")
    wo = f"Stunde ab {ab}" if len(r.stunden) == 1 else f"{len(r.stunden)} Stunden, die größte ab {ab}"
    vorgaenger = ("" if r.zugeordnet_bis is None else
                  f" (Vorgänger-Sensor, zugeordnet bis {datetime.fromtimestamp(r.zugeordnet_bis).strftime('%d.%m.%Y')})")
    return f"{r.statistic_id}{vorgaenger} am {r.tag.strftime('%d.%m.%Y')}: −{_menge(r.menge_kwh)} kWh ({wo})"


class HaRueckgangChecks:
    """Prüfung: Rückgang des Zählerstands in der HA-Statistik (``sum`` fällt)."""

    async def _check_ha_rueckgang(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Benennt jeden Tag, an dem HAs Summe eines gespiegelten Sensors fällt — Sensor, Tag, Menge, Stunde — mit
        dem Weg in HA. Ohne Spiegel (Standalone) kein Befund."""
        zeilen = (await self.db.execute(text(_SQL), {"a": anlage.id, "tol": TOLERANZ_KWH})).all()
        funde = gruppiere((sid, ts, d, bis) for sid, ts, d, bis in zeilen)
        if not funde:
            return []
        namen = "; ".join(_zeile(r) for r in funde[:BEISPIELE])
        if len(funde) > BEISPIELE:
            namen += f" (+{len(funde) - BEISPIELE} weitere)"
        return [CheckErgebnis(
            kategorie=CheckKategorie.HA_ZAEHLER_RUECKGANG.value,
            schwere=CheckSeverity.WARNING,
            # N-646 (Glen, #423): „negative Menge" in der Überschrift wurde als Vorzeichen (Entladen) gelesen — die
            # Überschrift nennt jetzt den gefallenen Zählerstand, der Detailtext sagt, dass es keine Richtung ist.
            meldung=(f"{len(funde)} Tag(e), an denen ein Zählerstand in der Home-Assistant-Statistik gefallen ist — "
                     "der Rückgang zieht Tag und Monat nach unten"),
            details=(
                "An diesen Tagen ist die Summe eines Sensors in der Langzeitstatistik von Home Assistant gefallen, "
                "statt zu steigen — meist, weil der Wert in Home Assistant nachträglich nach unten angepasst wurde "
                "oder der Sensor einen kleineren Zählerstand gemeldet hat. eedc übernimmt die Statistik so, wie das "
                "Energie-Dashboard von Home Assistant sie zeigt — der Rückgang steht deshalb als Abzug (negative Menge) in "
                "Tag, Monat und Jahr. Das ist kein Vorzeichen für Entladen oder Einspeisen: Lade-, Entlade- und "
                f"Einspeisezähler laufen nur nach oben, jede Richtung hat ihr eigenes Feld. Gefunden: {namen}. "
                "Lösung in Home Assistant: Entwicklerwerkzeuge → Statistik → den Sensor suchen → beim Symbol "
                "„Wert anpassen“ die genannte Stunde wählen und die Menge auf den echten Wert setzen. eedc gleicht "
                "die korrigierte Statistik beim nächsten nächtlichen Abgleich von selbst ab. Hast du den Monat schon "
                "mit dem Rückgang gespeichert („Aus HA laden“ oder Import), übernimm ihn danach im Monatsabschluss neu."
                + (
                    # #429 (jedema1805): die Zeilen eines ersetzten Sensors zählen weiter — der Text sagt es.
                    " Stammt der Rückgang von einem Sensor, den du inzwischen ersetzt hast, entfernt die "
                    "Werkbank-Operation „Werte vor dem Sensorbeginn verwerfen“ seine Werte vor dem Beginn des neuen "
                    "Sensors (Einstellungen → Daten → Energieprofil-Pflege); die Meldung verschwindet dann."
                    if any(r.zugeordnet_bis is not None for r in funde) else ""
                )
            ),
            # Kein „Beheben"-Link — dieselbe Begründung wie `ha_sprung` (Lab 4.1.3-rc1): die Korrektur liegt in Home
            # Assistant, die Checker-Links navigieren nur innerhalb von eedc. Der Weg steht im Text.
            link=None,
        )]


__all__ = ["BEISPIELE", "HaRueckgangChecks", "Rueckgang", "TOLERANZ_KWH", "gruppiere", "tag_der_zeile"]
