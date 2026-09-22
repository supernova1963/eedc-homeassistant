"""HA-Export — die Investitions-Sensoren: `calculate_investition_sensors` je Komponente (Speicher, E-Auto, Wärmepumpe,
Wallbox, Balkonkraftwerk, Sonstiges) aus den Monats-Fakten und dem Layer-SoT.
"""
# Reiner Umzug aus `api/routes/ha_export.py` (18.09.2026, Vorlage 8 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from backend.core.berechnungen import heizwaerme_ist_abgeleitet
from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag
from backend.core.berechnungen.fenster import verteile_auf_guenstigste
from backend.services.daten_checker.kuehl_zaehler import hat_kuehl_zaehler
from backend.core.berechnungen.waermepumpe_kennzahl import (
    abgrenzungs_grund,
    arbeitszahl,
    ersparnis_vorbehalt,
    heizwaerme_kwh,
    waerme_gesamt_kwh,
)
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from datetime import date
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    monats_strompreis_lookup,
    resolve_strompreis_for_komponente,
)
from backend.core.betriebsmodus import BETRIEBSMODUS_LABEL
from backend.core.berechnungen.betriebsart_gemessen import (
    ModusStromZeile,
    funktionsfremd_abzug_kwh,
    modus_strom_zeile,
)
from backend.core.field_definitions import (
    get_emob_pv_netz_kwh,
    get_wp_strom_kwh,
    get_wp_warmwasser_kwh,
    nenner_ist_feine_summe,
)
from backend.services.eauto_wirtschaftlichkeit import berechne_eauto_ersparnis_periode
from backend.models.monatsdaten import Monatsdaten
from backend.services.energie_profil.modus_split_monat import lade_modus_split_ohne_abschluss
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.strompreis import Strompreis
from backend.services.ha_sensors_export import (
    SensorValue,
    INVESTITION_SENSOREN,
    E_AUTO_SENSOREN,
    WAERMEPUMPE_SENSOREN,
)
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    abgrenzung_stoerung,
)
from backend.api.routes.ha_export.emob import _EmobPoolCtx, _emob_month_share


def laufzeit_attribute(investition: Investition, heute: Optional[date] = None) -> dict:
    """N-543 — die Laufzeit eines Geraets als Attribute seines Kosten-Sensors.

    ⛔ **Warum (Gernot, 21.09.2026):** Der Geraete-Export laeuft ueber ALLE Investitionen
    der Anlage (`ha_mqtt_sync.py`, `sensoren.py` — kein Filter), die anlagenweite Summe
    `investition_gesamt_euro` nur ueber die heute aktiven (`anlage_sensoren.py`,
    `aktiv_jetzt()`). In HA stand damit je Geraet ein Kostenwert, dem man weder Laufzeit
    noch Stilllegung ansah, neben einer Summe, die stillgelegte Geraete nicht enthaelt.
    Die Attribute machen es sichtbar; sie rechnen nichts neu (Stammdaten).

    `betriebsjahre`: von der Anschaffung bis heute bzw. bis zur Stilllegung, eine
    Nachkommastelle; `None` ohne Anschaffungsdatum (ADR-002/P4 — keine erfundene 0).
    """
    heute = heute or date.today()
    ab = investition.anschaffungsdatum
    bis = investition.stilllegungsdatum
    ende = bis if (bis and bis < heute) else heute
    jahre = round((ende - ab).days / 365.25, 1) if ab else None
    return {
        "anschaffungsdatum": ab.isoformat() if ab else None,
        "stilllegungsdatum": bis.isoformat() if bis else None,
        "aktiv": bool(investition.aktiv) and not (bis and bis < heute),
        "betriebsjahre": jahre,
    }


