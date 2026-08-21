"""#263/T2: die Aufteilung Heizen/Kühlen gibt es auch für einen einzelnen Tag.

**Gemeldet von OB73-gif** (2026-08-20): *„Die Übersicht am Ende (wie beim
Monat), wieviel Energie in heizen/kühlen/nicht aufgeteilt floss, fehlt hier
auch."* — die Aufteilung existierte nur je Monat.

**Warum das eine kleine Ergänzung war und kein zweiter Rechenweg:** Die Faltung
ist ohnehin **tagesweise** (`falte_modus_split_tag`; die Normierung braucht die
Tages-Zählersumme), die Monatssicht summiert sie nur hinterher auf.
`lade_modus_split_tag` bleibt eine Ebene früher stehen und teilt sich mit ihr
den **Ladepfad** (`_lade_tages_eingaenge`) — genau deshalb wurde der extrahiert:
*eine Regel, die an zwei Stellen nachgebaut wird, driftet* (Modul-Kopf).

Konzept: `docs/KONZEPT-263-INNENGERAETE.md` §8.
"""

from __future__ import annotations

from datetime import date

from backend.core.betriebsmodus import HEIZEN, KUEHLEN
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)

DATUM = date(2025, 6, 15)


async def _anlage_mit_klima(db, *, stunden_modi, kwh_je_stunde=-0.5, anschaffung=None):
    """Anlage + Klimaanlage + eine Tageszeile je Stunde."""
    anlage = Anlage(anlagenname="T2", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Splitklima",
        anschaffungsdatum=anschaffung or date(2025, 1, 1),
        anschaffungskosten_gesamt=3000.0, parameter={"wp_art": "luft_luft"},
    )
    db.add(inv)
    await db.flush()

    for h in range(24):
        modus = stunden_modi(h)
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=DATUM, stunde=h,
            komponenten={f"waermepumpe_{inv.id}": kwh_je_stunde},
            betriebsmodus_je_wp={str(inv.id): modus} if modus else None,
        ))
    await db.commit()
    return anlage, inv


async def test_t2_der_tag_hat_seine_eigene_aufteilung(db):
    """12 h Kühlen, 12 h Heizen ⇒ beide Teilmengen tragen die Hälfte."""
    from backend.services.energie_profil import lade_modus_split_tag

    anlage, inv = await _anlage_mit_klima(
        db, stunden_modi=lambda h: KUEHLEN if h < 12 else HEIZEN,
    )
    splits = await lade_modus_split_tag(db, anlage.id, DATUM)

    split = splits[str(inv.id)]
    assert split.teilmenge_kwh(KUEHLEN) == 6.0
    assert split.teilmenge_kwh(HEIZEN) == 6.0
    assert split.abdeckung_h == 24


async def test_t2_ohne_modus_signal_gibt_es_nichts_statt_null(db):
    """P4: keine Aussage ist keine 0.

    **Der Sprengsatz:** Ein leeres Dict statt „nicht vorhanden" ließe den Block
    mit drei Nullen erscheinen — die F-42-Klasse, gegen die S4 gebaut ist.
    """
    from backend.services.energie_profil import lade_modus_split_tag

    anlage, _ = await _anlage_mit_klima(db, stunden_modi=lambda h: None)
    assert await lade_modus_split_tag(db, anlage.id, DATUM) == {}


async def test_t2_ein_anderer_tag_bleibt_unberuehrt(db):
    """Die Tagesgrenze ist die Aussage — sonst wäre es wieder ein Monatswert."""
    from backend.services.energie_profil import lade_modus_split_tag

    anlage, _ = await _anlage_mit_klima(db, stunden_modi=lambda h: KUEHLEN)
    assert await lade_modus_split_tag(db, anlage.id, DATUM) != {}
    assert await lade_modus_split_tag(db, anlage.id, date(2025, 6, 16)) == {}


async def test_t2_der_endpunkt_liefert_die_drei_groessen_plus_abdeckung(db):
    """Der ganze Weg bis in die Antwort — nicht nur der Lader.

    Ein Prüfer auf `lade_modus_split_tag` allein wäre grün geblieben, ohne dass
    die Fläche etwas zeigt: genau der Fehler, an dem der `hvac_action`-Wächter
    scheiterte (Konzept §6).
    """
    from backend.api.routes.energie_profil.views import get_tag_detail

    anlage, _ = await _anlage_mit_klima(
        db, stunden_modi=lambda h: KUEHLEN if h < 18 else None,
    )
    antwort = await get_tag_detail(anlage_id=anlage.id, datum=DATUM, db=db)

    assert antwort.wp_modus_strom_kuehlen_kwh == 9.0     # 18 h × 0,5 kWh
    assert antwort.wp_modus_strom_heizen_kwh == 0.0
    assert antwort.wp_modus_abdeckung_h == 18
    # Der Rest ist die Differenz zum Bezug und kommt aus dem Backend — ohne ihn
    # müsste der Client subtrahieren und käme bei anderem Bezug auf eine andere
    # Zahl als die Monatssicht.
    assert antwort.wp_modus_nicht_aufgeteilt_kwh is not None


async def test_t2_ohne_signal_bleiben_die_felder_None(db):
    """Kein Modus ⇒ vier `None`, damit der Block gar nicht erst erscheint."""
    from backend.api.routes.energie_profil.views import get_tag_detail

    anlage, _ = await _anlage_mit_klima(db, stunden_modi=lambda h: None)
    antwort = await get_tag_detail(anlage_id=anlage.id, datum=DATUM, db=db)

    assert antwort.wp_modus_strom_heizen_kwh is None
    assert antwort.wp_modus_strom_kuehlen_kwh is None
    assert antwort.wp_modus_nicht_aufgeteilt_kwh is None
    assert antwort.wp_modus_abdeckung_h is None


async def test_t2_ein_am_tag_noch_nicht_angeschafftes_geraet_zaehlt_nicht(db):
    """Dieselbe Datums-Achse wie überall — `ist_aktiv_an` entscheidet.

    Ohne diese Prüfung trüge ein Tag vor der Anschaffung eine Aufteilung für
    ein Gerät, das es an diesem Tag noch nicht gab.
    """
    from backend.api.routes.energie_profil.views import get_tag_detail

    anlage, _ = await _anlage_mit_klima(
        db, stunden_modi=lambda h: KUEHLEN, anschaffung=date(2025, 12, 1),
    )
    antwort = await get_tag_detail(anlage_id=anlage.id, datum=DATUM, db=db)
    assert antwort.wp_modus_abdeckung_h is None


async def test_t2_monat_und_tag_teilen_den_ladepfad(db):
    """Σ der Tage eines Monats == der Monatswert — sonst wären es zwei Wege.

    Das ist der Grund, warum `_lade_tages_eingaenge` extrahiert wurde statt die
    Auswahlregeln ein zweites Mal zu schreiben.
    """
    from backend.services.energie_profil import (
        lade_modus_split_monat,
        lade_modus_split_tag,
    )

    anlage, inv = await _anlage_mit_klima(db, stunden_modi=lambda h: KUEHLEN)

    tag = (await lade_modus_split_tag(db, anlage.id, DATUM))[str(inv.id)]
    monat = (await lade_modus_split_monat(db, anlage.id, 2025, 6))[str(inv.id)]

    # Nur dieser eine Tag trägt Daten ⇒ die Werte müssen identisch sein.
    assert tag.teilmenge_kwh(KUEHLEN) == monat.teilmenge_kwh(KUEHLEN)
    assert tag.abdeckung_h == monat.abdeckung_h
