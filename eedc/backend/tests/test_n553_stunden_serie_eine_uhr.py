"""N-553: die Stundenliste des Tagesdetails trägt EINE Uhr — und die
Tagesende-Kachel ihre eigene Größe.

**Der Befund** (Nebenfund des N-387-Baus, 23.09.2026): Die Route
``GET /api/energie-profil/{id}/stunden`` reichte jede ``TagesEnergieProfil``-Zeile
durch, wie sie in der Datenbank steht — und diese Zeile trägt **zwei**
Konventionen: die ``*_kw``-Spalten liegen **backward** (Zeile ``s`` = Energie aus
``[s-1, s)``), ``soc_prozent`` liegt **forward** (Mittel über ``[s, s+1)``).
Wer in der Stundentabelle die Spalte „SoC" einschaltet, las den Ladestand der
**Nachbarstunde** neben dem Batteriefluss derselben Zeile.

⚠ **Was NICHT betroffen war, und warum das hier steht:** Der Stundenverlauf-Chart
(``TagVerlaufChart``) zeichnet **keine** SoC-Kurve — der Fund-Eintrag sprach von
einer „versetzten SoC-Kurve", die es nicht gibt (am Code gemessen 23.09.). Die
Anzeige, die es wirklich trifft, ist die abgewählte Tabellenspalte. Die
Prognose-Sicht (``EnergieprofilPrognose``) zeigt den Ladestand der **Simulation**
und hat mit der Zeile nichts zu tun.

⭐ **Warum eine zweite Größe dazukommt, statt eine zu verschieben.** Die Kachel
„Ladestand · Stand am Tagesende" fragt *„wie voll war der Speicher zuletzt"* —
eine andere Frage als *„welcher Stand gehört zu dieser Stunde"*. Die Paarung
schiebt den jüngsten Messwert aus dem Tagesraster (sein Intervall ``[23, 24)``
liegt backward schon im Folgetag); am **laufenden** Tag wäre die Kachel damit
eine Stunde älter geworden. Sie bekommt deshalb ``soc_zuletzt_prozent``.
"""

from __future__ import annotations

from datetime import date, datetime

from backend.models import Anlage  # noqa: F401  (Base.metadata)
from backend.models.tages_energie_profil import TagesEnergieProfil

# Fester Tag NACH der Bestandsgrenze (`SLOT_PAARUNG_VORZEILE_AB`, 2026-06-04);
# keine Prozessuhr — der Wächter `test_konformitaet_echte_uhr_in_tests.py` gilt.
TAG = date(2026, 8, 10)
VORTAG = date(2026, 8, 9)
NEU_GESCHRIEBEN = datetime(2026, 8, 11, 3, 0, 0)
ALT_GESCHRIEBEN = datetime(2026, 5, 1, 3, 0, 0)