async def calculate_investition_sensors(
    db: AsyncSession,
    investition: Investition,
    strompreis: Optional[Strompreis],
    emob_ctx: Optional[_EmobPoolCtx] = None,
    modus_map: Optional[dict[int, str]] = None,
    fenster_ctx=None,
) -> list[SensorValue]:
    """Berechnet Sensor-Werte für eine Investition basierend auf Typ.

    `emob_ctx` (Phase 2a): liegt die Heimladung kanonisch auf der Wallbox
    (evcc), ziehen die E-Auto-Sensoren PV-Anteil + Ersparnis km-anteilig aus dem
    Wallbox-Pool statt aus der leeren E-Auto-IMD. Ohne Kontext (Default) bleibt
    das Verhalten unverändert (eigene IMD-Werte).

    `fenster_ctx` (S3, 21.09.2026): der gemeinsame Eingang der Fenster-Sensoren
    (`services/ha_export_fenster.py::FensterKontext`), **einmal je Publish-Lauf**
    gebildet und hier nur benutzt. Ohne ihn entstehen die Plan-Sensoren P4/P7/P8/P9
    schlicht nicht — sie sind eine Zugabe, kein Bestandteil der bisherigen Antwort."""
    sensor_values = []

    # InvestitionMonatsdaten laden
    imd_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id == investition.id)
    )
    # #308: SoT-Filter auf die Laufzeit (Anschaffung→Stilllegung), symmetrisch
    # zur Schwesterfunktion `calculate_anlage_sensors` (#236). Ohne ihn flossen
    # IMD-Monate vor Anschaffung / nach Stilllegung in die per-Investition-
    # HA-Sensoren (km, Verbrauch, PV-Anteil, Ersparnis) ein.
    monatsdaten = [
        md for md in imd_result.scalars().all()
        if investition.ist_aktiv_im_monat(md.jahr, md.monat)
    ]

    def _emob_daten(md: InvestitionMonatsdaten) -> dict:
        """F-16: die Zeile mit abgeleitetem PV-Anteil aus dem Pool-Kontext.

        Bewusst **nicht** hier selbst abgeleitet: der Torwächter entscheidet
        über E-Auto und Wallbox eines Monats zusammen, diese Funktion sieht aber
        nur ein Gerät (s. ``_EmobPoolCtx.daten_by_key``). Ohne Kontext bleibt es
        beim Rohwert — dasselbe Verhalten wie vor F-16.
        """
        if emob_ctx is None:
            return md.verbrauch_daten or {}
        return emob_ctx.daten_by_key.get(
            (investition.id, md.jahr, md.monat), md.verbrauch_daten or {}
        )

    params = investition.parameter or {}
    netzbezug_preis = strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else 30.0

    # ROI-Basisdaten
    if investition.anschaffungskosten_gesamt:
        for sensor in INVESTITION_SENSOREN:
            if sensor.key == "investition_gesamt_euro":
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=investition.anschaffungskosten_gesamt,
                    berechnung=None,
                    zusatz_attribute=laufzeit_attribute(investition),
                ))

    # E-Auto / Wallbox Sensoren
    if investition.typ in ("e-auto", "wallbox"):
        gesamt_km = 0.0
        gesamt_verbrauch = 0.0
        gesamt_pv_ladung = 0.0
        gesamt_netz_ladung = 0.0

        for md in monatsdaten:
            d = _emob_daten(md)
            km_m = d.get("km_gefahren", 0) or 0
            gesamt_km += km_m
            gesamt_verbrauch += d.get("verbrauch_kwh", 0) or 0
            # Phase 2a: evcc-Setup → PV/Netz km-anteilig aus dem Wallbox-Pool.
            share = _emob_month_share(emob_ctx, investition.typ, km_m, md.jahr, md.monat)
            if share is not None:
                gesamt_pv_ladung += share.pv_kwh
                gesamt_netz_ladung += share.netz_kwh
            else:
                # #262: PV/Netz via SoT-Helper — bei Imports ohne expliziten
                # `ladung_netz_kwh`-Key wird aus `Total − PV` abgeleitet.
                pv, netz = get_emob_pv_netz_kwh(d)
                gesamt_pv_ladung += pv
                gesamt_netz_ladung += netz

        gesamt_ladung = gesamt_pv_ladung + gesamt_netz_ladung

        for sensor in E_AUTO_SENSOREN:
            value = None
            berechnung = None

            if sensor.key == "e_auto_km_gesamt":
                if gesamt_km > 0:
                    value = gesamt_km
                    berechnung = f"Summe aus {len(monatsdaten)} Monaten"
            elif sensor.key == "e_auto_verbrauch_kwh_100km":
                if gesamt_km > 0 and gesamt_verbrauch > 0:
                    value = gesamt_verbrauch / gesamt_km * 100
                    berechnung = f"{gesamt_verbrauch:.0f} / {gesamt_km:.0f} × 100"
            elif sensor.key == "e_auto_pv_anteil_prozent":
                if gesamt_ladung > 0:
                    value = gesamt_pv_ladung / gesamt_ladung * 100
                    berechnung = f"{gesamt_pv_ladung:.0f} / {gesamt_ladung:.0f} × 100"
            elif sensor.key == "e_auto_ersparnis_vs_benzin_euro":
                if gesamt_km > 0:
                    # Monatliche Kraftstoffpreise laden (Fallback: statischer Parameter)
                    fallback_benzinpreis = params.get(PARAM_E_AUTO["BENZINPREIS_EURO"], PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"])
                    vergleich_l = params.get(
                        PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"],
                        PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
                    )
                    anlage_md_result = await db.execute(
                        select(Monatsdaten).where(Monatsdaten.anlage_id == investition.anlage_id)
                    )
                    anlage_md_dict = {
                        (m.jahr, m.monat): m for m in anlage_md_result.scalars().all()
                    }
                    # N-181/F-18: sechste Kopie der Formel aufgelöst — die
                    # Rechnung kommt aus dem Layer-SoT, diese Schleife sammelt
                    # nur die Eingänge. Die Preisachse war hier die letzte, die
                    # noch den **heutigen** Tarif nahm (`netzbezug_preis`), und
                    # zwar den ALLGEMEINEN statt des Wallbox-Tarifs.
                    km_pro_monat_sensor: list[tuple[int, int, float]] = []
                    netz_pro_monat_sensor: list[tuple[int, int, float]] = []
                    netz_total_sensor = 0.0
                    fahrverbrauch_sensor = 0.0
                    monate_sensor: list[tuple[int, int]] = []
                    for md in monatsdaten:
                        d = _emob_daten(md)
                        km = d.get("km_gefahren", 0) or 0
                        # #262: SoT-Helper liefert (pv, netz) mit Fallback.
                        _, netz = get_emob_pv_netz_kwh(d)
                        # Phase 2a: evcc → Netz km-anteilig aus dem Wallbox-Pool.
                        share = _emob_month_share(emob_ctx, investition.typ, km, md.jahr, md.monat)
                        if share is not None:
                            netz = share.netz_kwh
                        monate_sensor.append((md.jahr, md.monat))
                        netz_total_sensor += netz
                        if netz > 0:
                            netz_pro_monat_sensor.append((md.jahr, md.monat, netz))
                        if km > 0:
                            km_pro_monat_sensor.append((md.jahr, md.monat, km))
                            fahrverbrauch_sensor += d.get("verbrauch_kwh", 0) or 0

                    preis_lookup_sensor = await monats_strompreis_lookup(
                        db, investition.anlage_id, "wallbox", monate_sensor,
                        fallback_bezug=netzbezug_preis,
                    )
                    erg = berechne_eauto_ersparnis_periode(
                        km_pro_monat=km_pro_monat_sensor,
                        ladung_netz_kwh_gesamt=netz_total_sensor,
                        # Wie beim Anlagen-Sensor: externe Ladekosten waren hier
                        # noch nie enthalten — beim Umhängen nicht stillschweigend
                        # dazunehmen.
                        ladung_extern_euro_gesamt=0.0,
                        wallbox_strompreis_cent=netzbezug_preis,
                        eauto_parameter=params,
                        monats_benzinpreis_lookup={
                            k: m.kraftstoffpreis_euro for k, m in anlage_md_dict.items()
                        },
                        fahrverbrauch_kwh_gesamt=fahrverbrauch_sensor or None,
                        monats_strompreis_lookup=preis_lookup_sensor,
                        netz_pro_monat=netz_pro_monat_sensor or None,
                    )
                    benzin_kosten = erg.benzin_kosten_euro
                    strom_kosten = erg.strom_kosten_euro
                    fossile_kosten = erg.fossile_kosten_euro

                    value = erg.ersparnis_euro
                    berechnung = (
                        f"{benzin_kosten:.2f} (Benzin) - {strom_kosten:.2f} (Strom"
                        f" @ {erg.verwendeter_strompreis_cent:.2f} ct/kWh)"
                        + (f" - {fossile_kosten:.2f} (Kraftstoff)" if fossile_kosten else "")
                    )

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung
                ))

    # Wärmepumpe Sensoren
    elif investition.typ == "waermepumpe":
        # DI-4: WP-Strom mit dem WP-Spezialtarif bewerten (Fallback allgemein),
        # deckungsgleich mit aktueller_monat.py und der Anlage-Aggregation oben.
        gesamt_strom = 0.0
        # N-391: die Wärme des Geräts nach der kanonischen Vorrangregel D1 —
        # **je Zeile aufgelöst**, nicht am Ende aus zwei Summen gebildet.
        # ⛔ Hier standen bis zum 14.09.2026 `gesamt_heizung` und
        # `gesamt_warmwasser`, deren einziger Zweck ihre Summe am Ende war. Eine
        # Zeile mit gemeinsamem Wärmemengenzähler trug zu beiden nichts bei —
        # die Wärme-, Arbeitszahl- und Ersparnis-Sensoren dieser Wärmepumpe
        # meldeten 0 bzw. nichts, während Hub und Cockpit die Zahl zeigten.
        gesamt_waerme_kanonisch = 0.0

        # #263 K-2 (Konzept §3.5): abgeleitete Wärme trägt keine JAZ — sonst
        # exportierte eedc die gepflegte JAZ als gemessenen Sensorwert nach HA,
        # wo sie in Automationen und Langzeitstatistik weiterlebt.
        waerme_abgeleitet = False
        # #263 K-2 (S4): Teilmengen nach Betriebsmodus — nie Summanden.
        gesamt_modus_heizen = 0.0
        gesamt_modus_kuehlen = 0.0
        gesamt_modus_warmwasser = 0.0
        #: ⭐ **SOLL-§9-E7/Option A: was vom Nenner abgezogen werden DARF.**
        #: ⛔ **Nicht die Summe der funktionsfremden Mengen** — hier stand bis
        #: zum 12.09.2026 `gesamt_modus_funktionsfremd`, das jede solche Menge
        #: aufaddierte. Bei getrennter Strommessung mit nur **abgeleiteter**
        #: Aufteilung ist der Abzug 0: Die Verteilung darf
        #: `strom_heizen + strom_warmwasser` nicht um eine Menge kürzen, die nie
        #: dazukam (W-16 addiert nur den **gemessenen** Anteil). Die Mengen
        #: selbst tragen unverändert die Betriebsart-Sensoren weiter unten (K1)
        #: — sie stehen in `gesamt_modus_kuehlen` und seinen Nachbarn.
        gesamt_modus_funktionsfremd_abzug = 0.0
        gesamt_modus_abdeckung_h = 0.0
        #: F-56 — trägt irgendeine Zeile GEMESSENE Betriebsart-Zähler? Dann
        #: dürfen die beiden Sensoren erscheinen, auch ohne Modus-Abdeckung:
        #: die Abdeckung ist die Zeitbasis des *abgeleiteten* Wegs und bleibt
        #: bei gemessenen Zählern zu Recht 0.
        gesamt_modus_gemessen = False
        #: F-52: Was der Abschluss schon festgeschrieben hat — und der gepflegte
        #: Gesamtwert je Monat. Beides braucht der Nachtrag unten, um
        #: „gespeichert schlägt gerechnet" und die Teilmengen-Invariante
        #: anwenden zu können. Entsteht in DIESEM Durchlauf, damit keine dritte
        #: Quelle für dieselben Werte aufgemacht wird.
        gespeichert_je_monat: dict[tuple[int, int], dict[str, tuple[bool, float]]] = {}
        # B5/X-1: der Kühlstrom je Monat — für E-B in der Ersparnis unten.
        kuehl_je_monat: dict[tuple[int, int], float] = {}
        # B5/X-1: der Kühlstrom je Monat — für E-B in der Ersparnis unten.
        kuehl_je_monat: dict[tuple[int, int], float] = {}
        #: ⛔ **N-462 (13.09.2026): je Monatszeile, nicht einmal vor der
        #: Schleife.** SOLL-§9-E7/Option A fragt „steckt der funktionsfremde
        #: Anteil im Nenner?" — das entscheidet die **Stufe** dieser Zeile (K3),
        #: nicht das Kennzeichen des Geräts. Der Nachtrag-Block weiter unten
        #: sieht seine Zeile nicht mehr und liest die Stufe deshalb hier mit.
        _nenner_fein_je_monat: dict[tuple[int, int], bool] = {}
        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            # F-56: **gemessen schlägt abgeleitet**, über den Layer-SoT —
            # nicht daneben nachgebaut. Genau dieser Nachbau (`d.get(
            # MODUS_STROM_FELD[…])` plus eine Abdeckungs-Prüfung ohne den
            # Gemessen-Zweig) ließ die beiden Sensoren stumm, während Cockpit
            # und Komponenten-Hub die Aufteilung schon zeigten.
            _zeile = modus_strom_zeile(d)
            kuehl_je_monat[(md.jahr, md.monat)] = _zeile.kuehlen_kwh
            gesamt_modus_heizen += _zeile.heizen_kwh
            gesamt_modus_kuehlen += _zeile.kuehlen_kwh
            gesamt_modus_warmwasser += _zeile.warmwasser_kwh
            # SOLL-§9-E7/Option A — die Regel wird gerufen, nicht nachgebaut.
            _nenner_fein_je_monat[(md.jahr, md.monat)] = nenner_ist_feine_summe(
                d, investition.parameter,
            )
            gesamt_modus_funktionsfremd_abzug += funktionsfremd_abzug_kwh(
                _zeile, hat_split=_nenner_fein_je_monat[(md.jahr, md.monat)],
            )
            gesamt_modus_abdeckung_h += _zeile.abdeckung_h
            gesamt_modus_gemessen = gesamt_modus_gemessen or _zeile.gemessen
            gesamt_strom += get_wp_strom_kwh(d, investition.parameter)
            gespeichert_je_monat[(md.jahr, md.monat)] = {
                str(investition.id): (
                    # ⚠ `hat_aufteilung`, nicht nur die Abdeckung: eine
                    # gemessene Zeile braucht den gerechneten Split nicht und
                    # darf ihn nicht zusätzlich bekommen (Doppelzählung).
                    # `monats_fakten/` wendet dieselbe Weiche an.
                    _zeile.hat_aufteilung,
                    get_wp_strom_kwh(d, investition.parameter),
                )
            }
            gesamt_waerme_kanonisch += waerme_gesamt_kwh(
                d.get("waerme_kwh"),
                heizwaerme_kwh(d),   # N-398
                # N-379: die eine Lesetuer — sonst traegt der HA-Sensor eine
                # Waermemenge, die es am Geraet nicht gibt.
                get_wp_warmwasser_kwh(d, investition.parameter),
            )
            waerme_abgeleitet = waerme_abgeleitet or heizwaerme_ist_abgeleitet(
                md.source_provenance
            )

        # F-52: Monate ohne Abschluss tragen ihren Split aus der Tagesebene
        # nach. **Ohne diesen Block blieben genau diese zwei Sensoren stumm**,
        # während Komponenten-Hub und Cockpit die Aufteilung schon zeigen —
        # zwei Zahlen für dieselbe Größe, die Klasse hinter #331 und F-15.
        # ⚠ Die Regeln stehen NICHT hier, sondern im gemeinsamen Lader; dieser
        # Pfad faltet je Investition und geht deshalb nicht über die
        # Monats-Fakten (bekannte P10-Restschuld von `ha_export.py`).
        nachgetragen = await lade_modus_split_ohne_abschluss(
            db, investition.anlage_id,
            inv_by_id={investition.id: investition},
            gespeichert=gespeichert_je_monat,
        )
        for _schluessel, _je_inv in nachgetragen.items():
            for _split in _je_inv.values():
                kuehl_je_monat[_schluessel] = (
                    kuehl_je_monat.get(_schluessel, 0.0) + _split.kuehlen_kwh
                )
                gesamt_modus_heizen += _split.heizen_kwh
                gesamt_modus_kuehlen += _split.kuehlen_kwh
                gesamt_modus_warmwasser += _split.warmwasser_kwh
                # ⚠ Hier zählt `kuehlen_kwh` und nicht die volle Definition —
                # `AngewandterSplit` hat sie nicht, und das ist richtig so: Der
                # **abgeleitete** Modus-Split kennt nur Heizen, Kühlen und
                # Warmwasser (er leitet aus dem Betriebsmodus ab, und
                # Lüften/Entfeuchten liefern dort keine eigene Menge).
                # ⭐ **SOLL-§9-E7/Option A, und hier ist der Zweig immer der
                # abgeleitete** — `lade_modus_split_ohne_abschluss` trägt genau
                # die Monate ohne gemessene Betriebsart-Zeile nach. Die Regel
                # wird gerufen, nicht nachgebaut (F-56); `ModusStromZeile` ist
                # bloß die Übergabeform.
                gesamt_modus_funktionsfremd_abzug += funktionsfremd_abzug_kwh(
                    ModusStromZeile(
                        heizen_kwh=_split.heizen_kwh,
                        kuehlen_kwh=_split.kuehlen_kwh,
                        warmwasser_kwh=_split.warmwasser_kwh,
                        gemessen=False,
                        abdeckung_h=_split.abdeckung_h,
                    ),
                    # N-462: die Stufe DIESES Monats. Trägt er gar keine
                    # Zeile, gibt es auch keinen Gesamtzähler, auf den er
                    # zurückfallen könnte — dann bleibt es bei der Lage des
                    # Kennzeichens, und die ist hier „feine Summe".
                    hat_split=_nenner_fein_je_monat.get(
                        _schluessel,
                        bool((investition.parameter or {})
                             .get("getrennte_strommessung")),
                    ),
                )
                gesamt_modus_abdeckung_h += _split.abdeckung_h

        # N-391: dieselbe Auflösung wie im Hub und in den Monats-Fakten. Ohne sie
        # meldeten die Sensoren *Wärme erzeugt*, *Arbeitszahl* und *Ersparnis*
        # einer Wärmepumpe mit gemeinsamem Wärmemengenzähler 0 bzw. nichts.
        gesamt_waerme = gesamt_waerme_kanonisch

        # Issue #238: Counter-Summen (Starts/Betriebsstunden) dieser WP aus
        # TagesZusammenfassung.komponenten_starts über die Laufzeit. Nur gesetzt,
        # wenn der jeweilige Zähler überhaupt Werte geliefert hat.
        from backend.models.tages_energie_profil import TagesZusammenfassung
        inv_id_str = str(investition.id)
        tz_res = await db.execute(
            select(TagesZusammenfassung.datum, TagesZusammenfassung.komponenten_starts)
            .where(TagesZusammenfassung.anlage_id == investition.anlage_id)
            .where(TagesZusammenfassung.komponenten_starts.is_not(None))
        )
        wp_starts_total = 0
        wp_stunden_total = 0.0
        hat_starts = hat_stunden = False
        for datum_, komp in tz_res.all():
            if not investition.ist_aktiv_im_monat(datum_.year, datum_.month):
                continue
            c = ((komp or {}).get("wp_starts_anzahl") or {}).get(inv_id_str)
            if isinstance(c, (int, float)) and c > 0:
                wp_starts_total += int(c)
                hat_starts = True
            h = ((komp or {}).get("wp_betriebsstunden") or {}).get(inv_id_str)
            if isinstance(h, (int, float)) and h > 0:
                wp_stunden_total += float(h)
                hat_stunden = True

        for sensor in WAERMEPUMPE_SENSOREN:
            value = None
            berechnung = None
            zusatz_attribute: dict = {}

            if sensor.key == "wp_cop_durchschnitt":
                # ADR-002/P12 (02.09.2026): Die Arbeitszahl entsteht im Layer,
                # nie hier. **Bis dahin stand an dieser Stelle
                # `gesamt_waerme / gesamt_strom`** — eine eigene Division, die
                # von allen R2-Sperren nur die abgeleitete Wärme kannte.
                #
                # ⛔ **Zwei Größen fehlten, und beide bewegen die Zahl:**
                # der funktionsfremde Strom (**W-14/E4** — Kühlen, Lüften,
                # Entfeuchten standen im Nenner, obwohl ihre Nutzenergie in
                # keinem Wärmemengenzähler landet) und die Anwender-Angabe
                # „Fremdanteil auf dem Zähler" (**W-7**, Heizstab/bivalent).
                # Der Hub rechnete beides seit dem 26.08. heraus; dieser Sensor
                # nicht — **dieselbe Anlage, zwei Aussagen**, und diese hier
                # verlässt eedc in fremde Dashboards und Automationen.
                #
                # ⚠ `bauarten_gemischt` und `geraete_ohne_waerme` gehören hier
                # **nicht** hinein und ihr Fehlen ist keine Lücke: Der Block
                # faltet **eine** Investition. Ein Gerät hat nur eine Bauart,
                # und meldet es keine Wärme, ist `gesamt_waerme` bereits 0.
                _az = arbeitszahl(
                    gesamt_waerme, gesamt_strom,
                    waerme_abgeleitet_kwh=1.0 if waerme_abgeleitet else 0.0,
                    # SOLL-§9-E7/Option A: der **Abzug**, nicht die Menge.
                    strom_funktionsfremd_kwh=gesamt_modus_funktionsfremd_abzug,
                    abgrenzung_verletzt=abgrenzungs_grund(
                        abgrenzung_stoerung=abgrenzung_stoerung(investition),
                    ),
                )
                if _az.wert is not None:
                    value = _az.wert
                    berechnung = (
                        f"{_az.zaehler_kwh:.0f} / {_az.nenner_kwh:.0f}"
                        if _az.zaehler_kwh is not None and _az.nenner_kwh is not None
                        else None
                    )
                elif _az.grund and (gesamt_strom > 0 or gesamt_waerme > 0):
                    # B5/X-3 (SOLL §3.3 S3, ADR-002/P12): eine GESPERRTE
                    # Kennzahl ist ein Sensor ohne Wert, der seinen Grund
                    # nennt — nicht ein Sensor, der fehlt. Fehlte er, bliebe
                    # in Home Assistant der letzte publizierte Wert stehen
                    # (retain, kein expire_after) und liefe stündlich in die
                    # Langzeitstatistik weiter. Nur wo die Eingänge da sind:
                    # ein Gerät ohne jede Messung (F1) bekommt weiterhin keinen
                    # Sensor — sonst entstünden Entitäten für nie erfasste
                    # Größen (#400, Knallfrosch-Klasse).
                    zusatz_attribute = {"grund": _az.grund}
            elif sensor.key == "wp_ersparnis_euro":
                # B5/X-1 (05.09.2026): dieselbe Rechnung wie Hub und Cockpit —
                # der Layer `berechne_wp_ersparnis`, je Monat mit dem Tarif
                # seines Stichtags (ADR-002/P8) und ohne den Kühlstrom im
                # Vergleich (Entscheid E-B, 18.08.).
                #
                # ⛔ **Bis hierher stand eine eigene Formel:** `alte Kosten −
                # Σ Strom × heutiger WP-Tarif`. Gemessen an denselben Sprossen
                # wie der Hub: F8 (Kühlstrom 300 kWh) 10 € statt 100 €; zwei
                # Tarife (Juli 30 ct, ab September 40 ct) 66,67 € statt
                # 166,67 € — der Juli wurde mit dem Septemberpreis bewertet.
                # Dritte Kopie der Ersparnis-Formel (SOLL §3.3 S1); die
                # Zusatzkosten der Altheizung, die hier schon standen, trägt
                # seit X-4 der Layer selbst.
                #
                # N-88/F2b bleibt: ohne ersetzte Heizung ist kein Monat
                # `bewertbar`, und der Sensor bleibt leer statt eine Ersparnis
                # zu behaupten.
                anlage_md_result = await db.execute(
                    select(Monatsdaten).where(Monatsdaten.anlage_id == investition.anlage_id)
                )
                anlage_md_dict = {
                    (m.jahr, m.monat): m for m in anlage_md_result.scalars().all()
                }
                alte_kosten = 0.0
                wp_kosten = 0.0
                kuehl_kosten = 0.0
                bewertbar = False
                for md in monatsdaten:
                    d = md.verbrauch_daten or {}
                    m_waerme = waerme_gesamt_kwh(   # N-391 (D1), N-379, N-398
                        d.get("waerme_kwh"),
                        heizwaerme_kwh(d),
                        get_wp_warmwasser_kwh(d, investition.parameter),
                    )
                    m_strom = get_wp_strom_kwh(d, investition.parameter)
                    if m_waerme <= 0 and m_strom <= 0:
                        continue
                    m_tarife = await lade_tarife_fuer_anlage(
                        db, investition.anlage_id, target_date=date(md.jahr, md.monat, 1)
                    )
                    m_preis = resolve_strompreis_for_komponente(
                        m_tarife, "waermepumpe", fallback=netzbezug_preis
                    )
                    amd = anlage_md_dict.get((md.jahr, md.monat))
                    m_erg = berechne_wp_ersparnis(
                        wp_waerme_kwh=m_waerme,
                        wp_strom_kwh=m_strom,
                        wp_strompreis_cent=m_preis,
                        wp_parameter=investition.parameter,
                        monats_gaspreis_cent=(
                            amd.gaspreis_cent_kwh if amd else None
                        ),
                        strom_kuehlen_kwh=kuehl_je_monat.get((md.jahr, md.monat), 0.0),
                    )
                    alte_kosten += m_erg.alte_heizung_kosten_euro
                    wp_kosten += m_erg.wp_kosten_euro
                    kuehl_kosten += m_erg.kuehl_kosten_euro
                    bewertbar = bewertbar or m_erg.bewertbar
                if bewertbar:
                    value = alte_kosten - (wp_kosten - kuehl_kosten)
                    berechnung = (
                        f"{alte_kosten:.2f} (alt) - {wp_kosten - kuehl_kosten:.2f} (WP)"
                    )
                    if kuehl_kosten > 0:
                        berechnung += (
                            f" · Kühlstrom {kuehl_kosten:.2f} € nicht im Vergleich"
                        )
                    # B5/X-2: der Vorbehalt aus dem Layer — dieselben Worte
                    # wie Hub (B3) und Cockpit (B4). Nur gesetzt, wenn es
                    # einen gibt; MQTT trägt ihn als Attribut, REST als
                    # `hinweis`.
                    _vorbehalt = ersparnis_vorbehalt(
                        waerme_abgeleitet=waerme_abgeleitet,
                        abgrenzung=abgrenzung_stoerung(investition),
                    )
                    if _vorbehalt:
                        zusatz_attribute = {"vorbehalt": _vorbehalt}
            elif sensor.key == "wp_strom_heizen_modus_kwh":  # noqa: E501
                # Ohne erfassten Modus bleibt der Sensor leer — er behauptete
                # sonst „0 kWh geheizt" für ein Gerät, das eedc nicht beobachtet
                # hat. In HA-Langzeitstatistik lebt so eine 0 weiter.
                if gesamt_modus_abdeckung_h > 0 or gesamt_modus_gemessen:
                    value = gesamt_modus_heizen
                    berechnung = f"{gesamt_modus_heizen:.1f} von {gesamt_strom:.1f} kWh gesamt"
            elif sensor.key == "wp_strom_kuehlen_modus_kwh":
                if gesamt_modus_abdeckung_h > 0 or gesamt_modus_gemessen:
                    value = gesamt_modus_kuehlen
                    berechnung = f"{gesamt_modus_kuehlen:.1f} von {gesamt_strom:.1f} kWh gesamt"
            elif sensor.key == "wp_strom_warmwasser_modus_kwh":
                # N-336 — dieselbe Leer-Regel wie bei den zwei Nachbarn: ohne
                # erfassten Modus fehlt der Sensor, statt 0 zu behaupten.
                if gesamt_modus_abdeckung_h > 0 or gesamt_modus_gemessen:
                    value = gesamt_modus_warmwasser
                    berechnung = (
                        f"{gesamt_modus_warmwasser:.1f} von {gesamt_strom:.1f} kWh gesamt"
                    )
            elif sensor.key == "wp_betriebsmodus":
                # #398: der EINZIGE Sensor dieser Liste, der KEINE Monatsgröße
                # ist, sondern ein Zustand. Er kommt deshalb auch nicht aus den
                # Monatsdaten, sondern aus `betriebsmodus_live` — und fehlt
                # ganz, wenn es keine Zuordnung gibt (kein „—", keine leere
                # Entität, die in HA für immer weiterlebt).
                _modus = (modus_map or {}).get(investition.id)
                if _modus:
                    value = BETRIEBSMODUS_LABEL[_modus]
                    berechnung = f"Kanon-Wert „{_modus}\" der zugeordneten climate-Quelle"
            elif sensor.key == "wp_kompressor_starts":
                if hat_starts:
                    value = wp_starts_total
                    berechnung = "Σ erfasste Kompressor-Starts"
            elif sensor.key == "wp_betriebsstunden":
                if hat_stunden:
                    value = wp_stunden_total
                    berechnung = "Σ erfasste Betriebsstunden"

            if value is not None or zusatz_attribute.get("grund"):
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung,
                    zusatz_attribute=zusatz_attribute,
                ))

        # ── S2/S3: Entscheidung und Plan dieser Wärmepumpe ──────────────────
        await _wp_steuerung_und_plan(
            db=db,
            investition=investition,
            sensor_values=sensor_values,
            fenster_ctx=fenster_ctx,
            modus_map=modus_map,
            monatsdaten=monatsdaten,
            kuehl_je_monat=kuehl_je_monat,
        )

    # ── S3/P9: Sonstige Verbraucher je Gerät ────────────────────────────────
    elif investition.typ == "sonstiges":
        await _sonstiges_sensoren(
            db=db,
            investition=investition,
            sensor_values=sensor_values,
            fenster_ctx=fenster_ctx,
        )

    return sensor_values


