"""Daten-Checker — Zählerstand springt in der HA-Statistik (Sensorwechsel mit Grund, U2 Lauf c, Rechenweg F12, Leitlinie
Gernot 19.11.2026 / Bauplan Nr. 132 (b)).

**Warum es das gibt.** Wird das Gerät hinter einem Zähler getauscht und Home Assistant führt dieselbe Entität weiter, zählt HA
den Unterschied der Zählerstände als Menge der Stunde des Tauschs — einen Sprung nach oben ganz, einen Neubeginn, der nicht bei
0 liegt, mit dem ganzen neuen Stand. eedc übernimmt HAs Statistik wie das Energie-Dashboard (Grundregel «Quellentreue») und
berichtigt nichts; diese Prüfung benennt die Stunde (Feld, Sensor, Menge) und den Weg in Home Assistant. Bis hierhin erkannte
das keine Prüfung: ``ha_zaehlersprung`` kennt nur «kurz 0 und zurück», ``ha_zaehler_rueckgang`` nur eine fallende Summe.

**Erkennung:** ``core/berechnungen/zaehlerstand_sprung.py`` (Maß, zwei Arme, Schwellen aus M4) je **Quell-Abschnitt** eines
Mengen- oder Stand-Kanals mit Familie Spiegel — ein Zeilenpaar über eine Wechselstelle (zwei Statistiken) ist nie ein Sprung.
Gelesen wird der ganze Spiegel (wie ``ha_rueckgang``): ein Sprung steht in jedem Zeitraum, der ihn enthält, auch in einem alten
Monat, den «Aus HA laden» oder der Sammelimport holt. Die Rückkehr-Stunden des Musters «kurz 0 und zurück» überlässt die Prüfung
``ha_zaehlersprung`` (``ha_sprung.rueckkehr_stunden``). **U3-K (B2):** der Arm «Sprung» meldet nur bei reifem Bezug oder über der
Grenze «mehr, als eine Anlage in einer Stunde leisten kann» (``grenze_der_einheit``, nur kWh) — die erste gewöhnliche Stunde
nach Wochen mit Standby ist kein Befund.

**Zwei Lagen, eine Zeile:**

* **Mengen-Zähler** (Kanal-Art ``sum``): «Summe anpassen» in HA berichtigt die Summe; eedc übernimmt sie beim nächtlichen
  Abgleich oder sofort mit «Aus Home Assistant neu übernehmen» (``SPIEGEL_ABGLEICH_TAG``, danach der Tag des größten Funds neu
  aufgebaut). Danach ist Δ ``sum`` der Stunde klein (das Maß fällt unter die Schwelle) bzw. ungleich Δ ``state`` — der Befund ist
  weg. Schwere Warnung, Aktion.
* **Stand-Zähler** (Kanal-Art ``stand``: Gas, Wasser, Öl, Kilometerstand): eedc rechnet mit ``state``; «Summe anpassen» ändert nur
  ``sum`` und wirkte hier nicht (Lab, Messblatt 4c-0 §10). Der Text nennt deshalb die Wege nach Entscheid E2 (Bauplan Nr. 139):
  den getauschten Zähler als eigenes Gerät führen (Handbuch Einstellungen §3.4a) und beim nächsten Tausch einen neuen Sensor
  zuordnen und «Bisherige Werte bleiben» wählen. Ohne Mengen-Fund ist die Zeile eine Auskunft mit Schwere Info (W-6).

**Beginn nicht bei 0 (Fund-Päckchen B, 22.11.2026):** beginnt die Statistik eines Mengen-Zählers in HA mit einem Stand über
der Grenze (b) — etwa eine importierte Statistik —, zählen HA und eedc (``kanal/lesen._ha_beginn_sql``, Anfangsstand 0) den
ganzen Stand als Menge der ersten Stunde. Die Zeile nennt sie (``zaehlerstand_sprung.beginn_ueber_grenze``), nur wenn eedc
diese erste Zeile ab 0 zählt (``kanal/bilanz_leser.ha_statistik_beginn`` — dieselbe Bedingung); sonst zählt sie nirgends.
Derselbe Weg wie beim Sprung: «Summe anpassen» in HA an der ersten Stunde, danach «Aus Home Assistant neu übernehmen».

Der Kanalwert eines Mengen-Kanals ist ``sum + offset``; die Differenz zweier Zeilen derselben Quelle ist Δ ``sum`` — der Kern
liest ``sum`` und ``state`` wörtlich.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, text

from backend.core.berechnungen.zaehlerstand_sprung import (
    BEGINN,
    NEUBEGINN,
    Standsprung,
    beginn_ueber_grenze,
    finde_standspruenge,
    grenze_unmoeglich,
)
from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.services.daten_checker.datenquelle.ha_sprung import rueckkehr_stunden
from backend.services.daten_checker.kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
    aktion_spiegel_abgleich_tag,
)

#: Wie viele Funde die Meldung beim Namen nennt.
BEISPIELE = 5

# Je Spiegel-Abschnitt eines Mengen- oder Stand-Kanals die Zeilen in Zeitfolge (Abschnitt = [gueltig_ab, nächstes gueltig_ab)).
_SQL = """
WITH q AS (
    SELECT kanal_id, gueltig_ab, familie, statistic_id,
           LEAD(gueltig_ab) OVER (PARTITION BY kanal_id ORDER BY gueltig_ab) AS gueltig_bis
    FROM kanal_quelle
)
SELECT k.id, k.key, k.art, k.einheit, q.gueltig_ab, q.statistic_id, s.start_ts, s.state, s.sum
FROM kanal k
JOIN q ON q.kanal_id = k.id
JOIN kanal_statistik s ON s.kanal_id = k.id AND s.start_ts >= q.gueltig_ab
                      AND (q.gueltig_bis IS NULL OR s.start_ts < q.gueltig_bis)
