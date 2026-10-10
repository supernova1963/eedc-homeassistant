"""HA-Export, Anlagen-Sensoren — die Komponentenseite: historische Komponenten-Monatswerte (IMD im #236-Fenster, E-Mob-
Anreicherung F-16, Wallbox-Pool F-17) mit den Monatspreisen für Wärmepumpe und Wallbox (DI-4/F-18, P8), die rückblickenden
Alternativkosten-Ersparnisse und CO₂-Aggregate (DI-2, PHEV #331), Jahresersparnis, Kapitaleinsatz, ROI und Amortisation
(F-19) sowie die Speicher-KPIs (N-252).
"""
# Vorlage 8b des Refactorings grosser Dateien (18.09.2026): Phasen des Rechners
# `ha_export/anlage_sensoren.py::calculate_anlage_sensors` byte-identisch als Funktionen, Schnittstelle als
# Schluesselwort-Parameter und Rueckgabe-Dict; der Rechner orchestriert. Kein Verhaltenswechsel —
# Gate ist `plans/skript-golden-master-ha-export.py` (alte gegen neue Antworten, bitgleich).

from sqlalchemy import select
from backend.core.investition_kennwerte import (
    get_speicher_kapazitaet_kwh,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.core.berechnungen import (
    berechne_wp_alternativkosten_ersparnis,
    imd_typ_beitrag,
    speicher_wirkungsgrad,
    vollzyklen as berechne_vollzyklen,
)
from datetime import date
from backend.services.strompreis_aggregator import aufgeloester_monatspreis
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_strompreis_for_komponente,
)
from backend.core.berechnungen.kapitalrechnung import (
    ErsparnisPosten,
    jahres_ersparnis_euro,
    kapitaleinsatz_euro,
)
from backend.services.eauto_wirtschaftlichkeit import (
    berechne_eauto_ersparnis_periode,
    eigener_verbrauch_l_100km,
)
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import InvestitionMonatsdaten
from backend.core.investition_parameter import PARAM_E_AUTO, PARAM_E_AUTO_DEFAULTS, ist_dienstlich
from backend.core.calculations import berechne_co2_bilanz
from backend.services.emob_kontext import lade_emob_kontext
from backend.api.routes.ha_export.emob import (
    _emob_extern_im_monat,
    _emob_heimladung_im_monat,
)
from backend.services.eauto_wirtschaftlichkeit import monate_des_autos


