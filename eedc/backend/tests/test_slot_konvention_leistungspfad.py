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

**Warum er versetzt liegt — am Code, nicht an Anlagendaten:**

* ``live_tagesverlauf_service.py:550``/``:847`` beschriften jeden Punkt mit dem
  **Slot-BEGINN** (``{h_start.hour}:{h_start.minute}``), und
  ``live_tagesverlauf_5min.py`` nennt das Raster wörtlich ``h_start <= p < h_end``.
  Ein Punkt „05:00" deckt also ``[05:00, 05:10)`` — **forward**.
* ``aggregator.py`` bucketet diese Punkte nach ihrem **Stundenlabel** und mittelt;
  Zeile ``h`` trägt damit ``[h, h+1)``.
* Die Spalte ``pv_kw`` derselben Zeile kommt aus ``kwh_pro_stunde[h]`` und ist
  **backward** — ``[h-1, h)``.

⇒ **Zeile ``h`` beschreibt zwei verschiedene Stunden.** Über 24 Slots hebt sich das
auf, weshalb Tagessummen, Monat und ROI unauffällig bleiben; pro Stunde nicht.

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

    # ── OFFEN (N-382): der Leistungspfad liegt eine Stunde davor ────────────
    # Diese Probe hält den HEUTIGEN Zustand fest und schlägt fehl, sobald gebaut
    # wird — dann ist sie auf `treffer == [BACKWARD_SLOT]` umzustellen und dieser
    # Block samt Kommentar zu entfernen. Kein `xfail` (Muster gibt es im Baum
    # nicht, s. test_soll_waerme_klima_achse*.py).
    treffer = [h for h, r in je_stunde.items() if pv_aus_komponenten(r) > 0]
    assert treffer == [INTERVALL_START_STUNDE], (
        "Erwartet war der heutige, FEHLERHAFTE Zustand: der Leistungspfad legt "
        f"[05:00, 06:00) in Slot {INTERVALL_START_STUNDE} statt {BACKWARD_SLOT}, "
        f"gefunden {treffer}. Zwei Deutungen — (a) N-382 ist gebaut: dann diesen "
        f"Block durch `assert treffer == [{BACKWARD_SLOT}]` ersetzen; (b) der "
        "Leistungspfad hat sich anders bewegt: dann erst messen, welche "
        "Konvention er jetzt trägt (live_tagesverlauf_service.py:550/:847 "
        "beschriften mit dem Slot-BEGINN, aggregator.py bucketet nach diesem "
        "Label)."
    )
