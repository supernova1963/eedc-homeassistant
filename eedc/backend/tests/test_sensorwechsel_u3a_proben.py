"""Sensorwechsel U3 Lauf a «Auskunft» (Rechenweg ``opus-berichte/SENSORWECHSEL-U3-RECHENWEG-2026-11-19.md`` G2, G3; Bauplan
Nr. 150) — Proben mit Sprengsatz.

* **G2** ``monatswert_ueberholt``: nur an berührten Monaten, gespeichert, voller Wert aus dem Kanal, Abweichung ≥ 1 kWh, nicht
  bei «gespeicherten behalten».
* **G3** ``SATZ_TAG_FEST`` nur mit Tag und Wert, wenn die Tageszeile den Schlüssel trägt.

Die Proben zu G1 (``zaehler_zeit_verworfen``), G8 (Rest fremder Stände, Lage «Rest» am Versatz-Befund) und zum Anlass «Korrektur»
von G2 sind mit der Korrektur und den Befunden ``zaehler_zeit_verworfen``/``zaehler_versatz`` entfernt (Weg B, Sitzung B3a).

Saat unten (Wallbox «Ladung PV», 100 + 0,5 kWh je Stunde ab 01.06.2026, keine Zeitumstellung im Juni); keine
Probe liest die Uhr (die Datei läuft auch mit ``TZ=Pacific/Auckland`` und ``TZ=UTC``).
Schwesterdateien: test_sensorwechsel_u2c_proben.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw

# Saat (bis Weg B, Sitzung B3a, in ``test_daten_checker_zaehler_versatz.py``): Wallbox «Ladung PV», 100 + 0,5 kWh je Stunde ab
# 01.06.2026, optional ein um ``VERSATZ`` versetzter Abschnitt, HA-Spiegel als Kanal.
T0 = datetime(2026, 6, 1, 0)
SENSOR = "sensor.pv_ladung"
SPRUNG_H = 9 * 24 + 1          # 10.06. 01:00
RUECK_H = 13 * 24 + 19         # 14.06. 19:00
VERSATZ = 80.0


def _ha(h: int) -> float:
    """Der Stand, den Home Assistant führt: 100 kWh + 0,5 kWh je Stunde."""
    return 100.0 + 0.5 * h


def _reihe(stunden: int = 29 * 24, *, sprung=SPRUNG_H, rueck=RUECK_H, versatz=VERSATZ, loch=()):
    """Stündliche Stände; zwischen ``sprung`` und ``rueck`` (exklusiv) um ``versatz`` versetzt, außer in ``loch``."""
    return [(T0 + timedelta(hours=h), _ha(h) + (versatz if sprung is not None and sprung <= h < rueck and h not in loch
                                                else 0.0)) for h in range(stunden)]


async def _anlage(db, *, staende=None, spiegel=True, spiegel_plus=0.0, quelle_sensor=SENSOR, offset=0.0, quelle="ha_statistics",
                  feld="ladung_pv_kwh"):
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
    from backend.models.sensor_snapshot import SensorSnapshot

    a = Anlage(anlagenname="Versatz", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="Ladepunkt", anschaffungsdatum=date(2025, 1, 1))
    db.add(wb)
    await db.flush()
    a.sensor_mapping = {"investitionen": {str(wb.id): {"felder": {feld: {"strategie": "sensor", "sensor_id": SENSOR}}}}}
    key = f"inv:{wb.id}:{feld}"
    db.add_all([SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=t, wert_kwh=w, quelle=quelle)
                for t, w in (staende if staende is not None else _reihe())])
    if spiegel:
        k = Kanal(anlage_id=a.id, key=key, einheit="kWh", art=ART_SUM)
        db.add(k)
        await db.flush()
        ab = int(T0.timestamp()) - 3600
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=ab, familie=FAMILIE_SPIEGEL, statistic_id=quelle_sensor, offset=offset))
        db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ab + 3600 * h, sum=_ha(h) + spiegel_plus - offset, state=_ha(h),
                                   familie=FAMILIE_SPIEGEL) for h in range(29 * 24)])
    await db.commit()
    return a, wb, key


QA = {"art": "ha", "entity_id": SENSOR}


# ═══ G2 — «Gespeicherter Monatswert passt nicht mehr» ════════════════════════════════════════════════════════════════

NETZ = "basis:netzbezug"
JUNI = datetime(2026, 6, 1)


async def _g2_saat(db, *, gespeichert: float, grund: str = "fortsetzung", behalten=None, bis_tage: int = 32):
    """Netzbezug-Kanal (Spiegel) 0,5 kWh je Stunde ⇒ Juni 360,0 kWh; Monatszeile Juni mit ``gespeichert``; ein Wechsel am
    10.06. 10:00 mit ``grund``."""
    from backend.models.anlage import Anlage
    from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
    from backend.models.monatsdaten import Monatsdaten

    a = Anlage(anlagenname="G2", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    k = Kanal(anlage_id=a.id, key=NETZ, einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    t0 = int(JUNI.timestamp())
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=t0 - 2 * 3600, familie=FAMILIE_SPIEGEL, statistic_id="sensor.netz", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=t0 + 3600 * h, sum=0.5 * (h + 1), state=0.5 * (h + 1),
                               familie=FAMILIE_SPIEGEL) for h in range(-2, bis_tage * 24)])
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=6, einspeisung_kwh=0.0, netzbezug_kwh=gespeichert,
                       source_provenance={"netzbezug_kwh": {"source": "manual"}},
                       geprueft_gegen={"netzbezug_kwh": behalten} if behalten else {}))
    t = datetime(2026, 6, 10, 10)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=NETZ, erklaert_ts=t, ab_ts=t, vorher={"art": "ha", "entity_id": "sensor.alt"},
                            nachher={"art": "ha", "entity_id": "sensor.netz"}, grund=grund, herkunft="wechsel"))
    await db.commit()
    return a


async def _ueberholt(db, a):
    from backend.services.daten_checker import DatenChecker

    zw.vergiss(db)
    return await DatenChecker(db)._check_monatswert_ueberholt(a, heute=date(2026, 7, 15))


async def test_g2_abweichung_eine_zeile_mit_monat_oeffnen(db):
    (e,) = await _ueberholt(db, await _g2_saat(db, gespeichert=365.0))
    assert (e.code, e.schwere, e.knopf) == ("monatswert_ueberholt", "warning", "Monat öffnen")
    assert (e.ziel.params, e.werte["abweichung_kwh"], e.werte["anlass"]) == (
        {"erfassen": "2026-06", "feld": "netzbezug_kwh"}, -5.0, "fortsetzung")
    assert e.meldung == "Netzbezug: gespeicherter Monatswert 06/2026 passt nicht mehr zur Quelle"
    assert e.details == ("Gespeichert sind 365,0 kWh. Seit dem Wechsel der Quelle am 10.06.2026 ergibt die Quelle für diesen "
                         "Monat 360,0 kWh. Alles, was eedc für diesen Monat zeigt, rechnet mit dem gespeicherten Wert; er "
                         "bleibt, bis du ihn änderst.")


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_toleranz_0"])
async def test_g2_rundung_unter_einer_kwh_ist_keine_zeile(db, monkeypatch, sprengsatz):
    """Produktiv-Kopie im Monat des Wechsels: 242,9 gespeichert gegen 242,871 — kein Unterschied. Sprengsatz Toleranz 0 ⇒ Zeile."""
    import backend.core.berechnungen.monatswert_vergleich as mv

    if sprengsatz:
        monkeypatch.setattr(mv, "MONATSWERT_TOLERANZ_KWH", 0.0)
        monkeypatch.setattr(mv.monatswert_weicht_ab, "__defaults__", (0.0,))
    erg = await _ueberholt(db, await _g2_saat(db, gespeichert=360.029))
    assert len(erg) == (1 if sprengsatz else 0)


@pytest.mark.parametrize("fall", ["ohne_grund", "behalten", "nicht_voll"])
async def test_g2_keine_zeile(db, fall):
    """Ein Wechsel ohne Grund berührt nichts; «gespeicherten behalten» mit genau diesem Wert; ohne volle Deckung des Monats."""
    kw = {"ohne_grund": {"grund": None}, "behalten": {"behalten": {"sensor": 360.0, "wert": 365.0}},
          "nicht_voll": {"bis_tage": 20}}[fall]
    assert await _ueberholt(db, await _g2_saat(db, gespeichert=365.0, **kw)) == []


# ═══ G3 — SATZ_TAG_FEST nur mit Tag und Wert ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("traegt", [True, False], ids=["tageszeile_traegt_den_schluessel", "ohne"])
async def test_g3_tag_fest_nur_mit_tag_und_wert(db, monkeypatch, traegt):
    """Tausch 12.06. 10:20 (vor dem laufenden Tag): trägt die Tageszeile des 12.06. den Schlüssel des Felds, nennt die Antwort
    Tag und Wert; sonst entfällt der Satz (Bauplan «Zu §14» Nr. 95 (4))."""
    from backend.models.tages_energie_profil import TagesZusammenfassung
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    a, _wb, key = await _anlage(db, spiegel=False, feld="ladung_kwh")
    ziele = await vq.bestand_ziele(db, a, key)
    assert ziele.tz_keys                                              # Wallbox «Ladung gesamt» steht in der Tageszeile
    tag = date(2026, 6, 12)
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=tag,
                                komponenten_kwh={sorted(ziele.tz_keys)[0] if traegt else "andere_1": 7.25}))
    await db.commit()
    la = zg.Lage(key, zg.WEG_FORTSETZUNG, QA, datetime(2026, 6, 12, 10, 20), vor_heute=True,
                 tag_fest=await zg.tag_fest(db, a, key, datetime(2026, 6, 12, 11)))
    saetze = zg.saetze(la)
    if traegt:
        assert la.tag_fest == (tag, 7.25)
        assert saetze[-1] == ("Für den 12.06.2026 hat eedc schon einen festen Tageswert dieses Felds gespeichert (7,25 kWh); "
                              "er bleibt, wie er ist, und kann den Unterschied weiter enthalten.")
    else:
        assert la.tag_fest is None and not any("festen Tageswert" in s for s in saetze)
