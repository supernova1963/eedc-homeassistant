"""N-340 — die Aufteilung braucht **eine** Modus-Quelle je Gerät.

## Der Fehler, den diese Datei festhält

Der Aggregationspfad las den Feld-Key **nackt** (`live["betriebsmodus"]`) — als
einzige der vier Lesestellen; Live, Daten-Checker und Snapshot-Keys lösen den
Innengeräte-Suffix (`betriebsmodus-3`) längst über `basis_feld_key` auf. Folge:
Wer den Modus je Innengerät zuordnete, bekam **keine Aufteilung**, während der
Daten-Checker „zugeordnet" meldete. Eine Zuordnung ohne Wirkung, ohne Hinweis.

## Und die zweite Hälfte, ohne die der Fix gefährlich wäre

Löst man nur den Suffix auf, können plötzlich **mehrere** Entitäten an einem
Gerät hängen — und beide Lesestellen schrieben `ergebnis[inv_id] = modus`,
also **letzte gewinnt**, nach Einfüge-Reihenfolge des Mappings. Aus einem
stillen Nichts wäre ein stiller Zufall geworden. Deshalb steht die Regel in
`core.betriebsmodus.modus_quelle` und gilt für beide Pfade.

Schwesterdateien: `test_263_k2_betriebsmodus_lesen_mitschreiben.py` (dieselbe Regel
am **Aggregationspfad** — hier steht sie nur als Funktion) und
`test_daten_checker_modus_quelle_mehrdeutig.py` (die **Auskunft** an den Anwender).
"""

from __future__ import annotations

from backend.core.betriebsmodus import modus_quelle


class TestModusQuelle:
    """Die Regel selbst — jeder Zweig einzeln."""

    def test_ohne_zuordnung_keine_quelle(self):
        assert modus_quelle({}) is None
        assert modus_quelle(None) is None

    def test_nackter_key_ist_eine_quelle(self):
        """Der Bestandsfall: ein Gerät ohne Innengeräte-Liste."""
        assert modus_quelle({"betriebsmodus": "climate.a"}) == "climate.a"

    def test_innengeraete_suffix_wird_aufgeloest(self):
        """Der eigentliche Fund: `betriebsmodus-3` lieferte vorher NICHTS."""
        assert modus_quelle({"betriebsmodus-3": "climate.a"}) == "climate.a"

    def test_mehrere_innengeraete_auf_derselben_entitaet_sind_EINE_quelle(self):
        """Konzept D3: Der Modus gehört dem Außengerät.

        Das ist der ausdrücklich erlaubte Normalfall — wer alle Innengeräte auf
        dieselbe `climate`-Entität legt, muss seine Aufteilung behalten.
        """
        assert modus_quelle({
            "betriebsmodus-3": "climate.a",
            "betriebsmodus-4": "climate.a",
            "betriebsmodus-5": "climate.a",
        }) == "climate.a"

    def test_verschiedene_entitaeten_ergeben_KEINE_quelle(self):
        """ADR-002/P4: eedc würfelt keinen Anlagen-Modus aus N Innengeräten."""
        assert modus_quelle({
            "betriebsmodus-3": "climate.a",
            "betriebsmodus-4": "climate.b",
        }) is None

    def test_fremde_felder_zaehlen_nicht(self):
        """Sonst hinge die Aufteilung an einem Leistungssensor."""
        assert modus_quelle({"leistung_w-3": "sensor.x"}) is None

    def test_leere_zuordnung_ist_keine_zuordnung(self):
        """„keine" bzw. leer ist eine Absage, kein Sensor."""
        assert modus_quelle({"betriebsmodus-3": "", "betriebsmodus-4": None}) is None

    def test_eine_echte_neben_einer_leeren_bleibt_eindeutig(self):
        """Sonst entwertete ein leeres Feld eine vorhandene Quelle (K3)."""
        assert modus_quelle({
            "betriebsmodus-3": "climate.a",
            "betriebsmodus-4": None,
        }) == "climate.a"
