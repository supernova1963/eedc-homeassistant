"""Konformitäts-Wächter: eine Testdatei im Cluster nennt ihre Schwestern (M15).

**Die Regel** stammt nicht aus diesem Auftrag, sondern aus Gernots Feedback vom
2026-06-14 (Memory `feedback_testabdeckung_per_symbol_nicht_dateiname`, Punkt 3):
*„Im Datei-Docstring die Schwester-Test-Dateien des Moduls auflisten, damit das
Set aus jeder Richtung auffindbar ist."* Sie stand seither nur in einer
Memory-Datei — also nirgends, wo ein Lauf sie prüfen könnte.

**Der Anlass, am Code gemessen.** `ha_statistics_service.py` galt einmal als
„0 Tests", weil die Suche `test_ha_statistics*` lautete und die Familie
`test_ha_lts_*` heißt. Der Fehlbefund floss in einen Refactoring-Plan ein und
hätte Doppelarbeit erzeugt. Gernots Satz dazu: **Namens-Drift erzeugt Lücken aus
beiden Suchrichtungen** — wer Konvention A sucht, übersieht Konvention B. Ein
Docstring, der eine Schwester nennt, macht das Set von jedem Einstiegspunkt aus
begehbar; das ist billiger als jede Umbenennung und billiger als ein
Verzeichnisbaum.

## Warum kein Verzeichnisbaum (E8/M15, Entscheid Gernot 2026-08-24)

E8 sah ursprünglich Themen-Unterverzeichnisse vor. Am Baum gemessen wurde daraus
nichts, und der Grund ist dieselbe Regel wie oben: **135 der 409 Testdateien
(33 %) tragen mehr als ein Thema im Namen** — `test_ha_export_wp_spezialtarif.py`
ist gleichzeitig `ha/`, `waerme/`, `finanzen/` und `import_export/`. Ein
Themen-Ordner wäre eine dritte Konvention über den Feature-Namen gewesen und
hätte für jede dieser 135 Dateien eine Entscheidung getroffen, die der nächste
Sucher nicht nachvollziehen kann. **Nicht neu aufrollen** — wer es doch will,
bringt eine neue Messung mit, nicht das alte Argument.

## Was der Wächter prüft, und was bewusst nicht

Geprüft wird **nur** für Dateien, deren Präfix-Cluster (erstes Namenssegment nach
`test_`) mindestens zwei Dateien umfasst — ein Einzelgänger hat keine Schwester,
und ihn dafür anzumeckern wäre falsch. Verlangt wird eine Nennung im
**Modul-Docstring**, die (a) eine **existierende** Testdatei benennt und (b)
**nicht die Datei selbst** ist.

⚠ **Nicht verlangt wird, dass die Schwester aus demselben Cluster stammt** — und
das ist gemessen, nicht nachlässig: von den 43 Dateien, die heute eine echte
Schwester nennen, verweisen **38 über den Cluster hinaus**, und das sind
regelmäßig die *wertvollsten* Verweise (`test_cockpit_anschaffungsdatum_grenze_651.py`
nennt seinen Symmetriepartner `test_aussichten_…`). Eine Cluster-Pflicht hätte
genau die vorbildlichen Dateien bestraft — derselbe Fehler, vor dem der
Uhr-Wächter nebenan warnt (`test_konformitaet_echte_uhr_in_tests.py`: „Ein
Wächter, der Vorbildlichkeit bestraft, wird beim ersten roten Lauf
abgeschaltet").

⭐ **Die Selbstnennung ist der Grund für Bedingung (b).** Ohne sie hätte die
Baseline 259 gelautet statt 275: **16 Dateien** nennen im Docstring
ausschließlich sich selbst (`test_daten_checker_stilllegung.py` → sich).
Das ist eine Überschrift, kein Querverweis, und ein Prüfer, der sie zählt,
behauptet eine Auffindbarkeit, die es nicht gibt.

**Er heilt keine der 275 bestehenden Dateien** — er verhindert die 276. Dieselbe
Zusage wie beim Uhr-Wächter, und dieselbe Mechanik: die Liste ist abschmelzend.
"""

from __future__ import annotations

