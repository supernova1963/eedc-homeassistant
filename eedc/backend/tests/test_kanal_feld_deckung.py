"""Wächter Feld-Deckung (HA-Bauform E1, Bauplan §3): jedes Feld hat GENAU eine Kanal-Zuweisung.

**Die Regel.** Jedes Feld der Registry-Listen (``BASIS_FELDER``, ``BEDINGTE_BASIS_FELDER``,
``OPTIONALE_FELDER``, ``INVESTITION_FELDER``, ``LIVE_FELDER_INV``, ``BASIS_LIVE_FELDER``,
``BASIS_PREIS_FELDER``) und der Snapshot-Listen in ``services/snapshot/keys.py``
(``KUMULATIVE_ZAEHLER_FELDER``, ``KUMULATIVE_COUNTER_FELDER``, ``BASIS_ZAEHLER_FELDER``,
``MQTT_STAND_ZAEHLER_FELDER``) ist im Kanal-Katalog (``services/kanal/katalog.py``) einer Art
(``sum`` · ``mean`` · ``stand``) zugewiesen **oder** steht mit Grund in einer benannten Ausnahme-Klasse
(``_SNAPSHOT_AUSNAHMEN`` · „Abschluss-Feld ohne Sensor" O1–O6 · „Tagesgröße ohne Kanal", #110). Baseline 0.

**Warum baumweit und nicht je Feld.** Der Katalog ist abgeleitet — ein neues kWh-Feld bekommt seine
Art durch die Regel, ohne dass jemand es einträgt. Ein Feld, auf das KEINE Regel passt (neue Einheit,
neue Bedingung, neue Gruppe), wäre sonst still ohne Kanal: genau die N-259-Lage (vierzehn Monate
unentdeckt), eine Ebene höher. Der Wächter macht „bewusst kein Kanal" von „vergessen" unterscheidbar.

**Gegenprobe im Test selbst** (``test_gegenprobe_*``): künstliche Felder ohne passende Regel werden
dem Katalog hineingereicht und müssen beim Namen gemeldet werden — sonst wäre ein grüner Lauf nichts wert.

Schwesterdateien: test_kanal_spiegel.py, test_kanal_eigene_summe.py, test_kanal_mitschrift_betriebsart.py, test_kanal_bestand_unberuehrt.py; Vorbild test_snapshot_felder_sot_konformitaet.py.
"""

from __future__ import annotations

from collections import Counter

import pytest

from backend.core.field_definitions import (
    BASIS_FELDER,
    BEDINGTE_BASIS_FELDER,
    INVESTITION_FELDER,
    LIVE_FELDER_INV,
    _SNAPSHOT_AUSNAHMEN,
)
from backend.models.kanal import ART_MEAN, ART_STAND, ART_SUM, FAMILIE_MITSCHRIFT, KANAL_ARTEN, KANAL_FAMILIEN
from backend.services.kanal import katalog as kat
from backend.services.snapshot.keys import (
    BASIS_ZAEHLER_FELDER,
    KUMULATIVE_COUNTER_FELDER,
    KUMULATIVE_ZAEHLER_FELDER,
    MQTT_STAND_ZAEHLER_FELDER,
)


def _meldung(ohne) -> str:
    return (
        "Felder ohne Kanal-Zuweisung: "
        + ", ".join(f"{liste}:{typ or '-'}/{feld}" for liste, typ, feld in ohne)
        + ". Entweder eine Regel in services/kanal/katalog.py trifft sie (Art + Familie), oder sie "
          "stehen mit Grund in einer Ausnahme-Klasse (Bauplan §3/§3a)."
    )


# ── 1. Der Wächter ──────────────────────────────────────────────────────────


def test_jedes_feld_hat_eine_zuweisung():
    ohne = kat.ohne_regel()
    assert not ohne, _meldung(ohne)


def test_genau_eine_art_oder_eine_ausnahme_je_feld():
    doppelt = [k for k, n in Counter((z.liste, z.typ, z.feld) for z in kat.zuweisungen()).items() if n > 1]
    assert not doppelt, f"Feld mehrfach im Katalog: {doppelt}"
    for z in kat.zuweisungen():
        assert (z.art is None) != (z.ausnahme is None), f"{z}: genau eines von art/ausnahme"
        if z.art is not None:
            assert z.art in KANAL_ARTEN, z
            assert z.familien and set(z.familien) <= KANAL_FAMILIEN, z
        else:
            assert z.ausnahme in kat.AUSNAHME_KLASSEN, z
            assert z.familien == (), z
        assert (z.grund or "").strip(), f"{z}: ohne Grund"


