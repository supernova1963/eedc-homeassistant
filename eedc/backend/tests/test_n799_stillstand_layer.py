"""Erfassungs-Stillstand im Layer (N-799, Bauplan Fassung 3, E-1 … E-3; ``core/berechnungen/spannen.py``).

Die Regel rein, ohne Datenbank: ``stillstand_fenster`` (k ≥ 2 Stunden, in denen jeder erfasste Bilanz-Zähler eine
lückenlose Zeile mit unverändertem Stand hat, danach eine Stunde mit ≥ 2 Zählern mit Menge; Vorbedingung; Grob- und
Häufigkeits-Sperre), ``erbt_marke`` (Nebenachsen, E-2), ``marke_der_stunde`` (E-2/E-3 an einer Zeile, auch die doppelte
Wanduhr-Stunde) und die Helfer ``spanne_roh`` / ``spannen_gebuendelt`` / ``zeile_gebuendelt`` («n ≠ 1»). Jede Sperre hat
ihren Sprengsatz: ohne sie (Konstante gestellt) wird die Probe rot, d. h. die Lage träfe. Keine Probe liest die Uhr; die
Zeitpunkte sind absolute Sekunden (zonenfrei), nur die Umstellungsprobe rechnet in der Prozesszone und gilt in jeder.

Schwesterdateien: test_n799_stillstand_lesestelle.py (Lesestelle, Marke an den Mischzeilen, beide Lesewege),
test_zaehlerluecken_leser.py (die Helfer der Zählerlücken), test_kanal_stunden_sichten.py (``mische_spannen``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.core.berechnungen import spannen as sp
from backend.core.berechnungen.spannen import (
    SPERRE_GROB,
    SPERRE_HAEUFIG,
    StillstandFenster,
    ZaehlerReihe,
    erbt_marke,
    marke_der_stunde,
    spanne,
    spanne_roh,
    spannen_gebuendelt,
    stillstand_fenster,
    verbrauch_gebuendelt,
    zeile_gebuendelt,
)

H = 3600
T0 = 1_780_000_000 - 1_780_000_000 % H          # eine volle Stunde, zonenfrei
TAG = 24


def _reihe(rolle: str, deltas: list[float], *, ab: int = 0, fehlt: tuple[int, ...] = ()) -> ZaehlerReihe:
    """Stündliche Zeilen ab Stunde ``ab``; die erste trägt kein Δ (kein voriger Stand), ``fehlt`` = Stunden ohne Zeile
    (die Folgezeile trägt dann Spanne > 1 h)."""
    werte, vorher = [], None
    for i, d in enumerate(deltas):
        h = ab + i
        if h in fehlt:
            continue
        ts = T0 + h * H
        werte.append((ts, None, None) if vorher is None else (ts, d, ts - vorher))
        vorher = ts
    return ZaehlerReihe(rolle, tuple(werte))


def _tag_profil(stunden: int, *, stand: dict[int, int] | None = None, grob: bool = False) -> dict[str, list[float]]:
    """Deltas je Rolle über ``stunden``: PV/Einspeisung tagsüber (8–17 Uhr des Schemas), Netzbezug nachts, fein (nicht
    Vielfache von 0,1) — außer ``grob``: Netzbezug in ganzen kWh. ``stand``: Beginnstunde → k Stunden Stillstand."""
    pv, einsp, netz = [], [], []
    for h in range(stunden):
        tag = 8 <= h % TAG < 18
        pv.append(1.237 if tag else 0.0)
        einsp.append(0.413 if tag else 0.0)
        netz.append((1.0 if h % 3 == 0 else 0.0) if grob else (0.0 if tag else 0.317))
    for beginn, k in (stand or {}).items():
        nachtrag = beginn + k
        for r in (pv, einsp, netz):
            summe = sum(r[beginn:nachtrag + 1])
            for h in range(beginn, nachtrag):
                r[h] = 0.0
            r[nachtrag] = summe
    return {"pv": pv, "einspeisung": einsp, "netzbezug": netz}


def _reihen(profil: dict[str, list[float]], **kw) -> dict[str, ZaehlerReihe]:
    return {f"basis:{rolle}": _reihe(rolle, d, **kw) for rolle, d in profil.items()}


# ── die Helfer «n ≠ 1» ───────────────────────────────────────────────────────────────────────────────────────────────

def test_spanne_roh_und_der_helfer_n_ungleich_1():
    assert spanne_roh(None, "pv") == 1 and spanne_roh({"pv": 0}, "pv") == 0 and spanne_roh({"pv": 4}, "pv") == 4
    assert spanne_roh({"netzbezug": 0}, "pv") == 1
    # `spanne()` bleibt ≥ 1 — eine Nullzeile zählt dort als ihre eine Stunde (Deckel, Mitternachtsbündel)
    assert spanne({"pv": 0}, "pv") == 1 and spanne({"pv": 4}, "pv") == 4
    assert [spannen_gebuendelt(s, "pv") for s in (None, {}, {"pv": 1}, {"pv": 0}, {"pv": 5})] == [
        False, False, False, True, True]
    zeile = SimpleNamespace(spannen={"pv": 0, "netzbezug": 0, "einspeisung": 0})
    assert zeile_gebuendelt(zeile, "pv") and verbrauch_gebuendelt(zeile)
    assert not zeile_gebuendelt(SimpleNamespace(spannen=None), "pv")


# ── E-1: die Fenster ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_ohne_stillstand_kein_fenster():
    assert stillstand_fenster(_reihen(_tag_profil(10 * TAG))) == []


def test_stillstand_k3_am_tag():
    reihen = _reihen(_tag_profil(10 * TAG, stand={5 * TAG + 10: 3}))
    (f,) = stillstand_fenster(reihen)
    assert (f.von_ts, f.nachtrag_ts, f.k, f.n, f.sperre) == (T0 + (5 * TAG + 10) * H, T0 + (5 * TAG + 13) * H, 3, 4, None)
    assert f.achsen == frozenset({"pv", "einspeisung", "netzbezug"})


def test_k1_bleibt_wie_heute():
    """G-3: ein Lauf mit einer Stunde ist kein Fenster."""
    assert stillstand_fenster(_reihen(_tag_profil(10 * TAG, stand={5 * TAG + 10: 1}))) == []


def test_lauf_ueber_mitternacht_und_drei_tage():
    (f,) = stillstand_fenster(_reihen(_tag_profil(12 * TAG, stand={5 * TAG + 22: 11})))
    assert (f.von_ts, f.k) == (T0 + (5 * TAG + 22) * H, 11)
    (g,) = stillstand_fenster(_reihen(_tag_profil(12 * TAG, stand={5 * TAG + 10: 3 * TAG})))
    assert g.k == 72 and g.nachtrag_ts == T0 + (8 * TAG + 10) * H


def test_fehlende_zeile_beendet_den_lauf():
    """Eine Stunde ohne Zeile ist eine Lücke (Lücken-Bündel), kein Stillstand."""
    profil = _tag_profil(10 * TAG, stand={5 * TAG + 10: 3})
    reihen = _reihen(profil)
    reihen["basis:netzbezug"] = _reihe("netzbezug", profil["netzbezug"], fehlt=(5 * TAG + 11,))
    assert stillstand_fenster(reihen) == []


def test_nachtrag_braucht_zwei_zaehler_mit_menge():
    """Nachts: nur der Netzbezug trägt Menge — G-1, kein Fenster."""
    assert stillstand_fenster(_reihen(_tag_profil(10 * TAG, stand={5 * TAG + 1: 3}))) == []


def test_vorbedingung_netzbezug_und_ein_weiterer():
    profil = _tag_profil(10 * TAG, stand={5 * TAG + 10: 3})
    ohne_netz = {k: r for k, r in _reihen(profil).items() if r.rolle != "netzbezug"}
    assert stillstand_fenster(ohne_netz) == []
    nur_netz = {k: r for k, r in _reihen(profil).items() if r.rolle == "netzbezug"}
    assert stillstand_fenster(nur_netz) == []


def _mit_speicher(profil, *, ladung: bool = True, entladung: bool = True) -> dict[str, ZaehlerReihe]:
    out = _reihen(profil)
    n = len(profil["pv"])
    if ladung:
        out["inv:2:ladung_kwh"] = _reihe("ladung", [0.0] * n)
    if entladung:
        out["inv:2:entladung_kwh"] = _reihe("entladung", [0.0] * n)
    return out


def test_speicher_verlangt_ladung_und_entladung():
    """Mit aktivem Speicher müssen Ladung UND Entladung erfasst sein — ein Speicher ohne Zähler friert jede
    Batterie-Nacht scheinbar ein (Bauplan §1: «≥ 1 Zähler» 194 Läufe). Sprengsätze: ohne Speicher-Bedingung (kein
    Speicher aktiv) trifft dieselbe Lage; eine Bedingung «nur Ladung» ließe die Lage ohne Entladung durch."""
    profil = _tag_profil(10 * TAG, stand={5 * TAG + 10: 3})
    an = lambda _ts: True  # noqa: E731
    assert stillstand_fenster(_reihen(profil), speicher_aktiv=an) == []
    assert len(stillstand_fenster(_reihen(profil), speicher_aktiv=lambda _ts: False)) == 1
    assert stillstand_fenster(_mit_speicher(profil, entladung=False), speicher_aktiv=an) == []
    assert stillstand_fenster(_mit_speicher(profil, ladung=False), speicher_aktiv=an) == []
    (f,) = stillstand_fenster(_mit_speicher(profil), speicher_aktiv=an)
    assert "batterie" in f.achsen


# ── «erfasst» blickt 30 Tage zurück ─────────────────────────────────────────────────────────────────────────────────

def _mit_pv2(profil, *, endet_tag: int) -> dict[str, ZaehlerReihe]:
    """Ein zweiter PV-Zähler, der ab ``endet_tag`` keine Zeile mehr hat (Pause/abgebaut)."""
    out = _reihen(profil)
    out["inv:9:pv"] = _reihe("pv", profil["pv"][:endet_tag * TAG])
    return out


def test_pausierender_zaehler_laenger_als_30_tage_zaehlt_nicht():
    """Ein Zähler ohne Zeile in den 30 Tagen vor dem Laufbeginn ist nicht erfasst — der Stillstand der übrigen ist ein
    Fenster. Sprengsatz «jeder Zähler immer erfasst»: seine fehlenden Zeilen beendeten jeden Lauf (kein Fenster)."""
    profil = _tag_profil(90 * TAG, stand={60 * TAG + 10: 3})
    (f,) = stillstand_fenster(_mit_pv2(profil, endet_tag=20))
    assert f.nachtrag_ts == T0 + (60 * TAG + 13) * H


def test_pausierender_zaehler_innerhalb_30_tagen_beendet_den_lauf():
    """Pausiert er erst 10 Tage vor dem Laufbeginn, ist er noch erfasst: seine fehlenden Zeilen beenden den Lauf.
    Sprengsatz «Rand 30 → 5 Tage»: dann wäre er nicht mehr erfasst und das Fenster käme."""
    profil = _tag_profil(90 * TAG, stand={60 * TAG + 10: 3})
    assert stillstand_fenster(_mit_pv2(profil, endet_tag=50)) == []


def test_spaetere_pause_aendert_kein_frueheres_fenster():
    """Nur rückwärts: ob ein Zähler NACH dem Fenster weiterläuft, ändert das Fenster nicht."""
    profil = _tag_profil(90 * TAG, stand={40 * TAG + 10: 3})
    mit = stillstand_fenster(_reihen(profil) | {"inv:9:pv": _reihe("pv", profil["pv"])})
    pause = stillstand_fenster(_mit_pv2(profil, endet_tag=41))
    assert [f.nachtrag_ts for f in mit] == [f.nachtrag_ts for f in pause] == [T0 + (40 * TAG + 13) * H]


# ── Grob-Sperre: 30 Tage vor der Nachtragsstunde ────────────────────────────────────────────────────────────────────

def _grob_netz(profil, positive: dict[int, float]) -> dict[str, list[float]]:
    """Netzbezug nur in den Stunden ``positive`` (Stunde → Δ), sonst 0 — der grobe Zähler; nachts deckt der Speicher
    (Entladung fein, sonst stünde jede Nacht still)."""
    netz = [0.0] * len(profil["netzbezug"])
    for h, d in positive.items():
        netz[h] = d
    return {**profil, "entladung": profil["netzbezug"], "netzbezug": netz}


def _grob_fall(positive: dict[int, float], nachtrag_tag: int = 40):
    profil = _tag_profil(60 * TAG, stand={nachtrag_tag * TAG + 10: 3})
    nachtrag = nachtrag_tag * TAG + 13
    netz = _grob_netz(profil, positive)
    netz["netzbezug"][nachtrag] = 2.0
    (f,) = [x for x in stillstand_fenster(_reihen(netz)) if x.nachtrag_ts == T0 + nachtrag * H]
    return f


def test_grob_sperre_genau_fuenf_positive_vielfache():
    """Fünf positive Δ (die Nachtragsstunde mitgezählt), alle Vielfache von 0,1, in den 30 Tagen vor der Nachtragsstunde
    ⇒ grob. Sprengsatz «Schwelle 5 → 50»: nicht gesperrt."""
    f = _grob_fall({(36 * TAG) + 2: 0.3, (37 * TAG) + 2: 0.7, (38 * TAG) + 2: 1.0, (39 * TAG) + 2: 0.4})
    assert f.sperre == SPERRE_GROB
    g = _grob_fall({(37 * TAG) + 2: 0.7, (38 * TAG) + 2: 1.0, (39 * TAG) + 2: 0.4})       # vier
    assert g.sperre is None


def test_grob_sperre_aufloesung_zehntel():
    """Δ in Zehntel-kWh (0,3; 0,7 …) sind grob. Sprengsatz «Auflösung 0,1 → 1,0»: nicht gesperrt."""
    f = _grob_fall({(30 + i) * TAG + 2: d for i, d in enumerate((0.3, 0.7, 0.2, 0.9, 0.6))})
    assert f.sperre == SPERRE_GROB
    fein = _grob_fall({(30 + i) * TAG + 2: d for i, d in enumerate((0.31, 0.7, 0.2, 0.9, 0.6))})
    assert fein.sperre is None


def test_grob_sperre_blickt_30_tage_zurueck_nicht_vor():
    """Die groben Δ liegen 20–28 Tage vor der Nachtragsstunde ⇒ gesperrt (Sprengsatz «Rand kleiner»: frei); dieselben Δ
    NACH der Nachtragsstunde zählen nicht (nur rückwärts), ebenso solche über 30 Tage davor."""
    vorher = _grob_fall({(12 + i) * TAG + 2: 1.0 for i in range(6)})
    assert vorher.sperre == SPERRE_GROB
    nachher = _grob_fall({(41 + i) * TAG + 2: 1.0 for i in range(6)})
    assert nachher.sperre is None
    zu_frueh = _grob_fall({(2 + i) * TAG + 2: 1.0 for i in range(6)})
    assert zu_frueh.sperre is None


# ── Häufigkeits-Sperre: 60 Tage vor der Nachtragsstunde ─────────────────────────────────────────────────────────────

def test_haeufigkeit_die_ersten_fuenf_bleiben_markiert():
    """Tägliches Einfrieren an 20 Tagen: die ersten fünf Fenster markiert, jedes weitere gesperrt. Sprengsatz «5 → 6»:
    das sechste wäre markiert."""
    stand = {d * TAG + 10: 3 for d in range(5, 25)}
    alle = stillstand_fenster(_reihen(_tag_profil(40 * TAG, stand=stand)))
    assert len(alle) == 20
    assert [f.sperre for f in alle] == [None] * 5 + [SPERRE_HAEUFIG] * 15


def test_haeufigkeit_blickt_60_tage_zurueck():
    """Sechs Fenster im Abstand von 10 Tagen: das sechste liegt 50 Tage nach dem ersten ⇒ gesperrt. Sprengsatz «60 → 30
    Tage»: es zählte nur vier und bliebe markiert. Ein siebtes 61 Tage nach dem ersten zählt das erste nicht mehr mit."""
    stand = {(5 + 10 * i) * TAG + 10: 3 for i in range(6)}
    alle = stillstand_fenster(_reihen(_tag_profil(80 * TAG, stand=stand)))
    assert [f.sperre for f in alle] == [None] * 5 + [SPERRE_HAEUFIG]


def test_spaeteres_fenster_aendert_kein_frueheres():
    """Nur rückwärts: acht wöchentliche Fenster — die ersten fünf bleiben markiert, gleich ob die Daten nach dem
    fünften enden oder weiterlaufen (Nachmessung F4: vorher fielen vier markierte zurück, als das sechste kam)."""
    stand = {(5 + 7 * i) * TAG + 10: 3 for i in range(8)}
    profil = _tag_profil(70 * TAG, stand=stand)
    voll = stillstand_fenster(_reihen(profil))
    bis_fuenf = stillstand_fenster(_reihen({k: v[:34 * TAG] for k, v in profil.items()}))
    assert [f.sperre for f in voll][:5] == [f.sperre for f in bis_fuenf] == [None] * 5
    assert [f.sperre for f in voll][5:] == [SPERRE_HAEUFIG] * 3


def test_grob_gesperrte_zaehlen_nicht_zur_haeufigkeit():
    """Fenster eines groben Zählers (grob gesperrt) sperren den ersten echten Stillstand nach dem Wechsel nicht."""
    profil = _tag_profil(80 * TAG, stand={(5 + i) * TAG + 10: 3 for i in range(8)} | {70 * TAG + 10: 3})
    netz = list(profil["netzbezug"])
    for h in range(0, 15 * TAG):                      # Tag 0–14 grober Zähler (ganze kWh), danach fein
        netz[h] = float(round(netz[h] * 3))
    alle = stillstand_fenster(_reihen({**profil, "netzbezug": netz}))
    letztes = [f for f in alle if f.nachtrag_ts == T0 + (70 * TAG + 13) * H]
    assert letztes and letztes[0].sperre is None


def test_ergebnis_haengt_nicht_am_lesebereich():
    """Treffer = Kaltlauf im Layer: ein Fenster kommt aus jedem Bereich, der ``RUECKBLICK_S`` vor ihm enthält, gleich
    heraus — auch mit einem pausierenden Zähler."""
    stand = {100 * TAG + 10: 3, 150 * TAG + 22: 11}
    profil = _tag_profil(170 * TAG, stand=stand)
    reihen = _mit_pv2(profil, endet_tag=120)
    voll = stillstand_fenster(reihen)
    rueck = sp.RUECKBLICK_S // H
    for von in (0, 5 * TAG, 50 * TAG):
        teil = {k: ZaehlerReihe(r.rolle, tuple(w for w in r.werte if w[0] >= T0 + von * H)) for k, r in reihen.items()}
        erwartet = [f for f in voll if f.nachtrag_ts >= T0 + (von + rueck) * H]
        assert [f for f in stillstand_fenster(teil) if f.nachtrag_ts >= T0 + (von + rueck) * H] == erwartet
    assert len(voll) == 2


# ── E-2: Nebenachsen und die Marke einer Zeile ───────────────────────────────────────────────────────────────────────

def test_nebenachse_erbt_nur_wenn_sie_stand():
    f = StillstandFenster(T0 + 10 * H, T0 + 13 * H, 3, frozenset({"pv"}))
    steht = _reihe("wallbox", [0.5] * 10 + [0.0] * 3 + [2.0] * 5)
    laeuft = _reihe("wallbox", [0.5] * 18)
    luecke = _reihe("wallbox", [0.5] * 10 + [0.0] * 3 + [2.0] * 5, fehlt=(11,))
    assert erbt_marke(f, [steht]) and not erbt_marke(f, [laeuft]) and not erbt_marke(f, [luecke])
    assert not erbt_marke(f, []) and not erbt_marke(f, [steht, laeuft])


def test_marke_der_stunde():
    f = StillstandFenster(T0 + 10 * H, T0 + 13 * H, 3, frozenset({"pv", "netzbezug"}))
    gesperrt = StillstandFenster(T0 + 30 * H, T0 + 33 * H, 3, frozenset({"pv"}), SPERRE_HAEUFIG)
    assert marke_der_stunde([f], [T0 + 9 * H]) is None
    assert marke_der_stunde([f], [T0 + 10 * H]) == (0, f.achsen)
    assert marke_der_stunde([f], [T0 + 12 * H]) == (0, f.achsen)
    assert marke_der_stunde([f], [T0 + 13 * H]) == (4, f.achsen)
    assert marke_der_stunde([gesperrt], [T0 + 31 * H]) is None


@pytest.mark.parametrize("datum", [date(2026, 10, 25), date(2026, 3, 29), date(2026, 4, 5), date(2026, 9, 27)])
def test_umstellungstag_die_doppelte_stunde_traegt_beide(datum):
    """Am Herbst-Umstellungstag trägt die Zeile der doppelten Wanduhr-Stunde zwei echte Stunden (Kanal-Tag, Stunde 2);
    ein Fenster, das nur die zweite trifft, markiert sie trotzdem — in jeder Prozesszone (ohne Umstellung eine).
    N-799 S2 F11: am Frühjahrs-Umstellungstag trägt die Zeile der fehlenden Wanduhr-Stunde **keine** echte Stunde (bis
    S1 lieferte ``timestamp()`` die Nachbarstunden, die leere Zeile trug deren Marke)."""
    from backend.services.energie_profil.stillstand_marke import stunden_der_zeile

    fehlend = 0
    for stunde in range(24):
        ts = stunden_der_zeile(datum, stunde)
        wand = datetime(datum.year, datum.month, datum.day, stunde)
        echt = {t for t in (int(wand.replace(fold=f).timestamp()) for f in (0, 1)) if datetime.fromtimestamp(t) == wand}
        assert ts == tuple(sorted(echt))
        if not ts:
            fehlend += 1
            f = StillstandFenster(int(wand.replace(fold=0).timestamp()) - H, int(wand.replace(fold=0).timestamp()) + H,
                                  2, frozenset({"pv"}))
            assert marke_der_stunde([f], ts) is None          # Sprengsatz: die alte Fassung markierte die leere Zeile
            continue
        f = StillstandFenster(ts[-1], ts[-1] + 2 * H, 2, frozenset({"pv"}))
        assert marke_der_stunde([f], ts) == (0, f.achsen)
    assert fehlend <= 1
    tage = {datetime.fromtimestamp(t).date() for t in stunden_der_zeile(datum, 0)}
    assert tage == {datum} and datum - timedelta(days=1) not in tage