# =============================================================================
# S2/S3 — Entscheidung und Plan je Gerät (KONZEPT-EEDC-AT-HA §5, P4/P7/P8/P9)
# =============================================================================
#
# ⚠ **Die Achse entscheidet, nicht die Bauart** (ADR-002/P13, Wärme/Klima R1).
# Ob ein Gerät ein Warmwasser-, Heiz- oder Kühlfenster bekommt, hängt daran, ob
# diese Achse **gemessen oder gepflegt** ist — nie an `wp_art`. Das Wort kommt
# in diesem Abschnitt deshalb nicht vor.
#
# ⛔ **Kein Fenster wird hier gerechnet.** Die Formel steht im Layer
# (`core/berechnungen/fenster.py`), der gemeinsame Eingang im Dienst
# (`services/ha_export_fenster.py`). Hier steht nur, WELCHE Menge, WELCHE Dauer
# und WELCHE Frist für dieses Gerät gilt.

#: Wie lange ein Warmwasser-Fenster dauert. Eine Wärmepumpe lädt den
#: Warmwasserspeicher in ein bis zwei Stunden; zwei ist die Dauer, die auch
#: ohne exakte Kenntnis der Anlage nicht daneben liegt.
_WW_FENSTER_DAUER_H = 2

#: Über wie viele Monate der Ø-Tagesverbrauch gebildet wird. Drei Monate
#: glätten einen einzelnen Ausreißer-Monat und folgen trotzdem der Jahreszeit —
#: ein Jahresmittel täte das nicht (Warmwasser im August ist nicht Warmwasser
#: im Januar).
_MENGE_MONATE = 3


