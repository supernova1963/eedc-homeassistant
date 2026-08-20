"""#377 / N-294 — Zählerstände unter *Sonstiges*: **erfasst, nicht bewertet**.

Diese Datei ist der Beleg für den einen Satz, an dem das ganze Vorhaben hängt:
**Ein Verbrauchszähler bewegt keine einzige Zahl in eedc.** Nicht die
Energiebilanz, nicht die Autarkie, nicht den ROI, nicht das CO₂, nicht den
Gemeinschaftsdatensatz, nicht die HA-Sensoren.

Das ist keine Behauptung, die man einmal prüft und dann glaubt — es ist eine
Invariante, die bei jedem Eingriff an *Sonstiges* neu brechen kann. Deshalb
stehen die Proben hier und nicht in einem Abnahmeprotokoll.

**Jede Probe hat ihre Gegenrichtung.** Ein Test, der nur zeigt „hier steht
nichts", ist auch dann grün, wenn die geprüfte Stelle gar nicht mehr existiert
(die Lehre aus N-259 und `feedback_beweis_familie`). Wo eine Abwesenheit geprüft
wird, prüft die Nachbarprobe, dass der Prüfer überhaupt etwas sehen *kann*.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen.energie import sonstiges_kwh_je_richtung
from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag
from backend.core.field_definitions import (
    INVESTITION_FELDER,
    SONSTIGES_ZAEHLER_KATEGORIEN,
    ZAEHLERSTAND_FELD,
    ZUSTAND_FELD_KEYS,
    _sonstiges_felder_ungepflegt,
    einheit_fuer,
    einheit_klasse,
    ist_zaehler_kategorie,
    kumulative_zaehler_felder_je_typ,
    sonstiges_feld_reihenfolge,
)
from backend.core.investition_parameter import ZAEHLER_ARTEN, ZAEHLER_EINHEITEN
from backend.services.snapshot.keys import (
    FLOAT_COUNTER_FELDER,
    KUMULATIVE_COUNTER_FELDER,
    _is_kumulativ_feld,
)


class _Inv:
    """Minimal-Investition — genau die Attribute, die die Layer lesen."""

    def __init__(self, typ="sonstiges", kategorie="zaehler", **params):
        self.typ = typ
        self.parameter = {"kategorie": kategorie, **params}


# ── Probe 1: die Feldreihenfolge ────────────────────────────────────────────


def test_p1_zaehler_hat_keine_energiefelder():
    """`sonstiges_feld_reihenfolge("zaehler")` ist leer.

    Ohne das liefe der Verbraucher-Fallback, und der Snapshot suchte am
    Gaszähler nach `verbrauch_sonstig_kwh` — die N-259-Klasse in der
    Gegenrichtung: nicht ein falscher Feldname, sondern ein Feld, das es an
    diesem Gerät gar nicht geben darf.
    """
    assert sonstiges_feld_reihenfolge("zaehler") == ()


def test_p1b_gegenprobe_andere_kategorien_liefern_weiter_felder():
    """Der Prüfer muss etwas sehen können.

    Ohne diese Probe wäre Probe 1 auch grün, wenn die Funktion **immer** leer
    zurückgäbe — und damit die Tageswerte jedes *Sonstiges*-Geräts abschaltete.
    """
    assert sonstiges_feld_reihenfolge("erzeuger") != ()
    assert sonstiges_feld_reihenfolge("verbraucher") != ()
    assert sonstiges_feld_reihenfolge(None) != ()


# ── Probe 2: die Zuordnungsfläche ───────────────────────────────────────────


def test_p2_ungepflegtes_geraet_bekommt_keinen_zaehlerstand():
    """Ein Gerät ohne gepflegte Kategorie wird als **Verbraucher** gelesen.

    Böte die Fläche ihm einen Zählerstand-Slot an, ordnete jemand dort einen
    Gassensor zu — und eedc läse ihn als Hausstrom. N-244 mit anderem
    Vorzeichen.
    """
    felder = {f["feld"] for f in _sonstiges_felder_ungepflegt()}
    assert ZAEHLERSTAND_FELD not in felder
    # Gegenrichtung: die Liste ist nicht einfach leer.
    assert "verbrauch_sonstig_kwh" in felder


# ── Probe 3: die Energie-Leckage ────────────────────────────────────────────


def test_p3_zaehlerstand_ist_kein_energiefeld():
    """Die eigentliche Sicherung: **die leere Einheit**.

    `kumulative_zaehler_felder_je_typ` filtert auf `einheit_klasse ==
    "energie"`. Ein einheitenloses Feld fällt dort **strukturell** heraus — es
    braucht keine Ausnahmeliste, an die jemand denken müsste.
    """
    assert ZAEHLERSTAND_FELD not in kumulative_zaehler_felder_je_typ()["sonstiges"]
    # …und der Grund dafür, namentlich (sonst wäre die Probe oben auch grün,
    # wenn das Feld gar nicht existierte):
    feld = INVESTITION_FELDER["sonstiges"]["zaehler"][0]
    assert feld["feld"] == ZAEHLERSTAND_FELD
    assert feld["einheit"] == "", (
        "Die leere Einheit IST die Sicherung - mit m3 oder kWh liefe der "
        "Zaehlerstand in die Energiebilanz."
    )
    assert einheit_klasse(feld["einheit"]) is None


def test_p3b_der_zaehler_wird_trotzdem_mitgeschrieben():
    """Die Gegenrichtung zu Probe 3 — sonst hieße „nicht Energie" schlicht
    „wird gar nicht erfasst", und die ganze Funktion wäre tot."""
    assert ZAEHLERSTAND_FELD in KUMULATIVE_COUNTER_FELDER["sonstiges"]
    assert _is_kumulativ_feld(ZAEHLERSTAND_FELD)


