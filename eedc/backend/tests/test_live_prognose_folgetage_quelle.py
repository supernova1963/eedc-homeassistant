"""Die Live-Kachel nimmt für die Folgetage den Tageswert der gewählten Quelle.

**Der gemeldete Fall** (Burkard / BMeyendriesch, simon42 T89667 #276, 2026-08-31,
Fortsetzung von [#401] Punkt 3): Bei SFML als Quelle heißt die Kachel
*„Solar-Aussicht (SFML)"*, zeigte aber für Morgen und Übermorgen die
eedc-Prognose — bei ihm 49,8 / 58,1 gegen SFML 43,7 / 44,4.

**Die Ursache war eine fehlende Zeile, keine falsche Rechnung.** Der Fix vom
30.08. (#401) hat die Folgetage über das **Stundenprofil** gelöst
(``quelle_tagesprofile``, aus dem evcc-``forecast``-Attribut). Der **Tageswert**
der Quelle wurde für Tag 2 nie gelesen — ``uebermorgen_kwh`` kam im ganzen
Live-Pfad nicht vor, obwohl ``prognose_discovery`` die Rolle kennt und der
Vergleichs-Endpoint (``prognosen.py``) sie seit jeher liest. Wer kein
Stundenprofil hat, sah dort also zwangsläufig eedc, während der Sensor daneben
stand (an einer echten Instanz gemessen: ``sensor.prognose_ubermorgen`` = 38,8).

**Bei Solcast fehlten beide Folgetage.** Solcast liefert im Live-Pfad nur *heute*
stündlich; die Tageswerte trägt dasselbe Objekt als ``tage_voraus`` mit, und der
Live-Pfad las sie nicht aus.

**Die Regel, die dieser Test festhält** (Entscheid Gernot, 31.08.2026): *Wer eine
Quelle wählt, bekommt diese Quelle; eedc ist der Rückfall, nicht der Normalfall.*
Die Reihenfolge je Tag ist damit: **Tageswert der Quelle → ihr Stundenprofil →
eedc** (dann mit ``rueckfall: "eedc"`` ausgewiesen).

⛔ **Was hier NICHT geprüft wird und bewusst so bleibt:** *Cockpit → Aussicht*
(``aussichten.py`` kennt SFML/Solcast nicht — Entscheid nach #401 Punkt 3) und
die MQTT-/HA-Sensoren (tragen bewusst immer die eedc-Prognose). Beide sind
begründete Ausnahmen, keine vergessenen Stellen.

Schwesterdateien: ``test_solcast_tagesprofile_357.py`` (dieselbe Quellen-Achse
im Live-Pfad) und ``test_prognose_kanon_quellen.py`` (der Kanon selbst).
"""

from __future__ import annotations

from datetime import date, timedelta

#: Festes Datum statt Prozessuhr (N-167): Die Suite läuft in mehreren Zonen,
#: und `date.today()` wettet auf die Stunde ihres Laufs. Die Route bildet ihr
#: „heute" selbst; für die Auswahl-Logik ist nur die REIHENFOLGE der drei Tage
#: erheblich, nicht welcher Tag es ist.
_HEUTE = date(2026, 8, 31)


def _tage(quelle: str, *, sfml_morgen=None, sfml_uebermorgen=None,
          solcast_tage=None, profile=None, heute_kwh=10.0,
          heute: date = _HEUTE) -> list[dict]:
    """Bildet die Auswahl-Logik der Route nach — dieselbe Reihenfolge.

    Die Route selbst hängt an einer HA-Verbindung, einer Anlage und drei
    Service-Abrufen; nachgebaut ist genau der Entscheidungsbaum, um den es
    geht. ⚠ Driftet die Route, ist das hier eine Behauptung — deshalb prüft
    `test_route_traegt_die_reihenfolge_im_quelltext` unten den Quelltext mit.
    """
    ist_sfml = quelle == "sfml"
    ist_solcast = quelle == "solcast"
    out = []
    for i in range(3):
        tag_datum = heute + timedelta(days=i)
        slots = profile[i] if profile and i < len(profile) else None
        kwh = None
        if i == 0:
            kwh = heute_kwh
        elif ist_sfml:
            kwh = sfml_morgen if i == 1 else sfml_uebermorgen
        elif ist_solcast and solcast_tage:
            tag_str = tag_datum.isoformat()
            kwh = next((t.get("kwh") for t in solcast_tage
                        if t.get("datum") == tag_str), None)
        if kwh is None and slots:
            kwh = round(sum(slots), 1)
        out.append({"datum": tag_datum.isoformat(), "kwh": kwh,
                    "rueckfall": None if kwh is not None else "eedc"})
    return out