import ast
import re
from collections import Counter

from backend.tests.quellbaum import probenbaum

#: Eine Nennung im Docstring: `test_irgendwas.py`.
_NENNUNG = re.compile(r"test_[a-z0-9_]+\.py")


def _cluster(name: str) -> str:
    """Erstes Namenssegment nach `test_` — `test_ha_lts_mean_reader.py` ⇒ `ha`."""
    return name.removeprefix("test_").removesuffix(".py").split("_")[0]


# ── Baseline (gemessen 2026-08-24: 272 Dateien im Cluster ohne Schwesterhinweis)
#
# Erhoben waren es 275; die drei Dateien der `ha_lts`-Familie sind im selben
# Paket abgearbeitet worden — sie sind das Lehrbeispiel der Regel (der
# Fehlbefund „0 Tests" von 2026-06-14 betraf genau sie) und tragen ihre
# Verweise jetzt selbst.
#
# Die Liste ist **abschmelzend** — `test_baseline_ist_nicht_zu_hoch` meldet rot,
# sobald eine gelistete Datei die Regel erfüllt, und zwingt damit zum Streichen
# statt zum Vergessen. Dieselbe Mechanik wie `_BASELINE` im Uhr-Wächter und wie
# `P3A_BASELINE_AUSNAHMEN`; und derselbe Grund, aus dem `EXPECTED_ROUTES = 217`
# gegen 271 reale Routen jahrelang nichts mehr gemessen hat (M1).
#
# Wer eine Datei hier streicht, hat ihren Docstring um einen Schwesterverweis
# ergänzt — das ist die einzige erlaubte Richtung.
_BASELINE: frozenset[str] = frozenset({
    "test_263_innengeraete.py",
    "test_263_k2_betriebsmodus_lesen_mitschreiben.py",
    "test_263_t1_geraete_spalten_beide_pfade.py",
    "test_263_t2_modus_split_tag.py",
    "test_377_zaehlerstaende.py",
    "test_377_zaehlerwechsel.py",
    "test_aggregate_day_kraftstoffpreis_rettung.py",
    "test_aggregate_day_prognose_rettung.py",
    "test_aggregate_day_restore_provenance_299.py",
    "test_aggregator_symmetrie.py",
    "test_aggregiert_eigenverbrauch_v2h_304.py",
    "test_aggregiert_kwp_verteilung.py",
    "test_aktueller_monat_connector_override_325.py",
    "test_aktueller_monat_emob_komponenten.py",
    "test_amortisation_nenner_symmetrie.py",
    "test_aussichten_anschaffungsdatum_grenze_651.py",
    "test_aussichten_bkw_flexpreis_326.py",
    "test_aussichten_eigenverbrauch_imd_304.py",
    "test_aussichten_historischer_tarif.py",
    "test_aussichten_multi_eauto.py",
    "test_aussichten_multi_wp.py",
    "test_backfill_konsolidierung.py",
    "test_backfill_per_tag_commit.py",
    "test_batterie_vorzeichen_durchgaengig.py",
    "test_batterie_vorzeichen_historie_check.py",
    "test_berechnungen_invarianten.py",
    "test_berechnungen_speicher.py",
    "test_bkw_erzeuger_sichten_f10.py",
    "test_bkw_kanon_und_wr_kappung_347.py",
    "test_bkw_parent_pv_module_n266.py",
    "test_bkw_speicher_datenpfad.py",
    "test_bkw_wizard_kwp_f32.py",
    "test_block1_aggregiert_d1_d3.py",
    "test_block1_imd_aggregat_charnetz.py",
    "test_cloud_credentials_maskierung.py",
    "test_cloud_import_async_job.py",
    "test_cloud_quellen_mehrere_349.py",
    "test_co2_amortisation_284.py",
    "test_co2_autarkie_sichten_symmetrie.py",
    "test_co2_bilanz_ha_export_symmetrie.py",
    "test_co2_tages_bezugsgroesse.py",
    "test_co2_wp_readsite_symmetrie.py",
    "test_cockpit_einspeise_neg_preis.py",
    "test_cockpit_ev_ersparnis_flex_326.py",
    "test_cockpit_finanzen_pv_historie.py",
    "test_cockpit_sonstige_netto_ertrag_326.py",
    "test_cockpit_spez_ertrag_periode.py",
    "test_cockpit_uebersicht_benzinpreis_260.py",
    "test_community_autarkie_speicher_294.py",
    "test_community_nachsenden.py",
    "test_community_payload_f47_f48.py",
    "test_community_payload_monats_fakten.py",
    "test_connector_bridge_energy.py",
    "test_connector_daily_poll_300.py",
    "test_connector_ssrf_block.py",
    "test_custom_import_einheit_non_energy.py",
    "test_custom_import_preview_inv_werte.py",
    "test_d3_zaehler_flankenpruefungen.py",
    "test_d3_zaehlerstaende_checker.py",
    "test_dashboards_evcc_pool_fallback.py",
    "test_daten_checker_anschaffungsdatum.py",
    "test_daten_checker_basisdaten_schwere.py",
    "test_daten_checker_bkw_kind_deckt_f39.py",
    "test_daten_checker_bkw_wr_grenze_347.py",
    "test_daten_checker_connector_monatswert.py",
    "test_daten_checker_custom_import_quelle.py",
    "test_daten_checker_einspeiseverguetung_null.py",
    "test_daten_checker_emob_pool_pflege.py",
    "test_daten_checker_emob_sensor_doppelmapping.py",
    "test_daten_checker_erfassungsort_positionen.py",
    "test_daten_checker_erzeuger_vor_anlage.py",
    "test_daten_checker_investition_id_tagging.py",
    "test_daten_checker_klima_betriebsart.py",
    "test_daten_checker_kwp_detailfeld.py",
    "test_daten_checker_leere_tage_trotz_zaehler.py",
    "test_daten_checker_lts_labels.py",
    "test_daten_checker_lts_summen_spalte.py",
    "test_daten_checker_modul_details_kwp.py",
    "test_daten_checker_monats_nachzug.py",
    "test_daten_checker_mqtt_quellenwahl.py",
    "test_daten_checker_ohne_tageswerte.py",
    "test_daten_checker_phev_anteil_unbestimmt.py",
    "test_daten_checker_provenance_detail.py",
    "test_daten_checker_pv_teilabdeckung.py",
    "test_daten_checker_pv_ueber_erfassung.py",
    "test_daten_checker_pv_verteilung.py",
    "test_daten_checker_schema_durchreichung.py",
    "test_daten_checker_sensor_mapping_einheit.py",
    "test_daten_checker_stilllegung.py",
    "test_daten_checker_strompreis_gleichstand.py",
    "test_daten_checker_strompreis_luecke.py",
    "test_daten_checker_tages_zusatzfelder_dok9.py",
    "test_daten_checker_vergleichspreis_fehlt.py",
    "test_daten_checker_verwendungs_stapel.py",
    "test_daten_checker_vorjahr_inbetriebnahme.py",
    "test_daten_checker_wallbox_schwaeche_ab.py",
    "test_daten_checker_wp_getrennte_strommessung.py",
    "test_daten_checker_wp_modus_widerspruch.py",
    "test_daten_checker_zaehler_helfer_empfehlung.py",
    "test_daten_checker_zeitzone.py",
    "test_datenquellen_b8_2.py",
    "test_datenquellen_b8_materialisieren.py",
    "test_datenquellen_historie_hinweis.py",
    "test_datenquellen_invert.py",
    "test_datenquellen_mapping_sync.py",
    "test_datenquellen_p2_assistenz.py",
    "test_datenquellen_pv_aggregat_tagesebene.py",
    "test_datenquellen_reparatur_tageswerte.py",
    "test_datenquellen_resolver_c2a.py",
    "test_datenquellen_resolver_c2b.py",
    "test_datenquellen_speicher_felder.py",
    "test_datenquellen_strompreis_slot.py",
    "test_datenquellen_validierung.py",
    "test_eauto_ersparnis_periode.py",
    "test_ecoflow_diagnose_log.py",
    "test_ecoflow_history_bloecke.py",
    "test_ecoflow_powerocean_mapping.py",
    "test_ecoflow_signatur.py",
    "test_einspeise_erloes.py",
    "test_einspeise_monatswert_392.py",
    "test_einstellungs_sperre_konformitaet.py",
    "test_emob_canonical_migration.py",
    "test_emob_heimladung_canonical.py",
    "test_emob_km_uebersicht_bug.py",
    "test_emob_ladeanteil.py",
    "test_emob_pool_komponenten.py",
    "test_emob_pool_konsistenz.py",
    "test_emob_preisachse_sichten_symmetrie.py",
    "test_emob_readsite_symmetrie.py",
    "test_emob_write_canonical_felder.py",
    "test_emob_zaehlerpfad_quellenregel.py",
    "test_erzeuger_einspeise_erloes.py",
    "test_erzeuger_kwh_je_tag_350.py",
    "test_etappe_4_migrate.py",
    "test_etappe_5_peaks.py",
    "test_etappe_6_drift_check.py",
    "test_genauigkeit_ausreisser_296.py",
    "test_genauigkeit_pv_only.py",
    "test_genauigkeit_wetter_296.py",
    "test_ha_aktivierung_mqtt_default_b7_5c.py",
    "test_ha_export_betriebsart_gemessen_f56.py",
    "test_ha_export_eigenverbrauch_imd_304.py",
    "test_ha_export_multi_eauto.py",
    "test_ha_export_preis_150.py",
    "test_ha_export_preis_morgen_n104.py",
    "test_ha_export_prognose_150.py",
    "test_ha_export_spez_ertrag_symmetrie.py",
    "test_ha_export_wp_ersparnis_sensor.py",
    "test_ha_export_wp_spezialtarif.py",
    "test_ha_export_yaml_rest.py",
    "test_ha_import_ohne_zaehlerwerte_n240.py",
    "test_ha_integrations_wissen.py",
    "test_ha_statistics_websocket_transport.py",
    "test_ha_verbindung_remote_erreicht_beide_dienste.py",
    "test_import_hauszaehler_349.py",
    "test_import_sensor_mapping_remap_353.py",
    "test_import_ueberschreiben_haken_349.py",
    "test_import_writer.py",
    "test_import_ziel_investition_349.py",
    "test_import_zuordnung_kwp.py",
    "test_invariante_komponenten_konsistenz.py",
    "test_investition_aktiv_filter.py",
    "test_investition_felder_leeren.py",
    "test_investition_kennwerte.py",
    "test_investition_response_kwp_effektiv.py",
    "test_investition_typ_reihenfolge.py",
    "test_komponenten_beitraege.py",
    "test_komponenten_dashboards_monats_fakten.py",
    "test_konformitaet_prognose_felder.py",
    "test_konformitaet_tz_felder.py",
    "test_live_history_kwh_scale.py",
    "test_live_komponenten_builder_emob.py",
    "test_live_pv_zaehler_f49.py",
    "test_live_tagesverlauf_farben_kanon.py",
    "test_live_tagesverlauf_short_term.py",
    "test_live_tagesverlauf_strompreis_carry_forward.py",
    "test_live_tageswerte_luecken.py",
    "test_live_wetter_grund.py",
    "test_live_wetter_verbrauchsprofil.py",
    "test_migrate_connector_field_inv_map.py",
    "test_migrate_pv_erzeugung_aggregat_clear.py",
    "test_migrate_sensor_mapping_strategien.py",
    "test_migrate_v3_33_0_lts_komponenten_kwh.py",
    "test_monats_co2_komposition.py",
    "test_monats_fakten_schicht.py",
    "test_monats_luecken_symmetrie.py",
    "test_monatsabschluss_connector_verteilt_label.py",
    "test_monatsabschluss_connector_zuordnung.py",
    "test_monatsabschluss_feld_dyn_tarif.py",
    "test_monatsabschluss_geprueft_gegen.py",
    "test_monatsabschluss_sonstige_loeschen.py",
    "test_monatsdaten_aggregiert_finanzen.py",
    "test_monatsdaten_tarif_aufloesung.py",
    "test_mqtt_broker_settings_b7_5.py",
    "test_mqtt_compute_deltas_pv_aggregation.py",
    "test_mqtt_discovery_entity_category.py",
    "test_mqtt_export_rundung_je_groessenart.py",
    "test_mqtt_export_toggle_b7_5b.py",
    "test_mqtt_hourly_eintraege.py",
    "test_mqtt_publish_consolidation_655.py",
    "test_mqtt_richtungen_migration_b7_5c.py",
    "test_netzbezug_arbeitspreis_kosten.py",
    "test_netzbezug_kosten.py",
    "test_pdf_jahresbericht_303.py",
    "test_pdf_jahresbericht_f43_waerme_nullen.py",
    "test_pdf_jahresbericht_module_monatswerte.py",
    "test_pdf_jahresbericht_pvgis_auswahl.py",
    "test_pdf_zip_export_121.py",
    "test_phev_anteil_331.py",
    "test_phev_vier_sichten_symmetrie.py",
    "test_prognose_discovery_sfml.py",
    "test_prognose_ertrag_tag.py",
    "test_prognose_kanon.py",
    "test_prognose_kanon_wettermodell_a30.py",
    "test_prognose_modellrand_f36.py",
    "test_prognose_snapshot_kanon_a29.py",
    "test_provenance.py",
    "test_provenance_migrate.py",
    "test_pv_anteil_ladung.py",
    "test_pv_monatswerte_service.py",
    "test_pv_spike_cap.py",
    "test_pv_strings_kwp_verteilung.py",
    "test_pv_strings_pvgis_auswahl.py",
    "test_pv_verteilung_helper.py",
    "test_pv_verteilung_provenance_352.py",
    "test_pvgis_ac_kappung_354_367.py",
    "test_pvgis_aktualitaet.py",
    "test_pvgis_prognose_plausibilitaet.py",
    "test_reparatur_lts_reichweite.py",
    "test_reparatur_werkbank_komponenten_korrektur.py",
    "test_roi_amortisation_jahr.py",
    "test_roi_bkw_hierarchie_381.py",
    "test_roi_dashboard_benzinpreis.py",
    "test_roi_dashboard_gruppierung.py",
    "test_roi_dashboard_sonstige_310.py",
    "test_roi_klimaanlage_nicht_bewertet.py",
    "test_roi_summe_symmetrie_f37.py",
    "test_scheduler_job_registrierung.py",
    "test_scheduler_mqtt_jobs_conditional.py",
    "test_scheduler_publish_takt.py",
    "test_snapshot_felder_sot_konformitaet.py",
    "test_soll_anschaffungsmonat_366.py",
    "test_soll_anteil_laufender_monat_n69.py",
    "test_sonstige_positionen_filter.py",
    "test_sonstige_readsite_symmetrie.py",
    "test_sonstiges_dashboard_laufzeit_308.py",
    "test_sonstiges_erzeuger_bilanz.py",
    "test_sonstiges_spalten_tag_und_monat.py",
    "test_source_marker.py",
    "test_source_priority.py",
    "test_speicher_dashboard_attribut_bug.py",
    "test_speicher_dyn_tarif_und_soc.py",
    "test_speicher_kanon_symmetrie.py",
    "test_speicher_kapazitaet_einheit_n235.py",
    "test_speicher_kopplung_351.py",
    "test_speicher_laedt_aus_netz.py",
    "test_speicher_netzladung_kanon_key.py",
    "test_speicher_simulation_bilanz.py",
    "test_speicher_sizing.py",
    "test_speicher_wirtschaftlichkeit_netzanteil.py",
    "test_speicher_zusatzpotential.py",
    "test_speicher_zyklen_kapazitaets_basis.py",
    "test_wp_aggregator_bugs.py",
    "test_wp_alter_wirkungsgrad.py",
    "test_wp_dashboard_betriebsstunden.py",
    "test_wp_klimaanlage_phase1.py",
    "test_wp_wirtschaftlichkeit.py",
    "test_wurzelmuster_konformitaet.py",
    "test_wurzelmuster_p1_orientierung.py",
    "test_wurzelmuster_p4_teilsumme.py",
    "test_wurzelmuster_p5_invariante.py",})


