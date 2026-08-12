"""Der Sizing-Simulator darf den Speichernutzen nicht überschätzen (#358 Phase 3).

Drei Dinge sind hier gegen einen konkreten, an der Prod-Anlage beobachteten
Fehlgriff gebaut und nicht bloß gegen die Theorie:

1. **Vorzeichen-Robustheit.** Die erste Fassung der Vorprüfung mischte Stunden
   mit invertiertem ``batterie_kw`` in die Kalibrierung und bekam
   **0,91 kWh/100 %** statt 8,3 — eine Anlage mit Alt-Tagen hätte damit einen
   Zwerg-Speicher simuliert und jede Erweiterung als Volltreffer gemeldet.
2. **Beide Kalibrierungs-Seiten.** Die Entladeseite ist die dünnere (n≈100 gegen
   n≈430) und zugleich die, die die Kapazität bestimmt.
3. **Spread statt Voll-Strompreis.** Der gesparte Netzbezug ist nicht der
   Nutzen — die dafür entgangene Einspeisung geht ab (Kanon Gernot 2026-08-04).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.core.berechnungen.speicher_sizing import (
    MIN_PAARE_JE_SEITE,
    Kalibrierung,
    SizingBewertung,
    SizingStunde,
    kalibriere_speicher,
    messe_soc_nutzung,
    nutzen_euro,
    simuliere_speicher,
    sizing_kurve,
)

START = datetime(2026, 3, 1, 0, 0)


def _reihe(werte, *, start: datetime = START) -> list[SizingStunde]:
    """(pv, verbrauch) je Stunde, lückenlos ab ``start``."""
    return [
        SizingStunde(zeit=start + timedelta(hours=i), pv_kwh=pv, verbrauch_kwh=vb)
        for i, (pv, vb) in enumerate(werte)
    ]


# --------------------------------------------------------------- Simulation --


def test_ohne_speicher_ist_die_bilanz_direkt():
    """Der untere Anker der Kurve: 0 kWh Kapazität = Überschuss geht ins Netz."""
    stunden = _reihe([(5.0, 1.0), (0.0, 3.0)])

    ergebnis = simuliere_speicher(stunden, kap_kwh=0.0, eta=0.85)

    assert ergebnis.einspeisung_kwh == pytest.approx(4.0)
    assert ergebnis.netzbezug_kwh == pytest.approx(3.0)
    assert ergebnis.eigenverbrauch_kwh == pytest.approx(1.0)
    assert ergebnis.speicherverluste_kwh == pytest.approx(0.0)


def test_der_wirkungsgrad_sitzt_auf_der_ladeseite():
    """4 kWh Überschuss bei η = 0,5 füllen 2 kWh — und 2 kWh sind Verlust.

    Der Gegenentwurf (η beim Entladen) würde hier 4 kWh einlagern und 2 kWh
    abgeben: dieselbe Verlustmenge, aber ein doppelt so großer nutzbarer
    Speicher. Weil die Kalibrierung die Kapazität auf der **Entladeseite** misst,
    ist nur diese Variante mit ihr konsistent.
    """
    stunden = _reihe([(5.0, 1.0), (0.0, 3.0)])

    ergebnis = simuliere_speicher(stunden, kap_kwh=10.0, eta=0.5, start_soc_anteil=0.0)

    assert ergebnis.einspeisung_kwh == pytest.approx(0.0)
    assert ergebnis.netzbezug_kwh == pytest.approx(1.0), "2 kWh im Speicher decken von 3 kWh"
    assert ergebnis.speicherverluste_kwh == pytest.approx(2.0)


def test_die_kapazitaet_deckelt_die_aufnahme():
    """Was nicht mehr hineinpasst, geht ins Netz — auch bei perfektem η."""
    stunden = _reihe([(9.0, 1.0), (0.0, 2.0)])

    ergebnis = simuliere_speicher(stunden, kap_kwh=3.0, eta=1.0, start_soc_anteil=0.0)

    assert ergebnis.einspeisung_kwh == pytest.approx(5.0), "8 kWh Überschuss, 3 passen hinein"
    assert ergebnis.netzbezug_kwh == pytest.approx(0.0)


def test_mehr_kapazitaet_senkt_beides_und_niemals_nur_eines():
    """Die Monotonie, an der die Kurve hängt — und der Grund für den Spread.

    Der größere Speicher senkt den Netzbezug **und** die Einspeisung. Beide
    Deltas sind ungleich groß (die Differenz ist der Roundtrip-Verlust); wer nur
    das Netzbezugs-Delta bewertet, verkauft die Verluste als Gewinn.
    """
    stunden = _reihe([(6.0, 1.0), (6.0, 1.0), (0.0, 4.0), (0.0, 4.0)])

    klein = simuliere_speicher(stunden, kap_kwh=2.0, eta=0.85, start_soc_anteil=0.0)
    gross = simuliere_speicher(stunden, kap_kwh=8.0, eta=0.85, start_soc_anteil=0.0)

    assert gross.netzbezug_kwh < klein.netzbezug_kwh
    assert gross.einspeisung_kwh < klein.einspeisung_kwh
    d_netz = klein.netzbezug_kwh - gross.netzbezug_kwh
    d_ein = klein.einspeisung_kwh - gross.einspeisung_kwh
    assert d_ein > d_netz, "die Differenz ist genau der Roundtrip-Verlust"


def test_stunde_ohne_eingang_wird_uebersprungen_statt_als_null_gerechnet():
    """Eine Lücke ist keine Stunde mit 0 kWh Verbrauch."""
    stunden = _reihe([(5.0, 1.0), (0.0, 2.0)])
    stunden.insert(1, SizingStunde(zeit=START + timedelta(minutes=30), pv_kwh=None, verbrauch_kwh=None))

    ergebnis = simuliere_speicher(stunden, kap_kwh=10.0, eta=1.0)

    assert ergebnis.stunden_ohne_eingang == 1
    assert ergebnis.pv_kwh == pytest.approx(5.0)
    assert ergebnis.verbrauch_kwh == pytest.approx(3.0)


# ------------------------------------------------------------- Kalibrierung --


def _kalibrier_reihe(
    *, kap_kwh: float, roundtrip: float, paare: int, invertiert: bool = False,
    start: datetime = START,
) -> list[SizingStunde]:
    """Baut eine bilanzkonsistente Reihe mit abwechselnd Lade- und Entladepaaren.

    Je „Paar" eine Ruhestunde (Referenz-SoC) und eine Bewegungsstunde mit 25 pp
    Hub. Die Bewegungsstunde trägt alle fünf Bilanz-Summanden, damit die
    Vorzeichen-Probe greifen kann — bei ``invertiert`` mit gedrehtem
    ``batterie_kwh``, also genau dem Alt-Tag-Regime.
    """
    hub = 25.0
    ein_kwh = kap_kwh * hub / 100.0 / roundtrip   # Ladung: rein
    aus_kwh = kap_kwh * hub / 100.0              # Entladung: raus
    zeilen: list[SizingStunde] = []
    zeit = start
    for i in range(paare):
        laden = i % 2 == 0
        soc_vor, soc_nach = (30.0, 55.0) if laden else (55.0, 30.0)
        batterie = -ein_kwh if laden else aus_kwh
        # Bilanz: pv − verbrauch + batterie = einspeisung − netzbezug.
        pv, verbrauch = (ein_kwh, 0.0) if laden else (0.0, aus_kwh)
        zeilen.append(SizingStunde(
            zeit=zeit, pv_kwh=0.0, verbrauch_kwh=0.0, soc_prozent=soc_vor,
            batterie_kwh=0.0, einspeisung_kwh=0.0, netzbezug_kwh=0.0,
        ))
        zeilen.append(SizingStunde(
            zeit=zeit + timedelta(hours=1),
            pv_kwh=pv, verbrauch_kwh=verbrauch, soc_prozent=soc_nach,
            batterie_kwh=-batterie if invertiert else batterie,
            einspeisung_kwh=0.0, netzbezug_kwh=0.0,
        ))
        zeit += timedelta(hours=2)
    return zeilen


def test_kalibrierung_findet_kapazitaet_und_roundtrip():
    """8,3 kWh effektiv / 84,6 % Roundtrip — die Zahlen der Vorprüfung.

    Der Roundtrip deckt sich mit dem η ≈ 84 %, das die unabhängige
    Kumulativ-Rechnung (Journal `91eec676`) für dieselbe Anlage liefert.
    """
    stunden = _kalibrier_reihe(kap_kwh=8.3, roundtrip=0.846, paare=2 * MIN_PAARE_JE_SEITE)

    kalibrierung = kalibriere_speicher(stunden)

    assert kalibrierung is not None
    assert kalibrierung.kapazitaet_kwh == pytest.approx(8.3, abs=0.05)
    assert kalibrierung.roundtrip == pytest.approx(0.846, abs=0.005)
    assert kalibrierung.paare_laden >= MIN_PAARE_JE_SEITE
    assert kalibrierung.paare_entladen >= MIN_PAARE_JE_SEITE


def test_invertierte_vorzeichen_stunden_werden_verworfen_statt_gemischt():
    """Der reproduzierte Fehlgriff: Alt-Tage kippen die Kalibrierung.

    Die Alt-Hälfte trägt ein invertiertes ``batterie_kwh`` und ist damit
    bilanz-inkonsistent. Ohne die Probe landen Lade- und Entladewerte in
    denselben beiden Töpfen und der Median rutscht ins Nichts; mit der Probe
    bleibt die korrigierte Hälfte übrig — und die stimmt.
    """
    alt = _kalibrier_reihe(
        kap_kwh=8.3, roundtrip=0.846, paare=2 * MIN_PAARE_JE_SEITE, invertiert=True,
    )
    neu = _kalibrier_reihe(
        kap_kwh=8.3, roundtrip=0.846, paare=2 * MIN_PAARE_JE_SEITE,
        start=alt[-1].zeit + timedelta(hours=1),
    )

    kalibrierung = kalibriere_speicher(alt + neu)

    assert kalibrierung is not None
    assert kalibrierung.kapazitaet_kwh == pytest.approx(8.3, abs=0.05)
    assert kalibrierung.stunden_verworfen == 2 * MIN_PAARE_JE_SEITE, (
        "jede invertierte Bewegungsstunde muss gezählt und verworfen werden"
    )


def test_kalibrierung_ohne_entladeseite_liefert_none():
    """n≈430 Ladepaare belegen die Kapazität nicht — die misst die Entladeseite."""
    nur_laden = [
        z for z in _kalibrier_reihe(kap_kwh=8.3, roundtrip=0.846, paare=4 * MIN_PAARE_JE_SEITE)
        if (z.batterie_kwh or 0) <= 0
    ]
    # Die Paar-Bildung braucht Nachbarschaft; hier bleibt sie erhalten, weil nur
    # die Entlade-Bewegungsstunden entfernt wurden.
    assert kalibriere_speicher(nur_laden) is None


def test_zu_duenne_basis_liefert_none_statt_einer_zahl():
    stunden = _kalibrier_reihe(kap_kwh=8.3, roundtrip=0.846, paare=4)

    assert kalibriere_speicher(stunden) is None


def test_unmoeglicher_roundtrip_liefert_none():
    """Mehr heraus als hinein ist kein guter Speicher, sondern ein Datenfehler."""
    stunden = _kalibrier_reihe(kap_kwh=8.3, roundtrip=1.3, paare=2 * MIN_PAARE_JE_SEITE)

    assert kalibriere_speicher(stunden) is None


def test_paare_ueber_eine_luecke_hinweg_zaehlen_nicht():
    """Zwischen zwei Stunden muss genau eine Stunde liegen — sonst kein Paar.

    Ohne diese Prüfung dominieren die SoC-Sprünge an Tages- und Lückengrenzen
    das Ergebnis; das ist derselbe Grund, aus dem hier der Median steht und
    keine Ausgleichsrechnung.
    """
    stunden = _kalibrier_reihe(kap_kwh=8.3, roundtrip=0.846, paare=2 * MIN_PAARE_JE_SEITE)
    zerrissen = [
        SizingStunde(
            zeit=z.zeit + timedelta(hours=5 * i), pv_kwh=z.pv_kwh, verbrauch_kwh=z.verbrauch_kwh,
            soc_prozent=z.soc_prozent, batterie_kwh=z.batterie_kwh,
            einspeisung_kwh=z.einspeisung_kwh, netzbezug_kwh=z.netzbezug_kwh,
        )
        for i, z in enumerate(stunden)
    ]

    assert kalibriere_speicher(zerrissen) is None


# ------------------------------------------------------------ Sizing-Kurve --


def test_der_nutzen_ist_der_spread_nicht_der_bezugspreis():
    """185 kWh weniger Bezug, 216 kWh weniger Einspeisung — die Zahlen der Kurve.

    Zum Voll-Strompreis (35 ct) wären das 64,75 €. Nach dem Spread-Kanon bleiben
    bei 8 ct Vergütung **47,47 €** — die entgangene Einspeisung geht ab. Genau
    diese Verwechslung stand v4.0.5 in `aktueller_monat.py` und war dort 36 %
    zu hoch.
    """
    bewertung = SizingBewertung(
        bezug_preis_cent=35.0, einspeise_verg_cent=8.0, tage_im_zeitraum=365,
    )

    assert nutzen_euro(-185.0, -216.0, bewertung) == pytest.approx(47.47, abs=0.01)
    assert -185.0 * -0.35 == pytest.approx(64.75), "die Zahl, die es NICHT ist"


def test_kurve_bezieht_alles_auf_die_heutige_kapazitaet():
    stunden = _reihe([(6.0, 1.0), (6.0, 1.0), (0.0, 4.0), (0.0, 4.0)] * 10)
    basis = Kalibrierung(
        kapazitaet_kwh=8.0, ladung_je_100_prozent_kwh=9.5, roundtrip=0.85,
        paare_laden=100, paare_entladen=50, stunden_verworfen=0,
    )

    punkte = sizing_kurve(stunden, basis, [0.5, 1.0, 1.5])

    heute = next(p for p in punkte if p.faktor == 1.0)
    assert heute.kapazitaet_kwh == pytest.approx(8.0)
    assert heute.delta_netzbezug_kwh == pytest.approx(0.0)
    assert heute.delta_einspeisung_kwh == pytest.approx(0.0)
    kleiner = next(p for p in punkte if p.faktor == 0.5)
    assert kleiner.delta_netzbezug_kwh > 0, "weniger Speicher = mehr Netzbezug"


def test_ohne_bewertung_bleiben_die_euro_felder_leer():
    """Eine Anlage ohne Tarif bekommt die Energie-Kurve, keine erfundenen Preise."""
    stunden = _reihe([(6.0, 1.0), (0.0, 4.0)] * 10)
    basis = Kalibrierung(8.0, 9.5, 0.85, 100, 50, 0)

    punkte = sizing_kurve(stunden, basis, [1.0, 1.5])

    assert all(p.nutzen_euro_jahr is None for p in punkte)
    assert all(p.amortisation_jahre is None for p in punkte)


def test_teilzeitraum_wird_auf_das_jahr_hochgerechnet():
    """Ein halbes Jahr Historie darf keinen halben Jahresnutzen ausweisen."""
    stunden = _reihe([(6.0, 1.0), (6.0, 1.0), (0.0, 4.0), (0.0, 4.0)] * 10)
    basis = Kalibrierung(8.0, 9.5, 0.85, 100, 50, 0)

    ganz = sizing_kurve(stunden, basis, [1.5], bewertung=SizingBewertung(35.0, 8.0, 365))
    halb = sizing_kurve(stunden, basis, [1.5], bewertung=SizingBewertung(35.0, 8.0, 182))

    assert halb[0].nutzen_euro_jahr == pytest.approx(ganz[0].nutzen_euro_jahr * 365 / 182)


def test_amortisation_nur_bei_echtem_nutzen():
    """Ohne Nutzen keine Jahreszahl — „unendlich" ist keine Amortisationsdauer."""
    stunden = _reihe([(1.0, 1.0)] * 48)   # nie Überschuss, nie Defizit
    basis = Kalibrierung(8.0, 9.5, 0.85, 100, 50, 0)

    punkte = sizing_kurve(
        stunden, basis, [2.0], bewertung=SizingBewertung(35.0, 8.0, 2),
    )

    assert punkte[0].nutzen_euro_jahr == pytest.approx(0.0)
    assert punkte[0].mehrkosten_euro == pytest.approx(8.0 * 500.0)
    assert punkte[0].amortisation_jahre is None