def test_sfml_uebermorgen_kommt_aus_der_quelle_ohne_stundenprofil():
    """Burkards Fall: kein Stundenprofil, aber die Tageswerte liegen vor."""
    tage = _tage("sfml", sfml_morgen=43.7, sfml_uebermorgen=44.4, profile=None)

    assert tage[1]["kwh"] == 43.7, "Morgen muss aus SFML kommen"
    assert tage[2]["kwh"] == 44.4, (
        "Übermorgen muss aus SFML kommen — vorher war hier zwangsläufig eedc, "
        "weil der Tageswert nie gelesen wurde"
    )
    assert all(t["rueckfall"] is None for t in tage), "kein Tag fällt zurück"


def test_solcast_folgetage_kommen_aus_tage_voraus():
    """Solcast liefert hier nur heute stündlich — die Tageswerte trägt es mit."""
    solcast_tage = [
        {"datum": (_HEUTE + timedelta(days=1)).isoformat(), "kwh": 39.4},
        {"datum": (_HEUTE + timedelta(days=2)).isoformat(), "kwh": 51.8},
    ]
    tage = _tage("solcast", solcast_tage=solcast_tage, profile=[[1.0] * 24])

    assert tage[1]["kwh"] == 39.4
    assert tage[2]["kwh"] == 51.8
    assert all(t["rueckfall"] is None for t in tage)


def test_tageswert_schlaegt_das_stundenprofil():
    """Reihenfolge: Tageswert der Quelle VOR ihrer Profilsumme.

    Der Tageswert ist die Aussage der Quelle selbst; die Profilsumme ist die
    Ableitung daraus und kann durch fehlende Slots zu klein sein.
    """
    tage = _tage("sfml", sfml_morgen=43.7, sfml_uebermorgen=44.4,
                 profile=[[1.0] * 24, [0.5] * 24, [0.5] * 24])  # Σ = 12.0

    assert tage[1]["kwh"] == 43.7, "Tageswert, nicht die 12.0 aus dem Profil"
    assert tage[2]["kwh"] == 44.4


def test_ohne_wert_und_ohne_profil_wird_der_rueckfall_ausgewiesen():
    """Die Gegenprobe: der Fix darf den Rückfall nicht verstecken.

    Liefert die Quelle für einen Tag nichts, steht dort weiterhin `eedc` —
    sichtbar, statt still eine fremde Zahl unter ihrer Überschrift zu zeigen.
    """
    tage = _tage("sfml", sfml_morgen=43.7, sfml_uebermorgen=None, profile=None)

    assert tage[1]["kwh"] == 43.7
    assert tage[2]["kwh"] is None
    assert tage[2]["rueckfall"] == "eedc", "der Rückfall muss ausgewiesen bleiben"


def test_route_traegt_die_reihenfolge_im_quelltext():
    """Hält den Nachbau oben an die Route — sonst prüft er nur sich selbst.

    ⚠ Der Test darüber bildet die Auswahl nach. Driftet die Route, wären die
    Zusicherungen still wertlos; diese Probe fängt das an drei Markern, die der
    Fix gesetzt hat.
    """
    from pathlib import Path
    quelle = (Path(__file__).resolve().parents[1]
              / "api" / "routes" / "live_wetter.py").read_text(encoding="utf-8")

    assert 'sfml_disc.wert("uebermorgen_kwh")' in quelle, (
        "die SFML-Rolle für Übermorgen wird nicht mehr gelesen — genau der Befund"
    )
    assert "solcast_tage_voraus" in quelle, (
        "die Solcast-Tageswerte werden nicht mehr ausgelesen"
    )
    # Tageswert VOR Profilsumme: die Profil-Zuweisung steht hinter der Quelle.
    i_quelle = quelle.index('kwh = sfml_tomorrow if i == 1 else sfml_uebermorgen')
    i_profil = quelle.index("if kwh is None and slots:", i_quelle)
    assert i_quelle < i_profil, "die Profilsumme darf den Tageswert nicht überholen"