async def historische_komponenten(*, _tarife, anlage, db, investitionen, monatsdaten, strompreis):
    """Wärmepumpen, E-Autos, Wallboxen; IMD im aktiven Fenster laden, E-Mob-Zeilen anreichern (F-16), Pool-Kontext (F-17);
    Netzbezugspreis, Monatsdaten je Periode, WP- und Wallbox-Arbeitspreis je Monat (P8).

    Aus `calculate_anlage_sensors` Zeilen 462-595 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 8b.
    """
    # Alternativkosten-Ersparnisse aus historischen InvestitionMonatsdaten:
    # WP vs. Gas/Öl, E-Auto vs. Benzin, BKW-Eigenverbrauch.
    # Ohne diese Komponenten wäre die Jahresersparnis nur PV-Netto-Ertrag,
    # was bei Anlagen mit WP/E-Auto zu absurd langer Amortisation führt.
    waermepumpen = [i for i in investitionen if i.typ == "waermepumpe"]
    e_autos = [
        i for i in investitionen
        if i.typ == "e-auto" and not ist_dienstlich(i)
    ]

    # IMD vor anschaffungsdatum / nach stilllegungsdatum überspringen (#236):
    # Sonst fließen Werte in HA-Sensor-Aggregate ein, obwohl die Komponente
    # in dem Monat noch gar nicht / nicht mehr aktiv war.
    historische_inv_daten: dict[tuple[int, int, int], dict] = {}
    inv_ids = [i.id for i in investitionen]
    inv_by_id_export = {i.id: i for i in investitionen}
    if inv_ids:
        imd_alle = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(inv_ids))
        )
        _imd_objekte = imd_alle.scalars().all()
        for imd in _imd_objekte:
            inv = inv_by_id_export.get(imd.investition_id)
            if not inv or not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            historische_inv_daten[(imd.investition_id, imd.jahr, imd.monat)] = (
                imd.verbrauch_daten or {}
            )

    # F-16 + Phase 2a + N-555: die E-Mob-Zeilen mit abgeleitetem PV-Anteil und der
    # Entscheid je Monat aus dem einen Kontext (`services/emob_kontext.py`) — mit
    # Dienstwagen, dienstlicher Wallbox, Herkunft von „Heim: gesamt" und den Quellen des
    # laufenden Monats (Konzept Regel 2, 3, 8). Der Pool-Kontext und die
    # Ersparnis-Schleife unten schöpfen beide aus dieser Map.
    _emob_kontext = await lade_emob_kontext(
        db, anlage.id, investitionen, _imd_objekte if inv_ids else [],
    )
    for _key, _daten in _emob_kontext.daten.items():
        if _key in historische_inv_daten:
            historische_inv_daten[_key] = _daten
    emob_ctx = _emob_kontext.ctx

    netzbezug_preis_cent = (
        strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else 30.0
    )

    # Monatsdaten-Dict für Monats-Gaspreis / -Benzinpreis
    md_by_periode = {(md.jahr, md.monat): md for md in monatsdaten}

    # DI-4: WP-Strom mit dem WP-Spezialtarif bewerten (Fallback allgemein), wie
    # in aktueller_monat.py — sonst rechnet der HA-Export die WP-Ersparnis mit
    # dem allgemeinen Netzbezugspreis, obwohl ein günstigerer WP-Tarif gepflegt ist.
    # ADR-002/P8: JE MONAT auflösen — die WP-Ersparnis summiert über die ganze
    # Historie, ein Einheitstarif hätte einen Tarifwechsel rückwirkend über alle
    # Jahre gezogen (dieselbe Klasse wie der Jahresbericht-Drift, #326).
    wp_preis_by_periode: dict[tuple[int, int], float] = {}
    for (_inv_id, _p_jahr, _p_monat) in historische_inv_daten:
        _periode = (_p_jahr, _p_monat)
        if _periode in wp_preis_by_periode:
            continue
        _p_tarife = await lade_tarife_fuer_anlage(
            db, anlage.id, target_date=date(_p_jahr, _p_monat, 1)
        )
        wp_preis_by_periode[_periode] = resolve_strompreis_for_komponente(
            _p_tarife, "waermepumpe", fallback=netzbezug_preis_cent
        )

    # Heutiger WP-Tarif: Fallback für Monate ohne Auflösung und Grundlage der
    # nach vorn gerichteten Sensor-Werte weiter unten. `_tarife` steht seit
    # N-200 schon oben (dieselbe Abfrage, ein Ladevorgang).
    wp_netzbezug_preis_cent = resolve_strompreis_for_komponente(
        _tarife, "waermepumpe", fallback=netzbezug_preis_cent
    )

    # F-18: dasselbe für die WALLBOX. Die WP hatte ihre Monats-Auflösung seit
    # v4.0.5 (#326), die E-Mob-Seite nicht — `bisherige_eauto_ersparnis` unten
    # bewertete die Netzladung der ganzen Historie mit dem HEUTIGEN Tarif und
    # driftete damit gegen den Komponenten-Hub, der längst mittelte. Der Wert
    # steckt über `historischer_netto_ertrag` in vier ausgelieferten Sensoren
    # (`netto_ertrag_euro` · `roi_prozent` · `amortisation_jahre` und dem
    # per-Investition-Sensor `e_auto_ersparnis_vs_benzin_euro`).
    # ⭐ **#412 (11.09.2026): auch dieser Sensor sieht die volle Kaskade.** Bis
    # dahin las die Schleife allein den Wallbox-Tarif — der **abgerechnete**
    # Monats-Ø kam nie an, während Cockpit → Übersicht ihn für dieselbe
    # Ersparnis längst nahm. Zwei Zahlen für eine Größe, je nach Sicht.
    _md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )
    _md_je_monat = {(m.jahr, m.monat): m for m in _md_result.scalars().all()}
    _preis_cache_wb: dict = {}
    wallbox_preis_by_periode: dict[tuple[int, int], float] = {}
    for (_inv_id, _p_jahr, _p_monat) in historische_inv_daten:
        _periode = (_p_jahr, _p_monat)
        if _periode in wallbox_preis_by_periode:
            continue
        _p_tarife = await lade_tarife_fuer_anlage(
            db, anlage.id, target_date=date(_p_jahr, _p_monat, 1)
        )
        # Der Wallbox-Tarif bleibt Stufe 4 (`stammpreis_override`) — er geht
        # nicht verloren, nur ein gepflegter oder gemessener Ø schlägt ihn.
        wallbox_preis_by_periode[_periode] = (await aufgeloester_monatspreis(
            db, anlage.id, _p_jahr, _p_monat, _md_je_monat.get(_periode),
            _p_tarife.get("allgemein"),
            stammpreis_override=resolve_strompreis_for_komponente(
                _p_tarife, "wallbox", fallback=netzbezug_preis_cent
            ),
            cache=_preis_cache_wb,
        )).cent
    wallbox_netzbezug_preis_cent = resolve_strompreis_for_komponente(
        _tarife, "wallbox", fallback=netzbezug_preis_cent
    )
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("e_autos", "emob_ctx", "historische_inv_daten", "inv_by_id_export", "md_by_periode", "waermepumpen", "wallbox_netzbezug_preis_cent", "wallbox_preis_by_periode", "wp_netzbezug_preis_cent", "wp_preis_by_periode",) if k in _loc}


