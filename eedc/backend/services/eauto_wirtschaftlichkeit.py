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
from typing import Callable, Iterable, Mapping, Optional

from backend.core.berechnungen.phev_anteil import teile_fahrleistung
from backend.core.field_definitions import (
    get_eauto_ladung_kwh,
    get_emob_pv_netz_kwh,
    traegt_heimlade_wert,
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


def fahranteil_prozent(eauto_parameter: Optional[dict]) -> Optional[float]:
    """Gepflegter elektrischer Fahranteil in % — ``None``, wenn nicht gepflegt.

    ⚠ **Öffentlich seit rapahl (T89667 #253)**, und der Grund gehört zur
    Funktion: „nicht gepflegt" hat mehrere Gestalten — der fehlende Schlüssel,
    ein geleertes Feld (``""``, seit dem Formular-Fix der Rückweg aus einer
    einmal getroffenen Auswahl) und ein unbrauchbarer Wert aus einem Import.
    Diese Funktion macht aus allen dreien ``None``.

    Wer stattdessen ``parameter.get(...) is not None`` schreibt, sieht bei den
    letzten beiden einen *gepflegten* Wert, wo die Rechnung hier ``None``
    bekommt — die beiden Seiten driften dann auseinander, ohne dass es auffällt.
    Genau so schwieg der Daten-Checker in dem Fall, für den er gebaut wurde.
    ``0`` bleibt ein gepflegter Wert und wird **nicht** zu ``None``.
    """
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
            anteil_prozent=fahranteil_prozent(p),
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
            anteil_prozent=fahranteil_prozent(eauto_parameter),
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
            anteil_prozent=fahranteil_prozent(eauto_parameter),
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
    deshalb hatte `aussichten/finanzen.py` als einzige der fünf E-Mob-Sichten **gar
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
    #: N-555: der Entscheid der einen Funktion je Monat (``(jahr, monat) →``). Er
    #: sagt, ob der Monat der Wallbox, den Autos, der 0 oder der Schätzung gehört —
    #: die Leser fragen ihn über ``emob_heimladung_im_monat``.
    entscheide: dict = field(default_factory=dict)


def build_emob_pool_ctx(
    inv_daten: dict[tuple[int, int, int], dict],
    eauto_ids: set[int],
    wallbox_ids: set[int],
    *,
    wallbox_in_betrieb: Optional[Callable[[int, int], bool]] = None,
    quoten: Optional[Mapping[tuple[int, int], float]] = None,
    quellen_je_monat: Optional[Mapping[tuple[int, int], frozenset]] = None,
) -> EmobPoolCtx:
    """Baut den Pool-Kontext aus bereits aktiv-gefilterten IMD.

    ``inv_daten`` ist ``{(inv_id, jahr, monat): verbrauch_daten}``.
    ``use_wb_pool`` ist **strukturell**: True, sobald eine Wallbox überhaupt
    Heimladung trägt (Entscheidung 1 des Konzepts) — nicht magnitudenabhängig,
    sonst wählt Streudatenlage die falsche Quelle (#262).

    N-555: zusätzlich je Monat der Entscheid der einen Funktion
    (``entscheide_emob_heimladung``). ``wallbox_in_betrieb(jahr, monat)`` sagt, ob
    eine private Wallbox in Betrieb ist (ohne ⇒ „es gibt eine Wallbox-Zeile");
    ``quoten`` ist der abgeleitete PV-Anteil je Monat für die Schätzung
    (``emob_ladeanteil.reichere_monatszeilen_an_mit_quoten``). ``quellen_je_monat``
    trägt für den **laufenden** Monat die Heimlade-Quellen (Regel 1:
    ``services/emob_heimlade_quellen.laufende_heimlade_quellen``) — abgeschlossene
    Monate entscheiden nur nach dem gespeicherten Wert.
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
    je_monat: dict[tuple[int, int], tuple[dict[int, dict], list[dict]]] = {}
    for (i, j, m), d in inv_daten.items():
        if i in eauto_ids:
            je_monat.setdefault((j, m), ({}, []))[0][i] = d
        elif i in wallbox_ids:
            je_monat.setdefault((j, m), ({}, []))[1].append(d)
    entscheide = {}
    for (jahr, monat), (ea_je_inv, wb_zeilen) in je_monat.items():
        entscheide[(jahr, monat)] = entscheide_emob_heimladung(
            eauto_je_inv=ea_je_inv,
            wallbox_zeilen=wb_zeilen,
            wallbox_in_betrieb=(
                wallbox_in_betrieb(jahr, monat) or bool(wb_zeilen)
                if wallbox_in_betrieb is not None else None
            ),
            pv_quote=(quoten or {}).get((jahr, monat)),
            heimlade_quellen=(quellen_je_monat or {}).get((jahr, monat), frozenset()),
        )
    return EmobPoolCtx(
        use_wb_pool, wb_pool_by_month, eauto_km_by_month, dict(inv_daten),
        entscheide,
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

    ⚠ Seit N-555 fragen die E-Auto-Leser ``emob_heimladung_im_monat`` — sie kennt
    auch die Monate, in denen die Wallbox **nicht** die Quelle ist.
    """
    if ctx is None or not ctx.use_wb_pool or typ != "e-auto":
        return None
    ms = attribute_month_share(
        ctx.wb_pool_by_month.get((jahr, monat)),
        km,
        ctx.eauto_km_by_month.get((jahr, monat), 0),
    )
    return ms if (ms.pv_kwh + ms.netz_kwh) > 0 else None


def emob_extern_im_monat(
    ctx: Optional[EmobPoolCtx],
    km: float,
    jahr: int,
    monat: int,
    zeile: Optional[dict],
) -> tuple[float, float]:
    """``(kWh, €)`` der externen Ladung eines E-Autos in ``(jahr, monat)`` — nach der Topf-Regel.

    Der Weg für die Leser, die je Fahrzeug und Monat rechnen (HA-Export). Ist die Wallbox
    im Monat die Quelle, konkurrieren ihr km-Anteil am Extern der Wallbox-Zeilen und das
    eigene Extern des Autos — das Paar mit den höheren Kosten gewinnt
    (``waehle_extern_paar``, dieselbe Regel wie Topf, Hub und T-Konto). Sonst ist es das
    eigene Extern des Autos.
    """
    zeile = zeile or {}
    eigen = (
        float(zeile.get("ladung_extern_kwh", 0) or 0),
        float(zeile.get("ladung_extern_euro", 0) or 0),
    )
    entscheid = ctx.entscheide.get((jahr, monat)) if ctx is not None else None
    if entscheid is None or entscheid.quelle != QUELLE_WALLBOX:
        return eigen
    anteil = attribute_month_share(
        ctx.wb_pool_by_month.get((jahr, monat)),
        km,
        ctx.eauto_km_by_month.get((jahr, monat), 0),
    )
    return waehle_extern_paar(anteil.extern_kwh, anteil.extern_euro, *eigen)


def emob_heimladung_im_monat(
    ctx: Optional[EmobPoolCtx],
    inv_id: int,
    km: float,
    jahr: int,
    monat: int,
    zeile: Optional[dict],
) -> tuple[float, float]:
    """``(pv, netz)`` der privaten Heimladung eines E-Autos in ``(jahr, monat)`` — nach Regel 2-Ü.

    Der eine Weg für die Leser, die ``InvestitionMonatsdaten`` je Fahrzeug selbst
    laden (Aussichten, HA-Export, Hub-Tabelle). Bis N-555 stand an jeder dieser
    Stellen ``get_emob_pv_netz_kwh(zeile)`` mit dem Wallbox-Anteil als Override —
    und damit der still eingesetzte Fahrverbrauch, sobald die Wallbox im Monat
    nichts trug. Die km-Verteilung des Wallbox-Topfs bleibt dieselbe wie bisher
    (``attribute_month_share``).

    Ohne Kontext (``ctx is None``) entscheidet die Funktion für diese eine Zeile
    allein — so, als gäbe es keine Wallbox.
    """
    if ctx is None:
        entscheid = entscheide_emob_heimladung(
            eauto_je_inv={inv_id: zeile or {}}, wallbox_zeilen=[],
        )
        return heimladung_des_autos(entscheid, inv_id, zeile)
    entscheid = ctx.entscheide.get((jahr, monat))
    if entscheid is None:
        entscheid = entscheide_emob_heimladung(
            eauto_je_inv={inv_id: zeile or {}}, wallbox_zeilen=[],
        )
    anteil = None
    if entscheid.quelle == QUELLE_WALLBOX:
        anteil = attribute_month_share(
            ctx.wb_pool_by_month.get((jahr, monat)),
            km,
            ctx.eauto_km_by_month.get((jahr, monat), 0),
        )
    return heimladung_des_autos(entscheid, inv_id, zeile, wallbox_anteil=anteil)


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


def waehle_extern_paar(
    wallbox_kwh: float, wallbox_euro: float, eauto_kwh: float, eauto_euro: float,
) -> tuple[float, float]:
    """Das Extern-Paar ``(kWh, €)`` aus der Quelle mit den **höheren** externen Kosten.

    Die eine Regel für die externe Ladung (Topf, #260): Extern ist orthogonal zur
    Heimlade-Quelle und kommt geschlossen aus EINER Seite — der Wallbox-Seite (bzw. dem
    Wallbox-Anteil eines Autos) oder den eigenen Zeilen des Autos, je nachdem, welche die
    höheren Kosten trägt. Bei Gleichstand gewinnt die Wallbox (wie bisher).

    ⚑ N-555 F-5: Bis 25.09.2026 stand diese Regel nur im Topf. Der E-Auto-Hub und die
    T-Konto-Zeile ersetzten im Wallbox-Fall das Extern des Autos durch den Extern-Anteil
    der **Wallbox** — die Registry führt Extern aber am Auto, die Wallbox hat kein
    Extern-Feld. Folge: Extern 0 und 0 € externe Kosten, obwohl am Auto erfasst, und eine
    Ersparnis vs. Verbrenner, die um genau diese Kosten zu hoch war.
    """
    if wallbox_euro >= eauto_euro:
        return (wallbox_kwh, wallbox_euro)
    return (eauto_kwh, eauto_euro)


def _traegt_heimladung(pool: "EmobLadungPool") -> bool:
    """Die Schwelle der Phase-2a-Quellenwahl — **genau einmal** ausgeschrieben.

    Beide Einstiege (``wallbox_ist_heimlade_quelle`` und
    ``get_emob_heimladung_canonical``) lesen sie von hier, damit die Regel nicht
    an zwei Stellen driften kann.
    """
    return pool.ladung_kwh > 0


def wallbox_ist_heimlade_quelle(wallbox_imd_data: Iterable[dict]) -> bool:
    """Ist die **Wallbox** die kanonische Heimlade-Quelle dieses Monats?

    Die Phase-2a-Regel als eigener Name, damit sie **einmal** existiert.
    ``get_emob_heimladung_canonical`` wendet sie auf die gepoolte Trias an;
    ``services/emob_ladeanteil`` braucht sie **vor** dem Poolen, um zu
    entscheiden, wessen ``ladung_pv_kwh`` uberhaupt zaehlt.

    ⚑ **Warum sie herausgezogen ist.** Bis 2026-08-24 stand die Quellenwahl nur
    hier, der Torwaechter der PV-Ableitung fragte dagegen **beide** Seiten. Zwei
    unserer eigenen Regeln widersprachen sich damit: diese hier erklaerte den
    E-Auto-Wert bei vorhandener Wallbox fuer unbeachtlich, jene gab genau ihm
    ein Vetorecht gegen die Ableitung. Ende zu Ende gemessen hiess das
    **PV-Anteil 0 %** statt der abgeleiteten 62 % — nicht eine falsche Zahl,
    sondern gar keine. Eine Regel, die an zwei Stellen verschieden gelesen wird,
    ist keine Regel; deshalb steht sie jetzt an einer.
    """
    return _traegt_heimladung(summiere_emob_quelle(wallbox_imd_data))


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

    ⭐ **Seit N-555 nur noch die Kurzform der einen Funktion**
    (``entscheide_emob_heimladung``, Konzept Heimladung/Fahrverbrauch Regel 2-Ü):
    für Aufrufer, die EINEN Monat als zwei Listen halten und keine Quelle, keine
    Investitionsliste und keine Tages-Quote kennen. „Wallbox in Betrieb" heißt dann
    „es gibt eine Wallbox-Zeile". Eine Regel, zwei Einstiege — kein zweiter Rechenweg.
    """
    return entscheide_emob_heimladung(
        eauto_je_inv=dict(enumerate(eauto_imd_data)),
        wallbox_zeilen=list(wallbox_imd_data),
    ).pool


# ═════════════════════════════════════════════════════════════════════════════
# N-555 Stufe 1 — die EINE Funktion: wer trägt die Heimladung dieses Monats?
# ═════════════════════════════════════════════════════════════════════════════
#
# Konzept Heimladung/Fahrverbrauch, Fassung 7.1, Abschnitt 3: Regel 1 (der
# Fahrverbrauch springt nur ein, wenn über die Heimladung nichts bekannt ist),
# Regel 2-Ü (die heutige Rangfolge, jetzt nach Regel 1) und Regel 6 (eine Stelle
# entscheidet, alle Sichten folgen).
#
# ⛔ **Warum das hier steht und nicht mehr in den Lese-Hilfen.** Bis 25.09.2026
# setzten `get_eauto_ladung_kwh` und `get_emob_pv_netz_kwh` (`core/field_definitions/
# reader.py`) den Fahrverbrauch **still** als Ladung ein, sobald keine Ladung
# eingetragen war — auch neben einer Wallbox, die im Monat gemessen 0 kWh geladen
# hatte (Johnny_1993, T89667 #363–#374: 1.364 kWh „Ladung" bei einer Wallbox, die
# nicht geladen hatte). Eine 0 und „nichts erfasst" sahen dort gleich aus. Jetzt
# lesen die Helfer nur noch Ladefelder, und die Schätzung aus dem Fahrverbrauch
# entsteht **ausschließlich** hier — ausdrücklich als Schätzung gekennzeichnet,
# nie gespeichert (Wächter `test_n555_fahrverbrauch_bleibt_fahrverbrauch.py`).
#
# Stufe 1 gibt den **Topf** aus wie bisher (`EmobLadungPool`, Garantie
# `pv + netz == ladung_kwh`); die Leser behalten ihre Verteilung nach Kilometern.
# Die Eingänge sind schon je Auto (Stufe 2 tauscht nur die Rangfolge und ergänzt
# eine Ausgabe je Auto — zurückgebaut wird nichts).

#: Quelle des Entscheids (`EmobLadungPool.quelle`). `"wallbox"`/`"e-auto"` wie bisher.
QUELLE_WALLBOX = "wallbox"
QUELLE_EAUTO = "e-auto"
#: Regel 2-Ü Schritt 3: über die Heimladung ist etwas bekannt (Wert, auch 0, oder im
#: laufenden Monat eine Quelle) — sie ist **0**.
QUELLE_NULL = "null"
#: Regel 2-Ü Schritt 4: nichts bekannt — der Fahrverbrauch der privaten Autos ist die
#: **Schätzung** der Heimladung.
QUELLE_SCHAETZUNG = "schaetzung"
#: Nichts bekannt und kein Fahrverbrauch — der alte Name für „keine Heimladung".
QUELLE_LEER = "leer"


@dataclass(frozen=True)
class DienstlicheLadung:
    """Die dienstliche Ladung EINES Dienstwagens bzw. einer dienstlichen Wallbox im Monat.

    Stufe 1 rechnet sie **wie bisher** (Konzept Regel 2-Ü, letzter Absatz): seine Felder,
    sonst sein Fahrverbrauch als Netzstrom. Neu ist nur, dass das ausdrücklich hier
    geschieht und ``gemessen`` es sagt, statt dass ein Leser es still einsetzt. Die
    Doppelzählung an der privaten Wallbox (F4) bleibt bis Stufe 2.
    """
    pv_kwh: float
    netz_kwh: float
    #: ``False`` ⇒ die Menge ist der Fahrverbrauch (Schätzung), nicht gemessen.
    gemessen: bool


@dataclass(frozen=True)
class EmobHeimladungEntscheid:
    """Das Ergebnis der einen Funktion für EINEN Monat."""
    #: Der private Heimladungs-Topf (Garantie ``pv + netz == ladung_kwh``);
    #: ``pool.quelle`` ∈ {wallbox, e-auto, null, schaetzung, leer}.
    pool: EmobLadungPool
    #: Regel 2-Ü Schritt 4 je privatem Auto: ``inv_id → (pv, netz)`` der Schätzung.
    #: Leer, wenn der Monat nicht geschätzt ist. Interne Ausgabe für die Leser, die je
    #: Auto rechnen (T-Konto, Hub, Aussichten, HA-Export) — keine Verteilung des Topfs.
    schaetzung_je_auto: dict[int, tuple[float, float]]
    #: Dienstliche Menge je Dienstwagen/dienstlicher Wallbox (``inv_id →``).
    dienstlich_je_inv: dict[int, DienstlicheLadung]
    #: Ist im Monat eine private Wallbox in Betrieb? (Regel 2-Ü Schritt 2)
    wallbox_in_betrieb: bool
    #: Trägt die Schätzung einen aus der Tagesebene abgeleiteten PV-Anteil?
    anteil_abgeleitet: bool = False

    @property
    def quelle(self) -> str:
        return self.pool.quelle

    @property
    def dienstlich_pv_kwh(self) -> float:
        return sum(d.pv_kwh for d in self.dienstlich_je_inv.values())

    @property
    def dienstlich_netz_kwh(self) -> float:
        return sum(d.netz_kwh for d in self.dienstlich_je_inv.values())


def eauto_zeile_ohne_altwert(zeile: Optional[dict], *, wallbox_in_betrieb: bool) -> dict:
    """Die Heimlade-Felder EINER privaten E-Auto-Zeile, wie Regel 2-Ü Schritt 2 sie liest.

    Ein alter Gesamtwert ``ladung_kwh`` am Auto zählt nur, wenn **keine** private
    Wallbox in Betrieb ist (Steckerlader); neben einer Wallbox gelten nur „Heim: PV"
    und „Heim: Netz". Gibt eine Kopie zurück, wenn etwas wegfällt.
    """
    zeile = zeile or {}
    if wallbox_in_betrieb and "ladung_kwh" in zeile:
        zeile = {k: v for k, v in zeile.items() if k != "ladung_kwh"}
    return zeile


def eauto_heimladung_der_zeile(
    zeile: Optional[dict], *, wallbox_in_betrieb: bool,
) -> tuple[float, float]:
    """``(pv, netz)`` der eigenen Heimlade-Felder EINER privaten E-Auto-Zeile.

    Kein Fahrverbrauch: der kommt nur über ``entscheide_emob_heimladung`` als
    Schätzung ins Spiel.
    """
    return get_emob_pv_netz_kwh(
        eauto_zeile_ohne_altwert(zeile, wallbox_in_betrieb=wallbox_in_betrieb)
    )


def dienstliche_ladung_der_zeile(zeile: Optional[dict]) -> DienstlicheLadung:
    """Die dienstliche Menge EINER Zeile — bitgleich zur Rechnung bis 25.09.2026.

    Bis dahin stand an ``monats_fakten/roh.py`` ``get_emob_pv_netz_kwh(data)`` ohne
    ``total_kwh``, und die Lese-Hilfe nahm ``ladung_kwh or verbrauch_kwh``. Genau das
    steht hier ausdrücklich: gemessen ist, was Ladefelder trägt; sonst ist der
    Fahrverbrauch die Schätzung, als Netzstrom (Konzept Regel 2-Ü, Dienstwagen).
    """
    zeile = zeile or {}
    pv = float(zeile.get("ladung_pv_kwh") or 0)
    if zeile.get("ladung_netz_kwh") is not None:
        return DienstlicheLadung(pv, float(zeile["ladung_netz_kwh"]), True)
    if zeile.get("ladung_kwh"):
        return DienstlicheLadung(pv, max(0.0, float(zeile["ladung_kwh"]) - pv), True)
    fahrverbrauch = float(zeile.get("verbrauch_kwh") or 0)
    if fahrverbrauch:
        return DienstlicheLadung(pv, max(0.0, fahrverbrauch - pv), False)
    return DienstlicheLadung(pv, 0.0, pv > 0)


def entscheide_emob_heimladung(
    *,
    eauto_je_inv: Mapping[int, dict],
    wallbox_zeilen: Iterable[dict],
    wallbox_in_betrieb: Optional[bool] = None,
    dienstwagen_je_inv: Optional[Mapping[int, dict]] = None,
    heimlade_quellen: Iterable = (),
    pv_quote: Optional[float] = None,
) -> EmobHeimladungEntscheid:
    """Regel 1 + Regel 2-Ü für EINEN Monat — die eine Stelle (Regel 6).

    1. Trägt eine private Wallbox in Betrieb Heimladung **über 0**, ist sie die Quelle.
    2. Sonst: private E-Autos mit Werten in „Heim: PV"/„Heim: Netz" (ohne Wallbox in
       Betrieb auch der alte Gesamtwert ``ladung_kwh``) ⇒ diese (Steckerlader).
    3. Sonst: trägt irgendein Heimlade-Feld (Wallbox oder Auto) einen Wert, **auch 0**,
       oder — im laufenden Monat — eine Quelle ⇒ Heimladung **0**.
    4. Sonst: Fahrverbrauch je privatem E-Auto als **Schätzung**.

    Args:
        eauto_je_inv: ``inv_id → verbrauch_daten`` der **privaten** E-Autos des Monats
            (in Betrieb gefiltert). Die Zeilen dürfen den abgeleiteten PV-Anteil schon
            tragen (Phase 5); eine Zeile nur mit Fahrverbrauch trägt ihn nicht.
        wallbox_zeilen: ``verbrauch_daten`` der **privaten** Wallboxen in Betrieb.
        wallbox_in_betrieb: Ist eine private Wallbox im Monat in Betrieb — auch ohne
            Zeile? ``None`` ⇒ „es gibt eine Wallbox-Zeile" (für Aufrufer ohne
            Investitionsliste).
        dienstwagen_je_inv: ``inv_id → verbrauch_daten`` der Dienstwagen und
            dienstlichen Wallboxen; ihre Menge wie bisher (``DienstlicheLadung``).
        heimlade_quellen: nur im **laufenden Monat** (und am Tag): die Heimlade-Felder
            mit zugeordneter Quelle, z. B. ``{(7, "ladung_kwh")}`` — aus
            ``snapshot.keys.feld_hat_zaehler``. Abgeschlossene Monate entscheiden nur
            nach dem gespeicherten Wert (Regel 1); dort bleibt das Argument leer.
        pv_quote: der aus der Tagesebene abgeleitete PV-Anteil (0…1) dieses Monats.
            Er gilt für die Schätzung genauso, wie er vor N-555 über die Anreicherung
            der Zeile auf den Fahrverbrauch fiel — Zahl und Monat = Σ Tage bleiben.
    """
    eauto_je_inv = dict(eauto_je_inv or {})
    wallbox_zeilen = [z or {} for z in (wallbox_zeilen or ())]
    if wallbox_in_betrieb is None:
        wallbox_in_betrieb = bool(wallbox_zeilen)

    wb = summiere_emob_quelle(wallbox_zeilen)
    ea = summiere_emob_quelle(
        eauto_zeile_ohne_altwert(z, wallbox_in_betrieb=wallbox_in_betrieb)
        for z in eauto_je_inv.values()
    )

    schaetzung: dict[int, tuple[float, float]] = {}
    abgeleitet = False
    if _traegt_heimladung(wb):
        heim, name = wb, QUELLE_WALLBOX
    elif _traegt_heimladung(ea):
        heim, name = ea, QUELLE_EAUTO
    elif (
        any(traegt_heimlade_wert("wallbox", z) for z in wallbox_zeilen)
        or any(traegt_heimlade_wert("e-auto", z) for z in eauto_je_inv.values())
        or any(True for _ in (heimlade_quellen or ()))
    ):
        heim, name = wb, QUELLE_NULL
    else:
        for inv_id, zeile in eauto_je_inv.items():
            fahrverbrauch = float((zeile or {}).get("verbrauch_kwh") or 0)
            if fahrverbrauch <= 0:
                continue
            pv = fahrverbrauch * pv_quote if pv_quote is not None else 0.0
            schaetzung[inv_id] = (pv, fahrverbrauch - pv)
            abgeleitet = abgeleitet or pv_quote is not None
        if schaetzung:
            pv_s = sum(p for p, _ in schaetzung.values())
            netz_s = sum(n for _, n in schaetzung.values())
            heim = EmobLadungPool(pv_s + netz_s, pv_s, netz_s, 0.0, 0.0, 0.0, "")
            name = QUELLE_SCHAETZUNG
        else:
            heim, name = wb, QUELLE_LEER

    # Extern bleibt orthogonal (unverändert): das Paar kommt aus der Quelle mit
    # den höheren externen Kosten — die eine Regel, `waehle_extern_paar`.
    extern_kwh, extern_euro = waehle_extern_paar(
        wb.extern_kwh, wb.extern_euro, ea.extern_kwh, ea.extern_euro,
    )

    return EmobHeimladungEntscheid(
        pool=EmobLadungPool(
            ladung_kwh=heim.ladung_kwh,
            pv_kwh=heim.pv_kwh,
            netz_kwh=heim.netz_kwh,
            extern_kwh=extern_kwh,
            extern_euro=extern_euro,
            ladevorgaenge=max(wb.ladevorgaenge, ea.ladevorgaenge),
            quelle=name,
        ),
        schaetzung_je_auto=schaetzung,
        dienstlich_je_inv={
            inv_id: dienstliche_ladung_der_zeile(z)
            for inv_id, z in (dienstwagen_je_inv or {}).items()
        },
        wallbox_in_betrieb=wallbox_in_betrieb,
        anteil_abgeleitet=abgeleitet and bool(schaetzung),
    )


def heimladung_des_autos(
    entscheid: EmobHeimladungEntscheid,
    inv_id: int,
    zeile: Optional[dict],
    *,
    wallbox_anteil: Optional[EmobPoolShare] = None,
) -> tuple[float, float]:
    """``(pv, netz)`` der privaten Heimladung EINES Autos in EINEM Monat — nach dem Entscheid.

    Der Weg für die Leser, die je Fahrzeug rechnen (T-Konto, Hub, Aussichten,
    HA-Export). Die **Verteilung** des Wallbox-Topfs bleibt beim Leser (Stufe 1): er
    übergibt seinen km-Anteil als ``wallbox_anteil``.

    * Wallbox ist die Quelle ⇒ der übergebene km-Anteil (``None`` ⇒ 0): die eigenen
      Felder des Autos zählen daneben nicht (Regel 2-Ü Schritt 1).
    * E-Auto ⇒ seine eigenen Heimlade-Felder (Schritt 2).
    * Schätzung ⇒ sein Fahrverbrauch (Schritt 4).
    * 0 / leer ⇒ ``(0, 0)`` (Schritt 3).
    """
    quelle = entscheid.quelle
    if quelle == QUELLE_WALLBOX:
        if wallbox_anteil is None:
            return (0.0, 0.0)
        return (wallbox_anteil.pv_kwh, wallbox_anteil.netz_kwh)
    if quelle == QUELLE_EAUTO:
        return eauto_heimladung_der_zeile(
            zeile, wallbox_in_betrieb=entscheid.wallbox_in_betrieb,
        )
    if quelle == QUELLE_SCHAETZUNG:
        return entscheid.schaetzung_je_auto.get(inv_id, (0.0, 0.0))
    return (0.0, 0.0)
