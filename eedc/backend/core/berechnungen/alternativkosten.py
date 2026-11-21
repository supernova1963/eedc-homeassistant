"""Alternativkosten-Ersparnis: historische Komponenten-Ersparnis vs. Altanlage.

Single Source of Truth für die **historische** (bisherige) Alternativkosten-
Ersparnis, die im HA-Export und in der Aussichten-Finanzprognose in die
Jahresersparnis / ROI / Amortisation einfließt:

- **Wärmepumpe vs. Gas/Öl** — je Wärmepumpe und Monat mit Wärme die hypothetischen
  Brennstoffkosten der Altanlage minus die tatsächlichen WP-Netz-Stromkosten,
  plus das Zwölftel der fixen Zusatzkosten (Schornsteinfeger, Wartung, Grundpreis).
- **Balkonkraftwerk** — der BKW-Eigenverbrauch zum Netzbezugspreis bewertet.

Die Formeln waren an mehreren Read-Sites dupliziert (`ha_export.py`,
`aussichten/finanzen.py`) und sind eine bekannte Drift-Quelle: bei Multi-Komponenten-
Haushalten mit unterschiedlichen Parametern (zwei WPs Gas+Öl, zwei E-Autos)
rechnete der last-write-wins-Pfad falsch. Dieser Layer rechnet **per
Komponente und per Monat** und ist DB-/Service-frei (ADR-001): der Caller
übergibt bereits geladene und auf Laufzeit/Aktivität gefilterte IMD-Dicts
(``historische_inv_daten``) sowie den aufgelösten Monats-Gaspreis.

Der **E-Auto-Pfad** liegt bewusst NICHT hier: er braucht die km-anteilige
Wallbox-Pool-Attribution (`services.eauto_wirtschaftlichkeit`), die core nicht
importieren darf (Layer-Regel). Er wird im Caller resolved.
"""

from __future__ import annotations

from typing import Iterable, Optional

from backend.core.berechnungen.betriebsart_gemessen import modus_strom_zeile
from backend.core.berechnungen.waermepumpe_kennzahl import (
    heizwaerme_kwh,
    waerme_gesamt_kwh,
)
from backend.core.field_definitions import (
    get_wp_strom_kwh,
    get_wp_warmwasser_kwh,
)
from backend.core.investition_parameter import (
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
)
from backend.core.wirtschaftlichkeit_defaults import (
    WP_WIRKUNGSGRAD_GAS_DEFAULT,
    WP_WIRKUNGSGRAD_OEL_DEFAULT,
    WP_WIRKUNGSGRAD_STROM_DEFAULT,
)


# Wert von `alter_energietraeger` für „diese Wärmepumpe hat nichts ersetzt".
#
# Bis 2026-08-16 kannte das Feld nur `gas` / `oel` / `strom`, Default `gas` —
# es gab **keine** Möglichkeit zu sagen, dass gar keine Heizung ersetzt wurde.
# Damit bekam jede Wärmepumpe im **Neubau** eine Gaskessel-Ersparnis
# angerechnet, die es nie gab; dieselbe Klasse traf Split-Klimaanlagen, die nur
# kühlen. Der bisherige Ausweg war ein **Typ**-Sonderweg (`wp_art == luft_luft`
# ⇒ gar nicht bewerten) — und der beruhte auf einer falschen Annahme: Eine
# Luft-Luft-Wärmepumpe **kann** sehr wohl eine Gasheizung ersetzen (Gernot,
# 16.08.). Ob sie dafür die effizienteste Bauart ist, ist eine andere Frage und
# nicht die, die eedc hier beantwortet.
#
# Die Frage „hat dieses Gerät eine Heizung ersetzt?" hängt also an der
# **Installation**, nicht an der Bauart — deshalb ist sie ein Feld und keine
# Typ-Regel. Vorgeschichte: F2(b) im Auftrag `auftrag-n87-klima-roi-verbraucher.md`
# (02.08.), damals bewusst auf den Klima-Fall verkürzt und als **N-88** mit
# Trigger geparkt.
ERSETZT_NICHTS: str = "nichts"