def alternativkosten_und_co2(
    *,
    e_autos,
    eigenverbrauch_ohne_verluste,
    emob_ctx,
    historische_inv_daten,
    inv_by_id_export,
    md_by_periode,
    waermepumpen,
    wallbox_netzbezug_preis_cent,
    wallbox_preis_by_periode,
    wp_netzbezug_preis_cent,
    wp_preis_by_periode,
):
    """WP-Ersparnis gegenüber Gas/Öl (Layer-SoT) und je Gerät, E-Auto-Ersparnis je Fahrzeug mit PHEV-Anteil (#331),
    E-Mob- und WP-CO₂-Aggregate, die Gesamt-CO₂-Bilanz (DI-2).

    Aus `calculate_anlage_sensors` Zeilen 596-750 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 8b.
    """
    # WP-Alternativkosten (vs. Gas/Öl) über den Berechnungs-Layer (ADR-001):
    # per-WP-Parameter (kein last-write-wins über waermepumpen), per-Monat-
    # Gaspreis aus Monatsdaten mit Fallback auf den WP-Parameter-Default.
    # F-20: **je Wärmepumpe einzeln**, damit jeder Posten seine eigene
    # Monatszahl behält. Ein Sammelaufruf lieferte nur eine Summe — und die
    # wurde anschließend mit der Monatszahl der ANLAGE annualisiert, obwohl
    # eine 2024 nachgerüstete WP nur einen Teil davon lief.
    bisherige_wp_ersparnis = 0.0
    wp_posten: list[ErsparnisPosten] = []
    for _wp in waermepumpen:
        _wp_summe = berechne_wp_alternativkosten_ersparnis(
            [_wp],
            historische_inv_daten,
            {k: md.gaspreis_cent_kwh for k, md in md_by_periode.items()},
            wp_preis_by_periode,
            wp_netzbezug_preis_cent,
        )
        _wp_monate = len({
            (j, m) for (inv_id, j, m) in historische_inv_daten if inv_id == _wp.id
        })
        bisherige_wp_ersparnis += _wp_summe
        wp_posten.append(ErsparnisPosten(
            bezeichnung=f"Wärmepumpe {_wp.bezeichnung}",
            summe_euro=_wp_summe,
            monate=_wp_monate,
        ))

    # Per-E-Auto-Aufschlüsselung der bisherige-Ersparnis. Vorher las eine
    # `for ea`-Schleife `benzinpreis_default` + `vergleich_l_100km` in zwei
    # globale Variablen (last-write-wins). Bei zwei E-Autos mit
    # unterschiedlichen Parametern wurden BEIDE mit den Werten des LETZTEN
    # gerechnet → `jahres_ersparnis_euro`, `roi_prozent` und
    # `amortisation_jahre`-HA-Sensoren waren falsch. Zusätzlich fehlte der
    # `md.kraftstoffpreis_euro`-Monatspreis-Fallback (EU OB) — der Anlage-
    # Sensor driftete deshalb auch gegen den per-Investition-Sensor
    # `e_auto_ersparnis_vs_benzin_euro` (Zeile 583+, der hatte den Fallback).
    bisherige_eauto_ersparnis = 0.0
    # DI-2: E-Mob-CO₂-Aggregate (Dienstwagen bereits über e_autos ausgeschlossen,
    # deckungsgleich mit der Cockpit-Bilanz): gefahrene km, Heim-Netzladung und
    # der Benzin-Vergleichsverbrauch in Litern (je Fahrzeug sein eigener Wert).
    co2_emob_km = 0.0
    co2_emob_netz_kwh = 0.0
    co2_benzin_liter = 0.0
    # #331: die PHEV-Aufteilung wird NACH der Schleife je Fahrzeug **einmal für
    # den ganzen Zeitraum** bestimmt — exakt wie in
    # `berechne_eauto_ersparnis_periode`, die das Cockpit rechnet. Monatsweise
    # aufzuteilen wäre genauer und würde genau deshalb driften.
    #
    # N-181/F-18: die **Rechnung** liegt seit 2026-08-08 im Layer-SoT
    # `berechne_eauto_ersparnis_periode`; diese Schleife sammelt nur noch die
    # Eingänge und die CO₂-Aggregate. Vorher stand hier eine wortgleiche Kopie
    # der Formel — inklusive einer eigenen, abweichenden Preisauflösung, und
    # genau daran ist sie gedriftet.
    _ea_km_pro_monat: dict[int, list[tuple[int, int, float]]] = {}
    _ea_netz_pro_monat: dict[int, list[tuple[int, int, float]]] = {}
    _ea_netz_total: dict[int, float] = {}
    _ea_fahrverbrauch: dict[int, float] = {}
    _ea_extern_euro: dict[int, float] = {}
    for ea in e_autos:
        params = ea.parameter or {}
        ea_vergleich_l_100km = params.get(
            PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"],
            PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
        ) or PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"]
        inv_id = ea.id
        # N-555 Stufe 2: auch die Monate ohne Zeile, in denen das Auto Rest der Wallbox
        # bekommt (`monate_des_autos`, Konzept Regel 2 Schritt 3).
        for jahr, monat, daten in monate_des_autos(emob_ctx, ea.id, historische_inv_daten):
            km = daten.get("km_gefahren", 0) or 0
            # #262/Phase 2a/N-555: Netz DIESES Autos nach dem Entscheid des
            # Monats — Wallbox-Anteil nach km, eigene Heim-Felder, Schätzung, 0.
            _, netz = _emob_heimladung_im_monat(emob_ctx, inv_id, km, jahr, monat, daten)
            # N-555 (§11): externe Ladekosten nach der Topf-Regel (`waehle_extern_paar`).
            _ea_extern_euro[ea.id] = _ea_extern_euro.get(ea.id, 0.0) + _emob_extern_im_monat(
                emob_ctx, km, jahr, monat, daten,
            )[1]
            # DI-2: CO₂-Aggregate mitziehen (gleicher Netz-/km-/Benzin-Pfad).
            co2_emob_km += km
            co2_emob_netz_kwh += netz
            co2_benzin_liter += km / 100 * ea_vergleich_l_100km
            _ea_netz_total[ea.id] = _ea_netz_total.get(ea.id, 0.0) + netz
            if netz > 0:
                _ea_netz_pro_monat.setdefault(ea.id, []).append((jahr, monat, netz))
            if km > 0:
                _ea_km_pro_monat.setdefault(ea.id, []).append((jahr, monat, km))
                _ea_fahrverbrauch[ea.id] = _ea_fahrverbrauch.get(ea.id, 0.0) + (
                    daten.get("verbrauch_kwh", 0) or 0
                )

    # #331: der fossile Anteil eines Plug-in-Hybrids — als Kosten UND als
    # geminderte CO₂-Vermeidung. Ohne gepflegtes `eigener_verbrauch_l_100km`
    # bleibt beides 0 und der Export trägt exakt dieselben Zahlen wie vorher.
    # Die Kosten-Seite kommt jetzt aus dem SoT (`fossile_kosten_euro`), die
    # CO₂-Seite bleibt hier — sie ist keine Geldgröße.
    _benzinpreis_lookup_export = {
        k: md.kraftstoffpreis_euro for k, md in md_by_periode.items()
    }
    co2_fossil_liter = 0.0
    emob_posten: list[ErsparnisPosten] = []
    for ea in e_autos:
        km_pro_monat = _ea_km_pro_monat.get(ea.id, [])
        # ⭐ N-555 Stufe 2 (Konzept Regel 2, E6): hier stand `if not km_pro_monat` — ein
        # Auto, das geladen hat, aber nie gefahren ist, verlor still seine Stromrechnung
        # (dasselbe `km > 0`-Tor wie in der Übersicht).
        if not km_pro_monat and not _ea_netz_pro_monat.get(ea.id):
            continue
        _erg = berechne_eauto_ersparnis_periode(
            km_pro_monat=km_pro_monat,
            ladung_netz_kwh_gesamt=_ea_netz_total.get(ea.id, 0.0),
            # N-555 (§11, Entscheid Gernot 25.09.2026 „angleichen"): externe
            # Ladekosten gehören in die Stromkosten — so rechnen Cockpit, Hub
            # und T-Konto. Hier stand bis dahin bewusst 0,0 (beim Umhängen der
            # Preisachse nicht nebenbei gefüllt); der Anlagen-Sensor lag damit um
            # genau diese Kosten über dem Cockpit. Einmaliger Sprung in der
            # HA-Langzeitstatistik, im CHANGELOG angekündigt.
            ladung_extern_euro_gesamt=_ea_extern_euro.get(ea.id, 0.0),
            wallbox_strompreis_cent=wallbox_netzbezug_preis_cent,
            eauto_parameter=ea.parameter,
            monats_benzinpreis_lookup=_benzinpreis_lookup_export,
            fahrverbrauch_kwh_gesamt=_ea_fahrverbrauch.get(ea.id) or None,
            monats_strompreis_lookup=wallbox_preis_by_periode,
            netz_pro_monat=_ea_netz_pro_monat.get(ea.id) or None,
        )
        bisherige_eauto_ersparnis += _erg.ersparnis_euro
        # F-20: die Monatszahl DIESES Fahrzeugs — `km_pro_monat` ist genau die
        # Liste der Monate, aus denen `ersparnis_euro` stammt.
        emob_posten.append(ErsparnisPosten(
            bezeichnung=f"E-Auto {ea.bezeichnung}",
            summe_euro=_erg.ersparnis_euro,
            # N-555 Stufe 2: ein Auto ganz ohne km (E6) zählt die Monate seiner
            # Netzladung; sonst unverändert die km-Monate (F-20).
            monate=len({(j, m) for (j, m, _km) in km_pro_monat}) or len(
                {(j, m) for (j, m, _n) in _ea_netz_pro_monat.get(ea.id, [])}
            ),
        ))
        eigener_l = eigener_verbrauch_l_100km(ea.parameter)
        if eigener_l is not None and _erg.km_verbrenner > 0:
            co2_fossil_liter += _erg.km_verbrenner / 100 * eigener_l

    # DI-2: WP-CO₂-Aggregate (gemessene Wärme/Strom) über den kanonischen
    # Zeilen-Helper `imd_typ_beitrag` — dieselbe Wärme-/Strom-Auflösung wie das
    # Cockpit (waerme_kwh-Vorrang, sonst Heizung+Warmwasser; WP-Split-Strom).
    wp_ids = {w.id for w in waermepumpen}
    co2_wp_waerme_kwh = 0.0
    co2_wp_strom_kwh = 0.0
    co2_wp_kuehlen_kwh = 0.0
    for (inv_id, _j, _m), daten in historische_inv_daten.items():
        if inv_id in wp_ids:
            _b = imd_typ_beitrag(inv_by_id_export[inv_id], daten)
            co2_wp_waerme_kwh += _b.wp_waerme
            co2_wp_strom_kwh += _b.wp_strom
            co2_wp_kuehlen_kwh += _b.wp_modus_strom_kuehlen

    # DI-2: Gesamt-CO₂-Bilanz (PV-Eigenverbrauch + WP + E-Mob) über den
    # kanonischen Helper — deckungsgleich mit der Cockpit-Kachel `co2_gesamt_kg`.
    co2_ersparnis = berechne_co2_bilanz(
        # N-588 (P15): der Eigenverbrauch ohne die bewertbaren Wandlungsverluste (`anlage_energie.py`).
        eigenverbrauch_kwh=eigenverbrauch_ohne_verluste,
        wp_waerme_kwh=co2_wp_waerme_kwh,
        wp_strom_kwh=co2_wp_strom_kwh,
        # #263 K-2 (E-B): Kühlen ersetzt keine Heizung.
        wp_strom_kuehlen_kwh=co2_wp_kuehlen_kwh,
        emob_km=co2_emob_km,
        emob_netz_ladung_kwh=co2_emob_netz_kwh,
        benzin_verbrauch_liter=co2_benzin_liter,
        fossil_getankt_liter=co2_fossil_liter,
    ).co2_gesamt_kg
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("bisherige_eauto_ersparnis", "bisherige_wp_ersparnis", "co2_ersparnis", "emob_posten", "wp_posten",) if k in _loc}


