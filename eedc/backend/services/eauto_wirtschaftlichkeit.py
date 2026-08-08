"""E-Auto/Wallbox-Wirtschaftlichkeit — Single Source of Truth.

Anlass: Drift-Audit Domäne A2 (`docs/archive/INVENTUR-DRIFT-AUDIT.md`).
Cockpit/Monatsbericht hatten 7 L/100km und 1,80 €/L hartcodiert, ignorierten
User-gepflegte Werte — User sahen 7-9% falsche Ersparnis vs. Aussichten/PDF.

Vorher: vier Code-Pfade, zwei verschiedene Defaults (7 vs. 7,5 L; 1,80 vs.
1,65 €/L). Nachher: ein Helper mit kanonischen Defaults aus
`PARAM_E_AUTO_DEFAULTS`.

Formel:
    benzin_kosten  = (km / 100) × verbrauch_l_100km × benzinpreis_euro
    strom_kosten   = ladung_netz_kwh × wallbox_strompreis_cent / 100 + ladung_extern_euro
    fossile_kosten = (km_verbrenner / 100) × eigener_verbrauch_l_100km × benzinpreis_euro
    ersparnis      = benzin_kosten - strom_kosten - fossile_kosten

`fossile_kosten` ist der Plug-in-Hybrid-Anteil (#331) und ohne gepflegtes
`eigener_verbrauch_l_100km` **exakt 0** — für ein BEV ändert sich keine Zahl.
Die Aufteilung der Kilometer liegt in `core/berechnungen/phev_anteil.py`, damit
die Prognose-Achse (`core/calculations.py`) dieselbe Funktion ruft.

Verbrauch: aus `params.vergleich_verbrauch_l_100km`, Default 7,5 L/100km.
Benzinpreis: monatlicher Override (Monatsdaten.kraftstoffpreis_euro) >
             params.benzinpreis_euro > Default 1,65 €/L.
Strompreis: **der zum jeweiligen Monat gültige** separate Wallbox-Tarif >
            allgemeiner Tarif (ADR-002/P8, seit 2026-08-08 über
            `aufgeloester_strompreis_cent`). Vorher war die Preisachse die
            letzte, die noch vier verschiedene Formen hatte, während die
            Benzinachse längst monatsgenau war — F-18/N-181.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from backend.core.berechnungen.phev_anteil import teile_fahrleistung
from backend.core.field_definitions import (
    get_eauto_ladung_kwh,
    get_emob_pv_netz_kwh,
)
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
)
from backend.core.wirtschaftlichkeit_defaults import (
    BENZIN_PREIS_DEFAULT_EURO_L,
    BENZIN_VERBRAUCH_DEFAULT_L_100KM,
)


@dataclass
class EAutoErsparnisErgebnis:
    """Ergebnis der E-Auto-Ersparnis-Berechnung vs. Verbrenner.

    ``fossile_kosten_euro`` ist die **real angefallene** Tankrechnung eines
    Plug-in-Hybrids (#331) — ein eigenes Feld, damit die Anzeige sie **benennen**
    kann statt sie in der Ersparnis verschwinden zu lassen. Bei einem BEV (kein
    ``eigener_verbrauch_l_100km`` gepflegt) ist sie 0, und alle anderen Felder
    tragen dieselben Zahlen wie vor #331.
    """
    ersparnis_euro: float
    benzin_kosten_euro: float
    strom_kosten_euro: float
    # Diagnostik: welche Werte wurden tatsächlich verwendet?
    verwendeter_verbrauch_l_100km: float
    verwendeter_benzinpreis_euro: float
    # #331 (PHEV) — additiv ans Ende, damit die positionalen Frühausstiege
    # unten und alle Bestandsaufrufer unverändert gültig bleiben.
    fossile_kosten_euro: float = 0.0
    km_elektrisch: float = 0.0
    km_verbrenner: float = 0.0
    #: "gemessen" | "prozent" | "unbestimmt" — s. `berechnungen/phev_anteil.py`
    anteil_quelle: str = "unbestimmt"
    #: F-18/ADR-002/P8: der tatsächlich angewendete Netzbezugspreis in ct/kWh —
    #: bei einer Periode mit Tarifwechsel der mengengewichtete Ø, sonst der
    #: übergebene Skalar. Diagnostik-Feld: es macht die Preisachse in Tests und
    #: in der `berechnung`-Zeile des HA-Exports **sichtbar**, statt sie im
    #: Ergebnis verschwinden zu lassen (genau daran driftete sie unbemerkt).
    verwendeter_strompreis_cent: float = 0.0


def _vergleich_verbrauch(eauto_parameter: Optional[dict]) -> float:
    """Liest Benzin-Vergleichsverbrauch aus params, sonst kanon. Default 7,5."""
    if eauto_parameter is None:
        return BENZIN_VERBRAUCH_DEFAULT_L_100KM
    return eauto_parameter.get(
        PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"],
        PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
    ) or BENZIN_VERBRAUCH_DEFAULT_L_100KM


def eigener_verbrauch_l_100km(eauto_parameter: Optional[dict]) -> Optional[float]:
    """Der REAL getankte Verbrauch — ``None``, wenn nicht gepflegt.

    ⚠ **Hier gibt es bewusst keinen Default** (Entscheidung 3 des Konzepts): das
    gesetzte Feld *ist* die Aussage „dieses Fahrzeug hat einen Verbrenner". Ein
    Fallback-Wert würde aus jedem Bestands-BEV einen Hybrid machen und Zahlen
    bei Anwendern bewegen, die von #331 gar nicht betroffen sind.

    Nicht zu verwechseln mit ``_vergleich_verbrauch`` — das ist der *fiktive*
    Vergleichs-Benziner mit sieben Produktions-Lesern.
    """
    if not eauto_parameter:
        return None
    wert = eauto_parameter.get(PARAM_E_AUTO["EIGENER_VERBRAUCH_L_100KM"])
    try:
        wert = float(wert) if wert is not None else None
    except (TypeError, ValueError):
        return None
    return wert if wert and wert > 0 else None


def _fahranteil_prozent(eauto_parameter: Optional[dict]) -> Optional[float]:
    """Gepflegter elektrischer Fahranteil in % — ``None``, wenn nicht gepflegt."""
    if not eauto_parameter:
        return None
    wert = eauto_parameter.get(PARAM_E_AUTO["ELEKTRISCHER_FAHRANTEIL_PROZENT"])
    try:
        return float(wert) if wert is not None else None
    except (TypeError, ValueError):
        return None


def _verbrauch_kwh_100km(eauto_parameter: Optional[dict]) -> float:
    """Fahrzeug-Kennwert kWh/100 km (Default 18) — Umrechner kWh → km."""
    if not eauto_parameter:
        return float(PARAM_E_AUTO_DEFAULTS["verbrauch_kwh_100km"])
    return float(
        eauto_parameter.get(
            PARAM_E_AUTO["VERBRAUCH_KWH_100KM"],
            PARAM_E_AUTO_DEFAULTS["verbrauch_kwh_100km"],
        )
        or PARAM_E_AUTO_DEFAULTS["verbrauch_kwh_100km"]
    )


def _benzinpreis_default(eauto_parameter: Optional[dict]) -> float:
    """Liest Benzinpreis-Default aus params, sonst kanon. 1,65 €/L."""
    if eauto_parameter is None:
        return BENZIN_PREIS_DEFAULT_EURO_L
    return eauto_parameter.get(
        PARAM_E_AUTO["BENZINPREIS_EURO"],
        PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"],
    ) or BENZIN_PREIS_DEFAULT_EURO_L


@dataclass
class BenzinpreisAufloesung:
    """Aufgelöster Benzinpreis für eine Berechnung + Quelle für Diagnostik."""
    preis_euro: float
    quelle: str  # "slider" | "parameter" | "monatsdaten" | "default"


def km_gewichtete_eauto_params(
    *,
    eauto_params_und_km: Iterable[tuple[Optional[dict], float]],
) -> tuple[float, float]:
    """km-gewichtetes Mittel von `vergleich_verbrauch_l_100km` und
    `benzinpreis_euro` über mehrere E-Autos.

    Bei Anlagen mit nur einem E-Auto = dessen Wert (kein Verhaltens-
    Unterschied). Bei mehreren E-Autos mit unterschiedlichen Parametern
    gewichtet nach gefahrenen km. Ersetzt das verbreitete `for ea: …` mit
    last-write-wins-Variable, das bei zwei E-Autos den letzten gewann.

    Args:
        eauto_params_und_km: Iterable von `(inv.parameter, km_im_zeitraum)`.
            E-Autos mit `km <= 0` werden ignoriert. Bei leerer Eingabe oder
            ausschließlich km-0-Einträgen liefert der Helper die kanonischen
            Defaults zurück.

    Returns:
        `(vergleich_l_100km, benzinpreis_default_euro)` — beide km-gewichtet.
    """
    eintraege = [
        (km, params or {})
        for params, km in eauto_params_und_km
        if km is not None and km > 0
    ]
    if not eintraege:
        return (
            float(PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"]),
            float(PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"]),
        )
    km_sum = sum(km for km, _ in eintraege)
    vergleich = sum(
        km * (
            p.get(PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"])
            or PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"]
        )
        for km, p in eintraege
    ) / km_sum
    benzinpreis = sum(
        km * (
            p.get(PARAM_E_AUTO["BENZINPREIS_EURO"])
            or PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"]
        )
        for km, p in eintraege
    ) / km_sum
    return float(vergleich), float(benzinpreis)


def fossil_getankte_liter(
    *,
    km_je_fahrzeug: dict[int, float],
    fahrverbrauch_je_fahrzeug: Optional[dict[int, float]] = None,
    params_je_fahrzeug: Optional[dict[int, Optional[dict]]] = None,
) -> float:
    """Σ der **real getankten** Liter über die Plug-in-Hybride eines Zeitraums.

    Gegenstück zur km-gewichteten Vergleichsrechnung (`km_gewichtete_eauto_params`)
    und der einzige Weg, auf dem eine CO₂-Sicht an den fossilen Anteil kommt:
    die Menge wird **je Fahrzeug** mit DESSEN Parametern gebildet, weil ein
    Haushalt ein BEV und einen PHEV nebeneinander fahren kann (G20-2-Linie).

    Fahrzeuge ohne gepflegtes `eigener_verbrauch_l_100km` tragen 0 bei — für
    eine reine BEV-Anlage ist das Ergebnis exakt 0 und keine CO₂-Zahl bewegt
    sich (#331, Entscheidung 3).
    """
    verbrauch = fahrverbrauch_je_fahrzeug or {}
    params = params_je_fahrzeug or {}
    liter = 0.0
    for inv_id, km in km_je_fahrzeug.items():
        if not km or km <= 0:
            continue
        p = params.get(inv_id)
        eigener = eigener_verbrauch_l_100km(p)
        if eigener is None:
            continue
        anteil = teile_fahrleistung(
            km_gefahren=km,
            fahrverbrauch_kwh=verbrauch.get(inv_id),
            verbrauch_kwh_100km=_verbrauch_kwh_100km(p),
            anteil_prozent=_fahranteil_prozent(p),
        )
        liter += anteil.km_verbrenner / 100 * eigener
    return liter


def resolve_eauto_benzinpreis(
    *,
    query_override: Optional[float],
    eauto_parameter: Optional[dict],
    letzter_monats_benzinpreis: Optional[float],
) -> BenzinpreisAufloesung:
    """Auflösungs-Kette für annuelle E-Auto-ROI-Berechnung (`get_roi_dashboard`).

    Anders als die periodische Ersparnis (`berechne_eauto_ersparnis_periode`)
    rechnet ROI mit Jahresfahrleistung × einmaligem Preis. Reihenfolge:

    1. **Query-Override** (ROI-Slider): bewusste User-Eingabe, gilt für alle E-Autos.
    2. **`inv.parameter['benzinpreis_euro']`**: per-Investition gepflegter Wert.
    3. **Letzter `Monatsdaten.kraftstoffpreis_euro`** (EU Weekly Oil Bulletin):
       aktueller Marktpreis aus der Realität.
    4. `PARAM_E_AUTO_DEFAULTS['benzinpreis_euro']` (1,65 €) als letzter Fallback.

    Vorher las `get_roi_dashboard` nur den Query-Param (Default 1,85 €) und
    ignorierte die per-Investition gespeicherten Werte — gleiche Bug-Klasse
    wie der v3.25.0-Fix für `jahresfahrleistung_km` etc., aber für
    `benzinpreis_euro` damals vergessen.
    """
    if query_override is not None:
        return BenzinpreisAufloesung(float(query_override), "slider")
    if eauto_parameter is not None:
        param_preis = eauto_parameter.get(PARAM_E_AUTO["BENZINPREIS_EURO"])
        if param_preis is not None:
            return BenzinpreisAufloesung(float(param_preis), "parameter")
    if letzter_monats_benzinpreis is not None:
        return BenzinpreisAufloesung(float(letzter_monats_benzinpreis), "monatsdaten")
    return BenzinpreisAufloesung(
        float(PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"]), "default",
    )


def letzter_kraftstoffpreis_aus_lookup(
    lookup: dict[tuple[int, int], Optional[float]],
) -> Optional[float]:
    """Letzter nicht-leerer `kraftstoffpreis_euro` aus dem Monatsdaten-Lookup.

    Iteriert in absteigender Reihenfolge (jüngster Monat zuerst) und liefert
    den ersten nicht-None Preis. Wird als Hinweis-Wert (Slider-Placeholder)
    und als Stufe 3 der `resolve_eauto_benzinpreis`-Kette genutzt.
    """
    if not lookup:
        return None
    for (_, _), preis in sorted(lookup.items(), reverse=True):
        if preis is not None:
            return float(preis)
    return None


def berechne_eauto_ersparnis(
    *,
    km_gefahren: float,
    ladung_netz_kwh: float,
    ladung_extern_euro: float,
    wallbox_strompreis_cent: float,
    eauto_parameter: Optional[dict] = None,
    monats_benzinpreis_euro: Optional[float] = None,
    fahrverbrauch_kwh: Optional[float] = None,
) -> EAutoErsparnisErgebnis:
    """Berechnet E-Auto-Ersparnis vs. Verbrenner.

    Args:
        km_gefahren: Kilometer im Zeitraum
        ladung_netz_kwh: Heim-Netzladung in kWh (PV-Ladung ist kostenlos und
            wird hier ignoriert; wer das anders modelliert, übergibt die
            Gesamtladung als netz-Anteil)
        ladung_extern_euro: tatsächliche Kosten externer Ladevorgänge in €
        wallbox_strompreis_cent: Strompreis für Heim-Netzladung in ct/kWh
            (separater Wallbox-Tarif oder allgemeiner Tarif als Fallback)
        eauto_parameter: `Investition.parameter`-Dict für das E-Auto.
            Wird genutzt für Vergleichsverbrauch und Default-Benzinpreis.
        monats_benzinpreis_euro: Optionaler monatlicher Benzinpreis-Override
            aus `Monatsdaten.kraftstoffpreis_euro`. Hat Vorrang vor Param-Default.
        fahrverbrauch_kwh: **Explizit** gepflegter elektrischer Fahrverbrauch
            desselben Zeitraums (#331). Nur für die PHEV-Aufteilung; niemals
            über `get_eauto_ladung_kwh` beschaffen — der fällt auf dasselbe
            doppelt belegte Feld zurück und läse eine Heimladung als
            Fahrverbrauch.

    Returns:
        EAutoErsparnisErgebnis mit Ersparnis, Komponenten und Diagnostik.
    """
    if km_gefahren <= 0:
        return EAutoErsparnisErgebnis(
            0.0, 0.0, 0.0,
            BENZIN_VERBRAUCH_DEFAULT_L_100KM,
            BENZIN_PREIS_DEFAULT_EURO_L,
        )

    verbrauch_l_100km = _vergleich_verbrauch(eauto_parameter)

    if monats_benzinpreis_euro is not None:
        benzinpreis_euro = monats_benzinpreis_euro
    else:
        benzinpreis_euro = _benzinpreis_default(eauto_parameter)

    # Die Vergleichsfrage bleibt über ALLE Kilometer gestellt (Entscheidung 5):
    # sonst verglichen wir ein Auto mit einem halben Auto.
    benzin_kosten = (km_gefahren / 100) * verbrauch_l_100km * benzinpreis_euro
    strom_kosten = max(0.0, ladung_netz_kwh) * wallbox_strompreis_cent / 100 + ladung_extern_euro

    # #331: die real getankte Rechnung des Verbrenner-Anteils steht als eigene
    # Kostenposition daneben. Ohne gepflegtes `eigener_verbrauch_l_100km` ist
    # sie 0 und die Ersparnis exakt die von vorher.
    #
    # ⚠ **Ohne dieses Feld wird gar nicht erst aufgeteilt**, statt nur die
    # Kosten auf 0 zu setzen: sonst meldete ein BEV mit lückenhaft gepflegtem
    # Fahrverbrauch einen „Verbrenner-Anteil" von mehreren hundert Kilometern —
    # eine Zahl ohne Bedeutung, die in der Response steht und irgendwann jemand
    # anzeigt. Kein Verbrenner ⇒ nichts aufzuteilen.
    eigener_l_100km = eigener_verbrauch_l_100km(eauto_parameter)
    anteil = (
        teile_fahrleistung(
            km_gefahren=km_gefahren,
            fahrverbrauch_kwh=fahrverbrauch_kwh,
            verbrauch_kwh_100km=_verbrauch_kwh_100km(eauto_parameter),
            anteil_prozent=_fahranteil_prozent(eauto_parameter),
        )
        if eigener_l_100km is not None
        else teile_fahrleistung(km_gefahren=km_gefahren)
    )
    fossile_kosten = (
        (anteil.km_verbrenner / 100) * eigener_l_100km * benzinpreis_euro
        if eigener_l_100km is not None
        else 0.0
    )

    ersparnis = benzin_kosten - strom_kosten - fossile_kosten

    return EAutoErsparnisErgebnis(
        ersparnis_euro=ersparnis,
        benzin_kosten_euro=benzin_kosten,
        strom_kosten_euro=strom_kosten,
        verwendeter_verbrauch_l_100km=verbrauch_l_100km,
        verwendeter_benzinpreis_euro=benzinpreis_euro,
        fossile_kosten_euro=fossile_kosten,
        km_elektrisch=anteil.km_elektrisch,
        km_verbrenner=anteil.km_verbrenner,
        anteil_quelle=anteil.quelle,
        verwendeter_strompreis_cent=wallbox_strompreis_cent,
    )


def aufgeloester_strompreis_cent(
    *,
    wallbox_strompreis_cent: float,
    monats_strompreis_lookup: Optional[dict[tuple[int, int], Optional[float]]] = None,
    gewichte: Optional[Iterable[tuple[int, int, float]]] = None,
) -> float:
    """Der über eine Periode **mengengewichtete** Netzbezugspreis in ct/kWh.

    ADR-002/P8 für die E-Mob-Fläche. Vor 2026-08-08 lösten vier Sichten diese
    eine Größe auf vier verschiedene Arten auf (F-18 · N-181):

    ==============================  ====================================
    Cockpit → Jahr, HA-Export (2×)  der **heute** gültige Tarif
    Komponenten-Hub                 mengengewichteter Monats-Ø
    Aussichten                      echter Monatspreis inkl. Flex-Ø
    ==============================  ====================================

    Der heutige Tarif ist schlicht falsch — eine Preiserhöhung bewertete die
    ganze Historie rückwirkend neu. Die anderen beiden sind **beide** richtig,
    aber verschieden genau, und genau daran driften die Sichten.

    ⚠ **Warum hier gemittelt und nicht monatsweise multipliziert wird:** im
    Wallbox-Pool-Fall (#262, evcc) ersetzt ``attribute_emob_pool_by_km`` die
    Monatswerte durch EINEN nach km verteilten Gesamtwert — eine
    Monatsaufteilung der Netzladung **existiert dort nicht**. Ein reiner
    Monatspreis-Lookup hätte in diesem Fall nichts zu multiplizieren. Deshalb
    nimmt diese Funktion die Gewichte, die der Aufrufer tatsächlich hat
    (Netzladung je Monat, sonst km je Monat), und liefert **einen** Preis
    zurück, den der Aufrufer auf seinen Gesamtwert anwendet.

    Für eine Anlage **ohne** Tarifwechsel ist das Ergebnis identisch zum
    bisherigen Wert — die Umstellung bewegt dort keine Zahl.

    Args:
        wallbox_strompreis_cent: Fallback (ct/kWh), wenn keine Gewichte oder
            kein Lookup vorliegen. Bleibt der einzige Wert, wenn der Aufrufer
            keine Monatsauflösung anbieten kann.
        monats_strompreis_lookup: ``{(jahr, monat): preis_cent_oder_None}`` —
            der **zum Monat gültige** Tarif, idealerweise bereits inklusive
            Flex-Ø (`resolve_netzbezug_preis_cent`). Einträge mit ``None``
            fallen auf ``wallbox_strompreis_cent`` zurück.
        gewichte: ``(jahr, monat, menge)`` — Netzladung je Monat, wo sie
            existiert; sonst km je Monat (derselbe Schlüssel, nach dem der
            Pool attribuiert). Nicht-positive Mengen werden übersprungen.

    Returns:
        ct/kWh. Ohne Lookup oder ohne positive Gewichte exakt
        ``wallbox_strompreis_cent``.
    """
    if not monats_strompreis_lookup or gewichte is None:
        return wallbox_strompreis_cent

    summe_gewicht = 0.0
    summe_gewichteter_preis = 0.0
    for jahr, monat, menge in gewichte:
        if menge is None or menge <= 0:
            continue
        preis = monats_strompreis_lookup.get((jahr, monat))
        if preis is None:
            preis = wallbox_strompreis_cent
        summe_gewicht += menge
        summe_gewichteter_preis += menge * preis

    if summe_gewicht <= 0:
        return wallbox_strompreis_cent
    return summe_gewichteter_preis / summe_gewicht


def berechne_eauto_ersparnis_periode(
    *,
    km_pro_monat: Iterable[tuple[int, int, float]],
    ladung_netz_kwh_gesamt: float,
    ladung_extern_euro_gesamt: float,
    wallbox_strompreis_cent: float,
    eauto_parameter: Optional[dict] = None,
    monats_benzinpreis_lookup: Optional[dict[tuple[int, int], Optional[float]]] = None,
    fahrverbrauch_kwh_gesamt: Optional[float] = None,
    monats_strompreis_lookup: Optional[dict[tuple[int, int], Optional[float]]] = None,
    netz_pro_monat: Optional[Iterable[tuple[int, int, float]]] = None,
) -> EAutoErsparnisErgebnis:
    """E-Auto-Ersparnis über eine Periode mit per-Monat-korrektem Benzinpreis.

    Drift-Fix #260 (NongJoWo): das E-Auto-Dashboard summierte zuvor `km`
    über die ganze Periode und rief `berechne_eauto_ersparnis` einmal mit
    einem festen Default-Benzinpreis (1,65 €/L) auf. Die Cockpit-Übersicht
    las hingegen pro Monat den dynamischen Preis aus
    `Monatsdaten.kraftstoffpreis_euro` (EU Weekly Oil Bulletin, seit v3.17.0).
    Ergebnis: zwei Sichten, zwei Ersparniszahlen, keine erkennbare Ursache.

    Korrektur: `benzin_kosten = Σ (km_monat × verbrauch × preis_monat)` mit
    Fallback-Kette pro Monat: Lookup → params.benzinpreis_euro → Default 1,65.

    `ladung_netz_kwh_gesamt` und `ladung_extern_euro_gesamt` bleiben Gesamt-
    Werte — der Wallbox-Pool-Anteil aus `attribute_emob_pool_by_km` wird
    ebenfalls auf Gesamtbasis verteilt und nicht pro Monat.

    Args:
        km_pro_monat: Iterable von `(jahr, monat, km)`-Tupeln für die Periode.
        ladung_netz_kwh_gesamt: Heim-Netzladung gesamt in kWh.
        ladung_extern_euro_gesamt: tatsächliche Kosten externer Ladung in € (gesamt).
        wallbox_strompreis_cent: Strompreis Heim-Netzladung in ct/kWh.
        eauto_parameter: `Investition.parameter` für Vergleichsverbrauch + Default-Benzinpreis.
        monats_benzinpreis_lookup: `{(jahr, monat): kraftstoffpreis_euro_oder_None}`
            aus `Anlage.monatsdaten`. Einträge mit `None` werden wie fehlende
            Monate behandelt (Fallback greift).
        monats_strompreis_lookup: ``{(jahr, monat): netzbezugspreis_cent}`` — der
            **zum Monat gültige** Tarif (ADR-002/P8), idealerweise inklusive
            Flex-Ø. Ohne ihn bleibt es bei ``wallbox_strompreis_cent``, und die
            Funktion rechnet exakt wie vor 2026-08-08.
        netz_pro_monat: ``(jahr, monat, netz_kwh)`` — die Gewichte für die
            Preis-Mittelung. ⚠ Im Wallbox-Pool-Fall existiert diese Aufteilung
            **nicht**; dann übergibt der Aufrufer ``km_pro_monat`` (derselbe
            Schlüssel, nach dem attribuiert wird). Fehlt beides, greift
            ``km_pro_monat`` automatisch.
        fahrverbrauch_kwh_gesamt: elektrischer Fahrverbrauch über die **ganze**
            Periode (#331). ⚠ Der Verbrenner-Anteil wird daraus einmal für die
            Periode bestimmt und dann monatsweise **proportional zu den km**
            angewendet — dieselbe Linie, auf der schon `ladung_netz_kwh_gesamt`
            und `ladung_extern_euro_gesamt` Gesamtwerte sind. Der Monatspreis
            trifft damit den fossilen Anteil genauso wie den Vergleichswert;
            was er nicht abbildet, ist ein Anteil, der sich **innerhalb** der
            Periode verschiebt (etwa Winter fossil, Sommer elektrisch).

    Returns:
        EAutoErsparnisErgebnis. `verwendeter_benzinpreis_euro` ist der
        km-gewichtete Durchschnitt der tatsächlich angewendeten Preise.
    """
    verbrauch_l_100km = _vergleich_verbrauch(eauto_parameter)
    fallback_preis = _benzinpreis_default(eauto_parameter)
    lookup = monats_benzinpreis_lookup or {}

    # `km_pro_monat` wird zweimal gebraucht (Benzin-Schleife + ggf. als
    # Preis-Gewicht) — ein Iterator wäre nach dem ersten Durchlauf leer.
    km_liste = list(km_pro_monat)

    # ADR-002/P8: der Strompreis der Periode, mengengewichtet über die Monate,
    # in denen tatsächlich geladen wurde. Ohne Lookup exakt der übergebene
    # Skalar — Bestandsaufrufer bewegen keine Zahl.
    strompreis_cent = aufgeloester_strompreis_cent(
        wallbox_strompreis_cent=wallbox_strompreis_cent,
        monats_strompreis_lookup=monats_strompreis_lookup,
        gewichte=netz_pro_monat if netz_pro_monat is not None else km_liste,
    )

    monate: list[tuple[float, float]] = []  # (km, preis)
    gesamt_km = 0.0
    gesamt_benzin = 0.0
    summe_gewichteter_preis = 0.0

    for jahr, monat, km in km_liste:
        if km is None or km <= 0:
            continue
        preis = lookup.get((jahr, monat))
        if preis is None:
            preis = fallback_preis
        gesamt_km += km
        gesamt_benzin += (km / 100) * verbrauch_l_100km * preis
        summe_gewichteter_preis += km * preis
        monate.append((km, preis))

    if gesamt_km <= 0:
        return EAutoErsparnisErgebnis(
            0.0, 0.0, 0.0,
            verbrauch_l_100km, fallback_preis,
            verwendeter_strompreis_cent=strompreis_cent,
        )

    strom_kosten = (
        max(0.0, ladung_netz_kwh_gesamt) * strompreis_cent / 100
        + ladung_extern_euro_gesamt
    )

    # ⚠ Ohne gepflegten Verbrenner-Verbrauch gar nicht erst aufteilen — s. die
    # Begründung in `berechne_eauto_ersparnis`.
    eigener_l_100km = eigener_verbrauch_l_100km(eauto_parameter)
    anteil = (
        teile_fahrleistung(
            km_gefahren=gesamt_km,
            fahrverbrauch_kwh=fahrverbrauch_kwh_gesamt,
            verbrauch_kwh_100km=_verbrauch_kwh_100km(eauto_parameter),
            anteil_prozent=_fahranteil_prozent(eauto_parameter),
        )
        if eigener_l_100km is not None
        else teile_fahrleistung(km_gefahren=gesamt_km)
    )
    fossile_kosten = 0.0
    if eigener_l_100km is not None and anteil.km_verbrenner > 0:
        v_quote = anteil.km_verbrenner / gesamt_km
        fossile_kosten = sum(
            (km * v_quote / 100) * eigener_l_100km * preis for km, preis in monate
        )

    ersparnis = gesamt_benzin - strom_kosten - fossile_kosten

    return EAutoErsparnisErgebnis(
        ersparnis_euro=ersparnis,
        benzin_kosten_euro=gesamt_benzin,
        strom_kosten_euro=strom_kosten,
        verwendeter_verbrauch_l_100km=verbrauch_l_100km,
        verwendeter_benzinpreis_euro=summe_gewichteter_preis / gesamt_km,
        fossile_kosten_euro=fossile_kosten,
        km_elektrisch=anteil.km_elektrisch,
        km_verbrenner=anteil.km_verbrenner,
        anteil_quelle=anteil.quelle,
        verwendeter_strompreis_cent=strompreis_cent,
    )


@dataclass
class EmobPoolAttribution:
    """Pool-Aggregat über E-Auto- und Wallbox-IMDs für evcc-artige Setups.

    Wallbox = Loadpoint-Wahrheit (evcc/Portal-Import schreibt hier),
    E-Auto = Vehicle-Wahrheit (km + ggf. eigene Ladedaten).
    `use_wb_pool` ist True, sobald eine Wallbox überhaupt Heimladung trägt
    (Phase-2a-Regel, strukturell statt magnitudenabhängig) — dann fließen die
    Wallbox-Ladedaten anteilig nach km in die E-Auto-Sichten zurück.
    """
    wb_pool_pv: float
    wb_pool_netz: float
    wb_pool_extern_kwh: float
    wb_pool_extern_euro: float
    eauto_total_km: float
    use_wb_pool: bool


@dataclass
class EmobPoolShare:
    """Km-anteilige Verteilung des Wallbox-Pools auf ein einzelnes E-Auto."""
    pv_kwh: float
    netz_kwh: float
    extern_kwh: float
    extern_euro: float


def compute_emob_pool_attribution(
    *,
    eauto_imd_data: Iterable[dict],
    wallbox_imd_data: Iterable[dict],
) -> EmobPoolAttribution:
    """Aggregiert das Wallbox-IMD-`verbrauch_daten` zum km-verteilbaren Pool und
    entscheidet **strukturell**, ob dieser Pool die E-Auto-Sichten speist.

    Phase-2a-Regel (`docs/KONZEPT-WALLBOX-EAUTO.md`, Entscheidung 1): sobald eine
    Wallbox-Investition Heimladung trägt, ist sie die kanonische Quelle
    (`use_wb_pool=True`) — unabhängig davon, wie viel (ggf. verirrte) Heimladung
    auf den E-Auto-IMD steht. Das löst den früheren Magnituden-Vergleich ab, der
    bei Streudaten die falsche Quelle wählte (#262). Gleiche Quellen-Entscheidung
    wie `get_emob_heimladung_canonical`, damit alle Sichten dieselbe Zahl zeigen.

    Aufrufer übergibt bereits gefilterte Iterables (nach `ist_aktiv_im_monat`
    und ggf. `ist_dienstlich`).
    """
    wb_pool_pv = 0.0
    wb_pool_netz = 0.0
    wb_pool_extern_kwh = 0.0
    wb_pool_extern_euro = 0.0
    for d in wallbox_imd_data:
        pv, netz = get_emob_pv_netz_kwh(d)
        wb_pool_pv += pv
        wb_pool_netz += netz
        wb_pool_extern_kwh += d.get("ladung_extern_kwh", 0) or 0
        wb_pool_extern_euro += d.get("ladung_extern_euro", 0) or 0

    eauto_total_km = 0.0
    for d in eauto_imd_data:
        eauto_total_km += d.get("km_gefahren", 0) or 0

    # Strukturell: Wallbox vorhanden + hat Heimladung → Pool-Quelle (Entsch. 1).
    use_wb_pool = (wb_pool_pv + wb_pool_netz) > 0

    return EmobPoolAttribution(
        wb_pool_pv=wb_pool_pv,
        wb_pool_netz=wb_pool_netz,
        wb_pool_extern_kwh=wb_pool_extern_kwh,
        wb_pool_extern_euro=wb_pool_extern_euro,
        eauto_total_km=eauto_total_km,
        use_wb_pool=use_wb_pool,
    )


_ZERO_SHARE = EmobPoolShare(0.0, 0.0, 0.0, 0.0)


def attribute_emob_pool_by_km(
    attribution: EmobPoolAttribution, eauto_km: float,
) -> EmobPoolShare:
    """Liefert den km-anteiligen Wallbox-Pool-Anteil für ein einzelnes E-Auto.

    Gibt einen geteilten Null-Share zurück, wenn `use_wb_pool` falsch ist oder
    km fehlt — der Aufrufer darf bedenkenlos abrufen ohne vorher zu prüfen.
    """
    if (
        not attribution.use_wb_pool
        or attribution.eauto_total_km <= 0
        or eauto_km <= 0
    ):
        return _ZERO_SHARE
    anteil = eauto_km / attribution.eauto_total_km
    return EmobPoolShare(
        pv_kwh=attribution.wb_pool_pv * anteil,
        netz_kwh=attribution.wb_pool_netz * anteil,
        extern_kwh=attribution.wb_pool_extern_kwh * anteil,
        extern_euro=attribution.wb_pool_extern_euro * anteil,
    )


def build_wb_pool_by_month(
    wallbox_imd: Iterable[tuple[int, int, dict]],
) -> dict[tuple[int, int], EmobPoolShare]:
    """Summiert Wallbox-IMD pro `(jahr, monat)` zu einem PV/Netz/Extern-Topf.

    Gegenstück zu `compute_emob_pool_attribution`, aber monatsweise — für die
    Pro-Monat-Attribution in der E-Auto-Detailtabelle (#262). `netz` über den
    SoT-Helper `get_emob_pv_netz_kwh` (liest `ladung_netz_kwh` oder leitet
    `Total − PV` ab). Aufrufer übergibt bereits aktiv-gefilterte Tripel.
    """
    acc: dict[tuple[int, int], list[float]] = {}
    for jahr, monat, d in wallbox_imd:
        d = d or {}
        pv, netz = get_emob_pv_netz_kwh(d, total_kwh=get_eauto_ladung_kwh(d))
        a = acc.setdefault((jahr, monat), [0.0, 0.0, 0.0, 0.0])
        a[0] += pv
        a[1] += netz
        a[2] += d.get("ladung_extern_kwh", 0) or 0
        a[3] += d.get("ladung_extern_euro", 0) or 0
    return {k: EmobPoolShare(v[0], v[1], v[2], v[3]) for k, v in acc.items()}


def build_eauto_km_by_month(
    eauto_imd: Iterable[tuple[int, int, dict]],
) -> dict[tuple[int, int], float]:
    """Σ gefahrene km ALLER E-Autos pro `(jahr, monat)` — der Nenner für die
    km-anteilige Pool-Verteilung. Aufrufer übergibt aktiv-gefilterte Tripel."""
    acc: dict[tuple[int, int], float] = {}
    for jahr, monat, d in eauto_imd:
        acc[(jahr, monat)] = acc.get((jahr, monat), 0.0) + ((d or {}).get("km_gefahren", 0) or 0)
    return acc


def attribute_month_share(
    wb_pool_month: Optional[EmobPoolShare],
    eauto_km_month: float,
    eauto_km_total_month: float,
) -> EmobPoolShare:
    """km-anteiliger Wallbox-Pool-Anteil eines E-Autos für EINEN Monat.

    Liefert den geteilten Null-Share, wenn kein Wallbox-Topf existiert oder km
    fehlen — der Aufrufer darf bedenkenlos abrufen.
    """
    if not wb_pool_month or eauto_km_total_month <= 0 or eauto_km_month <= 0:
        return _ZERO_SHARE
    f = eauto_km_month / eauto_km_total_month
    return EmobPoolShare(
        pv_kwh=wb_pool_month.pv_kwh * f,
        netz_kwh=wb_pool_month.netz_kwh * f,
        extern_kwh=wb_pool_month.extern_kwh * f,
        extern_euro=wb_pool_month.extern_euro * f,
    )


@dataclass
class EmobPoolCtx:
    """Phase-2a-Pool-Kontext einer Anlage, monatsweise aufgelöst.

    Liegt die E-Mob-Heimladung kanonisch auf der Wallbox (evcc-Setup), sehen
    die E-Auto-Sichten sonst leere IMD → PV-Anteil fehlt, Ersparnis überhöht
    (kein Netzstrom abgezogen). Mit diesem Kontext zieht jede E-Auto-Sicht den
    km-anteiligen Wallbox-Pool.

    ⚠ **Lag bis 2026-08-08 privat in `api/routes/ha_export.py`** — und genau
    deshalb hatte `aussichten.py` als einzige der fünf E-Mob-Sichten **gar
    keine** Pool-Attribution (F-17): sie hätte den Nachbau abschreiben müssen.
    Ein Mechanismus, den nur eine Route besitzt, ist für jede andere Sicht
    unsichtbar; die vierte Sicht baut ihn dann nicht nach, sondern gar nicht.
    """
    use_wb_pool: bool
    wb_pool_by_month: dict[tuple[int, int], EmobPoolShare]
    eauto_km_by_month: dict[tuple[int, int], float]
    #: Die Monatszeilen **mit** abgeleitetem PV-Anteil (F-16), nach
    #: ``(inv_id, jahr, monat)``. Sie liegen hier und nicht bei jedem Aufrufer,
    #: weil der Torwächter („ein gepflegter Wert gewinnt") über E-Auto **und**
    #: Wallbox eines Monats zusammen entscheidet — eine per-Investition-Schleife
    #: sieht aber immer nur ein Gerät. Wer dort selbst anreicherte, hielte eine
    #: gepflegte Wallbox-Zeile für nicht vorhanden und schätzte über eine
    #: Messung hinweg.
    daten_by_key: dict = field(default_factory=dict)


def build_emob_pool_ctx(
    inv_daten: dict[tuple[int, int, int], dict],
    eauto_ids: set[int],
    wallbox_ids: set[int],
) -> EmobPoolCtx:
    """Baut den Pool-Kontext aus bereits aktiv-gefilterten IMD.

    ``inv_daten`` ist ``{(inv_id, jahr, monat): verbrauch_daten}``.
    ``use_wb_pool`` ist **strukturell**: True, sobald eine Wallbox überhaupt
    Heimladung trägt (Entscheidung 1 des Konzepts) — nicht magnitudenabhängig,
    sonst wählt Streudatenlage die falsche Quelle (#262).
    """
    wb_pool_by_month = build_wb_pool_by_month(
        (jahr, monat, daten)
        for (inv_id, jahr, monat), daten in inv_daten.items()
        if inv_id in wallbox_ids
    )
    eauto_km_by_month = build_eauto_km_by_month(
        (jahr, monat, daten)
        for (inv_id, jahr, monat), daten in inv_daten.items()
        if inv_id in eauto_ids
    )
    use_wb_pool = any(
        (s.pv_kwh + s.netz_kwh) > 0 for s in wb_pool_by_month.values()
    )
    return EmobPoolCtx(
        use_wb_pool, wb_pool_by_month, eauto_km_by_month, dict(inv_daten)
    )


def emob_month_share(
    ctx: Optional[EmobPoolCtx],
    typ: str,
    km: float,
    jahr: int,
    monat: int,
) -> Optional[EmobPoolShare]:
    """km-anteiliger Wallbox-Pool-Anteil eines E-Autos für ``(jahr, monat)``.

    ``None`` heißt „keine Attribution" — kein Kontext, keine Wallbox-Heimladung
    oder ``typ != "e-auto"``. Dann verwendet der Aufrufer die eigenen IMD-Werte.
    Die Wallbox-Sicht behält immer ihre eigenen Daten (sie **ist** die Quelle).
    """
    if ctx is None or not ctx.use_wb_pool or typ != "e-auto":
        return None
    ms = attribute_month_share(
        ctx.wb_pool_by_month.get((jahr, monat)),
        km,
        ctx.eauto_km_by_month.get((jahr, monat), 0),
    )
    return ms if (ms.pv_kwh + ms.netz_kwh) > 0 else None


def pick_emob_ref_parameter(investitionen: Iterable) -> Optional[dict]:
    """Wählt das `parameter`-Dict für emob-Hauptberechnungen (Vergleichsverbrauch,
    Benzinpreis).

    E-Auto bevorzugt, weil die Felder E-Auto-spezifisch sind. Bei evcc-Setups
    steht die Wallbox häufig als erste emob-Investition vorne und hat diese
    Params naturgemäß nicht — Default 7,5 L/100km statt User-Wert war eine
    Drift-Quelle zwischen Hauptwert und Komponenten-Sicht.
    """
    eauto = next((i for i in investitionen if i.typ == "e-auto"), None)
    if eauto is not None:
        return eauto.parameter
    wb = next((i for i in investitionen if i.typ == "wallbox"), None)
    return wb.parameter if wb is not None else None


@dataclass
class EmobLadungPool:
    """Konsistentes E-Mobilitäts-Ladungs-Aggregat aus genau EINER Quelle.

    Garantie: `pv_kwh + netz_kwh == ladung_kwh`. Anders als feldweises
    `max()` über getrennte E-Auto- und Wallbox-Töpfe — das kann `pv` aus
    Quelle A und `netz` aus Quelle B nehmen und einen PV-Anteil > 100 %
    erzeugen (#262 junky84: Auswertungen → Komponenten zeigte PV 48 % +
    Netz 85 % = 133 %, weil die drei Felder aus drei `max()`-Aufrufen
    stammten). Die Heimladungs-Trias kommt hier immer geschlossen aus der
    Quelle mit der größeren Heimladung.
    """
    ladung_kwh: float       # Heimladung gesamt = pv_kwh + netz_kwh
    pv_kwh: float
    netz_kwh: float
    extern_kwh: float
    extern_euro: float
    ladevorgaenge: float
    quelle: str             # "wallbox" | "e-auto" | "leer"


def summiere_emob_quelle(imd_data: Iterable[dict]) -> EmobLadungPool:
    """Summiert eine Quelle (alle Wallbox- ODER alle E-Auto-IMD) zu einer in
    sich konsistenten Trias. `netz` über den SoT-Helper `get_emob_pv_netz_kwh`
    (liest `ladung_netz_kwh` direkt oder leitet `Total − PV` ab).

    Öffentlich seit S6: es gibt Sichten, die die Quellen **getrennt** ausweisen
    müssen (der Community-Payload trägt `eauto_*` und `wallbox_*` als eigene
    Felder). Sie dürfen die Felder trotzdem nicht selbst aus dem
    `verbrauch_daten`-Dict lesen — genau dort saß #262. `quelle` bleibt hier
    leer; die Quellen-WAHL trifft ausschließlich
    `get_emob_heimladung_canonical`.
    """
    pv = netz = extern_kwh = extern_euro = ladevorgaenge = 0.0
    for d in imd_data:
        d = d or {}
        p, n = get_emob_pv_netz_kwh(d, total_kwh=get_eauto_ladung_kwh(d))
        pv += p
        netz += n
        extern_kwh += d.get("ladung_extern_kwh", 0) or 0
        extern_euro += d.get("ladung_extern_euro", 0) or 0
        ladevorgaenge += d.get("ladevorgaenge", 0) or 0
    return EmobLadungPool(pv + netz, pv, netz, extern_kwh, extern_euro,
                          ladevorgaenge, "")


def get_emob_heimladung_canonical(
    *,
    eauto_imd_data: Iterable[dict],
    wallbox_imd_data: Iterable[dict],
) -> EmobLadungPool:
    """Kanonische E-Mob-Heimladung über eine **strukturelle** Quellen-Regel.

    Phase-2a-Helfer (`docs/KONZEPT-WALLBOX-EAUTO.md`, Entscheidung 1). Wählt die
    Quelle deterministisch — nicht magnitudenabhängig (die frühere Magnituden-
    Heuristik `wb.ladung_kwh >= ea.ladung_kwh` kippte bei verirrten Streudaten):

        Existiert eine Wallbox-Investition mit Heimladung → Wallbox ist Quelle.
        Sonst (keine Wallbox, oder Wallbox ohne Heimladung — z. B. Steckerlader/
        Schuko) → E-Auto ist Quelle.

    Die Wallbox misst den Stromfluss am Ladepunkt (evcc/Portal-Import schreibt
    hierher); ist sie vorhanden und hat sie Heimladung, ist sie die Wahrheit —
    unabhängig davon, wie viel verirrte Heimladung auf der E-Auto-IMD steht
    (#262 junky84: ~3.300 kWh Streudaten auf dem E-Auto — ein Magnituden-Pool
    hätte die falsche Quelle gewählt, sobald die Streudaten die echte übertreffen).

    Multi-Wallbox (Entscheidung 4): jede Wallbox = eigener Ladepunkt, alle
    WB-IMD werden summiert (Heimladung gesamt über alle Loadpoints). Für den
    0/1-Wallbox-Fall ist das mit der einfachen Summe identisch.

    Externe Ladung bleibt orthogonal: das Paar `(kWh, €)` kommt aus der Quelle
    mit den höheren externen Kosten.

    Aufrufer übergibt bereits gefilterte Iterables (nach `ist_aktiv_im_monat`
    und `ist_dienstlich`). Die `pv + netz == ladung_kwh`-Garantie von
    `EmobLadungPool` bleibt erhalten (Trias kommt geschlossen aus einer Quelle).
    """
    wb = summiere_emob_quelle(wallbox_imd_data)
    ea = summiere_emob_quelle(eauto_imd_data)

    if wb.ladung_kwh > 0:
        heim, name = wb, "wallbox"
    elif ea.ladung_kwh > 0:
        heim, name = ea, "e-auto"
    else:
        heim, name = wb, "leer"

    extern = wb if wb.extern_euro >= ea.extern_euro else ea

    return EmobLadungPool(
        ladung_kwh=heim.ladung_kwh,
        pv_kwh=heim.pv_kwh,
        netz_kwh=heim.netz_kwh,
        extern_kwh=extern.extern_kwh,
        extern_euro=extern.extern_euro,
        ladevorgaenge=max(wb.ladevorgaenge, ea.ladevorgaenge),
        quelle=name,
    )