WHERE k.anlage_id = :a AND k.art IN ('sum', 'stand') AND q.familie = 'spiegel' AND s.familie = 'spiegel'
ORDER BY k.id, q.gueltig_ab, s.start_ts
"""


class _Fund:
    __slots__ = ("key", "stand", "einheit", "sensor", "sprung")

    def __init__(self, key: str, stand: bool, einheit: str, sensor: str, sprung: Standsprung):
        self.key, self.stand, self.einheit, self.sensor, self.sprung = key, stand, einheit, sensor, sprung


def _abschnitte(zeilen) -> list[tuple[tuple, list[tuple]]]:
    """Die Zeilen der Abfrage je Abschnitt: ``((key, art, einheit, sensor), [(start_ts, state, sum)])``."""
    out: list[tuple[tuple, list[tuple]]] = []
    marke = None
    for kid, key, art, einheit, ab, sid, ts, st, su in zeilen:
        if (kid, ab) != marke:
            marke = (kid, ab)
            out.append(((key, art, einheit or "", sid or ""), []))
        out[-1][1].append((int(ts), st, su))
    return out


def grenze_der_einheit(einheit: Optional[str], schwelle_anlage: Optional[float]) -> Optional[float]:
    """B2 (b) (U3-K): die Grenze «mehr, als eine Anlage in einer Stunde leisten kann» — nur an kWh-Feldern; ein Stand-Zähler in
    einer anderen Einheit (m³, l, km) hat keine."""
    return grenze_unmoeglich(schwelle_anlage) if einheit == "kWh" else None


def finde(zeilen, schwelle_anlage: Optional[float] = None, beginn: Optional[dict[str, int]] = None) -> list[_Fund]:
    """Reine Funktion über die Zeilen der Abfrage: je Sprung ein Fund, größte Menge zuerst. ``schwelle_anlage``: 1,5 × kWp der
    Anlage (``snapshot/plausibility``), für die Grenze B2 (b). ``beginn``: je Mengen-Kanal, dessen erste Zeile eedc ab dem
    Anfangsstand 0 zählt, ihr ``start_ts`` (``ha_statistik_beginn``) — dort prüft der Fall «Beginn nicht bei 0»."""
    funde: list[_Fund] = []
    beginn = beginn or {}
    for (key, art, einheit, sid), z in _abschnitte(zeilen):
        stand = art == "stand"
        if not stand and beginn.get(key) == z[0][0]:
            sp = beginn_ueber_grenze(z[0], grenze_der_einheit(einheit, schwelle_anlage))
            if sp is not None:
                funde.append(_Fund(key, stand, einheit, sid, sp))
        for sp in finde_standspruenge(z, stand=stand, ausgenommen=rueckkehr_stunden(z),
                                      grenze=grenze_der_einheit(einheit, schwelle_anlage)):
            funde.append(_Fund(key, stand, einheit, sid, sp))
    funde.sort(key=lambda f: (-f.sprung.menge, f.sprung.start_ts))
    return funde


def _zeile(f: _Fund, namen: dict) -> str:
    stunde = datetime.fromtimestamp(f.sprung.start_ts)
    einheit = f" {f.einheit}" if f.einheit else ""
    wie = {NEUBEGINN: "der neue Stand beginnt nicht bei 0",
           BEGINN: "die Statistik beginnt mit diesem Stand statt bei 0"}.get(f.sprung.art, "der Stand springt nach oben")
    return (f"{namen.get(f.key, f.key)} ({f.sensor}) am {stunde.strftime('%d.%m.%Y')}, Stunde ab {stunde.strftime('%H:%M')}: "
            f"+{fmt_zahl(f.sprung.menge, 1)}{einheit} (Stand {fmt_zahl(f.sprung.stand_vorher, 1)} → "
            f"{fmt_zahl(f.sprung.stand_nachher, 1)}, {wie})")


def _aufzaehlung(funde: list[_Fund], namen: dict) -> str:
    s = "; ".join(_zeile(f, namen) for f in funde[:BEISPIELE])
    return s + (f" (+{len(funde) - BEISPIELE} weitere)" if len(funde) > BEISPIELE else "")


SATZ_WAS = ("In diesen Stunden ist der Zählerstand eines Sensors gesprungen — meist, weil das Gerät dahinter getauscht wurde und "
            "Home Assistant denselben Sensor weiterführt. Home Assistant zählt den Sprung als Verbrauch bzw. Erzeugung dieser "
            "Stunde; beginnt ein neuer Zähler nicht bei 0, zählt es seinen ganzen Stand. eedc übernimmt die Statistik so, wie "
            "das Energie-Dashboard von Home Assistant sie zeigt, und berichtigt nichts — der Sprung steht deshalb in Tag, Monat "
            "und Jahr.")
SATZ_BEGINN = ("Beginnt die Statistik eines Sensors in Home Assistant mit einem großen Stand statt bei 0 — etwa, weil sie "
               "importiert wurde —, zählt Home Assistant diesen Stand als Menge der ersten Stunde, eedc ebenso.")
SATZ_MENGE = ("Gefunden: {namen}. Lösung in Home Assistant: Einstellungen → Werkzeuge → Statistik (in älteren "
              "Home-Assistant-Versionen: Entwicklerwerkzeuge → Statistik) → den Sensor suchen → beim Symbol „Summe anpassen“ "
              "unter „Zeitpunkt auswählen“ die Zeit des Sprungs in der genannten Stunde wählen, bei „Neuer Wert“ die echte "
              "Menge eintragen und „Anpassen“ drücken. eedc gleicht die "
              "korrigierte Statistik beim nächsten nächtlichen Abgleich von selbst ab — oder sofort hier mit „Aus Home "
              "Assistant neu übernehmen“. Hast du den Monat schon mit dem Sprung gespeichert („Aus HA laden“ oder Import), "
              "übernimm ihn danach im Monatsabschluss neu.")
SATZ_STAND = ("Bei Zählerständen (Gas, Wasser, Öl, Kilometerstand) rechnet eedc mit dem Stand, den der Sensor anzeigt, nicht mit "
              "der Summe der Statistik — „Summe anpassen“ in Home Assistant ändert dort nichts. Gefunden: {namen}. Wurde der "
              "Zähler getauscht, führe den neuen als eigenes Gerät: am alten Gerät ein Stilllegungsdatum setzen und den neuen "
              "Zähler anlegen (Handbuch Einstellungen, Verbrauchszähler). Beim nächsten Tausch zählt kein Sprung, wenn du in "
              "Home Assistant für den neuen Zähler einen eigenen Sensor oder Helfer anlegst, ihn in eedc unter Datenquellen "
              "zuordnest und „Bisherige Werte bleiben“ wählst.")


class ZaehlerstandSpringtChecks:
    """Prüfung: der Zählerstand eines gespiegelten Sensors springt (Gerätetausch bei gleicher Entität)."""

    async def _check_ha_zaehlerstand_springt(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Benennt Stunden, in denen HAs Statistik einen Zählerstand-Sprung als Menge zählt — Feld, Sensor, Stunde, Menge —
        mit dem Weg in Home Assistant. Ohne Spiegel (Standalone) kein Befund."""
        from backend.services.kanal.bilanz_leser import ha_statistik_beginn
        from backend.services.snapshot.plausibility import schwelle_der_anlage_stunde_kwh

        zeilen = (await self.db.execute(text(_SQL), {"a": anlage.id})).all()
        funde = (finde(zeilen, await schwelle_der_anlage_stunde_kwh(self.db, anlage.id),
                       await ha_statistik_beginn(self.db, anlage.id)) if zeilen else [])
        if not funde:
            return []
        namen = await self._standsprung_namen(anlage.id, {f.key for f in funde})
        mengen = [f for f in funde if not f.stand]
        staende = [f for f in funde if f.stand]
        teile = [SATZ_WAS] + ([SATZ_BEGINN] if any(f.sprung.art == BEGINN for f in funde) else [])
        if mengen:
            teile.append(SATZ_MENGE.format(namen=_aufzaehlung(mengen, namen)))
        if staende:
            teile.append(SATZ_STAND.format(namen=_aufzaehlung(staende, namen)))
        return [CheckErgebnis(
            kategorie=CheckKategorie.HA_ZAEHLERSTAND_SPRINGT.value,
            # Ohne Mengen-Fund wirkt kein Handgriff in eedc: Auskunft mit Info (W-6).
            schwere=CheckSeverity.WARNING if mengen else CheckSeverity.INFO,
            meldung=(f"{len(funde)} Stunde(n), in denen ein Zählerstand in Home Assistant springt — Tag, Monat und Jahr "
                     "zählen den Sprung mit"),
            details=" ".join(teile),
            # Der Schritt nach der Berichtigung in HA (wie `ha_zaehlersprung`): Abgleich + Tag des größten Mengen-Funds.
            action=(aktion_spiegel_abgleich_tag(anlage.id, datetime.fromtimestamp(mengen[0].sprung.start_ts).date())
                    if mengen else None),
            code="ha_zaehlerstand_springt",
            werte={"stunden": len(funde), "funde": [
                {"feld": f.key, "sensor": f.sensor, "art": f.sprung.art, "stand_zaehler": f.stand,
                 "stunde": datetime.fromtimestamp(f.sprung.start_ts).isoformat(timespec="minutes"),
                 "menge": round(f.sprung.menge, 3), "einheit": f.einheit, "stand_vorher": f.sprung.stand_vorher,
                 "stand_nachher": f.sprung.stand_nachher, "mass": round(f.sprung.mass, 1)}
                for f in funde[:BEISPIELE]]},
        )]

    async def _standsprung_namen(self, anlage_id: int, keys: set) -> dict:
        """Name je Feld wie in Vorschau und Auswahl («Süddach · PV-Erzeugung», «Anlage · Netzbezug»)."""
        from backend.models.investition import Investition
        from backend.services.verwerfen_vor_quellbeginn import feld_label

        invs = {i.id: i for i in (await self.db.execute(
            select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all()}
        return {k: feld_label(k, invs) for k in keys}


__all__ = ["BEISPIELE", "ZaehlerstandSpringtChecks", "finde", "grenze_der_einheit"]

