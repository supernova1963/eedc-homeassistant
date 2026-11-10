"""Daten-Checker nennt die Zusatz-Zähler, ohne die Tageswerte leer bleiben (DOK-9).

`ENERGIEPROFIL_ABDECKUNG` flaggte nur die kritischen kWh-Felder. Die
tages-**ableitbaren** Zusatzfelder — WP `heizenergie_kwh`/`warmwasser_kwh`
(Wärmemengenzähler) und `ladung_pv_kwh` an Wallbox/E-Auto — fehlten in der
Prüfung, obwohl der „—"-Tooltip in Cockpit/Tag sie bereits als fehlende
Zuordnung nennt. Der Checker schwieg also zu etwas, das die Oberfläche
anzeigt.

Bewusst **INFO, nicht WARNING**: das sind Zusatz-Messstellen, die längst nicht
jede Anlage hat. Eine Dauerwarnung dafür wäre genau das Nörgeln, das der
Daten-Checker vermeiden soll — deshalb steht jedem „Befund"-Test ein
„kein Befund"-Test gegenüber.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity

_MELDUNG = "ohne Zusatz-Zähler für Tageswerte"


def _sensor(eid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": eid}


async def _anlage(db, komponenten: list[tuple[str, str, dict]], mapping_felder=None) -> Anlage:
    """komponenten = [(typ, bezeichnung, parameter)]; mapping_felder = {bez: {feld: cfg}}"""
    anlage = Anlage(anlagenname="DOK9", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    bez_zu_id: dict[str, int] = {}
    for typ, bez, params in komponenten:
        inv = Investition(
            anlage_id=anlage.id, typ=typ, bezeichnung=bez,
            anschaffungsdatum=date(2023, 1, 1), parameter=params,
        )
        db.add(inv)
        await db.flush()
        bez_zu_id[bez] = inv.id

    investitionen = {
        str(bez_zu_id[bez]): {"felder": felder}
        for bez, felder in (mapping_felder or {}).items()
    }
    anlage.sensor_mapping = {"investitionen": investitionen} if investitionen else {}
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()


def _treffer(anlage, db):
    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage, [])
    return [r for r in ergebnisse if _MELDUNG in r.meldung]


async def test_waermepumpe_ohne_waermemengenzaehler_wird_als_info_genannt(db):
    anlage = await _anlage(db, [("waermepumpe", "Vitocal", {})])

    treffer = _treffer(anlage, db)

    assert len(treffer) == 1
    assert treffer[0].schwere == CheckSeverity.INFO, "WARNING wäre Nörgeln"
    assert "Vitocal: Heizwärme, Warmwasser" in treffer[0].details
    assert "Tagesansicht im Cockpit" in treffer[0].details


async def test_split_klimaanlage_wird_nicht_nach_waermemengenzaehler_gefragt(db):
    """Luft-Luft-WP: beide Zusatzfelder setzen einen Wärmemengenzähler voraus.

    Eine Split-Klimaanlage hat weder den noch einen Warmwasserkreis — der
    Hinweis war für den Anwender unauflösbar (dietmar1968, Forum #89667/87)
    und widersprach der Zusage im Investitionsformular („Es genügt der
    Stromverbrauchs-Sensor"). Die Monatsdaten-Prüfung kennt die Ausnahme
    längst; hier fehlte sie.
    """
    anlage = await _anlage(db, [("waermepumpe", "Daikin Split", {"wp_art": "luft_luft"})])

    assert not _treffer(anlage, db)


async def test_klassische_waermepumpe_wird_weiterhin_gefragt(db):
    """Gegenprobe: die Ausnahme darf nur Luft-Luft treffen."""
    anlage = await _anlage(db, [("waermepumpe", "Vitocal", {"wp_art": "luft_wasser"})])

    treffer = _treffer(anlage, db)

    assert len(treffer) == 1
    assert "Vitocal: Heizwärme, Warmwasser" in treffer[0].details


async def test_waermepumpe_ohne_wp_art_wird_weiterhin_gefragt(db):
    """Legacy-Bestand ohne `wp_art` zählt als klassische WP — eine fehlende
    Angabe darf die Erwartung nicht stillschweigend abschalten."""
    anlage = await _anlage(db, [("waermepumpe", "Legacy WP", {})])

    treffer = _treffer(anlage, db)

    assert len(treffer) == 1
    assert "Legacy WP: Heizwärme, Warmwasser" in treffer[0].details


async def test_gepflegte_zusatzzaehler_schweigen(db):
    anlage = await _anlage(
        db,
        [("waermepumpe", "Vitocal", {})],
        mapping_felder={"Vitocal": {
            "heizenergie_kwh": _sensor("sensor.wmz_heizen"),
            "warmwasser_kwh": _sensor("sensor.wmz_ww"),
        }},
    )

    assert not _treffer(anlage, db)


async def test_teilweise_gepflegt_nennt_nur_den_rest(db):
    anlage = await _anlage(
        db,
        [("waermepumpe", "Vitocal", {})],
        mapping_felder={"Vitocal": {"heizenergie_kwh": _sensor("sensor.wmz_heizen")}},
    )

    treffer = _treffer(anlage, db)

    assert len(treffer) == 1
    assert "Vitocal: Warmwasser" in treffer[0].details
    assert "Heizwärme" not in treffer[0].details


async def test_wallbox_deckt_die_pv_ladung_des_eautos_ab(db):
    """Dieselbe Regel wie `bedingung_anlage: keine_wallbox` in field_definitions:
    mit Wallbox wird die Heimladung dort geführt, nicht am Fahrzeug.

    Gepflegte Wallbox + E-Auto daneben ⇒ **gar kein** Befund: die Wallbox ist
    abgedeckt, das Fahrzeug wird übersprungen. Ohne die Wallbox-Regel stünde
    hier „ID.4: Ladung PV" — eine Zuordnung, die es doppelt gäbe.
    """
    anlage = await _anlage(
        db,
        [("wallbox", "Go-E", {}), ("e-auto", "ID.4", {})],
        mapping_felder={"Go-E": {"ladung_pv_kwh": _sensor("sensor.wb_pv")}},
    )

    assert not _treffer(anlage, db)


async def test_ohne_wallbox_wird_die_pv_ladung_am_fahrzeug_genannt(db):
    """Gegenprobe: dieselbe Anlage ohne Wallbox — jetzt trägt das Auto das Feld."""
    anlage = await _anlage(db, [("e-auto", "ID.4", {})])

    treffer = _treffer(anlage, db)

    assert len(treffer) == 1
    assert "ID.4: Ladung PV" in treffer[0].details


async def test_dienstwagen_bleibt_aussen_vor(db):
    """Konsistent mit den übrigen E-Auto-Checks (`ist_dienstlich`)."""
    anlage = await _anlage(db, [("e-auto", "Firmen-ID.4", {"ist_dienstlich": True})])

    assert not _treffer(anlage, db)


async def test_anlage_ohne_solche_komponenten_bleibt_still(db):
    anlage = await _anlage(db, [("pv-module", "Dach Süd", {})])

    assert not _treffer(anlage, db)


# ═══ N-451b (14.09.2026): die Gruppe zählt, nicht das eine Feld ═════════════
#
# ⛔ **Der Befund, gemessen über `_check_tages_zusatzfelder`.** Seit WK-14b gibt
# es *Wärme gesamt* (`waerme_kwh`) — EIN Wärmemengenzähler für die ganze
# Wärmeabgabe, Alternative zu *Heizwärme* in derselben Bedarfs-Gruppe
# `wp_waerme`. Diese INFO kannte die Gruppe nicht und mahnte einen Zähler an,
# den der vorhandene ersetzt: *„Offen: Vitocal: Heizwärme, Warmwasser"*. Das ist
# die **N-86-Klasse** — dieselbe Anlage, zwei Flächen, gegenteilige Aussage: Die
# Zuordnungs-Fläche zählt *Heizwärme* längst als gedeckt (`pflicht_am_geraet`
# ist dort für ALTERNATIV-Gruppen ausgeschaltet), der Checker nicht.
#
# Der Monats-Checker hat dieselbe Frage mit WK-14b gelernt
# (`daten_checker/monatsdaten.py`); dieser hier blieb stehen.


async def test_waerme_gesamt_deckt_die_heizwaerme_ab(db):
    """EIN gemeinsamer Wärmemengenzähler ⇒ **kein** „Offen: … Heizwärme" mehr.

    ⚠ *Warmwasser* bleibt genannt, und das ist keine Lücke der Regel, sondern
    ihre Grenze: `warmwasser_kwh` steht **nicht** in der Gruppe `wp_waerme`
    (gemessen: `get_feld_bedarf` liefert `('optional', None)`). Ein Gesamtzähler
    liefert die Wärmemenge, aber nicht ihre Aufteilung — wer die Warmwasser-Linie
    im Tag sehen will, braucht dafür weiterhin einen eigenen Zähler (K1: die
    Aufteilung steht neben der Gesamtmenge, nie an ihrer Stelle).
    """
    anlage = await _anlage(
        db,
        [("waermepumpe", "Vitocal", {})],
        mapping_felder={"Vitocal": {"waerme_kwh": _sensor("sensor.wmz_gesamt")}},
    )

    treffer = _treffer(anlage, db)

    assert len(treffer) == 1
    assert "Heizwärme" not in treffer[0].details, treffer[0].details
    assert "Vitocal: Warmwasser" in treffer[0].details


async def test_waerme_gesamt_und_warmwasser_schweigen_ganz(db):
    """Gesamtzähler + Warmwasser-Zähler ⇒ gar kein Befund.

    Die Gegenprobe zur Klausel darüber: Es ist wirklich nur die Warmwasser-Seite
    offen geblieben, nicht ein Rest der alten Feld-Frage.
    """
    anlage = await _anlage(
        db,
        [("waermepumpe", "Vitocal", {})],
        mapping_felder={"Vitocal": {
            "waerme_kwh": _sensor("sensor.wmz_gesamt"),
            "warmwasser_kwh": _sensor("sensor.wmz_ww"),
        }},
    )

    assert not _treffer(anlage, db)


async def test_summanden_gruppe_deckt_nichts_ab(db):
    """⛔ **Eine Gruppe ist nicht automatisch eine Alternative** (N-456).

    `wp_strom` führt `stromverbrauch_kwh`, `strom_heizen_kwh` und
    `strom_warmwasser_kwh` — dort sind es **Summanden**, keiner deckt den
    anderen ab. Die Unterscheidung hängt an `BEDARF_GRUPPEN_ALTERNATIV`; wer sie
    beim Lesen weglässt, baut aus einem behobenen Fehlalarm ein verschwiegenes
    Loch. Die Klausel prüft den Leser direkt, weil die Strom-Felder in dieser
    INFO gar nicht vorkommen — und genau deshalb würde es hier niemand merken.
    """
    from backend.services.daten_checker.energieprofil import _alternativ_geschwister

    param = {"wp_art": "luft_wasser", "getrennte_strommessung": True}
    assert _alternativ_geschwister("waermepumpe", "strom_heizen_kwh", param) == [
        "strom_heizen_kwh"
    ]
    assert _alternativ_geschwister("wallbox", "ladung_pv_kwh", {}) == ["ladung_pv_kwh"]
    assert set(_alternativ_geschwister("waermepumpe", "heizenergie_kwh", param)) == {
        "heizenergie_kwh", "waerme_kwh",
    }