async def _anlage(db) -> Anlage:
    anlage = Anlage(anlagenname="N553", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    return anlage


def _zeile(anlage_id: int, tag: date, stunde: int, soc, *, created_at=NEU_GESCHRIEBEN):
    return TagesEnergieProfil(
        anlage_id=anlage_id, datum=tag, stunde=stunde,
        soc_prozent=soc, batterie_kw=1.0, created_at=created_at,
    )


async def _route(db, anlage, tag: date = TAG):
    from backend.api.routes.energie_profil.views import get_stundenwerte

    return await get_stundenwerte(anlage_id=anlage.id, datum=tag, db=db)


async def test_die_zeile_traegt_den_ladestand_ihrer_eigenen_stunde(db):
    """Zeile ``s`` bekommt den Ladestand aus Zeile ``s-1`` — die Backward-Stunde
    der Zeile ist ``[s-1, s)``, und genau dieses Intervall beschreibt das
    Stundenmittel der Vorzeile."""
    anlage = await _anlage(db)
    for h in range(24):
        db.add(_zeile(anlage.id, TAG, h, float(h)))       # SoC = Stundennummer
    db.add(_zeile(anlage.id, VORTAG, 23, 99.0))
    await db.flush()

    antwort = await _route(db, anlage)
    je_stunde = {s.stunde: s.soc_prozent for s in antwort.stunden}

    assert je_stunde[7] == 6.0, "Slot 7 = [06,07) ⇒ Mittel der Zeile 6"
    assert je_stunde[23] == 22.0
    assert je_stunde[1] == 0.0


async def test_slot_null_nimmt_die_23_des_vortags(db):
    """``[Vortag 23:00, 00:00)`` **ist** Slot 0 dieses Tages — deshalb lädt die
    Route den Vortag mit."""
    anlage = await _anlage(db)
    db.add(_zeile(anlage.id, VORTAG, 23, 41.0))
    for h in range(24):
        db.add(_zeile(anlage.id, TAG, h, float(h)))
    await db.flush()

    antwort = await _route(db, anlage)
    assert antwort.stunden[0].stunde == 0
    assert antwort.stunden[0].soc_prozent == 41.0


async def test_ohne_vortag_bleibt_slot_null_leer_statt_geraten(db):
    """Keine stille Nachbar-Übernahme: fehlt die Vorzeile, ist der Wert ``None``
    — ein Ladestand aus der übernächsten Stunde wäre keine Messung dieser."""
    anlage = await _anlage(db)
    for h in range(24):
        db.add(_zeile(anlage.id, TAG, h, float(h)))
    await db.flush()

    antwort = await _route(db, anlage)
    assert antwort.stunden[0].soc_prozent is None
    assert antwort.stunden[1].soc_prozent == 0.0


async def test_eine_luecke_im_tag_vererbt_nichts(db):
    """Fehlt eine Stunde, bekommt die Folgestunde ``None`` — nicht den Wert von
    zwei Stunden davor."""
    anlage = await _anlage(db)
    for h in (0, 1, 2, 4, 5):
        db.add(_zeile(anlage.id, TAG, h, float(h) * 10))
    db.add(_zeile(anlage.id, VORTAG, 23, 5.0))
    await db.flush()

    antwort = await _route(db, anlage)
    je_stunde = {s.stunde: s.soc_prozent for s in antwort.stunden}
    assert je_stunde[4] is None, "Stunde 3 fehlt ⇒ kein Wert für Slot 4"
    assert je_stunde[5] == 40.0


async def test_der_tagesende_stand_bleibt_der_juengste_messwert(db):
    """``soc_zuletzt_prozent`` ist der **rohe** Ladestand der letzten gemessenen
    Zeile — nicht der gepaarte Wert der letzten Listenzeile.

    Der laufende Tag ist der Fall, der das entscheidet: HA hat bis Stunde 14
    verdichtet, die Kachel soll 14 zeigen und nicht 13."""
    anlage = await _anlage(db)
    for h in range(15):                       # bis einschließlich 14
        db.add(_zeile(anlage.id, TAG, h, float(h)))
    db.add(_zeile(anlage.id, VORTAG, 23, 99.0))
    await db.flush()

    antwort = await _route(db, anlage)
    assert antwort.soc_zuletzt_prozent == 14.0
    assert antwort.stunden[-1].soc_prozent == 13.0, "die Liste bleibt gepaart"


async def test_ohne_jeden_ladestand_gibt_es_keinen_tagesende_stand(db):
    """``None`` heißt „an diesem Tag wurde kein Ladestand gemessen" — nicht 0 %."""
    anlage = await _anlage(db)
    for h in range(24):
        db.add(_zeile(anlage.id, TAG, h, None))
    await db.flush()

    antwort = await _route(db, anlage)
    assert antwort.soc_zuletzt_prozent is None


async def test_altbestand_behaelt_die_zeilen_zuordnung(db):
    """Zeilen, die **vor** dem 04.06.2026 aggregiert wurden, tragen ihre
    ``*_kw`` selbst forward (`slot_konvention`) — dort ist die Zeilen-Zuordnung
    die richtige, und die Route darf sie nicht verschieben."""
    anlage = await _anlage(db)
    for h in range(24):
        db.add(_zeile(anlage.id, TAG, h, float(h), created_at=ALT_GESCHRIEBEN))
    db.add(_zeile(anlage.id, VORTAG, 23, 99.0, created_at=ALT_GESCHRIEBEN))
    await db.flush()

    antwort = await _route(db, anlage)
    je_stunde = {s.stunde: s.soc_prozent for s in antwort.stunden}
    assert je_stunde[7] == 7.0, "Altbestand: die Zeile trägt ihren eigenen Wert"
    assert je_stunde[0] == 0.0


async def test_der_vortag_steht_nicht_in_der_antwort(db):
    """Die Route liefert weiter genau die Stunden **dieses** Tages; der Vortag
    ist nur Eingang der Paarung."""
    anlage = await _anlage(db)
    for h in range(24):
        db.add(_zeile(anlage.id, VORTAG, h, 50.0))
        db.add(_zeile(anlage.id, TAG, h, float(h)))
    await db.flush()

    antwort = await _route(db, anlage)
    assert len(antwort.stunden) == 24
    assert [s.stunde for s in antwort.stunden] == list(range(24))
