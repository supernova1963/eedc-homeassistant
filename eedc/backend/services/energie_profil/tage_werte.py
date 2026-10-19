"""Tages-Werte-Builder für die Werte/Tabelle-Embed-Sicht (IA v4 E3, Cockpit/Monat).

Liefert pro Tag eine vollständige Werte-Zeile (Energie-Bilanz + Quoten +
Speicher/WP + Finanzen + CO₂ + tag-native Peaks/PR/Börsenpreis) — die
numerische Zwillings-Quelle des Tagesverlauf-Charts.

**Keine Aggregat-Logik im Frontend** ([[feedback_aggregations_drift]]): die
Energie-Bilanz kommt aus dem SoT-Helper `bilanz_aus_stundenrows`
(core/berechnungen, identische Σ-Semantik wie der Monats-Endpoint
`get_monatsauswertung` → additive Symmetrie, vom Symmetrie-Test abgesichert).
Die Finanzen laufen über den `baue_finanz_zeile`-SoT (#326, je-Monat-Tarif);
die Speicher-Ladung und -Entladung des Tages gehen mit (N-635, 05.10.2026), V2H
und BKW bleiben 0 — so ist die Finanz-Eigenverbrauchsmenge == der Energie-Spalte
`eigenverbrauch` (= Direktverbrauch + Speicher-Entladung, dieselbe Formel wie im
Monat). Bis dahin ging der Speicher mit 0 ein und beide Seiten rechneten
`PV − Einspeisung` — gleich miteinander, aber nicht mit dem Monat. Der Grundpreis ist
monatlich-fix und wird auf Tagesebene **nicht** anteilig verteilt.

**CO₂ — eine Definition, ein bewusst benannter Teil-Umfang (F-6, 2026-07-31).**
Bis dahin stand hier ``erzeugung × CO2_FAKTOR_STROM_KG_KWH``. Das war ein
Überlebender der DI-2-Ablösung: es schrieb auch der **eingespeisten** kWh die
volle Netzstrom-Vermeidung gut, lag also systematisch zu hoch. Gerechnet wird
jetzt über den Kanon ``berechne_co2_bilanz`` (ADR-001) — dieselbe Bezugsgröße
wie die Finanz-Spalte ``ev_ersparnis`` nebenan (Eigenverbrauch, nicht Erzeugung).

Der Tageswert trägt aus dieser Bilanz **nur den PV-Anteil** (``co2_pv_kg``):
WP-**Wärme** und E-Mobilitäts-**Kilometer** liegen ausschließlich monatlich vor
(``InvestitionMonatsdaten``); stündlich existiert von der Wärmepumpe nur die
Stromaufnahme (``TagesEnergieProfil.waermepumpe_kw``), und ohne Wärmemenge ist
die WP-Ersparnis nicht bestimmbar. Daraus folgt eine Aussage, die **nicht**
stillschweigend bleiben darf: **Σ Tage ≠ CO₂-Monatswert**, sobald die Anlage
eine Wärmepumpe oder ein E-Auto hat. Die vollständige Bilanz (PV + WP + E-Mob)
liefert ``/cockpit/nachhaltigkeit/{anlage}``; sie ist die Quelle von Cockpit/Jahr
und Auswertungen → CO₂. Die Spalte heißt im Client deshalb „CO₂-Einsparung (PV)".
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.energie_profil._shared import TagWerteResponse
from backend.core.berechnungen.ergebnis import ErgebnisEingang, berechne_ergebnis
from backend.core.berechnungen.kennzahlen import autarkie_prozent, eigenverbrauchsquote_prozent
from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
from backend.core.berechnungen.slot_konvention import forward_werte_je_backward_zeile
from backend.core.berechnungen.spannen import verbrauch_gebuendelt
from backend.core.berechnungen import (
    aggregiere_tep_komponenten,
    berechne_finanz_aggregat,
    berechne_grundlast,
    bilanz_aus_stundenrows,
    delta_soc_kwh,
    eigenverbrauch_ohne_verluste_kwh,
    erzeuger_kwh_je_investition,
    sonstiges_kwh_je_richtung,
    speicher_wirkungsgrad,
    mit_v2h_entladung,
    summe_bkw_kwh,
    summe_pv_anlage_kwh,
    summe_v2h_kwh,
    vollzyklen as berechne_vollzyklen,
)
from backend.core.calculations import berechne_co2_bilanz
from backend.core.investition_kennwerte import (
    get_speicher_kapazitaet_kwh,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.einspeise_erloes_service import neg_preis_einspeisung_tageswert
from backend.services.finanz_zeilen import FinanzZeileEingabe, baue_finanz_zeile
from backend.services.zaehlerstaende import lade_zaehlerstaende

logger = logging.getLogger(__name__)


# ── RF-20 (Serie „Funktion vor Datei", 13.10.2026): `baue_tage_werte` ist ein Orchestrator ──────────────────────────
# Er lädt, was alle Tage des Zeitraums teilen (Stundenzeilen samt SoC-Paarung, Tageszeilen, Speicher/Sonstiges/Erzeuger,
# Monatsdaten, Zählerstände, Kanal-Tage, Tarife und Slot-Kosten — in dieser Reihenfolge, sie ist die SQL-Folge), und
# baut je Tag die Zeile über `_tageszeile`. Die Phasen darunter sind wortgleich umgezogen; was alle Tage teilen, reist
# in `_TageKontext`. Die Antwortzeile entsteht aus drei Spaltengruppen (`_energie_spalten`, `_geld_spalten`,
# `_tagnative_spalten`); die Feldreihenfolge der Antwort bestimmt das Schema `TagWerteResponse`, nicht der Aufruf.


@dataclass
class _TageKontext:
    """Was alle Tage EINER Anfrage teilen — im Orchestrator geladen, von den Phasen nur gelesen."""
    db: AsyncSession
    anlage_id: int
    tep_pro_tag: dict[date, list[TagesEnergieProfil]]
    soc_gepaart: dict[tuple[date, int], Optional[float]]
    tz_pro_tag: dict[date, TagesZusammenfassung]
    speicher_invs: list[Investition]
    sonstiges_invs: list[Investition]
    erzeuger_invs: list[Investition]
    md_pro_monat: dict[tuple[int, int], Monatsdaten]
    zaehler_stand_pro_tag: dict[date, dict[str, float]]
    kanal_je_tag: dict
    #: HA-Bauform E-S3-2: je Kanal-Tag die Mischzeilen (`kanal_stunden.py`) — der Eingang der stundengepaarten Größen.
    kanal_stunden_je_tag: dict
    #: HA-Bauform S5 (E-S5-3, §10h 6): `komponenten_kwh` je Tag aus der einen Mischung `kanal_stunden.komponenten_der_tage`
    #: (an einem Kanal-Tag Bilanz- und Sonstiges-Schlüssel aus den Kanälen — die Gruppen, die diese Sicht liest).
    komp_je_tag: dict
    tarif_cache: dict[date, dict]
    slot_kosten_je_tag: dict


async def baue_tage_werte(
    db: AsyncSession,
    anlage: Anlage,
    von: date,
    bis: date,
) -> list[TagWerteResponse]:
    """Baut die Tages-Werte-Zeilen für ``[von, bis]`` (inklusiv), aufsteigend.

    Eine Zeile pro Tag, der stündliche TEP-Daten **oder** eine
    Tageszusammenfassung hat. Energie aus TEP-Σ, tag-native Felder aus der
    Tageszusammenfassung.
    """
    anlage_id = anlage.id

    # Stündliche Rohdaten je Tag gruppieren.
    # ⭐ **Ein Tag früher** (N-387): der Ladestand, der zur Backward-Stunde 0
    # gehört, steht in der Zeile 23 des Vortags. Die Zeilen dieses Zusatztages
    # liefern nur den SoC und landen **nicht** in `tep_pro_tag` — sonst bekäme
    # der Aufrufer eine Zeile für einen Tag, nach dem er nicht gefragt hat.
    # HA-Bauform S4 (S4-R-3b): **und ein Tag später** — an einem Kanal-Tag trägt die Zeile 0 des Folgetags die
    # Backward-Bahnen der Stunde 23 (`slot_konvention.bestandszeile_fuer_stundenbeginn`). Auch diese Zeilen landen
    # nicht in `tep_pro_tag`, nur in den Mischzeilen des letzten Tages.
    tep_result = await db.execute(
        select(TagesEnergieProfil)
        .where(and_(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von - timedelta(days=1),
            TagesEnergieProfil.datum <= bis + timedelta(days=1),
        ))
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    alle_tep = list(tep_result.scalars().all())
    soc_gepaart: dict[tuple[date, int], Optional[float]] = {
        (r.datum, r.stunde): wert
        for r, wert in zip(
            alle_tep, forward_werte_je_backward_zeile(alle_tep, "soc_prozent")
        )
    }
    tep_pro_tag: dict[date, list[TagesEnergieProfil]] = defaultdict(list)
    tep_folgetag: list[TagesEnergieProfil] = []
    for r in alle_tep:
        if r.datum > bis:
            tep_folgetag.append(r)
        elif r.datum >= von:
            tep_pro_tag[r.datum].append(r)

    # Tageszusammenfassungen (tag-native Felder)
    tz_result = await db.execute(
        select(TagesZusammenfassung)
        .where(and_(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        ))
    )
    tz_pro_tag: dict[date, TagesZusammenfassung] = {
        t.datum: t for t in tz_result.scalars().all()
    }

    # Speicher-Kapazität für die Tages-Vollzyklen. Pro Tag ausgewertet, weil ein
    # Speicher mitten im Zeitraum dazukommen oder stillgelegt werden kann
    # ([[feedback_anschaffungsdatum_grenze]]).
    speicher_result = await db.execute(
        select(Investition).where(and_(
            Investition.anlage_id == anlage_id,
            Investition.typ == "speicher",
        ))
    )
    speicher_invs = list(speicher_result.scalars().all())

    # Sonstiges-Geräte für die beiden Sonstiges-Spalten. Wie beim Speicher pro
    # Tag ausgewertet — ein Heizstab kann mitten im Zeitraum dazukommen oder
    # stillgelegt werden ([[feedback_anschaffungsdatum_grenze]]).
    sonstiges_result = await db.execute(
        select(Investition).where(and_(
            Investition.anlage_id == anlage_id,
            Investition.typ == "sonstiges",
        ))
    )
    sonstiges_invs = list(sonstiges_result.scalars().all())

    # Erzeuger für den Nenner des spezifischen Tagesertrags (F-58). Wie Speicher
    # und Sonstiges pro Tag ausgewertet: ein String, der mitten im Zeitraum
    # dazukommt oder stillgelegt wird, gehört nur an seinen eigenen Tagen in den
    # Nenner ([[feedback_anschaffungsdatum_grenze]]). Der frühere Nenner war der
    # gepflegte `Anlage.leistung_kwp` — ein zeitloser Skalar, den seit dem
    # Wegfall des Summenvergleichs nichts mehr gegen die Investitionen hielt.
    erzeuger_result = await db.execute(
        select(Investition).where(and_(
            Investition.anlage_id == anlage_id,
            Investition.typ.in_(("pv-module", "balkonkraftwerk")),
        ))
    )
    erzeuger_invs = list(erzeuger_result.scalars().all())

    # Monatsdaten des Zeitraums für den Flex-Ø-Override. Bei dynamischem Tarif
    # trägt `netzbezug_durchschnittspreis_cent` den ABGERECHNETEN Monats-Ø und
    # schlägt den Stammdaten-Arbeitspreis (`resolve_netzbezug_preis_cent`).
    # Ohne diese Zeilen rechnete der Tag mit dem Referenzpreis, während Monat
    # und Jahr den Ø nahmen — Σ Tage ≠ Monat ([[feedback_aggregator_symmetrie]]).
    md_result = await db.execute(
        select(Monatsdaten).where(and_(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr >= von.year,
            Monatsdaten.jahr <= bis.year,
        ))
    )
    md_pro_monat: dict[tuple[int, int], Monatsdaten] = {
        (m.jahr, m.monat): m for m in md_result.scalars().all()
    }

    # #377 — Zählerstände je Tag. **Einmal** für den ganzen Zeitraum geladen und
    # dann je Tag ausgewertet: eine Abfrage je Tag wären bei einem Jahr 365.
    #
    # Der Wert einer Tageszeile ist der **letzte Stand des Tages** — ein
    # Zählerstand ist eine Bestandsgröße, kein Tagesumsatz. Was sich am Tag
    # bewegt hat, ist die Differenz zum Vortag, und die bildet der Client aus
    # zwei benachbarten Zeilen; hier steht der Stand selbst.
    zaehler_stand_pro_tag: dict[date, dict[str, float]] = defaultdict(dict)
    try:
        for _zf in await lade_zaehlerstaende(
            db, anlage_id,
            datetime.combine(von, datetime.min.time()),
            datetime.combine(bis, datetime.max.time()),
            mit_verlauf=True, nur_aktive=False,
        ):
            for _p in _zf.verlauf:
                # Späterer Punkt gewinnt — der Verlauf ist aufsteigend sortiert.
                zaehler_stand_pro_tag[_p.zeitpunkt.date()][str(_zf.investition_id)] = _p.stand
    except Exception:  # pragma: no cover - eine Zusatzspalte kippt die Tabelle nicht
        logger.exception("Zählerstände für die Tages-Tabelle nicht ladbar")

    # HA-Bauform E4a-2 (Umschaltstelle 4): je Tag EINE Quellenwahl der Bilanz-Gruppe. Ein Kanal-Tag nimmt Mengen,
    # Eigenverbrauch, Quoten und die Bilanz-Schlüssel aus den Kanälen (Weg 2, kein Deckel); die übrigen Schlüssel
    # der Tageszeile und die stundengepaarten Spalten bleiben (B-3, D4). Ein Tag mit Wahl `bestand` rechnet wie bisher.
    from backend.services.kanal.bilanz_leser import kanal_tage

    kanal_je_tag = await kanal_tage(db, anlage_id, von, bis)
    # HA-Bauform E-S3-2: die Stunden eines Kanal-Tags aus dem Kanal-Stundentag (Mischzeilen) — Direktverbrauch,
    # Überschuss, Defizit, Zahl der Stunden, WP-Strom über dieselbe Layer-Formel wie die Stundenzeilen (S3-R5).
    from backend.services.energie_profil.kanal_stunden import (
        GRUPPE_BILANZ, GRUPPE_SONSTIGES, komponenten_der_tage, stunden_der_kanal_tage,
    )

    kanal_stunden_je_tag = await stunden_der_kanal_tage(
        db, anlage_id, kanal_je_tag, {**tep_pro_tag, bis + timedelta(days=1): tep_folgetag},
    )
    # HA-Bauform S5 (E-S5-3, §10h 6): die Tageskomponenten über die eine Mischung — diese Sicht liest aus ihnen nur die
    # Bilanz- (PV/BKW-Split, Erzeuger) und Sonstiges-Schlüssel (Sonstiges/Abgabe) und V2H (ohne Kanal, Tageszeile).
    komp_je_tag = await komponenten_der_tage(db, anlage_id, von, bis, gruppen=(GRUPPE_BILANZ, GRUPPE_SONSTIGES))

    alle_tage = sorted(set(tep_pro_tag) | set(tz_pro_tag) | set(kanal_je_tag))
    tarif_cache: dict[date, dict] = {}

    # ── Tageskosten aus Slot-Preisen (SOLL Flex-Tarife P-2/A-3, 17.09.2026) ──
    #
    # ⛔ **Hier stand bis dahin ``Tagesmenge × Monatspreis``.** Bei einem
    # dynamischen Tarif trug damit jeder Tag desselben Monats denselben Preis —
    # die Stundenpreise, die eedc mitschreibt, blieben ungenutzt, obwohl sie die
    # feinere und damit richtige Quelle sind (OB73-gif, #412-Folgemeldung;
    # Entscheid Gernot 17.09.2026: *„Tage bleiben Messung, Monat bleibt
    # Abrechnung"*).
    #
    # ⭐ **Für Festpreis-Anlagen ändert sich dadurch keine Zahl:** Der Helper
    # leitet den Slot-Preis dort aus dem Vertrag ab, und Σ(Menge_s × Preis) ist
    # identisch zu Tagesmenge × Preis (SOLL §10, Prüfstein 2).
    from backend.api.routes.strompreise import lade_tarife_je_stichtag

    _stichtage = sorted({date(t.year, t.month, 1) for t in alle_tage})
    _tarife_je_stichtag = await lade_tarife_je_stichtag(db, anlage_id, _stichtage)

    def _tarif_fuer(tag: date):
        """Der Vertragspreis-Träger dieses Slots — heute der Monatstarif.

        P-7 (Stichtag eines Vertragspreises ist der Beginn des Zeitraums, den
        die Zahl beschreibt — für einen Slot also sein Tag) ist damit noch
        **nicht** umgesetzt: Ein Tarifwechsel zur Monatsmitte wirkt hier erst im
        Folgemonat, wie bisher unter ADR-002/P8. Die Stelle dafür ist genau
        diese Funktion; der Helper nimmt sie als Callable entgegen.
        """
        return (_tarife_je_stichtag.get(date(tag.year, tag.month, 1)) or {}).get("allgemein")

    def _abgerechnet_fuer(tag: date):
        """Der abgerechnete Monats-Ø — Stufe 2 der Slot-Kaskade.

        ⚠ **Nicht wegoptimieren.** Ohne ihn zeigte ein dynamischer Tarif ohne
        Stundenmitschrift wieder den Stammpreis (30 ct) im Tag, während der
        Monat mit dem abgerechneten Ø (18 ct) rechnet — genau der Zustand, den
        `test_tage_werte_symmetrie.py::test_tage_werte_nehmen_den_abgerechneten_
        monats_durchschnittspreis` seit dem 30.07.2026 verhindert (Forum
        simon42 #89667/60).
        """
        _md = md_pro_monat.get((tag.year, tag.month))
        return getattr(_md, "netzbezug_durchschnittspreis_cent", None) if _md else None

    slot_kosten_je_tag = _slot_kosten_der_bestandstage(
        [r for r in alle_tep if r.datum <= bis], kanal_stunden_je_tag, von, _tarif_fuer, _abgerechnet_fuer,
    )
    # HA-Bauform S4 (§10a (3)): an einem Kanal-Tag dieselbe Kaskade über seine Mischzeilen — Kosten und EV-Preis im
    # Kalendertag wie der Netzbezug daneben (Preis zeilengleich gepaart, Beginn-Raster).
    slot_kosten_je_tag.update(_slot_kosten_der_kanal_tage(kanal_stunden_je_tag, _tarif_fuer, _abgerechnet_fuer))

    kx = _TageKontext(
        db=db,
        anlage_id=anlage_id,
        tep_pro_tag=tep_pro_tag,
        soc_gepaart=soc_gepaart,
        tz_pro_tag=tz_pro_tag,
        speicher_invs=speicher_invs,
        sonstiges_invs=sonstiges_invs,
        erzeuger_invs=erzeuger_invs,
        md_pro_monat=md_pro_monat,
        zaehler_stand_pro_tag=zaehler_stand_pro_tag,
        kanal_je_tag=kanal_je_tag,
        kanal_stunden_je_tag=kanal_stunden_je_tag,
        komp_je_tag=komp_je_tag,
        tarif_cache=tarif_cache,
        slot_kosten_je_tag=slot_kosten_je_tag,
    )

    zeilen: list[TagWerteResponse] = []

    for tag in alle_tage:
        zeilen.append(await _tageszeile(kx, anlage, tag))

    return zeilen


def _slot_kosten_der_bestandstage(zeilen: list, kanal_stunden_je_tag: dict, von: date, tarif_fuer,
                                  abgerechnet_fuer) -> dict:
    """Je Tag ohne Mischzeilen die Slot-Kosten (Kaskade P-6, ``slot_kosten_aus_zeilen``) aus den schon geladenen
    Stundenzeilen (``von``-1 … ``bis``) — dieselbe Zeilenfolge und Paarung wie ``lade_slot_kosten_je_tag`` über
    ``stunden_der_tage`` (Vortag für die Vorzeile, an Kanal-Tagen die Mischzeilen: ``stundenzeilen_mit_kanaelen``), ohne
    die Kanal-Stunden ein zweites Mal zu rechnen (HA-Bauform S5 E-S5-1b, Gate B). Die Kanal-Tage rechnet
    ``_slot_kosten_der_kanal_tage``. Die Vorzeile der Stunde 0 eines Tages nach einem Kanal-Tag trägt dort wie hier den
    Preis der Stundenzeile ``(D-1, 23)`` (Forward-Bahn der Mischzeile, S4-R-3b)."""
    from backend.services.energie_profil.kanal_stunden import stundenzeilen_mit_kanaelen
    from backend.services.strompreis_aggregator import slot_kosten_aus_zeilen

    folge = stundenzeilen_mit_kanaelen(zeilen, kanal_stunden_je_tag)
    gepaart = [(z, preis) for z, preis in zip(folge, forward_werte_je_backward_zeile(folge, "strompreis_cent"))
               if z.datum >= von and z.datum not in kanal_stunden_je_tag]
    return slot_kosten_aus_zeilen(gepaart, tarif_fuer=tarif_fuer, abgerechnet_fuer=abgerechnet_fuer)


def _slot_kosten_der_kanal_tage(kanal_stunden_je_tag: dict, tarif_fuer, abgerechnet_fuer) -> dict:
    """Je Kanal-Tag die Slot-Kosten (Kaskade P-6) aus seinen Mischzeilen (HA-Bauform S4, §10a (3))."""
    from backend.services.strompreis_aggregator import slot_kosten_aus_zeilen

    gepaart = [(z, preis) for zeilen in kanal_stunden_je_tag.values()
               for z, preis in zip(zeilen, forward_werte_je_backward_zeile(zeilen, "strompreis_cent"))]
    return slot_kosten_aus_zeilen(gepaart, tarif_fuer=tarif_fuer, abgerechnet_fuer=abgerechnet_fuer)


async def _tageszeile(kx: _TageKontext, anlage: Anlage, tag: date) -> TagWerteResponse:
    """Die Werte-Zeile EINES Tages (RF-20: Schleifenrumpf von `baue_tage_werte`, Reihenfolge = HEAD).

    `anlage` reist als eigener Name statt in `kx`: der P3-a-Wächter erlaubt `anlage.leistung_kwp` nur am Namen."""
    stunden_rows = kx.tep_pro_tag.get(tag, [])
    tz = kx.tz_pro_tag.get(tag)
    bilanz, komp_tag, verworfen_tag, kanal_tag, v2h_tag = _tagesbilanz(kx, tag, stunden_rows, tz)

    # Grundlast dieser Nacht (ADR-001: Sourcing hier, Formel im Layer).
    # Der Filter ist WOERTLICH der der Monats-/Jahres-Kachel
    # (`aktueller_monat._load_grundlast_nacht_kw`): Stunden < 5, nur
    # `verbrauch_kw` ueber 0. Wer ihn hier „verbessert", erzeugt zwei
    # Grundlasten, die sich nicht mehr erklaeren lassen.
    # ⚠ Keine Mindestzahl an Nachtstunden: fehlen sie ganz, liefert
    # `berechne_grundlast` None und die Spalte zeigt „—" (Total-Fall);
    # eine Teilabdeckung bleibt stehen, wie ueberall im Baum.
    # ⚠ Zählerlücken wie HA (§2, Grundlast-Guard): eine Zeile, deren
    # Verbrauchs-Achsen mehr als eine reale Stunde tragen, ist keine
    # Stunden-Stichprobe — sie trüge den Verbrauch einer ganzen Lücke als
    # „Nachtleistung". R6 lässt `verbrauch_kw` bei verschiedenen Spannen
    # schon leer; bei gleicher Spanne fällt die Zeile hier heraus.
    # HA-Bauform S4 (§10a (3)): an einem Kanal-Tag aus seinen Mischzeilen (Stunden 0–4 = [00:00, 05:00) des
    # Kalendertags), sonst aus den Stundenzeilen (Slots 0–4).
    stunden_des_tags = kx.kanal_stunden_je_tag.get(tag, stunden_rows)
    nacht_kw = [
        float(r.verbrauch_kw) for r in stunden_des_tags
        if r.stunde < 5 and r.verbrauch_kw is not None and r.verbrauch_kw > 0
        and not verbrauch_gebuendelt(r)
    ]
    grundlast_kw = berechne_grundlast(
        nacht_verbrauch_kw=nacht_kw,
        gesamtverbrauch_kwh=None,   # der Anteil hat hier keinen Leser
        tage=1,
    ).grundlast_kw

    # Nenner des spezifischen Tagesertrags (F-58). `mit_bkw=True`, weil der
    # Zähler `bilanz.erzeugung_kwh` die Kategorie `pv` ist und ein
    # Balkonkraftwerk dort mitläuft (`live_sensor_config.py`).
    kwp_tag = anlagen_kwp(
        kx.erzeuger_invs, tag, mit_bkw=True, referenzwert=anlage.leistung_kwp,
    )

    # Erträge je Erzeuger (#350, Rainer): erst der Boundary-Rollup, sonst die
    # Σ der Stunden-Komponenten. Der Rollup fehlt im Standalone-Betrieb und an
    # einzelnen Tagen auch im Add-on-Modus — genau deshalb liest die
    # Tages-Komponenten-Kachel im Client schon länger von den Stunden
    # (`v4/TagKomponenten.tsx`). Die ID-Normalisierung liegt im Layer, weil
    # dasselbe Balkonkraftwerk in den beiden Keyspaces `bkw_<id>` bzw.
    # `pv_<id>` heißt — je Roh-Key gruppiert ergäbe das zwei Spalten für ein
    # Gerät (s. `erzeuger_kwh_je_investition`).
    erzeuger_kwh = erzeuger_kwh_je_investition(komp_tag)
    if not erzeuger_kwh:
        erzeuger_kwh = erzeuger_kwh_je_investition(
            aggregiere_tep_komponenten(stunden_rows)
        )

    # Sonstiges je Richtung — dieselbe Quellen-Präzedenz wie eine Zeile
    # darüber: erst der Boundary-Rollup, sonst die Σ der Stunden. Die
    # Kategorien werden **je Tag** gebildet, damit die Laufzeitgrenze des
    # Geräts gilt und nicht die des Zeitraums.
    sonstiges_kategorien = {
        str(i.id): ((i.parameter or {}).get("kategorie") or "")
        for i in kx.sonstiges_invs if i.ist_aktiv_an(tag)
    }
    sonstiges = sonstiges_kwh_je_richtung(
        komp_tag, sonstiges_kategorien
    )
    # §9.2: die Abgabe zählt als dritte Richtung — sonst überschriebe der
    # Leistungspfad-Fallback einen Tag, der NUR eine Abgabe gemessen hat.
    if (
        sonstiges.erzeugung_kwh is None and sonstiges.verbrauch_kwh is None
        and sonstiges.abgabe_kwh is None
    ):
        sonstiges = sonstiges_kwh_je_richtung(
            aggregiere_tep_komponenten(stunden_rows), sonstiges_kategorien
        )
    abgabe_tag, ev_tag, autarkie_tag, evq_tag = _abgabe_und_quoten(bilanz, sonstiges)
    # ── Speicher-η: derselbe Maßstab wie im Monat (Melder Knallfrosch,
    # T89667 #163). Der rohe Quotient Entladung ÷ Ladung stand hier ohne
    # jede Einordnung — an einem Tag, der voll beginnt und leer endet,
    # ergibt er über 100 %. `Cockpit → Monat` unterdrückt das seit F-22 und
    # nennt die Quelle; die Tagessicht tat beides nicht. ΔSoC kommt aus den
    # ohnehin geladenen Stunden-Rows, kostet also keine zusätzliche Abfrage.
    # ⭐ **N-387: der Ladestand jeder Zeile kommt aus ihrer Vorzeile.** Die
    # Lade-/Entlademengen daneben stammen aus Σ `batterie_kw` über die
    # Backward-Slots `[Vortag 23:00, 23:00)`. Der SoC der Zeile 0 beschrieb
    # forward `[00,01)` (Schwerpunkt 00:30) und lag damit **1½ h** hinter
    # dem Beginn der Mengenreihe, der SoC der Zeile 23 (`[23,24)`,
    # Schwerpunkt 23:30) ½ h dahinter — der Rand war unsymmetrisch. Mit der
    # Vorzeile sind es ½ h auf beiden Seiten (Zeile 0 ← Vortag 23 ⇒ 23:30,
    # Zeile 23 ← Zeile 22 ⇒ 22:30).
    # HA-Bauform S4 (S4-R-3b): an einem Kanal-Tag die Mischzeilen, deren Ladestand zeilengleich gepaart ist.
    soc_je_zeile = (forward_werte_je_backward_zeile(kx.kanal_stunden_je_tag[tag], "soc_prozent")
                    if tag in kx.kanal_stunden_je_tag
                    else [kx.soc_gepaart.get((r.datum, r.stunde)) for r in stunden_rows])
    soc_delta = delta_soc_kwh(
        soc_je_zeile,
        sum(
            get_speicher_nutzbare_kapazitaet_kwh(i) or 0
            for i in kx.speicher_invs if i.ist_aktiv_an(tag)
        ),
    )
    eta = speicher_wirkungsgrad(
        bilanz.speicher_ladung_kwh, bilanz.speicher_entladung_kwh, soc_delta,
    )

    # §51 gilt nur für Anlagen mit gesetztem Schalter — das Gate liegt im
    # Erlös-Service, nicht hier (bis 2026-08-03 las diese Zeile die Spalte
    # roh und kürzte den Erlös auch ohne §51-Pflicht).
    neg_preis_kwh = neg_preis_einspeisung_tageswert(
        anlage, tz.einspeisung_neg_preis_kwh if tz else None
    )
    geld = await _geld_spalten(kx, tag, bilanz, abgabe_tag, neg_preis_kwh, kanal_tag)

    return TagWerteResponse(
        datum=tag,
        stunden_verfuegbar=(tz.stunden_verfuegbar if tz else bilanz.stunden),
        datenquelle=(tz.datenquelle if tz else None),
        # Zählerlücken wie HA (R4/R9): Markierung + Regelmarke der Tageszeile.
        verworfen=verworfen_tag,
        # N-567: Nachtrag nach Nullstunden — benannt, in den Summen enthalten.
        nachtrag=(tz.nachtrag if tz else None),
        **_energie_spalten(
            bilanz=bilanz, komp_tag=komp_tag, ev_tag=ev_tag, autarkie_tag=autarkie_tag, evq_tag=evq_tag,
            kwp_tag=kwp_tag, v2h_tag=v2h_tag, eta=eta, speicher_invs=kx.speicher_invs, tag=tag, sonstiges=sonstiges,
        ),
        **geld,
        **_tagnative_spalten(
            tag=tag, tz=tz, bilanz=bilanz, grundlast_kw=grundlast_kw, neg_preis_kwh=neg_preis_kwh,
            erzeuger_kwh=erzeuger_kwh, zaehler_stand_pro_tag=kx.zaehler_stand_pro_tag,
        ),
    )


def _tagesbilanz(kx: _TageKontext, tag: date, stunden_rows: list, tz: Optional[TagesZusammenfassung]):
    """Die Tagesbilanz: Stundenzeilen nach der Regelmarke, an einem Kanal-Tag gemischt (E4a-2), danach EINMAL V2H.

    Rückgabe ``(bilanz, komp_tag, verworfen_tag, kanal_tag, v2h_tag)`` — die HEAD-Namen des Schleifenrumpfs."""
    from backend.services.kanal.bilanz_leser import mische_bilanz, mische_verworfen

    # Zählerlücken wie HA (R7/R9): die Tageszeile sagt selbst, nach welcher
    # Regel sie gerechnet ist — `verworfen` ist die Regelmarke. Ohne Marke
    # (Altbestand) rechnet der Tag N-92 wie bisher (E6).
    # HA-Bauform E-S3-2: an einem Kanal-Tag sind die Zeilen die Mischzeilen des Kanal-Stundentags — `mische_bilanz`
    # nimmt aus ihnen nur die stundengepaarten Größen (D4); Mengen, Ladung/Entladung kommen aus der Komposition (H-2).
    bilanz = bilanz_aus_stundenrows(
        kx.kanal_stunden_je_tag.get(tag, stunden_rows), verworfen=(tz.verworfen if tz else None),
    )
    # HA-Bauform E4a-2/S4 §10a (4)/S5 E-S5-3: an einem Kanal-Tag die Bilanz-Schlüssel und Sonstiges/Abgabe im
    # Kalendertag aus den Kanälen (`kx.komp_je_tag`, die eine Mischung), sonst die Tageszeile. V2H hat keinen Kanal
    # (`katalog.TAGESGROESSE_OHNE_KANAL`) und bleibt aus der Tageszeile (benannt).
    komp_tag = kx.komp_je_tag.get(tag, tz.komponenten_kwh if tz else None)
    verworfen_tag = tz.verworfen if tz else None
    kanal_tag = kx.kanal_je_tag.get(tag)
    if kanal_tag is not None:
        bilanz = mische_bilanz(kanal_tag.bilanz, bilanz)
        verworfen_tag = mische_verworfen(verworfen_tag)
    # ⭐ #110 V2H-Tageswert (Konzept §2, B5/B6): die Rückspeisung des E-Autos ins Haus aus dem Rollup
    # (`v2h_<id>`, Σ; `None` ohne Key — eine 0,0 ist gemessen). EINMAL nach dem Mischen: an einem Kanal-Tag
    # kommen Gesamtverbrauch, Eigenverbrauch und Quoten aus der Kanal-Komposition, und die kennt kein V2H
    # (Kanal-Klasse „Tagesgröße ohne Kanal", O2). `mische_komponenten` lässt `v2h_<id>` stehen (kein
    # Bilanz-Schlüssel). Die Funktion rechnet aus den Summen der Bilanz neu — idempotent, ohne Regelmarke
    # (Altbestand) wirkungslos.
    v2h_tag = summe_v2h_kwh(komp_tag)
    bilanz = mit_v2h_entladung(bilanz, v2h_tag)
    return bilanz, komp_tag, verworfen_tag, kanal_tag, v2h_tag


def _abgabe_und_quoten(bilanz, sonstiges):
    """Eigenverbrauch, Autarkie und EV-Quote des Tages ohne die Abgabe an Dritte (§9.2).

    Rückgabe ``(abgabe_tag, ev_tag, autarkie_tag, evq_tag)``."""
    # §9.2: die Abgabe an Dritte ist kein Eigenverbrauch — dieselbe Regel
    # wie im Monats-Layer (`berechne_verbrauchs_kennzahlen`). Die Stunden-
    # Bilanz kennt sie nicht (sie sieht nur den Netzpunkt); der Tag zieht
    # die gemessene Tagesmenge ab und bildet Autarkie und Quote neu.
    abgabe_tag = sonstiges.abgabe_kwh or 0.0
    ev_tag = (
        None if bilanz.eigenverbrauch_kwh is None
        else max(0.0, bilanz.eigenverbrauch_kwh - abgabe_tag)
    )
    autarkie_tag = bilanz.autarkie_prozent
    evq_tag = bilanz.ev_quote_prozent
    if abgabe_tag > 0 and ev_tag is not None:
        if bilanz.netzbezug_erfasst:
            autarkie_tag = autarkie_prozent(ev_tag, ev_tag + bilanz.netzbezug_kwh)
        if bilanz.pv_erfasst:
            evq_tag = eigenverbrauchsquote_prozent(ev_tag, bilanz.erzeugung_kwh)
    return abgabe_tag, ev_tag, autarkie_tag, evq_tag


async def _geld_spalten(kx: _TageKontext, tag: date, bilanz, abgabe_tag, neg_preis_kwh, kanal_tag) -> dict:
    """Finanzzeile des Tages über den SoT (eine Abfrage-Folge je Tag) und die Geld- und CO₂-Spalten der Antwort."""
    # ── Finanzen über den SoT-Helper (je-Monat-Tarif, §51-bereinigt) ──
    eingabe = FinanzZeileEingabe(
        jahr=tag.year,
        monat=tag.month,
        einspeisung_kwh=bilanz.einspeisung_kwh,
        netzbezug_kwh=bilanz.netzbezug_kwh,
        pv_erzeugung_kwh=bilanz.erzeugung_kwh,
        abgabe_dritte_kwh=abgabe_tag,
        neg_preis_kwh=neg_preis_kwh,
        # N-635: Ladung und Entladung des Tages gehen mit, damit die
        # Finanz-Eigenverbrauchsmenge dieselbe Formel rechnet wie die
        # Energie-Spalte `eigenverbrauch` (Direktverbrauch + Entladung).
        # #110: V2H aus dem Rollup — dieselbe Menge wie in `bilanz`
        # (`mit_v2h_entladung`). BKW-Eigenverbrauch bleibt 0 (kein Tageswert).
        speicher_ladung_kwh=bilanz.speicher_ladung_kwh,
        speicher_entladung_kwh=bilanz.speicher_entladung_kwh,
        v2h_entladung_kwh=bilanz.v2h_entladung_kwh,
        monatsdaten=kx.md_pro_monat.get((tag.year, tag.month)),
        # A-2: Die Ersparnis bewertet VERMIEDENEN Bezug — sie wird deshalb
        # mit dem Preis der Slots gewichtet, in denen er vermieden wurde,
        # nicht mit dem des tatsächlichen Bezugs. Ohne Slot-Daten bleibt es
        # beim Bezugspreis (der Helper liefert dann `None`).
        ev_preis_cent=(
            kx.slot_kosten_je_tag[tag].ev_mittel_cent
            if tag in kx.slot_kosten_je_tag else None
        ),
        # N-588: an einem Kanal-Tag die Wandlungsverluste des Tages samt Messpunkt-Vertrag — die Ersparnis bewertet
        # den Eigenverbrauch ohne sie (am Klemmtag des Volleinspeisers 0 statt Cent-Beträgen). Bestand: keine.
        wandlungsverluste_kwh=kanal_tag.wandlungsverluste_kwh if kanal_tag is not None else None,
        verluste_grund=kanal_tag.verluste_grund if kanal_tag is not None else None,
    )
    finanz_zeile = await baue_finanz_zeile(
        kx.db, kx.anlage_id, eingabe, tarif_cache=kx.tarif_cache
    )
    finanz = berechne_finanz_aggregat([finanz_zeile])
    # Ein €-Betrag ist nur so belastbar wie die Menge, auf der er steht.
    # Fehlt die Menge ganz, ist der Betrag keine 0, sondern nicht
    # bestimmbar — sonst stünde in derselben Zeile „— kWh Netzbezug" neben
    # „0,00 € Netzbezug-Kosten" (Entscheid Gernot, 15.08.2026, im Zuge von
    # T89667 #162). Der Finanz-SoT bleibt unangetastet: er rechnet mit den
    # Mengen, die er bekommt; die Aussage über ihre Herkunft trifft diese
    # Schicht. Die umfassende Regel dafür ist die Bewertungsgrenze (eigener
    # Auftrag) — hier stehen nur die zwei Beträge, deren Menge diese Zeile
    # selbst als fehlend ausweist.
    # Die Kosten dieses Tages sind die Summe seiner Slot-Kosten (A-3), nicht
    # Menge × Ø. Fehlen Slot-Zeilen ganz, gibt es keinen Betrag — und keine
    # 0: `None` ist hier „nicht bestimmbar", genau wie eine Zeile darüber
    # für die fehlende Menge.
    _slot = kx.slot_kosten_je_tag.get(tag)
    netzbezug_kosten = (
        _slot.kosten_euro
        if bilanz.netzbezug_erfasst and _slot is not None else None
    )
    ev_ersparnis = (
        finanz.ev_ersparnis_euro if bilanz.eigenverbrauch_kwh is not None else None
    )
    # Beide Summen erben die Lücke ihres Summanden. Ohne das wanderte der
    # Widerspruch nur eine Kachel weiter: „Netto-Ertrag 1,28 €" über einer
    # Bilanz-Tabelle, in der die EV-Ersparnis mit „—" dasteht.
    # Stufe 1 der Ergebnis-Leiter (03.10.2026) — ohne USt-Anteil: ein Tag kennt keine Jahresgröße, Σ Tage ≠ Monat
    # bleibt dokumentiert (BERECHNUNGEN §Tag). Pflichtposten wie im Monat: ohne EV-Ersparnis kein Netto-Ertrag.
    netto_ertrag = berechne_ergebnis(ErgebnisEingang(
        einspeise_erloes=finanz.einspeise_erloes_euro, ev_ersparnis=ev_ersparnis,
        bkw_rest_ersparnis=finanz.bkw_ersparnis_euro, erzeuger_erloes=finanz.erzeuger_erloes_euro,
        sonstige_netto=finanz.sonstige_netto_euro,
    )).netto_ertrag
    netto_bilanz = (
        netto_ertrag - netzbezug_kosten
        if netto_ertrag is not None and netzbezug_kosten is not None else None
    )

    return dict(
        # Finanzen — bewusst UNGERUNDET, wie der Monatspfad
        # (`aktueller_monat.py`) sie liefert. Bis 15.08.2026 stand hier je
        # ein `round(…, 2)`, und das erzeugte zwei sichtbare Widersprüche
        # auf derselben Seite (Melder Knallfrosch, T89667 #163):
        #   · Die Finanz-Bilanz-Tabelle summiert die gerundeten Summanden
        #     (7,49 + 8,55 = 16,04), die Netto-Ertrag-Kachel zeigte die
        #     gerundete Summe (16,05) — Summe der Gerundeten gegen
        #     gerundete Summe.
        #   · „Ø-Preis Netz" teilt Kosten ÷ Menge. Bei 0,19 kWh machte der
        #     auf 2 Stellen gerundete Cent-Betrag daraus 31,6 ct/kWh,
        #     während dieselbe Seite mit ~29,5 ct rechnete.
        # Gerundet wird jetzt erst bei der Anzeige (Client, 2 Stellen); die
        # Σ-Zeile der Werte-Tabelle summiert dadurch ebenfalls exakt.
        einspeise_erloes=finanz.einspeise_erloes_euro,
        ev_ersparnis=ev_ersparnis,
        netzbezug_kosten=netzbezug_kosten,
        netto_ertrag=netto_ertrag,
        netto_bilanz=netto_bilanz,
        # CO₂ — Kanon statt eigener Formel; nur der PV-Anteil ist auf
        # Tagesebene bestimmbar (s. Modul-Docstring). WP-Strom wird bewusst
        # NICHT übergeben: ohne die zugehörige Wärmemenge wäre die
        # WP-Komponente rein negativ und damit eine Falschaussage.
        # Ohne erfassten Eigenverbrauch gibt es keine CO₂-Aussage — vorher
        # wurde aus dem negativen Eigenverbrauch eine negative „Einsparung".
        co2_einsparung=(
            round(
                berechne_co2_bilanz(
                    # N-588 (P15): dieselbe Menge wie die Ersparnis — ohne Wandlungsverluste des Kanal-Tags.
                    eigenverbrauch_kwh=eigenverbrauch_ohne_verluste_kwh(
                        bilanz.eigenverbrauch_kwh,
                        kanal_tag.wandlungsverluste_kwh if kanal_tag is not None else None,
                        kanal_tag.verluste_grund if kanal_tag is not None else None,
                    )
                ).co2_pv_kg,
                1,
            )
            if bilanz.eigenverbrauch_kwh is not None else None
        ),
    )


def _energie_spalten(
    *, bilanz, komp_tag, ev_tag, autarkie_tag, evq_tag, kwp_tag, v2h_tag, eta, speicher_invs, tag, sonstiges,
) -> dict:
    """Energie-, Quoten-, Speicher-, WP- und Sonstiges-Spalten der Antwortzeile."""
    return dict(
        # Energie. `erzeugung` ist None, solange keine Stunde einen PV-Wert
        # trug — eine 0 wäre hier nicht „nichts erzeugt", sondern „nicht
        # gemessen" (`docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`). Betrifft
        # Anlagen, deren PV nur als Anlagen-Aggregat gepflegt ist: das
        # versorgt den Monat, nicht die Tagesebene.
        erzeugung=(round(bilanz.erzeugung_kwh, 3) if bilanz.pv_erfasst else None),
        # PV/BKW-Split (R17/Verlauf) aus dem Tages-komponenten_kwh-JSON.
        pv_anlage=round(summe_pv_anlage_kwh(komp_tag) if komp_tag is not None else 0.0, 3),
        bkw=round(summe_bkw_kwh(komp_tag) if komp_tag is not None else 0.0, 3),
        eigenverbrauch=_r(ev_tag, 3),
        # Dieselbe Regel wie bei `erzeugung` darüber, jetzt auf allen vier
        # Achsen: eine Achse, die an KEINER Stunde des Tages einen Wert
        # trug, ist nicht 0, sondern nicht gemessen. Strikers Januar zeigte
        # sonst „— PV · 106 kWh Einspeisung · 0 kWh Netzbezug" in einer
        # Zeile — die 0 war die einzige Zahl daran, die nichts gemessen
        # hatte (T89667 #162). Träger, nicht `> 0`: wer einen Tag lang
        # nichts bezieht, hat eine gemessene 0 und behält sie.
        einspeisung=(round(bilanz.einspeisung_kwh, 3) if bilanz.einspeisung_erfasst else None),
        netzbezug=(round(bilanz.netzbezug_kwh, 3) if bilanz.netzbezug_erfasst else None),
        gesamtverbrauch=(round(bilanz.gesamtverbrauch_kwh, 3) if bilanz.verbrauch_erfasst else None),
        # Σ min(pv, verbrauch) — braucht beide Achsen, wie die Summe selbst
        # (der Layer zählt nur Stunden mit beiden Werten).
        direktverbrauch=(
            round(bilanz.direktverbrauch_kwh, 3)
            if bilanz.pv_erfasst and bilanz.verbrauch_erfasst else None
        ),
        # Quoten
        autarkie=_r(autarkie_tag, 1),
        evQuote=_r(evq_tag, 1),
        spezErtrag=(
            round(bilanz.erzeugung_kwh / kwp_tag, 2)
            if kwp_tag > 0 and bilanz.pv_erfasst else None
        ),
        # Speicher (None wenn kein Lade-/Entlade-Geschehen)
        speicher_ladung=_nz(bilanz.speicher_ladung_kwh),
        speicher_entladung=_nz(bilanz.speicher_entladung_kwh),
        # #110: `None` ohne V2H-Schlüssel im Rollup; nur mit Regelmarke in der Bilanz (Altbestand: keiner).
        v2h_entladung=(_r(v2h_tag, 3) if bilanz.regelmarke else None),
        speicher_effizienz=_r(eta.prozent, 1),
        speicher_effizienz_quelle=eta.quelle,
        speicher_vollzyklen=_r(berechne_vollzyklen(
            bilanz.speicher_entladung_kwh,
            sum(
                get_speicher_kapazitaet_kwh(i) or 0
                for i in speicher_invs if i.ist_aktiv_an(tag)
            ),
        ), 2),
        # E4d (Bauplan §8a, Rest N-585): eine gemessene 0 ist erfasst — 0 statt „—" (`wp_erfasst`).
        wp_strom=(round(bilanz.wp_strom_kwh, 3) if getattr(bilanz, "wp_erfasst", False) else None),
        sonstiges_erzeugung=_r(sonstiges.erzeugung_kwh, 3),
        sonstiges_verbrauch=_r(sonstiges.verbrauch_kwh, 3),
        sonstiges_abgabe=_r(sonstiges.abgabe_kwh, 3),
    )


def _tagnative_spalten(*, tag, tz, bilanz, grundlast_kw, neg_preis_kwh, erzeuger_kwh, zaehler_stand_pro_tag) -> dict:
    """Tag-native Spalten (Überschuss/Defizit, Peaks, Grundlast, PR, Wetter, Börse, §51), Erzeuger und Zählerstände."""
    return dict(
        # Tag-native. Überschuss und Defizit entstehen stundenweise aus
        # PV **und** Verbrauch — fehlt eine der beiden Achsen ganz, ist die
        # Summe 0 aus Mangel an Eingabe, nicht aus Ausgeglichenheit.
        ueberschuss_kwh=(
            round(bilanz.ueberschuss_kwh, 3)
            if bilanz.pv_erfasst and bilanz.verbrauch_erfasst else None
        ),
        defizit_kwh=(
            round(bilanz.defizit_kwh, 3)
            if bilanz.pv_erfasst and bilanz.verbrauch_erfasst else None
        ),
        peak_pv_kw=(tz.peak_pv_kw if tz else None),
        peak_netzbezug_kw=(tz.peak_netzbezug_kw if tz else None),
        grundlast_kw=grundlast_kw,
        peak_einspeisung_kw=(tz.peak_einspeisung_kw if tz else None),
        # PR ohne erfasste PV ist keine 0, sondern keine Aussage. Der
        # Aggregator schreibt sie seit demselben Paket gar nicht mehr;
        # diese Zeile deckt die Tage, die vorher schon eine 0 gespeichert
        # haben — es gibt bewusst keinen Migrationslauf.
        performance_ratio=(
            tz.performance_ratio if (tz and bilanz.pv_erfasst) else None
        ),
        batterie_vollzyklen=(tz.batterie_vollzyklen if tz else None),
        temperatur_min_c=(tz.temperatur_min_c if tz else None),
        temperatur_max_c=(tz.temperatur_max_c if tz else None),
        strahlung_summe_wh_m2=(tz.strahlung_summe_wh_m2 if tz else None),
        gti_summe_wh_m2=(tz.gti_summe_wh_m2 if tz else None),
        boersenpreis_avg_cent=(tz.boersenpreis_avg_cent if tz else None),
        boersenpreis_min_cent=(tz.boersenpreis_min_cent if tz else None),
        negative_preis_stunden=(tz.negative_preis_stunden if tz else None),
        # Ausweis-Spalte: dasselbe Gate wie die Rechnung darüber — sonst
        # nennt die Tagestabelle eine §51-Menge, die die Monatstabelle bei
        # derselben Anlage verschweigt (`monatsdaten.py`).
        einspeisung_neg_preis_kwh=neg_preis_kwh,
        # Leer bleibt leer: ohne eigenen Sensor je Erzeuger gibt es hier
        # keinen Wert. Auf Tagesebene wird **nicht** nach kWp verteilt
        # (anders als im Monat) — eine verteilte Tageszahl wäre in der
        # Spalte „Dach Süd" eine Behauptung über eine Messung, die es nicht
        # gibt (#352-Klasse).
        erzeuger_kwh={k: round(v, 3) for k, v in erzeuger_kwh.items()} or None,
        # #377: der Stand am Ende dieses Tages, je Zähler-Gerät.
        zaehler_stand={
            k: round(v, 3) for k, v in zaehler_stand_pro_tag.get(tag, {}).items()
        } or None,
    )


def _r(v: float | None, dec: int) -> float | None:
    return round(v, dec) if v is not None else None


def _nz(v: float) -> float | None:
    """0-Σ → None (keine aktive Komponente an dem Tag)."""
    return round(v, 3) if abs(v) > 1e-9 else None
