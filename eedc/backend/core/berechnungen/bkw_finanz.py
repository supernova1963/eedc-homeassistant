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
