"""Die Schreib-Hierarchie der Aggregat-Tabellen — bis E6 ohne Test (M9).

``core/source_priority.py`` entscheidet, welcher Schreiber einen vorhandenen
Wert überschreiben darf. Das Modul stand in keiner Testdatei (AST-Messung
2026-08-24: 0 Importe im Testbaum) — die vorhandenen Präzedenz-Tests prüfen
``services/provenance.py`` und erreichen die Hierarchie nur mittelbar.

Drei Dinge werden hier festgehalten:

1. **Die Ordnung selbst** — niedrigere Zahl gewinnt, und in welcher Reihenfolge.
2. **Die Zuordnung der Labels zu ihrer Klasse** — ein Label, das die Klasse
   wechselt, ändert stillschweigend, wer wen überschreibt.
3. **Die abgeschlossene Vokabular-Menge** als Baseline. Ihr Docstring sagt:
   *„neue Schreib-Pfade müssen ihr Source-Label hier eintragen, sonst weist der
   Helper sie ab."* Ein neues Label ist damit eine bewusste Entscheidung — und
   diese Probe macht sie sichtbar, statt sie im Vorbeigehen zuzulassen.
"""

import pytest

from backend.core.source_priority import (
    SOURCE_LABELS,
    SourcePriority,
    get_priority,
)


class TestOrdnung:
    """Niedrigere Zahl = höhere Priorität."""

    def test_die_sechs_stufen_stehen_in_dieser_reihenfolge(self):
        assert [int(s) for s in SourcePriority] == [0, 1, 2, 3, 4, 5]
        assert [s.name for s in SourcePriority] == [
            "REPAIR",
            "MANUAL",
            "EXTERNAL_AUTHORITATIVE",
            "AUTO_AGGREGATION",
            "FALLBACK",
            "LEGACY",
        ]

    def test_repair_steht_ueber_allem(self):
        assert all(
            SourcePriority.REPAIR < s
            for s in SourcePriority
            if s is not SourcePriority.REPAIR
        )

    def test_manuell_schlaegt_jede_maschine(self):
        """User-Eingabe wird niemals von einer Maschine überschrieben."""
        maschinell = [
            SourcePriority.EXTERNAL_AUTHORITATIVE,
            SourcePriority.AUTO_AGGREGATION,
            SourcePriority.FALLBACK,
            SourcePriority.LEGACY,
        ]
        assert all(SourcePriority.MANUAL < s for s in maschinell)

    def test_legacy_verliert_gegen_jeden_bewussten_schreiber(self):
        assert all(
            s < SourcePriority.LEGACY
            for s in SourcePriority
            if s is not SourcePriority.LEGACY
        )

    def test_vergleich_ist_numerisch_moeglich(self):
        """`IntEnum`, damit `<` im Schreib-Pfad direkt trägt."""
        assert SourcePriority.MANUAL < SourcePriority.FALLBACK
        assert SourcePriority.MANUAL == 1


class TestLabelZuordnung:
    """Ein Label, das die Klasse wechselt, verschiebt die Schreib-Rechte."""

    @pytest.mark.parametrize(
        "label,erwartet",
        [
            ("repair", SourcePriority.REPAIR),
            ("manual:form", SourcePriority.MANUAL),
            ("manual:csv_import", SourcePriority.MANUAL),
            # Backup-Restore ist ein expliziter User-Klick ⇒ MANUAL-Klasse
            ("manual:csv_backup", SourcePriority.MANUAL),
            ("manual:json_backup", SourcePriority.MANUAL),
            ("external:ha_statistics", SourcePriority.EXTERNAL_AUTHORITATIVE),
            ("external:cloud_import:solaredge", SourcePriority.EXTERNAL_AUTHORITATIVE),
            ("external:fuel_price", SourcePriority.EXTERNAL_AUTHORITATIVE),
            ("auto:monatsabschluss", SourcePriority.AUTO_AGGREGATION),
            ("auto:demo_data", SourcePriority.AUTO_AGGREGATION),
            ("auto:preserve_restore", SourcePriority.AUTO_AGGREGATION),
            ("fallback:sensor_snapshot", SourcePriority.FALLBACK),
            ("legacy:unknown", SourcePriority.LEGACY),
        ],
    )
    def test_get_priority_liefert_die_erwartete_klasse(self, label, erwartet):
        assert get_priority(label) is erwartet

    def test_demo_daten_verlieren_gegen_spaetere_handeingabe(self):
        """Der Docstring verspricht genau das — hier steht es als Probe."""
        assert get_priority("manual:form") < get_priority("auto:demo_data")

    def test_ein_echter_externer_schreiber_schlaegt_preserve_restore(self):
        assert get_priority("external:fuel_price") < get_priority(
            "auto:preserve_restore"
        )