def ersetzt_keine_heizung(energietraeger: Optional[str]) -> bool:
    """Hat diese Wärmepumpe laut Pflege **keine** Heizung ersetzt?

    Single Source der Frage, an der jede Alternativkosten- und
    Alternativ-CO₂-Konstruktion hängt. Wer sie mit ``True`` beantwortet bekommt,
    weist **keine** Ersparnis gegen Gas/Öl/Strom aus — auch keine anteiligen
    Zusatzkosten (Schornsteinfeger, Wartung, Grundpreis einer Anlage, die es
    nicht gibt).

    ``None`` bzw. ein ungesetztes Feld heißt bewusst **nicht** „nichts":
    Bestandsgeräte tragen den alten Default `gas`, und eine fehlende Angabe darf
    eine bisher ausgewiesene Ersparnis nicht stillschweigend abschalten
    (dieselbe Begründung wie bei `ist_luft_luft_waermepumpe`).
    """
    return energietraeger == ERSETZT_NICHTS


def alter_wirkungsgrad(energietraeger: Optional[str]) -> float:
    """Erzeugungs-Wirkungsgrad der ersetzten Altanlage je Energieträger.

    Single Source der η-Wahl, die vorher an drei Stellen als
    ``OEL if traeger == "oel" else GAS`` dupliziert war (`_wp_aggregate` hier,
    `services.wp_wirtschaftlichkeit._wp_alter_wirkungsgrad`, das WP-Aggregat in
    `api/routes/aussichten/finanzen.py`). Alle drei kannten nur Gas und Öl — die im
    Formular wählbare **Strom-Direktheizung** („Strom (Direktheizung)",
    `WaermepumpeFelder.tsx`) bekam damit stillschweigend den Gas-Kessel-Wirkungsgrad
    0,90 und wurde dadurch um gut 11 % zu teuer gerechnet (= zu hohe WP-Ersparnis).

    Eine Widerstands-/Direktheizung setzt Strom praktisch verlustfrei in Wärme um,
    deshalb **1,0**: ``waerme / 1.0`` lässt `gas_kosten_altanlage` für diesen
    Energieträger zur reinen ``waerme × preis``-Rechnung werden — genau richtig,
    denn der eingetragene Preis ist dort der Strompreis je kWh Wärme.

    Args:
        energietraeger: ``"gas"``, ``"oel"``, ``"strom"`` oder ``None``
            (unbekannt/ungesetzt → Gas als bisheriger Default).

    Returns:
        Wirkungsgrad als Faktor (0 < η ≤ 1).
    """
    if energietraeger == "oel":
        return WP_WIRKUNGSGRAD_OEL_DEFAULT
    if energietraeger == "strom":
        return WP_WIRKUNGSGRAD_STROM_DEFAULT
    return WP_WIRKUNGSGRAD_GAS_DEFAULT


def gas_kosten_altanlage(
    waerme_kwh: float, wirkungsgrad: float, gaspreis_cent: float,
) -> float:
    """Hypothetische Brennstoffkosten der fossilen Altanlage in €.

    Single Source of der drift-anfälligen Formel ``(Wärme / Wirkungsgrad) ×
    Gaspreis / 100`` — die Energiekosten, die die ersetzte Gas-/Öl-Heizung für
    eine gegebene thermische Wärmemenge verursacht hätte. Genutzt von der
    per-Monat-Aggregat-Ersparnis (hier), der per-WP-Service-Ersparnis
    (`services.wp_wirtschaftlichkeit`) sowie den HA-Export- und Prognose-Sichten.
    """
    return (waerme_kwh / wirkungsgrad) * gaspreis_cent / 100


def _wp_aggregate(parameter: Optional[dict]) -> dict:
    """Per-WP-Kennwerte (alter Preis, Wirkungsgrad, fixe Zusatzkosten/Jahr) aus
    den Investitions-Parametern — vereinheitlicht über die Defaults.

    Per-WP statt last-write-wins: bei zwei WPs mit verschiedenen Energieträgern
    (Gas + Öl) wurde sonst der Wirkungsgrad der letzten auf beide angewandt.
    """
    params = parameter or {}
    return {
        "alter_preis_cent": (
            params.get(
                PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"],
                PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"],
            ) or PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"]
        ),
        "alter_wirkungsgrad": alter_wirkungsgrad(
            params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])
        ),
        "zusatzkosten_jahr": params.get(
            PARAM_WAERMEPUMPE["ALTERNATIV_ZUSATZKOSTEN_JAHR"], 0,
        ) or 0,
    }