# ----------------------------------------------------- Wirkungsgrad (N-238) --


def test_tages_simulation_meldet_voll_spaeter_wenn_verluste_zaehlen():
    """N-238: verlustfrei gerechnet ist der Speicher zu früh voll.

    Der eigentliche Befund hinter N-238, und er hängt an keiner
    Kapazitäts-Debatte: `simuliere_speicher_tag` rechnete den Ladeweg
    **verlustfrei**. Um 10 kWh einzulagern, braucht es bei η = 50 % aber
    20 kWh Überschuss — der Sensor `eedc_speicher_voll_um` und die Kachel
    „Speicher voll" meldeten dadurch systematisch zu früh.
    """
    from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag

    pv = [0.0] * 6 + [2.0] * 12 + [0.0] * 6      # 24 kWh über den Tag
    verbrauch = [0.0] * 24

    verlustfrei = simuliere_speicher_tag(pv, verbrauch, 10.0, 0.0)
    mit_verlust = simuliere_speicher_tag(pv, verbrauch, 10.0, 0.0, wirkungsgrad_prozent=50.0)

    assert verlustfrei.speicher_voll_um == "10:00"
    assert mit_verlust.speicher_voll_um == "15:00", (
        "mit halbem Wirkungsgrad braucht dieselbe Füllung doppelt so viel Überschuss"
    )
    # Und der Rest geht ins Netz, statt zu verschwinden: Ladung 20, Einspeisung 4.
    assert sum(b.einspeisung_kwh for b in mit_verlust.stunden_bilanz) == pytest.approx(4.0)


