"""E-Auto/Wallbox-Wirtschaftlichkeit — Single Source of Truth.

Anlass: Drift-Audit Domäne A2 (`docs/drafts/INVENTUR-DRIFT-AUDIT.md`).
Cockpit/Monatsbericht hatten 7 L/100km und 1,80 €/L hartcodiert, ignorierten
User-gepflegte Werte — User sahen 7-9% falsche Ersparnis vs. Aussichten/PDF.

Vorher: vier Code-Pfade, zwei verschiedene Defaults (7 vs. 7,5 L; 1,80 vs.
1,65 €/L). Nachher: ein Helper mit kanonischen Defaults aus
`PARAM_E_AUTO_DEFAULTS`.

Formel:
    benzin_kosten = (km / 100) × verbrauch_l_100km × benzinpreis_euro
    strom_kosten = ladung_netz_kwh × wallbox_strompreis_cent / 100 + ladung_extern_euro
    ersparnis = benzin_kosten - strom_kosten

Verbrauch: aus `params.vergleich_verbrauch_l_100km`, Default 7,5 L/100km.
Benzinpreis: monatlicher Override (Monatsdaten.kraftstoffpreis_euro) >
             params.benzinpreis_euro > Default 1,65 €/L.
Strompreis: separater Wallbox-Tarif > allgemeiner Tarif.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

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
    """Ergebnis der E-Auto-Ersparnis-Berechnung vs. Verbrenner."""
    ersparnis_euro: float
    benzin_kosten_euro: float
    strom_kosten_euro: float
    # Diagnostik: welche Werte wurden tatsächlich verwendet?
    verwendeter_verbrauch_l_100km: float
    verwendeter_benzinpreis_euro: float


def _vergleich_verbrauch(eauto_parameter: Optional[dict]) -> float:
    """Liest Benzin-Vergleichsverbrauch aus params, sonst kanon. Default 7,5."""
    if eauto_parameter is None:
        return BENZIN_VERBRAUCH_DEFAULT_L_100KM
    return eauto_parameter.get(
        PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"],
        PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
    ) or BENZIN_VERBRAUCH_DEFAULT_L_100KM


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

    benzin_kosten = (km_gefahren / 100) * verbrauch_l_100km * benzinpreis_euro
    strom_kosten = max(0.0, ladung_netz_kwh) * wallbox_strompreis_cent / 100 + ladung_extern_euro
    ersparnis = benzin_kosten - strom_kosten

    return EAutoErsparnisErgebnis(
        ersparnis_euro=ersparnis,
        benzin_kosten_euro=benzin_kosten,
        strom_kosten_euro=strom_kosten,
        verwendeter_verbrauch_l_100km=verbrauch_l_100km,
        verwendeter_benzinpreis_euro=benzinpreis_euro,
    )


def berechne_eauto_ersparnis_periode(
    *,
    km_pro_monat: Iterable[tuple[int, int, float]],
    ladung_netz_kwh_gesamt: float,
    ladung_extern_euro_gesamt: float,
    wallbox_strompreis_cent: float,
    eauto_parameter: Optional[dict] = None,
    monats_benzinpreis_lookup: Optional[dict[tuple[int, int], Optional[float]]] = None,
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

    Returns:
        EAutoErsparnisErgebnis. `verwendeter_benzinpreis_euro` ist der
        km-gewichtete Durchschnitt der tatsächlich angewendeten Preise.
    """
    verbrauch_l_100km = _vergleich_verbrauch(eauto_parameter)
    fallback_preis = _benzinpreis_default(eauto_parameter)
    lookup = monats_benzinpreis_lookup or {}

    gesamt_km = 0.0
    gesamt_benzin = 0.0
    summe_gewichteter_preis = 0.0

    for jahr, monat, km in km_pro_monat:
        if km is None or km <= 0:
            continue
        preis = lookup.get((jahr, monat))
        if preis is None:
            preis = fallback_preis
        gesamt_km += km
        gesamt_benzin += (km / 100) * verbrauch_l_100km * preis
        summe_gewichteter_preis += km * preis

    if gesamt_km <= 0:
        return EAutoErsparnisErgebnis(
            0.0, 0.0, 0.0,
            verbrauch_l_100km, fallback_preis,
        )

    strom_kosten = (
        max(0.0, ladung_netz_kwh_gesamt) * wallbox_strompreis_cent / 100
        + ladung_extern_euro_gesamt
    )
    ersparnis = gesamt_benzin - strom_kosten

    return EAutoErsparnisErgebnis(
        ersparnis_euro=ersparnis,
        benzin_kosten_euro=gesamt_benzin,
        strom_kosten_euro=strom_kosten,
        verwendeter_verbrauch_l_100km=verbrauch_l_100km,
        verwendeter_benzinpreis_euro=summe_gewichteter_preis / gesamt_km,
    )


