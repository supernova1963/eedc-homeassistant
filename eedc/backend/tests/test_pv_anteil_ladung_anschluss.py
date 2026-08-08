"""Der abgeleitete PV-Anteil der Heimladung erreicht die Monatszeile (N-141 c).

Der Rechenkern (`core/berechnungen/pv_anteil_ladung.py`) ist mit `ed874a9f`
gebaut und in `test_pv_anteil_ladung.py` für sich geprüft. Diese Datei prüft den
**Anschluss** — also genau das, was am 08.08. bewusst gefehlt hat: dass die
Ableitung eine angezeigte Zahl bewegt, und zwar nur dort, wo sie darf.

Geprüft wird die Kette in beide Richtungen:

- **Rahmenbedingung 1** — ein gepflegter Wert gewinnt immer, und zwar auch die
  gepflegte **0**. Das ist die F-15-Klasse eine Ebene weiter: dort verschluckte
  `wert or DEFAULT` eine gepflegte 0, hier täte es eine Schätzung.
- **Die Trias bleibt geschlossen** (`ladung == pv + netz`). Abgeleitet wird der
  *Anteil*, nicht die Kilowattstunde — sonst entsteht der #262-Fehler
  (PV-Anteil > 100 %), sobald Tagesebene und Monatszeile verschiedene
  Ladungsmengen kennen. Genau dieser Fall steht unten als eigene Probe.
- **Rahmenbedingung 5** — keine rückwirkende Neuberechnung: ein Monat, dessen
  Tageszeilen die Spalten noch nicht tragen (Bestand vor der Migration), bleibt
  unverändert.
- **Die Kennzeichnung** (`ladung_anteil_abgeleitet`, Rahmenbedingung 4): eine
  Schätzung, die aussieht wie eine Messung, ist der Fehler, den die P4-Linie
  verhindern soll.
- **Die Grundgesamtheit** darf sich NICHT ändern: das Nachladen der Tagesebene
  geschieht für den Ladeanteil, nicht um neue Monate aufzumachen (N-121 hat das
  bewusst hinter `inkl_nur_tageswerte` gestellt).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil._provenance_helpers import seed_tz_provenance
from backend.services.monats_fakten import (
    TAGESWERT_EMOB_ANTEIL,
    lade_monats_fakten,
)
from backend.services.provenance import (
    ABGELEITET_EINSPEISE_DECKUNG,
    ABGELEITET_EINSPEISE_DECKUNG_TEILWEISE,
)

ANSCHAFFUNG = date(2024, 1, 1)


async def _anlage(db) -> Anlage:
    anlage = Anlage(anlagenname="Ladeanteil", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage


async def _inv(db, anlage, typ, bezeichnung, **kwargs) -> Investition:
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung=bezeichnung,
        anschaffungsdatum=ANSCHAFFUNG, **kwargs,
    )
    db.add(inv)
    await db.flush()
    return inv


def _imd(inv, jahr, monat, daten) -> InvestitionMonatsdaten:
    return InvestitionMonatsdaten(
        investition_id=inv.id, jahr=jahr, monat=monat, verbrauch_daten=daten
    )


def _tag(anlage, tag: date, *, pv: float | None, netz: float | None):
    """Eine Tageszeile mit (oder ohne) abgeleitetem Ladeanteil."""
    return TagesZusammenfassung(
        anlage_id=anlage.id,
        datum=tag,
        emob_ladung_pv_abgeleitet_kwh=pv,
        emob_ladung_netz_abgeleitet_kwh=netz,
    )


def _fakt(fakten, jahr, monat):
    treffer = [f for f in fakten if f.schluessel == (jahr, monat)]
    assert treffer, (
        f"kein MonatsFakt für {jahr}-{monat:02d} — vorhanden: "
        f"{[f.schluessel for f in fakten]}"
    )
    return treffer[0]


# ═══════════════════════════════════════════════════════════════════════
# Die Lücke, die der Fund schließt
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_heimladung_ohne_gepflegten_pv_anteil_wird_abgeleitet(db):
    """Ohne evcc gab es für den PV-Anteil gar keine Quelle — jetzt schon.

    Vorher galt die **gesamte** Heimladung als Netzstrom (`get_emob_pv_netz_kwh`
    liefert bei fehlendem `ladung_pv_kwh` genau `(0, total)`). Das ist keine
    Messung, sondern eine Behauptung.
    """
    anlage = await _anlage(db)
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(wb, 2025, 5, {"ladung_kwh": 200.0}))
    # Tagesebene: 60 % der gedeckten Ladung kam aus der Sonne.
    db.add(_tag(anlage, date(2025, 5, 10), pv=30.0, netz=20.0))
    db.add(_tag(anlage, date(2025, 5, 11), pv=30.0, netz=20.0))
    await db.commit()

    fakt = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5)
    emob = fakt.emob

    assert emob.ladung_anteil_abgeleitet is True
    assert emob.ladung_pv_kwh == pytest.approx(120.0), "60 % von 200 kWh"
    assert emob.ladung_netz_kwh == pytest.approx(80.0)
    assert TAGESWERT_EMOB_ANTEIL in fakt.meta.tageswert_gruppen, (
        "eine Sicht muss erkennen können, dass die Aufteilung nicht aus der DB kommt"
    )


@pytest.mark.asyncio
async def test_die_trias_bleibt_geschlossen_auch_bei_anderer_tagesmenge(db):
    """Der **Anteil** wird übernommen, nicht die Kilowattstunde (#262-Schutz).

    Tagesebene und Monatszeile kennen hier absichtlich **verschiedene**
    Ladungsmengen: die Tagesspur deckt nur 50 kWh ab, die Monatszeile trägt 200.
    Wer die abgeleiteten kWh direkt übernähme, schriebe 30 kWh PV neben 200 kWh
    Ladung — die Trias wäre offen, und in der anderen Richtung (Tagesspur größer
    als Monat) käme ein PV-Anteil über 100 % heraus.
    """
    anlage = await _anlage(db)
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(wb, 2025, 5, {"ladung_kwh": 200.0}))
    db.add(_tag(anlage, date(2025, 5, 10), pv=30.0, netz=20.0))
    await db.commit()

    emob = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5).emob

    assert emob.ladung_pv_kwh + emob.ladung_netz_kwh == pytest.approx(
        emob.ladung_kwh
    ), "die Trias muss exakt aufgehen"
    assert emob.ladung_pv_kwh <= emob.ladung_kwh, "kein PV-Anteil über 100 %"
    assert emob.ladung_pv_kwh == pytest.approx(120.0), (
        "60 % Anteil auf die kanonische Monatsladung, nicht die 30 kWh der Tagesspur"
    )


# ═══════════════════════════════════════════════════════════════════════
# Rahmenbedingung 1 — der gepflegte Wert gewinnt
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_gepflegter_pv_anteil_schlaegt_die_ableitung(db):
    """Ein erfasster Wert wird nie überschrieben — auch nicht von einer
    Tagesebene, die etwas ganz anderes sagt."""
    anlage = await _anlage(db)
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(wb, 2025, 5, {"ladung_kwh": 200.0,
                              "ladung_pv_kwh": 150.0,
                              "ladung_netz_kwh": 50.0}))
    db.add(_tag(anlage, date(2025, 5, 10), pv=10.0, netz=90.0))
    await db.commit()

    emob = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5).emob

    assert emob.ladung_anteil_abgeleitet is False
    assert emob.ladung_pv_kwh == pytest.approx(150.0)
    assert emob.ladung_netz_kwh == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_gepflegte_null_ist_eine_aussage_keine_luecke(db):
    """**Die F-15-Klasse, eine Ebene weiter.**

    „Diesen Monat kam nichts aus der Sonne" ist eine Aussage. Wer sie als Lücke
    liest und eine Schätzung darüberschreibt, macht denselben Fehler wie
    `wert or DEFAULT` bei der Einspeisevergütung — nur mit kWh statt Cent.
    """
    anlage = await _anlage(db)
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(wb, 2025, 5, {"ladung_kwh": 200.0, "ladung_pv_kwh": 0.0}))
    db.add(_tag(anlage, date(2025, 5, 10), pv=60.0, netz=40.0))
    await db.commit()

    emob = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5).emob

    assert emob.ladung_anteil_abgeleitet is False, (
        "eine gepflegte 0 darf keine Ableitung auslösen"
    )
    assert emob.ladung_pv_kwh == pytest.approx(0.0)
    assert emob.ladung_netz_kwh == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_pflege_auf_der_anderen_quelle_zaehlt_auch(db):
    """Der Pool wählt die Wallbox, gepflegt ist der Anteil am Fahrzeug.

    Die Quellenwahl ist eine Frage der **Menge**, nicht der **Pflege** — wer den
    Anteil irgendwo erfasst hat, bekommt keine Schätzung.
    """
    anlage = await _anlage(db)
    auto = await _inv(db, anlage, "e-auto", "Auto")
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(auto, 2025, 5, {"ladung_kwh": 80.0, "ladung_pv_kwh": 40.0}))
    db.add(_imd(wb, 2025, 5, {"ladung_kwh": 200.0}))
    db.add(_tag(anlage, date(2025, 5, 10), pv=90.0, netz=10.0))
    await db.commit()

    emob = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5).emob

    assert emob.quelle == "wallbox"
    assert emob.ladung_anteil_abgeleitet is False


# ═══════════════════════════════════════════════════════════════════════
# Rahmenbedingung 5 + Abgrenzungen
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bestandstage_ohne_ableitung_bleiben_unveraendert(db):
    """**Rahmenbedingung 5**: keine rückwirkende Neuberechnung.

    Tageszeilen aus der Zeit vor diesem Feature tragen NULL in beiden Spalten.
    Sie dürfen die Monatszeile nicht bewegen — und schon gar nicht auf 0 % PV
    festnageln, denn NULL heißt „keine Aussage", nicht „keine Sonne".
    """
    anlage = await _anlage(db)
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(wb, 2025, 5, {"ladung_kwh": 200.0}))
    db.add(_tag(anlage, date(2025, 5, 10), pv=None, netz=None))
    await db.commit()

    emob = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5).emob

    assert emob.ladung_anteil_abgeleitet is False
    assert emob.ladung_pv_kwh == pytest.approx(0.0), "unveraendertes Bestandsverhalten"
    assert emob.ladung_netz_kwh == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_ohne_heimladung_wird_die_tagesebene_nicht_gebraucht(db):
    """Ein Monat ohne E-Mobilität bekommt keinen abgeleiteten Anteil — und die
    Vorprüfung verhindert, dass dafür überhaupt geladen wird."""
    anlage = await _anlage(db)
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(wb, 2025, 5, {"ladung_kwh": 0.0}))
    db.add(_tag(anlage, date(2025, 5, 10), pv=60.0, netz=40.0))
    await db.commit()

    emob = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5).emob

    assert emob.ladung_anteil_abgeleitet is False
    assert emob.ladung_kwh == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_nachladen_fuer_den_anteil_macht_keine_neuen_monate_auf(db):
    """Die Grundgesamtheit bleibt, was sie war (N-121-Abgrenzung).

    Mai hat eine Monatszeile, Juli **nur** eine Tagesspur. Ohne
    `inkl_nur_tageswerte` darf Juli nicht auftauchen — obwohl die Tagesebene
    für den Ladeanteil des Mai geladen wurde.
    """
    anlage = await _anlage(db)
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(wb, 2025, 5, {"ladung_kwh": 200.0}))
    db.add(_tag(anlage, date(2025, 5, 10), pv=60.0, netz=40.0))
    db.add(_tag(anlage, date(2025, 7, 10), pv=10.0, netz=10.0))
    await db.commit()

    ohne_flag = await lade_monats_fakten(db, anlage.id)
    assert [f.schluessel for f in ohne_flag] == [(2025, 5)], (
        "das Nachladen fuer den Ladeanteil erweitert die Grundgesamtheit NICHT"
    )
    # Gegenprobe: mit dem Flag ist Juli da — sonst prüfte die Zeile darüber
    # nur, dass die Tagesebene gar nicht gelesen wurde.
    mit_flag = await lade_monats_fakten(db, anlage.id, inkl_nur_tageswerte=True)
    assert (2025, 7) in [f.schluessel for f in mit_flag]


# ═══════════════════════════════════════════════════════════════════════
# Rahmenbedingung 4 — die Zahl sagt, dass sie gerechnet ist
# ═══════════════════════════════════════════════════════════════════════


class TestProvenanceMarke:
    """Der Source-Tag beschreibt den **Lauf**, die Marke die **Herkunft**.

    Ohne die Marke trüge eine Schätzung dasselbe `external:ha_statistics:daily`
    wie ein Zählerwert — sie sähe aus wie eine Messung. Und war nicht jede
    Ladestunde gedeckt, muss die Marke auch das sagen (P4): eine Teilsumme, die
    aussieht wie eine Gesamtsumme, ist der Fehler, den die Linie verhindert.
    """

    def _row(self, pv, netz):
        return TagesZusammenfassung(
            anlage_id=1, datum=date(2025, 5, 10),
            emob_ladung_pv_abgeleitet_kwh=pv,
            emob_ladung_netz_abgeleitet_kwh=netz,
            ueberschuss_kwh=12.0,
        )

    def test_vollstaendige_deckung_traegt_die_regel(self):
        row = self._row(60.0, 40.0)
        seed_tz_provenance(
            row, writer="test", source="external:ha_statistics:daily",
            abgeleitet_je_feld={
                "emob_ladung_pv_abgeleitet_kwh": ABGELEITET_EINSPEISE_DECKUNG,
                "emob_ladung_netz_abgeleitet_kwh": ABGELEITET_EINSPEISE_DECKUNG,
            },
        )
        eintrag = row.source_provenance["emob_ladung_pv_abgeleitet_kwh"]
        assert eintrag["abgeleitet"] == ABGELEITET_EINSPEISE_DECKUNG
        assert eintrag["source"] == "external:ha_statistics:daily", (
            "die Marke ersetzt den Source-Tag nicht, sie tritt daneben"
        )

    def test_teilweise_deckung_ist_eine_andere_marke(self):
        row = self._row(60.0, 40.0)
        seed_tz_provenance(
            row, writer="test", source="external:ha_statistics:daily",
            abgeleitet_je_feld={
                "emob_ladung_pv_abgeleitet_kwh":
                    ABGELEITET_EINSPEISE_DECKUNG_TEILWEISE,
            },
        )
        assert (
            row.source_provenance["emob_ladung_pv_abgeleitet_kwh"]["abgeleitet"]
            != ABGELEITET_EINSPEISE_DECKUNG
        ), "eine Teilsumme darf nicht dieselbe Marke tragen wie eine volle Deckung"

    def test_gemessene_spalten_bleiben_ohne_marke(self):
        """Abgrenzung: die Marke gilt genau den zwei Spalten.

        Ohne diese Probe bliebe unbemerkt, wenn `abgeleitet_je_feld` alle
        Felder markierte — dann trüge jeder Zählerwert der Tageszeile den
        Stempel „gerechnet".
        """
        row = self._row(60.0, 40.0)
        seed_tz_provenance(
            row, writer="test", source="external:ha_statistics:daily",
            abgeleitet_je_feld={
                "emob_ladung_pv_abgeleitet_kwh": ABGELEITET_EINSPEISE_DECKUNG,
            },
        )
        assert "abgeleitet" not in row.source_provenance["ueberschuss_kwh"]
        assert (
            "abgeleitet" not in row.source_provenance["emob_ladung_netz_abgeleitet_kwh"]
        )


# ═══════════════════════════════════════════════════════════════════════
# Der Aggregator-Lauf selbst — schreibt er die Spalten und die Marke?
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_aggregate_day_schreibt_den_abgeleiteten_ladeanteil(db):
    """Der **Integrationsbeweis**: ohne ihn wären nur die Bausteine geprüft.

    Die Proben oben zeigen, dass der Layer richtig rechnet und die Monatszeile
    richtig liest. Sie zeigen **nicht**, dass der Aggregator die Rechnung
    überhaupt anstößt und ihr Ergebnis ablegt — genau das war am 08.08. der
    Unterschied zwischen „Rechenkern gebaut" und „eine Zahl hat sich bewegt".

    Aufbau: zwei Ladestunden. In der ersten wird bei laufender Einspeisung
    geladen (voll gedeckt ⇒ PV), in der zweiten ausschließlich aus dem Netz.
    """
    from unittest.mock import AsyncMock, patch

    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.services.energie_profil.aggregator import Source, aggregate_day

    anlage = Anlage(
        anlagenname="Ladeanteil-Aggregat", leistung_kwp=10.0,
        standort_plz="10115", standort_land="DE",
        wechselrichter_hersteller="generic", sensor_mapping={},
    )
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    db.add(MqttEnergySnapshot(
        anlage_id=anlage.id,
        timestamp=datetime.combine(gestern, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug", value_kwh=100.0,
    ))
    await db.commit()

    stunden = {h: {} for h in range(24)}
    # 12:00 — 4 kWh geladen, gleichzeitig 6 kWh eingespeist ⇒ voll aus der Sonne.
    stunden[12] = {"pv": 10.0, "einspeisung": 6.0, "netzbezug": 0.0,
                   "wallbox": 4.0, "verbrauch": 4.0, "batterie_netto": 0.0}
    # 20:00 — 3 kWh geladen, alles aus dem Netz, keine Einspeisung, kein Speicher.
    stunden[20] = {"pv": 0.0, "einspeisung": 0.0, "netzbezug": 3.0,
                   "wallbox": 3.0, "verbrauch": 3.0, "batterie_netto": 0.0}

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={
            "serien": [],
            "punkte": [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)],
        }),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=stunden),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        tz = await aggregate_day(anlage, gestern, db, source=Source.MANUAL_REPAIR)

    assert tz is not None
    assert tz.emob_ladung_pv_abgeleitet_kwh == pytest.approx(4.0), (
        "die Einspeisung derselben Stunde deckt die Ladung"
    )
    assert tz.emob_ladung_netz_abgeleitet_kwh == pytest.approx(3.0)

    marke = tz.source_provenance["emob_ladung_pv_abgeleitet_kwh"]["abgeleitet"]
    assert marke == ABGELEITET_EINSPEISE_DECKUNG, (
        "beide Ladestunden waren gedeckt ⇒ keine Teilsummen-Marke"
    )
    # Abgrenzung, feldunabhängig formuliert: **genau** die zwei Ladeanteils-
    # Spalten tragen den Stempel, kein gemessener Wert daneben. Ein fest
    # benanntes Vergleichsfeld wäre brüchig — `stunden_verfuegbar` steht in
    # dieser Row gar nicht in der Provenance (gemessen), und die Probe hätte
    # dann aus dem falschen Grund gehalten oder gebrochen.
    markiert = {
        feld for feld, eintrag in tz.source_provenance.items()
        if isinstance(eintrag, dict) and "abgeleitet" in eintrag
    }
    assert markiert == {
        "emob_ladung_pv_abgeleitet_kwh",
        "emob_ladung_netz_abgeleitet_kwh",
    }, f"nur die abgeleiteten Spalten dürfen den Stempel tragen, markiert: {markiert}"


@pytest.mark.asyncio
async def test_aggregate_day_ohne_ladung_laesst_die_spalten_leer(db):
    """Keine Heimladung ⇒ **keine Aussage**, nicht 0.

    Eine 0 hier wäre die Behauptung „diese Anlage hat nichts aus der Sonne
    geladen" — dieselbe stille Falsch-Aussage, die der Fund auflöst, nur mit
    umgekehrtem Vorzeichen.
    """
    from unittest.mock import AsyncMock, patch

    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.services.energie_profil.aggregator import Source, aggregate_day

    anlage = Anlage(
        anlagenname="Ohne Ladung", leistung_kwp=10.0,
        standort_plz="10115", standort_land="DE",
        wechselrichter_hersteller="generic", sensor_mapping={},
    )
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    db.add(MqttEnergySnapshot(
        anlage_id=anlage.id,
        timestamp=datetime.combine(gestern, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug", value_kwh=100.0,
    ))
    await db.commit()

    stunden = {h: {} for h in range(24)}
    stunden[12] = {"pv": 10.0, "einspeisung": 6.0, "netzbezug": 0.0,
                   "wallbox": None, "verbrauch": 4.0, "batterie_netto": 0.0}

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={
            "serien": [],
            "punkte": [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)],
        }),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=stunden),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        tz = await aggregate_day(anlage, gestern, db, source=Source.MANUAL_REPAIR)

    assert tz is not None
    assert tz.emob_ladung_pv_abgeleitet_kwh is None
    assert tz.emob_ladung_netz_abgeleitet_kwh is None
    assert "emob_ladung_pv_abgeleitet_kwh" not in tz.source_provenance


@pytest.mark.asyncio
async def test_aggregate_day_kennzeichnet_eine_unvollstaendige_deckung(db):
    """Nicht jede Ladestunde war auswertbar ⇒ **andere Marke** (P4).

    ⚠ Diese Probe existiert, weil ein Sprengsatz **stumm** blieb: „immer die
    volle Marke setzen" brach nichts, denn alle bisherigen Fälle waren voll
    gedeckt. Eine Invarianz-Probe ohne den teilweise gedeckten Fall belegt die
    Unterscheidung nicht — sie behauptet sie nur.

    Aufbau: 12:00 vollständig (⇒ zählt), 20:00 lädt, hat aber keinen
    Netzbezugswert (⇒ ungedeckt, fällt aus den Summen).
    """
    from unittest.mock import AsyncMock, patch

    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.services.energie_profil.aggregator import Source, aggregate_day

    anlage = Anlage(
        anlagenname="Teildeckung", leistung_kwp=10.0,
        standort_plz="10115", standort_land="DE",
        wechselrichter_hersteller="generic", sensor_mapping={},
    )
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    db.add(MqttEnergySnapshot(
        anlage_id=anlage.id,
        timestamp=datetime.combine(gestern, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug", value_kwh=100.0,
    ))
    await db.commit()

    stunden = {h: {} for h in range(24)}
    stunden[12] = {"pv": 10.0, "einspeisung": 6.0, "netzbezug": 0.0,
                   "wallbox": 4.0, "verbrauch": 4.0, "batterie_netto": 0.0}
    stunden[20] = {"pv": 0.0, "einspeisung": 0.0, "netzbezug": None,
                   "wallbox": 3.0, "verbrauch": 3.0, "batterie_netto": 0.0}

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={
            "serien": [],
            "punkte": [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)],
        }),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=stunden),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        tz = await aggregate_day(anlage, gestern, db, source=Source.MANUAL_REPAIR)

    assert tz is not None
    assert tz.emob_ladung_pv_abgeleitet_kwh == pytest.approx(4.0), (
        "nur die gedeckte Stunde geht in die Summe"
    )
    assert tz.emob_ladung_netz_abgeleitet_kwh == pytest.approx(0.0)
    assert (
        tz.source_provenance["emob_ladung_pv_abgeleitet_kwh"]["abgeleitet"]
        == ABGELEITET_EINSPEISE_DECKUNG_TEILWEISE
    ), "die ungedeckte Ladestunde macht den Wert zur Teilsumme — das muss dranstehen"
