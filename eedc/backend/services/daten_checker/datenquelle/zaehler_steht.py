"""Daten-Checker — PV-Zähler steht (N-662, Entscheid Gernot/Master 10.10.2026).

**Warum es das gibt.** Ein eingefrorener PV-Zähler (der Sensor meldet weiter, aber sein Stand bewegt sich nicht) ist
von einer gemessenen 0 nicht zu unterscheiden — eedc rechnet ihn als „keine Erzeugung". Steht dabei die Einspeisung
nicht still, ergibt die Tagesbilanz einen Widerspruch, den die Anzeige ehrlich zeigt (gemessen an N-662: PV 0,
Einspeisung 3,5, Netzbezug 3,6 ⇒ Gesamtverbrauch 0,1 ⇒ Autarkie −3500 %). Entschieden ist: **die Anzeige bleibt** (das
Symptom bleibt sichtbar, kein Klemmen, kein „—"), diese Kategorie **benennt die Ursache**.

**Die Regel (eng, Entscheid Master 10.10.2026 — Option A):** der **Anlagenzähler** (``basis:pv_gesamt``) hat über
mindestens ``STEHT_MIN_TAGE`` volle Tage kein Δ (< ``STEHT_DELTA_KWH`` je Tag), während im selben Zeitraum die
**Einspeisung** um mehr als die Entladung der Speicher plus die Erzeugung der Balkonkraftwerke mit eigenem Kanal plus
``EINSPEISUNG_REST_KWH`` wächst — oder die **String-Zähler** um mehr als ``STRINGS_KWH_JE_TAG`` je Tag (er misst sie
mit). Ein einzelner String-Zähler wird **nicht** geprüft (Option C zurückgenommen): steht ein String, während die
übrigen erzeugen, sind Teilbeschattung und Teilschnee richtige Datenlagen.

**Was bewusst keine Regel ist** (richtige Datenlagen, kein Fehlalarm — Halt der Bau-Session K2): ein stehender
Einspeisezähler bei wachsender PV (Nulleinspeisung, Winter mit 100 % Eigenverbrauch), ein stehender Netzbezug
(autarke Tage mit Speicher), ein stehender PV-Zähler bei wachsendem Netzbezug (Schnee). ``HANDBUCH_BEDIENUNG`` „Gemessen
0 ist 0" beschreibt die ersten beiden ausdrücklich als richtig. Ein Speicher, der ins Netz entlädt, während die PV
nichts liefert, ist durch den Abzug der Entladung gedeckt; ohne Entladungs-Kanal eines Speichers wird die
Einspeisung gar nicht als Gegengröße genommen (sie wäre dann nicht zu erklären).

Gelesen werden die Kanäle (über ``kanal/bilanz_leser.tagesdeltas`` → ``kanal/lesen.reihe_stapel``) der letzten ``STEHT_FENSTER_TAGE`` abgeschlossenen Tage im
Tagesfenster der Kanal-Schicht (``kanal/fenster.tagesfenster`` — seit HA-Bauform S4 der Kalendertag, dasselbe wie Cockpit → Tag
an einem Kanal-Tag); ein Tag zählt nur bei voller Abdeckung. ⛔ Kein Reparatur-Knopf: die Antwort liegt am Sensor in Home Assistant bzw. am MQTT-Topic.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from backend.core.zahlenformat import fmt_datum, fmt_zahl
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

#: So viele volle Tage in Folge ohne Δ, bevor ein Zähler als „steht" gilt — ein einzelner Tag ohne Erzeugung ist im
#: Winter normal, drei mit wachsender Gegengröße nicht.
STEHT_MIN_TAGE = 3
#: Unter diesem Δ je Tag (kWh) steht ein Zähler — die Auflösung üblicher Zähler liegt bei 0,01 kWh.
STEHT_DELTA_KWH = 0.01
#: So viele abgeschlossene Tage rückwärts werden geprüft (ein Monat — die Tage, die eine Monatssicht zeigt).
STEHT_FENSTER_TAGE = 31
#: Anlagenzähler gegen Einspeisung: so viel mehr als Speicher-Entladung + Balkonkraftwerke muss eingespeist sein.
EINSPEISUNG_REST_KWH = 1.0
#: Anlagenzähler gegen die String-Zähler: so viel müssen sie je Tag des Zeitraums im Mittel erzeugen.
STRINGS_KWH_JE_TAG = 0.5

ANLAGENZAEHLER_KEY = "basis:pv_gesamt"
EINSPEISUNG_KEY = "basis:einspeisung"


def _pv_key(inv_id: int) -> str:
    return f"inv:{inv_id}:pv_erzeugung_kwh"


def _entladung_key(inv_id: int) -> str:
    return f"inv:{inv_id}:entladung_kwh"


def _laeufe(steht: list[bool]) -> list[tuple[int, int]]:
    """Läufe ``(a, b)`` (Indizes inklusive) aufeinanderfolgender ``True`` mit mindestens ``STEHT_MIN_TAGE`` Länge."""
    out, a = [], None
    for i, s in enumerate(steht + [False]):
        if s and a is None:
            a = i
        elif not s and a is not None:
            if i - a >= STEHT_MIN_TAGE:
                out.append((a, i - 1))
            a = None
    return out


def _summe(deltas: Optional[list[Optional[float]]], a: int, b: int) -> Optional[float]:
    """Σ Δ über die Tage ``a…b`` — ``None``, wenn ein Tag nicht voll gedeckt ist (dann keine Aussage)."""
    if deltas is None:
        return None
    teil = deltas[a:b + 1]
    if any(d is None for d in teil):
        return None
    return sum(teil)


class ZaehlerStehtChecks:
    """Prüfung: der Anlagenzähler steht, obwohl Einspeisung bzw. Strings wachsen (N-662)."""

    async def _check_pv_zaehler_steht(self, anlage: Anlage) -> list[CheckErgebnis]:
        from backend.services.kanal.bilanz_leser import tagesdeltas

        invs = list(getattr(anlage, "investitionen", None) or [])
        bkw_ids = {i.id for i in invs if i.typ == "balkonkraftwerk"}
        # Strings = Module auf dem Dach (Gegengröße). Die Modul-Kinder eines Balkonkraftwerks (N-266) gehören zu ihm:
        # sie zählen beim Abzug von der Einspeisung, nicht als String.
        module = {i.id: i for i in invs if i.typ == "pv-module" and i.parent_investition_id not in bkw_ids}
        kinder = {b: [i.id for i in invs if i.typ == "pv-module" and i.parent_investition_id == b] for b in bkw_ids}
        speicher_alle = [i for i in invs if i.typ == "speicher"]

        keys = ([ANLAGENZAEHLER_KEY, EINSPEISUNG_KEY] + [_pv_key(i) for i in module]
                + [_pv_key(i) for b, ks in kinder.items() for i in [b, *ks]]
                + [_entladung_key(s.id) for s in speicher_alle])
        td = await tagesdeltas(self.db, anlage.id, keys, STEHT_FENSTER_TAGE)
        tage, delta = td.tage, td.delta
        if len(tage) < STEHT_MIN_TAGE or ANLAGENZAEHLER_KEY not in delta:
            return []
        speicher = [s.id for s in speicher_alle if s.ist_aktiv_an(tage[-1])]
        # Je Balkonkraftwerk EIN Abzug: sein eigener Kanal, sonst die Kanäle seiner Kinder — nie beide (kein Doppel).
        bkws = [k for b, ks in kinder.items()
                for k in ([_pv_key(b)] if _pv_key(b) in delta else [_pv_key(i) for i in ks])]

        steht = [d is not None and abs(d) < STEHT_DELTA_KWH for d in delta[ANLAGENZAEHLER_KEY]]
        for a, b in reversed(_laeufe(steht)):
            gegen = self._gegengroessen(a, b, tage, delta, module, bkws, speicher)
            if gegen:
                return [self._steht_befund(td.entitaet.get(ANLAGENZAEHLER_KEY), tage, a, b, gegen)]
        return []

    def _gegengroessen(self, a: int, b: int, tage: list[date], delta: dict, module: dict,
                       bkws: list[str], speicher: list[int]) -> dict[str, float]:
        """Die Gegengrößen, die im Lauf ``a…b`` wachsen — ``{"einspeisung": kWh, "strings": kWh}`` (leer = keine)."""
        n = b - a + 1
        gegen: dict[str, float] = {}
        # Strings: aktiv über den ganzen Lauf und voll gedeckt — der Anlagenzähler misst sie mit.
        summen = [
            _summe(delta.get(_pv_key(i)), a, b) for i, inv in module.items()
            if _pv_key(i) in delta and all(inv.ist_aktiv_an(t) for t in tage[a:b + 1])
        ]
        strings = sum(s for s in summen if s is not None)
        if strings > STRINGS_KWH_JE_TAG * n:
            gegen["strings"] = strings
        einsp = _summe(delta.get(EINSPEISUNG_KEY), a, b)
        entl = [_summe(delta.get(_entladung_key(i)), a, b) for i in speicher]
        bkw = [_summe(delta.get(k), a, b) for k in bkws]
        # Ein Speicher ohne Entladungs-Kanal erklärt Einspeisung, die eedc nicht kennt — dann keine Aussage.
        if einsp is not None and all(e is not None for e in entl):
            abzug = sum(entl) + sum(x for x in bkw if x is not None)
            if einsp > abzug + EINSPEISUNG_REST_KWH:
                gegen["einspeisung"] = einsp
        return gegen

    def _steht_befund(self, entitaet: Optional[str], tage: list[date], a: int, b: int,
                      gegen: dict[str, float]) -> CheckErgebnis:
        rolle = "Anlagenzähler „PV gesamt“"
        zaehler = f"{entitaet} ({rolle})" if entitaet else rolle
        if "einspeisung" in gegen and "strings" in gegen:
            obwohl = "obwohl Einspeisung und Strings wachsen"
        elif "einspeisung" in gegen:
            obwohl = "obwohl die Einspeisung wächst"
        else:
            obwohl = "obwohl die Strings wachsen"
        bis_heute = b == len(tage) - 1
        wann = (f"steht seit {fmt_datum(tage[a])}" if bis_heute
                else f"stand vom {fmt_datum(tage[a])} bis {fmt_datum(tage[b])}")
        n = b - a + 1
        mengen = []
        if "einspeisung" in gegen:
            mengen.append(f"Einspeisung {fmt_zahl(gegen['einspeisung'], 1)} kWh")
        if "strings" in gegen:
            mengen.append(f"Strings {fmt_zahl(gegen['strings'], 1)} kWh")
        return CheckErgebnis(
            kategorie=CheckKategorie.PV_ZAEHLER_STEHT.value,
            schwere=CheckSeverity.WARNING,
            meldung=(f"PV-Zähler {zaehler} {wann}, {obwohl} — Tag und Monat zeigen deshalb unplausible Werte; "
                     "Sensor in Home Assistant prüfen"),
            details=(
                f"Über {n} volle Tage hat sich der Stand des Anlagenzählers nicht bewegt, während im selben Zeitraum "
                f"{' und '.join(mengen)} dazukamen. Ohne Erzeugung kann das nicht sein — meist liefert der Sensor "
                "einen eingefrorenen Wert (Integration hängt, Gerät nicht erreichbar, Zähler zurückgesetzt). eedc "
                "rechnet in diesen Tagen mit „keine Erzeugung“; deshalb zeigen Cockpit → Tag und Monat z. B. eine "
                "negative Autarkie. Prüfe den Sensor in Home Assistant (bzw. das MQTT-Topic); liefert er wieder "
                "Werte, zählen die folgenden Tage richtig. Eine Nulleinspeisung, autarke Tage oder Schnee auf den "
                "Modulen lösen diese Meldung nicht aus."
            ),
            link="/einstellungen/datenquellen",
        )

__all__ = [
    "EINSPEISUNG_REST_KWH", "STEHT_DELTA_KWH", "STEHT_FENSTER_TAGE", "STEHT_MIN_TAGE", "STRINGS_KWH_JE_TAG",
    "ZaehlerStehtChecks",
]