_HINWEIS = (
    "\n\nEine Testdatei, die zu einer Familie gehört, nennt im Modul-Docstring "
    "mindestens eine ihrer Schwestern — irgendeine existierende Testdatei außer "
    "sich selbst. Grund: Namens-Drift erzeugt Lücken aus beiden Suchrichtungen. "
    "`ha_statistics_service.py` galt einmal als „0 Tests\", weil die Suche "
    "`test_ha_statistics*` lautete und die Familie `test_ha_lts_*` heißt "
    "(Memory `feedback_testabdeckung_per_symbol_nicht_dateiname`).\n"
    "Ein Satz genügt, z. B.: „Schwesterdateien: test_ha_lts_mean_reader.py, "
    "test_ha_lts_minmax_reader.py.\" Der Verweis darf über den Präfix-Cluster "
    "hinausgehen — ein Symmetriepartner ist oft der nützlichere Hinweis."
)


def _bestand() -> tuple[dict[str, str], set[str]]:
    """`({Dateiname: Docstring}, {alle Dateinamen})` des Testbaums.

    Quelle ist `quellbaum.probenbaum()` — dieselbe eine Definition, die alle
    baumweiten Prüfer benutzen, seit neun handgeschriebene Kopien auseinander-
    gelaufen waren (zwei davon durchsuchten das virtualenv mit, N-321).
    """
    docs: dict[str, str] = {}
    for datei in probenbaum():
        name = datei.pfad.name
        if not name.startswith("test_"):
            continue
        docs[name] = ast.get_docstring(datei.baum) or ""
    return docs, set(docs)


