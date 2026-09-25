"""Vergleichsgroessen von *Cockpit → Monat*: Vorjahresmonat, PVGIS-SOLL, Nachtsockel — und die
Tarifaufloesung (`_zeittarif_preis`), die Vorjahr und Endpunkt teilen.

Die Route konsumiert nur das Ergebnis; alle Funktionen hier lesen keinen Namen, den Tests am
Fassaden-Modul patchen (`datetime`, die fuenf Sammler).
"""
# Reiner Umzug aus `api/routes/aktueller_monat.py` (18.09.2026, Vorlage 1 des Refactorings
# grosser Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# exportiert alle Namen weiter, die Tests und Aufrufer bisher aus dem Modul importierten.

import logging
from datetime import date
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.prognose_auswahl import lade_aktive_monatsprognosen
from backend.services.strompreis_aggregator import wirksamer_arbeitspreis_cent
from backend.api.routes.strompreise import lade_tarife_fuer_anlage
from backend.core.berechnungen import (
    Monatsfenster,
    anteilig,
    berechne_netzbezug_kosten,
    einspeise_erloes_euro,
)
from backend.services.einspeise_erloes_service import get_neg_preis_einspeisung_monat
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.services.eauto_wirtschaftlichkeit import (
    compute_emob_pool_attribution,
    entscheide_emob_heimladung,
)
from backend.services.emob_ladeanteil import reichere_monatszeilen_an_mit_quoten
from backend.services.monats_fakten import lade_monats_fakten
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.core.investition_parameter import ist_dienstlich
from backend.api.routes.aktueller_monat.schemas import SollPv
from backend.api.routes.aktueller_monat.tkonto import _baue_investition_financial

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# N-267: Zeittarif (HT/NT) in Cockpit → Monat
# ─────────────────────────────────────────────────────────────────────────────
#
# ⛔ Diese Route ist die VIERTE Bildungsstelle des Monatspreises, und das
# Konzept zu N-267 hat sie zunaechst uebersehen — es nannte drei
# (`monats_fakten::_lade_tarif`, `finanz_zeilen::baue_finanz_zeile`,
# `strompreise::monats_strompreis_lookup`). Gefunden erst beim Bau von Z2, an
# `netzbezug_preis_effektiv_cent`: aus ihm entstehen hier die
# Netzbezugskosten (`berechne_netzbezug_kosten`), die EV-Ersparnis und das
# ausgelieferte Feld `netzbezug_preis_cent`. Ohne die Einhaengung haette
# Cockpit → Monat den Hochtarif genannt, waehrend Cockpit → Jahr daneben den
# gewichteten Preis zeigt — „zwei Zahlen auf einer Seite", die v4.0.1-Klasse.
#
# ⭐ Die Lehre steht schon in `test_zeittarif_ht_nt.py::test_wz1b_*`: JEDE
# Bildungsstelle braucht ihre eigene Gegenprobe. Die Zaehlung „drei" war eine
# Behauptung, kein Befund — sie kam aus einem Grep ueber Aufrufer des
# Resolvers, und diese Route bildet den Preis eine Ebene darueber.

async def _zeittarif_preis(
    db, anlage_id: int, jahr: int, monat: int, tarif, fallback: float, cache: dict
) -> float:
    """Der wirksame Arbeitspreis (ct/kWh) — mit Zeitfenstern gewichtet.

    ``fallback`` gilt, wenn es die Tarifzeile nicht gibt; ohne Fenster liefert
    der Helfer die Spalte unveraendert zurueck, ohne die Datenbank zu fragen.
    """
    if tarif is None or tarif.netzbezug_arbeitspreis_cent_kwh is None:
        return fallback
    return await wirksamer_arbeitspreis_cent(
        db, anlage_id, jahr, monat, tarif, cache=cache
    )


