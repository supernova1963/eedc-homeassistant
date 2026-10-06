"""Energie-Profil — der einzelne Tag.

GET /api/energie-profil/{anlage_id}/tag-detail — snapshot-teure Tages-Detailwerte (Cockpit → Tag)
GET /api/energie-profil/{anlage_id}/tag-status — warum ein Tag leer ist, und was hilft (F-2)

Dazu die W-18-Grund-Formulierer fuer Groessen aus mehreren Feldern.
"""
# Reiner Umzug aus `api/routes/energie_profil/views.py` (18.09.2026, Vorlage 4 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `views.py` haengt den Router ein und
# exportiert die Endpunkt-Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.monats_fakten import lade_monats_fakten
from ._shared import TagDetailResponse, TagStatusResponse

router = APIRouter()


def _grund_gewinner(
    grund_je_feld: dict[str, str], keys: tuple[str, ...],
) -> Optional[tuple[str, str]]:
    """``(ausgabe_key, grund)`` des aussagekräftigsten Grundes — oder ``None``.

    Die gemeinsame Hälfte der beiden Formulierer darunter. Sie ein zweites Mal
    hinzuschreiben wäre die F-56-Klasse: zwei Stellen, dieselbe Rangfolge, und
    die Kurzform würde beim nächsten Zustand einen anderen Gewinner nennen als
    die Langform.
    """
    from backend.core.tageswert_grund import GRUND_RANG

    treffer = [(k, grund_je_feld[k]) for k in keys if k in grund_je_feld]
    if not treffer:
        return None
    return max(treffer, key=lambda kg: GRUND_RANG.get(kg[1], -1))

def _tageswert_grund_kurz_kombiniert(
    grund_je_feld: dict[str, str], keys: tuple[str, ...],
) -> Optional[str]:
    """Die **Kurzform** für eine Größe aus mehreren Feldern — für Sperr-Gründe."""
    from backend.core.tageswert_grund import tageswert_grund_kurz

    gewinner = _grund_gewinner(grund_je_feld, keys)
    return tageswert_grund_kurz(gewinner[1]) if gewinner else None

def _tageswert_grund_kombiniert(
    grund_je_feld: dict[str, str], keys: tuple[str, ...],
) -> Optional[str]:
    """Der Grund für eine Größe, die aus **mehreren** Feldern entsteht (W-18).

    Die Tages-Wärme ist ``Heizwärme + Warmwasser``. Fehlen beide, gibt es zwei
    Gründe — und es wäre irreführend, den erstbesten zu nennen: Wer den
    Wärmemengenzähler für die Heizung zugeordnet hat und den fürs Warmwasser
    nicht, soll nicht lesen „kein Zähler zugeordnet". Deshalb gewinnt der
    aussagekräftigere (``GRUND_RANG``) — dieselbe Rangfolge wie in der Erhebung.

    Fehlt für **keines** der Felder ein Grund, gibt es nichts zu sagen.
    """
    from backend.core.tageswert_grund import tageswert_grund_text

    gewinner = _grund_gewinner(grund_je_feld, keys)
    if gewinner is None:
        return None
    key, grund = gewinner
    return tageswert_grund_text(grund, key)

