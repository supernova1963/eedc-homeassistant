"""Tests #150 Slice B — eedc-Börsenpreis-Rang-Export nach HA.

Rang je Tag-/Nacht-Fenster (1–5 günstigste, 99 Rest) + günstige-Stunden-Anzahl
gesamt/Tag/Nacht. „Günstig" ist zweistufig (Rainer-PN 2026-06-11): Rang 1–5
UND Preis ≥10 % unter dem Tagesdurchschnitt ohne die 3 Peak-Stunden.
Reine Rang-Logik + solar-basiertes Fenster isoliert, Verdrahtung mit gemockten
Preis-/Wetter-Quellen.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.preis_rang import (
    GUENSTIG_SCHWELLE_FAKTOR,
    GUENSTIG_TOP_N,
    RANG_TEUER,
    abstand_zum_durchschnitt_prozent,
    berechne_preis_rang,
    guenstig_schwelle,
    optimierter_durchschnitt,
)
from backend.services.solar_forecast_service import sonnenauf_unter_stunde
from backend.models import Anlage, Investition, Monatsdaten


# ── Günstig-Schwelle (rein) ─────────────────────────────────────────────────

def test_guenstig_schwelle_ohne_drei_peaks():
    # 24 Preise 1..24 ct: ohne die 3 Peaks (22, 23, 24) bleibt Ø(1..21) = 11.
    preise = {h: float(h + 1) for h in range(24)}
    schwelle = guenstig_schwelle(preise)
    assert schwelle == pytest.approx(11.0 * GUENSTIG_SCHWELLE_FAKTOR)


def test_guenstig_schwelle_zu_wenige_preise_ist_none():
    assert guenstig_schwelle({0: 8.0, 1: 9.0, 2: 7.0}) is None


def test_guenstig_schwelle_custom_faktor():
    # Pro Anlage einstellbarer Faktor (Folge-Wunsch 2026-06-11): z. B. Ø×0,925.
    preise = {h: float(h + 1) for h in range(24)}
    assert guenstig_schwelle(preise, faktor=0.925) == pytest.approx(11.0 * 0.925)


# ── Rang-Logik (rein) ───────────────────────────────────────────────────────

def test_rang_billigste_ist_eins_schwelle_kappt_top5():
    # Sortiert [5,10,15,20,25,30,40,50] → ohne 3 Peaks Ø=15 → Schwelle 13.5:
    # nur 5 ct und 10 ct sind günstig, der Rest der Top-5 fällt auf 99.
    preise = {h: float(p) for h, p in enumerate([30, 10, 20, 5, 40, 50, 15, 25])}
    erg = berechne_preis_rang(preise, tag_stunden=set(range(8)), nacht_stunden=set(), aktuelle_stunde=3)
    assert erg.schwelle_cent == pytest.approx(13.5)
    assert erg.rang_profil[3] == 1          # 5 ct = billigste
    assert erg.rang_profil[1] == 2          # 10 ct
    assert erg.rang_profil[6] == RANG_TEUER  # 15 ct > Schwelle → nicht günstig
    assert erg.rang_profil[5] == RANG_TEUER  # 50 ct = teuerste → 99
    assert erg.rang_aktuell == 1
    assert erg.guenstige_stunden_anzahl == 2


def test_rang_tag_und_nacht_getrennt_schwelle_global():
    # Nacht billig (5 ct), Tag teuer (30 ct): die Schwelle wird über ALLE
    # Tagespreise gebildet — im Tag-Fenster ist damit trotz Top-5-Ranking
    # KEINE Stunde günstig (Rainer-Kern: erzwungener Verbrauch bei 30 ct
    # ergibt keinen Sinn, nur weil die Stunde relativ vorn liegt).
    preise = {h: (5.0 if h < 6 else 30.0) for h in range(24)}
    tag = set(range(6, 21))
    nacht = set(range(24)) - tag
    erg = berechne_preis_rang(preise, tag_stunden=tag, nacht_stunden=nacht, aktuelle_stunde=10)
    assert all(erg.rang_profil[h] == RANG_TEUER for h in tag)
    assert erg.guenstige_stunden_tag == 0
    # Im Nacht-Fenster liegen ALLE 6 5-ct-Stunden unter der Schwelle und
    # zählen ab v4.1 auch alle sechs (#335/N-103). Der RANG bleibt auf die
    # fünf billigsten gedeckelt — die sechste ist günstig, aber nicht Top-5.
    assert erg.guenstige_stunden_nacht == 6
    assert erg.guenstige_stunden_anzahl == 6
    assert sum(1 for h in nacht if erg.rang_profil[h] <= GUENSTIG_TOP_N) == GUENSTIG_TOP_N
    assert erg.rang_aktuell == RANG_TEUER


def test_rang_kleines_fenster_alle_guenstig():
    preise = {0: 8.0, 1: 9.0, 2: 7.0}
    erg = berechne_preis_rang(preise, tag_stunden=set(), nacht_stunden={0, 1, 2}, aktuelle_stunde=2)
    assert erg.rang_profil == {2: 1, 0: 2, 1: 3}
    assert erg.rang_aktuell == 1
    assert erg.guenstige_stunden_anzahl == 3


def test_rang_aktuelle_stunde_ohne_preis_ist_none():
    erg = berechne_preis_rang({0: 5.0}, tag_stunden={0}, nacht_stunden=set(), aktuelle_stunde=14)
    assert erg.rang_aktuell is None


# ── #335: der optimierte Ø und der Abstand dazu (rapahl-PN 2026-08-05) ──────

def test_optimierter_durchschnitt_ist_die_schwelle_ohne_faktor():
    """Der Ø ohne 3 Peaks ist die Bezugsgröße — die Schwelle ist er × Faktor.

    Bis v4.0 verließ nur das Produkt die Datei; genau die Zahl, nach der
    gefragt wurde, war damit im Export unerreichbar.
    """
    preise = {h: float(h + 1) for h in range(24)}
    assert optimierter_durchschnitt(preise) == pytest.approx(11.0)
    assert guenstig_schwelle(preise) == pytest.approx(
        optimierter_durchschnitt(preise) * GUENSTIG_SCHWELLE_FAKTOR
    )


def test_optimierter_durchschnitt_zu_wenige_preise_ist_none():
    assert optimierter_durchschnitt({0: 8.0, 1: 9.0, 2: 7.0}) is None


def test_abstand_negativ_ist_billiger_positiv_ist_teurer():
    assert abstand_zum_durchschnitt_prozent(9.0, 10.0) == pytest.approx(-10.0)
    assert abstand_zum_durchschnitt_prozent(12.0, 10.0) == pytest.approx(20.0)
    assert abstand_zum_durchschnitt_prozent(10.0, 10.0) == pytest.approx(0.0)


def test_abstand_bei_negativem_durchschnitt_behaelt_das_vorzeichen():
    """Day-Ahead-Preise werden negativ — der Bezug ist der BETRAG des Ø.

    −5 ct ist gegenüber einem Ø von −10 ct **teurer**. Mit dem
    vorzeichenbehafteten Nenner käme −50 % heraus und der Sensor behauptete
    „billiger als der Ø" — genau die Aussage, auf die eine Nicht-Entlade-Regel
    hört.
    """
    assert abstand_zum_durchschnitt_prozent(-5.0, -10.0) == pytest.approx(50.0)
    assert abstand_zum_durchschnitt_prozent(-15.0, -10.0) == pytest.approx(-50.0)


def test_abstand_ohne_bezug_ist_none():
    assert abstand_zum_durchschnitt_prozent(5.0, 0.0) is None
    assert abstand_zum_durchschnitt_prozent(None, 10.0) is None
    assert abstand_zum_durchschnitt_prozent(5.0, None) is None


def test_ergebnis_traegt_preis_durchschnitt_und_abstand():
    preise = {h: float(h + 1) for h in range(24)}   # Ø ohne Peaks = 11
    erg = berechne_preis_rang(
        preise, tag_stunden=set(range(6, 20)), nacht_stunden=set(range(6)) | set(range(20, 24)),
        aktuelle_stunde=21,                          # 22 ct
    )
    assert erg.preis_aktuell_cent == pytest.approx(22.0)
    assert erg.optimierter_durchschnitt_cent == pytest.approx(11.0)
    assert erg.abstand_prozent == pytest.approx(100.0)


def test_ergebnis_ohne_preis_zur_aktuellen_stunde():
    erg = berechne_preis_rang({h: 10.0 for h in range(8)}, tag_stunden=set(range(8)),
                              nacht_stunden=set(), aktuelle_stunde=14)
    assert erg.preis_aktuell_cent is None
    assert erg.abstand_prozent is None
    assert erg.optimierter_durchschnitt_cent == pytest.approx(10.0)


# ── #335/N-103: die Günstig-Zählung ist nicht mehr bei 5 gedeckelt ──────────

def test_rang_bleibt_von_der_entkappung_unberuehrt():
    """Der RANG ändert sich durch #335 nicht — nur die Zählung.

    Rainer hat Automationen auf den bestehenden Exportwerten gebaut (sein
    Einwand 06.08.). Die Entkappung bewegt `guenstige_stunden_*`; dass
    `eedc_preis_rang` dieselbe Zahl liefert wie vorher, ist eine Behauptung
    über den Code und steht deshalb hier als Beleg: Rang 1–5 bekommen weiter
    nur die fünf billigsten je Fenster **und** nur unter der Schwelle,
    alles andere 99.
    """
    # 7 billige Stunden — mehr als der Top-5-Deckel, alle unter der Schwelle.
    preise = {h: (1.0 if h < 7 else 20.0) for h in range(24)}
    nacht = set(range(7))
    erg = berechne_preis_rang(preise, tag_stunden=set(range(7, 24)),
                              nacht_stunden=nacht, aktuelle_stunde=0)
    # Genau die Ränge 1..5 im Fenster, je einmal — der Rest 99.
    raenge_nacht = sorted(erg.rang_profil[h] for h in nacht)
    assert raenge_nacht == [1, 2, 3, 4, 5, RANG_TEUER, RANG_TEUER]
    assert all(erg.rang_profil[h] == RANG_TEUER for h in range(7, 24))
    # Und die teure Stunde bleibt teuer, auch wenn sie die billigste ihres
    # Fensters ist (Schwelle über dem Rang).
    erg_tag = berechne_preis_rang(preise, tag_stunden=set(range(7, 24)),
                                  nacht_stunden=nacht, aktuelle_stunde=7)
    assert erg_tag.rang_aktuell == RANG_TEUER

def test_guenstige_stunden_zaehlen_ungekappt():
    """Sieben Stunden unter der Schwelle zählen sieben, nicht fünf.

    Der Fund: als Anzeige war der Top-5-Deckel stimmig, als **Divisor** in
    einer Automation zu klein — eine daraus gerechnete Ladeleistung fiel zu
    hoch aus. Der Rang bleibt gedeckelt, weil er etwas anderes aussagt.
    """
    # 7 × 1 ct + 17 × 20 ct → Ø ohne 3 Peaks = 287/21 ≈ 13,67 → Schwelle ≈ 12,3.
    preise = {h: (1.0 if h < 7 else 20.0) for h in range(24)}
    nacht = set(range(7))
    erg = berechne_preis_rang(preise, tag_stunden=set(range(7, 24)),
                              nacht_stunden=nacht, aktuelle_stunde=0)
    assert erg.guenstige_stunden_nacht == 7
    assert erg.guenstige_stunden_anzahl == 7
    # …und trotzdem tragen nur fünf einen Rang.
    assert sum(1 for h in nacht if erg.rang_profil[h] <= GUENSTIG_TOP_N) == GUENSTIG_TOP_N
    assert all(erg.unter_schwelle_profil[h] for h in nacht)
    assert not any(erg.unter_schwelle_profil[h] for h in range(7, 24))


def test_null_prozent_legt_die_schwelle_auf_den_durchschnitt():
    """0 % je Anlage → Faktor 1,0 → die Schwelle IST der Ø ohne Peaks.

    UI-Text und Sensor-Referenz sagten bis v4.0 „0 % schaltet die Schwelle ab,
    dann zählen wieder die 5 günstigsten" — der Code hat sie nie abgeschaltet,
    sondern auf den Ø gelegt. Der Top-5-Deckel verdeckte den Unterschied;
    ohne ihn zählt 0 % jetzt sichtbar **alle** Stunden unter dem Ø. Texte
    wurden darauf korrigiert (Gernot, 06.08.).
    """
    # 7 × 1 ct + 17 × 20 ct → Ø ohne 3 Peaks ≈ 13,67.
    preise = {h: (1.0 if h < 7 else 20.0) for h in range(24)}
    erg = berechne_preis_rang(preise, tag_stunden=set(), nacht_stunden=set(range(24)),
                              aktuelle_stunde=0, schwelle_faktor=1.0)
    assert erg.schwelle_cent == pytest.approx(287.0 / 21.0, abs=0.01)
    assert erg.optimierter_durchschnitt_cent == pytest.approx(erg.schwelle_cent, abs=0.01)
    # Nur die sieben 1-ct-Stunden liegen unter dem Ø — nicht alle 24.
    assert erg.guenstige_stunden_anzahl == 7


def test_ohne_ausreichende_basis_greift_allein_die_rang_regel():
    """Zu wenige Preise für einen Ø ⇒ keine Schwelle ⇒ reines Ranking."""
    erg_ohne = berechne_preis_rang({0: 8.0, 1: 9.0, 2: 7.0}, tag_stunden=set(),
                                   nacht_stunden={0, 1, 2}, aktuelle_stunde=0)
    assert erg_ohne.schwelle_cent is None
    assert erg_ohne.optimierter_durchschnitt_cent is None
    assert erg_ohne.guenstige_stunden_anzahl == 3
    assert all(erg_ohne.unter_schwelle_profil.values())


# ── Solar-basiertes Tag/Nacht-Fenster ───────────────────────────────────────

def test_sonnenfenster_sommer_laenger_als_winter():
    sa_s, su_s = sonnenauf_unter_stunde("2026-06-21", 48.8, 9.2)
    sa_w, su_w = sonnenauf_unter_stunde("2026-12-21", 48.8, 9.2)
    assert (su_s - sa_s) > (su_w - sa_w)
    assert (su_s - sa_s) > 14            # Sommer > 14 h Tageslicht
    assert (su_w - sa_w) < 10            # Winter < 10 h Tageslicht
    assert 0 <= sa_s <= 12 <= su_s <= 24


# ── Verdrahtung: calculate_anlage_sensors mit gemockten Quellen ─────────────

@pytest.fixture
def _patch_preis(monkeypatch):
    import backend.services.strompreis_markt_service as smp

    async def fake_marktpreise(datum, markt="DE", timeout=15.0):
        # billigste Stunden früh (2 ct), teuer am Abend
        return {h: 2.0 + (h % 6) * 3.0 for h in range(24)}

    monkeypatch.setattr(smp, "fetch_marktpreise", fake_marktpreise)


async def _seed_anlage(db) -> Anlage:
    anlage = Anlage(anlagenname="Preis-Test", leistung_kwp=10.0,
                    latitude=48.8, longitude=9.2, standort_land="DE")
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    await db.flush()
    return anlage


async def test_preis_sensoren_erscheinen(db, _patch_preis):
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = await _seed_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    assert "eedc_preis_rang" in by_key
    assert by_key["eedc_preis_guenstige_stunden_anzahl"].value >= 1
    # Tag/Nacht-Split (Rainer-PN 2026-06-11): Summe == Gesamt-Anzahl.
    assert (
        by_key["eedc_preis_guenstige_stunden_tag"].value
        + by_key["eedc_preis_guenstige_stunden_nacht"].value
        == by_key["eedc_preis_guenstige_stunden_anzahl"].value
    )
    # Rang-Profil + Günstig-Schwelle reisen als Attribute mit.
    profil = by_key["eedc_preis_rang"].zusatz_attribute["rang_profil"]
    assert profil and all("stunde" in e and "rang" in e for e in profil)
    assert by_key["eedc_preis_rang"].zusatz_attribute["guenstig_schwelle_cent"] > 0


# ── #335: die drei Werte für eigene Preis-Regeln ────────────────────────────

async def test_preis_und_durchschnitt_werden_exportiert(db, _patch_preis):
    """Aktueller Preis, optimierter Ø und ihr Abstand verlassen eedc.

    rapahls Wunsch (PN 05.08., zweite Äußerung): „ein Sensor, der sagt, ob der
    aktuelle Börsenpreis über oder unter dem optimierten Ø liegt" — Grundlage
    einer Nicht-Entlade-Regel. Bis v4.0 lieferte der Export nur Ø × Faktor.
    """
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = await _seed_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    # Fake-Kurve 2/5/8/11/14/17 ct je 4× → Ø ohne 3 Peaks = 177/21 ≈ 8,43 ct.
    o = by_key["eedc_preis_optimierter_durchschnitt_cent"].value
    assert o == pytest.approx(177.0 / 21.0, abs=0.01)
    aktuell = by_key["eedc_preis_aktuell_cent"].value
    assert aktuell in {2.0, 5.0, 8.0, 11.0, 14.0, 17.0}

    # Der Abstand ist die Aussage „über/unter" — und stimmt mit den beiden
    # Absolutwerten überein, statt eine dritte Rechnung zu sein.
    abstand = by_key["eedc_preis_abstand_prozent"].value
    assert abstand == pytest.approx((aktuell - o) / abs(o) * 100.0, abs=0.01)
    assert (abstand < 0) is (aktuell < o)

    # Die Bezugsgröße reist auch als Attribut mit dem Rang-Sensor.
    assert by_key["eedc_preis_rang"].zusatz_attribute[
        "optimierter_durchschnitt_cent"
    ] == pytest.approx(o, abs=0.01)


async def test_rang_profil_traegt_preis_und_unter_schwelle(db, _patch_preis):
    """Das Profil liefert Rohmaterial statt nur einer fertigen Zerlegung (N-105).

    Die Sensor-Referenz bietet an, per Template „direkt auf den Attributen"
    eine eigene Schwelle zu rechnen. Mit Rängen 1–5/99 allein ging das nicht —
    weder eine strengere noch eine lockerere Schwelle ist ohne die
    Stundenpreise rekonstruierbar.
    """
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = await _seed_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    attrs = by_key["eedc_preis_rang"].zusatz_attribute
    profil = attrs["rang_profil"]
    assert len(profil) == 24
    assert all(e["preis_cent"] is not None for e in profil)
    assert {e["preis_cent"] for e in profil} == {2.0, 5.0, 8.0, 11.0, 14.0, 17.0}

    # Die Markierung ist am Preis nachvollziehbar — und ungekappt: sie zählt
    # dieselbe Zahl wie der Sensor.
    schwelle = attrs["guenstig_schwelle_cent"]
    assert all(e["unter_schwelle"] == (e["preis_cent"] <= schwelle) for e in profil)
    assert (
        sum(1 for e in profil if e["unter_schwelle"])
        == by_key["eedc_preis_guenstige_stunden_anzahl"].value
    )


async def test_guenstige_stunden_ungekappt_im_export(db, _patch_preis):
    """Der Sensor meldet mehr als 5 je Fenster, wenn mehr günstig sind (N-103).

    Kurve: 8 Stunden à 1 ct verteilt über den ganzen Tag, der Rest 20 ct →
    Ø ohne 3 Peaks = 268/21 ≈ 12,8 ct. Alle acht liegen darunter, und mehr als
    fünf davon fallen in dasselbe Fenster.
    """
    import backend.services.strompreis_markt_service as smp
    from backend.api.routes.ha_export import calculate_anlage_sensors

    async def billige_nacht(datum, markt="DE", timeout=15.0):
        # Stunden 0–7 billig — im Sommer wie im Winter überwiegend Nacht.
        return {h: (1.0 if h < 8 else 20.0) for h in range(24)}

    import pytest as _pytest
    monkeypatch = _pytest.MonkeyPatch()
    monkeypatch.setattr(smp, "fetch_marktpreise", billige_nacht)
    try:
        anlage = await _seed_anlage(db)
        sensors = await calculate_anlage_sensors(db, anlage)
        by_key = {sv.definition.key: sv for sv in sensors}
        assert by_key["eedc_preis_guenstige_stunden_anzahl"].value == 8
        assert (
            by_key["eedc_preis_guenstige_stunden_tag"].value
            + by_key["eedc_preis_guenstige_stunden_nacht"].value == 8
        )
        # Der Rang bleibt gedeckelt: höchstens 5 je Fenster tragen 1–5.
        profil = by_key["eedc_preis_rang"].zusatz_attribute["rang_profil"]
        assert sum(1 for e in profil if e["rang"] <= GUENSTIG_TOP_N) <= 2 * GUENSTIG_TOP_N
    finally:
        monkeypatch.undo()


async def test_guenstig_schwelle_pro_anlage_einstellbar(db, _patch_preis):
    """Anlage.guenstig_schwelle_prozent steuert das Günstig-Gating der Sensoren.

    Fake-Kurve: 2/5/8/11/14/17 ct je 4×; Ø ohne 3 Peaks = 177/21 ≈ 8,43 ct.
    Mit 45 % Schwelle (Faktor 0,55 → 4,64 ct) bleiben nur die vier
    2-ct-Stunden günstig — unabhängig vom saisonalen Tag/Nacht-Fenster,
    weil je Fenster höchstens 4 Kandidaten übrig sind (< Top-5-Kappung).
    """
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = await _seed_anlage(db)
    anlage.guenstig_schwelle_prozent = 45.0
    await db.flush()

    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    schwelle = by_key["eedc_preis_rang"].zusatz_attribute["guenstig_schwelle_cent"]
    assert schwelle == pytest.approx((177.0 / 21.0) * 0.55, abs=0.01)
    assert by_key["eedc_preis_guenstige_stunden_anzahl"].value == 4