def _monatsschluessel(heute: date, zurueck: int) -> list[tuple[int, int]]:
    """Die letzten ``zurueck`` **abgeschlossenen** Monate, neueste zuerst."""
    out: list[tuple[int, int]] = []
    jahr, monat = heute.year, heute.month
    for _ in range(zurueck):
        monat -= 1
        if monat == 0:
            jahr, monat = jahr - 1, 12
        out.append((jahr, monat))
    return out


def _tage_im_monat(jahr: int, monat: int) -> int:
    import calendar
    return calendar.monthrange(jahr, monat)[1]


async def _wp_steuerung_und_plan(
    *, db, investition, sensor_values, fenster_ctx, modus_map,
    monatsdaten, kuehl_je_monat: dict,
):
    """E2 (Warmwasserbetrieb) sowie P4 · P7 · P8 dieser Wärmepumpe.

    ⚠ **Die Faltung über `monatsdaten` (P4, unten) ist ein per-Investition-Aggregat;
    die Zeilen kommen aus `calculate_investition_sensors`, dem in
    `P10_PER_INVESTITION` gelisteten Lader.** Seit N-542 (22.09.2026) sieht der
    P10-Wächter auch diese Bauform: `test_wurzelmuster_konformitaet.py::_p10_imd_falter`
    findet Funktionen, die `verbrauch_daten`/`imd_typ_beitrag`/`modus_strom_zeile`
    über einen Parameter falten, und diese Funktion steht dort in
    `P10_PER_INVESTITION_PHASE` mit ihrem Lader. Wer die Funktion umbenennt oder
    aus der Liste nimmt, macht den Wächter rot; dass die Zeilen tatsächlich vom
    genannten Lader kommen, prüft er nicht (gemessen 22.09.2026) — das belegt der
    Aufruf in `calculate_investition_sensors`, nicht der Test. (Hier stand bis
    N-542: „der Wächter sieht diese Funktion nicht (kein `select`)" — das war die
    Blindstelle.)

    ⛔ **Warum überhaupt je Investition und nicht über `lade_monats_fakten`:**
    `WpFakten.strom_warmwasser_kwh` ist eine **anlagenweite** Summe über alle
    Wärmepumpen — bei zwei Geräten wäre die Menge des einen die Summe beider.
    Gelesen wird deshalb über `imd_typ_beitrag`, denselben Layer-SoT, den die
    Monats-Fakten selbst benutzen; ein eigener Griff ins `verbrauch_daten` wäre
    der Nachbau, an dem F-56 entstanden ist.
    """
    from backend.core.betriebsmodus import WARMWASSER
    from backend.services.ha_export_fenster import SLOTS_JE_TAG, fenster_fuer_menge
    from backend.services.ha_sensors_export import WAERMEPUMPE_SENSOREN

    def _def(key):
        for d in WAERMEPUMPE_SENSOREN:
            if d.key == key:
                return d
        raise KeyError(key)

    def _an(key, wert, zusatz=None, berechnung=None):
        if wert is None:
            return
        sensor_values.append(SensorValue(
            definition=_def(key), value=wert, berechnung=berechnung,
            zusatz_attribute={k: v for k, v in (zusatz or {}).items() if v is not None},
        ))

    # ── E2 · Warmwasserbetrieb ──────────────────────────────────────────────
    #
    # ⚠ Dieselbe Quelle wie `wp_betriebsmodus` (#398, `betriebsmodus_live`) —
    # und dieselbe Leer-Regel: ohne Zuordnung gibt es den Sensor nicht, statt
    # einer Entität, die in HA für immer „aus" zeigt.
    _modus = (modus_map or {}).get(investition.id)
    if _modus:
        _an("wp_warmwasserbetrieb", _modus == WARMWASSER,
            {"modus": BETRIEBSMODUS_LABEL[_modus]})

    if fenster_ctx is None:
        return

    heute = fenster_ctx.heute

    # ── P4 · Warmwasser-Fenster ─────────────────────────────────────────────
    #
    # **Menge:** der Ø-Warmwasserstrom je Tag der letzten drei abgeschlossenen
    # Monate.
    #
    # ⭐ **F-56 „gemessen schlägt abgeleitet", und zwar über den Layer-SoT.**
    # Es gibt zwei Wege zu dieser Größe, und sie sind nicht dasselbe:
    #   * **gemessen** — `strom_warmwasser_kwh` der getrennten Strommessung
    #     (ein eigener Zähler am Warmwasserbetrieb);
    #   * **abgeleitet** — `modus_strom_warmwasser_kwh`, aus dem
    #     mitgeschriebenen Betriebsmodus gerechnet.
    # `imd_typ_beitrag` liest beide je Zeile (`wp_strom_warmwasser` +
    # `..._gemessen`) — dieselbe Tür, die die Monats-Fakten benutzen. Ein
    # eigener Griff ins `verbrauch_daten` wäre genau der Nachbau, an dem F-56
    # entstanden ist. `herkunft` sagt dem Anwender, welcher Weg es war; bis zum
    # 21.09.2026 behauptete die Hilfe „ohne Warmwasser-Zähler kein Fenster",
    # und das stimmte schon damals nicht.
    letzte = _monatsschluessel(heute, _MENGE_MONATE)
    menge_gemessen = 0.0
    menge_abgeleitet = 0.0
    tage = 0
    ist_gemessen = False
    for md in monatsdaten:
        if (md.jahr, md.monat) not in letzte:
            continue
        beitrag = imd_typ_beitrag(investition, md.verbrauch_daten or {})
        menge_gemessen += beitrag.wp_strom_warmwasser
        ist_gemessen = ist_gemessen or beitrag.wp_strom_warmwasser_gemessen
        menge_abgeleitet += modus_strom_zeile(md.verbrauch_daten or {}).warmwasser_kwh
        tage += _tage_im_monat(md.jahr, md.monat)

    menge = menge_gemessen if (ist_gemessen and menge_gemessen > 0) else menge_abgeleitet
    herkunft = "gemessen" if (ist_gemessen and menge_gemessen > 0) else "abgeleitet"
    je_tag = (menge / tage) if tage else None
    if je_tag and je_tag > 0:
        f = fenster_fuer_menge(
            fenster_ctx, je_tag, dauer_h=_WW_FENSTER_DAUER_H,
            # N-544: „heute" endet backward mit Slot `SLOTS_JE_TAG` (= 24 =
            # 23–24 Uhr), nicht mit 23 (= 22–23 Uhr). Der Deckel 23 haette die
            # letzte Stunde des Tages ausgeschlossen, in der ein
            # Warmwasser-Fenster durchaus liegen kann.
            frist_slot=min(
                SLOTS_JE_TAG,
                fenster_ctx.frist_slot if fenster_ctx.frist_slot is not None else SLOTS_JE_TAG,
            ),
        )
        if f is not None:
            _an("wp_warmwasser_fenster_ab", fenster_ctx.slot_iso(f.ab), {
                **fenster_ctx.fenster_attribute(f),
                "menge_kwh": round(je_tag, 1),
                "herkunft": herkunft,
                "kosten_cent": round(f.kosten_cent_kwh * je_tag),
                "ersparnis_cent_vs_jetzt": (
                    None if f.delta_vs_jetzt is None
                    else round(-f.delta_vs_jetzt * je_tag)
                ),
                "preisquelle": fenster_ctx.preisquelle,
            }, berechnung=(
                f"Ø {je_tag:.1f} kWh Warmwasserstrom je Tag aus {tage} Tagen "
                f"({'gemessen' if herkunft == 'gemessen' else 'aus dem Betriebsmodus abgeleitet'})"
            ))

    # ── P7 · Heizfenster ────────────────────────────────────────────────────
    #
    # **Menge:** das **erwartete** WP-Stundenprofil von heute (Modell A mit
    # Heizgradtag-Korrektur), nicht eine Monatssumme — verschoben wird ein
    # Tagesgang, keine Jahresmenge. Ohne individuelles Profil (N-332) gibt es
    # die Reihe nicht und damit auch dieses Fenster nicht.
    wp_reihe = fenster_ctx.wp_stundenprofil_kwh
    if wp_reihe and any(v > 0 for v in wp_reihe):
        heizstunden = [i for i, v in enumerate(wp_reihe) if v > 0 and i >= fenster_ctx.jetzt_slot]
        verteilung = verteile_auf_guenstigste(fenster_ctx.kosten, wp_reihe, heizstunden)
        if verteilung is not None and verteilung.stunden:
            _an("wp_heizfenster_stunden", len(verteilung.stunden), {
                "heizstrom_stundenprofil_kwh": [round(v, 2) for v in wp_reihe],
                # N-544: Beginn-Angabe — Slot `h` beginnt `(h-1):00`. Bis
                # 22.09.2026 stand hier `h % 24`, also das ENDE: eine Automation
                # heizte eine Stunde zu spat.
                "guenstige_heizstunden": [
                    f"{(h - 1) % 24:02d}:00" for h in verteilung.stunden
                ],
                "ersparnis_cent_vs_profil": round(verteilung.ersparnis_cent),
                "heizzeit_stunden": len(heizstunden),
                "preisquelle": fenster_ctx.preisquelle,
                **fenster_ctx.profil_attribute,
            }, berechnung=(
                f"{len(verteilung.stunden)} von {len(heizstunden)} Stunden der "
                f"erwarteten Heizzeit — Verschiebung der gleichen Menge in die "
                f"günstigsten davon"
            ))

    # ── P8 · Kühlfenster ────────────────────────────────────────────────────
    #
    # ⛔ **Zwei Kriterien, beide nötig** (Wärme/Klima R1/E6):
    #   1. die Kühl-Achse liegt **am Zähler** — `hat_kuehl_zaehler`, derselbe
    #      SoT, den der Daten-Checker befragt. Eine Kältemenge oder eine
    #      zugeordnete Kühl-Leistung sind kein kWh-Zähler und lösen den Fall
    #      nicht auf.
    #   2. es gibt eine **gemessene Kühlstrom-Menge** in den letzten drei
    #      abgeschlossenen Monaten — das ist die Antwort auf „wie viel?" der
    #      Aufnahmeregel (Konzept §5).
    #
    # ⛔ **Hier stand im Bauplan `leistung_kuehlen_w` als Mengen-Quelle. Das
    # geht nicht, und zwar am Code gemessen (21.09.2026):** `leistung_kuehlen_w`
    # ist ein **Live-Feld** (`field_definitions/registry.py:885`, Einheit W,
    # ausdrücklich „reine Anzeige … die Mengen kommen aus dem kWh-Zähler") und
    # steht als **Entity-Zuordnung** im `sensor_mapping`, nicht als Zahl im
    # `parameter`-JSON (`PARAM_WAERMEPUMPE` kennt keinen solchen Schlüssel).
    # Aus einer Entity-ID lässt sich keine Menge bilden. Die gemessene
    # Kühlstrom-Menge kann es — und sie stammt aus derselben Auflösung, die die
    # Modus-Sensoren oben schon gefahren haben. *Ob das Live-Feld zugeordnet
    # ist, reist trotzdem als Attribut mit: F6 (S4) soll dem Anwender sagen
    # können, was ihm zum vollen Bild noch fehlt.*
    if kuehl_je_monat and hat_kuehl_zaehler(
        investition.id,
        imd_zeilen=monatsdaten,
        mapping=_mapping_der_anlage(investition),
        quellen=_quellen_der_anlage(investition),
    ):
        letzte = _monatsschluessel(heute, _MENGE_MONATE)
        menge = sum(v for k, v in kuehl_je_monat.items() if k in letzte)
        tage = sum(_tage_im_monat(*k) for k in kuehl_je_monat if k in letzte)
        je_tag = (menge / tage) if tage else 0.0
        temperaturen = [
            # N-544: die Temperaturreihe deckt HEUTE — backward sind das die
            # Slots 0…24 (Slot 24 = 23–24 Uhr). Der Schnitt bei 24 haette die
            # letzte Stunde des Tages uebersprungen; Modell A liefert sie zwar
            # ohnehin nicht (die 24er-Reihe endet bei Slot 23), der Schnitt sagt
            # aber jetzt dasselbe wie der Rest der Achse.
            (i, t) for i, t in enumerate(fenster_ctx.temperatur_c[:SLOTS_JE_TAG + 1])
            if t is not None
        ]
        spitze = max(temperaturen, key=lambda x: x[1])[0] if temperaturen else None
        # ⭐ **N-544: `spitze` ist ein Slot, kein Zeitpunkt.** Die Temperaturreihe
        # liegt backward auf derselben Achse wie alles andere: Slot `i` deckt
        # `[i-1, i)` und ENDET um `i:00`. Vorkuehlen heisst „bis zur Spitze
        # fertig sein" — die Frist ist also `spitze` selbst (inklusiv, das
        # Fenster darf im Slot davor enden), nicht `spitze - 1`. Und die Spitze
        # zaehlt noch, wenn sie in der laufenden Stunde liegt: `>=` statt `>`.
        # Auf der frueheren forward-Achse war `spitze - 1` / `>` dasselbe.
        if je_tag > 0 and spitze is not None and spitze >= fenster_ctx.jetzt_slot:
            f = fenster_fuer_menge(
                fenster_ctx, je_tag, dauer_h=2, frist_slot=spitze,
            )
            if f is not None:
                im_fenster = sum(fenster_ctx.ueberschuss_kwh[f.ab:f.bis])
                _an("wp_kuehlfenster_ab", fenster_ctx.slot_iso(f.ab), {
                    **fenster_ctx.fenster_attribute(f),
                    # Die Forecast-Temperatur ist ein MOMENTANWERT um `i:00`
                    # (nicht ein Stundenmittel) — die Angabe bleibt damit
                    # unveraendert `spitze:00` und ist eine Zeitpunkt-Angabe,
                    # keine Slot-Beschriftung.
                    "temperatur_max_um": f"{spitze % 24:02d}:00",
                    "temperatur_max_c": round(max(t for _i, t in temperaturen), 1),
                    "ueberschuss_kwh_im_fenster": round(im_fenster, 2),
                    "menge_kwh": round(je_tag, 1),
                    "leistung_kuehlen_zugeordnet": bool(
                        (_mapping_der_anlage(investition)
                         .get(str(investition.id), {}) or {})
                        .get("live", {}).get("leistung_kuehlen_w")
                    ),
                    "preisquelle": fenster_ctx.preisquelle,
                }, berechnung=(
                    f"Ø {je_tag:.1f} kWh gemessener Kühlstrom je Tag — günstigstes "
                    f"2-Stunden-Fenster vor der Tageshöchsttemperatur um {spitze:02d}:00"
                ))


