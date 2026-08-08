"""Eine Ladung, ein Zähler — N-196 im ZÄHLERpfad (Schwester von F-14).

`0fca2c5d` (#356) hat die strukturelle Quellen-Regel der E-Mob-Fläche gebaut:
**trägt eine Wallbox die Ladeenergie, ist sie die Quelle** — auch ohne
gesetzten `parent_investition_id`. Gebaut wurde sie aber nur im
**Leistungs**pfad (`services/live_sensor_config.py`).

Der **Zähler**pfad (`snapshot/aggregator.py` · `snapshot/lts_aggregator.py` über
`komponenten_beitraege.investition_beitraege`) kannte weiterhin nur die
Parent-Bedingung. Ein E-Auto mit eigenem kWh-Zähler **ohne** Parent lief an ihr
vorbei — derselbe Ladevorgang landete zweimal in `komponenten_kwh`.

⚠ **Ohne heute messbaren Schaden, und das gehört dazu:** an der einzigen
vermessenen Anlage hat das E-Auto gar keinen kWh-Zähler gemappt (nur km und
einen PV-Anteil), die F-14-Doppelzählung lief dort über `leistung_w`. Diese
Datei sichert also eine **Symmetrie**, keinen beobachteten Fehler — eine Regel,
die nur einer von zwei Pfaden kennt, ist die nächste Drift-Quelle.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.services.snapshot.komponenten_beitraege import (
    investition_beitraege,
    wallbox_deckt_ladung_ab,
)


def _inv(inv_id: int, typ: str, parent: int | None = None):
    return SimpleNamespace(
        id=inv_id, typ=typ, parameter={}, parent_investition_id=parent
    )


def _mapping(*eintraege: tuple[int, str]) -> dict:
    """`sensor_mapping` mit je einem gemappten kWh-Feld je Investition."""
    invs: dict[str, dict] = {}
    for inv_id, feld in eintraege:
        invs.setdefault(str(inv_id), {"felder": {}})["felder"][feld] = {
            "strategie": "sensor", "sensor_id": f"sensor.x{inv_id}_{feld}",
        }
    return {"investitionen": invs}


def _felder(mapping: dict, inv_id: int) -> dict:
    return mapping["investitionen"][str(inv_id)]


# ---------------------------------------------------------------------------
# wallbox_deckt_ladung_ab
# ---------------------------------------------------------------------------

def test_wallbox_mit_ladezaehler_deckt_ab():
    invs = [_inv(1, "e-auto"), _inv(2, "wallbox")]
    assert wallbox_deckt_ladung_ab(invs, _mapping((2, "ladung_kwh"))) is True


def test_wallbox_ohne_ladezaehler_deckt_nicht_ab():
    """Eine Wallbox, die nur ihre Leistung meldet, ist keine Zähler-Quelle."""
    invs = [_inv(1, "e-auto"), _inv(2, "wallbox")]
    assert wallbox_deckt_ladung_ab(invs, _mapping((2, "leistung_w"))) is False


def test_ohne_wallbox_deckt_nichts_ab():
    invs = [_inv(1, "e-auto")]
    assert wallbox_deckt_ladung_ab(invs, _mapping((1, "ladung_kwh"))) is False


def test_leeres_mapping_deckt_nichts_ab():
    assert wallbox_deckt_ladung_ab([_inv(2, "wallbox")], None) is False


# ---------------------------------------------------------------------------
# investition_beitraege — die Regel im Zählerpfad
# ---------------------------------------------------------------------------

def test_eauto_ohne_parent_traegt_bei_solange_keine_wallbox_misst():
    """Der Normalfall bleibt unberührt — sonst verschwände eine echte Ladung."""
    m = _mapping((1, "ladung_kwh"))
    beitraege = investition_beitraege(
        _inv(1, "e-auto"), _felder(m, 1), wallbox_deckt_ladung=False
    )
    assert [b.feld for b in beitraege] == ["ladung_kwh"]


def test_eauto_ohne_parent_schweigt_wenn_die_wallbox_misst():
    """N-196: genau der Fall, den F-14 im Leistungspfad geheilt hat."""
    m = _mapping((1, "ladung_kwh"), (2, "ladung_kwh"))
    beitraege = investition_beitraege(
        _inv(1, "e-auto"), _felder(m, 1),
        wallbox_deckt_ladung=wallbox_deckt_ladung_ab(
            [_inv(1, "e-auto"), _inv(2, "wallbox")], m
        ),
    )
    assert beitraege == []


def test_die_wallbox_selbst_traegt_immer_bei():
    """Sie IST die Quelle — die Regel darf sie nicht mit abschalten."""
    m = _mapping((2, "ladung_kwh"))
    beitraege = investition_beitraege(
        _inv(2, "wallbox"), _felder(m, 2), wallbox_deckt_ladung=True
    )
    assert [b.feld for b in beitraege] == ["ladung_kwh"]


def test_eauto_verbrauch_kwh_faellt_ebenfalls_weg():
    """Der Either-Or-Zweig ist derselbe Ladevorgang, nur anders gemessen."""
    m = _mapping((1, "verbrauch_kwh"), (2, "ladung_kwh"))
    beitraege = investition_beitraege(
        _inv(1, "e-auto"), _felder(m, 1), wallbox_deckt_ladung=True
    )
    assert beitraege == []


def test_andere_typen_bleiben_von_der_regel_unberuehrt():
    """Eine Wärmepumpe hat mit der E-Mob-Quellenfrage nichts zu tun."""
    m = _mapping((3, "stromverbrauch_kwh"))
    beitraege = investition_beitraege(
        _inv(3, "waermepumpe"), _felder(m, 3), wallbox_deckt_ladung=True
    )
    assert [b.feld for b in beitraege] == ["stromverbrauch_kwh"]


def test_parent_regel_gilt_weiterhin_unabhaengig():
    """Die ältere Bedingung bleibt — sie deckt den zugeordneten Fall ab."""
    m = _mapping((1, "ladung_kwh"))
    beitraege = investition_beitraege(
        _inv(1, "e-auto", parent=2), _felder(m, 1), wallbox_deckt_ladung=False
    )
    assert beitraege == []
