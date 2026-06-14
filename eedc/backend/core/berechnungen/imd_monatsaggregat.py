"""Per-Zeilen-Resolver für monatliche per-Typ-IMD-Aggregate (Schläfer-Abbau Block 1).

Single Source of Truth dafür, **welche Felder** eine `InvestitionMonatsdaten`-
Zeile pro Investitions-Typ zu den Monats-Aggregaten beiträgt und **mit welchem
Resolver** sie gelesen werden. Vor dieser Konsolidierung dupliziert jede der
Read-Sites (`aktueller_monat`, `monatsdaten`-`/aggregiert`, `cockpit/komponenten`,
`cockpit/uebersicht`) dieselbe `if inv.typ == "..."`-Schleife — die größte
Drift-Klasse der Read-Pfade (Pool-Bug, #289, #290; siehe
`docs/drafts/BLOCK1-FELD-MATRIX-20260614.md`).

Diese Funktion ist **rein** (kein DB-/Service-I/O, ADR-001): sie nimmt eine
Investition + ihr `verbrauch_daten`-Dict und gibt einen `ImdTypBeitrag` mit allen
kanonisch aufgelösten Skalar-Beiträgen zurück. Jede Read-Site faltet den Beitrag
in ihre eigene Form (flach / pro-Monat-Dict / kumuliert+by_ym) und nimmt die
Felder, die sie braucht. Aktiv-/Stilllegungs- und Dienstwagen-Filter bleiben
**Caller-Sache** (Verhalten je Site erhalten).

NICHT hier: der E-Mob-Heimladungs-**Pool** (`get_emob_heimladung_canonical` /
`compute_emob_pool_attribution`) — der braucht ALLE E-Auto-/Wallbox-Zeilen
zusammen und ist bereits SoT. Dieser Resolver liefert nur die per-Zeilen-
Skalare (km, Fahrverbrauch, V2H) sowie die roh-/kanonisch gelesenen Lade-
Felder, die einzelne Sites direkt (ohne Pool) verwenden.

D1-Entscheid (2026-06-14): WP-Heizung/Wärme werden hier **kanonisch** gelesen
(`get_wp_heizenergie_kwh` inkl. `heizung_kwh`-Legacy-Fallback; `wp_waerme` =
`waerme_kwh` oder `heizung + warmwasser`). Sites, die vorher roh lasen
(`/aggregiert`, Vorjahr-Variante), übernehmen damit die kanonische Semantik.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.field_definitions import (
    get_eauto_ladung_kwh,
    get_pv_erzeugung_kwh,
    get_sonstiges_verbrauch_kwh,
    get_speicher_netzladung_kwh,
    get_wp_heizenergie_kwh,
    get_wp_strom_kwh,
)


@dataclass(frozen=True)
class ImdTypBeitrag:
    """Kanonisch aufgelöste Skalar-Beiträge EINER IMD-Zeile.

    Alle Felder default 0.0/0/False — pro Typ werden nur die relevanten gesetzt.
    `typ` erlaubt dem Caller typ-spezifische Faltung (z. B. Pool-Sammlung) ohne
    eigene `inv.typ`-Abfrage.
    """

    typ: str | None = None

    # PV-Module
    pv_erzeugung: float = 0.0

    # Balkonkraftwerk (BKW) — separat von pv-module gehalten; Caller entscheidet,
    # ob die BKW-Erzeugung zusätzlich in die Gesamt-PV einfließt.
    bkw_erzeugung: float = 0.0
    bkw_eigenverbrauch: float = 0.0
    bkw_speicher_ladung: float = 0.0
    bkw_speicher_entladung: float = 0.0

    # Speicher
    speicher_ladung: float = 0.0
    speicher_entladung: float = 0.0
    speicher_arbitrage: float = 0.0       # Netzladung (get_speicher_netzladung_kwh)
    speicher_ladepreis_cent: float = 0.0  # für gewichteten Ø Ladepreis

    # Wärmepumpe (kanonisch, D1)
    wp_strom: float = 0.0
    wp_heizung: float = 0.0
    wp_warmwasser: float = 0.0
    wp_waerme: float = 0.0
    wp_strom_heizen: float = 0.0
    wp_strom_warmwasser: float = 0.0
    wp_hat_split: bool = False            # getrennte_strommessung aktiv

    # E-Mobilität (Skalar-Summen; Heimladungs-Pool bleibt separat)
    eauto_km: float = 0.0
    eauto_verbrauch: float = 0.0          # gemessener Fahrverbrauch
    eauto_v2h: float = 0.0
    eauto_ladung_kanonisch: float = 0.0   # get_eauto_ladung_kwh (Vorjahr-max-Logik)
    eauto_ladung_pv_netz: float = 0.0     # ladung_pv + ladung_netz (/aggregiert)
    wallbox_ladung: float = 0.0
    wallbox_ladung_pv: float = 0.0

    # Sonstiges
    sonstiges_erzeugung: float = 0.0
    sonstiges_verbrauch: float = 0.0


def _f(data: dict, key: str) -> float:
    """`data.get(key)` als float mit 0-Default (None/fehlend → 0.0)."""
    return float(data.get(key, 0) or 0)


def imd_typ_beitrag(inv, data: dict | None) -> ImdTypBeitrag:
    """Kanonischer per-Zeilen-Beitrag einer IMD-Zeile (`inv`, `data`).

    `inv` braucht `typ` und (für WP-Split) `parameter`. `data` ist das
    `verbrauch_daten`-Dict (oder None/{}).
    """
    data = data or {}
    typ = getattr(inv, "typ", None)

    if typ == "pv-module":
        return ImdTypBeitrag(typ=typ, pv_erzeugung=_f(data, "pv_erzeugung_kwh"))

    if typ == "balkonkraftwerk":
        return ImdTypBeitrag(
            typ=typ,
            bkw_erzeugung=get_pv_erzeugung_kwh(data),
            bkw_eigenverbrauch=_f(data, "eigenverbrauch_kwh"),
            bkw_speicher_ladung=_f(data, "speicher_ladung_kwh"),
            bkw_speicher_entladung=_f(data, "speicher_entladung_kwh"),
        )

    if typ == "speicher":
        return ImdTypBeitrag(
            typ=typ,
            speicher_ladung=_f(data, "ladung_kwh"),
            speicher_entladung=_f(data, "entladung_kwh"),
            speicher_arbitrage=get_speicher_netzladung_kwh(data),
            speicher_ladepreis_cent=_f(data, "speicher_ladepreis_cent"),
        )

    if typ == "waermepumpe":
        params = getattr(inv, "parameter", None) or {}
        hat_split = bool(params.get("getrennte_strommessung"))
        heizung = get_wp_heizenergie_kwh(data)
        warmwasser = _f(data, "warmwasser_kwh")
        # D1: waerme_kwh hat Vorrang, sonst Heizung + Warmwasser (kanonisch).
        waerme = _f(data, "waerme_kwh") or (heizung + warmwasser)
        return ImdTypBeitrag(
            typ=typ,
            wp_strom=get_wp_strom_kwh(data, params),
            wp_heizung=heizung,
            wp_warmwasser=warmwasser,
            wp_waerme=waerme,
            wp_strom_heizen=_f(data, "strom_heizen_kwh"),
            wp_strom_warmwasser=_f(data, "strom_warmwasser_kwh"),
            wp_hat_split=hat_split,
        )

    if typ == "e-auto":
        return ImdTypBeitrag(
            typ=typ,
            eauto_km=_f(data, "km_gefahren"),
            eauto_verbrauch=_f(data, "verbrauch_kwh"),
            eauto_v2h=_f(data, "v2h_entladung_kwh"),
            eauto_ladung_kanonisch=get_eauto_ladung_kwh(data),
            eauto_ladung_pv_netz=_f(data, "ladung_pv_kwh") + _f(data, "ladung_netz_kwh"),
        )

    if typ == "wallbox":
        return ImdTypBeitrag(
            typ=typ,
            wallbox_ladung=_f(data, "ladung_kwh"),
            wallbox_ladung_pv=_f(data, "ladung_pv_kwh"),
        )

    if typ == "sonstiges":
        params = getattr(inv, "parameter", None) or {}
        kategorie = params.get("kategorie", "")
        erzeugung = _f(data, "erzeugung_kwh")
        verbrauch = get_sonstiges_verbrauch_kwh(data)
        if kategorie == "erzeuger":
            verbrauch = 0.0
        elif kategorie == "verbraucher":
            erzeugung = 0.0
        # sonst (leere Kategorie): beide Werte mitnehmen (Site-3-Verhalten)
        return ImdTypBeitrag(typ=typ, sonstiges_erzeugung=erzeugung,
                             sonstiges_verbrauch=verbrauch)

    return ImdTypBeitrag(typ=typ)