class TestUnbekanntesLabel:
    """Keine stille Akzeptanz — das ist der Zweck des abgeschlossenen Vokabulars."""

    def test_unbekanntes_label_wirft_key_error(self):
        with pytest.raises(KeyError):
            get_priority("external:irgendwas_neues")

    def test_auch_die_leere_zeichenkette_wirft(self):
        with pytest.raises(KeyError):
            get_priority("")

    def test_gross_klein_wird_nicht_normalisiert(self):
        with pytest.raises(KeyError):
            get_priority("MANUAL:FORM")


class TestVokabularBaseline:
    """Das Vokabular ist abgeschlossen — eine Erweiterung ist eine Entscheidung.

    ⚠ Wer ein Label ergänzt, trägt es hier ein **und** entscheidet dabei
    bewusst über seine Klasse. Diese Probe ist der Ort, an dem das auffällt.
    """

    #: Stand 2026-08-24, aus dem Modul erhoben.
    ERWARTET = {
        "repair": 0,
        "manual:form": 1,
        "manual:csv_import": 1,
        "manual:csv_backup": 1,
        "manual:json_backup": 1,
        "external:ha_statistics": 2,
        "external:ha_statistics:daily": 2,
        "external:ha_statistics:hourly": 2,
        "external:portal_import": 2,
        "external:openmeteo": 2,
        "external:solcast": 2,
        "external:fuel_price": 2,
        "external:tom_ha_sfml": 2,
        "external:cloud_import:anker_solix": 2,
        "external:cloud_import:deye_solarman": 2,
        "external:cloud_import:ecoflow_powerocean": 2,
        "external:cloud_import:ecoflow_powerstream": 2,
        "external:cloud_import:fronius_solarweb": 2,
        "external:cloud_import:growatt": 2,
        "external:cloud_import:hoymiles_smiles": 2,
        "external:cloud_import:huawei_fusionsolar": 2,
        "external:cloud_import:solaredge": 2,
        "external:cloud_import:sungrow_isolarcloud": 2,
        "external:cloud_import:viessmann_gridbox": 2,
        "auto:monatsabschluss": 3,
        "auto:preserve_restore": 3,
        "auto:demo_data": 3,
        "fallback:sensor_snapshot": 4,
        "fallback:mqtt_inbound": 4,
        "legacy:unknown": 5,
    }

    def test_kein_label_ist_verschwunden(self):
        fehlend = sorted(set(self.ERWARTET) - set(SOURCE_LABELS))
        assert not fehlend, (
            f"{len(fehlend)} Label(s) aus dem Vokabular entfernt: {fehlend}. "
            "Schreib-Pfade, die sie benutzen, laufen ab jetzt in einen KeyError."
        )

    def test_kein_label_ist_unbemerkt_dazugekommen(self):
        neu = sorted(set(SOURCE_LABELS) - set(self.ERWARTET))
        assert not neu, (
            f"{len(neu)} neue(s) Label: {neu}. Das ist erlaubt — trag sie hier "
            "mit ihrer Klasse ein und entscheide dabei bewusst, wen sie "
            "ueberschreiben duerfen."
        )

    def test_keine_klasse_hat_sich_verschoben(self):
        verschoben = {
            label: (stufe, int(SOURCE_LABELS[label]))
            for label, stufe in self.ERWARTET.items()
            if label in SOURCE_LABELS and int(SOURCE_LABELS[label]) != stufe
        }
        assert not verschoben, (
            f"Klassenwechsel (erwartet, ist): {verschoben}. Das aendert, wer "
            "wen ueberschreiben darf — nie im Vorbeigehen."
        )