def _ohne_schwester() -> list[str]:
    """Dateien in einem Cluster (≥2), deren Docstring keine echte Schwester nennt."""
    docs, vorhanden = _bestand()
    groesse = Counter(_cluster(n) for n in vorhanden)
    fehlt: list[str] = []
    for name, doc in sorted(docs.items()):
        if groesse[_cluster(name)] < 2:
            continue  # Einzelgänger hat keine Schwester — nichts zu nennen
        echte = [
            s for s in _NENNUNG.findall(doc) if s in vorhanden and s != name
        ]
        if not echte:
            fehlt.append(name)
    return fehlt


def test_neue_testdatei_nennt_ihre_schwestern():
    """Keine Datei außerhalb der Baseline steht ohne Schwesterverweis da.

    Der Wächter sagt bewusst NICHTS über die 275 bestehenden — er verhindert die
    276. Eine größere Zusage wäre unwahr, solange die 275 nicht abgearbeitet sind.
    """
    neu = sorted(set(_ohne_schwester()) - _BASELINE)

    assert not neu, (
        "Testdatei(en) in einer Familie ohne Schwesterverweis im Docstring:\n"
        + "\n".join(f"  {d}  (Cluster `{_cluster(d)}`)" for d in neu)
        + _HINWEIS
    )