# ── Probe 4: keine Komponenten-Beiträge ─────────────────────────────────────


def test_p4_zaehler_erzeugt_keinen_komponenten_beitrag():
    """Ein Zähler-Gerät taucht in keiner Tages-Komponenten-Summe auf.

    Geprüft am Layer, der die Tagesebene faltet: eine `sonstige_<id>`-Zeile
    eines Zählers wird weder der Erzeugung noch dem Verbrauch zugeschlagen.
    ⚠ Der Fall ist **real**, obwohl neue Zähler gar keinen Eintrag mehr
    erzeugen: Wer ein bestehendes Verbrauchsgerät auf „Zähler" umstellt, hat
    die alten Einträge weiterhin in seinen Tageszeilen.
    """
    summen = sonstiges_kwh_je_richtung({"sonstige_7": 312.4}, {"7": "zaehler"})
    assert summen.erzeugung_kwh is None
    assert summen.verbrauch_kwh is None


def test_p4b_gegenprobe_ein_verbraucher_zaehlt_weiter():
    """Derselbe Wert, andere Kategorie — der Prüfer misst das richtige Objekt."""
    summen = sonstiges_kwh_je_richtung({"sonstige_7": 312.4}, {"7": "verbraucher"})
    assert summen.verbrauch_kwh == pytest.approx(312.4)


# ── Probe 5: keine Zahl im Monats-Aggregat ──────────────────────────────────


def test_p5_zaehler_bewegt_keine_zahl_im_monatsaggregat():
    """**Die Kernprobe.** Ein Zähler-Gerät trägt zu keiner Monatsgröße bei.

    Die `verbrauch_daten` unten sind der Umkategorisierungs-Fall: Sie tragen
    einen alten `verbrauch_sonstig_kwh`-Wert aus der Zeit, als das Gerät noch
    ein Verbraucher war. Ohne den ausdrücklichen Zweig liefe er weiter in
    Hausverbrauch und Autarkie — die Kategorie sagte „kein Strom", die Zahlen
    sagten etwas anderes.
    """
    daten = {
        "verbrauch_sonstig_kwh": 480.0,
        "erzeugung_kwh": 12.0,
        "bezug_netz_kwh": 400.0,
        ZAEHLERSTAND_FELD: 12345.6,
    }
    beitrag = imd_typ_beitrag(_Inv(), daten)
    assert beitrag.sonstiges_verbrauch == 0.0
    assert beitrag.sonstiges_erzeugung == 0.0
    assert beitrag.sonstiges_bezug_netz == 0.0
    assert beitrag.sonstiges_bezug_pv == 0.0
    assert beitrag.sonstiges_eigenverbrauch == 0.0
    assert beitrag.sonstiges_einspeisung == 0.0
    assert beitrag.sonstiges_einspeise_erloes_euro == 0.0


