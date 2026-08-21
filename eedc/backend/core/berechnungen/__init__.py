"""Berechnungs-Layer — Single Source of Truth für alle Aggregat-Berechnungen.

Dieser Layer bündelt Berechnungs-Funktionen, die historisch über die
Codebase verteilt waren (Drift-Quelle, siehe BKW-Doppelzählung 2026-05-19,
Rainer-PN). Jede Whitelist, jeder Σ-Helper, jede Invariante für die zentralen
Aggregat-Tabellen (TagesEnergieProfil, TagesZusammenfassung, InvestitionMonatsdaten)
gehört hierher — NICHT in Domain-Module wie daten_checker.py, prognosen.py
oder Routes.

Regel (siehe `docs/ADR-001-BERECHNUNGS-LAYER.md`):
- Jede neue Aggregat-Berechnung MUSS in `core/berechnungen/` definiert werden.
- Jeder bestehende Code, der eine Aggregat-Berechnung dupliziert und aus
  anderem Grund angefasst wird, MUSS bei der Gelegenheit auf den Layer migrieren.
- Der Pytest-Konformitäts-Test `test_berechnungs_layer_konformitaet.py` blockiert
  PRs, die Whitelist-/Prefix-Definitionen außerhalb dieses Layers neu einführen.

Submodule:
- `energie` — kWh-Aggregate aus komponenten_kwh, TagesEnergieProfil
- `einspeise_erloes` — §51-bereinigte Einspeise-Erlös-Berechnung
- `dienstliche_ladekosten` — Euro-Bewertung der Dienstwagen-Ladung (Gegenposten
  zur AG-Erstattung); PV-Anteil zum Netzbezugspreis, Netzanteil zum Wallbox-Preis
- `pv_anteil_ladung` — abgeleiteter PV-Anteil einer Heimladung aus den eigenen
  Stundengrößen, wo keine Wallbox ihn misst (N-141 (c); Ergebnis ist eine
  Schätzung und muss gekennzeichnet werden)
- `counter` — Counter-Aggregate (WP-Starts/Betriebsstunden): Stunden-Σ aus
  Tages-Boundary-Diff ableiten + Pflicht-Invariante (Variante 2-light)
- `invarianten` — Konsistenz-Asserts (Σ Hourly == Daily, Σ pv == komponenten_pv etc.)
- `speicher` — Speicher-Effizienz (gleitend, carry-over-immun)
- `spez_ertrag` — spezifischer Ertrag annualisiert (saisonal gewichtet,
  per-Monat-aktives kWp) — Cockpit-Kachel == HA-Export-Sensor
- `prognose_korrektur` — Kaskaden-Faktoren auf Prognose-Stundenprofil,
  Tageswert = Σ Export-Slots (Invariante HA-Export #150 / Prognosen-Vergleich)

Geplant (step-by-step, wenn Konsumenten angefasst werden):
- `peaks` — Peak-Werte (peak_pv/bezug/einspeisung)
- `kennzahlen` — Eigenverbrauch, Autarkie, spez. Tagesertrag (Migration aus calculations.py)
"""

