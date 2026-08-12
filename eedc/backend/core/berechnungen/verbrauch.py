"""Kanonische Verbrauchs-Kennzahlen (Eigenverbrauch / Autarkie / Quoten).

Single Source of Truth für die Eigenverbrauchs-/Autarkie-Formel. Die Formel war
bisher an mehreren Stellen dupliziert (cockpit/uebersicht.py, daten_checker.py,
Monatsdaten-Schreibpfad). HA-Export las stattdessen die berechneten
Legacy-Felder aus `Monatsdaten` (`eigenverbrauch_kwh` etc.) — die bei
IMD-basierten Setups leer bleiben, weil moderne Quellen in
`InvestitionMonatsdaten` schreiben. Folge: Eigenverbrauchsquote 2,2 % statt
~40 % (#304).

Definition (deckungsgleich mit cockpit/uebersicht.py + daten_checker.py):
    direktverbrauch = max(0, PV − Einspeisung − Speicher-Ladung)   [nur wenn PV>0]
    eigenverbrauch  = direktverbrauch + Speicher-Entladung + V2H-Entladung
    gesamtverbrauch = eigenverbrauch + Netzbezug

**Speicherverluste sind in keiner der drei Größen enthalten** (Gernots Frage 2026-08-12,
im Zuge einer Rainer-PN): Die Ladung wird abgezogen, die Entladung kommt dazu — gezählt
wird also, was aus dem Speicher wieder *herauskommt*, und die Differenz fällt zwischen
beiden Schritten heraus. An der Prod-Anlage nachgerechnet (Lebenszeit): PV 42.311 −
Einspeisung 25.681 − Ladung 7.675 = Direktverbrauch 8.955; + Entladung 6.461 =
Eigenverbrauch 15.416. Die 1.214 kWh Verlust (η ≈ 84 %) stehen in keiner der Zahlen.
Deshalb ist ``gesamtverbrauch_kwh`` das, was **im Haus ankam** — und darf „Hausverbrauch"
heißen.

**Warum die Netzladung hier nicht vorkommt, obwohl es sie gibt** (``SpeicherFakten.
netzladung_kwh``): Sie steckt bereits in ``speicher_ladung_kwh`` und im ``netzbezug_kwh``.
Der aus dem Netz geladene Strom wird damit einmal zu viel vom Direktverbrauch abgezogen
**und** ist einmal zu viel im Netzbezug — im ``gesamtverbrauch`` heben sich beide exakt
auf. Übrig bleibt allein, dass der ``eigenverbrauch`` um die Ladeverluste des Netzanteils
(``netzladung × (1 − η)``) zu **niedrig** liegt; die Abweichung ist konservativ und klein.
Eine Doppelzählung entsteht nicht — der wiederkehrende Verdacht ist damit an dieser Stelle
geprüft und widerlegt, nicht übersehen.

V2H (Vehicle-to-Home, E-Auto entlädt ins Haus) wird wie eine zweite Batterie
behandelt — voll als Eigenverbrauch gezählt, analog zur stationären
Speicher-Entladung (unabhängig von der Ladequelle). So bleibt die Autobatterie
gleichgestellt mit der Hausbatterie (#304-Definitionsentscheidung). Default 0.

WICHTIG: Diese Funktion rechnet nur die Formel. Das *Sourcing* (PV + Speicher
IMD-first aus `InvestitionMonatsdaten`, Einspeisung/Netzbezug als Zählerwerte
aus `Monatsdaten`) bleibt Aufgabe des Aufrufers — siehe ADR-001
(core/berechnungen). Die übrigen Leser (Aussichten, PDF) auf diesen Helper
umzustellen ist eine eigene Etappe (#304, nach v3.34).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.berechnungen.kennzahlen import (
    autarkie_prozent,
    eigenverbrauchsquote_prozent,
)


@dataclass
class VerbrauchsKennzahlen:
    """Abgeleitete Energie-Kennzahlen (kWh bzw. %)."""

    pv_erzeugung_kwh: float
    direktverbrauch_kwh: float
    eigenverbrauch_kwh: float
    gesamtverbrauch_kwh: float
    autarkie_prozent: float
    eigenverbrauchsquote_prozent: float
    direktverbrauchsquote_prozent: float


def berechne_verbrauchs_kennzahlen(
    *,
    pv_erzeugung_kwh: float,
    einspeisung_kwh: float,
    netzbezug_kwh: float,
    speicher_ladung_kwh: float = 0.0,
    speicher_entladung_kwh: float = 0.0,
    v2h_entladung_kwh: float = 0.0,
) -> VerbrauchsKennzahlen:
    """Berechnet die kanonischen Verbrauchs-Kennzahlen aus Energiemengen (kWh).

    Alle Eingaben in kWh; None-tolerant (wird als 0 behandelt). Die
    Eigenverbrauchsquote wird auf 100 % gedeckelt (Mess-Toleranz).
    ``v2h_entladung_kwh`` (E-Auto → Haus) wird wie Speicher-Entladung behandelt.
    """
    pv = pv_erzeugung_kwh or 0.0
    einspeisung = einspeisung_kwh or 0.0
    netzbezug = netzbezug_kwh or 0.0
    speicher_ladung = speicher_ladung_kwh or 0.0
    speicher_entladung = speicher_entladung_kwh or 0.0
    v2h_entladung = v2h_entladung_kwh or 0.0

    direktverbrauch = max(0.0, pv - einspeisung - speicher_ladung) if pv > 0 else 0.0
    eigenverbrauch = direktverbrauch + speicher_entladung + v2h_entladung
    gesamtverbrauch = eigenverbrauch + netzbezug

    autarkie = autarkie_prozent(eigenverbrauch, gesamtverbrauch)
    ev_quote = eigenverbrauchsquote_prozent(eigenverbrauch, pv)
    dv_quote = (direktverbrauch / pv * 100) if pv > 0 else 0.0

    return VerbrauchsKennzahlen(
        pv_erzeugung_kwh=pv,
        direktverbrauch_kwh=direktverbrauch,
        eigenverbrauch_kwh=eigenverbrauch,
        gesamtverbrauch_kwh=gesamtverbrauch,
        autarkie_prozent=autarkie,
        eigenverbrauchsquote_prozent=ev_quote,
        direktverbrauchsquote_prozent=dv_quote,
    )