def test_p5b_gegenprobe_derselbe_datensatz_als_verbraucher():
    """Dieselben Daten, Kategorie `verbraucher` — jetzt zählen sie.

    Ohne diese Probe wäre Probe 5 auch grün, wenn `imd_typ_beitrag` für
    *Sonstiges* gar nichts mehr liefern würde.
    """
    daten = {"verbrauch_sonstig_kwh": 480.0, "bezug_netz_kwh": 400.0}
    beitrag = imd_typ_beitrag(_Inv(kategorie="verbraucher"), daten)
    assert beitrag.sonstiges_verbrauch == pytest.approx(480.0)
    assert beitrag.sonstiges_bezug_netz == pytest.approx(400.0)


# ── Probe 6: keine Serie im Energiefluss ────────────────────────────────────


def test_p6_zaehler_bekommt_keine_tagesverlauf_serie():
    """m³ auf einer kW-Achse gibt es nicht.

    Der Serienbau ist die SoT für **beide** Pfade (Live-Chart und Backfill,
    #318) — deshalb genügt diese eine Stelle.
    """
    from backend.services.live_sensor_config import baue_investitions_serien

    serien, _ = baue_investitions_serien(
        {"7": {"leistung_w": "sensor.gas"}},
        {"7": _Inv()},
    )
    assert serien == []


def test_p6b_gegenprobe_ein_verbraucher_bekommt_seine_serie():
    from backend.services.live_sensor_config import baue_investitions_serien

    serien, _ = baue_investitions_serien(
        {"7": {"leistung_w": "sensor.pool"}},
        {"7": _Inv(kategorie="verbraucher")},
    )
    assert [s.inv_id for s in serien] == ["7"]


# ── Probe 7: nicht im Gemeinschaftsdatensatz, nicht im HA-Export ────────────


def test_p7_zaehlerstand_verlaesst_die_anlage_nicht():
    """Weder Community-Payload noch HA-Sensor-Export kennen das Feld.

    Beides sind Wege **nach draußen**: der eine in einen fremden Datensatz, der
    andere zurück nach Home Assistant — und der Wert kam von dort. Ein
    Abwesenheits-Grep über die zwei Dateien, mit Gegenprobe darunter.
    """
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1]
    for pfad in ("services/community_service.py", "api/routes/ha_export.py"):
        text = (wurzel / pfad).read_text(encoding="utf-8")
        assert ZAEHLERSTAND_FELD not in text, (
            f"{pfad} nennt den Zählerstand — er gehört in keinen Weg nach außen."
        )


def test_p7b_gegenprobe_der_grep_findet_ueberhaupt_etwas():
    """Der Prüfer oben muss sehen können.

    Ein Abwesenheits-Grep über eine Datei, die es nicht gibt oder die leer ist,
    ist immer grün ([[feedback_beweis_familie]]).
    """
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1]
    for pfad, muss_enthalten in (
        ("services/community_service.py", "sonstiges_verbrauch_kwh"),
        ("api/routes/ha_export.py", "INVESTITION_SENSOREN"),
    ):
        text = (wurzel / pfad).read_text(encoding="utf-8")
        assert muss_enthalten in text, f"{pfad}: der Grep misst das falsche Objekt"


# ── Probe 8: Float bleibt Float ─────────────────────────────────────────────


def test_p8_zaehlerstand_wird_nicht_ganzzahlig_gerundet():
    """312,4 Liter dürfen nicht zu 312 werden.

    Bei einem Anzahl-Zähler (Starts) ist die Rundung richtig, hier ist sie ein
    Messfehler — über einen Monat gingen an den Rändern bis zu zwei ganze
    Einheiten verloren.
    """
    assert ZAEHLERSTAND_FELD in FLOAT_COUNTER_FELDER


def test_p8b_gegenprobe_ein_anzahlzaehler_bleibt_ganzzahlig():
    assert "wp_starts_anzahl" not in FLOAT_COUNTER_FELDER


# ── Probe 10: der numerische Pfad bleibt ────────────────────────────────────


def test_p10_zaehlerstand_ist_kein_zustandsfeld():
    """`zustand: True` NICHT mitbenutzen (#263 K-2 sagt es selbst).

    Ein Zählerstand ist eine **Zahl** und braucht genau den numerischen Live-/
    MQTT-Pfad, den die Zustands-Weiche abschaltet. Dasselbe *Muster* wie beim
    Betriebsmodus (Eigenschaft am Feld, ein Leser), nicht dieselbe *Menge*.
    """
    assert ZAEHLERSTAND_FELD not in ZUSTAND_FELD_KEYS
    assert INVESTITION_FELDER["sonstiges"]["zaehler"][0].get("zustand") is not True


