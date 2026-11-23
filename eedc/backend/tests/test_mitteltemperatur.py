"""Die Vorrangkette der Außentemperatur (Konzept Wärme/Klima §8).

**Warum es diesen Dienst gibt:** Das Formularfeld
``Monatsdaten.durchschnittstemperatur`` ist seit dem IA-V4-Flip leer — sein
Auto-Fill lag in der gelöschten V3-Seite (**N-426**). Die Größe steckt trotzdem
in den eigenen Messreihen.

⭐ **Und die Tages-Näherung überlebt länger als die Stundenwerte:** Das
Löschfrist bis 4.3.1 traf ausschließlich ``TagesEnergieProfil``;
``TagesZusammenfassung`` mit Min/Max wurde nie beschnitten (seit Nachtrag G keine
Löschfrist mehr, ``services/energie_profil/scheduler_jobs.py``).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.models.monatsdaten import Monatsdaten
from backend.services.mitteltemperatur import (
    lade_heizgradtage_je_monat,
    lade_monatsmittel_temperatur,
    lade_tagesmittel_temperatur,
)


async def _anlage(db, name: str = "T") -> Anlage:
    a = Anlage(anlagenname=name, leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(a)
    await db.flush()
    return a


async def _stunden(db, anlage_id: int, tag: date, temps: list[float]):
    for h, t in enumerate(temps):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=tag, stunde=h, temperatur_c=t,
        ))


async def _tag(db, anlage_id: int, tag: date, tmin: float, tmax: float):
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=tag,
        temperatur_min_c=tmin, temperatur_max_c=tmax,
    ))


@pytest.mark.asyncio
async def test_stundenwerte_schlagen_die_min_max_naeherung(db):
    """Stufe 1 vor Stufe 2 — das echte Mittel ist genauer als (min+max)/2."""
    a = await _anlage(db)
    tag = date(2025, 1, 15)
    # Echtes Mittel 5,0 — die Näherung läge bei 7,5 und wäre schlechter.
    await _stunden(db, a.id, tag, [4.0, 4.0, 6.0, 6.0])
    await _tag(db, a.id, tag, 0.0, 15.0)
    await db.commit()
    je_tag = await lade_tagesmittel_temperatur(db, a.id)
    assert je_tag[tag] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_min_max_traegt_den_tag_ohne_stundenwerte(db):
    """Stufe 2 greift dort, wo die Stundenzeilen weg sind (älter als 2 Jahre)."""
    a = await _anlage(db)
    alt = date(2023, 1, 15)
    await _tag(db, a.id, alt, 0.0, 10.0)
    await db.commit()
    je_tag = await lade_tagesmittel_temperatur(db, a.id)
    assert je_tag[alt] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_monatsmittel_gewichtet_die_TAGE_gleich(db):
    """⚠ Gemittelt wird über Tagesmittel, nicht über alle Stunden des Monats.

    Sonst zöge ein Tag mit vielen erfassten Stunden das Monatsmittel zu sich —
    das Mittel kippte in Richtung der besser erfassten Zeit.
    """
    a = await _anlage(db)
    # Tag 1: acht Stunden à 10 °C. Tag 2: eine Stunde à 0 °C.
    await _stunden(db, a.id, date(2025, 3, 1), [10.0] * 8)
    await _stunden(db, a.id, date(2025, 3, 2), [0.0])
    await db.commit()
    je_monat = await lade_monatsmittel_temperatur(db, a.id)
    # Über die Tage: (10 + 0) / 2 = 5,0. Über alle Stunden wären es 8,9.
    assert je_monat[(2025, 3)] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_gepflegter_wert_fuellt_nur_luecken(db):
    """Stufe 3 zuletzt: die eigene Messreihe steht der Anlage näher als ein Archivwert."""
    a = await _anlage(db)
    await _stunden(db, a.id, date(2025, 4, 1), [12.0])
    await db.commit()
    je_monat = await lade_monatsmittel_temperatur(
        db, a.id,
        gepflegt_je_monat={(2025, 4): -99.0, (2025, 5): 17.5},
    )
    assert je_monat[(2025, 4)] == pytest.approx(12.0), "Messreihe schlägt Handeintrag"
    assert je_monat[(2025, 5)] == pytest.approx(17.5), "Handeintrag füllt die Lücke"


@pytest.mark.asyncio
async def test_monat_ohne_jede_spur_fehlt_statt_null_zu_sein(db):
    """Ein Monat ohne Temperaturspur ist kein Monat am Gefrierpunkt."""
    a = await _anlage(db)
    await db.commit()
    je_monat = await lade_monatsmittel_temperatur(db, a.id)
    assert (2025, 6) not in je_monat


# ═══ Heizgradtage — derselbe Eingang, eine andere Vorrangkette (K-2) ════════
#
# ⛔ **Die Kette ist hier KÜRZER als bei der Ø-Anzeige, und das ist der ganze
# Punkt.** Stufe 1+2 (Tagesmittel) ja, Stufe 3 (gepflegter Monats-Ø) nein:
# ``max(0; 15 − T)`` ist konvex, der Weg über den Monatsmittelwert unterschätzt
# die Summe (an der Demo-Anlage im Mai 2026 gemessene −26,6 %). Die Formel
# selbst steht in ``test_heizgradtage.py``; hier steht, was aus der **DB** in
# sie hineinkommt.


@pytest.mark.asyncio
async def test_b9_gepflegter_monatswert_ist_KEIN_heizgradtag_eingang(db):
    """⭐ **K-2 an der Datenbank.** Eine Anlage, die nur den von Hand gepflegten
    Monats-Ø trägt, bekommt **keine** Heizgradtage — sondern nichts, und daneben
    den Grund. Der Ø selbst bleibt unberührt: Für die **Anzeige** ist er Stufe 3
    und füllt die Lücke weiterhin.
    """
    a = await _anlage(db, "nur gepflegt")
    db.add(Monatsdaten(
        anlage_id=a.id, jahr=2025, monat=5, durchschnittstemperatur=14.3,
    ))
    await db.commit()

    hgt = await lade_heizgradtage_je_monat(db, a.id)
    assert hgt == {}, "Stufe 3 darf nicht in die Gradtagsrechnung sickern"

    # Gegenprobe: für die ANZEIGE trägt derselbe Wert weiterhin.
    je_monat = await lade_monatsmittel_temperatur(
        db, a.id, gepflegt_je_monat={(2025, 5): 14.3},
    )
    assert je_monat[(2025, 5)] == pytest.approx(14.3)


@pytest.mark.asyncio
async def test_b10_min_max_naeherung_traegt_die_heizgradtage(db):
    """Stufe 2 greift auch hier: min 0 / max 10 ⇒ Tagesmittel 5,0 ⇒ 10,0 Kd."""
    a = await _anlage(db, "nur min/max")
    await _tag(db, a.id, date(2023, 1, 15), 0.0, 10.0)
    await db.commit()
    hgt = await lade_heizgradtage_je_monat(db, a.id)
    assert hgt[(2023, 1)].kd == pytest.approx(10.0)
    assert hgt[(2023, 1)].tage_mit_temperatur == 1
    assert hgt[(2023, 1)].tage_im_monat == 31


@pytest.mark.asyncio
async def test_b11_stundenmittel_schlaegt_min_max_auch_bei_den_heizgradtagen(db):
    """Stufe 1 vor Stufe 2 — und der Unterschied ist hier **sichtbar**:
    echtes Mittel 5,0 ⇒ 10,0 Kd, die Näherung (0/15) läge bei 7,5 ⇒ 7,5 Kd."""
    a = await _anlage(db, "beides")
    tag = date(2025, 1, 15)
    await _stunden(db, a.id, tag, [4.0, 4.0, 6.0, 6.0])
    await _tag(db, a.id, tag, 0.0, 15.0)
    await db.commit()
    hgt = await lade_heizgradtage_je_monat(db, a.id)
    assert hgt[(2025, 1)].kd == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_heizgradtage_grenzen_wirken(db):
    """``von``/``bis`` schneiden dieselbe Reihe wie bei der Ø-Anzeige."""
    a = await _anlage(db, "gefenstert")
    await _stunden(db, a.id, date(2025, 1, 10), [5.0])
    await _stunden(db, a.id, date(2025, 3, 10), [5.0])
    await db.commit()
    hgt = await lade_heizgradtage_je_monat(
        db, a.id, von=date(2025, 2, 1), bis=date(2025, 12, 31),
    )
    assert set(hgt) == {(2025, 3)}