from backend.core.berechnungen.alternativkosten import (
    berechne_wp_alternativkosten_ersparnis,
    alter_wirkungsgrad,
    alle_ersetzen_nichts,
    ersetzt_keine_heizung,
    ERSETZT_NICHTS,
    gas_kosten_altanlage,
)
from backend.core.berechnungen.co2_amortisation import (
    QUELLE_DEFAULT,
    QUELLE_FEHLT,
    QUELLE_KEIN_DEFAULT,
    QUELLE_OVERRIDE,
    GraueLastBericht,
    GraueLastPosten,
    graue_last_einzeln,
    summe_graue_last,
)
from backend.core.berechnungen.counter import (
    CounterKonsistenzBericht,
    assert_counter_konsistent,
    pruefe_counter_konsistent,
    verteile_counter_auf_stunden,
)
from backend.core.berechnungen.datenquellen import (
    connector_deckt_monatsanfang,
    merge_datenquellen,
    teilzeitraum_felder,
)
from backend.core.berechnungen.bkw_finanz import (
    BkwEigenverbrauchsAnteil,
    BkwFinanzBeitrag,
    bkw_eigenverbrauch_anteil,
    bkw_finanz_beitrag,
)
from backend.core.berechnungen.dienstliche_ladekosten import (
    DienstlicheLadekosten,
    DienstlicheLadungZeile,
    berechne_dienstliche_ladekosten,
)
from backend.core.berechnungen.einspeise_erloes import (
    EinspeiseErloes,
    einspeise_erloes_euro,
)
from backend.core.berechnungen.finanz_aggregat import (
    FinanzAggregat,
    FinanzMonatsZeile,
    berechne_finanz_aggregat,
)
from backend.core.berechnungen.amortisation import (
    AmortisationsFortschritt,
    berechne_amortisations_fortschritt,
)
from backend.core.berechnungen.investitionskosten import (
    relevante_kosten_aus_investitionen,
)
from backend.core.berechnungen.kapitalrechnung import (
    ErsparnisPosten,
    annahme_dauer_text,
    erklaerung_jahres_ersparnis,
    jahres_ersparnis_euro,
    kapitaleinsatz_euro,
)
from backend.core.berechnungen.ertrag_zerlegung import (
    ErtragsZerlegung,
    anteil_je_zeile,
    verteile_nach_gewichten,
    zerlege_kumulierten_ertrag,
)
from backend.core.berechnungen.ust_eigenverbrauch import (
    AFA_JAHRE,
    UstJahresanteil,
    bemessungsgrundlage_aus_investitionen,
    berechne_ust_eigenverbrauch,
    ust_eigenverbrauch_fuer_anlage,
)
from backend.core.berechnungen.emob import (
    QUELLE_GEMESSEN,
    QUELLE_KEINE,
    QUELLE_LADUNG,
    EffizienzWert,
    eauto_effizienz_100km,
)
from backend.core.berechnungen.imd_monatsaggregat import (
    ImdTypBeitrag,
    imd_typ_beitrag,
)
from backend.core.berechnungen.modus_split import (
    ModusSplit,
    ModusStunde,
    REGEL_JAZ_MODUS_SPLIT,
    abgeleitete_heizwaerme_kwh,
    heiz_effizienz_gepflegt,
    heizwaerme_ist_abgeleitet,
    falte_modus_split_tag,
    summiere_modus_split,
    teilmengen_passen,
    unbekannte_modi,
)
from backend.core.berechnungen.netzbezug_kosten import berechne_netzbezug_kosten
from backend.core.berechnungen.kennzahlen import (
    autarkie_prozent,
    eigenverbrauchsquote_prozent,
    spezifischer_ertrag_kwh_kwp,
)
from backend.core.berechnungen.energie import (
    BATTERIE_KOMPONENTEN_PREFIXE,
    PV_KOMPONENTEN_PREFIXE,
    SONSTIGES_KOMPONENTEN_PREFIX,
    WAERMEPUMPE_KOMPONENTEN_PREFIXE,
    WALLBOX_KOMPONENTEN_PREFIXE,
    SonstigesTagesSummen,
    batterie_kw_spalte,
    erzeuger_kwh_je_investition,
    erzeugung_hinter_zaehler_kwh,
    sonstiges_kwh_je_richtung,
    sonstiges_richtung,
    summe_batterie_netto_kwh,
    summe_bkw_kwh,
    summe_pv_anlage_kwh,
    summe_pv_bkw_kwh,
    geraete_spalte_kw,
    summe_waermepumpe_kwh,
    waermepumpe_kwh_je_investition,
    summe_wallbox_eauto_kwh,
    wert_basis_kwh,
)
from backend.core.berechnungen.invarianten import (
    aggregiere_tep_komponenten,
    assert_speicher_durchsatz_konsistent,
    assert_speicher_ladung_konsistent,
    assert_speicher_netzladung_kumulativ,
    assert_tep_komponenten_intern_konsistent,
    assert_tep_tz_komponenten_konsistent,
    assert_tep_tz_konsistent,
    pruefe_speicher_durchsatz_konsistenz,
    pruefe_speicher_ladung_konsistenz,
    pruefe_speicher_netzladung_kumulativ,
    pruefe_tep_komponenten_intern_konsistenz,
    pruefe_tep_tz_komponenten_konsistenz,
    pruefe_tep_tz_konsistenz,
)
from backend.core.berechnungen.pv_anteil_ladung import (
    REGEL_EINSPEISE_DECKUNG,
    AbgeleiteterLadeAnteil,
    leite_pv_anteil_ab,
)
from backend.core.berechnungen.pv_verteilung import (
    QUELLE_FEHLT as PV_QUELLE_FEHLT,
    QUELLE_GEMESSEN as PV_QUELLE_GEMESSEN,
    QUELLE_VERTEILT as PV_QUELLE_VERTEILT,
    STATUS_FEHLT as PV_STATUS_FEHLT,
    STATUS_OK as PV_STATUS_OK,
    STATUS_TEIL_LUECKE as PV_STATUS_TEIL_LUECKE,
    STATUS_VERTEILT as PV_STATUS_VERTEILT,
    PvModul,
    PvModulWert,
    gesamt_pv_kwh,
    ist_vollstaendig,
    klassifiziere_pv_monat,
    resolve_pv_je_modul,
    verteile_basis_kwh_nach_kwp,
)
from backend.core.berechnungen.preis_rang import (
    GUENSTIG_SCHWELLE_FAKTOR,
    GUENSTIG_TOP_N,
    PEAK_AUSSCHLUSS_N,
    RANG_TEUER,
    PreisRangErgebnis,
    berechne_preis_rang,
    guenstig_schwelle,
)
from backend.core.berechnungen.prognose_korrektur import (
    KorrigiertesTagesprofil,
    korrigiere_tagesprofil,
)
from backend.core.berechnungen.prognose_final import (
    soll_final_einfrieren,
)
from backend.core.berechnungen.erzeuger_traeger import (
    abgetretene_bkw_ids,
    bkw_kwp_aus_kindern,
    erzeuger_traeger,
    modul_kinder,
    traegt_erzeugungsgroessen_selbst,
)
from backend.core.berechnungen.spez_ertrag import (
    MONATSGEWICHTE_52N,
    PV_ERZEUGER_TYPEN,
    berechne_spez_ertrag_annualisiert,
    kwp_aktiv_im_monat,
    monatsgewichte_aus_pvgis,
)
from backend.core.berechnungen.speicher import (
    EFFIZIENZ_FENSTER_MONATE,
    MonatsEffizienz,
    SocSpanne,
    auslastung_prozent,
    auslastungs_basis_kwh,
    gleitende_effizienz,
    netz_ladung_stunde_kwh,
    soc_spanne,
    speicher_effizienz_prozent,
    vollzyklen,
)
from backend.core.berechnungen.speicher_simulation import (
    SpeicherSimErgebnis,
    StundenBilanz,
    simuliere_speicher_tag,
)
from backend.core.berechnungen.speicher_wirkungsgrad import (
    MINDEST_LADUNG_KWH,
    SpeicherWirkungsgrad,
    delta_soc_kwh,
    speicher_wirkungsgrad,
)
from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
    ETA_DEGRADATION_SCHWELLE_PROZENTPUNKTE,
    SOC_DRIFT_SCHWELLE_PROZENTPUNKTE,
    SPEICHER_IST_MIN_MONATE,
    NetzladungKosten,
    SpeicherErsparnisErgebnis,
    SpeicherIstAggregat,
    aggregiere_speicher_ist,
    berechne_netzladung_kosten,
    berechne_speicher_ersparnis,
    berechne_v2h_ersparnis,
    ist_eta_degradation_alarm,
    ist_soc_drift_signifikant,
)
from backend.core.berechnungen.tagesbilanz import (
    TagesBilanz,
    bilanz_aus_stundenrows,
)
from backend.core.berechnungen.verbrauch import (
    VerbrauchsKennzahlen,
    berechne_verbrauchs_kennzahlen,
)
from backend.core.berechnungen.grundlast import (
    GrundlastKennzahlen,
    berechne_grundlast,
)
from backend.core.berechnungen.monatsfenster import (
    Monatsfenster,
    anteilig,
    monatsfenster,
    monatsfenster_investition,
)