# ── Die Einheit hängt am Gerät (S5) ─────────────────────────────────────────


def test_einheit_kommt_vom_geraet_nicht_vom_feld():
    """Der eine Leser (S5) — und was er leistet."""
    assert einheit_fuer(ZAEHLERSTAND_FELD, _Inv(zaehler_einheit="l")) == "l"
    # Ohne gepflegte Einheit gilt der Registry-Default, nicht "".
    assert einheit_fuer(ZAEHLERSTAND_FELD, _Inv()) == "m³"
    # Ein normales Feld bleibt bei seiner Feld-Einheit.
    assert einheit_fuer("pv_erzeugung_kwh", _Inv(zaehler_einheit="l")) == "kWh"


def test_die_auswahlwerte_sind_die_erwarteten():
    """Auswahl-Listen als Vertrag — Frontend und Backend müssen dasselbe kennen."""
    assert "gas" in ZAEHLER_ARTEN and "wasser" in ZAEHLER_ARTEN
    assert "m³" in ZAEHLER_EINHEITEN and "l" in ZAEHLER_EINHEITEN


# ── Der dritte Zustand als solcher ──────────────────────────────────────────


def test_die_kategorie_ist_weder_erzeuger_noch_verbraucher():
    """Der Kern von #377 in einer Zeile."""
    assert ist_zaehler_kategorie("zaehler")
    assert not ist_zaehler_kategorie("verbraucher")
    assert not ist_zaehler_kategorie("erzeuger")
    assert not ist_zaehler_kategorie(None)
    assert "zaehler" in SONSTIGES_ZAEHLER_KATEGORIEN


def test_jede_zaehler_kategorie_hat_ein_feld_in_der_registry():
    """Deckungsprüfung: die Konstante und die Registry beschreiben dasselbe.

    Ohne sie könnte jemand eine zweite Zähler-Kategorie in
    `SONSTIGES_ZAEHLER_KATEGORIEN` eintragen, für die es gar keine Felder gibt —
    sie wäre überall ausgenommen und nirgends erfassbar.
    """
    for kat in SONSTIGES_ZAEHLER_KATEGORIEN:
        assert kat in INVESTITION_FELDER["sonstiges"], (
            f"Kategorie {kat} ist ausgenommen, hat aber keine Feld-Definition."
        )
        assert INVESTITION_FELDER["sonstiges"][kat], f"`{kat}` hat keine Felder"


# ── Probe 9: der Zählerwechsel ──────────────────────────────────────────────
#
# Sie braucht eine Datenbank und steht deshalb in
# `test_377_zaehlerwechsel.py` — die Fenster-Arithmetik ist ohne echte
# Snapshot-Zeilen nicht ehrlich prüfbar
# ([[feedback_probe_unerreichbarer_zustand]]).


def test_stilllegungsdatum_ist_die_grenze_nicht_aktiv_false():
    """Der Fallstrick aus §4 des Konzepts, als Probe statt als Fußnote.

    `aktiv=False` heißt laut Modell „wie gelöscht: nirgends anzeigen, **auch
    nicht historisch**". Wer den alten Zähler deaktiviert statt stillzulegen,
    löscht seine Ablesungen aus jeder Sicht — die Historie ist weg, obwohl sie
    gemessen wurde.
    """
    from backend.models.investition import Investition

    alt = Investition(
        typ="sonstiges", bezeichnung="Gaszähler alt",
        anschaffungsdatum=date(2020, 1, 1), stilllegungsdatum=date(2026, 3, 15),
    )
    # Stillgelegt: in der Vergangenheit sichtbar …
    assert alt.ist_aktiv_im_zeitraum(date(2025, 1, 1), date(2025, 12, 31))
    # … und ab dem Folgetag nicht mehr.
    assert not alt.ist_aktiv_im_zeitraum(date(2026, 4, 1), date(2026, 4, 30))

    deaktiviert = Investition(
        typ="sonstiges", bezeichnung="Gaszähler alt",
        anschaffungsdatum=date(2020, 1, 1), aktiv=False,
    )
    assert not deaktiviert.ist_aktiv_im_zeitraum(date(2025, 1, 1), date(2025, 12, 31)), (
        "aktiv=False löscht die Historie — genau der Fallstrick aus §4."
    )