def test_die_neun_snapshot_ausnahmen_stehen_als_klasse_im_katalog():
    """Seit #110 (13.10.2026) neun: ``e-auto/v2h_entladung_kwh`` ist gesnapshottet (Tagesgröße) und steht in der
    eigenen Klasse ``AUSNAHME_TAGESGROESSE`` (Probe darunter)."""
    im_katalog = {(z.typ, z.feld) for z in kat.zuweisungen() if z.ausnahme == kat.AUSNAHME_SNAPSHOT}
    assert im_katalog == set(_SNAPSHOT_AUSNAHMEN)
    assert len(im_katalog) == 9
    assert ("e-auto", "v2h_entladung_kwh") not in im_katalog


def test_v2h_ist_tagesgroesse_ohne_kanal():
    """#110 V2H-Tageswert (Entscheid Master 13.10.2026, O2): der V2H-Zähler steht in ``KUMULATIVE_ZAEHLER_FELDER``
    (der Tag liest ihn), bekommt aber KEINEN Kanal — in beiden Listen der Katalog-Klasse ``AUSNAHME_TAGESGROESSE``,
    ``zaehler_art`` ⇒ ``None`` (der Schreiber lässt ihn aus), und die E-Mob-Kanalgruppe verlangt ihn nicht (sonst
    fiele sie ohne den Kanal auf ``bestand``, und der laufende Monat trüge V2H über sie)."""
    from backend.services.kanal.geraete_leser import _emob_felder

    assert set(kat.TAGESGROESSE_OHNE_KANAL) == {("e-auto", "v2h_entladung_kwh")}
    assert "v2h_entladung_kwh" in KUMULATIVE_ZAEHLER_FELDER["e-auto"]
    klasse = {(z.liste, z.typ, z.feld) for z in kat.zuweisungen() if z.ausnahme == kat.AUSNAHME_TAGESGROESSE}
    assert klasse == {(kat.L_INV, "e-auto", "v2h_entladung_kwh"), (kat.L_ZAEHLER, "e-auto", "v2h_entladung_kwh")}
    assert kat.zaehler_art("inv:7:v2h_entladung_kwh", "e-auto") is None
    assert kat.ist_tagesgroesse_ohne_kanal("inv:7:v2h_entladung_kwh", "e-auto")
    assert not kat.ist_tagesgroesse_ohne_kanal("inv:7:ladung_kwh", "e-auto")

    class _Auto:
        id, typ = 7, "e-auto"

    felder = _emob_felder(_Auto(), lambda _inv, _f: True)
    assert "v2h_entladung_kwh" not in felder
    assert set(felder) == set(KUMULATIVE_ZAEHLER_FELDER["e-auto"]) - {"v2h_entladung_kwh"}


def test_abschluss_ausnahmen_tragen_ihre_o_klasse():
    """O1–O6 (Bauplan §3a) — jede Zuweisung der Klasse nennt ihre Zeile."""
    for z in kat.zuweisungen():
        if z.ausnahme == kat.AUSNAHME_ABSCHLUSS:
            assert z.grund.split(":")[0] in {"O1", "O2", "O3", "O4", "O5", "O6"}, z


def test_snapshot_listen_sind_zaehler_kanaele():
    """Was der Bestand stündlich als Zähler mitschneidet, ist im Katalog ``sum`` oder ``stand`` —
    der Schreiber fragt GENAU diese Funktion (``zaehler_art``)."""
    falsch = []
    for typ, felder in {**KUMULATIVE_ZAEHLER_FELDER}.items():
        for feld in felder:
            if (typ, feld) in kat.TAGESGROESSE_OHNE_KANAL:
                # #110: Zähler des Tages ohne Kanal — die Art ist hier ausdrücklich KEINE (eigene Probe unten).
                if kat.zaehler_art(f"inv:1:{feld}", typ) is not None:
                    falsch.append(f"{typ}/{feld} (Tagesgröße mit Kanal-Art)")
                continue
            if kat.zaehler_art(f"inv:1:{feld}", typ) not in (ART_SUM, ART_STAND):
                falsch.append(f"{typ}/{feld}")
    for typ, felder in KUMULATIVE_COUNTER_FELDER.items():
        for feld in felder:
            if kat.zaehler_art(f"inv:1:{feld}", typ) != ART_STAND:
                falsch.append(f"{typ}/{feld}")
    for feld in BASIS_ZAEHLER_FELDER:
        if kat.zaehler_art(f"basis:{feld}", None) != ART_SUM:
            falsch.append(f"basis/{feld}")
    for feld in MQTT_STAND_ZAEHLER_FELDER:
        if kat.zaehler_art(f"inv:1:{feld}", None) != ART_STAND:
            falsch.append(f"mqtt-stand/{feld}")
    assert not falsch, f"Zähler ohne Zähler-Art im Katalog: {falsch}"