def test_default_bleibt_verlustfrei_damit_niemand_still_etwas_anderes_bekommt():
    """Der Default ist das Verhalten VOR N-238 — beide Produktionspfade
    übergeben den gepflegten Wert ausdrücklich."""
    from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag

    pv = [0.0] * 6 + [2.0] * 12 + [0.0] * 6
    ohne = simuliere_speicher_tag(pv, [0.0] * 24, 10.0, 0.0)
    hundert = simuliere_speicher_tag(pv, [0.0] * 24, 10.0, 0.0, wirkungsgrad_prozent=100.0)

    assert ohne.speicher_voll_um == hundert.speicher_voll_um
    assert ohne.end_soc_prozent == hundert.end_soc_prozent


# -------------------------------------------------------- SoC-Nutzung N-238 --


def _soc_reihe(tages_maxima, *, start: datetime = START) -> list[SizingStunde]:
    """Je Tag 24 Stunden, die von 5 % auf das gegebene Maximum steigen."""
    zeilen: list[SizingStunde] = []
    for tag, maximum in enumerate(tages_maxima):
        for h in range(24):
            anteil = h / 23
            zeilen.append(SizingStunde(
                zeit=start + timedelta(days=tag, hours=h),
                pv_kwh=1.0, verbrauch_kwh=0.5,
                soc_prozent=5.0 + anteil * (maximum - 5.0),
            ))
    return zeilen