async def _load_vorjahr(anlage_id: int, investitionen: list[Investition], jahr: int, monat: int, db: AsyncSession) -> Optional[dict]:
    """Lädt Vorjahres-Monatsdaten für Vergleich (Energie + Finanzen).

    Die **anlagenweiten** Mengen kommen aus den Monats-Fakten (ADR-002/**P10**).
    Damit fallen drei Divergenzen, die hier als „D6 / IST-Stand erhalten"
    konserviert waren und den Vorjahresvergleich systematisch zu niedrig
    zeigten — jede davon ist eine sichtbare Zahl:

    - **PV:** je Modul roh gelesen, **ohne** P7-Auflösung. Wer nur das
      Anlagen-Aggregat pflegt, hatte im Vorjahr 0 kWh stehen.
    - **Eigenverbrauch/Autarkie:** handgerechnet **ohne V2H**. Was das E-Auto
      ins Haus zurückspeist, zählt im laufenden Monat, im Vorjahr nicht.
    - **E-Mob-Ladung:** ``max(E-Auto, Wallbox)`` je Feld statt der kanonischen
      Trias aus EINER Quelle (#262) — dieselbe Falle, die der aktuelle Monat
      längst über ``get_emob_heimladung_canonical`` vermeidet.

    Selbst geladen wird nur noch, was **je Investition** hängt: die eMob-Zeilen
    des T-Kontos brauchen die Zuordnung ``inv → verbrauch_daten``, die
    ``MonatsFakt`` mangels per-Investition-Sicht (Register N-2) nicht hergibt.
    """
    from datetime import date as date_type
    vj = jahr - 1

    # Ein Tarif-Cache für beides: die Schicht löst den Stichtag (P8) ohnehin
    # auf, der Finanzblock unten liest denselben Eintrag statt ein zweites Mal
    # zu laden.
    tarif_cache: dict[date, dict] = {}
    # N-267: eigener Cache je Aufruf — begruendet im Block ueber `_zeittarif_preis`
    # bzw. ausfuehrlich in `monats_fakten/` ueber `_komponenten_preis`.
    _zt_cache: dict = {}
    fakten_vj = await lade_monats_fakten(
        db, anlage_id, von=(vj, monat), bis=(vj, monat), tarif_cache=tarif_cache
    )
    fakt = fakten_vj[0] if fakten_vj else None
    # Ohne Zählerzeile gibt es keinen Vergleich — unverändert die Bedingung,
    # unter der die Route bisher `None` lieferte.
    if fakt is None or fakt.meta.monatsdaten is None:
        return None
    md = fakt.meta.monatsdaten

    result: dict = {
        "einspeisung_kwh": md.einspeisung_kwh,
        "netzbezug_kwh": md.netzbezug_kwh,
        "netzbezug_durchschnittspreis_cent": md.netzbezug_durchschnittspreis_cent,
        # #392: variable Einspeisevergütung des Vorjahresmonats
        "einspeise_durchschnittspreis_cent": md.einspeise_durchschnittspreis_cent,
    }

    if fakt.erzeugung.pv_kwh > 0:
        result["pv_erzeugung_kwh"] = round(fakt.erzeugung.pv_kwh, 1)
    if fakt.speicher.ladung_kwh > 0:
        result["speicher_ladung_kwh"] = round(fakt.speicher.ladung_kwh, 1)
    if fakt.speicher.entladung_kwh > 0:
        result["speicher_entladung_kwh"] = round(fakt.speicher.entladung_kwh, 1)
    if fakt.wp.strom_kwh > 0:
        result["wp_strom_kwh"] = round(fakt.wp.strom_kwh, 1)
    if fakt.wp.waerme_kwh > 0:
        result["wp_waerme_kwh"] = round(fakt.wp.waerme_kwh, 1)
    if fakt.wp.modus_strom_kuehlen_kwh > 0:
        result["wp_modus_kuehlen_kwh"] = round(fakt.wp.modus_strom_kuehlen_kwh, 1)
    if fakt.emob.ladung_kwh > 0:
        result["emob_ladung_kwh"] = round(fakt.emob.ladung_kwh, 1)
    if fakt.emob.km > 0:
        result["emob_km"] = round(fakt.emob.km, 1)

    # Per-Investition: die eMob-Zeilen des T-Kontos brauchen die Zuordnung
    # `inv → verbrauch_daten`. DI-2-C: Vor-Anschaffungs-/Nach-Stilllegungs-
    # Monate überspringen — die Anschaffungsdatum-Grenze gilt für ALLE
    # Auswertungen ([[feedback_anschaffungsdatum_grenze]], #236).
    imd_data_by_inv_vj: dict[int, dict] = {}
    _pv_quote_vj = None
    emob_inv_ids = [
        i.id for i in investitionen
        if i.typ in ("e-auto", "wallbox") and not ist_dienstlich(i)
    ]
    if emob_inv_ids:
        imd_result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(emob_inv_ids),
                InvestitionMonatsdaten.jahr == vj,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        inv_by_id_vj = {i.id: i for i in investitionen}
        for imd in imd_result.scalars().all():
            inv = inv_by_id_vj.get(imd.investition_id)
            if inv is None or not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            imd_data_by_inv_vj[imd.investition_id] = imd.verbrauch_daten or {}

        # F-16: auch die Vorjahres-Zeile bekommt den abgeleiteten PV-Anteil.
        # Sie speist die Vorjahres-eMob-Ersparnis, die in Cockpit → Monat direkt
        # neben der laufenden steht — ungeteilt daneben wäre der Vergleich eine
        # Aussage über die Rechenweise statt über das Jahr.
        _wb_ids_vj = {i.id for i in investitionen if i.typ == "wallbox"}
        _keys_vj = list(imd_data_by_inv_vj)
        _daten_vj, _quoten_vj = await reichere_monatszeilen_an_mit_quoten(
            db,
            anlage_id,
            [
                ((vj, monat), inv_id in _wb_ids_vj, imd_data_by_inv_vj[inv_id])
                for inv_id in _keys_vj
            ],
        )
        imd_data_by_inv_vj = dict(zip(_keys_vj, _daten_vj))
        # N-555: die Schätzung aus dem Fahrverbrauch bekommt dieselbe Quote.
        _pv_quote_vj = _quoten_vj.get((vj, monat))

    # Berechnete Energie-Werte — aus der Schicht, also inkl. V2H (Entladung ins
    # Haus zählt wie Speicher-Entladung) und inkl. sonstiger Erzeuger hinter dem
    # Zähler. `pv_erzeugung_kwh` im Result bleibt daneben rein.
    kz = fakt.kennzahlen
    einsp = result.get("einspeisung_kwh", 0) or 0
    netz = result.get("netzbezug_kwh", 0) or 0
    ev = kz.eigenverbrauch_kwh
    gv = kz.gesamtverbrauch_kwh
    result["eigenverbrauch_kwh"] = round(ev, 1)
    result["direktverbrauch_kwh"] = round(kz.direktverbrauch_kwh, 1)
    result["gesamtverbrauch_kwh"] = round(gv, 1) if gv > 0 else None
    result["autarkie_prozent"] = round(kz.autarkie_prozent, 1) if gv > 0 else None

    # Finanzen mit historisch korrektem Tarif berechnen
    try:
        stichtag_vj = date_type(vj, monat, 1)
        tarife_vj = tarif_cache.get(stichtag_vj) or await lade_tarife_fuer_anlage(
            db, anlage_id, target_date=stichtag_vj
        )
        tarif_vj = tarife_vj.get("allgemein")
        if tarif_vj:
            netz_preis = await _zeittarif_preis(
                db, anlage_id, vj, monat, tarif_vj, NETZBEZUG_DEFAULT_CENT, _zt_cache,
            )
            # `is not None` statt truthy — dieselbe Regel wie beim Flex-Tarif
            # vier Zeilen tiefer: seit 08.08.2026 ist **0** die Vorbelegung
            # eines neuen Tarifs (eedc rät keinen EEG-Satz mehr). Mit `or`
            # rechnete genau diese Vorjahres-Zeile still mit 8,2 ct weiter,
            # während alle anderen Sichten 0 nehmen.
            einsp_preis = (
                tarif_vj.einspeiseverguetung_cent_kwh
                if tarif_vj.einspeiseverguetung_cent_kwh is not None
                else EINSPEISEVERGUETUNG_DEFAULT_CENT
            )
            grundpreis = tarif_vj.grundpreis_euro_monat or 0
            # Flexibler Tarif überschreibt wenn vorhanden. `is not None` statt
            # truthy: ein Monats-Ø von 0,0 ct ist bei dynamischem Tarif real
            # (viele Negativpreis-Stunden) und wäre sonst still auf den
            # Tarifpreis zurückgefallen.
            if result.get("netzbezug_durchschnittspreis_cent") is not None:
                netz_preis = result["netzbezug_durchschnittspreis_cent"]
            # #392: der Vergütungssatz des Vorjahresmonats schlägt den
            # Stammwert — dieselbe `is not None`-Regel wie zwei Zeilen darüber.
            if result.get("einspeise_durchschnittspreis_cent") is not None:
                einsp_preis = result["einspeise_durchschnittspreis_cent"]
            if einsp > 0:
                # §51 EEG: Einspeisung in Negativpreis-Stunden ist seit
                # Solarpaket I unvergütet. Wenn das Tages-Aggregat fehlt
                # (Anwender ohne Strompreis-Sensor), greift die alte
                # Berechnung unverändert (None → kein Abzug).
                m_neg = await get_neg_preis_einspeisung_monat(db, anlage_id, vj, monat)
                m_erloes = einspeise_erloes_euro(
                    einspeisung_kwh=einsp,
                    neg_preis_kwh=m_neg,
                    verguetung_ct_kwh=einsp_preis,
                )
                result["einspeise_erloes_euro"] = round(m_erloes.erloes_euro, 2)
            if netz > 0:
                result["netzbezug_kosten_euro"] = round(
                    berechne_netzbezug_kosten(netz, netz_preis, grundpreis), 2
                )
                # Arbeitspreis-Anteil ohne Grundpreis — symmetrisch zum
                # laufenden Monat, damit die Jahres-Summe beide Felder findet.
                result["netzbezug_arbeitspreis_kosten_euro"] = round(
                    netz * netz_preis / 100, 2
                )
            if ev > 0:
                result["ev_ersparnis_euro"] = round(ev * netz_preis / 100, 2)
            einspeise_e = result.get("einspeise_erloes_euro", 0) or 0
            ev_e = result.get("ev_ersparnis_euro", 0) or 0
            netz_k = result.get("netzbezug_kosten_euro", 0) or 0

            # DI-5 (G20-3): gesamtnettoertrag SYMMETRISCH zum aktuellen Monat —
            # inkl. WP- und E-Mob-Ersparnis. Vorher fehlten beide im Vorjahr →
            # das T-Konto-Δ verglich Äpfel (Monat mit WP/eMob) mit Birnen
            # (Vorjahr ohne). Es werden dieselben Leaf-Helfer wie im aktuellen
            # Monat mit den Vorjahres-Tarifen/-Preisen genutzt (kein Formel-Dupli).
            monats_gaspreis_vj = md.gaspreis_cent_kwh
            monats_benzinpreis_vj = md.kraftstoffpreis_euro

            # WP-Ersparnis über die WP-Mengen des Monats — dieselben, die oben
            # angezeigt werden. Der Filter „nur im Vorjahres-Monat AKTIVE WPs"
            # (#236/[[feedback_anschaffungsdatum_grenze]]) steckt in der Schicht;
            # bis C1c stand er hier als zweiter, handgeführter Loop über
            # dieselben Zeilen und lieferte per Konstruktion dieselbe Summe.
            wp_waerme_fin = fakt.wp.waerme_kwh
            wp_strom_fin = fakt.wp.strom_kwh

            wp_ersparnis_vj = 0.0
            if wp_waerme_fin > 0 and wp_strom_fin > 0:
                wp_p_vj = await _zeittarif_preis(
                    db, anlage_id, vj, monat, tarife_vj.get("waermepumpe"),
                    netz_preis, _zt_cache,
                )
                wp_invs_vj = [
                    i for i in investitionen
                    if i.typ == "waermepumpe" and i.ist_aktiv_im_monat(vj, monat)
                ]
                wp_r_vj = berechne_wp_ersparnis(
                    wp_waerme_kwh=wp_waerme_fin,
                    wp_strom_kwh=wp_strom_fin,
                    wp_strompreis_cent=wp_p_vj,
                    wp_parameter=wp_invs_vj[0].parameter if wp_invs_vj else None,
                    monats_gaspreis_cent=monats_gaspreis_vj,
                    # B5/X-5: E-B auch im Vorjahr — der laufende Monat zog den
                    # Kühlstrom ab, sein Vergleichswert ein Jahr davor nicht.
                    strom_kuehlen_kwh=fakt.wp.modus_strom_kuehlen_kwh,
                )
                wp_ersparnis_vj = round(wp_r_vj.ersparnis_euro, 2)

            emob_ersparnis_vj = 0.0
            wb_p_vj = await _zeittarif_preis(
                db, anlage_id, vj, monat, tarife_vj.get("wallbox"),
                netz_preis, _zt_cache,
            )
            _emob_aktiv = [
                i for i in investitionen
                if i.typ in ("e-auto", "wallbox")
                and not ist_dienstlich(i)
                and i.ist_aktiv_im_monat(vj, monat)
                and i.id in imd_data_by_inv_vj
            ]
            _ea_data_vj = [imd_data_by_inv_vj[i.id] for i in _emob_aktiv if i.typ == "e-auto"]
            _wb_data_vj = [imd_data_by_inv_vj[i.id] for i in _emob_aktiv if i.typ == "wallbox"]
            _emob_pool_attr_vj = compute_emob_pool_attribution(
                eauto_imd_data=_ea_data_vj,
                wallbox_imd_data=_wb_data_vj,
            )
            # N-555: der Entscheid des Vorjahresmonats — dieselbe eine Funktion.
            _emob_entscheid_vj = entscheide_emob_heimladung(
                eauto_je_inv={
                    i.id: imd_data_by_inv_vj[i.id] for i in _emob_aktiv if i.typ == "e-auto"
                },
                wallbox_zeilen=_wb_data_vj,
                wallbox_in_betrieb=bool(_wb_data_vj) or any(
                    i.typ == "wallbox" and not ist_dienstlich(i)
                    and i.ist_aktiv_im_monat(vj, monat)
                    for i in investitionen
                ),
                pv_quote=_pv_quote_vj,
            )
            for i in _emob_aktiv:
                _d_vj = _baue_investition_financial(
                    i,
                    imd_data_by_inv_vj[i.id],
                    netz_p=netz_preis,
                    einsp_p=einsp_preis,
                    wp_p=netz_preis,     # für eMob-Zweig irrelevant
                    wb_p=wb_p_vj,
                    monats_gaspreis=monats_gaspreis_vj,
                    monats_benzinpreis=monats_benzinpreis_vj,
                    emob_pool_attr=_emob_pool_attr_vj,
                    emob_entscheid=_emob_entscheid_vj,
                )
                if (
                    _d_vj is not None
                    and _d_vj.ersparnis_label == "Ersparnis vs. Verbrenner"
                    and _d_vj.ersparnis_euro is not None
                ):
                    emob_ersparnis_vj += _d_vj.ersparnis_euro
            emob_ersparnis_vj = round(emob_ersparnis_vj, 2)

            if wp_ersparnis_vj:
                result["wp_ersparnis_euro"] = wp_ersparnis_vj
            if emob_ersparnis_vj:
                result["emob_ersparnis_euro"] = emob_ersparnis_vj
            if einspeise_e or ev_e:
                result["gesamtnettoertrag_euro"] = round(
                    einspeise_e + ev_e + wp_ersparnis_vj + emob_ersparnis_vj - netz_k, 2
                )
    except Exception:
        logger.warning("Vorjahr-Finanzen konnten nicht berechnet werden")

    return result