def test_innengeraet_suffix_traegt_die_art_seines_basis_felds():
    assert kat.zaehler_art("inv:4:betriebsart_strom_kuehlen_kwh-3", "waermepumpe") == ART_SUM


def test_dasselbe_feld_hat_in_jeder_liste_dieselbe_art():
    arten: dict[tuple, set] = {}
    for z in kat.zuweisungen():
        if z.art in (ART_SUM, ART_STAND):
            arten.setdefault((z.typ, z.feld), set()).add(z.art)
    widerspruch = {k: v for k, v in arten.items() if len(v) > 1}
    assert not widerspruch, f"Feld mit zwei Arten: {widerspruch}"


def test_betriebsart_ist_mitschrift_anteil_je_stunde():
    zustand = [z for z in kat.zuweisungen() if z.liste == kat.L_LIVE_INV and z.feld == "betriebsmodus"]
    assert len(zustand) == 1
    z = zustand[0]
    assert (z.art, z.familien, z.schluessel, z.e1_schreiber) == (
        ART_MEAN, (FAMILIE_MITSCHRIFT,), "modus:inv:{id}:{betriebsart}", True)
    assert kat.modus_kanal_key(7, "heizen") == "modus:inv:7:heizen"


def test_staende_o7_o9_sind_stand():
    arten = {(z.typ, z.feld): z.art for z in kat.zuweisungen() if z.art}
    assert arten[("e-auto", "km_gefahren")] == ART_STAND        # O7
    assert arten[("wallbox", "ladevorgaenge")] == ART_STAND     # O7
    assert arten[("waermepumpe", "wp_starts_anzahl")] == ART_STAND   # O9
    assert arten[("waermepumpe", "wp_betriebsstunden")] == ART_STAND  # O9
    assert arten[("sonstiges", "zaehlerstand")] == ART_STAND


def test_mean_ist_mittelwert_kanal_spiegel_oder_mqtt_mitschrift_abgeleitetes_nur_benannt():
    """Seit HA-Bauform §9 (Standalone-Gleichstand S2): jeder ``mean`` außer der Betriebsart ist ein Mittelwert-Kanal —
    Spiegel bei HA-Entität, sonst MQTT-Mitschrift (bis S2: „Mitschrift, Quelle offen", ``mitschrift_offen``); die
    Betriebsart hat ihre eigene Mitschrift; abgeleitete Kanäle sind benannt."""
    for z in kat.zuweisungen():
        if z.art == ART_MEAN and z.feld != "betriebsmodus":
            assert z.e1_schreiber and z.mittelwert_kanal, z
            assert "sonst MQTT-Mitschrift (§9)" in z.grund, z
        elif z.art == ART_MEAN:
            assert z.e1_schreiber and not z.mittelwert_kanal, z
        else:
            assert not z.mittelwert_kanal, z
    assert kat.ist_mean_kanal("basis:strompreis", None)
    assert kat.ist_mean_kanal("inv:3:leistung_w-2", "waermepumpe")
    assert not kat.ist_mean_kanal("inv:3:betriebsmodus", "waermepumpe")
    assert not kat.ist_mean_kanal("inv:3:ladung_kwh", "speicher")
    assert set(kat.ABGELEITETE_KANAELE) >= {"kosten:*", "ueberschuss", "defizit"}


