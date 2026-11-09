"""Wächter «Übersicht der Größen» (Bauplan «Übersicht der Größen» §3, Stufe U1, 7.11.2026).

``docs/UEBERSICHT-GROESSEN.md`` ist **erzeugt** (``groessen_uebersicht.py``): jeder Eintrag der vier Registries —
Eingabefeld, Monatsgröße, Kennwert der Tabelle, HA-Export-Sensor — hat genau eine Zeile. Zwei Spalten weiß der Code
nicht (Regel-Abschnitt, haltender Test); sie stehen in ``groessen_hand.yaml``. Dieser Wächter hält beides an den Code:

(a) jede Monatsgröße, jeder Kennwert, jeder Sensor hat einen Hand-Eintrag mit ``abschnitt`` **oder** steht in
    ``groessen_offen_baseline.txt`` — einer Liste, die nur schrumpft (Muster ``test_routen_baseline.py``: eine Liste,
    keine Zahl; der Diff sagt, welche Größe dazukam). Eingabefelder brauchen keinen Hand-Eintrag (alle Spalten kommen
    aus Registry und Kanal-Katalog).
(b) jeder ``code_ort`` und jeder ``test`` existiert, jeder ``abschnitt`` ist der Anker einer Überschrift.
(c) die erzeugte Datei ist gleich der Erzeuger-Ausgabe — **skip ohne** ``docs/`` (Standalone-Spiegel, Muster
    ``test_soll_waerme_klima_achse3_aufloesung.py``).
(d) Anker-Probe: jeder Verweis ``BERECHNUNGEN.md#…``/``SENSOR-REFERENZ.md#…``/``MQTT_INBOUND.md#…`` in ``docs/*.md``,
    den Bausteinen und ``CHANGELOG.md``
    trifft eine Überschrift. Der Website-Build prüft keine Anker — das tut nur diese Probe (U0: zwei waren tot).
(e) Gegenproben: ein künstlicher Registry-Eintrag ohne Hand-Eintrag, ein falscher Verweis, ein toter Anker werden
    beim Namen gemeldet — sonst wäre ein grüner Lauf nichts wert (Muster ``test_kanal_feld_deckung.py``).

**SENSOR-REFERENZ (Stufe U3).** ``docs/SENSOR-REFERENZ.md`` ist ebenfalls erzeugt: Hand-Bausteine
``docs/sensor-referenz/NN-*.md`` (Prosa, Überschriften ⇒ Anker) und an Markern die Tabellen der Eingabefelder (Registry,
Kanal-Katalog, Sichten aus ``core/feld_auswertungen.py``) und der Export-Sensoren (Definitionen + ``hinweis`` der
Hand-Datei). (c) prüft beide Dateien, (d) liest auch die Bausteine; die Totalität (jede Eingabefeld-Zeile und jeder
Sensor in genau einem Marker, jede Kategorie in genau einem Unterabschnitt) prüft der Erzeuger selbst — die
Gegenproben unten zeigen, dass er dabei den Namen nennt.

**MQTT_INBOUND (Stufe U3b).** ``docs/MQTT_INBOUND.md`` ist erzeugt: Bausteine ``docs/mqtt-inbound/NN-*.md`` und an Markern je
Gerätetyp eine Tabelle der Energie- und eine der Live-Topics (jeder Registry-Eintrag außer ``SKIP_TYPEN`` genau einmal,
auch ohne Topic) sowie die Preset-Tabelle. (c) prüft auch diese Datei; der Erzeuger prüft Totalität je Marker und das
**Sollbild** gegen ``build_expected_topics`` in beiden Richtungen. Die Spalte «Payload» der Energie-Topics fragt die Leser
(``mq_energie_leser``). Ein Geräte-Energiefeld ohne Leser hat seit N-780 (Päckchen U) kein Topic mehr — die Zelle sagt
«kein MQTT-Topic — Monatsabschluss (Hand oder HA-Sensor)» bzw. «(Hand)», am Flag ``ohne_leser`` der Topic-Registry.

**Die Slug-Regeln** (github-slugger, ein Slugger je Dokument; Überschriften in Blockquotes und Setext zählen) sind am
7.11.2026 gegen die Pipeline der In-App-Hilfe gemessen (remark-gfm + rehype-raw + rehype-slug wie
``components/ui/MarkdownDoc.tsx``): 3164 Überschriften in 39 Dateien, alle Anker gleich.

**Wenn dieser Test rot wird:**

    scripts/groessen-uebersicht.sh              # UEBERSICHT-GROESSEN.md, SENSOR-REFERENZ.md, MQTT_INBOUND.md neu
    scripts/groessen-uebersicht.sh --baseline   # nach einem Hand-Eintrag: Baseline schrumpfen lassen
    ./scripts/sync-help.sh                      # In-App-Hilfe nachziehen

Eine neue Größe ohne Regel-Abschnitt ist kein Baseline-Fall: Hand-Eintrag mit ``abschnitt`` in ``groessen_hand.yaml``.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pytest

from backend.tests import groessen_uebersicht as gu

_MIT_DOCS = gu.DOCS.exists()
_OHNE_DOCS = pytest.mark.skipif(not _MIT_DOCS, reason="docs/ liegt nur im Source-of-Truth-Repo")

_BEFEHLE = (f"\n\nNeu erzeugen: {gu.BEFEHL} · Baseline: {gu.BEFEHL_BASELINE} · danach ./scripts/sync-help.sh "
            "(Anleitung im Modul-Docstring).")


@pytest.fixture(scope="module")
def zeilen():
    return gu.alle_zeilen()


@pytest.fixture(scope="module")
def hand():
    return gu.hand_lesen()


@pytest.fixture(scope="module")
def anker():
    return gu.anker_aller_zieldateien()


# ── Prüfmenge nicht leer (N-318-Klasse) ─────────────────────────────────────


def test_jede_ebene_hat_zeilen(zeilen):
    """Ein Parser, der nichts findet, meldet grün ohne zu messen — deshalb eine Untergrenze je Ebene (Stand 7.11.:
    106 · 104 · 76 · 86)."""
    zu_wenig = {e: len(z) for e, z in zeilen.items() if len(z) < 50}
    assert not zu_wenig, f"Ebene(n) mit weniger als 50 Zeilen: {zu_wenig} — liest der Parser die Quelle noch?"


def test_zeilen_identitaet_ist_eindeutig_je_ebene(zeilen):
    """Außer den `sonstiges`-Arten (dieselbe Identität ``<typ>:<feld>`` wie ``FELD_BEDARF``) ist jede Zeile eindeutig."""
    for ebene, liste in zeilen.items():
        schluessel = [z.schluessel for z in liste if not (ebene == gu.EINGABEFELD and z.schluessel.startswith("sonstiges:"))]
        doppelt = sorted({s for s in schluessel if schluessel.count(s) > 1})
        assert not doppelt, f"{ebene}: doppelte Zeilen-Identität {doppelt}"


# ── (a) Hand-Eintrag mit abschnitt oder Baseline ────────────────────────────


def test_a_jede_groesse_hat_abschnitt_oder_steht_in_der_baseline(zeilen, hand):
    neu = sorted(set(gu.offene_schluessel(hand, zeilen)) - set(gu.baseline_lesen()))
    assert not neu, (
        f"{len(neu)} Größe(n) ohne Regel-Abschnitt, die nicht in groessen_offen_baseline.txt stehen:\n  "
        + "\n  ".join(neu)
        + "\n\nNeue Größe? Hand-Eintrag mit `abschnitt` (Überschrift in BERECHNUNGEN.md oder SENSOR-REFERENZ.md) in "
          "eedc/backend/tests/groessen_hand.yaml — die Baseline wächst nicht." + _BEFEHLE
    )


def test_a_baseline_schrumpft_nur(zeilen, hand):
    """Die Baseline ist eine Behauptung (Muster ``test_kognitive_komplexitaet.py``): eine Zeile, die einen Abschnitt
    bekommen hat oder deren Größe es nicht mehr gibt, muss heraus — so sinkt die Zahl sichtbar im Commit."""
    veraltet = sorted(set(gu.baseline_lesen()) - set(gu.offene_schluessel(hand, zeilen)))
    assert not veraltet, (
        f"{len(veraltet)} Baseline-Zeile(n) ohne Bedarf (Abschnitt eingetragen oder Größe entfallen):\n  "
        + "\n  ".join(veraltet) + _BEFEHLE
    )


def test_a_baseline_ist_sortiert_ohne_doppel_und_nennt_den_befehl():
    zeilen_ = gu.baseline_lesen()
    assert zeilen_ == sorted(set(zeilen_)), "groessen_offen_baseline.txt unsortiert oder mit Doppeln" + _BEFEHLE
    assert gu.BEFEHL_BASELINE in gu.BASELINE.read_text(encoding="utf-8"), "Kopf der Baseline nennt den Befehl nicht"


# ── (b) Hand-Datei: Form und Verweise ───────────────────────────────────────


def test_b_hand_datei_ist_gueltig(zeilen, hand):
    fehler = gu.hand_formfehler(hand, zeilen)
    assert not fehler, "groessen_hand.yaml:\n  " + "\n  ".join(fehler) + _BEFEHLE


def test_b_jeder_verweis_der_hand_datei_existiert(hand, anker):
    fehler = gu.hand_verweisfehler(hand, anker, mit_docs=_MIT_DOCS)
    assert not fehler, "groessen_hand.yaml verweist ins Leere:\n  " + "\n  ".join(fehler) + _BEFEHLE


# ── (c) erzeugte Datei == Erzeuger-Ausgabe ──────────────────────────────────


@_OHNE_DOCS
def test_c_erzeugte_datei_ist_aktuell():
    soll = gu.erzeugen()
    ist = gu.ZIEL.read_text(encoding="utf-8") if gu.ZIEL.exists() else ""
    assert ist == soll, (
        "docs/UEBERSICHT-GROESSEN.md weicht von der Erzeuger-Ausgabe ab — Registry, Monats-Fakten, Werte-Registry, "
        "Export-Sensoren oder groessen_hand.yaml geändert, ohne neu zu erzeugen (oder die Datei von Hand geändert)."
        + _BEFEHLE
    )


@_OHNE_DOCS
def test_c_sensor_referenz_ist_aktuell():
    fehler, soll = gu.sr_pruefung_und_text()
    assert not fehler, "SENSOR-REFERENZ nicht erzeugbar:\n  " + "\n  ".join(fehler) + _BEFEHLE
    ist = gu.SR_ZIEL.read_text(encoding="utf-8") if gu.SR_ZIEL.exists() else ""
    assert ist == soll, (
        "docs/SENSOR-REFERENZ.md weicht von der Erzeuger-Ausgabe ab — ein Baustein in docs/sensor-referenz/, die "
        "Feld-Registry, der Kanal-Katalog, core/feld_auswertungen.py, die Export-Sensoren oder groessen_hand.yaml "
        "geändert, ohne neu zu erzeugen (oder die Datei von Hand geändert — Änderungen gehören in die Bausteine)."
        + _BEFEHLE
    )


# ── (d) Anker-Probe ─────────────────────────────────────────────────────────


@_OHNE_DOCS
def test_d_jeder_anker_verweis_trifft_eine_ueberschrift(anker):
    verweise = gu.anker_verweise(gu.verweis_dateien())
    assert len(verweise) >= 30, f"nur {len(verweise)} Verweise gefunden — liest die Probe noch die Dateien?"
    tot = gu.tote_anker(verweise, anker)
    assert not tot, (
        f"{len(tot)} Verweis(e) auf einen Anker ohne Überschrift:\n  " + "\n  ".join(tot)
        + "\n\nAnker = github-slugger der Überschrift (gu.slug(gu.ueberschrift_text(…))); Überschrift umbenannt? "
          "Dann den Verweis nachziehen — der Website-Build merkt es nicht."
    )


# ── Slug-Regeln (gemessen gegen rehype-slug, 7.11.2026) ─────────────────────


@pytest.mark.parametrize("ueberschrift, anker_", [
    ("### 4.1c Prognose-Vergleich (Auswertungen → Prognose)", "41c-prognose-vergleich-auswertungen--prognose"),
    ("### Backward-Slot-Konvention (ab v3.20.0, #144)", "backward-slot-konvention-ab-v3200-144"),
    ("> #### Mit eigenem Wärmepumpen-Tarif — Netzbezug zum WP-Tarif oder Grenze (N-767, N-770)",
     "mit-eigenem-wärmepumpen-tarif--netzbezug-zum-wp-tarif-oder-grenze-n-767-n-770"),
    ("### Was ein `binary_sensor` in eedc ist — und was er nicht kann",
     "was-ein-binary_sensor-in-eedc-ist--und-was-er-nicht-kann"),
    ("> ## ⭐ Dieses Dokument ist **Kapitel 8** von [`KONZEPT-WAERME-KLIMA.md`](KONZEPT-WAERME-KLIMA.md) (13.09.2026)",
     "-dieses-dokument-ist-kapitel-8-von-konzept-waerme-klimamd-13092026"),
])
def test_slug_wie_rehype_slug(ueberschrift, anker_):
    assert [s for _t, s in gu.ueberschriften(ueberschrift)] == [anker_]


def test_slug_doppel_setext_und_codezaun():
    md = "# A\n\n## A\n\nAbsatz\n---\n\n```\n# kein Titel\n```\n\n- Liste\n---\n"
    assert [s for _t, s in gu.ueberschriften(md)] == ["a", "a-1", "absatz"]


# ── (e) Gegenproben ─────────────────────────────────────────────────────────


def _neu_ohne_abschnitt(zeilen_) -> set[str]:
    """Wie Wächter (a): echte Hand-Datei, echte Baseline."""
    return set(gu.offene_schluessel(gu.hand_lesen(), zeilen_)) - set(gu.baseline_lesen())


def test_e_kuenstlicher_sensor_wird_beim_namen_gemeldet(monkeypatch):
    from backend.services.ha_sensors_export import SensorDefinition, SensorCategory

    echte = gu.sensor_definitionen()
    kuenstlich = SensorDefinition(key="kuenstlich_u1_kwh", name="Künstlich", unit="kWh", icon="mdi:test",
                                  category=SensorCategory.ENERGIE, formel="Gegenprobe")
    monkeypatch.setattr(gu, "sensor_definitionen", lambda: [*echte, kuenstlich])
    assert _neu_ohne_abschnitt(gu.alle_zeilen()) == {"sensor:kuenstlich_u1_kwh"}


@dataclass(frozen=True)
class KuenstlicheFakten:
    neu_kwh: float = 0.0
    schalter: bool = False


def test_e_kuenstliche_monatsgroesse_wird_beim_namen_gemeldet(monkeypatch):
    echte = gu.fakten_klassen()
    monkeypatch.setattr(gu, "fakten_klassen", lambda: [*echte, KuenstlicheFakten])
    neu = _neu_ohne_abschnitt(gu.alle_zeilen())
    assert neu == {"monatsgroesse:KuenstlicheFakten.neu_kwh"}, "bool ist keine Zeile, float schon"


def test_e_kuenstlicher_kennwert_wird_beim_namen_gemeldet(monkeypatch, tmp_path):
    ts = gu.WERTE_REGISTRY_TS.read_text(encoding="utf-8")
    anfang = "export const WERTE_METRIKEN: WerteMetrik[] = [\n"
    zeile = ("  { key: 'kuenstlich_u1', label: 'Künstlich', unit: 'kWh', gruppe: 'basis', decimals: 0, "
             "aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },\n")
    datei = tmp_path / "registry.ts"
    datei.write_text(ts.replace(anfang, anfang + zeile), encoding="utf-8")
    monkeypatch.setattr(gu, "WERTE_REGISTRY_TS", datei)
    assert _neu_ohne_abschnitt(gu.alle_zeilen()) == {"kennwert:kuenstlich_u1"}


def test_e_hand_datei_unbekannter_schluessel_und_formel_werden_gemeldet(zeilen):
    hand = {"sensor": {"gibt_es_nicht": {"abschnitt": "BERECHNUNGEN.md#x"}},
            "kennwert": {"erzeugung": {"formel": "von Hand"}}, "fantasie": {}}
    fehler = "\n".join(gu.hand_formfehler(hand, zeilen))
    for erwartet in ("`gibt_es_nicht` — keine Registry kennt", "Feld `formel` ist hier nicht erlaubt",
                     "unbekannte Ebene `fantasie`"):
        assert erwartet in fehler


def test_e_falsche_verweise_werden_gemeldet_richtige_nicht(anker):
    hand = {"monatsgroesse": {
        "ErzeugungFakten.pv_kwh": {"abschnitt": "BERECHNUNGEN.md#gibt-es-nicht",
                                   "test": "backend/tests/test_gibt_es_nicht.py",
                                   "code_ort": "backend.services.monats_fakten.bau::_gibt_es_nicht"},
        "ErzeugungFakten.bkw_kwh": {"test": "backend/tests/test_routen_baseline.py::test_keine_route_ist_verschwunden",
                                    "code_ort": "backend.services.monats_fakten.bau::_erzeugung"},
    }}
    fehler = gu.hand_verweisfehler(hand, anker, mit_docs=_MIT_DOCS)
    assert all("ErzeugungFakten.pv_kwh" in f for f in fehler), fehler
    assert len(fehler) == (3 if _MIT_DOCS else 2), fehler


@_OHNE_DOCS
def test_e_richtiger_abschnitt_wird_nicht_gemeldet(anker):
    hand = {"kennwert": {"erzeugung": {"abschnitt": "BERECHNUNGEN.md#41c-prognose-vergleich-auswertungen--prognose"}}}
    assert gu.hand_verweisfehler(hand, anker, mit_docs=True) == []


def test_e_toter_anker_wird_beim_namen_gemeldet(anker):
    verweise = [("X.md", 7, "BERECHNUNGEN.md", "gibt-es-nicht")]
    assert gu.tote_anker(verweise, anker) == ["X.md:7 → BERECHNUNGEN.md#gibt-es-nicht"]


@_OHNE_DOCS
def test_e_ein_hand_eintrag_aendert_die_datei(zeilen, anker):
    """(c) kann rot werden: ein Abschnitt in der Hand-Datei steht danach in der Spalte «Regel»."""
    hand = {e: {} for e in gu.EBENEN}
    hand[gu.SENSOR] = {zeilen[gu.SENSOR][0].schluessel: {"abschnitt": "SENSOR-REFERENZ.md#11-export-sensoren-eedc--ha"}}
    assert gu.dokument(zeilen, hand, anker) != gu.dokument(zeilen, {e: {} for e in gu.EBENEN}, anker)
    assert "(SENSOR-REFERENZ.md#11-export-sensoren-eedc--ha)" in gu.dokument(zeilen, hand, anker)


def test_e_quellen_sind_austauschbar():
    """Die Gegenproben greifen an den Lesern, nicht an Produktivcode — ``Quellen`` ist die Naht dafür."""
    leer = dataclasses.replace(gu.produktiv_quellen(), sensoren=list)
    assert gu.alle_zeilen(leer)[gu.SENSOR] == []


# ── (e) Gegenproben SENSOR-REFERENZ ─────────────────────────────────────────


def _sr_fehler(**quellen) -> str:
    return "\n".join(gu.sr_pruefung_und_text(**quellen)[0])


def test_e_sr_unbekannter_marker_wird_beim_namen_gemeldet():
    bausteine = [("00-kopf.md", "# Titel\n\n<!-- erzeugt: gibtsnicht typ=x -->\n")]
    fehler = _sr_fehler(bausteine=bausteine, felder=[], sensoren=[], hand={}, anker={})
    assert "00-kopf.md:3: unbekannter Marker" in fehler, fehler


def test_e_sr_marker_ohne_zeilen_wird_gemeldet():
    bausteine = [("00-kopf.md", "# Titel\n<!-- erzeugt: eingabefelder typ=gibtsnicht liste=monat -->\n")]
    fehler = _sr_fehler(bausteine=bausteine, felder=[], sensoren=[], hand={}, anker={})
    assert "00-kopf.md:2: Marker ohne Zeilen" in fehler, fehler


@_OHNE_DOCS
def test_e_sr_kuenstlicher_sensor_steht_in_der_tabelle_seiner_kategorie():
    from backend.services.ha_sensors_export import SensorCategory, SensorDefinition

    kuenstlich = SensorDefinition(key="kuenstlich_u3_kwh", name="Künstlich U3", unit="kWh", icon="mdi:test",
                                  category=SensorCategory.ENERGIE, formel="Gegenprobe")
    fehler, text = gu.sr_pruefung_und_text(sensoren=[*gu.sensor_definitionen(), kuenstlich])
    assert not fehler, fehler
    abschnitt = text.split("### Anlage-weite Sensoren", 1)[1].split("\n### ", 1)[0]
    assert "| `kuenstlich_u3_kwh` | Künstlich U3 | kWh |" in abschnitt


@_OHNE_DOCS
def test_e_sr_kategorie_ohne_marker_wird_beim_namen_gemeldet():
    bausteine = [(name, "\n".join(z for z in text.split("\n") if "kategorie=preis" not in z))
                 for name, text in gu.sr_bausteine_lesen()]
    fehler = _sr_fehler(bausteine=bausteine)
    assert "Kategorie `preis` gehört zu 0 Unterabschnitten" in fehler, fehler
    assert "Export-Sensor `eedc_preis_rang` (Kategorie `preis`) steht in 0 Markern" in fehler, fehler


@_OHNE_DOCS
def test_e_sr_eingabefeld_ohne_marker_wird_beim_namen_gemeldet():
    neu = gu.SrFeld("fantasie", "", "neu_kwh", "INVESTITION_FELDER", {"feld": "neu_kwh", "einheit": "kWh"})
    fehler = _sr_fehler(felder=[*gu.sr_eingabefelder(), neu])
    assert "Eingabefeld fantasie:neu_kwh (INVESTITION_FELDER) steht in 0 Markern" in fehler, fehler


@_OHNE_DOCS
def test_e_sr_doppelter_marker_wird_beim_namen_gemeldet():
    bausteine = gu.sr_bausteine_lesen()
    bausteine.append(("99-doppelt.md", "## Doppelt\n<!-- erzeugt: eingabefelder typ=speicher liste=live -->\n"))
    fehler = _sr_fehler(bausteine=bausteine)
    assert "Eingabefeld speicher:soc (LIVE_FELDER_INV) steht in 2 Markern" in fehler, fehler


def test_e_sr_sichten_kommen_aus_feld_auswertungen():
    """Die Spalte «Sichten» ist die Liste der Zuordnungs-Fläche (``sichten_fuer``), kein Hand-Feld."""
    from backend.core.feld_auswertungen import sichten_fuer

    felder = {f.name: f for f in gu.sr_eingabefelder()}
    assert gu.sr_sichten(felder["basis:einspeisung_kwh"]) == " · ".join(sichten_fuer("basis", "einspeisung_kwh"))
    assert gu.sr_sichten(felder["e-auto:km_stand"]).startswith("— "), "Feld ohne Auswertung nennt den Grund"
    assert "sichten" not in gu.HAND_FELDER[gu.EINGABEFELD]


# ── MQTT_INBOUND (Stufe U3b) ────────────────────────────────────────────────


@_OHNE_DOCS
def test_c_mqtt_inbound_ist_aktuell():
    fehler, soll = gu.mq_pruefung_und_text()
    assert not fehler, "MQTT_INBOUND nicht erzeugbar:\n  " + "\n  ".join(fehler) + _BEFEHLE
    ist = gu.MQ_ZIEL.read_text(encoding="utf-8") if gu.MQ_ZIEL.exists() else ""
    assert ist == soll, (
        "docs/MQTT_INBOUND.md weicht von der Erzeuger-Ausgabe ab — ein Baustein in docs/mqtt-inbound/, die Feld-Registry, "
        "die Topic-Registry (services/mqtt_topic_registry.py), ein MQTT-Leser, der Kanal-Katalog oder ein Preset geändert, "
        "ohne neu zu erzeugen (oder die Datei von Hand geändert — Änderungen gehören in die Bausteine)." + _BEFEHLE
    )


@_OHNE_DOCS
def test_d_mqtt_inbound_anker_sind_belegt(anker):
    """Hilfe und Sensor-Referenz verweisen auf zwei Anker von MQTT_INBOUND — beide stehen in den Bausteinen."""
    verweise = [v for v in gu.anker_verweise(gu.verweis_dateien()) if v[2] == "MQTT_INBOUND.md"]
    assert {a for *_r, a in verweise} >= {"topic-struktur", "zustand-und-sitzung-der-e-mobilität"}
    assert not gu.tote_anker(verweise, anker)


def _mq_fehler(**quellen) -> str:
    return "\n".join(gu.mq_pruefung_und_text(**quellen)[0])


def test_mq_jedes_feld_genau_eine_zeile_ohne_skip_typen():
    """Totalität: jeder Registry-Eintrag außer ``SKIP_TYPEN`` hat genau eine Zeile (Basis-Energy nimmt gleichnamige
    Basis-Felder auf); Wechselrichter haben keine."""
    felder = gu.sr_eingabefelder()
    zeilen = gu.mqtt_zeilen(felder)
    skip = gu._skip_typen()
    energy_keys = {k for k, *_r in gu._basis_energy_topics()}
    erwartet = sum(1 for f in felder if f.typ not in skip
                   and not (f.typ == "basis" and gu._MQ_LISTE[f.liste] == "energy" and f.feld in energy_keys))
    assert len(zeilen) == erwartet + len(energy_keys)
    assert not [z for z in zeilen if z.typ in skip]


def test_mq_sprengsatz_registry_feld_entfernt_wird_beim_namen_gemeldet():
    """Fehlt ein Feld in den Zeilen, das die Topic-Registry erwartet, meldet das Sollbild es — (c) wird rot."""
    felder = [f for f in gu.sr_eingabefelder() if f.name != "speicher:soc"]
    fehler = _mq_fehler(zeilen=gu.mqtt_zeilen(felder))
    assert "inv/{inv_id}_{name}/soc` (speicher): die Registry erwartet es, keine Tabellen-Zeile" in fehler, fehler


@pytest.mark.parametrize("neu, zeile", [
    # Ein Energie-Name MIT Leser (Stand-Zähler), den die Speicher-Registry nicht kennt — seit N-780 bekommt ein
    # Energie-Feld ohne Leser kein Topic mehr, ein erfundenes `neu_kwh` liefe deshalb still durch.
    (gu.SrFeld("speicher", "", "ladevorgaenge", "INVESTITION_FELDER", {"feld": "ladevorgaenge", "einheit": ""}),
     "speicher:ladevorgaenge [INVESTITION_FELDER, energy]"),
    (gu.SrFeld("speicher", "", "neu_w", "LIVE_FELDER_INV", {"key": "neu_w", "einheit": "W"}),
     "speicher:neu_w [LIVE_FELDER_INV, live]"),
], ids=["energy", "live"])
def test_mq_kuenstliches_feld_ohne_topic_in_der_registry_wird_gemeldet(neu, zeile):
    fehler = _mq_fehler(zeilen=gu.mqtt_zeilen([*gu.sr_eingabefelder(), neu]))
    assert f"{zeile}: die Tabelle nennt" in fehler, fehler


def test_mq_typ_ohne_marker_wird_beim_namen_gemeldet():
    neu = gu.SrFeld("fantasie", "", "neu_w", "LIVE_FELDER_INV", {"key": "neu_w", "einheit": "W"})
    fehler = _mq_fehler(zeilen=gu.mqtt_zeilen([*gu.sr_eingabefelder(), neu]))
    assert "Topic-Zeile fantasie:neu_w [LIVE_FELDER_INV, live] steht in 0 Markern" in fehler, fehler


def test_mq_falsche_marker_werden_beim_namen_gemeldet():
    bausteine = [("00-kopf.md", "# T\n<!-- erzeugt: mqtt-topics typ=wechselrichter liste=live -->\n"
                                "<!-- erzeugt: mqtt-topics typ=speicher -->\n<!-- erzeugt: mqtt-preset id=gibtsnicht -->\n")]
    fehler = _mq_fehler(bausteine=bausteine, topics=[])
    assert "00-kopf.md:2: Typ ['wechselrichter'] hat keine Topics (SKIP_TYPEN)" in fehler, fehler
    assert "00-kopf.md:3: Marker" in fehler and "fehlende ['liste']" in fehler, fehler
    assert "00-kopf.md:4: Preset `gibtsnicht` unbekannt" in fehler, fehler


def test_mq_nur_manuell_hat_kein_topic():
    zeilen = {z.name: z for z in gu.mqtt_zeilen()}
    z = zeilen["e-auto:km_stand [INVESTITION_FELDER, energy]"]
    assert z.topic is None and z.ohne_topic == gu.KEIN_TOPIC_MANUELL


def test_mq_payload_kommt_aus_den_lesern():
    """Ein Geräte-Energiefeld ohne Leser (Zählerreihe, Heute, Kilometerstand) hat seit N-780 kein Topic — die Zelle sagt,
    wie der Wert stattdessen kommt (HA-Sensor nur, wo der Monatsabschluss-Vorschlag ihn aus der HA-Statistik liest);
    eines mit Leser nennt den Stand."""
    assert gu.mq_energie_leser("e-auto", "ladung_extern_kwh") == []
    assert "Zählerreihe" in gu.mq_energie_leser("wallbox", "ladung_kwh")
    assert "Kilometerstand" in gu.mq_energie_leser("e-auto", "km_gefahren")
    zeilen = {z.name: z for z in gu.mqtt_zeilen()}
    kwh = zeilen["e-auto:ladung_extern_kwh [INVESTITION_FELDER, energy]"]
    assert kwh.topic is None and kwh.ohne_topic == gu.KEIN_TOPIC_OHNE_LESER_HA
    euro = zeilen["e-auto:ladung_extern_euro [INVESTITION_FELDER, energy]"]
    assert euro.topic is None and euro.ohne_topic == gu.KEIN_TOPIC_OHNE_LESER_HAND
    assert zeilen["wallbox:ladung_kwh [INVESTITION_FELDER, energy]"].payload == gu.PAYLOAD_ZAEHLER


def test_mq_sollbild_meldet_ein_topic_ohne_leser_beim_namen():
    """Die Tabelle darf für ein Feld mit ``ohne_leser`` kein Topic nennen (Gegenprobe an den Zeilen)."""
    zeilen = [dataclasses.replace(z, topic=gu.mq_topic(z.typ, z.liste, z.feld), ohne_topic="")
              if z.name == "e-auto:ladung_extern_kwh [INVESTITION_FELDER, energy]" else z for z in gu.mqtt_zeilen()]
    fehler = gu.mq_sollbild_fehler(zeilen, gu.mq_erwartete_topics())
    assert any("`ladung_extern_kwh` (e-auto) ist ohne Leser (N-780)" in f for f in fehler), fehler


def test_mq_zustandswoerter_kommen_aus_dem_kanon():
    from backend.core import zustands_kanon as zk

    zeilen = {z.name: z for z in gu.mqtt_zeilen()}
    payload = zeilen["wallbox:ladezustand [LIVE_FELDER_INV, live]"].payload
    assert all(f"`{w}`" in payload for w in zk.KANON["ladezustand"]), payload
    assert "`1`" in payload, "Codes (nur MQTT) stehen in der Zelle"
