"""Slot-Konvention des LEISTUNGSPFADS — die fünfte Quelle (N-382).

``core/berechnungen/slot_konvention.py`` ist der SoT für die Backward-Konvention
(#144): **Slot h = Energie [h-1, h)**. Sein eigener Kopf nennt die IST-Seite mit
**zwei** Pfaden (Snapshot-Diffs und HA-LTS) und hält die Lehre fest, die
``c71b0f08`` (2026-06-04, „HA-LTS-Stundenpfad auf Backward angleichen — IST 1h zu
früh") hinterlassen hat: *„jeden Parallelpfad pinnen."*

``test_slot_konvention_quellen.py`` pinnt danach **vier** Quellen — OpenMeteo,
Solcast, IST-Snapshot, IST-LTS. Es gibt aber eine **fünfte**, und sie ist
ungepinnt: den **Leistungspfad**, aus dem ``aggregate_day`` das
``TagesEnergieProfil.komponenten``-JSON speist.

⭐ **Seit 2026-09-04 liegt er richtig** (N-382 gebaut). Der Absatz darunter
beschreibt, WARUM er versetzt lag und was die Umstellung ausmacht — er bleibt
stehen, weil die Proben genau diese Kanten prüfen.

**Warum er versetzt lag — am Code, nicht an Anlagendaten:**

* ``live_tagesverlauf_service.py:550``/``:847`` beschriften jeden Punkt mit dem
  **Slot-BEGINN** (``{h_start.hour}:{h_start.minute}``), und
  ``live_tagesverlauf_5min.py`` nennt das Raster wörtlich ``h_start <= p < h_end``.
  Ein Punkt „05:00" deckt also ``[05:00, 05:10)`` — **forward**.
* ``aggregator.py`` bucketet diese Punkte nach ihrem **Stundenlabel** und mittelt;
  Zeile ``h`` trägt damit ``[h, h+1)``.
* Die Spalte ``pv_kw`` derselben Zeile kommt aus ``kwh_pro_stunde[h]`` und ist
  **backward** — ``[h-1, h)``.

⇒ **Zeile ``h`` beschrieb zwei verschiedene Stunden.** Über 24 Slots hebt sich das
auf, weshalb Tagessummen, Monat und ROI unauffällig blieben; pro Stunde nicht —
im Client wurde daraus ein Phantom-Band „PV (übrige)" bzw., auf steigender
Kurve, ein Quellenstapel ÜBER der Erzeugung (BMeyendriesch, #405).

**Was der Bau geändert hat — und die zwei Kanten, die dazugehören:**

* ``aggregator.py`` bucketet einen Punkt ``"05:00"`` jetzt in **Slot 6**.
* **Slot 0** kann nicht aus dem eigenen Tag kommen — er trägt
  ``[Vortag 23:00, 00:00)``. ``get_tagesverlauf(mit_vortagsrand=True)`` macht
  dafür das bestehende Abruf-Fenster eine Stunde weiter auf (kein zweiter
  Tagesabruf: der Scheduler-Job läuft alle 15 Minuten) und liefert die Punkte
  **getrennt** unter ``"vortagsrand"`` — ein Punkt trägt nur seine Uhrzeit,
  ``"23:00"`` von gestern und von heute wären sonst nicht unterscheidbar.
* **Bucket 23** des Tages gehört in Slot 0 des FOLGETAGS und fällt hier weg.

⛔ **Diese Probe ist bewusst an ``aggregate_day`` gehängt, nicht an eine
Hilfsfunktion.** Eine neue Funktion „gibt den Backward-Slot zurück" gegen sich
selbst zu prüfen wäre eine Tautologie und könnte nie rot werden. Geprüft wird das
Verhalten des echten Schreibpfads.

⭐ **Und sie kommt trotzdem ohne Anlagendaten aus** — das physische Test-Intervall
wird hier konstruiert. Das ist Absicht: Der Versatz wurde zuerst an einer echten
Anlage gemessen (SMA, 14 Tage, alle Stundenpaare), aber eine Probe, die an einer
Instanz hängt, prüft nur deren Konfiguration mit. Wer sie liest, soll den Befund
am Code nachvollziehen können, nicht an fremden Daten.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.investition import Investition
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.energie_profil.source import Source
from backend.tests import factories

# Dasselbe physische Intervall wie in `test_slot_konvention_quellen.py`:
# [05:00, 06:00) → Backward-Slot 6.
INTERVALL_START_STUNDE = 5
BACKWARD_SLOT = 6

PV_KWH = 2.0


def _lts_nur_in_slot(slot: int, wert: float) -> dict:
    """HA-LTS-Stundenwerte: PV ausschließlich im Backward-Slot ``slot``."""
    return {
        h: {
            "pv": wert if h == slot else 0.0,
            "einspeisung": 0.0,
            "netzbezug": 0.0,
            "verbrauch": 0.0,
            "wp": None,
            "wallbox": None,
            "batterie_netto": 0.0,
            "verbrauch_sonstiges": None,
        }
        for h in range(24)
    }


def _tagesverlauf_nur_ab_stunde(stunde: int, wert: float) -> dict:
    """Leistungspfad: PV ausschließlich im Punkt, der ``stunde`` beginnt.

    24 Punkte, damit die Stunden-Schleife alle Zeilen anlegt — sonst gäbe es die
    Zeile des Backward-Slots gar nicht und der Test prüfte nichts.
    """
    return {
        "serien": [{"key": "pv_3", "kategorie": "pv"}],
        "punkte": [
            {"zeit": f"{h:02d}:00", "werte": {"pv_3": wert if h == stunde else 0.0}}
            for h in range(24)
        ],
    }


def _tagesverlauf_mit_rand(rand_wert: float) -> dict:
    """Leistungspfad mit einem Vortagsrand — PV ausschliesslich dort.

    Der Tag selbst liefert lauter Nullen; alles, was danach in einer Zeile
    steht, kann also nur aus ``[Vortag 23:00, 00:00)`` stammen.
    """
    return {
        "serien": [{"key": "pv_3", "kategorie": "pv"}],
        "punkte": [
            {"zeit": f"{h:02d}:00", "werte": {"pv_3": 0.0}} for h in range(24)
        ],
        "vortagsrand": [{"zeit": "23:00", "werte": {"pv_3": rand_wert}}],
    }


@pytest.mark.asyncio
async def test_leistungspfad_landet_im_selben_backward_slot_wie_der_zaehlerpfad(db) -> None:
    """Dasselbe physische Intervall [05:00, 06:00) muss in BEIDEN Hälften
    derselben ``TagesEnergieProfil``-Zeile stehen — Backward-Slot 6.

    Der Zählerpfad liefert es dort ab (HA-LTS, seit ``c71b0f08`` backward). Der
    Leistungspfad bucketet nach dem Punkt-Label und legt es in Zeile 5.
    Solange das so ist, trägt Zeile 6 den Zählerwert von ``[05,06)`` und das
    Komponenten-JSON von ``[06,07)``.
    """
    anlage = factories.mach_anlage_mit_mapping("SlotKonventionLeistungspfad")
    db.add(anlage)
    await db.flush()

    db.add(Investition(
        id=3, anlage_id=anlage.id, typ="pv-module", bezeichnung="pv",
        aktiv=True, anschaffungsdatum=date(2020, 1, 1),
    ))
    # Festes Datum statt Prozessuhr: die Suite läuft in drei Zeitzonen, und eine
    # Probe, die `date.today()` liest, wettet auf die Stunde ihres Laufs (N-167).
    tag = date(2026, 5, 4)
    db.add(MqttEnergySnapshot(
        anlage_id=anlage.id,
        timestamp=datetime.combine(tag, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.commit()

    from backend.services.energie_profil._helpers import StrompreisStunden
    from backend.services.energie_profil.aggregator import aggregate_day

    with patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=_lts_nur_in_slot(BACKWARD_SLOT, PV_KWH)),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ), patch(
        # Die Gegenstelle gehört gemockt — sonst greift der Aggregator nach der
        # Börsenpreis-API und der Testrahmen meldet einen blockierten Netzzugriff.
        # Für die Slot-Frage ist der Preis ohne Belang.
        "backend.services.energie_profil._helpers._get_strompreis_stunden",
        new=AsyncMock(return_value=StrompreisStunden(sensor={}, boerse={})),
    ):
        await aggregate_day(
            anlage, tag, db,
            source=Source.VOLLBACKFILL_FROM_LTS,
            prefetched_tagesverlauf=_tagesverlauf_nur_ab_stunde(
                INTERVALL_START_STUNDE, PV_KWH,
            ),
        )
    await db.commit()

    rows = (await db.execute(
        select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage.id,
            TagesEnergieProfil.datum == tag,
        ).order_by(TagesEnergieProfil.stunde)
    )).scalars().all()
    je_stunde = {r.stunde: r for r in rows}

    def pv_aus_komponenten(row) -> float:
        komp = getattr(row, "komponenten", None) or {}
        return sum(
            v for k, v in komp.items()
            if isinstance(v, (int, float)) and str(k).startswith(("pv", "bkw"))
        )

    # ── ERFÜLLT: der Zählerpfad liegt, wo der SoT ihn verlangt ──────────────
    assert je_stunde[BACKWARD_SLOT].pv_kw == pytest.approx(PV_KWH), (
        f"Der Zählerpfad muss [05:00, 06:00) in Slot {BACKWARD_SLOT} ablegen "
        "(Backward, slot_konvention.py + c71b0f08). Liegt er woanders, ist die "
        "Grundlage dieses Tests weg."
    )

    # ── ERFÜLLT seit 2026-09-04 (N-382 gebaut): der Leistungspfad liegt im
    # SELBEN Slot wie der Zählerpfad ────────────────────────────────────────
    # Bis dahin stand hier die OFFEN-Fassung, die den Versatz festhielt
    # (Slot 5 statt 6). Sie ist eingelöst: `aggregator.py` bucketet einen Punkt
    # „05:00" — der [05:00, 06:00) deckt — jetzt in Slot 6, und Slot 0 bekommt
    # den Rand des Vortags (`get_tagesverlauf(mit_vortagsrand=True)`).
    #
    # ⛔ Wird sie wieder rot, ist das KEIN Grund, sie zu lockern: dann tragen
    # Spalte und JSON derselben Zeile erneut zwei verschiedene Stunden, und
    # jede Auswertung, die beide je Stunde zusammenführt, rechnet quer über den
    # Versatz (`core/berechnungen/energie.py::geraete_spalte_kw`, die Achse-2-
    # Invariante, `TagVerlaufChart` im Client).
    treffer = [h for h, r in je_stunde.items() if pv_aus_komponenten(r) > 0]
    assert treffer == [BACKWARD_SLOT], (
        f"Der Leistungspfad muss [05:00, 06:00) in Slot {BACKWARD_SLOT} ablegen "
        f"— denselben Slot wie der Zählerpfad —, gefunden {treffer}. "
        "Beschriftungsquelle ist live_tagesverlauf_service.py (Slot-BEGINN), "
        "gebucketet wird in aggregator.py (`h + 1`)."
    )


async def _aggregiere(db, tag, prefetched: dict, lts_slot: int = BACKWARD_SLOT):
    """Gemeinsamer Rahmen der Proben darunter — eine Anlage, ein `aggregate_day`.

    Herausgezogen, damit die drei Kanten-Proben nicht je ihren eigenen Mock-
    Turm bauen. Wer hier etwas ändert, ändert es für alle drei — das ist der
    Zweck.
    """
    anlage = factories.mach_anlage_mit_mapping("SlotKonventionKanten")
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        id=3, anlage_id=anlage.id, typ="pv-module", bezeichnung="pv",
        aktiv=True, anschaffungsdatum=date(2020, 1, 1),
    ))
    db.add(MqttEnergySnapshot(
        anlage_id=anlage.id,
        timestamp=datetime.combine(tag, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.commit()

    from backend.services.energie_profil._helpers import StrompreisStunden
    from backend.services.energie_profil.aggregator import aggregate_day

    with patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=_lts_nur_in_slot(lts_slot, PV_KWH)),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.energie_profil._helpers._get_strompreis_stunden",
        new=AsyncMock(return_value=StrompreisStunden(sensor={}, boerse={})),
    ):
        await aggregate_day(
            anlage, tag, db,
            source=Source.VOLLBACKFILL_FROM_LTS,
            prefetched_tagesverlauf=prefetched,
        )
    await db.commit()

    rows = (await db.execute(
        select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage.id,
            TagesEnergieProfil.datum == tag,
        ).order_by(TagesEnergieProfil.stunde)
    )).scalars().all()
    return {r.stunde: r for r in rows}


def _pv_je_slot(je_stunde: dict) -> dict[int, float]:
    """{Slot: Σ PV aus dem Komponenten-JSON} — nur Slots mit einem Wert > 0."""
    treffer = {}
    for h, row in je_stunde.items():
        komp = getattr(row, "komponenten", None) or {}
        summe = sum(
            v for k, v in komp.items()
            if isinstance(v, (int, float)) and str(k).startswith(("pv", "bkw"))
        )
        if summe > 0:
            treffer[h] = summe
    return treffer


@pytest.mark.asyncio
async def test_der_backward_slot_0_kommt_aus_dem_vortagsrand(db) -> None:
    """Slot 0 trägt ``[Vortag 23:00, 00:00)`` — er kann es gar nicht anders.

    Ohne den Rand hätte Slot 0 nie ein Komponenten-JSON, das zu seiner eigenen
    Spalte passt: der Zählerpfad legt dort das Intervall vor Mitternacht ab, der
    Leistungspfad hatte davon keinen Punkt. Diese Probe misst, dass der Rand
    wirklich ankommt — der Tag selbst liefert nur Nullen, ein PV-Wert in Slot 0
    kann also ausschließlich von gestern stammen.
    """
    je_stunde = await _aggregiere(
        db, date(2026, 5, 4), _tagesverlauf_mit_rand(PV_KWH),
    )

    assert 0 in je_stunde, (
        "Die Zeile des Backward-Slots 0 fehlt ganz. Sie wird von der "
        "Punkte-Schleife angelegt — wer den Bucket 0 entfernt, verliert mit ihr "
        "auch `pv_kw`, Wetter und Preis dieser Stunde."
    )
    assert _pv_je_slot(je_stunde) == {0: pytest.approx(PV_KWH)}, (
        "Der Vortagsrand muss in Slot 0 landen und sonst nirgends, gefunden "
        f"{_pv_je_slot(je_stunde)}. Quelle ist `tv_data['vortagsrand']` "
        "(`get_tagesverlauf(mit_vortagsrand=True)`), gebucketet in "
        "`aggregator.py`."
    )


@pytest.mark.asyncio
async def test_die_letzte_stunde_des_tages_gehoert_in_den_folgetag(db) -> None:
    """Bucket 23 ist ``[23:00, 24:00)`` und damit Slot 0 des FOLGETAGS.

    ⚠ Er darf hier NICHT als Slot 23 landen — Slot 23 trägt ``[22:00, 23:00)``,
    und das ist genau der Versatz, den N-382 beseitigt hat. Er darf ebenso wenig
    in Slot 24 landen: den gibt es nicht.
    """
    je_stunde = await _aggregiere(
        db, date(2026, 5, 4), _tagesverlauf_nur_ab_stunde(23, PV_KWH),
    )

    assert _pv_je_slot(je_stunde) == {}, (
        "Der Punkt 23:00 deckt [23:00, 24:00) und gehört in Slot 0 des "
        f"Folgetags — er darf an diesem Tag nirgends stehen, gefunden "
        f"{_pv_je_slot(je_stunde)}."
    )
    assert set(je_stunde) <= set(range(24)), (
        f"Es darf keinen Slot außerhalb 0–23 geben, gefunden {sorted(je_stunde)}."
    )


@pytest.mark.asyncio
async def test_ohne_vortagsrand_bleibt_die_zeile_null_trotzdem_stehen(db) -> None:
    """Kein Rand ⇒ Slot 0 ohne Komponenten — aber MIT seiner Zeile.

    Die Kante ist nicht theoretisch: der erste Tag einer Anlage hat keinen
    Vortag, und HA hebt seine Historie nur begrenzt auf. Fiele die Zeile weg,
    verlöre der Tag `pv_kw`, Wetter und Preis der Stunde 0 — Größen, die mit dem
    Leistungspfad nichts zu tun haben und unschuldig mitbetroffen wären.
    """
    je_stunde = await _aggregiere(
        db, date(2026, 5, 4),
        # Gleiche Form wie oben, nur OHNE `vortagsrand`.
        _tagesverlauf_nur_ab_stunde(BACKWARD_SLOT - 1, PV_KWH),
        lts_slot=0,
    )

    assert 0 in je_stunde, (
        "Ohne Vortagsrand fehlt die Zeile des Slots 0 — dann schreibt die "
        "Punkte-Schleife sie gar nicht. Der Bucket muss auch leer angelegt "
        "werden (`stunden_buckets[0] = []`)."
    )
    assert je_stunde[0].pv_kw == pytest.approx(PV_KWH), (
        "Die Spalte `pv_kw` des Slots 0 kommt aus dem ZÄHLERPFAD und ist vom "
        "fehlenden Leistungs-Rand nicht betroffen. Steht sie hier nicht, hat "
        "die Zeile mehr verloren als ihr Komponenten-JSON."
    )
    assert not (je_stunde[0].komponenten or {}), (
        "Ohne Rand gibt es für Slot 0 keine Leistungswerte — dann gehört dort "
        "auch keiner hin. Eine 0 wäre eine Behauptung, kein Messwert."
    )
