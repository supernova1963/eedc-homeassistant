"""Welcher BKW-Wert die Finanz-Zeile trägt — Erzeugung oder Rest-Eigenverbrauch.

Single Source of Truth für die **Überlappung** der beiden BKW-Eingänge einer
``FinanzMonatsZeile``. Ein Balkonkraftwerk speist hinter DENSELBEN Hauszähler
wie die Dachanlage (Layer-SoT ``erzeugung_hinter_zaehler_kwh``, v3.45.4). Seine
Erzeugung gehört deshalb in die Summe, aus der der Eigenverbrauch abgeleitet
wird — und sein selbst verbrauchter Anteil steckt dann **bereits** in dieser
Ableitung (``PV − Einspeisung − Speicherladung``).

Daraus folgt die Invariante (ADR-002/**P9**): *ein Energiefluss trägt genau
einmal zum Finanz-Netto bei*. Der separate Term ``bkw_eigenverbrauch_kwh`` ist
kein Zusatzposten, sondern ein **Ersatzträger** für den einen Fall, in dem die
Erzeugung fehlt:

===================================  ===============  =========================
Erfassung der BKW-Zeile              geht in PV-Summe  separater Term
===================================  ===============  =========================
Erzeugung (Pflichtfeld) gepflegt     Erzeugung        0 — sonst Doppelzählung
Erzeugung + Eigenverbrauch           Erzeugung        0 — sonst Doppelzählung
nur Eigenverbrauch (Datenlücke)      0                Eigenverbrauch
===================================  ===============  =========================

Warum die dritte Zeile überhaupt existiert: ``pv_erzeugung_kwh`` ist für das
Balkonkraftwerk **Pflichtfeld** und das einzige, das der Sensor-/MQTT-Pfad
schreiben kann (``KUMULATIVE_ZAEHLER_FELDER``); ``eigenverbrauch_kwh`` ist eine
optionale Verfeinerung aus manueller Pflege oder Import. Eine Zeile ohne
Erzeugung ist damit eine **Datenlücke**, keine zweite gleichberechtigte
Erfassungsform — ihre Ersparnis wäre aber sonst nirgends sichtbar, deshalb wird
sie getragen statt verworfen ([[feedback_reparatur_statt_loesch_features]]).

Vor dieser Konsolidierung wählte jede Read-Site die Kombination selbst und alle
vier wählten anders (#326-Inventur, letzte Dimension): die Aussichten zählten
den Eigenverbrauch zusätzlich zur mitgezählten Erzeugung (Doppelzählung),
Cockpit und Jahresbericht-PDF ließen die Datenlücken-Zeile ganz fallen, und der
HA-Export hielt seine Finanz-PV-Summe rein — sein Netto-Ertrags-Sensor trug die
BKW-Ersparnis dadurch gar nicht, während sie im ROI-Pfad mit einem **statischen**
Netzbezugspreis noch einmal separat gerechnet wurde (P8-Klasse).

Rein (kein DB-/Service-I/O, ADR-001). Der Aufrufer löst die Rohwerte kanonisch
auf — ``imd_typ_beitrag`` — und faltet das Ergebnis in seine eigene Form.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BkwFinanzBeitrag:
    """Aufgeteilter Finanz-Beitrag EINER BKW-Monatszeile (kWh).

    ``erzeugung_kwh`` gehört in ``FinanzMonatsZeile.pv_erzeugung_kwh``,
    ``rest_eigenverbrauch_kwh`` in ``FinanzMonatsZeile.bkw_eigenverbrauch_kwh``.
    Genau einer der beiden Werte ist je Zeile besetzt.
    """

    erzeugung_kwh: float
    rest_eigenverbrauch_kwh: float


def bkw_finanz_beitrag(
    *,
    erzeugung_kwh: float | None,
    eigenverbrauch_kwh: float | None,
) -> BkwFinanzBeitrag:
    """Entscheidet je (BKW, Monat), welcher Wert die Finanz-Zeile trägt.

    Args:
        erzeugung_kwh: kanonisch aufgelöste BKW-Erzeugung des Monats
            (``ImdTypBeitrag.bkw_erzeugung``) — None/0 = nicht erfasst.
        eigenverbrauch_kwh: gemessener BKW-Eigenverbrauch des Monats
            (``ImdTypBeitrag.bkw_eigenverbrauch``).

    Returns:
        ``BkwFinanzBeitrag`` — bei erfasster Erzeugung trägt sie den Beitrag und
        der Rest-Eigenverbrauch ist 0 (er steckt schon in der Ableitung); ohne
        Erzeugung trägt der gemessene Eigenverbrauch allein.
    """
    erzeugung = erzeugung_kwh or 0.0
    if erzeugung > 0:
        return BkwFinanzBeitrag(erzeugung_kwh=erzeugung, rest_eigenverbrauch_kwh=0.0)
    return BkwFinanzBeitrag(
        erzeugung_kwh=0.0,
        rest_eigenverbrauch_kwh=eigenverbrauch_kwh or 0.0,
    )


@dataclass(frozen=True)
class BkwEigenverbrauchsAnteil:
    """Der selbst verbrauchte Anteil EINES Balkonkraftwerks in einem Monat.

    ``bewertbar`` trennt „0 kWh gemessen" von „nicht ableitbar" (ADR-002/**P4**):
    ohne Zählerzeile gibt es keine Hausbilanz, aus der ein Anteil folgen könnte.
    Eine 0 wäre dort eine Aussage, die niemand belegen kann.
    """

    kwh: float
    bewertbar: bool
    quelle: str


def bkw_eigenverbrauch_anteil(
    *,
    bkw_erzeugung_kwh: float | None,
    bkw_eigenverbrauch_gemessen_kwh: float | None,
    erzeugung_hinter_zaehler_kwh: float | None,
    eigenverbrauch_gesamt_kwh: float | None,
    hat_zaehlerzeile: bool,
) -> BkwEigenverbrauchsAnteil:
    """Was EIN Balkonkraftwerk in EINEM Monat selbst verbraucht hat.

    Die Komponenten-Sicht braucht diese Zahl, die Finanz-Zeile nicht: dort geht
    die BKW-Erzeugung in die PV-Summe ein und der Eigenverbrauch fällt als
    Ableitung der **ganzen** Anlage an (``bkw_finanz_beitrag`` oben). Ein
    Komponenten-Hub muss den Beitrag aber **einem Gerät** zuordnen können —
    sonst steht dort 0 € Ersparnis, während das Cockpit dieselbe Energie sehr
    wohl bewertet (Befund **F-4** der Drift-Inventur 2026-07-31).

    Die Zuordnung ist eine Entscheidung, keine Messung, und sie ist hier
    festgelegt statt in der Route: **anteilig an der Erzeugung hinter dem
    Zähler.** Ein Balkonkraftwerk, das 10 % der Erzeugung liefert, trägt 10 %
    des Eigenverbrauchs. Das ist dieselbe Annahme, die der Netzpunkt selbst
    macht — an EINEM Zähler ist nicht unterscheidbar, welches Modul die
    verbrauchte Kilowattstunde geliefert hat.

    Args:
        bkw_erzeugung_kwh: Erzeugung **dieses** BKW im Monat
            (``ImdTypBeitrag.bkw_erzeugung``).
        bkw_eigenverbrauch_gemessen_kwh: gemessener EV **dieses** BKW; trägt
            allein, wenn die Erzeugung fehlt (die Datenlücke aus
            ``bkw_finanz_beitrag``).
        erzeugung_hinter_zaehler_kwh: Erzeugung der ganzen Anlage hinter dem
            Hauszähler im Monat (``ErzeugungFakten.hinter_zaehler_kwh``).
        eigenverbrauch_gesamt_kwh: Eigenverbrauch der ganzen Anlage im Monat
            (``VerbrauchsKennzahlen.eigenverbrauch_kwh``).
        hat_zaehlerzeile: ob es für den Monat eine ``Monatsdaten``-Zeile gibt.

    Returns:
        ``BkwEigenverbrauchsAnteil`` mit ``quelle`` ∈ {``"gemessen"``,
        ``"anteilig"``, ``"nicht_bewertbar"``}.
    """
    erzeugung = bkw_erzeugung_kwh or 0.0

    # Datenlücke: nur der Eigenverbrauch ist gepflegt. Dann ist er die Messung
    # selbst und braucht keine Zuordnung — derselbe Ersatzträger wie in
    # `bkw_finanz_beitrag`, damit beide Sichten dieselbe Zeile gleich lesen.
    if erzeugung <= 0:
        gemessen = bkw_eigenverbrauch_gemessen_kwh or 0.0
        return BkwEigenverbrauchsAnteil(
            kwh=gemessen, bewertbar=gemessen > 0, quelle="gemessen"
        )

    # Ohne Zählerzeile gibt es keine Einspeisung und damit keine Bilanz, aus der
    # ein Eigenverbrauch folgen könnte. Die ganze Erzeugung als Eigenverbrauch
    # auszuweisen wäre die P4-Verletzung, die #304 im Cockpit korrigiert hat.
    hinter_zaehler = erzeugung_hinter_zaehler_kwh or 0.0
    if not hat_zaehlerzeile or hinter_zaehler <= 0:
        return BkwEigenverbrauchsAnteil(
            kwh=0.0, bewertbar=False, quelle="nicht_bewertbar"
        )

    anteil = min(1.0, erzeugung / hinter_zaehler)
    return BkwEigenverbrauchsAnteil(
        kwh=max(0.0, (eigenverbrauch_gesamt_kwh or 0.0) * anteil),
        bewertbar=True,
        quelle="anteilig",
    )
