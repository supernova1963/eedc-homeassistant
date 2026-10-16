"""N-444 — Speicher- und E-Mob-Tagesdetail lesen im Fenster ihres Bezugs.

⚠ **STATUS: FIXTURE AUS DER VORLAGE WK-05 — NICHT GEFAHREN.**
Ziel-Ablage im BAU: ``eedc/backend/tests/test_n444_tagesdetail_ein_fenster.py``.
Braucht Lauf: ``cd eedc && source backend/venv/bin/activate &&
python -m pytest backend/tests/test_n444_tagesdetail_ein_fenster.py -q``.
Die Klassen ``TestNachtladungVorMitternacht``/``TestNachtladungNachDreiundzwanzig``
sind **vor** dem Bau rot (das ist der Zweck); ``TestOhneRandstunde`` ist vor und
nach dem Bau grün und ist die Gegenprobe.

**Der Fund** (12.09.2026, Verdacht V-4 des Wärme/Klima-Konzepts §9 D, am Code
gemessen): ``TAGESDETAIL_AUSGABE`` liefert ``speicher_ladung_netz_kwh`` und
``emob_ladung_pv_kwh``/``_netz_kwh`` über ``BoundaryRange.for_day_total``, also
[00:00, 24:00). Ihr **Bezug** in *Cockpit → Tag* kommt aus den
``TagesEnergieProfil``-Stundenzeilen:

* ``speicher_ladung_kwh`` = ``Σ max(0, −batterie_kw)``
  (``core/berechnungen/tagesbilanz.py``, über ``services/energie_profil/tage_werte.py``),
* ``emob_ladung_kwh`` = ``Σ`` der Wallbox-/E-Auto-Serien aus ``komponenten``
  (``v4/TagKomponenten.tsx::baueTagAlsMonat``).

Beide Stundenreihen liegen seit **N-382** im Rückwärtsraster
(``core/berechnungen/slot_konvention.py``): Slot ``h`` = [h−1, h), Σ der 24
Slots = [Vortag 23:00, Heute 23:00). Der Versatz ist damit **unbedingt** — bei
der Wärmepumpe (N-434/N-435) hing er noch am Deployment (LTS-Provenance), hier
nicht.

**Was er anrichtet** — zwei echte Quotienten in
``frontend/src/v4/KomponentenSektionen.tsx``:

* ``:744-745`` PV-Anteil E-Mobilität = ``emob_ladung_pv_kwh ÷ emob_ladung_kwh``,
* ``:200-215`` Speicher-Wirkungsverluste in € = Verlust × (PV-Anteil ×
  Einspeisepreis + Netz-Anteil × Bezugspreis) mit
  ``anteil_netz = Math.min(1, speicher_ladung_netz_kwh ÷ speicher_ladung_kwh)``
  — die Kappung verbirgt den Versatz, statt ihn zu melden.

Dazu die Detailzeilen ``:408`` („davon aus dem Netz (Arbitrage)") und ``:789``
(„Ladung · Netz-Anteil"): ein **Teil**, der aus einem anderen Fenster stammt als
sein Ganzes.

Schwesterdateien: ``test_n434_tagesfenster_betriebsart.py`` und
``test_n435_tages_jaz_ein_fenster.py`` (dieselbe Klasse an der Wärmepumpe,
dort über ``tageszeile_rueckwaerts``/``BoundaryRange.for_day_backward`` gelöst),
``test_slot_konvention_leistungspfad.py`` (das Rückwärtsraster der Stundenzeile).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows
from backend.services.snapshot.aggregator import get_tagesdetail_kwh

DATUM = date(2026, 1, 15)

#: Nachtladung, die über die Tagesgrenze fällt — der Fall des Funds.
NACHT_SPEICHER_NETZ = 6.0
NACHT_WALLBOX_NETZ = 8.0
#: Tagesgeschäft, das in BEIDEN Fenstern liegt ([00:00, 23:00)).
TAG_SPEICHER_PV = 4.0        # 4 × 1,0 kWh in den Slots 10–13
TAG_SPEICHER_ENTLADUNG = 3.0  # 3 × 1,0 kWh in den Slots 20–22
TAG_WALLBOX_PV = 9.0         # 4 × 2,25 kWh in den Slots 10–13


async def _anlage(db, *, nacht: str):
    """Speicher + Wallbox mit Zählern; die Nachtladung liegt je nach `nacht`
    vor oder nach Mitternacht.

    ``nacht="vortag"`` — die Ladung fällt in [Vortag 23:00, 00:00). Sie steht
    damit in **Slot 0** der Tageszeile und im Rückwärtsfenster, aber **nicht**
    in [00:00, 24:00).

    ``nacht="eigene"`` — die Ladung fällt in [Heute 23:00, 24:00). Sie steht in
    [00:00, 24:00), aber **nicht** in der Tageszeile: dieser Bucket gehört nach
    ``slot_konvention.leistungspfad_slot`` in Slot 0 des **Folgetags**.

    ``nacht="keine"`` — Gegenprobe: keine Randstunde, beide Fenster gleich.
    """
    assert nacht in ("vortag", "eigene", "keine")
    anlage = Anlage(anlagenname="N444", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Hausspeicher",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=9000.0,
        leistung_kwp=10.0,
    )
    wallbox = Investition(
        anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1200.0,
    )
    db.add_all([speicher, wallbox])
    await db.flush()

    t0 = datetime.combine(DATUM, datetime.min.time())
    zeiten = [t0 - timedelta(hours=1), t0, t0 + timedelta(hours=23),
              t0 + timedelta(hours=24)]

    def reihe(basis: float, nacht_kwh: float, tag_kwh: float) -> list[float]:
        """Vier Randstände: [Vortag 23:00, 00:00, Heute 23:00, Folgetag 00:00]."""
        vor = nacht_kwh if nacht == "vortag" else 0.0
        eigen = nacht_kwh if nacht == "eigene" else 0.0
        s = [basis]
        s.append(s[-1] + vor)          # [Vortag 23:00, 00:00)
        s.append(s[-1] + tag_kwh)      # [00:00, 23:00)
        s.append(s[-1] + eigen)        # [23:00, 24:00)
        return s

    felder_speicher = {
        "ladung_netz_kwh": reihe(100.0, NACHT_SPEICHER_NETZ, 0.0),
    }
    felder_wallbox = {
        "ladung_pv_kwh": reihe(200.0, 0.0, TAG_WALLBOX_PV),
        "ladung_netz_kwh": reihe(300.0, NACHT_WALLBOX_NETZ, 0.0),
    }
    mapping: dict[str, dict] = {}
    for inv, felder in ((speicher, felder_speicher), (wallbox, felder_wallbox)):
        cfg = {}
        for feld, staende in felder.items():
            cfg[feld] = {"strategie": "sensor", "sensor_id": f"sensor.{inv.id}_{feld}"}
            key = f"inv:{inv.id}:{feld}"
            for ts, wert in zip(zeiten, staende):
                db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                                      zeitpunkt=ts, wert_kwh=round(wert, 3),
                                      quelle="ha_statistics"))
        mapping[str(inv.id)] = {"felder": cfg}
    anlage.sensor_mapping = {"investitionen": mapping}

    # ── Die Tageszeile: 24 Rückwärts-Slots (N-382) ────────────────────────
    wb_key = f"wallbox_{wallbox.id}"
    for h in range(24):
        batterie = 0.0
        komponenten: dict[str, float] = {}
        if h == 0 and nacht == "vortag":
            batterie = -NACHT_SPEICHER_NETZ
            komponenten[wb_key] = NACHT_WALLBOX_NETZ
        elif 10 <= h <= 13:
            batterie = -TAG_SPEICHER_PV / 4
            komponenten[wb_key] = TAG_WALLBOX_PV / 4
        elif 20 <= h <= 22:
            batterie = TAG_SPEICHER_ENTLADUNG / 3
        if nacht == "keine" and h == 0:
            # Gegenprobe: die „Nacht"-Menge liegt mitten im Tag, in beiden Fenstern.
            batterie = 0.0
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=DATUM, stunde=h,
            batterie_kw=round(batterie, 3),
            komponenten=komponenten or None,
        ))
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=DATUM,
                                komponenten_kwh={}))
    await db.commit()
    return anlage, speicher, wallbox


async def _investitionen(db, anlage):
    return {
        str(i.id): i
        for i in (await db.execute(
            select(Investition).where(Investition.anlage_id == anlage.id)
        )).scalars().all()
    }


async def _tagesbezug(db, anlage, wallbox):
    """Der Bezug, gegen den die Detailwerte stehen — aus den Stundenzeilen."""
    rows = (await db.execute(
        select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage.id,
            TagesEnergieProfil.datum == DATUM,
        ).order_by(TagesEnergieProfil.stunde)
    )).scalars().all()

    class _R:
        def __init__(self, r):
            self.pv_kw = None
            self.verbrauch_kw = None
            self.einspeisung_kw = None
            self.netzbezug_kw = None
            self.batterie_kw = r.batterie_kw
            self.waermepumpe_kw = None

    bilanz = bilanz_aus_stundenrows([_R(r) for r in rows])
    emob = sum(
        abs((r.komponenten or {}).get(f"wallbox_{wallbox.id}", 0.0)) for r in rows
    )
    return bilanz, emob


class TestNachtladungVorMitternacht:
    """[Vortag 23:00, 00:00) — die Ladung steht in der Tageszeile, nicht im Detail.

    **Vor dem Bau gemessen (erwartet):** ``speicher_ladung_netz_kwh`` = 0,0 bei
    10,0 kWh Tages-Ladung, von der 6,0 kWh aus dem Netz kamen; die Detailzeile
    „davon aus dem Netz (Arbitrage)" behauptet **0,0 kWh**, und die
    Wirkungsverluste rechnen den ganzen Roundtrip-Verlust mit der entgangenen
    Einspeisung statt zu 60 % mit dem Bezugspreis.
    """

    async def test_speicher_netzladung_steht_im_fenster_ihres_bezugs(self, db):
        anlage, speicher, wallbox = await _anlage(db, nacht="vortag")
        detail = await get_tagesdetail_kwh(
            db, anlage, await _investitionen(db, anlage), DATUM,
        )
        bilanz, _ = await _tagesbezug(db, anlage, wallbox)

        assert bilanz.speicher_ladung_kwh == pytest.approx(
            NACHT_SPEICHER_NETZ + TAG_SPEICHER_PV, abs=0.01
        )
        # NACH DEM BAU: 6,0 — VOR dem Bau 0,0.
        assert detail.werte["speicher_ladung_netz_kwh"] == pytest.approx(
            NACHT_SPEICHER_NETZ, abs=0.01
        )
        assert detail.werte["speicher_ladung_netz_kwh"] <= bilanz.speicher_ladung_kwh

    async def test_emob_teile_ergeben_das_ganze(self, db):
        anlage, speicher, wallbox = await _anlage(db, nacht="vortag")
        detail = await get_tagesdetail_kwh(
            db, anlage, await _investitionen(db, anlage), DATUM,
        )
        _, emob_bezug = await _tagesbezug(db, anlage, wallbox)

        assert emob_bezug == pytest.approx(NACHT_WALLBOX_NETZ + TAG_WALLBOX_PV, abs=0.01)
        # NACH DEM BAU: 8,0 — VOR dem Bau 0,0.
        assert detail.werte["emob_ladung_netz_kwh"] == pytest.approx(
            NACHT_WALLBOX_NETZ, abs=0.01
        )
        assert detail.werte["emob_ladung_pv_kwh"] == pytest.approx(
            TAG_WALLBOX_PV, abs=0.01
        )
        # PV + Netz decken die Ladung des Tages — das ist die Aussage der
        # Detailzeilen „Ladung · Netz-Anteil" neben „Ladung gesamt".
        summe = (detail.werte["emob_ladung_pv_kwh"]
                 + detail.werte["emob_ladung_netz_kwh"])
        assert summe == pytest.approx(emob_bezug, abs=0.01)


class TestNachtladungNachDreiundzwanzig:
    """[Heute 23:00, 24:00) — die Ladung steht im Detail, nicht in der Tageszeile.

    **Vor dem Bau gemessen (erwartet):** ``speicher_ladung_netz_kwh`` = 6,0 bei
    4,0 kWh Tages-Ladung ⇒ ``anteil_netz`` = 1,5, von ``Math.min(1, …)`` still
    auf 1,0 gekappt. Der Roundtrip-Verlust von 1,0 kWh wird damit **vollständig**
    mit dem Bezugspreis bewertet: 0,32 € statt 0,08 € (Einspeisepreis 8 ct,
    Bezugspreis 32 ct) — Faktor 4.
    """

    async def test_speicher_netzladung_faellt_in_den_folgetag(self, db):
        anlage, speicher, wallbox = await _anlage(db, nacht="eigene")
        detail = await get_tagesdetail_kwh(
            db, anlage, await _investitionen(db, anlage), DATUM,
        )
        bilanz, _ = await _tagesbezug(db, anlage, wallbox)

        assert bilanz.speicher_ladung_kwh == pytest.approx(TAG_SPEICHER_PV, abs=0.01)
        # NACH DEM BAU: 0,0 — VOR dem Bau 6,0 (und damit größer als sein Bezug).
        assert detail.werte["speicher_ladung_netz_kwh"] == pytest.approx(0.0, abs=0.01)
        assert detail.werte["speicher_ladung_netz_kwh"] <= bilanz.speicher_ladung_kwh

    async def test_emob_netzanteil_faellt_in_den_folgetag(self, db):
        anlage, speicher, wallbox = await _anlage(db, nacht="eigene")
        detail = await get_tagesdetail_kwh(
            db, anlage, await _investitionen(db, anlage), DATUM,
        )
        _, emob_bezug = await _tagesbezug(db, anlage, wallbox)

        assert emob_bezug == pytest.approx(TAG_WALLBOX_PV, abs=0.01)
        # NACH DEM BAU: 0,0 — VOR dem Bau 8,0 unter „Ladung gesamt 9,0 kWh".
        assert detail.werte["emob_ladung_netz_kwh"] == pytest.approx(0.0, abs=0.01)
        summe = (detail.werte["emob_ladung_pv_kwh"]
                 + detail.werte["emob_ladung_netz_kwh"])
        assert summe == pytest.approx(emob_bezug, abs=0.01)


class TestOhneRandstunde:
    """Gegenprobe: kein Geschehen in der Randstunde ⇒ beide Fenster gleich.

    Diese Klasse ist **vor und nach dem Bau grün**. Sie ist der Beleg, dass die
    beiden Klassen darüber auf der Fenster-Achse messen und nicht auf
    „irgendetwas hat sich geändert" — und sie hält fest, dass der Bau an einem
    gewöhnlichen Tag **keine** Zahl bewegt.
    """

    async def test_bitgleich(self, db):
        anlage, speicher, wallbox = await _anlage(db, nacht="keine")
        detail = await get_tagesdetail_kwh(
            db, anlage, await _investitionen(db, anlage), DATUM,
        )
        bilanz, emob_bezug = await _tagesbezug(db, anlage, wallbox)

        assert detail.werte["speicher_ladung_netz_kwh"] == pytest.approx(0.0, abs=0.01)
        assert detail.werte["emob_ladung_pv_kwh"] == pytest.approx(
            TAG_WALLBOX_PV, abs=0.01
        )
        assert detail.werte["emob_ladung_netz_kwh"] == pytest.approx(0.0, abs=0.01)
        assert bilanz.speicher_ladung_kwh == pytest.approx(TAG_SPEICHER_PV, abs=0.01)
        assert emob_bezug == pytest.approx(TAG_WALLBOX_PV, abs=0.01)


class TestWaermepumpeBleibtBedingt:
    """⛔ Der Bau darf die N-435-Weiche der Wärmepumpe **nicht** unbedingt machen.

    Die Wärmepumpe hängt an ``TagesZusammenfassung.komponenten_kwh``, und
    **deren** Fenster hängt an der Herkunft (``tageszeile_ist_rueckwaerts``) —
    im Snapshot-Pfad ist es [00:00, 24:00). Speicher und E-Mobilität hängen an
    den Stundenzeilen und liegen **immer** rückwärts. Wer beide Fälle über
    denselben unbedingten Schalter zieht, macht die Arbeitszahl im
    Snapshot-Pfad wieder falsch — die Gegenrichtung, die
    ``test_n435_tages_jaz_ein_fenster.py::test_snapshot_tag_bleibt_im_tagesfenster``
    festhält. Diese Probe steht hier nur als Zeiger; sie wird **dort** gefahren.
    """


class TestJederTypHatEinFenster:
    """⛔ Kein Gerätetyp fällt still in den Default (Schritt 4 der Vorlage).

    ``tagesfenster_fuer`` liefert für einen **unbekannten** Typ [00:00, 24:00) —
    das ist richtig als Rückfall (bitgleich zu vor N-444) und falsch als
    Voreinstellung für ein Feld, das jemand neu in ``TAGESDETAIL_AUSGABE``
    einträgt, ohne über sein Fenster nachzudenken. Genau diese Klasse hat N-444
    erzeugt: Speicher und E-Mobilität standen im Default, weil niemand ihren
    Bezug nachgeschlagen hatte.

    Die zweite Probe hängt nicht an der Mitgliedschaft in einer Tabelle, sondern
    am **Ergebnis** — ein Eintrag, der auf das falsche Fenster zeigt, wäre in der
    ersten Probe grün.
    """

    def test_jeder_ausgabe_typ_steht_in_der_tabelle(self):
        from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
        from backend.services.snapshot.boundary_range import TAGESFENSTER_JE_TYP

        typen = {typ for (typ, _feld) in TAGESDETAIL_AUSGABE}
        fehlend = sorted(typen - set(TAGESFENSTER_JE_TYP))
        assert not fehlend, (
            "Diese Typen liefern Tagesdetail-Werte, haben aber keinen Eintrag in "
            f"TAGESFENSTER_JE_TYP und landen still in [00:00, 24:00): {fehlend}. "
            "Fenster des Bezugs nachschlagen und eintragen (SOLL §3.3/S1a)."
        )

    @pytest.mark.parametrize(
        "typ,tz_rueckwaerts,erwartet_offsets",
        [
            # Speicher/E-Mob: Bezug = Stundenzeilen ⇒ IMMER rückwärts.
            ("speicher", False, (-1, 23)),
            ("speicher", True, (-1, 23)),
            ("wallbox", False, (-1, 23)),
            ("e-auto", False, (-1, 23)),
            # Wärmepumpe: Bezug = `komponenten_kwh` ⇒ Fenster der Tageszeile.
            ("waermepumpe", False, (0, 24)),
            ("waermepumpe", True, (-1, 23)),
            # Unbekannt/None: Rückfall, bitgleich zu vor N-444.
            ("pv_modul", True, (0, 24)),
            (None, True, (0, 24)),
        ],
    )
    def test_fenster_je_typ(self, typ, tz_rueckwaerts, erwartet_offsets):
        from backend.services.snapshot.boundary_range import tagesfenster_fuer

        rng = tagesfenster_fuer(
            typ, DATUM, tageszeile_rueckwaerts=tz_rueckwaerts
        )
        assert rng.boundary_offsets == erwartet_offsets
        assert rng.datum == DATUM

    @pytest.mark.parametrize("typ", ["speicher", "wallbox", "e-auto", "waermepumpe", None])
    @pytest.mark.parametrize("tz_rueckwaerts", [False, True])
    def test_kanal_tag_folgt_dem_bezug_in_den_kalendertag(self, typ, tz_rueckwaerts):
        """HA-Bauform S4 E-S4-1 (Bauplan §10a (1), «N-444 folgt dem Bezug»): an einem **Kanal-Tag** steht der Bezug —
        Bilanz-Ladung, Wallbox-Ladung, WP-Strom — im Kalendertag ``[00:00, 24:00)`` (``kanal/fenster.py``, R-3). Dieselbe
        Regel (Teilmenge im Fenster ihres Bezugs) gibt dann für JEDEN Typ ``for_day_total``; Bestandstage bleiben bei der
        Tabelle (Zeilen oben)."""
        from backend.services.snapshot.boundary_range import tagesfenster_fuer

        rng = tagesfenster_fuer(typ, DATUM, tageszeile_rueckwaerts=tz_rueckwaerts, kanal_tag=True)
        assert rng.boundary_offsets == (0, 24) and rng.datum == DATUM