def ertrag_und_amortisation(
    *,
    betriebskosten_ges,
    bisherige_eauto_ersparnis,
    bisherige_wp_ersparnis,
    emob_posten,
    jahres_ertraege_ges,
    monatsdaten,
    netto_ertrag,
    relevante_kosten,
    sonstige_ausgaben_gesamt,
    sonstige_ertraege_gesamt,
    wp_posten,
):
    """Historischer Netto-Ertrag (P9: kein eigener BKW-Posten), Bilanz ohne sonstige Ausgaben (F-19), Jahresersparnis je
    Posten mit eigener Monatsbasis, Kapitaleinsatz, ROI und Amortisation.

    Aus `calculate_anlage_sensors` Zeilen 751-815 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 8b.
    """
    # BKW: KEIN eigener Posten mehr (ADR-002/P9). Die Ersparnis steckt seit
    # 2026-07-31 in `netto_ertrag` — entweder über die gemeinsame PV-Basis der
    # Finanz-Zeilen (Erzeugung erfasst) oder über deren Rest-Eigenverbrauchs-
    # Term (nicht erfasst), beides mit dem Preis DES MONATS. Der frühere
    # Zuschlag hier rechnete mit einem statischen Netzbezugspreis und tauchte
    # im Sensor `netto_ertrag_euro` gar nicht auf, nur in ROI/Amortisation.
    historischer_netto_ertrag = (
        netto_ertrag
        + bisherige_wp_ersparnis
        + bisherige_eauto_ersparnis
    )

    # F-19: für die KAPITALRECHNUNG ohne die sonstigen AUSGABEN — sie stehen ab
    # hier im Nenner. Ohne diesen Abzug stünde dieselbe Reparatur zweimal in
    # derselben Formel.
    #
    # §8/3 (2026-08-10): und **ohne die sonstigen Erträge**. Eine Position im
    # Monatsabschluss ist per Form einmal geflossen (§2/2) und wird deshalb
    # nicht in die Zukunft verlängert — sonst hätte eine einmalige Förderung
    # jedes künftige Jahr erhöht, spiegelbildlich zu F-19. Wer einen
    # *wiederkehrenden* Ertrag meint, pflegt ihn seit §8/1 als „Ertrag/Jahr" an
    # der Investition; der steht als eigener Summand in `jahres_ertraege_ges`.
    #
    # Der Sensor `netto_ertrag_euro` behält beide Seiten: er ist die
    # Zeitraum-Bilanz („was hat der Zeitraum eingebracht?"), und dort ist eine
    # Reparatur ein Aufwand und eine Förderung ein Ertrag des Zeitraums.
    # Trennlinie: `core/berechnungen/kapitalrechnung.py`.
    bilanz_ohne_sonstige = (
        netto_ertrag + sonstige_ausgaben_gesamt - sonstige_ertraege_gesamt
    )

    # Jahresersparnis — **jeder Posten mit seiner eigenen Monatszahl** (F-20).
    # `netto_ertrag` ist die Anlagenbilanz und gehört zu allen erfassten
    # Monaten; WP und E-Autos bringen ihre eigene Laufzeit mit. Vorher lief
    # alles durch `len(monatsdaten)`, und jede nachgerüstete Komponente wurde
    # dadurch verdünnt — bei vollem Kostenanteil im Nenner.
    anzahl_monate = len(monatsdaten)
    ersparnis_posten = [
        ErsparnisPosten("Anlagenbilanz", bilanz_ohne_sonstige, anzahl_monate),
        *wp_posten,
        *emob_posten,
    ]
    jahres_ersparnis = jahres_ersparnis_euro(
        ersparnis_posten,
        betriebskosten_jahr_euro=betriebskosten_ges,
        jahres_ertraege_euro=jahres_ertraege_ges,
    )

    # ROI und Amortisation. Nenner ist der Kapitaleinsatz (F-19): relevante
    # Kosten + die kumulierten sonstigen AUSGABEN, die bis 2026-08-09 im
    # Zähler standen und dort annualisiert wurden — **minus die kumulierten
    # sonstigen ERTRÄGE** (Bauschritt 7, 2026-08-10). Beide Seiten des
    # Monatsabschlusses stehen damit im Nenner; im Zähler
    # (`bilanz_ohne_sonstige`) sind sie seit §8/3 ohnehin nicht mehr.
    kapitaleinsatz = kapitaleinsatz_euro(
        relevante_kosten_euro=relevante_kosten,
        sonstige_ausgaben_euro=sonstige_ausgaben_gesamt,
        sonstige_ertraege_euro=sonstige_ertraege_gesamt,
    )
    roi_prozent = None
    amortisation_jahre = None
    if kapitaleinsatz > 0 and jahres_ersparnis > 0:
        roi_prozent = (jahres_ersparnis / kapitaleinsatz) * 100
        amortisation_jahre = kapitaleinsatz / jahres_ersparnis
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("amortisation_jahre", "ersparnis_posten", "jahres_ersparnis", "kapitaleinsatz", "roi_prozent",) if k in _loc}


