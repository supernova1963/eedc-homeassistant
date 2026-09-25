"""Komponenten von *Cockpit → Monat*: der Komponenten-Detailblock aus den Monats-Fakten (ADR-002/P10, C1d) und die
Geraetesicht mit der Tabelle je Geraet und dem einen Kasten (D-Sicht).
"""
# Vorlage 2 des Refactorings grosser Dateien (18.09.2026): Abschnitte des Endpunkts
# `get_aktueller_monat` byte-identisch als Funktionen, Schnittstelle als Schluesselwort-
# Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel — Gate ist
# `plans/skript-golden-master-aktueller-monat.py` (alte gegen neue Antworten, bitgleich).
import logging
from datetime import date
from typing import Optional
from backend.services.waerme_klima_block import achsen_der_anlage, geraete_zeilen, was_noch_moeglich
from backend.core.berechnungen.waermepumpe_kennzahl import (
    als_arbeitszahl,
    arbeitszahl_je_funktion,
    arbeitszahl_kuehlen,
)
from backend.core.berechnungen import (
    sonstiges_richtung,
    auslastung_prozent,
    auslastungs_basis_kwh,
    berechne_netzladung_kosten,
    speicher_wirkungsgrad as berechne_speicher_wirkungsgrad,
    vollzyklen as berechne_vollzyklen,
)
from backend.core.investition_kennwerte import get_speicher_kapazitaet_kwh
from backend.api.routes.aktueller_monat.schemas import SonstigesGeraet

logger = logging.getLogger(__name__)