__all__ = [
    "GrundlastKennzahlen",
    "berechne_grundlast",
    "Monatsfenster",
    "anteilig",
    "monatsfenster",
    "monatsfenster_investition",
    "TagesBilanz",
    "bilanz_aus_stundenrows",
    "berechne_wp_alternativkosten_ersparnis",
    "alter_wirkungsgrad",
    "alle_ersetzen_nichts",
    "ersetzt_keine_heizung",
    "ERSETZT_NICHTS",
    "gas_kosten_altanlage",
    "QUELLE_OVERRIDE",
    "QUELLE_DEFAULT",
    "QUELLE_FEHLT",
    "QUELLE_KEIN_DEFAULT",
    "GraueLastBericht",
    "GraueLastPosten",
    "graue_last_einzeln",
    "summe_graue_last",
    "CounterKonsistenzBericht",
    "assert_counter_konsistent",
    "pruefe_counter_konsistent",
    "verteile_counter_auf_stunden",
    "connector_deckt_monatsanfang",
    "merge_datenquellen",
    "teilzeitraum_felder",
    "BkwFinanzBeitrag",
    "bkw_finanz_beitrag",
    "BkwEigenverbrauchsAnteil",
    "bkw_eigenverbrauch_anteil",
    "DienstlicheLadekosten",
    "DienstlicheLadungZeile",
    "berechne_dienstliche_ladekosten",
    "EinspeiseErloes",
    "einspeise_erloes_euro",
    "AbgeleiteterLadeAnteil",
    "leite_pv_anteil_ab",
    "REGEL_EINSPEISE_DECKUNG",
    "FinanzAggregat",
    "FinanzMonatsZeile",
    "berechne_finanz_aggregat",
    "AFA_JAHRE",
    "UstJahresanteil",
    "AmortisationsFortschritt",
    "berechne_amortisations_fortschritt",
    "relevante_kosten_aus_investitionen",
    "ErsparnisPosten",
    "annahme_dauer_text",
    "erklaerung_jahres_ersparnis",
    "jahres_ersparnis_euro",
    "kapitaleinsatz_euro",
    "ErtragsZerlegung",
    "anteil_je_zeile",
    "verteile_nach_gewichten",
    "zerlege_kumulierten_ertrag",
    "bemessungsgrundlage_aus_investitionen",
    "berechne_ust_eigenverbrauch",
    "ust_eigenverbrauch_fuer_anlage",
    "ImdTypBeitrag",
    "ModusSplit",
    "REGEL_JAZ_MODUS_SPLIT",
    "abgeleitete_heizwaerme_kwh",
    "heizwaerme_ist_abgeleitet",
    "heiz_effizienz_gepflegt",
    "ModusStunde",
    "falte_modus_split_tag",
    "summiere_modus_split",
    "teilmengen_passen",
    "unbekannte_modi",
    "imd_typ_beitrag",
    "berechne_netzbezug_kosten",
    "autarkie_prozent",
    "eigenverbrauchsquote_prozent",
    "spezifischer_ertrag_kwh_kwp",
    "QUELLE_GEMESSEN",
    "QUELLE_LADUNG",
    "QUELLE_KEINE",
    "EffizienzWert",
    "eauto_effizienz_100km",
    "PV_KOMPONENTEN_PREFIXE",
    "WAERMEPUMPE_KOMPONENTEN_PREFIXE",
    "WALLBOX_KOMPONENTEN_PREFIXE",
    "BATTERIE_KOMPONENTEN_PREFIXE",
    "summe_pv_bkw_kwh",
    "summe_pv_anlage_kwh",
    "summe_bkw_kwh",
    "erzeuger_kwh_je_investition",
    "erzeugung_hinter_zaehler_kwh",
    "SONSTIGES_KOMPONENTEN_PREFIX",
    "SonstigesTagesSummen",
    "sonstiges_kwh_je_richtung",
    "sonstiges_richtung",
    "geraete_spalte_kw",
    "summe_waermepumpe_kwh",
    "waermepumpe_kwh_je_investition",
    "summe_wallbox_eauto_kwh",
    "batterie_kw_spalte",
    "summe_batterie_netto_kwh",
    "wert_basis_kwh",
    "assert_tep_tz_konsistent",
    "pruefe_tep_tz_konsistenz",
    "assert_tep_tz_komponenten_konsistent",
    "pruefe_tep_tz_komponenten_konsistenz",
    "aggregiere_tep_komponenten",
    "assert_tep_komponenten_intern_konsistent",
    "pruefe_tep_komponenten_intern_konsistenz",
    "assert_speicher_ladung_konsistent",
    "pruefe_speicher_ladung_konsistenz",
    "assert_speicher_netzladung_kumulativ",
    "pruefe_speicher_netzladung_kumulativ",
    "assert_speicher_durchsatz_konsistent",
    "pruefe_speicher_durchsatz_konsistenz",
    "GUENSTIG_SCHWELLE_FAKTOR",
    "GUENSTIG_TOP_N",
    "PEAK_AUSSCHLUSS_N",
    "RANG_TEUER",
    "PreisRangErgebnis",
    "berechne_preis_rang",
    "guenstig_schwelle",
    "KorrigiertesTagesprofil",
    "korrigiere_tagesprofil",
    "soll_final_einfrieren",
    "abgetretene_bkw_ids",
    "bkw_kwp_aus_kindern",
    "erzeuger_traeger",
    "modul_kinder",
    "traegt_erzeugungsgroessen_selbst",
    "MONATSGEWICHTE_52N",
    "PV_ERZEUGER_TYPEN",
    "berechne_spez_ertrag_annualisiert",
    "kwp_aktiv_im_monat",
    "monatsgewichte_aus_pvgis",
    "SpeicherSimErgebnis",
    "StundenBilanz",
    "simuliere_speicher_tag",
    "EFFIZIENZ_FENSTER_MONATE",
    "MonatsEffizienz",
    "SocSpanne",
    "auslastung_prozent",
    "auslastungs_basis_kwh",
    "gleitende_effizienz",
    "netz_ladung_stunde_kwh",
    "soc_spanne",
    "speicher_effizienz_prozent",
    "vollzyklen",
    "MINDEST_LADUNG_KWH",
    "SpeicherWirkungsgrad",
    "delta_soc_kwh",
    "speicher_wirkungsgrad",
    "SPEICHER_IST_MIN_MONATE",
    "SOC_DRIFT_SCHWELLE_PROZENTPUNKTE",
    "ETA_DEGRADATION_SCHWELLE_PROZENTPUNKTE",
    "SpeicherIstAggregat",
    "SpeicherErsparnisErgebnis",
    "NetzladungKosten",
    "aggregiere_speicher_ist",
    "berechne_netzladung_kosten",
    "berechne_speicher_ersparnis",
    "berechne_v2h_ersparnis",
    "ist_soc_drift_signifikant",
    "ist_eta_degradation_alarm",
    "VerbrauchsKennzahlen",
    "berechne_verbrauchs_kennzahlen",
    "PV_QUELLE_GEMESSEN",
    "PV_QUELLE_VERTEILT",
    "PV_QUELLE_FEHLT",
    "PV_STATUS_OK",
    "PV_STATUS_VERTEILT",
    "PV_STATUS_TEIL_LUECKE",
    "PV_STATUS_FEHLT",
    "PvModul",
    "PvModulWert",
    "verteile_basis_kwh_nach_kwp",
    "resolve_pv_je_modul",
    "gesamt_pv_kwh",
    "ist_vollstaendig",
    "klassifiziere_pv_monat",
]
