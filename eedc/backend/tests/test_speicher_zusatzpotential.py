"""Die Potential-Kennzahl darf nicht mehr versprechen, als der Speicher gebracht hätte.

**Der Anlass ist eine Messung, keine Theorie** (#358 Phase 2, 2026-08-12): An zwölf
Junitagen der Dev-Anlage weist die Konzept-Formel 471 kWh „ungenutztes Potential"
aus, während der Speicher in keiner dieser Nächte unter 31 % fiel — der reale
Nutzen zusätzlicher Kapazität war dort **null**. Die Tests halten genau diesen
Unterschied fest; der erste rechnet mit den gemessenen Werten des 11.08.
"""

import pytest

from backend.core.berechnungen.speicher_potential import (
    SOC_LEER_PROZENT,
    SOC_VOLL_PROZENT,
    SpeicherStunde,
    berechne_zusatzpotential,
)


def _reihe(*tripel) -> list[SpeicherStunde]:
    """(soc, einspeisung, netzbezug) je Stunde — in dieser Reihenfolge."""
    return [SpeicherStunde(soc_prozent=s, einspeisung_kwh=e, netzbezug_kwh=n) for s, e, n in tripel]


def test_voller_speicher_der_nachts_nicht_leer_wird_bringt_null():
    """Der gemessene Normalfall der Dev-Anlage — und der Grund für die Deckelung.

    Nachgebildet nach dem 11.08.2026: acht Stunden auf 100 % mit 64 kWh
    Einspeisung, danach eine Nacht, in der der Speicher nur bis 37,8 % abgibt.
    Die naive Summe sagt 64 kWh, der Nutzen ist 0 — der Speicher war groß genug.
    """
    stunden = _reihe(
        *[(100.0, 8.0, 0.0) for _ in range(8)],      # Mittag: voll, 64 kWh ins Netz
        *[(70.0, 0.0, 0.5) for _ in range(6)],       # Abend/Nacht: gibt ab, Netz stützt etwas
        *[(37.8, 0.0, 0.5) for _ in range(4)],       # Morgen: 37,8 % — nie leer
    )

    ergebnis = berechne_zusatzpotential(stunden)

    assert ergebnis.ueberschuss_gesamt_kwh == pytest.approx(64.0)
    assert ergebnis.nutzbares_zusatzpotential_kwh == 0.0
    assert ergebnis.zyklen_leergelaufen == 0
    assert ergebnis.deckelung_greift, "die Sicht muss sagen können, dass gedeckelt wurde"


def test_leergelaufener_speicher_deckelt_auf_den_nachtbezug():
    """Läuft er leer, zählt der Netzbezug **danach** — und nur der.

    12 kWh Überschuss am Tag, aber nach dem Leerlaufen nur 5 kWh aus dem Netz:
    mehr Kapazität hätte 5 kWh durchgesetzt, nicht 12.
    """
    stunden = _reihe(
        (100.0, 6.0, 0.0),
        (100.0, 6.0, 0.0),
        (40.0, 0.0, 0.0),      # gibt noch selbst ab — hier hilft mehr Kapazität nicht
        (3.0, 0.0, 2.0),       # leer, ab jetzt zählt der Bezug
        (2.0, 0.0, 3.0),
    )

    ergebnis = berechne_zusatzpotential(stunden)

    assert ergebnis.ueberschuss_gesamt_kwh == pytest.approx(12.0)
    assert ergebnis.nutzbares_zusatzpotential_kwh == pytest.approx(5.0)
    assert ergebnis.zyklen_leergelaufen == 1


def test_bezug_vor_dem_leerlaufen_zaehlt_nicht():
    """Solange der vorhandene Speicher liefert, belegt Netzbezug keine Lücke.

    Sonst würde jede Stunde mit gleichzeitigem Bezug und Entladung (Lastspitze
    über der Speicherleistung) als „hätte mehr Kapazität gebraucht" gelten —
    das ist aber eine Leistungs-, keine Kapazitätsfrage.
    """
    stunden = _reihe(
        (100.0, 10.0, 0.0),
        (60.0, 0.0, 4.0),      # Lastspitze: Bezug trotz halbvollem Speicher
        (30.0, 0.0, 4.0),
    )

    ergebnis = berechne_zusatzpotential(stunden)

    assert ergebnis.nutzbares_zusatzpotential_kwh == 0.0
    assert not ergebnis.zyklen[0].lief_leer