async def komponenten_detail(*, _wp_abgrenzung_je_funktion, _wp_funktion, _wp_kennzahlen_je_geraet, anlage_id, db, fenster, investitionen, jahr, monat, monats_fakt, speicher_entladung, speicher_ladung, wp_abgrenzung_verletzt, wp_arbeitszahl, wp_waerme_abgeleitet_kwh):
    """Komponenten-Detail aus den Monats-Fakten (ADR-002/P10, C1d): Speicher, Waermepumpe je Modus, BKW, E-Mob, Sonstiges.

    Aus `get_aktueller_monat` Zeilen 834-1150 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── Komponenten-Detail aus den Monats-Fakten (ADR-002/P10, C1d) ──
    # Bis C1d lief hier eine eigene `InvestitionMonatsdaten`-Batch mit fünf
    # anlagenweiten Faltungen daneben — die letzte des Baums. Sie hatte zwei
    # Fehler, die die Schicht nicht hat:
    #
    #   * **E-Auto und Wallbox wurden roh addiert.** Beide messen denselben
    #     Fluss aus zwei Perspektiven; wo beide gepflegt sind, stand die
    #     Netzladung doppelt in der Kachel, im T-Konto (× Arbeitspreis!) und in
    #     der Jahressumme. Die Schicht poolt kanonisch (#262).
    #   * **Kein Laufzeit-Filter.** Die Batch nahm jede IMD-Zeile des Typs,
    #     auch aus Monaten vor der Anschaffung (#236-Klasse).
    #
    # `monats_fakt` ist oben schon geladen (derselbe Monat) — hier wird nichts
    # nachgeladen. Die Präzedenz der vier Quellen bleibt davon unberührt: der
    # Detailblock war immer schon reiner DB-Zweig.
    mf_speicher = monats_fakt.speicher if monats_fakt else None
    mf_wp = monats_fakt.wp if monats_fakt else None
    mf_emob = monats_fakt.emob if monats_fakt else None
    mf_bkw = monats_fakt.bkw if monats_fakt else None
    mf_sonstiges = monats_fakt.sonstiges if monats_fakt else None
    #: Welche Typen im Monat eine SICHTBARE Zeile hatten — trennt „0 gemessen"
    #: von „gar keine Daten" (P4). Vorher leistete das die Frage, ob die
    #: IMD-Batch für den Typ etwas hergab.
    typen_mit_zeile = monats_fakt.meta.typen_mit_zeile if monats_fakt else frozenset()

    # Speicher: Kapazität, Arbitrage-Ladung, Wirkungsgrad, Vollzyklen, Auslastung
    speicher_ladung_netz = None
    speicher_wirkungsgrad = None
    speicher_vollzyklen = None
    speicher_kapazitaet = None
    speicher_auslastungs_basis = None
    speicher_auslastung = None
    speicher_ersparnis = None

    # F-24: nur die Speicher, die es in DIESEM Monat gab. `investitionen` ist
    # oben nur über den `aktiv`-Haken gefiltert — ein ersetztes Gerät trägt
    # aber ein **Stilllegungsdatum** und bleibt `aktiv` (sonst verschwände es
    # auch aus der Historie). Ohne diesen Filter summierte die Kachel unten
    # altes **und** neues Gerät: an einer Kopie des Dev-Bestands 15,4 + 30,8 =
    # 46,2 statt 30,8 kWh, und damit auch Vollzyklen und Auslastung daneben.
    speicher_invs = [
        i for i in investitionen
        if i.typ == "speicher" and i.ist_aktiv_im_monat(jahr, monat)
    ]
    speicher_soc_drift_flag = False
    # F-22: worauf der ausgewiesene η beruht — `soc_korrigiert` · `fenster_lang`
    # · `fenster-zu-kurz` · `keine-ladung` · `nicht-ermittelbar`. Trägt den
    # Grund, wenn kein Wert dasteht (P4: unvollständige Antworten sagen es).
    speicher_wirkungsgrad_quelle = None
    speicher_eff_ladepreis = None
    speicher_eff_ladepreis_quelle = None
    speicher_imd_ladepreis = None
    if speicher_invs:
        # Kapazität aus parameter — BRUTTO, das ist die Zyklen-Konvention des
        # ganzen Baums (docs/BERECHNUNGEN.md §Speicher). Eine hier früher
        # zusätzlich gebildete Netto-Summe (`nutzbare_kapazitaet_kwh` mit
        # Brutto-Fallback) wurde nirgends gelesen — sie suggerierte eine
        # zweite Basis, die es an dieser Stelle nicht gibt (R22-4).
        kap_sum = sum(get_speicher_kapazitaet_kwh(i) or 0 for i in speicher_invs)
        if kap_sum > 0:
            speicher_kapazitaet = round(kap_sum, 1)

        # Arbitrage-Ladung + kWh-gewichteter Ø der erfassten Ladepreise als
        # Preis-Fallback für die Netzladung-Kosten-Kachel (R15-1) — beides aus
        # der Schicht (Kanon-Key + Legacy-Fallback stecken in `imd_typ_beitrag`).
        #
        # Sobald Speicher-Monatsdaten existieren, ist auch 0 kWh ein Ergebnis
        # („nichts aus dem Netz geladen", Rainer-PN 2026-07-25). Nur ganz ohne
        # Zeile bleibt es None = „keine Daten" und die Kachel aus.
        if mf_speicher is not None and "speicher" in typen_mit_zeile:
            speicher_ladung_netz = round(mf_speicher.netzladung_kwh, 2)
        speicher_imd_ladepreis = (
            mf_speicher.netzladung_preis_cent if mf_speicher is not None else None
        )

        # Wirkungsgrad und Vollzyklen
        sl = speicher_ladung or 0
        se = speicher_entladung or 0

        # F-22 (Rainer-PN 2026-08-08, seine ZWEITE Meldung nach 2026-05-22):
        # Der Monats-η läuft über den SoT-Kanon, der die SoC-Drift
        # HERAUSRECHNET, statt sie nur zu erkennen und den Wert zu verwerfen.
        #
        # Was hier bis v4.0.11 stand, war ein Alles-oder-Nichts-Schalter auf
        # |ΔSoC| > 20 pp — und der lag in drei Richtungen falsch (gemessen an
        # der Demo-Anlage, 27 Monate):
        #   * über der Schwelle wurde ausgeblendet, obwohl ein guter Wert
        #     ermittelbar war (2025-11: „—" statt 81,6 %),
        #   * unter der Schwelle stand der ROHE Quotient (2025-10: 83,1 statt
        #     korrekt 82,4 %) — korrigiert wurde also NIE,
        #   * fehlten die SoC-Randwerte, blieb das Flag False und der Wert ging
        #     ungeprüft raus — genau der Pfad zu den >100 %, die Rainer meldete.
        #
        # `berechne_ist_wirkungsgrad` löst alle drei: es rechnet ΔSoC heraus
        # (Energieerhaltung), klemmt auf physikalisch mögliche 100 % und sagt
        # über `quelle`, worauf das Ergebnis beruht. Ausgeblendet wird nur noch,
        # was wirklich nicht ermittelbar ist — und dann MIT Grund (P4).
        if sl > 0 and se > 0:
            from calendar import monthrange
            from backend.core.investition_kennwerte import (
                get_speicher_nutzbare_kapazitaet_kwh,
            )
            from backend.services.speicher_wirtschaftlichkeit import (
                berechne_ist_wirkungsgrad,
            )
            try:
                monat_start = date(jahr, monat, 1)
                monat_ende = date(jahr, monat, monthrange(jahr, monat)[1])
                nutzbar = sum(
                    get_speicher_nutzbare_kapazitaet_kwh(i) or 0 for i in speicher_invs
                )
                _eta = await berechne_ist_wirkungsgrad(
                    db,
                    anlage_id=anlage_id,
                    von=monat_start,
                    bis=monat_ende,
                    ladung_kwh=sl,
                    entladung_kwh=se,
                    nutzbare_kapazitaet_kwh=float(nutzbar),
                    # Ein Kalendermonat — nie das lange Fenster, immer der
                    # SoC-korrigierte Pfad, sofern Randwerte vorliegen.
                    fenster_monate=1,
                )
                speicher_wirkungsgrad_quelle = _eta.quelle
                if _eta.wirkungsgrad_prozent is not None:
                    speicher_wirkungsgrad = round(_eta.wirkungsgrad_prozent, 1)
                else:
                    # Kein SoC am Periodenrand (kein SoC-Sensor, frisch
                    # installiert, Lücke in den Tagesprofilen). Hier NICHT
                    # schweigen: der rohe Quotient ist unkorrigiert, aber
                    # solange er physikalisch möglich ist, ist er eine Aussage —
                    # und für die meisten Anlagen die einzige, die es gibt.
                    # P4 heißt „sagen, was man weiß und wie sicher", nicht
                    # „lieber gar nichts". Ausgeblendet wird nur, was
                    # NACHWEISLICH falsch ist: über 100 % kann kein Speicher.
                    #
                    # Diese drei Zeilen waren bis zum 17.08.2026 eine wörtliche
                    # Zweitschrift des unkorrigierten SoT-Zweigs — gefunden vom
                    # Deckungs-Prüfer zu N-252, nicht vom Abwesenheits-Grep:
                    # *Cockpit → Monat* galt als „gedeckt", weil es den
                    # SoC-Pfad benutzt, und trug die Regel daneben trotzdem
                    # ein zweites Mal.
                    _roh_eta = berechne_speicher_wirkungsgrad(sl, se, None)
                    if _roh_eta.prozent is not None:
                        speicher_wirkungsgrad = round(_roh_eta.prozent, 1)
                        speicher_wirkungsgrad_quelle = _roh_eta.quelle
                # Rückwärtskompatibel: das alte Flag bleibt im Vertrag, trägt
                # jetzt aber die ehrliche Aussage „kein belastbarer η" statt
                # „SoC ist gedriftet". Clients, die es lesen, blenden weiterhin
                # korrekt aus — nur eben in den richtigen Fällen.
                speicher_soc_drift_flag = speicher_wirkungsgrad is None
            except Exception as e:  # noqa: BLE001
                # Der η darf den Endpoint nicht killen. Bei Fehler KEIN roher
                # Fallback-Quotient — das war der Pfad zu den >100 %.
                speicher_wirkungsgrad_quelle = "nicht-ermittelbar"
                speicher_soc_drift_flag = True
                logger.warning(
                    "aktueller_monat: η-Ermittlung fehlgeschlagen "
                    "(anlage=%s, %s/%s): %s", anlage_id, jahr, monat, e,
                )
        # Vollzyklen = ENTLADUNG ÷ Kapazität über den Layer-SoT (Kanon seit
        # 2026-07-28; vorher stand hier die Ladung `sl`).
        _vz = berechne_vollzyklen(se, speicher_kapazitaet)
        if _vz is not None:
            speicher_vollzyklen = round(_vz, 2)

        # #358 Phase 1: Auslastung = Entladung ÷ (Kapazität × Tage).
        #
        # Im LAUFENDEN Monat zählen nur die abgelaufenen Tage. Sonst stünde am
        # 3. eines Monats eine Auslastung von 10 %, die nichts über den Speicher
        # sagt, sondern über das Datum — ein Quotient aus einem vollen Nenner und
        # einem angefangenen Zähler ist genau der Fall, den die P4-Doktrin
        # unterdrücken oder ehrlich machen will (KONZEPT-UNVOLLSTAENDIGE-WERTE
        # §3). Hier ist er ehrlich zu machen: die Basis wächst mit.
        _basis = auslastungs_basis_kwh(speicher_kapazitaet, fenster.tage)
        if _basis is not None:
            speicher_auslastungs_basis = round(_basis, 1)
            _au = auslastung_prozent(se, _basis)
            if _au is not None:
                speicher_auslastung = round(_au, 1)

        # Etappe C1+C4: stundengewichteter effektiver Netz-Ladepreis für den Monat.
        # Helper liefert immer ein Ergebnis (auch bei dünner Datenlage) — UI
        # entscheidet anhand der `quelle`, ob KPI anzeigen oder nur Param.
        if speicher_ladung_netz is not None and speicher_ladung_netz > 0:
            from calendar import monthrange as _monthrange
            from backend.services.speicher_wirtschaftlichkeit import (
                berechne_effektiver_ladepreis as _berechne_eff_ladepreis,
            )
            try:
                _ende = date(jahr, monat, _monthrange(jahr, monat)[1])
                eff = await _berechne_eff_ladepreis(
                    db, anlage_id=anlage_id, von=date(jahr, monat, 1), bis=_ende,
                )
                # Wert nur zurückgeben, wenn belastbar (dyn-tarif/boersenpreis)
                # ODER zumindest mit Diagnose (datenbasis-zu-duenn). Bei
                # `keine-netzladung`/`keine-tep-daten` bleibt das Feld None.
                if eff.effektiver_ladepreis_cent is not None:
                    speicher_eff_ladepreis = round(eff.effektiver_ladepreis_cent, 2)
                speicher_eff_ladepreis_quelle = eff.quelle
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "aktueller_monat: effektiver-Ladepreis-Lookup fehlgeschlagen "
                    "(anlage=%s, %s/%s): %s", anlage_id, jahr, monat, e,
                )

    # WP: Heizung/Warmwasser-Split (Wärme + bei getrennter Strommessung auch Strom, #191)
    wp_heizung = None
    wp_warmwasser = None
    wp_strom_heizen = None
    wp_strom_warmwasser = None
    wp_modus_heizen = None
    wp_modus_kuehlen = None
    wp_modus_warmwasser = None
    wp_modus_lueften = None
    wp_modus_entfeuchten = None
    wp_nutz_lueften = None
    wp_nutz_entfeuchten = None
    wp_modus_rest = None
    wp_modus_abdeckung = None
    wp_modus_gemessen = None
    wp_modus_bezug = None
    # ⭐ **EINE Lesestelle, zwei Herkünfte** (WK-16i): `_wp_funktion` ist die
    # Monatszeile, wo sie eine Menge trägt, sonst die Faltung über die
    # Geräte-Mengen. Beide tragen dieselben Feldnamen — deshalb steht hier
    # **kein** zweiter Zweig, der dieselben vier Gates noch einmal schreibt.
    if _wp_funktion.heizung_kwh > 0:
        wp_heizung = round(_wp_funktion.heizung_kwh, 2)
    if _wp_funktion.warmwasser_kwh > 0:
        wp_warmwasser = round(_wp_funktion.warmwasser_kwh, 2)
    if _wp_funktion.hat_split:
        # Auch 0-Werte zurückgeben, damit Frontend "getrennt erfasst, aktuell 0"
        # vs. "gar nicht getrennt erfasst" unterscheiden kann.
        wp_strom_heizen = round(_wp_funktion.strom_heizen_kwh, 2)
        wp_strom_warmwasser = round(_wp_funktion.strom_warmwasser_kwh, 2)
    if mf_wp is not None:
        # #263 K-2: derselbe Alles-oder-nichts-Grundsatz für den Modus-Split —
        # ohne erfasste Stunde gibt es keine Aufteilung statt einer 0.
        if mf_wp.hat_modus_split:
            wp_modus_heizen = round(mf_wp.modus_strom_heizen_kwh, 2)
            wp_modus_kuehlen = round(mf_wp.modus_strom_kuehlen_kwh, 2)
            wp_modus_warmwasser = round(mf_wp.modus_strom_warmwasser_kwh, 2)
            wp_modus_lueften = round(mf_wp.modus_strom_lueften_kwh, 2)
            wp_modus_entfeuchten = round(mf_wp.modus_strom_entfeuchten_kwh, 2)
            # R-C: nur mit Zahl (D-Sicht) — `or None` statt einer 0-Zeile.
            wp_nutz_lueften = round(mf_wp.nutzenergie_lueften_kwh, 2) or None
            wp_nutz_entfeuchten = (
                round(mf_wp.nutzenergie_entfeuchten_kwh, 2) or None)
            wp_modus_rest = round(mf_wp.modus_nicht_aufgeteilt_kwh, 2)
            wp_modus_abdeckung = round(mf_wp.modus_abdeckung_h, 1)
            wp_modus_gemessen = mf_wp.modus_gemessen
            # W-17b: die Grundmenge des Balkens, damit er nicht stumm unter
            # einer groesseren Kachel steht.
            wp_modus_bezug = round(mf_wp.modus_strom_bezug_kwh, 2)

    # W-4 (SOLL §4.1): je Funktion eine eigene Zahl. Sie beantwortet, was die
    # Gesamtzahl nicht kann — *warum* eine Anlage dasteht, wie sie dasteht.
    # Warmwasser liegt bauartbedingt niedriger (höhere Zieltemperatur); wer viel
    # Warmwasser macht, hat deshalb eine niedrigere Gesamtzahl, **ohne schlechter
    # zu sein**. Dieselben R2-Sperren, weil dieselbe Layer-Funktion gerufen wird.
    # W-5 (SOLL §4.1): Kältemenge ÷ Kühlstrom. Beide Größen nur gemessen — es
    # gibt keinen Weg, eine Kältemenge abzuleiten. Heißt bewusst NICHT „SEER"
    # (genormte Prüfstandsgröße), sondern „Arbeitszahl Kühlen".
    wp_az_kuehlen = arbeitszahl_kuehlen(
        mf_wp.nutzenergie_kuehlen_kwh if mf_wp is not None else None,
        mf_wp.modus_strom_kuehlen_kwh if mf_wp is not None else None,
        # Kuehlen ist KEINE klimaanlagen-exklusive Funktion: A4 ist eine
        # Luft-Wasser-WP mit Kaeltemengenzaehler, und die `luft_luft`-Bedingung
        # der Betriebsart-Felder ist weich. Deshalb dieselbe je-Funktion-Frage
        # wie oben — nicht „gilt hier ohnehin nicht".
        abgrenzung_verletzt=_wp_abgrenzung_je_funktion["kuehlen"],
    )
    wp_az_funktion = arbeitszahl_je_funktion(
        heizung_kwh=wp_heizung,
        strom_heizen_kwh=wp_strom_heizen,
        warmwasser_kwh=wp_warmwasser,
        strom_warmwasser_kwh=wp_strom_warmwasser,
        # WK-16i: dieselbe Quelle wie die vier Mengen darüber — im laufenden
        # Monat also das Kennzeichen der **beitragenden** Geräte, wie es der
        # Tag seit jeher fragt (`views.py::_wp_getrennte_strommessung_tag`).
        hat_split=_wp_funktion.hat_split,
        # **N-479: der Monat darf jetzt denselben Zeitraum-Grund führen wie der
        # Tag.** Er konnte es nicht, weil seine Summen („gemessen 0" und „kein
        # Zähler" tragen beide 0.0 bei) die Frage nicht mehr beantworteten — und
        # meldete deshalb im Sommer „kein Wärmemengenzähler zugeordnet", obwohl
        # beide Zähler hingen und lieferten (simon42 T89667, dietmar1968). Die
        # Marke kommt aus den Monats-Fakten, je Funktion getrennt: Die Heizwärme
        # kann gemessen sein und die Warmwasser-Wärme nicht.
        # ⚠ **BEIDE Seiten müssen gemessen sein, nicht nur die Wärme** (N-438/S3,
        # von deren Probe gefangen). „In diesem Zeitraum nicht geheizt" ist eine
        # Aussage über das Gerät — sie setzt voraus, dass Zähler **und** Nenner
        # dastanden und null meldeten. Bei gemessener Wärme ohne Heizstrom ist
        # „kein Stromverbrauch erfasst" der genauere Satz und behält Vorrang.
        null_ist_gemessen_heizen=(
            _wp_funktion.heizung_gemessen and _wp_funktion.strom_heizen_gemessen
        ),
        null_ist_gemessen_warmwasser=(
            _wp_funktion.warmwasser_gemessen
            and _wp_funktion.strom_warmwasser_gemessen
        ),
        # N-391: Misst EIN gemeinsamer Wärmemengenzähler beide Funktionen, gibt
        # es die Wärme je Funktion nicht — die Zeile sagt dann den Grund, statt
        # die Gesamtwärme durch den Heizstrom zu teilen (gemessen: 5,0 statt 3,0).
        waerme_ist_gesamt=_wp_funktion.waerme_ist_gesamt,
        waerme_abgeleitet_kwh=wp_waerme_abgeleitet_kwh,
        abgrenzung_verletzt=wp_abgrenzung_verletzt,
        abgrenzung_je_funktion_grund=_wp_abgrenzung_je_funktion,
        # **R-2 (WK-16h, N-499): anlagenweit entsteht eine Funktions-Zahl nur
        # aus den Geräten, die die Achse HABEN.** Die Vereinigung über die
        # beitragenden Geräte steht an einer Stelle (`achsen_der_anlage`) —
        # Monat, Tag und Jahr fragen dieselbe. Trägt die Ausstattung nur eine
        # Wärme-Achse, ist die anlagenweite Gesamtzahl ihre Zahl; eine Schranke
        # geht dabei nicht mit (`als_arbeitszahl` liefert dann `None`).
        achsen=achsen_der_anlage(_wp_kennzahlen_je_geraet),
        gesamt=als_arbeitszahl(wp_arbeitszahl),
    )
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("mf_bkw", "mf_emob", "mf_sonstiges", "mf_wp", "speicher_auslastung", "speicher_auslastungs_basis", "speicher_eff_ladepreis", "speicher_eff_ladepreis_quelle", "speicher_ersparnis", "speicher_imd_ladepreis", "speicher_kapazitaet", "speicher_ladung_netz", "speicher_soc_drift_flag", "speicher_vollzyklen", "speicher_wirkungsgrad", "speicher_wirkungsgrad_quelle", "wp_az_funktion", "wp_az_kuehlen", "wp_heizung", "wp_modus_abdeckung", "wp_modus_bezug", "wp_modus_entfeuchten", "wp_modus_gemessen", "wp_modus_heizen", "wp_modus_kuehlen", "wp_modus_lueften", "wp_modus_rest", "wp_modus_warmwasser", "wp_nutz_entfeuchten", "wp_nutz_lueften", "wp_strom_heizen", "wp_strom_warmwasser", "wp_warmwasser",) if k in _loc}


def geraete_sicht(*, _wp_kennzahlen_je_geraet, get_val, emob_entscheid=None, investitionen, mf_bkw, mf_emob, mf_sonstiges, netzbezug_preis_effektiv_cent, speicher_eff_ladepreis, speicher_imd_ladepreis, speicher_ladung_netz, wp_arbeitszahl, wp_az_funktion, wp_az_kuehlen):
    """D-Sicht: die Tabelle je Geraet und der EINE Kasten; Sonstiges-Geraete, E-Mob-Mengen, BKW-Eigenverbrauch.

    Aus `get_aktueller_monat` Zeilen 1151-1278 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── D-Sicht: die Tabelle je Gerät und der EINE Kasten ──────────────────
    #
    # Die Gründe werden **hier** gesammelt, weil erst hier alle vier vorliegen;
    # welche davon in den Kasten gehören, entscheidet die Klasse an der
    # Grund-Konstante (`grund_klasse`), nicht diese Route und erst recht nicht
    # der Client.
    wp_block_geraete = geraete_zeilen(_wp_kennzahlen_je_geraet)
    # R-4: die **Geräte**-Ausstattungsgründe kommen mit in den Kasten, mit dem
    # Namen davor und dedupliziert gegen die anlagenweiten Zeilen darüber.
    wp_block_moeglich = was_noch_moeglich([
        ("Arbeitszahl", wp_arbeitszahl.grund),
        ("Arbeitszahl Heizen", wp_az_funktion.heizen.grund),
        ("Arbeitszahl Warmwasser", wp_az_funktion.warmwasser.grund),
        ("Arbeitszahl Kühlen", wp_az_kuehlen.grund),
    ], wp_block_geraete)

    # E-Mobilität: PV/Netz/Extern-Split + V2H
    emob_pv = get_val("emob_pv_ladung_kwh")
    emob_ladung_netz = None
    emob_ladung_extern = None
    emob_v2h = None

    # C1d: der Netz-Anteil kommt aus dem KANONISCHEN Pool, nicht aus einer
    # Roh-Summe über beide Typen. E-Auto und Wallbox messen denselben Fluss
    # (Vehicle- vs. Loadpoint-Perspektive) — genau die Doppelzählung, die
    # `typ_aggregation` oben schon bewusst vermeidet. `emob_pv` daneben stammt
    # aus derselben Trias (`get_val` → Fakten-Zweig), beide passen jetzt
    # zusammen statt aus zwei Rechnungen zu kommen.
    if mf_emob is not None:
        if mf_emob.ladung_netz_kwh > 0:
            emob_ladung_netz = round(mf_emob.ladung_netz_kwh, 2)
        if mf_emob.extern_kwh > 0:
            emob_ladung_extern = round(mf_emob.extern_kwh, 2)
        if mf_emob.v2h_entladung_kwh > 0:
            emob_v2h = round(mf_emob.v2h_entladung_kwh, 2)
    # N-555/N-557: hat die Route den Monat selbst entschieden (laufender Monat,
    # Monat ohne gemessene gespeicherte Heimladung), gehören Netz und Extern zu
    # DIESEM Entscheid — sonst stünde der Netz-Anteil einer verworfenen Schätzung
    # neben einer Heimladung von 0, und Extern käme erst mit dem Monatsabschluss.
    if emob_entscheid is not None:
        _pool = emob_entscheid.pool
        # Die Trias kommt geschlossen aus EINER Entscheidung (#262).
        emob_pv = round(_pool.pv_kwh, 2) if _pool.pv_kwh > 0 else None
        emob_ladung_netz = round(_pool.netz_kwh, 2) if _pool.netz_kwh > 0 else None
        if _pool.extern_kwh > 0:
            emob_ladung_extern = round(_pool.extern_kwh, 2)

    # BKW: Eigenverbrauch
    bkw_eigenverbrauch = None
    if mf_bkw is not None and mf_bkw.eigenverbrauch_gemessen_kwh > 0:
        bkw_eigenverbrauch = round(mf_bkw.eigenverbrauch_gemessen_kwh, 2)

    # Sonstiges: erzeuger + verbraucher aggregieren
    sonstiges_erzeugung = None
    sonstiges_eigenverbrauch = None
    sonstiges_einspeisung = None
    sonstiges_verbrauch = None
    sonstiges_bezug_pv = None
    sonstiges_bezug_netz = None

    sonstiges_geraete: list[SonstigesGeraet] = []
    if mf_sonstiges is not None:
        if mf_sonstiges.erzeugung_kwh > 0:
            sonstiges_erzeugung = round(mf_sonstiges.erzeugung_kwh, 2)
        if mf_sonstiges.eigenverbrauch_kwh > 0:
            sonstiges_eigenverbrauch = round(mf_sonstiges.eigenverbrauch_kwh, 2)
        if mf_sonstiges.einspeisung_kwh > 0:
            sonstiges_einspeisung = round(mf_sonstiges.einspeisung_kwh, 2)
        if mf_sonstiges.verbrauch_kwh > 0:
            sonstiges_verbrauch = round(mf_sonstiges.verbrauch_kwh, 2)
        if mf_sonstiges.bezug_pv_kwh > 0:
            sonstiges_bezug_pv = round(mf_sonstiges.bezug_pv_kwh, 2)
        if mf_sonstiges.bezug_netz_kwh > 0:
            sonstiges_bezug_netz = round(mf_sonstiges.bezug_netz_kwh, 2)

        # Pro-Gerät-Liste in Investitions-Reihenfolge. Die MENGEN kommen aus
        # `je_geraet` (dort schon kategorie-bewusst und laufzeitgefiltert),
        # Bezeichnung und Kategorie aus der Investition — die Anzeige-Form
        # bleibt hier, die Auflösung nicht mehr.
        def _v(x: float) -> Optional[float]:
            return round(x, 2) if x > 0 else None
        for inv in investitionen:
            if inv.typ != "sonstiges":
                continue
            g = mf_sonstiges.je_geraet.get(inv.id)
            if g is None:
                continue
            # N-250: Richtung ohne gepflegte Kategorie aus dem WERT, nicht aus
            # einem Default. Hier stand `.get("kategorie", "erzeuger")` — als
            # einzige von vier Stellen im Baum: die beiden Tages-Schreibpfade
            # (`snapshot/komponenten_beitraege`, `live_sensor_config`) und der
            # Tages-Layer (`core/berechnungen/energie.sonstiges_kwh_je_richtung`)
            # lesen eine leere Kategorie als *Verbraucher*, und `monats_fakten`
            # nimmt ohne sie **beide** Felder mit. Ein ungepflegtes Gerät fiel
            # deshalb in den Erzeuger-Zweig, scheiterte dort an `erzeugung > 0`
            # und war unsichtbar — während seine Zahlen in den Summen darüber
            # mitliefen. Gemeldet an einem Gerät mit Verbrauch (rapahl, 08/2026).
            # Ein *gepflegtes* Gerät ändert sich durch diese Zeile nicht.
            kat = sonstiges_richtung(
                (inv.parameter or {}).get("kategorie"),
                hat_erzeugung=g.erzeugung_kwh > 0,
            )
            if kat == "abgabe":
                if g.abgabe_kwh > 0 or g.einspeise_erloes_euro > 0:
                    sonstiges_geraete.append(SonstigesGeraet(
                        bezeichnung=inv.bezeichnung, kategorie="abgabe",
                        abgabe_kwh=_v(g.abgabe_kwh),
                        erloes_euro=_v(g.einspeise_erloes_euro),
                    ))
            elif kat == "verbraucher":
                if g.verbrauch_kwh > 0 or g.bezug_pv_kwh > 0 or g.bezug_netz_kwh > 0:
                    sonstiges_geraete.append(SonstigesGeraet(
                        bezeichnung=inv.bezeichnung, kategorie="verbraucher",
                        verbrauch_kwh=_v(g.verbrauch_kwh),
                        bezug_pv_kwh=_v(g.bezug_pv_kwh),
                        bezug_netz_kwh=_v(g.bezug_netz_kwh),
                    ))
            else:
                if g.erzeugung_kwh > 0:
                    sonstiges_geraete.append(SonstigesGeraet(
                        bezeichnung=inv.bezeichnung, kategorie="erzeuger",
                        erzeugung_kwh=_v(g.erzeugung_kwh),
                        eigenverbrauch_kwh=_v(g.eigenverbrauch_kwh),
                        einspeisung_kwh=_v(g.einspeisung_kwh),
                    ))

    # (`netzbezug_durchschnittspreis` wird oben mit der Monatszeile geladen —
    #  er geht in die Netzbezugskosten ein und muss dort schon vorliegen.)

    # R15-1 (Rainer-Kostenkacheln): Kosten der Speicher-Netzladung.
    # Preis-Kette TEP-effektiv → IMD-Ø (Handeingabe) → Bezugspreis
    # (Ø-Monatspreis vor festem Tarif) — Berechnungs-Layer-Helper.
    netzladung_kosten = berechne_netzladung_kosten(
        speicher_ladung_netz,
        eff_ladepreis_cent=speicher_eff_ladepreis,
        imd_preis_cent=speicher_imd_ladepreis,
        netzbezug_preis_cent=netzbezug_preis_effektiv_cent,
    )
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("bkw_eigenverbrauch", "emob_ladung_extern", "emob_ladung_netz", "emob_pv", "emob_v2h", "netzladung_kosten", "sonstiges_bezug_netz", "sonstiges_bezug_pv", "sonstiges_eigenverbrauch", "sonstiges_einspeisung", "sonstiges_erzeugung", "sonstiges_geraete", "sonstiges_verbrauch", "wp_block_geraete", "wp_block_moeglich",) if k in _loc}