def _mapping_der_anlage(investition) -> dict:
    """`sensor_mapping["investitionen"]` der Anlage — ohne Nachladen.

    ⚠ Die Beziehung ist in diesem Pfad geladen (die Aufrufer holen die Anlage
    ohnehin); ist sie es nicht, bleibt das Mapping leer und `hat_kuehl_zaehler`
    entscheidet allein über die gepflegten Monatszeilen. Das ist die
    vorsichtige Richtung: im Zweifel **kein** Sensor.
    """
    anlage = getattr(investition, "anlage", None)
    return ((getattr(anlage, "sensor_mapping", None) or {}).get("investitionen") or {})


def _quellen_der_anlage(investition) -> dict:
    anlage = getattr(investition, "anlage", None)
    return ((getattr(anlage, "sensor_mapping", None) or {}).get("quellen") or {})


async def _sonstiges_sensoren(*, db, investition, sensor_values, fenster_ctx):
    """P9 — Monatsverbrauch und bestes Fenster eines sonstigen Verbrauchers.

    ⭐ **Das ist auch Stufe 1.** Bis zum 21.09.2026 exportierte eedc für ein
    Gerät der Kategorie *Sonstiges/Verbraucher* (Pool, Sauna, Trockner,
    Heizstab mit eigenem Zähler = Fall H-A) **keinen einzigen Energiewert** —
    je Gerät gab es höchstens `investition_gesamt_euro`. Erst der Gerätesensor,
    dann das Fenster.

    ⛔ **Die Mengen kommen aus den Monats-Fakten** (ADR-002/P10): `SonstigesFakten`
    trägt seit C1d `je_geraet` mit genau diesen drei Größen, inklusive
    Laufzeit-Filter. Eine eigene Faltung über `InvestitionMonatsdaten` wäre die
    Klasse hinter der Drift-Inventur vom 31.07.2026.
    """
    from backend.services.ha_export_fenster import fenster_fuer_menge
    from backend.services.monats_fakten import lade_monats_fakten
    from backend.services.ha_sensors_export import SONSTIGES_SENSOREN

    if (investition.parameter or {}).get("kategorie") != "verbraucher":
        return

    def _def(key):
        for d in SONSTIGES_SENSOREN:
            if d.key == key:
                return d
        raise KeyError(key)

    def _an(key, wert, zusatz=None, berechnung=None):
        if wert is None:
            return
        sensor_values.append(SensorValue(
            definition=_def(key), value=wert, berechnung=berechnung,
            zusatz_attribute={k: v for k, v in (zusatz or {}).items() if v is not None},
        ))

    heute = fenster_ctx.heute if fenster_ctx is not None else date.today()
    monate = _monatsschluessel(heute, _MENGE_MONATE)
    von = min(monate)
    fakten = await lade_monats_fakten(
        db, investition.anlage_id, von=von, bis=(heute.year, heute.month)
    )
    if not fakten:
        return

    laufend = next(
        (f for f in fakten if (f.jahr, f.monat) == (heute.year, heute.month)), None
    )
    geraet = (
        (laufend.sonstiges.je_geraet or {}).get(investition.id) if laufend else None
    )
    if geraet is not None and geraet.verbrauch_kwh > 0:
        pv_anteil = (
            round(geraet.bezug_pv_kwh / geraet.verbrauch_kwh * 100, 1)
            if geraet.verbrauch_kwh > 0 else None
        )
        _an("sonstiges_verbrauch_monat_kwh", round(geraet.verbrauch_kwh, 1), {
            "pv_anteil_prozent": pv_anteil,
            "bezug_pv_kwh": round(geraet.bezug_pv_kwh, 1),
            "bezug_netz_kwh": round(geraet.bezug_netz_kwh, 1),
        }, berechnung=f"Stromverbrauch im laufenden Monat ({heute.month}/{heute.year})")

    if fenster_ctx is None:
        return

    # Ø-Tagesverbrauch aus den abgeschlossenen Monaten — der laufende Monat
    # ist unvollständig und würde die Menge systematisch zu klein machen.
    menge, tage = 0.0, 0
    for f in fakten:
        if (f.jahr, f.monat) not in monate:
            continue
        g = (f.sonstiges.je_geraet or {}).get(investition.id)
        if g is None:
            continue
        menge += g.verbrauch_kwh
        tage += _tage_im_monat(f.jahr, f.monat)
    je_tag = (menge / tage) if tage else None
    if not je_tag or je_tag <= 0:
        return

    fenster = fenster_fuer_menge(fenster_ctx, je_tag, dauer_h=2)
    if fenster is None:
        return
    _an("sonstiges_fenster_ab", fenster_ctx.slot_iso(fenster.ab), {
        **fenster_ctx.fenster_attribute(fenster),
        "menge_kwh": round(je_tag, 1),
        "ersparnis_cent_vs_jetzt": (
            None if fenster.delta_vs_jetzt is None
            else round(-fenster.delta_vs_jetzt * je_tag)
        ),
        "preisquelle": fenster_ctx.preisquelle,
        **fenster_ctx.profil_attribute,
    }, berechnung=(
        f"Ø {je_tag:.1f} kWh je Tag aus {tage} Tagen — günstigstes 2-Stunden-Fenster"
    ))