def berechne_wp_alternativkosten_ersparnis(
    waermepumpen: Iterable,
    historische_inv_daten: dict[tuple[int, int, int], dict],
    gaspreis_by_periode: dict[tuple[int, int], Optional[float]],
    netzbezug_preis_by_periode: dict[tuple[int, int], float],
    netzbezug_preis_fallback: float,
) -> float:
    """Bisherige WP-Ersparnis vs. Gas/Öl über alle erfassten Monate.

    Der Strompreis kommt **je Monat** herein, wie der Gaspreis daneben: Die
    Funktion summiert über die gesamte Historie, ein Skalar hätte einen
    Tarifwechsel rückwirkend über alle Jahre gezogen (ADR-002/P8). Bewusst
    zwei Pflicht-Parameter statt eines optionalen Mappings — ein Caller, der
    das Mapping vergisst, würde sonst still auf einen Einheitspreis
    zurückfallen, und genau diese stille Rückfall-Form ist die Drift-Quelle.

    Args:
        waermepumpen: Investitionen vom Typ ``waermepumpe`` (gelesen: ``.id``,
            ``.parameter``).
        historische_inv_daten: bereits auf Aktivität/Laufzeit gefilterte IMD,
            ``{(inv_id, jahr, monat): verbrauch_daten}``.
        gaspreis_by_periode: aufgelöster Monats-Gaspreis (ct/kWh) je
            ``(jahr, monat)``; ``None``/fehlend → WP-Parameter-Default.
        netzbezug_preis_by_periode: WP-Arbeitspreis (ct/kWh) je ``(jahr, monat)``
            — der Caller löst ihn über ``lade_tarife_fuer_anlage`` mit dem
            Monatsersten als Stichtag auf.
        netzbezug_preis_fallback: Arbeitspreis für Monate, die im Mapping
            fehlen (ct/kWh).

    Returns:
        Σ über alle WPs/Monate ``(gas_kosten − wp_stromkosten)`` plus die
        anteiligen fixen Zusatzkosten **je Wärmepumpe über ihre eigenen
        gezählten Monate**: ``Σ_WP zusatzkosten_jahr_WP × gezählte_Monate_WP / 12``.
        Der **ganze** WP-Strom wird zum Netztarif belastet (SOLL Wärme/Klima
        S1b) — auch der Teil aus der eigenen PV. Sein Wert steht auf der
        PV-Seite als Eigenverbrauch; ihn hier ein zweites Mal abzuziehen
        zählte dieselbe Kilowattstunde doppelt (ADR-002/P9).

    ⛔ **N-806 (21.11.2026): Sammelaufruf = Summe der Einzelaufrufe.** Bis hierher
    stand der Zusatzkosten-Term HINTER der Geräteschleife: ``Σ zusatzkosten_jahr
    aller WPs × |Vereinigung ihrer Monate| / 12``. Zwei Wärmepumpen nacheinander
    (A Januar–Juni, B Juli–Dezember, je 600 €/Jahr) trugen so je 12 Zwölftel
    statt je 6 — gemessen 1 466,65 € gegen Σ Gerätezeilen 866,64 € in Aussichten →
    Finanzen; die Zerlegung je Gerät (``finanz_zerlegung.py``) wies die Differenz
    als «Rest» aus. Jetzt zählt jede WP ihr Zwölftel nur in ihren eigenen Monaten,
    wie die Gerätezeile (``services/wp_wirtschaftlichkeit.py::wp_ersparnis_zeile``).
    """
    ersparnis = 0.0
    for wp in waermepumpen:
        # N-88/F2b: Eine WP, die nichts ersetzt hat, bringt gar nichts in diese
        # Summe ein — weder Brennstoff-Ersparnis noch die anteiligen fixen
        # Zusatzkosten (sonst zahlte der Anwender den Schornsteinfeger einer
        # Anlage, die es nie gab). Die Zusatzkosten der übrigen WPs bleiben
        # davon unberührt.
        if ersetzt_keine_heizung(
            (wp.parameter or {}).get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])
        ):
            continue
        wp_agg = _wp_aggregate(wp.parameter)
        monate_wp = 0
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id != wp.id:
                continue
            # N-379: `get_wp_warmwasser_kwh` statt Rohzugriff — an einer
            # Split-Klimaanlage gibt es die Groesse nicht, und genau hier
            # entstand aus einem Altwert die "Ersparnis vs. Gas" fuer Waerme,
            # die das Geraet nie abgegeben hat (dietmar1968, T89667 #295).
            #
            # ⛔ **N-391/D1 (14.09.2026): der Gesamtwert VOR den Summanden.**
            # Hier stand bis dahin die blosse Summe der beiden Achsen. Wer EINEN
            # Waermemengenzaehler ueber Heizung und Warmwasser fuehrt, traegt
            # seine Waerme seit WK-14b in `waerme_kwh` — und `thermisch` war
            # dann **0**. An dieser Funktion gemessen (Lage B: Waerme gesamt
            # 3000 kWh, Strom 1000 kWh, Gas 10 ct, Netz 30 ct): **-300,00 EUR**
            # statt **33,33 EUR** — keine Gas-Ersparnis, nur die Stromkosten.
            #
            # Das ist die **N-397-Klasse** (roh gelesen, wo der Layer kanonisch
            # liest) an einem **Geldpfad**: An dieser Summe haengen die
            # Aussichten, der ROI-Fortschritt und die Jahres-Ersparnis des
            # HA-Exports. `waerme_gesamt_kwh` ist die eine Regelstelle (D1);
            # `waerme_kwh` waere als dritter Summand eine Doppelzaehlung, sobald
            # jemand Gesamtzaehler **und** Aufteilung pflegt.
            thermisch = waerme_gesamt_kwh(
                daten.get("waerme_kwh"),
                heizwaerme_kwh(daten),   # N-398
                get_wp_warmwasser_kwh(daten, wp.parameter),
            )
            strom = get_wp_strom_kwh(daten, wp.parameter)
            # N-670 (Fachentscheid Master Wärme/Klima, 11.10.2026): Strom ohne Wärme (Standby) ist eine Gerätezeile
            # mit 0 € (`services/wp_wirtschaftlichkeit.py::wp_ersparnis_zeile`) — ohne Wärme kein Vergleich, also
            # weder Stromkosten noch der Zwölftel Zusatzkosten der Altanlage (die Zeile kennt ihn dort auch nicht).
            # Bis hierher zog diese Summe den Strom des Monats ab: Aussichten, ROI-Fortschritt und die
            # Jahres-Ersparnis des HA-Exports lagen unter Hub und Cockpit.
            # N-806 (21.11.2026): ein Monat mit Strom UND Wärme 0 (oder ohne erfasste Mengen) ist kein Betrieb —
            # die Gerätezeile trägt 0 € (E4d, `null_ist_kein_betrieb`) bzw. keine Zeile, also auch kein Zwölftel
            # Zusatzkosten. Bis hierher zählte er es (gemessen 55,19 € bei 662,28 €/Jahr gegen 0 € der Zeile).
            # Damit gilt für jeden Monat ohne Wärme dieselbe Regel wie im Export-Sensor je Gerät
            # (`ha_export/investition_sensoren.py::_wp_ersparnis_sensor`: `m_waerme <= 0` ⇒ übersprungen).
            if thermisch <= 0:
                continue
            # B5/X-5 (05.09.2026, Entscheid E-B 18.08.): Kühlen ersetzt keine
            # Heizung — sein Strom gehört nicht in den Vergleich. Der Monats-
            # Layer (`berechne_wp_ersparnis`) zog ihn seit dem 19.08. ab, diese
            # Jahresformel (Aussichten, Export-Jahresersparnis, ROI) nicht:
            # eine Klimaanlage senkte hier weiter ihre eigene Heiz-Ersparnis.
            strom -= min(max(modus_strom_zeile(daten).kuehlen_kwh, 0.0), max(strom, 0.0))
            g = gaspreis_by_periode.get((jahr, monat))
            monats_gaspreis = g if g is not None else wp_agg["alter_preis_cent"]
            gas_kosten = gas_kosten_altanlage(
                thermisch, wp_agg["alter_wirkungsgrad"], monats_gaspreis
            )
            monats_strompreis = netzbezug_preis_by_periode.get(
                (jahr, monat), netzbezug_preis_fallback
            )
            # S1b (13.09.2026, N-459): der GANZE Strom zum Netztarif. Bis
            # hierher stand ein fester PV-Abschlag von 50 %
            # (`WP_PV_ANTEIL_DEFAULT`) — er zog eine Kilowattstunde ab, die auf
            # der PV-Seite schon als Eigenverbrauch gutgeschrieben ist
            # (ADR-002/P9). Der am Gerät gepflegte „PV-Anteil (%)" beantwortet
            # eine Mengenfrage (N-277/N-354), keine Preisfrage.
            wp_stromkosten = strom * monats_strompreis / 100
            ersparnis += gas_kosten - wp_stromkosten
            monate_wp += 1
        # N-806: das Zwölftel je WP über IHRE gezählten Monate (je Schlüssel
        # `(inv_id, jahr, monat)` steht ein Monat genau einmal).
        ersparnis += wp_agg["zusatzkosten_jahr"] * monate_wp / 12
    return ersparnis
