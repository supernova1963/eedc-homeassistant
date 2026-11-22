"""Sensorwechsel Weg B, Sitzung B3b — kleine Punkte aus dem Lab-Durchlauf 2b (Wortlaute, kein Rechenweg).

* **W11** «1 Tage»: die Protokoll-Zeile nach «Daten vor der Änderung löschen» nennt Stundenwerte, Zählerstände und Tage mit
  Ein- oder Mehrzahl (``abfrage.aktivitaet_text``).
* **W13** Live-Satz: der Dialog «Zähler getauscht» nennt die Live-Anzeige nur, wenn es einen Sprung gibt — nicht neben
  «Einen Sprung sieht eedc an dieser Zeit nicht.» (``zaehler_getauscht._saetze_fortsetzung``).

Schwesterdateien: ``test_sensorwechsel_wegb_loeschen_proben.py`` (Rechenweg «löschen»), ``test_sensorwechsel_u3b_proben.py``
(«Zähler getauscht» über MQTT mit Datenbank).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.services.feld_loeschen import Geloescht
from backend.services.zuordnung_wechsel import zaehler_getauscht as zg
from backend.services.zuordnung_wechsel.abfrage import Frage, Vollzug, aktivitaet_text
from backend.services.zuordnung_wechsel.rohstand import SPRUNG

T = datetime(2026, 6, 8, 10, 20)
KEY = "basis:netzbezug"


@pytest.mark.parametrize("n, erwartet", [
    (1, "Netzbezug: Daten vor der Änderung gelöscht (1 Stundenwert, 1 Zählerstand; 1 Tag wird neu gebildet)"),
    (2, "Netzbezug: Daten vor der Änderung gelöscht (2 Stundenwerte, 2 Zählerstände; 2 Tage werden neu gebildet)"),
    (0, "Netzbezug: Daten vor der Änderung gelöscht (0 Stundenwerte, 0 Zählerstände; 0 Tage werden neu gebildet)"),
], ids=["eins", "zwei", "null"])
def test_w11_protokoll_nach_loeschen_mit_ein_und_mehrzahl(n, erwartet):
    g = Geloescht(key=KEY, t=T, kanalzeilen=n, staende=n, rohstaende=0, tage=[date(2026, 6, d + 1) for d in range(n)])
    v = Vollzug(fragen=[Frage(KEY, None, None, True)], geloescht=[(g, "L1")])
    assert aktivitaet_text(v, {KEY: "Netzbezug"}) == erwartet


def _lage(rohstand: str, abgehoben: bool) -> zg.Lage:
    rand = ((datetime(2026, 6, 8, 10, 15), 5000.0), (datetime(2026, 6, 8, 10, 25), 5002.0))
    return zg.Lage(KEY, zg.WEG_FORTSETZUNG, getauscht_am=datetime(2026, 6, 8, 10, 25), rand=rand, rohstand=rohstand,
                   heute=date(2026, 6, 8), abgehoben=abgehoben, einheit="kWh")


@pytest.mark.parametrize("rohstand, abgehoben, live, hinweis", [
    (zg.ROH_SCHRITT, False, False, zg.SATZ_HINWEIS_KEIN_SPRUNG),
    (zg.ROH_SCHRITT, True, True, zg.SATZ_HINWEIS_UNKLAR),
    (SPRUNG, False, True, None),
], ids=["schritt_ohne_sprung", "schritt_hebt_sich_ab", "eindeutiger_hoehenwechsel"])
def test_w13_live_satz_nur_bei_einem_sprung(rohstand, abgehoben, live, hinweis):
    saetze = zg.saetze(_lage(rohstand, abgehoben))
    assert (zg.SATZ_LIVE in saetze) is live
    if hinweis is not None:
        assert hinweis in saetze


def test_w13_live_satz_nur_heute_oder_gestern():
    la = _lage(SPRUNG, False)
    la.heute = date(2026, 6, 10)
    assert zg.SATZ_LIVE not in zg.saetze(la)