def test_mittelwert_live_keys_ohne_preis_und_ohne_zustand():
    """S2-1 (G3, G7): die Live-Keys der MQTT-Mitschrift — W · °C · %, Innengeräte-Kopien, kein Modus, kein Preis."""
    assert kat.mittelwert_live_keys(None) == {
        "einspeisung_w": "W", "netzbezug_w": "W", "netz_kombi_w": "W", "pv_gesamt_w": "W", "aussentemperatur_c": "°C"}
    assert "strompreis" not in kat.mittelwert_live_keys(None) and "strompreis_ct" not in kat.mittelwert_live_keys(None)
    wp = kat.mittelwert_live_keys("waermepumpe", {"wp_art": "luft_wasser"})
    assert {"leistung_w", "vorlauf_temperatur_c", "ruecklauf_temperatur_c", "heizstab_leistung_w",
            "warmwasser_temperatur_c"} <= set(wp)
    assert "betriebsmodus" not in wp and wp["vorlauf_temperatur_c"] == "°C"
    split = kat.mittelwert_live_keys("waermepumpe", {"wp_art": "luft_luft",
                                                     "innengeraete": [{"id": 3, "bezeichnung": "Büro"}]})
    assert split["leistung_w-3"] == "W" and split["ist_temperatur_c-3"] == "°C"
    assert kat.mittelwert_live_keys("e-auto") == {"leistung_w": "W", "soc": "%"}
    assert kat.mittelwert_live_keys("speicher") == {"leistung_w": "W", "soc": "%"}
    for pv in ("pv-module", "balkonkraftwerk", "wechselrichter"):
        assert kat.mittelwert_live_keys(pv) == {"leistung_w": "W"}


# ── 2. Gegenprobe: der Prüfer KANN rot melden ───────────────────────────────


def _mit_zusatz(listen: dict, typ: str, eintrag: dict) -> dict:
    neu = dict(listen)
    alt = neu[typ]
    if isinstance(alt, dict):
        neu[typ] = {**alt, "neu": [*next(iter(alt.values())), eintrag]}
    else:
        neu[typ] = [*alt, eintrag]
    return neu


def test_gegenprobe_kuenstliches_investitionsfeld_ohne_regel():
    inv = _mit_zusatz(INVESTITION_FELDER, "speicher", {"feld": "co2_kg", "label": "CO₂", "einheit": "kg"})
    _, ohne = kat.kanal_katalog(investition_felder=inv)
    assert ("INVESTITION_FELDER", "speicher", "co2_kg") in ohne, _meldung(ohne)


def test_gegenprobe_kuenstliches_live_feld_ohne_regel():
    live = {**LIVE_FELDER_INV, "speicher": [*LIVE_FELDER_INV["speicher"], {"key": "helligkeit", "einheit": "lx"}]}
    _, ohne = kat.kanal_katalog(live_felder_inv=live)
    assert ("LIVE_FELDER_INV", "speicher", "helligkeit") in ohne


def test_gegenprobe_neue_basis_gruppe_und_neue_bedingung():
    basis = [*BASIS_FELDER, {"feld": "luftdruck_hpa", "einheit": "hPa", "gruppe": "klima"}]
    bedingt = [*BEDINGTE_BASIS_FELDER, {"feld": "holzpreis", "einheit": "€/rm", "bedingung_basis": "hat_ofen"}]
    _, ohne = kat.kanal_katalog(basis_felder=basis, bedingte_basis_felder=bedingt)
    assert ("BASIS_FELDER", None, "luftdruck_hpa") in ohne
    assert ("BEDINGTE_BASIS_FELDER", None, "holzpreis") in ohne


def test_gegenprobe_snapshot_liste_mit_unbekanntem_feld():
    zaehler = {**KUMULATIVE_ZAEHLER_FELDER, "speicher": (*KUMULATIVE_ZAEHLER_FELDER["speicher"], "phantom")}
    _, ohne = kat.kanal_katalog(kumulative_zaehler_felder=zaehler)
    assert ("KUMULATIVE_ZAEHLER_FELDER", "speicher", "phantom") in ohne


@pytest.mark.parametrize("feld,einheit,art", [("waerme2_kwh", "kWh", ART_SUM), ("leistung2_w", "W", None)])
def test_gegenprobe_die_regel_greift_fuer_neue_felder_von_selbst(feld, einheit, art):
    """Die andere Richtung: ein neues kWh-Feld braucht keinen Eintrag — die Regel trägt es."""
    inv = _mit_zusatz(INVESTITION_FELDER, "waermepumpe", {"feld": feld, "einheit": einheit})
    zuw, ohne = kat.kanal_katalog(investition_felder=inv)
    if art is None:
        assert ("INVESTITION_FELDER", "waermepumpe", feld) in ohne
    else:
        assert any(z.feld == feld and z.art == art for z in zuw)