@router.get("/{anlage_id}/tag-detail", response_model=TagDetailResponse)
async def get_tag_detail(
    anlage_id: int,
    datum: date = Query(..., description="Tag (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """Snapshot-teure Tages-Detailwerte für Cockpit/Tag (D1 „maximal erheben",
    SPEC-COCKPIT-TAG-JAHR Abschnitt F/I): WP-Strom-Split + WP-Wärme (Heizung/
    Warmwasser, nur mit Wärmemengenzähler), Speicher-Netzladung + effektiver
    Ladepreis, E-Mob PV-/Netz-Anteil der Ladung, PV-Tages-SOLL (OM × eedc-
    Lernfaktor) und Tagestarif (für Wirkungsverluste €/Tarif-Zeile). Alles
    tagesgenau aus Snapshots/TEP/Prognose. Bewusst EIN Aufruf pro gewähltem Tag
    (nicht über die 90-Tage-Werte-Spanne), da Snapshot-Boundary-Diffs teuer sind.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    inv_result = await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))
    investitionen_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}

    from backend.services.snapshot.aggregator import get_tagesdetail_kwh
    from backend.services.speicher_wirtschaftlichkeit import berechne_effektiver_ladepreis
    from backend.services.finanz_zeilen import FinanzZeileEingabe, baue_finanz_zeile
    from backend.api.routes.live_wetter import _get_lernfaktor

    from backend.services.snapshot.boundary_range import tageszeile_ist_rueckwaerts

    # ⛔ **N-434/N-435: Die Tageszeile wird ZUERST gelesen**, weil ihre Herkunft
    # das Fenster aller Wärmepumpen-Zähler dieses Tages bestimmt. Im HA-Add-on
    # steht `komponenten_kwh` als Σ der 24 LTS-Slots [Vortag 23:00, 23:00);
    # Teilmengen (Betriebsart-Zähler) und Gegenstücke (Wärme der Arbeitszahl)
    # desselben Geräts müssen im selben Fenster stehen — sonst wird die
    # Differenz zweier Randstunden zu „nicht aufgeteilt" bzw. zu einer falschen
    # Arbeitszahl.
    tz_zeile = (await db.execute(
        select(
            TagesZusammenfassung.komponenten_kwh,
            TagesZusammenfassung.source_provenance,
            TagesZusammenfassung.verworfen,
        ).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum == datum,
        )
    )).one_or_none()
    tz_komp = tz_zeile[0] if tz_zeile else None
    # HA-Bauform E4a-2 (Umschaltstelle 4): an einem Kanal-Tag kommen die Bilanz-Schlüssel aus den Kanälen (B-3);
    # gelesen werden hier heute nur die WP-Schlüssel, die aus der Tageszeile bleiben.
    from backend.services.kanal.bilanz_leser import bilanz_ziele, kanal_tage, mische_komponenten

    _kanal = (await kanal_tage(db, anlage_id, datum, datum)).get(datum)
    if _kanal is not None:
        tz_komp = mische_komponenten(tz_komp, _kanal, (await bilanz_ziele(db, anlage_id, [datum]))[datum])
    tz_rueckwaerts = tageszeile_ist_rueckwaerts(
        tz_zeile[1] if tz_zeile else None, tz_zeile[2] if tz_zeile else None,
    )

    _tagesdetail = await get_tagesdetail_kwh(
        db, anlage, investitionen_by_id, datum,
        tageszeile_rueckwaerts=tz_rueckwaerts,
    )
    detail = _tagesdetail.werte
    # W-18: Warum ein Tageswert fehlt. Der Grund wird **hergeleitet**, nicht
    # geraten — bis zum 26.08.2026 hing der Client an jedes „—" denselben Satz
    # „Sensor zuordnen", auch bei zugeordnetem Zähler (dietmar1968, T89667 #210).
    _grund = _tagesdetail.grund_je_feld
    eff = await berechne_effektiver_ladepreis(db, anlage_id=anlage_id, von=datum, bis=datum)

    # PV Tages-SOLL = OM-Tagesprognose × eedc-Lernfaktor (wie Genauigkeits-Tracking).
    tz_prog = await db.execute(
        select(TagesZusammenfassung.pv_prognose_kwh).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum == datum,
        )
    )
    pv_prognose = tz_prog.scalar_one_or_none()
    lernfaktor = await _get_lernfaktor(anlage_id, db, quelle="openmeteo")
    soll_pv = round(pv_prognose * lernfaktor, 1) if (pv_prognose and lernfaktor) else pv_prognose

    # Tagestarif (Monatstarif je Tag) — Preise hängen nicht von Mengen ab.
    # Die Monatsdaten-Zeile muss mit: bei dynamischem Tarif trägt sie den
    # abgerechneten Monats-Ø, der den Stammdaten-Arbeitspreis schlägt. Ohne sie
    # nennt die Tarif-Zeile hier einen anderen Preis als Cockpit/Monat.
    md_tag = (await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == datum.year,
            Monatsdaten.monat == datum.month,
        )
    )).scalar_one_or_none()
    tarif = await baue_finanz_zeile(
        db,
        anlage_id,
        FinanzZeileEingabe(jahr=datum.year, monat=datum.month, monatsdaten=md_tag),
        tarif_cache={},
    )

    # ── Der Preis DIESES Tages (SOLL Flex-Tarife P-2, 17.09.2026) ──
    #
    # Die Zeile darüber liefert den **Monats**preis; bis hierher war er auch der
    # Preis des Tages. Wo Slot-Preise mitgeschrieben sind, ist der Tages-Ø die
    # feinere und damit richtige Quelle — und dieselbe, mit der die Tages-
    # Tabelle (`services/energie_profil/tage_werte.py`) seit demselben Bau
    # rechnet. Ohne diesen Block nennten die beiden Tagessichten verschiedene
    # Preise für denselben Tag (die F-18-Klasse).
    from backend.api.routes.strompreise import lade_tarife_je_stichtag as _ltjs
    from backend.services.strompreis_aggregator import lade_slot_kosten_je_tag

    _stichtag = date(datum.year, datum.month, 1)
    _tarife_tag = await _ltjs(db, anlage_id, [_stichtag])
    _slot_kosten = await lade_slot_kosten_je_tag(
        db, anlage_id, von=datum, bis=datum,
        tarif_fuer=lambda _t: (_tarife_tag.get(_stichtag) or {}).get("allgemein"),
        abgerechnet_fuer=lambda _t: getattr(
            md_tag, "netzbezug_durchschnittspreis_cent", None
        ) if md_tag else None,
    )
    _slot_tag = _slot_kosten.get(datum)
    netzbezug_preis_tag = (
        _slot_tag.mittel_cent if _slot_tag is not None and _slot_tag.mittel_cent is not None
        else tarif.netzbezug_preis_cent
    )
    netzbezug_preis_herkunft_tag = _slot_tag.herkunft if _slot_tag is not None else None

    # #263/T2 — die Aufteilung Heizen/Kühlen des Tages, anlagenweite Σ.
    #
    # Die Rechnung ist ohnehin tagesweise (`falte_modus_split_tag`); die
    # Monatssicht summiert sie nur hinterher auf. Hier bleibt sie eine Ebene
    # früher stehen — derselbe Ladepfad, dieselbe Faltung.
    #
    from backend.core.berechnungen import waermepumpe_kwh_je_investition
    from backend.core.berechnungen.tages_stapel import (
        beitrag_abzug_kwh, beitraege_des_tages, falte_tages_stapel,
    )
    from backend.core.berechnungen.wp_tages_praezedenz import (
        QUELLE_TAGESRAND, loese_wp_tagesstrom_auf,
    )
    from backend.core.berechnungen.waermepumpe_kennzahl import (
        GRUND_FUNKTION_NICHT_DECKUNGSGLEICH, abgrenzungs_grund,
        ARBEITSZAHL_FUNKTIONEN, abgrenzung_je_funktion,
        als_arbeitszahl, arbeitszahl, arbeitszahl_je_funktion,
        arbeitszahl_kuehlen,
        deckung_aus_geraeten, heizwaerme_je_geraet, systemarbeitszahl,
        waerme_gesamt_je_geraet,
    )
    from backend.services.waermepumpe_kennzahlen_je_geraet import (
        kennzahlen_aus_mengen, mengen_aus_tageswerten,
    )
    from backend.services.waerme_klima_block import (
        achsen_der_anlage, funktions_eingaenge_der_anlage, geraete_zeilen,
        schranken_eingang, was_noch_moeglich,
    )
    from backend.core.investition_parameter import (
        abgrenzung_stoerung, ist_luft_luft_waermepumpe,
    )
    from backend.core.tageswert_grund import (
        GRUND_KEINE_ZAEHLERSTAENDE, GRUND_NICHT_ZUGEORDNET,
        GRUND_ZAEHLER_RUECKSPRUNG,
        tages_abdeckung_hinweis, tageswert_grund_kurz, tageswert_grund_text,
    )
    from backend.services.energie_profil import lade_modus_split_tag
    from backend.services.snapshot.aggregator import (
        WP_STROM_AUSGABE_ZU_FELD as _WP_STROM_AUSGABE_ZU_FELD,
        get_betriebsart_strom_tageswerte,
        get_wp_strom_stufe_je_investition,
    )

    # ── Zweig 1 laden: gemessene Betriebsart-Zähler (#263) ────────────────
    #
    # **Gemessen schlägt abgeleitet — ganz oder gar nicht je Gerät**
    # (SOLL §6.1/F4, Invariante K2; SoT `core/berechnungen/betriebsart_gemessen.py`).
    # Die Weiche wird **nicht** hier nachgebaut: die Feldnamen gehen
    # **unverändert** weiter, samt Innengerät-Suffix, und `modus_strom_zeile`
    # löst *Gerätefeld gewinnt, sonst Σ Innengeräte* selbst auf. Genau diese
    # Regel ein zweites Mal zu schreiben war F-56.
    # Der Bezug je Gerät kommt aus dem **Zählerpfad** (`komponenten_kwh`), nicht
    # aus der Stundensumme des Leistungspfads — die weicht ab, und genau daran
    # hängt W-17b (30 kWh Balken unter einer 284-kWh-Kachel). Die Tageszeile
    # und ihr Fenster sind oben schon gelesen (N-434/N-435).
    gemessen_je_inv = await get_betriebsart_strom_tageswerte(
        db, anlage, investitionen_by_id, datum, rueckwaerts=tz_rueckwaerts,
    )

    # ── R-4/N-482 · N-491: der Tages-Strom je Gerät, aufgelöst ────────────
    #
    # ⛔ **Hier stand bis zum 15.09.2026 nur** ``waermepumpe_kwh_je_investition
    # (tz_komp)`` — die aggregierte Tageszeile und sonst nichts. Sie fehlt für
    # ein Gerät in zwei Lagen, und beide standen auf Gernots Screenshot vom
    # 15.09.: ein an diesem Tag **stummer** Gesamtzähler (N-482) und ein Tag,
    # der erst um 11 Uhr beginnt bzw. noch läuft (N-491). Die Folge war jedes
    # Mal dieselbe: kein Nenner, keine Arbeitszahl, keine Verteilung — und der
    # Grund „kein Stromverbrauch erfasst" **neben** einer Strom-Kachel mit
    # Zahl. Die Präzedenz steht im Layer (n-gegen-1, Vorbild
    # ``pv_tages_praezedenz``); hier werden nur ihre Eingänge gesammelt.
    #
    # ⚠ **Die Registry-Feldnamen sind der Vertrag.** ``wp_strom_aufteilung``
    # liest eine IMD-Zeile; sie kann dieselbe Frage an Tageswerten nur
    # beantworten, wenn die Schlüssel dieselben sind — deshalb die Rückabbildung
    # der Ausgabe-Keys, und deshalb gehen die Betriebsart-Felder **unverändert**
    # (samt Innengerät-Suffix) mit hinein: ihre K2-Auflösung steht in
    # ``betriebsart_gemessen``, nicht hier.
    _wp_tageswerte_je_inv: dict[str, dict[str, float]] = {}
    for _ausgabe, _registry_feld in _WP_STROM_AUSGABE_ZU_FELD.items():
        for _inv_id, _kwh in (_tagesdetail.werte_je_inv.get(_ausgabe) or {}).items():
            _wp_tageswerte_je_inv.setdefault(_inv_id, {})[_registry_feld] = _kwh
    for _inv_id, _felder_tag in gemessen_je_inv.items():
        _wp_tageswerte_je_inv.setdefault(_inv_id, {}).update(_felder_tag)
    wp_strom_je_inv, wp_strom_herkunft = loese_wp_tagesstrom_auf(
        waermepumpe_kwh_je_investition(tz_komp or {}),
        _wp_tageswerte_je_inv,
        investitionen_by_id,
    )
    wp_kwh_je_inv: dict[str, float] = {}
    if gemessen_je_inv:
        wp_kwh_je_inv = dict(wp_strom_je_inv)

    # ⭐ **Die Zusammenführung beider Zweige steht seit dem 10.09.2026 im Layer**
    # (`core/berechnungen/tages_stapel.py`) und nicht mehr hier. Auslöser war der
    # Monats-Verlauf (Konzept Wärme/Klima §8, Bauschnitt 4): Er braucht denselben
    # Stapel für 28–31 Tage, und in einer Route ist er für ihn unerreichbar. Ihn
    # dort ein zweites Mal hinzuschreiben wäre F-56 gewesen — die Probe
    # `test_263_t3_gemessene_betriebsart_tag.py` sagt im Kopf, warum das teuer
    # ist: *„die beiden Zweige treffen sich in `get_tag_detail`, die
    # Vorrang-Regel ist nur im Paar prüfbar."*
    #
    # **Geladen wird weiter hier, gefaltet wird dort** — dieselbe Bauform wie
    # `_lade_tages_eingaenge` neben `falte_modus_split_tag`.
    # Bauschnitt 6: Die BEITRÄGE je Gerät werden gebraucht, nicht nur ihre
    # Faltung — die Tages-Kühlzahl fragt, WELCHE Geräte Kühlstrom in den Stapel
    # bringen (R2 beidseitig, s. u.). `falte_tages_stapel` ist genau
    # `_falte(beitraege_des_tages(…))`; beides aus denselben Eingängen ⇒ bitgleich.
    _splits_tag = await lade_modus_split_tag(db, anlage_id, datum)
    # N-462: SOLL-§9-E7/Option A fragt „steckt der funktionsfremde Anteil im
    # Nenner?" — und das entscheidet die K3-Stufe des Bezugs, nicht das
    # Kennzeichen. Gemessen: 3,00 statt 3,75 an derselben Anlage.
    _stufe_je_inv = await get_wp_strom_stufe_je_investition(
        db, anlage, investitionen_by_id,
    )
    beitraege_tag = beitraege_des_tages(
        gemessen_je_inv, wp_kwh_je_inv, _splits_tag, investitionen_by_id, datum,
        stufe_je_inv=_stufe_je_inv,
    )
    stapel = falte_tages_stapel(
        gemessen_je_inv,
        wp_kwh_je_inv,
        _splits_tag,
        investitionen_by_id,
        datum,
        stufe_je_inv=_stufe_je_inv,
    )
    heizen_tag = stapel.heizen_kwh
    kuehlen_tag = stapel.kuehlen_kwh
    warmwasser_tag = stapel.warmwasser_kwh
    lueften_tag = stapel.lueften_kwh
    entfeuchten_tag = stapel.entfeuchten_kwh
    rest_tag = stapel.nicht_aufgeteilt_kwh
    bezug_tag = stapel.bezug_kwh
    abdeckung_tag = stapel.abdeckung_h
    hat_split = stapel.hat_split
    hat_gemessen = stapel.hat_gemessen

    # ── Wärme gesamt + Arbeitszahl des Tages, beide aus dem Layer ──────────
    #
    # Der Tages-Strom ist die Σ der `waermepumpe_*`-Keys der Tageszusammen-
    # fassung — dieselbe Quelle, aus der der Modus-Split oben seinen Bezug
    # nimmt. Die Wärme ist im Tag **immer gemessen** (nur ein zugeordneter
    # Wärmemengenzähler kommt hier an), deshalb gibt es keinen abgeleiteten
    # Anteil und die Sperre greift nur über die beiden Mengen selbst.
    # ⭐ **N-391: das erste Argument ist seit dem 14.09.2026 belegt.** Hier stand
    # `None`, weil es den gemeinsamen Wärmemengenzähler als Feld nicht gab — der
    # Tag konnte die Vorrangregel D1 also gar nicht anwenden. Mit dem Feld
    # *Wärme gesamt* kommt sein Tageswert über den Aggregator an
    # (`TAGESDETAIL_AUSGABE`), und Tag, Monat und Jahr lesen dieselbe Regel.
    # ⛔ **N-391b: je GERÄT, dann summieren — nie auf `detail` (den Anlagen-
    # summen).** Das Feld liegt am Gerät; über den Summen verschlänge der
    # Gesamtzähler EINER Wärmepumpe die Aufteilung aller anderen (zwei WPs,
    # 30 + [20 + 5] ⇒ 30 statt 55, während der Monat für denselben Bestand 55
    # sagt). `werte_je_inv` trägt dieselben Zahlen je Gerät; `detail` ist ihre
    # Summe — die Auflösung gehört davor, nicht danach.
    # ⭐ **R-2/N-487: D1-Stufe 3 gilt auch am Tag.** Bis zum 15.09.2026 stand
    # hier `werte_je_inv["wp_heizung_kwh"]` roh — die **Achse** und sonst
    # nichts. Ein Gerät, das seine Heizwärme je Betriebsart misst, brachte im
    # Tag keine Wärme ein, und der Kasten nannte den Handgriff „Wärmemengen-
    # zähler zuordnen", den es längst getan hatte. Die Weiche ist dieselbe wie
    # im Monat und steht im Layer; hier wird sie **je Gerät** gerufen.
    _wp_heizung_je_inv = heizwaerme_je_geraet(
        _tagesdetail.werte_je_inv.get("wp_heizung_kwh"),
        _tagesdetail.werte_je_inv.get("wp_betriebsart_heizen_kwh"),
    )
    _wp_waerme_je_geraet = waerme_gesamt_je_geraet(
        _tagesdetail.werte_je_inv.get("wp_waerme_kwh"),
        _wp_heizung_je_inv,
        _tagesdetail.werte_je_inv.get("wp_warmwasser_kwh"),
    )
    # Die anlagenweite Heizwärme ist die Σ der **aufgelösten** Geräte (E1), nicht
    # die Σ der Achse — sonst nennt dieselbe Route zwei Zahlen.
    _wp_heizung_tag = sum(_wp_heizung_je_inv.values()) if _wp_heizung_je_inv else None
    # W-18 für eine **Alternativ-Gruppe**: Die Heizwärme hat seit R-2 zwei
    # mögliche Zähler, und ein Grund gilt der Gruppe, nicht dem Feld.
    #
    # ⛔ **Die Bedingung ist nicht kosmetisch.** `grund_je_feld` enthält genau
    # die Keys **ohne** Wert — daran hängt die Zusage „ein Grund steht nur da,
    # wo nichts geliefert hat". Nähme man den Betriebsart-Key unbedingt dazu,
    # trüge jede ganz normale Wärmepumpe (Achse gepflegt, Betriebsart-Zähler
    # nicht zugeordnet) plötzlich den Grund *„kein Wärmemengenzähler
    # zugeordnet"* neben ihrer gemessenen Null — gemessen an
    # `test_n348_…::test_gemessene_null_heisst_kein_betrieb_nicht_kein_zaehler`,
    # und genau die Verwechslung, die dietmar1968 einen Zuordnungsfehler suchen
    # ließ (T89667 #322).
    _D1_HEIZ_GRUND_KEYS = (
        ("wp_heizung_kwh", "wp_betriebsart_heizen_kwh")
        if "wp_heizung_kwh" in _grund else ("wp_heizung_kwh",)
    )
    _wp_waerme_tag = sum(_wp_waerme_je_geraet.values())
    wp_waerme_tag = round(_wp_waerme_tag, 2) if _wp_waerme_tag > 0 else None
    # ⛔ **Hier stand bis zum 15.09.2026 eine ZWEITE Abfrage derselben Spalte**
    # (`komponenten_kwh`) und eine zweite Faltung daneben — während `tz_komp`
    # dreißig Zeilen weiter oben schon gelesen war. `wp_strom_je_inv` kommt
    # jetzt aus der einen Auflösung (R-4), und damit lesen der Stapel, die
    # Verteilung und die Arbeitszahl **dieselbe** Menge.
    wp_strom_tag = sum(wp_strom_je_inv.values()) or None
    # ── D-Sicht 3: die Mengen je Gerät des TAGES ──────────────────────────
    #
    # ⚠ **Die zweite Mengen-Herkunft** (s. Modulkopf des Dienstes): Der Tag
    # faltet Snapshots, nicht IMD-Zeilen — die **Kennzahl** entsteht trotzdem in
    # derselben Funktion wie im Hub, im Monat und im Jahr.
    _wp_kaelte_je_inv = _tagesdetail.werte_je_inv.get("wp_kaelte_kwh") or {}
    _wp_ww_je_inv = _tagesdetail.werte_je_inv.get("wp_warmwasser_kwh") or {}
    _wp_gesamtwaerme_je_inv = _tagesdetail.werte_je_inv.get("wp_waerme_kwh") or {}
    _wp_strom_heizen_je_inv = _tagesdetail.werte_je_inv.get("wp_strom_heizen_kwh") or {}
    _wp_strom_ww_je_inv = _tagesdetail.werte_je_inv.get("wp_strom_warmwasser_kwh") or {}
    _wp_beitrag_je_inv = {b.inv_id: b for b in beitraege_tag}
    # ⚠ **Der Geräte-Kreis ist der der STROM-Beiträge — und das ist heute eine
    # benannte Grenze, keine Absicht** (WK-16j/§7). Ein Gerät mit Wärmemengen-
    # zähler und ohne Stromwert **an diesem Tag** (r28/Demo, 15.06.2026: Daikin
    # mit 4,0 kWh Wärme) kommt hier nicht vor: Es fehlt deshalb in der Tabelle
    # *Zahlen je Gerät* **und** im Zähler-Kreis der Deckung. Es aufzunehmen ist
    # gemessen **nicht** folgenlos — ``kennzahlen_aus_mengen`` kennt den
    # W-18-Grund des Tages nicht und schriebe an so eine Zeile *„kein
    # Stromverbrauch erfasst"*, also genau den Satz, den N-492 abgestellt hat
    # (der Zähler **ist** zugeordnet, nur dieser Tag trägt keine Stände).
    _wp_kennzahlen_je_geraet = []
    for _inv_id_str, _inv_strom in wp_strom_je_inv.items():
        _inv = investitionen_by_id.get(_inv_id_str)
        if _inv is None:
            continue
        _b = _wp_beitrag_je_inv.get(_inv_id_str)
        _wp_kennzahlen_je_geraet.append(kennzahlen_aus_mengen(
            mengen_aus_tageswerten(
                _inv,
                strom_kwh=float(_inv_strom or 0.0),
                waerme_kwh=float(_wp_waerme_je_geraet.get(_inv_id_str, 0.0)),
                heizung_kwh=float(_wp_heizung_je_inv.get(_inv_id_str, 0.0)),
                warmwasser_kwh=float(_wp_ww_je_inv.get(_inv_id_str, 0.0)),
                strom_heizen_kwh=float(_wp_strom_heizen_je_inv.get(_inv_id_str, 0.0)),
                strom_warmwasser_kwh=float(_wp_strom_ww_je_inv.get(_inv_id_str, 0.0)),
                kaelte_kwh=float(_wp_kaelte_je_inv.get(_inv_id_str, 0.0)),
                modus_strom_kuehlen_kwh=(_b.kuehlen_kwh if _b else 0.0),
                funktionsfremd_abzug_kwh=(beitrag_abzug_kwh(_b) if _b else 0.0),
                waerme_ist_gesamt=bool(_wp_gesamtwaerme_je_inv.get(_inv_id_str)),
            ),
        ))
    _wp_strom_ohne_waerme_tag, _wp_geraete_ohne_waerme_tag = schranken_eingang(
        _wp_kennzahlen_je_geraet,
    )
    # R2 (26.08.2026): Auch der Tag kannte bisher **keine** Abgrenzungs-Sperre.
    # Die Anwender-Angabe hängt am **Gerät**, nicht am Zeitraum — ein Heizstab
    # auf dem WP-Zähler ist am Dienstag derselbe wie im Monatsbericht. Genau
    # deshalb galt hier sonst der Fall, den ADR-001 beschreibt: dieselbe Frage,
    # zwei Antworten, je nachdem welche Sicht der Anwender öffnet.
    #
    # ⚠ Gefragt werden nur die Geräte, die **an diesem Tag** Strom beigetragen
    # haben. Ein stillgelegtes oder stillstehendes Gerät mit gemeldeter Störung
    # darf die Zahl eines Tages nicht sperren, an dem es gar nicht lief.
    # R2/Bauart (SOLL §5): Trägt der Tag Luft-Wasser **und** Luft-Luft?
    #
    # ⚠ **Hier wird gezählt statt `WpFakten` gefragt, und das ist kein zweiter
    # Rechenweg:** Die Monats-Fakten gibt es für einen einzelnen Tag nicht — der
    # Tag faltet Snapshots, nicht IMD-Zeilen. Die **Regel** steht trotzdem nur
    # einmal (`abgrenzungs_grund` + `GRUND_BAUARTEN_GEMISCHT`); hier entsteht
    # allein ihr Eingang, mit derselben Bedingung wie die Störung darunter:
    # **nur Geräte, die an diesem Tag Strom beigetragen haben.**
    _bauarten_tag = {
        ist_luft_luft_waermepumpe(investitionen_by_id.get(inv_id_str))
        for inv_id_str, kwh in wp_strom_je_inv.items()
        if kwh and investitionen_by_id.get(inv_id_str) is not None
    }
    # R2/§4.2 Fall 1 (ADR-002/P12, 02.09.2026): Trägt der Tag Strom von Geräten,
    # deren Wärme fehlt? **Bis dahin fehlte diese Lage hier — unbegründet.**
    # Cockpit → Monat sperrte, die Tagesansicht daneben zeigte eine Zahl: zwei
    # Sichten, zwei Antworten auf dieselbe Frage.
    #
    # ⭐ **Warum sie aus dem MONAT kommt und nicht vom Tag.** Die Tagesebene
    # kennt den Strom je Gerät (`komponenten_kwh`), die Wärme aber nur als
    # **Anlagensumme** — aus ihr ist nicht ableitbar, von wie vielen Geräten sie
    # stammt. Die Frage ist damit auf Tagesdaten strukturell unbeantwortbar. Sie
    # aus den Monats-Fakten zu holen ist **kein zweiter Rechenweg**, sondern
    # derselbe SoT, den Cockpit → Monat liest (ADR-002/P10) — anders als
    # `bauarten_gemischt` darunter, das aus **Stammdaten** kommt und deshalb
    # ohne Fetch auskommt.
    #
    # ⚠ **Die Rest-Unschärfe gehört dazu:** Meldet ein Gerät im Monat Wärme,
    # aber an genau diesem Tag nicht, bleibt der Tag ungesperrt. Genauer geht es
    # erst, wenn die Tagesebene die Wärme je Gerät führt; die Aussage ist dann
    # „im Monat dieses Tages", und der einzige Fehler, den sie machen kann, ist
    # der mildere von beiden.
    _wp_fakten_monat = await lade_monats_fakten(
        db, anlage_id, von=(datum.year, datum.month), bis=(datum.year, datum.month),
    )
    _geraete_ohne_waerme_monat = any(
        f.wp.waerme_deckt_nicht_alle_geraete for f in _wp_fakten_monat
    )
    # N-441: die Gegenrichtung, aus derselben Monats-Naeherung wie die Zeile
    # darueber und aus demselben Grund — die Tagesebene fuehrt die Waerme nur
    # als Anlagensumme.
    _geraete_verschieden_monat = any(
        f.wp.geraete_verschieden for f in _wp_fakten_monat
    )
    wp_abgrenzung_tag = abgrenzungs_grund(
        abgrenzung_stoerung=next(
            (
                stoerung
                for inv_id_str, kwh in wp_strom_je_inv.items()
                if kwh
                for stoerung in (
                    abgrenzung_stoerung(investitionen_by_id.get(inv_id_str)),
                )
                if stoerung
            ),
            None,
        ),
        bauarten_gemischt=len(_bauarten_tag) > 1,
        geraete_ohne_waerme=_geraete_ohne_waerme_monat,
        geraete_verschieden=_geraete_verschieden_monat,
    )
    # ── SOLL §3.2b: WELCHE Funktionen die Verletzung trifft — am TAG gezählt ─
    #
    # ⛔ **Hier stand bis zum 15.09.2026 die Monats-Näherung**, und sie war im
    # **laufenden** Monat leer: Ohne `Monatsdaten`-Zeile antwortet
    # `WpFakten.deckung_je_funktion` überall `None` ⇒ „die Frage stellt sich
    # nicht" ⇒ keine Sperre. Gemessen an der Prüfstand-Anlage der r28
    # (`tag-detail?datum=2026-09-10`): *Arbeitszahl Heizen* **3,346** und
    # *Warmwasser* **4,211**, beide **ohne Grund** — genau die zwei Zahlen, die
    # *Cockpit → Monat* derselben Anlage seit WK-16i mit R2 zurückhält, und die
    # derselbe Monat nach seinem Abschluss sperrt (Juli, August 2026). **Zwei
    # Sichten, zwei Antworten auf dieselbe Frage** (N-506).
    #
    # ⭐ **Der Tag fragt jetzt dieselbe Faltung wie der Monat** (**WK-16j/R-1**,
    # `waerme_klima_block.funktions_eingaenge_der_anlage`) — Σ über dieselben
    # Geräte-Mengen, aus denen die Tabelle *Zahlen je Gerät* entsteht, und über
    # denselben Layer-SoT `deckung_aus_geraeten` (Identitäten, nicht Anzahlen,
    # N-441). **Keine zweite Faltung** (F-56): derselbe Aufruf, eine Route
    # weiter. Deshalb steht der Block mit den Geräte-Kennzahlen jetzt **über**
    # diesem hier — eine Deckungs-Aussage kommt aus denselben Mengen, die die
    # Zahl bilden.
    #
    # ⚠ **Die Monats-Näherung bleibt für die beiden Block-Lagen darüber**
    # (`_geraete_ohne_waerme_monat`, `_geraete_verschieden_monat` in
    # `wp_abgrenzung_tag`): Sie beschreiben den **Block**, nicht eine Funktion,
    # und die eine davon zählt der Tag ohnehin selbst (`_wp_abgrenzung_sperrt_tag`).
    _wp_funktions_eingaenge_tag = funktions_eingaenge_der_anlage(
        _wp_kennzahlen_je_geraet,
    )
    _deckung_je_funktion_tag = {
        f: _wp_funktions_eingaenge_tag.deckung_je_funktion(f)
        for f in ARBEITSZAHL_FUNKTIONEN
    }

    # ── Und Zähler und Nenner kommen aus DERSELBEN Faltung wie die Deckung ──
    #
    # ⛔ **Sonst bewacht die Deckung eine andere Rechnung, als sie sieht.**
    # Gemessen an der Prüfstand-Lage **ohne** den Vaillant (Nibe + Brauchwasser-WP,
    # laufender Monat): Die Faltung setzt die Brauchwasser-WP nach der
    # Ein-Achsen-Regel (**R-4**) auf **beide** Seiten der Warmwasser-Achse ⇒ die
    # Deckung sagt zu Recht „deckt sich". Der Tages-Nenner
    # ``detail["wp_strom_warmwasser_kwh"]`` kennt sie aber nicht — ihr Strom steht
    # unter ``stromverbrauch_kwh``. Ergebnis wäre 12,5 ÷ 1,5 = **8,33** statt
    # 12,5 ÷ 3,5 = **3,57**: eine freigegebene Zahl mit halbem Nenner. *Cockpit →
    # Monat* rechnet im laufenden Monat seit WK-16i aus genau derselben Faltung
    # (dort 96,36 ÷ 29,08); der Tag zieht damit nach.
    #
    # ⭐ **Jede Seite aus der Quelle, die für sie vollständig ist.**
    #
    # * **Nenner — die Faltung.** Nur sie kennt die Ein-Achsen-Regel; ein Gerät
    #   ohne Gesamt-Strom kann keinen Funktions-Strom tragen, ihr Geräte-Kreis
    #   verliert auf dieser Seite also nichts.
    # * **Zähler — die Tagessumme.** Sie deckt **jedes** Gerät mit Wärme ab, auch
    #   eines ohne Tages-Stromwert (r27/Demo, 05.12.2025: 29,9 kWh Heizwärme ohne
    #   einen einzigen Stromstand). Die Faltung sähe es nicht, und eine Kachel
    #   darf nicht schrumpfen, weil ein Nachbargerät seinen Zähler hat.
    #
    # ⚠ **Die Faltung gewinnt nur, wo sie etwas trägt** — dieselbe Bauform wie
    # die S5-Weiche ``traegt_menge``: Eine 0 ist hier keine Messung, sondern ein
    # Gerät, das sie nicht sieht; der Tageswert trägt dann seinen vollen Wert
    # **und** seine ``None``-heit, an der der W-18-Grund hängt.
    # ⭐ **Gemessen bitgleich** auf r27 (alle fünf Tage) und auf den Demo-Tagen
    # der r28; sichtbar wird der Unterschied nur, wo R-4 greift.
    def _nenner_der_funktion(
        aus_faltung: float, aus_tageswerten: Optional[float],
    ) -> Optional[float]:
        return aus_faltung if aus_faltung > 0 else aus_tageswerten

    _wp_heizung_fn = _wp_heizung_tag
    _wp_warmwasser_fn = detail.get("wp_warmwasser_kwh")
    _wp_strom_heizen_fn = _nenner_der_funktion(
        _wp_funktions_eingaenge_tag.strom_heizen_kwh,
        detail.get("wp_strom_heizen_kwh"),
    )
    _wp_strom_warmwasser_fn = _nenner_der_funktion(
        _wp_funktions_eingaenge_tag.strom_warmwasser_kwh,
        detail.get("wp_strom_warmwasser_kwh"),
    )
    # ── Bauschnitt 6: R2 für KÜHLEN aus dem Tag selbst, beidseitig ─────────
    #
    # ⛔ **Hier reicht die Monats-Näherung darüber NICHT**, und das ist gemessen:
    # Die Kälte summiert `get_tagesdetail_kwh` über alle Geräte, den Kühlstrom
    # trägt nur, wer den Tages-Stapel besteht (Bezug da · Teilmengen-Invariante
    # · aktiv, `tages_stapel.beitraege_des_tages`). Fällt ein Gerät an diesem Tag
    # heraus, stand seine Kälte im Zähler und sein Strom nirgends — **6,0 statt
    # 3,0**, während der Monat sich deckt und deshalb nicht sperrt.
    #
    # ⭐ Anders als bei der Wärme **kennt** der Tag hier beide Seiten je Gerät
    # (Kälte je Gerät aus `werte_je_inv`, Kühlstrom je Beitrag). Die Regel ist
    # dieselbe wie im Monat (`deckung_aus_geraeten`) — und seit N-441 vergleicht
    # sie selbst die **Identitäten**. Der Zwei-Zeilen-Sonderweg, der hier bis
    # zum 12.09.2026 stand (Anzahlen an die Regel, Identität per `if` daneben),
    # ist damit entfallen: eine Regel statt anderthalb.
    _kuehl_geraete_tag = {b.inv_id for b in beitraege_tag if b.kuehlen_kwh > 0}
    _kaelte_geraete_tag = {
        inv_id for inv_id, kwh in
        _tagesdetail.werte_je_inv.get("wp_kaelte_kwh", {}).items()
        if kwh > 0
    }
    _deckung_kuehlen_tag = deckung_aus_geraeten(
        _kuehl_geraete_tag, _kaelte_geraete_tag,
    )
    # Nur „kuehlen" wird ersetzt: Die Faltung beantwortet diese Funktion
    # ausdrücklich **nicht** (sie liefert die Eingänge, deren Mengen sie auch
    # liefert), und der Tag kennt hier beide Seiten je Gerät — genauer geht es
    # nicht. Heizen und Warmwasser kommen seit WK-16j aus derselben Faltung.
    _deckung_je_funktion_tag = {
        **_deckung_je_funktion_tag, "kuehlen": _deckung_kuehlen_tag,
    }
    _wp_abgrenzung_je_funktion_tag = abgrenzung_je_funktion(
        abgrenzung_stoerung=next(
            (
                stoerung
                for inv_id_str, kwh in wp_strom_je_inv.items()
                if kwh
                for stoerung in (
                    abgrenzung_stoerung(investitionen_by_id.get(inv_id_str)),
                )
                if stoerung
            ),
            None,
        ),
        bauarten_gemischt=len(_bauarten_tag) > 1,
        geraete_ohne_waerme=_geraete_ohne_waerme_monat,
        deckung_je_funktion=_deckung_je_funktion_tag,
    )
    # ── E1b: die anlagenweite Tageszahl als Schranke statt als Strich ─────
    #
    # ⭐ Dieselbe Entscheidung wie in Monat und Jahr (14.09.2026): Der Grund
    # *„nicht alle Geräte melden Wärme"* sperrte hier eine Zahl, die er nur zu
    # **klein** macht — der Strom eines Geräts ohne Wärmemessung steht im
    # Nenner, seine Nutzenergie in keinem Zähler. Das ist eine untere Schranke
    # und als solche wahr (ADR-002/P4). Die Gegenrichtung — Wärme ohne den
    # zugehörigen Strom — sperrt weiter.
    # ⛔ **Die Gegenrichtung wird am TAG gezählt, nicht aus dem Monat genähert —
    # und das ist gemessen (r28, Demo-Anlage, 15.06.2026).** Dort trägt die
    # Daikin die Wärme des Tages, aber keinen Strom (kein Tages-Zähler), während
    # der Multisplit Strom trägt und keine Wärme. Die Monats-Näherung sieht die
    # Kreuzung nicht (im Monat decken sich die Geräte); mit ihr allein stand
    # **30,0** als Schranke im Block — Wärme des einen geteilt durch den Strom
    # des anderen. Eine untere Schranke ist das nicht: Der Zähler ist zu groß,
    # die Zahl kippt nach **oben**.
    #
    # ⭐ **Der Tag kann es seit N-391b exakt** — er führt die Wärme je Gerät
    # (`_wp_waerme_je_geraet`) und den Strom je Gerät (`wp_strom_je_inv`). Die
    # Rest-Unschärfe, die der Kommentar an `_geraete_ohne_waerme_monat` oben
    # benennt, gilt damit nur noch für die **andere** Richtung — und die wird
    # zur Schranke, wo sie zutrifft, statt zu sperren.
    _wp_strom_geraete_tag = {i for i, kwh in wp_strom_je_inv.items() if kwh}
    _wp_waerme_geraete_tag = {
        i for i, kwh in _wp_waerme_je_geraet.items() if kwh and kwh > 0
    }
    _wp_abgrenzung_sperrt_tag = abgrenzungs_grund(
        abgrenzung_stoerung=next(
            (
                stoerung
                for inv_id_str, kwh in wp_strom_je_inv.items()
                if kwh
                for stoerung in (
                    abgrenzung_stoerung(investitionen_by_id.get(inv_id_str)),
                )
                if stoerung
            ),
            None,
        ),
        geraete_verschieden=bool(_wp_waerme_geraete_tag - _wp_strom_geraete_tag),
    )
    # W-18, als Eingang für BEIDES: die Sperre der Arbeitszahl und die Zeile im
    # Kasten. ⚠ **Die Kurzform, nicht die Langform** — der Kasten trägt Sätze
    # neben einem Handgriff; der Absatz aus `_tageswert_grund_kombiniert` steht
    # weiterhin unter der Wärme-Kachel, wo er hingehört.
    _wp_waerme_grund_kurz_tag = _tageswert_grund_kurz_kombiniert(
        _grund, (*_D1_HEIZ_GRUND_KEYS, "wp_warmwasser_kwh"),
    )
    # ── R-5/N-492: „kein Stromverbrauch erfasst" neben einer Strom-Kachel ──
    #
    # Der Satz ist eine Aussage über das **Gerät**; er ist falsch, sobald ein
    # Stromzähler zugeordnet ist und nur an **diesem Tag** nichts hergibt. Genau
    # das stand auf dem Lab-Screenshot vom 15.09.2026: *„Strom verbraucht
    # 2 kWh"* und daneben *„Arbeitszahl — kein Stromverbrauch erfasst"*.
    #
    # ⛔ **``GRUND_NICHT_ZUGEORDNET`` bleibt draußen, und zwar aus einem
    # gemessenen Grund:** seine Kurzform lautet *„kein Wärmemengenzähler
    # zugeordnet"* (``TAGESWERT_GRUND_KURZ``) — unter einer **Strom**-Zeile eine
    # Falschaussage. Für diese Lage ist ``GRUND_KEIN_STROM`` mit seinem
    # Handgriff *„Stromzähler zuordnen oder den Monatswert pflegen"* der
    # richtige Satz, und er bleibt.
    _wp_strom_grund_kurz_tag = _tageswert_grund_kurz_kombiniert(
        {
            k: g for k, g in _grund.items()
            if g != GRUND_NICHT_ZUGEORDNET
        },
        ("wp_strom_gesamt_kwh", "wp_strom_heizen_kwh", "wp_strom_warmwasser_kwh"),
    )
    wp_jaz_tag = systemarbeitszahl(
        wp_waerme_tag, wp_strom_tag,
        # W-14 + E4: Strom in Funktionen ohne bewertete Nutzenergie. Am Tag
        # wiegt der Effekt am schwersten: ein Sommertag kann fast reiner
        # Kühlbetrieb sein.
        #
        # ⭐ **SOLL-§9-E7/Option A (12.09.2026): abgezogen wird nur, was im
        # Nenner steht.** Hier stand bis dahin `kuehlen_tag + lueften_tag +
        # entfeuchten_tag` — die Mengen. Ein Gerät mit getrennter
        # Strommessung, dessen Aufteilung nur **abgeleitet** ist, kürzte damit
        # einen Nenner um eine Menge, die er nie enthielt (der Split verteilt
        # `strom_heizen + strom_warmwasser`, er stellt nichts daneben). Der
        # Stapel entscheidet das **je Gerät**; die drei Summanden daneben
        # bleiben unverändert und tragen weiter die Balken (K1).
        kuehlstrom_kwh=stapel.funktionsfremd_abzug_kwh,
        strom_ohne_waerme_kwh=_wp_strom_ohne_waerme_tag,
        geraete_ohne_waerme=_wp_geraete_ohne_waerme_tag,
        abgrenzung_verletzt=_wp_abgrenzung_sperrt_tag,
        # W-18: Die Sperre „kein Wärmemengenzähler zugeordnet" ist im Tag
        # regelmäßig falsch — der Zähler kann zugeordnet und für DIESEN Tag
        # trotzdem leer sein (Snapshots entstehen erst ab der Zuordnung; der
        # Monatswert kommt aus der HA-Langzeitstatistik und steht deshalb da).
        # Der Erhebungspfad weiß es, der Layer kann es nicht wissen.
        waerme_fehlt_grund=_wp_waerme_grund_kurz_tag,
        # R-5: dieselbe Bauform auf der Stromseite — der Erhebungspfad weiß,
        # welcher der drei W-18-Zustände vorliegt, der Layer kann es nicht.
        strom_fehlt_grund=_wp_strom_grund_kurz_tag,
    )

    # ── Arbeitszahl JE FUNKTION — der dritte Aufrufer desselben SoT (N-348) ─
    #
    # ⛔ **Bis 2026-08-29 gab es diesen Block nicht, und der Tag hat die drei
    # Zeilen deshalb ERSATZLOS weggelassen** — nicht als „—", sondern gar nicht.
    # Der Monat ruft `arbeitszahl_je_funktion` unbedingt und liefert immer Wert
    # **oder** Grund; der Tag lieferte keines von beidem, und die geteilte
    # Blockfabrik rendert dann keine Zeile. Dieselbe Anlage, dieselbe Datenlage,
    # zwei Auskünfte — genau der S3-Verstoß aus SOLL §3.3.
    #
    # ⚠ **`hat_split` heißt hier etwas ANDERES als die gleichnamige lokale
    # Variable oben** — die trägt „der Modus-Split hat Daten". Gemeint ist das
    # Investitions-Kennzeichen `getrennte_strommessung`, dieselbe Quelle wie im
    # Monat (`imd_monatsaggregat.py:223`). Die Namensgleichheit ist genau die
    # Falle, an der ein Fix „im Vorbeigehen" eine falsche Zahl erzeugt hätte,
    # deshalb der ausgeschriebene Name.
    #
    # ⚠ Gefragt werden — wie bei der Abgrenzung darüber — **nur die Geräte, die
    # an diesem Tag Strom beigetragen haben.** Ein stillgelegtes Gerät mit
    # getrennter Messung darf einen Tag nicht freischalten, an dem es nicht lief.
    _wp_getrennte_strommessung_tag = any(
        bool(((investitionen_by_id.get(inv_id_str).parameter or {})
              .get("getrennte_strommessung")))
        for inv_id_str, kwh in wp_strom_je_inv.items()
        if kwh and investitionen_by_id.get(inv_id_str) is not None
    )
    # `waerme_abgeleitet_kwh` bleibt 0: Im Tag kommt nur eine **gemessene**
    # Wärme an (nur ein zugeordneter Wärmemengenzähler erreicht `detail`) — der
    # abgeleitete Zweig existiert hier nicht, siehe die Begründung an
    # `_wp_waerme_tag` oben. `abgrenzung_verletzt` ist dieselbe Sperre wie bei
    # der Gesamtzahl: ein Heizstab auf dem Zähler trifft beide Funktionen.
    wp_az_funktion_tag = arbeitszahl_je_funktion(
        # R-2: dieselbe aufgelöste Heizwärme wie oben — `detail` trägt nur die
        # Achse, und die ist bei einem Gerät mit Betriebsart-Wärme leer.
        heizung_kwh=_wp_heizung_fn,
        strom_heizen_kwh=_wp_strom_heizen_fn,
        warmwasser_kwh=_wp_warmwasser_fn,
        strom_warmwasser_kwh=_wp_strom_warmwasser_fn,
        hat_split=_wp_getrennte_strommessung_tag,
        # N-391: derselbe Eingang wie im Monat, nur aus dem Tagesdetail. Trägt
        # der Tag einen Wert des gemeinsamen Wärmemengenzählers, sagen die zwei
        # Zeilen „Wärme nicht je Funktion gemessen" statt „kein Zähler
        # zugeordnet" — der Zähler ist zugeordnet.
        waerme_ist_gesamt=bool(detail.get("wp_waerme_kwh")),
        abgrenzung_verletzt=wp_abgrenzung_tag,
        abgrenzung_je_funktion_grund=_wp_abgrenzung_je_funktion_tag,
        # W-18 je Funktion: dieselbe Sperre wie oben bei der Gesamt-Arbeitszahl,
        # aber **je Zähler**. Der Layer bekam den Parameter am 26.08.; dieser
        # Block entstand am 29.08. (N-348) und hat ihn nie durchgereicht — die
        # zwei Zeilen liefen deshalb weiter auf den Default „kein
        # Wärmemengenzähler zugeordnet", und der ist am Tag regelmäßig falsch:
        # Der Zähler kann zugeordnet und für DIESEN Tag trotzdem leer sein.
        # ⚠ Je EINE Feldliste, nicht die kombinierte von oben — sonst erbt die
        # eine Zeile den Grund der anderen.
        waerme_fehlt_grund_heizen=_tageswert_grund_kurz_kombiniert(
            _grund, _D1_HEIZ_GRUND_KEYS,
        ),
        waerme_fehlt_grund_warmwasser=_tageswert_grund_kurz_kombiniert(
            _grund, ("wp_warmwasser_kwh",),
        ),
        # Der Tag ist die EINZIGE der fünf Sichten, die „gemessene 0" von
        # „nichts gemessen" trennen kann: `detail` trägt den Wert nur, wenn das
        # Feld aggregiert wurde, und `_grund` sagt sonst, warum nicht. Monat und
        # Jahr summieren vorher (`sum()` ⇒ immer eine Zahl) und dürfen den
        # Wortlaut deshalb nicht führen.
        null_ist_gemessen=True,
        # **R-2 (WK-16h, N-499): dieselbe Frage wie im Monat und im Jahr.**
        # Gemessen an der Demo-Anlage der r28 am 15.06.2026: An diesem Tag trägt
        # allein die Split-Klimaanlage Strom bei — und der Kasten empfahl
        # *„Getrennte Strommessung einschalten und beide Zähler zuordnen"* für
        # eine Warmwasser-Achse, die es an dieser Ausstattung nicht gibt.
        achsen=achsen_der_anlage(_wp_kennzahlen_je_geraet),
        gesamt=als_arbeitszahl(wp_jaz_tag),
    )

    # ── Arbeitszahl KÜHLEN — derselbe Aufruf wie im Monat (Bauschnitt 6) ───
    #
    # Zähler: die Kälte des Tages (`wp_kaelte_kwh`, Gerätefeld oder Σ
    # Innengeräte, im Fenster der Tageszeile). Nenner: der Kühlstrom des
    # Stapels. Die Σ über ALLE Geräte ist hier richtig: Deckt sich der
    # Geräte-Kreis, sind es dieselben Geräte; deckt er sich nicht, sperrt R2.
    #
    # W-18 für die Kälte: nur „keine Stände" und „Rücksprung" gehen als
    # Kurzform hinein. ⛔ **Nicht „nicht zugeordnet"** — dessen Kurzform spricht
    # von einem *Wärme*mengenzähler; für die Kälte ist `GRUND_KEINE_KAELTEMENGE`
    # (der Default des Layers) der richtige Satz, und er trifft jeden kühlenden
    # Anwender ohne Kältemengenzähler.
    _kaelte_grund_roh = _grund.get("wp_kaelte_kwh")
    wp_az_kuehlen_tag = arbeitszahl_kuehlen(
        detail.get("wp_kaelte_kwh"),
        kuehlen_tag,
        abgrenzung_verletzt=(
            _wp_abgrenzung_je_funktion_tag["kuehlen"]
            or (
                GRUND_FUNKTION_NICHT_DECKUNGSGLEICH
                if _deckung_kuehlen_tag is False else None
            )
        ),
        kaelte_fehlt_grund=(
            tageswert_grund_kurz(_kaelte_grund_roh)
            if _kaelte_grund_roh in (GRUND_KEINE_ZAEHLERSTAENDE, GRUND_ZAEHLER_RUECKSPRUNG)
            else None
        ),
        null_ist_gemessen=True,
    )

    # D-Sicht 3: EINMAL gebaut — die Tabelle im Block **und** der Kasten lesen
    # dieselben Zeilen (R-4). Zwei Aufrufe nebeneinander wären zwei Wahrheiten
    # über dieselbe Frage, und die Dedup-Regel des Kastens hinge dann an einer
    # zweiten Liste.
    _wp_block_geraete = geraete_zeilen(_wp_kennzahlen_je_geraet)

    # ── Aktive Geräte je Typ (Namen) für die „aggregiert aus …"-Hinweise ──
    #
    # Wortgleich zur Monatssicht (`aktueller_monat.py`), nur mit der feineren
    # Grenze: der Tag fragt `ist_aktiv_an`, nicht `ist_aktiv_im_monat`. Ein am
    # 20. angeschafftes Gerät gehört in den Hinweis des 21., nicht in den des 3.
    komponenten_geraete: dict[str, list[str]] = {}
    for _inv in investitionen_by_id.values():
        if _inv.ist_aktiv_an(datum):
            komponenten_geraete.setdefault(_inv.typ, []).append(_inv.bezeichnung)

    return TagDetailResponse(
        datum=datum,
        komponenten_geraete=komponenten_geraete,
        wp_modus_strom_heizen_kwh=round(heizen_tag, 2) if hat_split else None,
        wp_modus_strom_kuehlen_kwh=round(kuehlen_tag, 2) if hat_split else None,
        wp_modus_strom_warmwasser_kwh=round(warmwasser_tag, 2) if hat_split else None,
        wp_modus_strom_lueften_kwh=round(lueften_tag, 2) if hat_split else None,
        wp_modus_strom_entfeuchten_kwh=round(entfeuchten_tag, 2) if hat_split else None,
        wp_modus_nicht_aufgeteilt_kwh=round(rest_tag, 2) if hat_split else None,
        wp_modus_abdeckung_h=round(abdeckung_tag, 1) if hat_split else None,
        # W-17b: Der Balken sagt jetzt, worauf er sich bezieht. Ohne dieses
        # Feld stand er unter einer Kachel mit einer GROESSEREN Zahl, ohne dass
        # irgendwo die Differenz benannt war — dietmar1968 sah 30 kWh Balken
        # unter 284 kWh Kachel (T89667 #210).
        wp_modus_strom_bezug_kwh=round(bezug_tag, 2) if hat_split else None,
        # Wie in der Monatssicht: „gemessen" gilt für die Zeile, sobald ein
        # Gerät des Tages seine Aufteilung aus Zählern hat. Ein
        # Betriebsart-Zähler hat keine „Stunden mit Signal" — die Abdeckung
        # bleibt dann 0, ohne dass etwas fehlt (das Frontend zeigt deshalb
        # „Herkunft: gemessen" statt „Modus erfasst: 0 Stunden").
        wp_modus_gemessen=hat_gemessen if hat_split else None,
        # A6: Die Kacheln zeigen, **womit die Kennzahl gerechnet hat** — also
        # dieselben vier Zahlen, die oben in `arbeitszahl_je_funktion` gehen.
        wp_strom_heizen_kwh=_wp_strom_heizen_fn,
        wp_strom_warmwasser_kwh=_wp_strom_warmwasser_fn,
        # R-2: die **aufgelöste** Heizwärme (D1-Stufe 3), nicht die Achse.
        # R-4: die Marke steht an der **Basis**-Größe des Blocks, nicht an
        # jeder abgeleiteten — dieselbe Regel, mit der N-472 die Gründe im
        # laufenden Monat verteilt hat. Sonst stünde derselbe Satz fünfmal.
        wp_abdeckung_hinweis=tages_abdeckung_hinweis(
            _tagesdetail.abdeckung_von.strftime("%H:%M")
            if _tagesdetail.abdeckung_von else None,
            _tagesdetail.abdeckung_bis.strftime("%H:%M")
            if _tagesdetail.abdeckung_bis else None,
        ),
        wp_heizung_kwh=_wp_heizung_fn,
        wp_warmwasser_kwh=_wp_warmwasser_fn,
        wp_waerme_kwh=wp_waerme_tag,
        # W-18: Warum die Wärme fehlt. Sie entsteht aus ZWEI Feldern; der
        # aussagekräftigere Grund gewinnt (`GRUND_RANG`), damit nicht „kein
        # Zähler" gemeldet wird, während der zweite Zähler zugeordnet, aber
        # leer ist. Steht ein Wert, steht kein Grund — nie beides.
        wp_waerme_grund=(
            _tageswert_grund_kombiniert(
                _grund, (*_D1_HEIZ_GRUND_KEYS, "wp_warmwasser_kwh"),
            ) if wp_waerme_tag is None else None
        ),
        wp_jaz=wp_jaz_tag.wert,
        wp_jaz_grund=wp_jaz_tag.grund,
        wp_jaz_hinweis=wp_jaz_tag.hinweis,
        wp_jaz_zaehler_kwh=wp_jaz_tag.zaehler_kwh,
        wp_jaz_nenner_kwh=wp_jaz_tag.nenner_kwh,
        # N-348 — je Funktion, wie der Monat. Wert ODER Grund, nie beides leer.
        wp_jaz_heizen=wp_az_funktion_tag.heizen.wert,
        wp_jaz_heizen_grund=wp_az_funktion_tag.heizen.grund,
        wp_jaz_warmwasser=wp_az_funktion_tag.warmwasser.wert,
        wp_jaz_warmwasser_grund=wp_az_funktion_tag.warmwasser.grund,
        # Bauschnitt 6 (11.09.2026): Die Kältemenge hat jetzt einen Tagespfad —
        # bis dahin stand hier ein Grund „nur im Monat", weil der Zähler des
        # Quotienten den Tag nie erreichte (N-348).
        wp_jaz_kuehlen=wp_az_kuehlen_tag.wert,
        wp_jaz_kuehlen_grund=wp_az_kuehlen_tag.grund,
        wp_jaz_ist_schranke=wp_jaz_tag.ist_schranke,
        wp_jaz_schranke_hinweis=wp_jaz_tag.schranke_hinweis,
        wp_geraete=_wp_block_geraete,
        # D-Sicht 1: Der Tag kennt einen Grund mehr als Monat und Jahr — den
        # der **Wärme** (W-18: „für diesen Tag keine Zählerstände"). Er gehört
        # in denselben Kasten; welche Klasse er trägt, entscheidet die
        # Grund-Konstante, nicht diese Route.
        wp_moeglich=was_noch_moeglich([
            ("Arbeitszahl", wp_jaz_tag.grund),
            (
                "Wärme erzeugt",
                _wp_waerme_grund_kurz_tag if wp_waerme_tag is None else None,
            ),
            ("Arbeitszahl Heizen", wp_az_funktion_tag.heizen.grund),
            ("Arbeitszahl Warmwasser", wp_az_funktion_tag.warmwasser.grund),
            ("Arbeitszahl Kühlen", wp_az_kuehlen_tag.grund),
        # R-4: die Geräte-Ausstattungsgründe, dedupliziert gegen die Zeilen
        # darüber (WK-16h/N-502).
        ], _wp_block_geraete),
        # Bauschnitt 8: derselbe Wert, den die Kühlzahl eben als Zähler bekam.
        wp_kaelte_kwh=(
            round(detail["wp_kaelte_kwh"], 2)
            if (detail.get("wp_kaelte_kwh") or 0) > 0 else None
        ),
        speicher_ladung_netz_kwh=detail.get("speicher_ladung_netz_kwh"),
        speicher_effektiver_ladepreis_cent=(
            round(eff.effektiver_ladepreis_cent, 2)
            if eff.effektiver_ladepreis_cent is not None else None
        ),
        speicher_effektiver_ladepreis_quelle=eff.quelle,
        emob_ladung_pv_kwh=detail.get("emob_ladung_pv_kwh"),
        emob_ladung_netz_kwh=detail.get("emob_ladung_netz_kwh"),
        # W-18, dieselbe Klasse an der E-Mobilität: Der PV-Anteil trug denselben
        # fest verdrahteten „Sensor zuordnen"-Satz. Er wird ebenfalls über
        # denselben Weg erhoben und hat deshalb dieselben drei Zustände.
        emob_ladung_pv_grund=tageswert_grund_text(
            _grund.get("emob_ladung_pv_kwh"), "emob_ladung_pv_kwh",
        ),
        soll_pv_kwh=soll_pv,
        einspeise_preis_cent=tarif.einspeiseverguetung_cent,
        netzbezug_preis_cent=netzbezug_preis_tag,
        netzbezug_preis_herkunft=netzbezug_preis_herkunft_tag,
    )

@router.get("/{anlage_id}/tag-status", response_model=TagStatusResponse)
async def get_tag_status(
    anlage_id: int,
    datum: date = Query(..., description="Tag (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """Warum liegen für diesen Tag keine Werte vor — und was hilft? (F-2)

    Aufruf **nur** aus der leeren Tagessicht heraus, nicht bei jedem
    Tageswechsel: die letzte Prüfung ist ein HA-LTS-Read für den Tag, und nur
    er unterscheidet „Lücke, nachholbar" von „HA hat für den Tag selbst nichts".

    Bewusst getrennt vom Daten-Checker: der beschreibt die **Anlage** (letzte
    Tageszeile, 90-Tage-Lücken, ~2,5 s je Lauf) und beantwortet die Frage nach
    **diesem** Tag nicht.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    from backend.services.energie_profil.tag_status import baue_tag_status

    status = await baue_tag_status(db, anlage, datum)
    return TagStatusResponse(
        datum=datum,
        lage=status.lage,
        meldung=status.meldung,
        details=status.details,
        link=status.link,
        aktion_kind=status.aktion_kind,
        aktion_label=status.aktion_label,
    )