def speicher_kpis(*, batterie_entladung, batterie_ladung, investitionen):
    """Speicher-Kapazität aus den Investitionen, Wirkungsgrad über den Layer-SoT (N-252) und Zyklen.

    Aus `calculate_anlage_sensors` Zeilen 816-863 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 8b.
    """
    # Speicher-KPIs berechnen
    speicher_effizienz = None
    speicher_zyklen = None

    # Speicher-Kapazität aus Investitionen ermitteln
    speicher_kapazitaet = 0
    for inv in investitionen:
        if inv.typ == 'speicher' and inv.parameter:
            # Zyklen-Basis ist die BRUTTO-Kapazität — dieselbe Konvention wie in
            # Monatsbericht, Speicher-Dashboard und Jahresbericht
            # (docs/BERECHNUNGEN.md §3.3). Der Kommentar behauptete hier
            # früher, `nutzbare_kapazitaet_kwh` sei ein Override; der Code liest
            # aber bewusst zuerst Brutto. Ein Dreher hätte den HA-Sensor gegen
            # den Monatsbericht laufen lassen (R22-4). `nutzbare_kapazitaet_kwh`
            # ist nur der Fallback, wenn Brutto nicht gepflegt ist; ist beides
            # leer → kein Speicher gepflegt.
            #
            # A31-2: die Lese-REIHENFOLGE bleibt genau so — dies ist der
            # Vollzyklen-Nenner, und der ist brutto (Kanon
            # `core/berechnungen/speicher.py::vollzyklen`, Entscheidung Gernot
            # 2026-07-28). Der Netto-Umstieg von A31-2 gilt für Simulation und
            # Wirtschaftlichkeits-Prognose, NICHT hier. Migriert ist nur der
            # Zugriffsweg: statt zweier Roh-Lesungen die beiden SoT-Helper —
            # `get_speicher_nutzbare_kapazitaet_kwh` greift erst, wenn brutto
            # `None` ist, und liefert dann den Netto-Wert (sein eigener
            # Brutto-Fallback läuft in diesem Fall ins Leere). Identisches
            # Verhalten, nur ohne Literal-Zugriff.
            kap = get_speicher_kapazitaet_kwh(inv) or get_speicher_nutzbare_kapazitaet_kwh(inv)
            if kap:
                speicher_kapazitaet += float(kap)

    # η über den Layer-SoT (N-252) — dieselbe Regel wie Cockpit, Komponenten
    # und Speicher-Dashboard. Der Zeitraum ist hier ein ganzes Jahr, deshalb
    # `fenster_lang`; die Obergrenze gilt trotzdem.
    #
    # ⚠ Bewusste Folge für Home Assistant (Entscheid Gernot 17.08.2026): Wo der
    # Quotient über 100 % liegt, liefert eedc jetzt GAR KEINEN Sensorwert mehr
    # statt einer unmöglichen Zahl (`value` bleibt ungesetzt ⇒ der Sensor
    # meldet `unknown`). Das reißt genau an den Tagen eine Lücke in die
    # HA-Langzeitstatistik, an denen dort bisher ein falscher Wert stand —
    # dieselbe Klasse wie der einmalige LTS-Sprung des CO₂-Sensors unter DI-2.
    _eta_ha = speicher_wirkungsgrad(
        batterie_ladung, batterie_entladung, None, langes_fenster_quelle="fenster_lang"
    )
    speicher_effizienz = _eta_ha.prozent
    # Layer-SoT statt eigener Division — dieselbe Zahl wie Hub/Monat/PDF.
    speicher_zyklen = berechne_vollzyklen(batterie_entladung, speicher_kapazitaet)
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("speicher_effizienz", "speicher_kapazitaet", "speicher_zyklen",) if k in _loc}

