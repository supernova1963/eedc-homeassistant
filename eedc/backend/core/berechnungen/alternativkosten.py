"""Alternativkosten-Ersparnis: historische Komponenten-Ersparnis vs. Altanlage.

Single Source of Truth für die **historische** (bisherige) Alternativkosten-
Ersparnis, die im HA-Export und in der Aussichten-Finanzprognose in die
Jahresersparnis / ROI / Amortisation einfließt:

- **Wärmepumpe vs. Gas/Öl** — pro erfasstem Monat die hypothetischen
  Brennstoffkosten der Altanlage minus die tatsächlichen WP-Netz-Stromkosten,
  plus anteilige fixe Zusatzkosten (Schornsteinfeger, Wartung, Grundpreis).
- **Balkonkraftwerk** — der BKW-Eigenverbrauch zum Netzbezugspreis bewertet.

Die Formeln waren an mehreren Read-Sites dupliziert (`ha_export.py`,
`aussichten.py`) und sind eine bekannte Drift-Quelle: bei Multi-Komponenten-
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

from backend.core.field_definitions import get_wp_strom_kwh
from backend.core.investition_parameter import (
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
)
from backend.core.wirtschaftlichkeit_defaults import (
    WP_PV_ANTEIL_DEFAULT,
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


def alle_ersetzen_nichts(waermepumpen: Iterable) -> bool:
    """Tragen **alle** übergebenen Wärmepumpen „nichts ersetzt"?

    Für die **anlagenweit aggregierten** Sichten (Jahresbericht-CO₂,
    Aussichten-Jahresprognose): Dort ist die Wärme bereits über alle Geräte
    summiert, eine Zuordnung je Gerät gibt es an der Stelle nicht mehr. Die
    einzige Aussage, die sich ohne Umbau sicher treffen lässt, ist deshalb die
    strenge: **erst wenn keine einzige WP etwas ersetzt hat**, entfällt der
    fossile Vergleich.

    ⚠ **Die Umkehrung ist bewusst konservativ und bleibt ungenau:** Steht neben
    einer Neubau-WP eine zweite, die eine Gasheizung ersetzt hat, wird weiterhin
    die **gesamte** Wärme verglichen — auch der Anteil, der nichts ersetzt.
    Sauber wäre eine Trennung je Gerät in der Aggregation selbst; die berührt
    Cockpit, Komponenten-Zeitreihe, Aussichten, HA-Export und den Jahresbericht
    und ist deshalb ein eigenes Paket. **So herum verschlechtert sich für
    niemanden etwas**, während die häufige Lage (eine WP, oder alle gleich
    gepflegt) korrekt wird — die per-Gerät-Pfade
    (`berechne_wp_ersparnis`, `berechne_wp_alternativkosten_ersparnis`) sind
    ohnehin exakt.

    Leere Eingabe → ``False``: keine WP ist kein „nichts ersetzt", sondern kein
    Gegenstand.
    """
    wps = list(waermepumpen)
    if not wps:
        return False
    return all(
        ersetzt_keine_heizung(
            (getattr(wp, "parameter", None) or {}).get(
                PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"]
            )
        )
        for wp in wps
    )


def alter_wirkungsgrad(energietraeger: Optional[str]) -> float:
    """Erzeugungs-Wirkungsgrad der ersetzten Altanlage je Energieträger.

    Single Source der η-Wahl, die vorher an drei Stellen als
    ``OEL if traeger == "oel" else GAS`` dupliziert war (`_wp_aggregate` hier,
    `services.wp_wirtschaftlichkeit._wp_alter_wirkungsgrad`, das WP-Aggregat in
    `api/routes/aussichten.py`). Alle drei kannten nur Gas und Öl — die im
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
        Σ über alle WPs/Monate ``(gas_kosten − wp_stromkosten_netz)`` plus die
        anteiligen fixen Zusatzkosten ``Σ zusatzkosten_jahr × erfasste_Monate / 12``.
        Der PV-Anteil am WP-Strom (``WP_PV_ANTEIL_DEFAULT``) wird nicht zum
        Netztarif belastet.
    """
    ersparnis = 0.0
    zusatzkosten_jahr_gesamt = 0.0
    monate_gezaehlt: set[tuple[int, int]] = set()
    for wp in waermepumpen:
        # N-88/F2b: Eine WP, die nichts ersetzt hat, bringt gar nichts in diese
        # Summe ein — weder Brennstoff-Ersparnis noch die anteiligen fixen
        # Zusatzkosten. Der `continue` steht VOR `zusatzkosten_jahr_gesamt`,
        # sonst zahlte der Anwender den Schornsteinfeger einer Anlage, die es
        # nie gab. Ihre Monate zählen auch nicht in `monate_gezaehlt`; die
        # Zusatzkosten der übrigen WPs bleiben davon unberührt.
        if ersetzt_keine_heizung(
            (wp.parameter or {}).get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])
        ):
            continue
        wp_agg = _wp_aggregate(wp.parameter)
        zusatzkosten_jahr_gesamt += wp_agg["zusatzkosten_jahr"]
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id != wp.id:
                continue
            thermisch = (daten.get("heizenergie_kwh", 0) or 0) + (
                daten.get("warmwasser_kwh", 0) or 0
            )
            strom = get_wp_strom_kwh(daten, wp.parameter)
            g = gaspreis_by_periode.get((jahr, monat))
            monats_gaspreis = g if g is not None else wp_agg["alter_preis_cent"]
            gas_kosten = gas_kosten_altanlage(
                thermisch, wp_agg["alter_wirkungsgrad"], monats_gaspreis
            )
            monats_strompreis = netzbezug_preis_by_periode.get(
                (jahr, monat), netzbezug_preis_fallback
            )
            wp_stromkosten_netz = (
                strom * (1.0 - WP_PV_ANTEIL_DEFAULT) * monats_strompreis / 100
            )
            ersparnis += gas_kosten - wp_stromkosten_netz
            monate_gezaehlt.add((jahr, monat))
    ersparnis += zusatzkosten_jahr_gesamt * len(monate_gezaehlt) / 12
    return ersparnis
