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
(d) Anker-Probe: jeder Verweis ``BERECHNUNGEN.md#…``/``SENSOR-REFERENZ.md#…`` in ``docs/*.md`` und ``CHANGELOG.md``
    trifft eine Überschrift. Der Website-Build prüft keine Anker — das tut nur diese Probe (U0: zwei waren tot).
(e) Gegenproben: ein künstlicher Registry-Eintrag ohne Hand-Eintrag, ein falscher Verweis, ein toter Anker werden
    beim Namen gemeldet — sonst wäre ein grüner Lauf nichts wert (Muster ``test_kanal_feld_deckung.py``).

**Die Slug-Regeln** (github-slugger, ein Slugger je Dokument; Überschriften in Blockquotes und Setext zählen) sind am
7.11.2026 gegen die Pipeline der In-App-Hilfe gemessen (remark-gfm + rehype-raw + rehype-slug wie
``components/ui/MarkdownDoc.tsx``): 3164 Überschriften in 39 Dateien, alle Anker gleich.

**Wenn dieser Test rot wird:**

    scripts/groessen-uebersicht.sh              # docs/UEBERSICHT-GROESSEN.md neu schreiben
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
    assert not fehler, "groessen_hand.yaml verweist ins Leere:\n  " + "\n  ".join(fehler)


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
    return set(gu.offene_schluessel({}, zeilen_)) - set(gu.baseline_lesen())


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
