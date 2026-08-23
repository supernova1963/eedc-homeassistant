"""N-121: der Verlauf zeichnet auch Monate, die nur als Tageswerte existieren.

**Der Befund.** *Cockpit → Jahr* nannte oben „Jan–Aug · 9.653 kWh", der Verlauf
darunter zeichnete sechs Balken. Das ist genau das Bild, das **N-68** beseitigen
sollte — an einer echten Anlage war es weiterhin da. Ursache war nicht der
Client und nicht die Route, sondern die **Grundgesamtheit** der Monats-Fakten:
sie kennt einen Monat nur mit DB-Spur (``Monatsdaten`` oder
``InvestitionMonatsdaten``). N-68 hob lediglich die *Zählerzeilen*-Bedingung auf.

**Warum das kein Randfall ist.** Einen automatischen Monatsabschluss gibt es
nicht — ``scheduler.py::monthly_snapshot_job`` setzt nur einen Log-Zeitstempel.
Der **laufende** Monat hat deshalb nie eine ``Monatsdaten``-Zeile und fehlte im
Jahres-Verlauf immer; der Vormonat so lange, bis jemand den Abschluss macht.

**Was diese Datei festhält**: dass der Default sich **nicht** bewegt (jede Sicht
außer der Zeitreihe sieht unverändert nur DB-Daten), dass das Flag den Monat
aufnimmt, und dass vorhandene DB-Werte **gewinnen** — Tageswerte füllen Lücken,
sie überschreiben nichts (Präzedenz P7).

Uhr-Unabhängigkeit: alle Daten liegen fest in 2026, kein ``date.today()``
(Lehre 2026-08-03, ``time.monotonic``).
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.monats_fakten import (
    TAGESWERT_PV,
    TAGESWERT_ZAEHLER,
    lade_monats_fakten,
)
from backend.tests import factories


async def _anlage(db) -> Anlage:
    return await factories.anlage(db, anlagenname="N-121", standort_land="DE")


async def _pv_modul(db, anlage_id: int) -> Investition:
    inv = Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Ost",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0)
    db.add(inv)
    await db.flush()
    return inv


async def _tag(db, anlage_id: int, tag: date, *, pv: float,
               einspeisung: float = 0.0, netzbezug: float = 0.0) -> None:
    """Eine Tages-Spur: Komponenten-kWh (PV) + eine Stundenzeile (Zähler).

    Bewusst EINE Stunde statt 24 — die Faltung ist eine Σ, die Stundenzahl ist
    für die geprüfte Aussage ohne Belang und hielte den Test nur langsam.
    """
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=tag,
        komponenten_kwh={"pv_1": pv},
    ))
    db.add(TagesEnergieProfil(
        anlage_id=anlage_id, datum=tag, stunde=12,
        pv_kw=pv, verbrauch_kw=0.0,
        einspeisung_kw=einspeisung, netzbezug_kw=netzbezug,
    ))


async def _mai_in_db_juli_nur_tage(db) -> Anlage:
    """Mai vollständig gepflegt, Juli existiert **nur** als Tagesebene."""
    anlage = await _anlage(db)
    modul = await _pv_modul(db, anlage.id)

    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    db.add(InvestitionMonatsdaten(investition_id=modul.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 900.0}))

    # Juli: weder Monatsabschluss noch IMD — nur zwei Tage Snapshot-Spur.
    await _tag(db, anlage.id, date(2026, 7, 1), pv=30.0, einspeisung=20.0, netzbezug=1.0)
    await _tag(db, anlage.id, date(2026, 7, 2), pv=25.0, einspeisung=15.0, netzbezug=2.0)
    await db.commit()
    return anlage


# ─── Der Default bewegt sich nicht ──────────────────────────────────────────

async def test_default_kennt_den_nur_tageswert_monat_nicht(db):
    """REGRESSION. Ohne das Flag bleibt die Grundgesamtheit exakt wie bisher.

    Das ist die Bedingung, unter der dieser Umbau überhaupt vertretbar ist: die
    Schicht speist *Auswertungen → Tabelle*, Monatsbericht, HA-Export und den
    Community-Payload. Dort wäre so ein Monat eine Zeile ohne Datensatz, die
    man weder bearbeiten noch löschen kann.
    """
    anlage = await _mai_in_db_juli_nur_tage(db)

    fakten = await lade_monats_fakten(db, anlage.id)

    assert [f.schluessel for f in fakten] == [(2026, 5)]


async def test_default_auch_mit_ohne_zaehlerzeile_nicht(db):
    """REGRESSION. Auch `inkl_ohne_zaehlerzeile` allein holt ihn **nicht** —
    genau daran ist N-68 an der echten Anlage vorbeigelaufen. Das Flag hebt die
    Zählerzeilen-Bedingung auf, nicht die Grundgesamtheit.
    """
    anlage = await _mai_in_db_juli_nur_tage(db)

    rows = await list_monatsdaten_aggregiert(
        anlage_id=anlage.id, jahr=2026, inkl_ohne_zaehlerzeile=True, db=db,
    )

    assert [r.monat for r in rows] == [5]


# ─── Mit Flag: der Monat ist da, und er ist als solcher erkennbar ───────────

async def test_flag_nimmt_den_nur_tageswert_monat_auf(db):
    """**N-121.** Der Juli erscheint, mit den Mengen seiner Tagesebene."""
    anlage = await _mai_in_db_juli_nur_tage(db)

    fakten = await lade_monats_fakten(db, anlage.id, inkl_nur_tageswerte=True)

    assert [f.schluessel for f in fakten] == [(2026, 5), (2026, 7)]
    juli = fakten[1]
    assert juli.erzeugung.pv_kwh == 55.0          # 30 + 25 aus komponenten_kwh
    assert juli.zaehler.einspeisung_kwh == 35.0   # 20 + 15 aus den Stundenzeilen
    assert juli.zaehler.netzbezug_kwh == 3.0


async def test_tageswert_monat_nennt_seine_herkunft(db):
    """Was aus Tageswerten stammt, sagt es (P4/`KONZEPT-UNVOLLSTAENDIGE-WERTE`).

    Ohne diese Kennzeichnung könnte eine Sicht die Zeile nicht von einem
    gepflegten Monat unterscheiden — und die Route könnte die „hat etwas
    beigetragen?"-Weichen nicht stellen, ohne aus einer 0 zu raten.
    """
    anlage = await _mai_in_db_juli_nur_tage(db)

    fakten = await lade_monats_fakten(db, anlage.id, inkl_nur_tageswerte=True)
    mai, juli = fakten

    assert mai.meta.tageswert_gruppen == frozenset()
    assert TAGESWERT_PV in juli.meta.tageswert_gruppen
    assert TAGESWERT_ZAEHLER in juli.meta.tageswert_gruppen
    assert juli.meta.hat_zaehlerzeile is False


async def test_route_liefert_die_menge_und_die_markierung(db):
    """Die Route reicht beides durch — die Zahl **und** ihre Herkunft.

    ``pv_erzeugung_kwh`` darf hier nicht `None` sein: die „hat eine Komponente
    beigetragen?"-Weiche der Route kennt sonst nur IMD-Zeilen, und der Verlauf
    zeichnete wieder nichts.
    """
    anlage = await _mai_in_db_juli_nur_tage(db)

    rows = await list_monatsdaten_aggregiert(
        anlage_id=anlage.id, jahr=2026,
        inkl_ohne_zaehlerzeile=True, inkl_nur_tageswerte=True, db=db,
    )

    assert [r.monat for r in rows] == [7, 5]      # absteigend wie immer
    juli = rows[0]
    assert juli.id is None                        # es gibt keinen Datensatz
    assert juli.pv_erzeugung_kwh == 55.0
    assert juli.einspeisung_kwh == 35.0
    assert juli.aus_tageswerten == ["pv", "zaehler"]
    assert rows[1].aus_tageswerten is None        # der gepflegte Mai: unberührt


# ─── Präzedenz: die DB gewinnt ─────────────────────────────────────────────

async def test_gepflegter_monat_bleibt_unberuehrt(db):
    """**Die zentrale Invariante.** Tageswerte füllen Lücken, sie überschreiben
    nichts — dieselbe Präzedenz wie bei P7 (Einzelwerte vor Aggregat).

    Der Mai hat sowohl eine gepflegte PV-Zeile (900 kWh) als auch eine
    Tagesebene, die etwas ganz anderes sagt (5 kWh). Gewinnt die Tagesebene,
    verschiebt dieser Umbau still gepflegte Zahlen — der schlimmstmögliche
    Ausgang, weil ihn niemand bemerkt.
    """
    anlage = await _mai_in_db_juli_nur_tage(db)
    await _tag(db, anlage.id, date(2026, 5, 1), pv=5.0, einspeisung=4.0, netzbezug=3.0)
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id, inkl_nur_tageswerte=True)
    mai = next(f for f in fakten if f.monat == 5)

    assert mai.erzeugung.pv_kwh == 900.0          # die gepflegte Zeile, nicht 5
    assert mai.zaehler.einspeisung_kwh == 300.0   # der Monatsabschluss, nicht 4
    assert mai.zaehler.netzbezug_kwh == 200.0
    assert mai.meta.tageswert_gruppen == frozenset()


async def test_teilspur_bekommt_nur_die_fehlende_gruppe(db):
    """Feldgruppen-weise, nicht monatsweise.

    Ein Monat, dessen einzige DB-Spur eine Wärmepumpen-Zeile ist, war in der
    Grundgesamtheit schon immer enthalten — seine PV stand aber auf 0. Genau so
    entsteht die Klasse „still zu niedrig", gegen die P4 geschrieben wurde.
    """
    anlage = await _anlage(db)
    await _pv_modul(db, anlage.id)
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
                     anschaffungsdatum=date(2024, 1, 1))
    db.add(wp)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2026, monat=7,
                                  verbrauch_daten={"stromverbrauch_kwh": 40.0}))
    await _tag(db, anlage.id, date(2026, 7, 1), pv=30.0, einspeisung=20.0)
    await db.commit()

    ohne = await lade_monats_fakten(db, anlage.id)
    mit = await lade_monats_fakten(db, anlage.id, inkl_nur_tageswerte=True)

    # Der Monat war schon vorher da — die WP-Zeile hat ihn aufgenommen.
    assert [f.schluessel for f in ohne] == [(2026, 7)]
    assert ohne[0].erzeugung.pv_kwh == 0.0        # ... und log die PV bei 0
    assert ohne[0].wp.strom_kwh == 40.0

    assert mit[0].erzeugung.pv_kwh == 30.0        # jetzt belegt
    assert mit[0].wp.strom_kwh == 40.0            # die DB-Größe unverändert
    assert TAGESWERT_PV in mit[0].meta.tageswert_gruppen


async def test_ohne_tagesebene_aendert_das_flag_nichts(db):
    """Wer keine Datenquellen zugeordnet hat, hat keine Tageszeilen — dort ist
    das Flag wirkungslos statt schädlich. (Er sieht dann auch in der Kachel
    keine Zahl, es gibt also keine Diskrepanz zu heilen.)
    """
    anlage = await _anlage(db)
    modul = await _pv_modul(db, anlage.id)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    db.add(InvestitionMonatsdaten(investition_id=modul.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 900.0}))
    await db.commit()

    ohne = await lade_monats_fakten(db, anlage.id)
    mit = await lade_monats_fakten(db, anlage.id, inkl_nur_tageswerte=True)

    assert [f.schluessel for f in ohne] == [f.schluessel for f in mit] == [(2026, 5)]
    assert mit[0].erzeugung.pv_kwh == ohne[0].erzeugung.pv_kwh == 900.0


async def test_fenster_gilt_auch_fuer_die_tagesebene(db):
    """Das `von`/`bis`-Fenster darf die neue Quelle nicht umgehen — sonst zöge
    eine Jahres-Abfrage die Tagesebene aller Jahre mit.
    """
    anlage = await _mai_in_db_juli_nur_tage(db)
    await _tag(db, anlage.id, date(2025, 7, 1), pv=99.0)
    await db.commit()

    fakten = await lade_monats_fakten(
        db, anlage.id, von=(2026, 1), bis=(2026, 12), inkl_nur_tageswerte=True,
    )

    assert [f.schluessel for f in fakten] == [(2026, 5), (2026, 7)]
