"""N-552: Der SoC-Hub zweier Stundenmittel gehört gegen ZWEI halbe Stunden.

**Der Befund** (Nebenfund des N-387-Baus, 23.09.2026): `kalibriere_speicher`
stellte die Differenz zweier Ladestände einer **einzelnen** Stundenmenge
gegenüber. Beide Ladestände sind aber Stunden**mittel** — ihre Differenz
beschreibt den Fluss zwischen den Intervall-Mitten, also je zur Hälfte
``[s-1, s)`` und ``[s, s+1)``. Die Ein-Stunden-Formel lag eine halbe Stunde
daneben; an einem echten Jahr trieben steile Ladeanfänge den Roundtrip auf
82–88 %, je nach Zeitraum.

**Gemessen** (Prod-Anlage, Reihe 2025-09-22…2026-09-22): Der Hub korreliert mit
``½ (b[s] + b[s+1])`` zu 0,98, mit ``b[s]`` zu 0,95; bis Dezember 2025 tragen
die Zeilen die Altkonvention und korrelieren mit ``½ (b[s-1] + b[s])``. Die
Validierung gegen gemessene Einspeisung und Netzbezug fällt von 4,9 auf 3,3 pp,
der Roundtrip bleibt über Schwellen und Halbjahre stabil bei 72–74 %. Tabelle
und Schwellen-Entscheid stehen am Layer.

Die Proben hier bauen Reihen in der **Konvention echter Daten**: Ladestand als
Mittel über ``[s, s+1)``, Energie je nach Zeile backward oder forward. Mit
bekannter Wahrheit muss die Kalibrierung **exakt** treffen.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.core.berechnungen.speicher_sizing import (
    MIN_PAARE_JE_SEITE, SizingStunde, _hub_energie, _ist_bilanzkonsistent, kalibriere_speicher,
)

START = datetime(2026, 8, 3, 0, 0)
KAP_LADE = 10.0      # kWh je 100 % SoC hinein
KAP_ENTLADE = 9.0    # kWh je 100 % SoC heraus ⇒ Roundtrip 0,9


def _zeile(zeit: datetime, batterie: float, soc: float, *, kw_backward: bool = True,
           bilanz_ok: bool = True) -> SizingStunde:
    """Eine bilanzkonsistente Zeile: Ladung kommt aus PV, Entladung geht in den Verbrauch.

    ``bilanz_ok=False`` bricht die Bilanz über einen **Netzbezug, der nicht
    aufgeht** — nicht über das Vorzeichen der Batterie. Ein gedrehtes Vorzeichen
    hätte in der Folgezeilen-Probe den Richtungsfilter ausgelöst, und die Probe
    wäre grün geblieben, ohne dass die Bilanzprobe überhaupt geprüft wurde
    (gemessen am Sprengsatz, 23.09.2026).
    """
    pv, verbrauch = (-batterie, 0.0) if batterie < 0 else (0.0, batterie)
    return SizingStunde(
        zeit=zeit, pv_kwh=pv, verbrauch_kwh=verbrauch, soc_prozent=soc,
        batterie_kwh=batterie,
        einspeisung_kwh=0.0, netzbezug_kwh=0.0 if bilanz_ok else 2.0, kw_backward=kw_backward,
    )


def _reihe(zyklen: int, *, kw_backward: bool = True) -> list[SizingStunde]:
    """Je Zyklus: Ruhe, zwei Ladestunden, Ruhe, zwei Entladestunden — je 25 pp.

    Der Fluss liegt je Wanduhr-Stunde ``[h, h+1)``; die Zeile ``s`` trägt ihn
    backward (``[s-1, s)``) oder forward (``[s, s+1)``), den Ladestand immer als
    Mittel über ``[s, s+1)``.
    """
    ein, aus = KAP_LADE * 0.25, KAP_ENTLADE * 0.25
    fluss: list[float] = []
    for _ in range(zyklen):
        fluss += [0.0, -ein, -ein, 0.0, aus, aus]
    zustand = [20.0]
    for f in fluss + [0.0]:
        delta = -f / KAP_LADE * 100 if f < 0 else -f / KAP_ENTLADE * 100 if f > 0 else 0.0
        zustand.append(zustand[-1] + delta)
    zeilen = []
    for s in range(len(fluss) + 1):
        if kw_backward:
            f = fluss[s - 1] if s >= 1 else 0.0
        else:
            f = fluss[s] if s < len(fluss) else 0.0
        zeilen.append(_zeile(START + timedelta(hours=s), f, (zustand[s] + zustand[s + 1]) / 2,
                             kw_backward=kw_backward))
    return zeilen


# ------------------------------------------------------------- Wahrheit --

@pytest.mark.parametrize("kw_backward", [True, False], ids=["backward", "forward-Altbestand"])
def test_die_kalibrierung_trifft_die_wahrheit_exakt(kw_backward):
    """Beide Konventionen, dieselbe Wahrheit: 10,0 hinein, 9,0 heraus, Roundtrip 0,9."""
    k = kalibriere_speicher(_reihe(10, kw_backward=kw_backward))

    assert k is not None
    assert k.ladung_je_100_prozent_kwh == pytest.approx(KAP_LADE, abs=1e-9)
    assert k.kapazitaet_kwh == pytest.approx(KAP_ENTLADE, abs=1e-9)
    assert k.roundtrip == pytest.approx(0.9, abs=1e-9)
    assert k.paare_laden >= MIN_PAARE_JE_SEITE and k.paare_entladen >= MIN_PAARE_JE_SEITE


def test_die_konvention_je_zeile_entscheidet():
    """Dieselbe backward-Reihe, als forward markiert, verfehlt — deshalb die
    Unterscheidung je Zeile und keine Formel für beide."""
    falsch = [SizingStunde(**{**z.__dict__, "kw_backward": False}) for z in _reihe(10)]

    k = kalibriere_speicher(falsch)

    assert k is None or abs(k.kapazitaet_kwh - KAP_ENTLADE) > 0.5 \
        or abs(k.ladung_je_100_prozent_kwh - KAP_LADE) > 0.5


# ------------------------------------------------- die Paarbildung, einzeln --

def _drei(b1: float, b2: float, b3: float, **kw) -> list[SizingStunde]:
    return [_zeile(START + timedelta(hours=h), b, 50.0, **kw) for h, b in enumerate((b1, b2, b3))]


def _k(zeilen):
    return [_ist_bilanzkonsistent(z) for z in zeilen]


def test_backward_nimmt_diese_und_die_folgezeile():
    z = _drei(0.0, -2.0, -4.0)
    assert _hub_energie(z, _k(z), 1) == pytest.approx(-3.0)


def test_forward_nimmt_vorzeile_und_diese():
    z = _drei(-2.0, -4.0, 0.0, kw_backward=False)
    assert _hub_energie(z, _k(z), 1) == pytest.approx(-3.0)


def test_eine_ruhende_haelfte_zaehlt_mit_null():
    z = _drei(0.0, -2.0, 0.0)
    assert _hub_energie(z, _k(z), 1) == pytest.approx(-1.0)


def test_gegenlaeufige_haelften_sind_kein_paar():
    """Eine lädt, die andere entlädt: der Hub mischt zwei Wirkungsgrade."""
    z = _drei(0.0, -2.0, 1.5)
    assert _hub_energie(z, _k(z), 1) is None


def test_ohne_folgezeile_kein_paar():
    z = _drei(0.0, -2.0, -4.0)[:2]
    assert _hub_energie(z, _k(z), 1) is None


def test_folgezeile_mit_luecke_ist_kein_paar():
    z = _drei(0.0, -2.0, -4.0)
    z[2] = SizingStunde(**{**z[2].__dict__, "zeit": z[2].zeit + timedelta(hours=1)})
    assert _hub_energie(z, _k(z), 1) is None


def test_folgezeile_ohne_bilanz_ist_kein_paar():
    z = _drei(0.0, -2.0, -4.0)
    z[2] = _zeile(z[2].zeit, -4.0, 50.0, bilanz_ok=False)
    assert _hub_energie(z, _k(z), 1) is None


def test_konventionswechsel_zwischen_den_haelften_ist_kein_paar():
    z = _drei(0.0, -2.0, -4.0)
    z[2] = SizingStunde(**{**z[2].__dict__, "kw_backward": False})
    assert _hub_energie(z, _k(z), 1) is None
    f = _drei(-2.0, -4.0, 0.0, kw_backward=False)
    f[0] = SizingStunde(**{**f[0].__dict__, "kw_backward": True})
    assert _hub_energie(f, _k(f), 1) is None


def test_verworfene_stunden_zaehlen_jede_stunde_einmal():
    """Eine bilanz-inkonsistente Zeile ist Folgezeile des einen und Zeile des
    nächsten Paares — gezählt wird sie genau einmal, wie vor N-552."""
    zeilen = _reihe(10)
    zeilen[8] = _zeile(zeilen[8].zeit, zeilen[8].batterie_kwh or -1.0,
                       zeilen[8].soc_prozent or 50.0, bilanz_ok=False)

    k = kalibriere_speicher(zeilen)

    assert k is not None and k.stunden_verworfen == 1


# ------------------------------------------------------------ der Adapter --

def test_der_dienst_setzt_die_konvention_je_zeile_an_der_aggregationszeit():
    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services.speicher_sizing_service import _als_sizing_stunde

    def zeile(created_at):
        return TagesEnergieProfil(anlage_id=1, datum=date(2026, 3, 10), stunde=6,
                                  batterie_kw=-1.0, soc_prozent=40.0, created_at=created_at)

    assert _als_sizing_stunde(zeile(datetime(2026, 7, 1, 3))).kw_backward is True
    assert _als_sizing_stunde(zeile(datetime(2026, 3, 11, 3))).kw_backward is False
    assert _als_sizing_stunde(zeile(None)).kw_backward is False, "ohne Schreibzeit zählt das Datum"