async def _load_soll_pv(
    anlage_id: int, jahr: int, monat: int, db: AsyncSession, fenster: Monatsfenster,
) -> SollPv:
    """Lädt PVGIS SOLL-Wert für den Monat — aus der AKTIVEN Prognose (P5).

    Vorher stand hier ein `JOIN` auf `ist_aktiv` **ohne `limit`** und ein `sum()`
    darüber: bei zwei aktiven Prognosen kam der Monatswert doppelt zurück (N83).
    Der Fehler war nicht sichtbar, weil die Summe plausibel aussah — sie war nur
    doppelt so groß, und die SOLL/IST-Abweichung sowie die Grundlast-SOLL-Kachel
    rechneten mit. Der Auswahl-SoT trägt das `LIMIT 1` in der Subquery.

    **Im laufenden Monat trägt der Rückgabewert nur die abgelaufenen Tage**
    (N-69, Entscheid Gernot 2026-08-04): PVGIS liefert eine Monatssumme, der IST
    daneben ist angefangen. Ungekürzt maß die Erfüllungsquote das Datum statt
    die Anlage — am 4. August 19 % für eine Anlage, die über die abgeschlossenen
    Monate auf 119 % kam. Begründung der Kürzung im Layer-Docstring
    (`core/berechnungen/monatsfenster.py`); die Jahres-Sicht summiert diese
    Monatswerte und erbt die Korrektur damit ohne eigene Rechnung.
    """
    prognosen = await lade_aktive_monatsprognosen(db, anlage_id, monat=monat)
    if not prognosen:
        return SollPv(None, None)
    voll = sum(p.ertrag_kwh for p in prognosen)
    gekuerzt = anteilig(voll, fenster)
    return SollPv(
        anteilig=round(gekuerzt, 1) if gekuerzt is not None else None,
        monat=round(voll, 1),
    )

async def _load_grundlast_nacht_kw(
    anlage_id: int, jahr: int, monat: int, db: AsyncSession,
) -> list[float]:
    """Nacht-Stunden-Leistungen (0–5 Uhr, verbrauch_kw > 0) des Monats aus dem
    stündlichen Energieprofil — Sourcing für `berechne_grundlast` (ADR-001:
    Formel liegt im Berechnungs-Layer, hier nur die Query). Leer, wenn die Anlage
    keine Stundenprofile hat (dann fällt die Sicht auf PVGIS-SOLL/IST zurück)."""
    from calendar import monthrange
    from backend.models.tages_energie_profil import TagesEnergieProfil

    monat_ende = date(jahr, monat, monthrange(jahr, monat)[1])
    result = await db.execute(
        select(TagesEnergieProfil.verbrauch_kw).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= date(jahr, monat, 1),
            TagesEnergieProfil.datum <= monat_ende,
            TagesEnergieProfil.stunde < 5,
            TagesEnergieProfil.verbrauch_kw.is_not(None),
            TagesEnergieProfil.verbrauch_kw > 0,
        )
    )
    return [float(w) for w in result.scalars().all()]