def test_baseline_ist_nicht_zu_hoch():
    """Die Baseline schmilzt ab — ein erledigter Eintrag ist selbst ein Fehler.

    Wer einen Docstring um den Verweis ergänzt, streicht die Zeile hier. Sonst
    deckt der Eintrag später eine neue Lücke an derselben Stelle zu, und die
    Liste behauptet einen Rückstand, den es nicht mehr gibt.
    """
    offen = set(_ohne_schwester())
    erledigt = sorted(_BASELINE - offen)

    assert not erledigt, (
        "Baseline-Eintrag ohne Gegenstand — Zeile streichen:\n"
        + "\n".join(f"  {d}" for d in erledigt)
    )


def test_baseline_nennt_nur_existierende_dateien():
    """Kein Eintrag für eine Datei, die es nicht mehr gibt.

    Eine gelöschte oder umbenannte Datei würde sonst als Rückstand weitergezählt
    — und schlimmer: ihr Name könnte später für eine NEUE Datei wiederverwendet
    werden, die damit still freigestellt wäre.
    """
    _, vorhanden = _bestand()
    verwaist = sorted(_BASELINE - vorhanden)

    assert not verwaist, (
        "Baseline nennt Dateien, die es nicht (mehr) gibt:\n"
        + "\n".join(f"  {d}" for d in verwaist)
    )
