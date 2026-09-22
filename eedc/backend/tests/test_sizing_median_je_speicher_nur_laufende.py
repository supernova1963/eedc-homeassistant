"""Die SoC-Aufschlüsselung des Sizing-Simulators nennt nur laufende Geräte
(Nachlese 4.0.50, A5).

**Ein Block widersprach sich selbst.** Seit N-546 zählt `anzahl_speicher` nur die
heute laufenden Speicher — der Hinweistext darunter sagt „Diese Anlage hat 1
Speicher". Die Liste **darüber** (`median_je_speicher`, gerendert als „Speicher
<id>" in `v4/SpeicherSizingIST.tsx`) kam aus
`TagesEnergieProfil.soc_je_speicher` und faltete **alle** IDs der Stundenzeilen,
auch die eines längst ausgebauten Geräts. Der Anwender las also zwei Zeilen unter
der Überschrift „1 Speicher", und die zweite trug eine ID, die sonst nirgends
mehr vorkommt.

**Warum die Liste und nicht der Ladestand:** `soc_prozent` einer Stundenzeile ist
ein historischer Messwert der **Anlage** (kapazitätsgewichtet, N-239) — er bleibt
richtig, auch wenn ein Gerät später ausgebaut wird, und er ist die Grundlage der
Kalibrierung. Die **Aufschlüsselung je Gerät** dagegen ist eine Aussage über den
heutigen Bestand; dort gehört das ausgebaute Gerät nicht hin. Genau deshalb sitzt
der Filter im Service und nicht im Layer.

⚠ **Feste Daten, kein `date.today()`** (`test_konformitaet_echte_uhr_in_tests.py`).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.api.routes.investitionen import get_speicher_sizing
from backend.models import Anlage, Investition, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil

STILLGELEGT_VERGANGENHEIT = date(2021, 3, 31)
STILLGELEGT_ZUKUNFT = date(2099, 12, 31)


async def _seed(db, *, aktiv_alt: bool = True,
                stillgelegt: date | None = STILLGELEGT_VERGANGENHEIT) -> tuple[int, int, int]:
    anlage = Anlage(anlagenname="A5", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    alt = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher alt",
        anschaffungsdatum=date(2015, 1, 1),
        parameter={"kapazitaet_kwh": 5.06, "nutzbare_kapazitaet_kwh": 5.06,
                   "wirkungsgrad_prozent": 85},
        aktiv=aktiv_alt, stilllegungsdatum=stillgelegt,
    )
    db.add(alt)
    await db.flush()
    neu = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher neu",
        anschaffungsdatum=date(2025, 6, 1),
        parameter={"kapazitaet_kwh": 12.8, "nutzbare_kapazitaet_kwh": 10.24,
                   "wirkungsgrad_prozent": 95},
    )
    db.add(neu)
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=35.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.commit()
    return anlage.id, alt.id, neu.id


def _tag(db, anlage_id: int, tag: date, *, alt_id: int, neu_id: int):
    """24 Stunden mit **zwei** Geräte-Ladeständen je Zeile.

    Die beiden Mediane sind bewusst verschieden (40 % alt, 70 % neu), damit ein
    Prüfer, der nur die Anzahl der Einträge zählt, nicht mit dem verwechselt
    werden kann, der die richtige ID behält.
    """
    for h in range(24):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=tag, stunde=h,
            pv_kw=6.0 if 10 <= h < 16 else 0.0, verbrauch_kw=0.7,
            soc_prozent=55.0,
            soc_je_speicher={str(alt_id): 40.0, str(neu_id): 70.0},
        ))


async def _sizing(db, anlage_id: int):
    return await get_speicher_sizing(
        anlage_id, von=None, bis=None, richtpreis_eur_je_kwh=None, db=db,
    )


async def test_ausgebautes_geraet_steht_nicht_mehr_in_der_aufschluesselung(db):
    anlage_id, alt_id, neu_id = await _seed(db)
    for i in range(3):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i),
             alt_id=alt_id, neu_id=neu_id)
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.anzahl_speicher == 1, "N-546 — die Zahl, an der der Text hängt"
    assert antwort.soc_nutzung is not None
    assert antwort.soc_nutzung.median_je_speicher == {str(neu_id): 70.0}, (
        "ungefiltert stünde hier auch das ausgebaute Gerät — zwei Zeilen unter "
        "der Überschrift „1 Speicher"
    )


async def test_abgewaehltes_geraet_ohne_datum_steht_auch_nicht_darin(db):
    anlage_id, alt_id, neu_id = await _seed(db, aktiv_alt=False, stillgelegt=None)
    for i in range(3):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i),
             alt_id=alt_id, neu_id=neu_id)
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.soc_nutzung is not None
    assert antwort.soc_nutzung.median_je_speicher == {str(neu_id): 70.0}


async def test_zwei_laufende_geraete_stehen_weiter_beide_darin(db):
    """Die Gegenrichtung — sonst wäre unbelegt, dass die Liste überhaupt noch füllt."""
    anlage_id, alt_id, neu_id = await _seed(db, stillgelegt=STILLGELEGT_ZUKUNFT)
    for i in range(3):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i),
             alt_id=alt_id, neu_id=neu_id)
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.anzahl_speicher == 2
    assert antwort.soc_nutzung is not None
    assert antwort.soc_nutzung.median_je_speicher == {
        str(alt_id): 40.0, str(neu_id): 70.0,
    }


async def test_der_anlagen_ladestand_bleibt_unberuehrt(db):
    """`soc_prozent` ist ein historischer Messwert der Anlage — er ändert sich nicht.

    Der Filter greift ausdrücklich **nur** an der Aufschlüsselung. Würde er auch
    die Perzentile treffen, wäre das ein stiller Eingriff in die Historie und
    in die Kalibrierung.
    """
    anlage_id, alt_id, neu_id = await _seed(db)
    for i in range(3):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i),
             alt_id=alt_id, neu_id=neu_id)
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.soc_nutzung is not None
    assert antwort.soc_nutzung.tage_mit_soc == 3
    assert antwort.soc_nutzung.soc_p5 == pytest.approx(55.0)
    assert antwort.soc_nutzung.soc_median == pytest.approx(55.0)
    assert antwort.soc_nutzung.tages_max_median == pytest.approx(55.0)