def test_ueberschuss_deckelt_die_fehlmenge_wenn_er_kleiner_ist():
    """Die Deckelung schneidet in beide Richtungen.

    Im Winter ist es umgekehrt: der Speicher läuft jede Nacht leer, es gäbe also
    Bedarf — aber es kam kaum Überschuss an, den er hätte aufnehmen können.
    """
    stunden = _reihe(
        (96.0, 1.5, 0.0),      # magerer Wintertag: 1,5 kWh Überschuss
        (20.0, 0.0, 0.0),
        (0.0, 0.0, 9.0),       # leer, lange Nacht, viel Netzbezug
        (0.0, 0.0, 9.0),
    )

    ergebnis = berechne_zusatzpotential(stunden)

    assert ergebnis.nutzbares_zusatzpotential_kwh == pytest.approx(1.5)
    assert ergebnis.zyklen[0].fehlmenge_kwh == pytest.approx(18.0)


def test_zwei_zyklen_werden_getrennt_bewertet():
    """Jeder Überschuss wird an SEINER Nacht gemessen, nicht an der Summe.

    Sonst würde ein einzelner leergelaufener Tag die Überschüsse aller anderen
    Tage rechtfertigen — genau die Vermischung, die eine Zeitraum-Summe
    nahelegt.
    """
    stunden = _reihe(
        (100.0, 10.0, 0.0),    # Zyklus 1: viel Überschuss …
        (50.0, 0.0, 1.0),      # … Nacht ohne Leerlaufen ⇒ 0 nutzbar
        (100.0, 4.0, 0.0),     # Zyklus 2: weniger Überschuss …
        (2.0, 0.0, 3.0),       # … aber leergelaufen ⇒ 3 nutzbar
    )

    ergebnis = berechne_zusatzpotential(stunden)

    assert ergebnis.zyklen_gesamt == 2
    assert ergebnis.ueberschuss_gesamt_kwh == pytest.approx(14.0)
    assert ergebnis.nutzbares_zusatzpotential_kwh == pytest.approx(3.0)


def test_stunden_ohne_soc_belegen_weder_voll_noch_leer():
    """Ein fehlender SoC ist nicht 0 — sonst erfindet eine Messlücke Bedarf.

    Die P4-Linie: aus „unbekannt" darf nicht „war leer" werden.
    """
    stunden = _reihe(
        (100.0, 5.0, 0.0),
        (None, 0.0, 4.0),      # Messlücke — kein Leerlaufen
        (None, 0.0, 4.0),
    )

    ergebnis = berechne_zusatzpotential(stunden)

    assert ergebnis.nutzbares_zusatzpotential_kwh == 0.0
    assert ergebnis.zyklen_leergelaufen == 0


def test_bezug_vor_dem_ersten_ueberschuss_zaehlt_nicht():
    """Der Zeitraum-Anfang darf keine Fehlmenge erfinden.

    Beginnt die Reihe mit einem leeren Speicher, gab es davor keinen Überschuss,
    den er hätte aufnehmen können — die Nacht davor liegt außerhalb des Fensters.
    """
    stunden = _reihe(
        (0.0, 0.0, 5.0),
        (0.0, 0.0, 5.0),
        (100.0, 2.0, 0.0),
    )

    ergebnis = berechne_zusatzpotential(stunden)

    assert ergebnis.nutzbares_zusatzpotential_kwh == 0.0
    assert ergebnis.zyklen_gesamt == 1


def test_leere_reihe_liefert_nullen_statt_zu_werfen():
    ergebnis = berechne_zusatzpotential([])

    assert ergebnis.nutzbares_zusatzpotential_kwh == 0.0
    assert ergebnis.zyklen_gesamt == 0
    assert not ergebnis.deckelung_greift


def test_schwellen_sind_benannt_und_nicht_symmetrisch_gemeint():
    """Die beiden Grenzen haben verschiedene Gründe — sie dürfen sich trennen.

    Oben flacht der Hersteller-SoC durch Balancing ab, unten liegt die
    Entladetiefe-Reserve. Wer eine der beiden anpasst, soll die andere nicht
    mitziehen müssen.
    """
    assert SOC_VOLL_PROZENT == 95.0
    assert SOC_LEER_PROZENT == 5.0