@dataclass
class EmobPoolAttribution:
    """Pool-Aggregat über E-Auto- und Wallbox-IMDs für evcc-artige Setups.

    Wallbox = Loadpoint-Wahrheit (evcc/Portal-Import schreibt hier),
    E-Auto = Vehicle-Wahrheit (km + ggf. eigene Ladedaten).
    `use_wb_pool` ist True, wenn die Wallbox-Heimladung größer ist als die
    aller E-Autos zusammen — dann fließen die Ladedaten anteilig nach km
    in die E-Auto-Sichten zurück.
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
    """Aggregiert WB- + E-Auto-IMD-`verbrauch_daten` und entscheidet, ob das
    Wallbox-Aggregat als Pool-Quelle für die E-Auto-Sichten dient.

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

    eauto_pool_pv = 0.0
    eauto_pool_netz = 0.0
    eauto_total_km = 0.0
    for d in eauto_imd_data:
        pv, netz = get_emob_pv_netz_kwh(d)
        eauto_pool_pv += pv
        eauto_pool_netz += netz
        eauto_total_km += d.get("km_gefahren", 0) or 0

    use_wb_pool = (wb_pool_pv + wb_pool_netz) > (eauto_pool_pv + eauto_pool_netz)

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


def _summiere_emob_quelle(imd_data: Iterable[dict]) -> EmobLadungPool:
    """Summiert eine Quelle (alle Wallbox- ODER alle E-Auto-IMD) zu einer in
    sich konsistenten Trias. `netz` über den SoT-Helper `get_emob_pv_netz_kwh`
    (liest `ladung_netz_kwh` direkt oder leitet `Total − PV` ab)."""
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


def aggregiere_emob_ladung(
    *,
    eauto_imd_data: Iterable[dict],
    wallbox_imd_data: Iterable[dict],
) -> EmobLadungPool:
    """Poolt E-Auto- + Wallbox-Ladung zu EINER konsistenten Heimladungs-Trias.

    Wallbox (Loadpoint-Sicht) und E-Auto (Vehicle-Sicht) messen oft denselben
    Stromfluss aus zwei Perspektiven. Die Quelle mit der größeren Heimladung
    (`pv + netz`) liefert die komplette Trias — nie feldweise gemischt. Selbe
    use-wb-pool-Entscheidung wie `compute_emob_pool_attribution` /
    EAutoDashboard, damit alle Sichten dieselbe Zahl zeigen.

    Externe Ladung (öffentliche Ladesäulen) wird getrennt entschieden: das
    Paar `(kWh, €)` kommt aus der Quelle mit den höheren externen Kosten —
    extern wird oft nur an einer Investition gepflegt, unabhängig davon, wo
    die Heimladung steht.

    Aufrufer übergibt bereits gefilterte Iterables (nach `ist_aktiv_im_monat`
    und `ist_dienstlich`).
    """
    wb = _summiere_emob_quelle(wallbox_imd_data)
    ea = _summiere_emob_quelle(eauto_imd_data)

    if wb.ladung_kwh >= ea.ladung_kwh:
        heim, name = wb, ("wallbox" if wb.ladung_kwh > 0 else "leer")
    else:
        heim, name = ea, "e-auto"

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
