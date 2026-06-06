"""
Unit-Tests für das einheitliche „Verbleibend"-Verfahren (#296 #3/#5/#6).

Die Prognosen-Seite zeigte zwei unterschiedliche Verfahren:
  • Gesamtspalte = IST + Σ Reststunden-Slots
  • Pro-Quelle    = Tagesprognose − IST   (andere Formel, IST>0 erzwungen)

Vereinheitlicht auf EIN Verfahren (Tagesprojektion = IST + Σ Reststunden der
jeweiligen Quelle), das auch bei IST==0 funktioniert.
"""

from __future__ import annotations

from backend.api.routes.prognosen import (
    StundenProfilEintrag,
    _eintraege_zu_array,
    _tagesprojektion,
)


def test_array_fuellt_fehlende_slots_mit_null():
    eintraege = [
        StundenProfilEintrag(stunde=8, kw=1.0),
        StundenProfilEintrag(stunde=12, kw=3.0),
    ]
    arr = _eintraege_zu_array(eintraege)
    assert len(arr) == 24
    assert arr[8] == 1.0
    assert arr[12] == 3.0
    assert arr[0] == 0.0
    assert arr[23] == 0.0


def test_array_ueberspringt_null_kw_luecken():
    # IST-Lücke (kein Zähler gemappt, Issue #135) → kw=None → zählt als 0
    eintraege = [StundenProfilEintrag(stunde=10, kw=None)]
    arr = _eintraege_zu_array(eintraege)
    assert arr[10] == 0.0


def test_projektion_ist_plus_reststunden():
    # 24-Slot-Profil: je 1 kW von 9..15 Uhr
    arr = [0.0] * 24
    for h in range(9, 16):
        arr[h] = 1.0
    # aktuelle Stunde 11 → Reststunden 12..15 = 4 kWh, IST bisher 5 kWh
    assert _tagesprojektion(5.0, arr, 11) == 9.0


def test_projektion_bei_ist_null_liefert_volle_restprognose():
    # #5: frühmorgens IST==0, trotzdem ein Wert (keine „—"-Lücke)
    arr = [0.0] * 24
    for h in range(6, 20):
        arr[h] = 2.0
    # aktuelle Stunde 3 → alle 6..19 zählen = 14*2 = 28
    assert _tagesprojektion(0.0, arr, 3) == 28.0


def test_projektion_ohne_profil_ist_none():
    assert _tagesprojektion(5.0, None, 12) is None
    assert _tagesprojektion(5.0, [], 12) is None


def test_projektion_abends_nur_ist():
    # Nach Sonnenuntergang: keine Reststunden mehr → reine IST-Tagessumme
    arr = [0.0] * 24
    for h in range(9, 16):
        arr[h] = 1.0
    assert _tagesprojektion(7.0, arr, 22) == 7.0


def test_projektion_kuerzeres_array_kein_indexfehler():
    # Solcast/SFML-Profil kann <24 Einträge haben
    arr = [1.0] * 18  # nur Stunden 0..17
    # aktuelle Stunde 16 → nur Stunde 17 zählt
    assert _tagesprojektion(3.0, arr, 16) == 4.0