def test_anlage_mit_ladegrenze_wird_als_solche_erkannt():
    """Der Fall, für den Gernot N-238 aufgemacht hat: 80-%-Ladegrenze.

    Der Speicher erreicht die Voll-Schwelle an **keinem** Tag ⇒ die Lücke
    zwischen gepflegter und gemessener Kapazität ist gewollt, nicht Verlust.
    """
    nutzung = messe_soc_nutzung(_soc_reihe([80.0] * 30))

    assert nutzung is not None
    assert nutzung.tage_bis_voll == 0
    assert nutzung.tages_max_median == pytest.approx(80.0)
    assert nutzung.laedt_planmaessig_voll is False


def test_anlage_die_durchlaedt_wird_unterschieden():
    """Die Referenzanlage: 247 von 361 Tagen bis ≥ 95 % ⇒ die Lücke ist Verlust."""
    nutzung = messe_soc_nutzung(_soc_reihe([100.0] * 20 + [60.0] * 10))

    assert nutzung is not None
    assert nutzung.tage_bis_voll == 20
    assert nutzung.anteil_tage_voll == pytest.approx(20 / 30)
    assert nutzung.laedt_planmaessig_voll is True


def test_soc_nutzung_braucht_keine_bilanzkonsistenz():
    """Ein invertiertes `batterie_kwh` verdirbt den **Ladestand** nicht.

    Die Vorzeichen-Frage betrifft die Kalibrierung; wer sie hier anwendete,
    würde einer Anlage mit Alt-Tagen die halbe Historie wegnehmen.
    """
    reihe = [
        SizingStunde(zeit=z.zeit, pv_kwh=z.pv_kwh, verbrauch_kwh=z.verbrauch_kwh,
                     soc_prozent=z.soc_prozent, batterie_kwh=None)
        for z in _soc_reihe([100.0] * 10)
    ]

    nutzung = messe_soc_nutzung(reihe)

    assert nutzung is not None and nutzung.tage_bis_voll == 10


def test_ohne_ladestand_gibt_es_keine_aussage():
    assert messe_soc_nutzung(_reihe([(1.0, 0.5)] * 24)) is None
