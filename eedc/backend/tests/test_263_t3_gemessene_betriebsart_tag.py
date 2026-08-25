"""#263: der **gemessene** Betriebsart-Zweig gilt auch für einen einzelnen Tag.

**Der Fund** (2026-08-25): `wp_modus_gemessen` gab es in der Monatssicht
(`aktueller_monat.py`) und in der Jahressicht (`JahrAggregat.tsx`) — im
Tagespfad **gar nicht**: weder im Schema (`energie_profil/_shared.py`) noch im
Frontend-Typ noch in der Erhebung. `get_tagesdetail_kwh` führte die vier
`betriebsart_strom_*`-Zähler nicht in seiner `AUSGABE`-Map, der Tag erhob sie
also nie.

**Warum das sichtbar wurde:** Die Blockfabrik `KomponentenSektionen.tsx` ist
für Monat und Tag **dieselbe** und gattert auf
``wp_modus_gemessen || wp_modus_abdeckung_h > 0``. Ein Betriebsart-Zähler hat
keine „Stunden mit Signal" — die Abdeckung ist dann 0. Ergebnis: Wer die mit
v4.0.24 eingeführten Zähler zuordnete, sah die Aufteilung in Monat und Jahr und
unter *Cockpit → Tag* **nie**, ohne dass etwas fehlte.

Dieselbe Klasse wie F-56, nur eine Fläche weiter: dort fehlte der
Gemessen-Zweig im HA-Export.

Schwesterdateien: `test_263_t2_modus_split_tag.py` (der **abgeleitete** Zweig
desselben Tages — die beiden Zweige treffen sich in `get_tag_detail`, und die
Vorrang-Regel „gemessen schlägt abgeleitet" ist nur im Paar prüfbar) und
`test_263_t1_geraete_spalten_beide_pfade.py`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)

DATUM = date(2025, 6, 15)


async def _anlage_mit_zaehlern(db, *, felder_werte, wp_tag_kwh=10.0, suffix=""):
    """Anlage + Klimaanlage mit gemappten Betriebsart-Zählern.

    `felder_werte`: ``{basis_feldname: tages_kwh}``. `suffix` hängt eine
    Innengerät-Kennung an die Feldnamen (`…_kuehlen_kwh-3`).
    """
    anlage = Anlage(anlagenname="T3", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Splitklima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter={"wp_art": "luft_luft"},
    )
    db.add(inv)
    await db.flush()

    felder = {}
    t0 = datetime.combine(DATUM, datetime.min.time())
    for basis, tages_kwh in felder_werte.items():
        feld = f"{basis}{suffix}"
        sensor_id = f"sensor.klima_{basis}"
        felder[feld] = {"strategie": "sensor", "sensor_id": sensor_id}
        key = f"inv:{inv.id}:{feld}"
        # Boundary-Diff über [Tag 00:00, Folgetag 00:00): Startstand 100.
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                              zeitpunkt=t0, wert_kwh=100.0, quelle="ha_statistics"))
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                              zeitpunkt=t0 + timedelta(days=1),
                              wert_kwh=100.0 + tages_kwh, quelle="ha_statistics"))

    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": felder}}}
    # Tages-Bezug: `TagesZusammenfassung.komponenten_kwh` führt die WP positiv.
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=DATUM,
        komponenten_kwh={f"waermepumpe_{inv.id}": wp_tag_kwh},
    ))
    await db.commit()
    return anlage, inv


async def test_t3_gemessene_zaehler_erreichen_den_tag(db):
    """Der Kern des Fundes: der Tag erhebt die Betriebsart-Zähler überhaupt."""
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_zaehlern(db, felder_werte={
        "betriebsart_strom_heizen_kwh": 3.0,
        "betriebsart_strom_kuehlen_kwh": 5.0,
    })
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )
    assert str(inv.id) in werte
    assert werte[str(inv.id)]["betriebsart_strom_heizen_kwh"] == 3.0
    assert werte[str(inv.id)]["betriebsart_strom_kuehlen_kwh"] == 5.0


async def test_t3_innengeraet_suffix_wird_nicht_verschluckt(db):
    """`…_kuehlen_kwh-3` muss ankommen — mit UNVERÄNDERTEM Namen.

    Die Auflösung *Gerätefeld gewinnt, sonst Σ Innengeräte* gehört dem SoT
    `modus_strom_zeile`; hier vorab zu summieren wäre die Doppelzählungs-Klasse.
    """
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_zaehlern(db, suffix="-3", felder_werte={
        "betriebsart_strom_kuehlen_kwh": 4.0,
    })
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )
    assert werte[str(inv.id)] == {"betriebsart_strom_kuehlen_kwh-3": 4.0}


async def test_t3_tag_detail_meldet_gemessen(db):
    """Die Route füllt `wp_modus_gemessen` — das Feld, an dem der Block hängt."""
    from backend.api.routes.energie_profil.views import get_tag_detail

    anlage, inv = await _anlage_mit_zaehlern(db, wp_tag_kwh=10.0, felder_werte={
        "betriebsart_strom_heizen_kwh": 3.0,
        "betriebsart_strom_kuehlen_kwh": 5.0,
    })
    resp = await get_tag_detail(anlage.id, DATUM, db)

    assert resp.wp_modus_gemessen is True
    assert resp.wp_modus_strom_heizen_kwh == 3.0
    assert resp.wp_modus_strom_kuehlen_kwh == 5.0
    # Lüften/Entfeuchten und Standby fallen unter „nicht aufgeteilt":
    # 10 − 3 − 5 = 2 (Entscheid Gernot 2026-08-25 — erst differenzieren, wenn
    # Anwender es verlangen).
    assert resp.wp_modus_nicht_aufgeteilt_kwh == 2.0
    # Ein Betriebsart-Zähler hat keine „Stunden mit Signal".
    assert resp.wp_modus_abdeckung_h == 0.0


async def test_t3_widerspruch_laesst_das_geraet_ganz_aus(db):
    """Σ Teilmengen > Bezug ⇒ Gerät auslassen statt kappen.

    Dieselbe Invariante wie `teilmengen_passen` im abgeleiteten Zweig: eine
    stille Kappung machte aus einem Widerspruch eine plausible Zahl.
    """
    from backend.api.routes.energie_profil.views import get_tag_detail

    anlage, inv = await _anlage_mit_zaehlern(db, wp_tag_kwh=2.0, felder_werte={
        "betriebsart_strom_heizen_kwh": 30.0,
    })
    resp = await get_tag_detail(anlage.id, DATUM, db)
    assert resp.wp_modus_gemessen is None
    assert resp.wp_modus_strom_heizen_kwh is None


async def test_t3_ohne_zaehler_bleibt_alles_wie_bisher(db):
    """Kein Betriebsart-Zähler ⇒ keine Aussage (P4), kein leerer Block."""
    from backend.api.routes.energie_profil.views import get_tag_detail

    anlage, inv = await _anlage_mit_zaehlern(db, felder_werte={})
    resp = await get_tag_detail(anlage.id, DATUM, db)
    assert resp.wp_modus_gemessen is None
    assert resp.wp_modus_strom_heizen_kwh is None
    assert resp.wp_modus_abdeckung_h is None
