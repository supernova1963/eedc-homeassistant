"""HA-Bauform S5, Etappe E-S5-1 — die eine Ladefunktion der Stundenleser (Bauplan S5 §3 (A), §4 S5-R1; Auftrag Punkt 3).

``kanal_stunden.stunden_der_tage`` liefert die Stundenzeilen eines Bereichs: an einem Kanal-Tag der Bilanz die
Mischzeilen (dieselben wie *Cockpit → Tag* / ``tage-werte``), an jedem anderen Tag die Stundenzeile unverändert. Die
Leser aus §3 (A) rufen sie statt eines eigenen ``select(TagesEnergieProfil)``; die Tagesmengen der Tageszeile nehmen sie
an Kanal-Tagen aus ``kanal_tage`` (``pv_ist_je_tag``, ``komponenten_der_tage``, ``verworfen_der_tage``).

Proben (Auftrag Punkt 3):

* **(a) Bestandstag bitgleich** — Datenstand ohne Kanal (die Kanalzeilen gelöscht): jeder Leser rechnet mit der
  Ladefunktion dasselbe wie mit dem heutigen Lader (volle Stundenzeilen aus ``select(TagesEnergieProfil)``, Bereich und
  Ordnung wie vorher); die Ladefunktion selbst liefert dieselben Zeilen wie die Abfrage.
* **(b) Kanal-Tag** — Matrix-Form mit HA-Spiegel (``sum``/``change``): die Stunden, die ein Leser an einem Kanal-Tag
  bekommt, tragen die Mengen der Mischzeilen von ``tage-werte`` (``stunden_der_kanal_tage``) und ``raster = "beginn"``;
  die Stunde 23 liegt auf dem Beginn (S4-R-3b), gepaart wird über das Raster (Slot-Leser: ``bestandszeile_fuer_
  stundenbeginn``). PV-IST, Grundlast, Komponenten-Schlüssel am Kanal-Tag wie *Cockpit → Tag*.
* **(c) gemischter Bereich** — Bestand → Kanal-Naht: jede ``(Tag, Stunde)`` einmal, die Tagzahl gleich.
* **(d) N-593** — ``test_n593_wp_tagesfaktor.py`` (unverändert grün, Teil des Gates).
* **(e) Tagesvergleich** — ``tage_ohne_tagesvergleich``: ein Kanal-Tag mit Kanal-Mengen ohne Bündel in seinen
  Kanal-Stunden taugt für den Vergleich (die gefaltete Stundenzeile und ``verworfen`` der Bilanz-Achsen zählen dort
  nicht); ein Bestandstag mit Mitternachtsbündel bleibt draußen.

Datenstände: Achsen-Formen (``kanal_bilanz_gleichheit.datenstand``, HA, 01.06.–03.07.2026), Uhr der Matrix gestellt.
Schwesterdateien: test_kanal_stunden_sichten.py, test_s4_kalendertag_sichten.py, test_n593_wp_tagesfaktor.py.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update

from backend.core.berechnungen import summe_pv_bkw_kwh
from backend.core.berechnungen.slot_konvention import bestandszeile_fuer_stundenbeginn, ist_beginn_raster
from backend.models.anlage import Anlage
from backend.models.kanal import Kanal, KanalStatistik
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.api.routes import prognosen as _prognosen  # vor jedem Patch geladen: das Modul bindet `stunden_der_tage` beim Import
from backend.services.energie_profil import kanal_stunden as ks
from backend.services.kanal import bilanz_leser
from backend.tests import kanal_bilanz_gleichheit as kg

TAG = date(2026, 6, 15)
VON, BIS = date(2026, 6, 10), date(2026, 6, 20)
BILANZ = ("pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw")


@pytest.fixture
def uhr(monkeypatch):
    """Die Uhr der Leser steht auf der Uhr der Matrix (``kg.JETZT_TS``)."""
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)


class _Tag(date):
    """``date.today()`` der Leser mit eigener Uhr — festgenagelt auf den 04.07.2026 (Matrix-Uhr, N-167)."""

    @classmethod
    def today(cls):  # noqa: D401
        return cls(2026, 7, 4)


# ── Werkzeug ────────────────────────────────────────────────────────────────


async def _alter_lader(db, anlage_id, von, bis, *, felder=None):
    """Der heutige Lader der Leser (HEAD): volle Stundenzeilen ``von`` … ``bis`` aus ``select(TagesEnergieProfil)``,
    nach Tag und Stunde — ohne Kanal-Weiche."""
    q = select(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == anlage_id)
    if von is not None:
        q = q.where(TagesEnergieProfil.datum >= von)
    if bis is not None:
        q = q.where(TagesEnergieProfil.datum <= bis)
    return list((await db.execute(q.order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde))).scalars().all())


class _Spion:
    """Zeichnet jede Antwort von ``stunden_der_tage`` auf (der echte Lader läuft)."""

    def __init__(self, monkeypatch):
        self.antworten: list[list] = []
        self.hinweise: list[tuple] = []
        echt = ks.stunden_der_tage

        async def spion(*args, **kwargs):
            out = await echt(*args, **kwargs)
            self.antworten.append(out)
            self.hinweise.append(tuple(kwargs.get("felder") or ()))
            return out

        monkeypatch.setattr(ks, "stunden_der_tage", spion)
        monkeypatch.setattr(_prognosen, "stunden_der_tage", spion)

    def zeilen_am(self, tag: date, *, mit_feld: str | None = None) -> list:
        """Die Zeilen des Tages aus allen Antworten — mit ``mit_feld`` nur aus Aufrufen, deren Lade-Hinweis es nennt."""
        return [z for a, h in zip(self.antworten, self.hinweise) for z in a
                if z.datum == tag and (mit_feld is None or mit_feld in h)]


def _alter_lader_setzen(monkeypatch):
    monkeypatch.setattr(ks, "stunden_der_tage", _alter_lader)
    monkeypatch.setattr(_prognosen, "stunden_der_tage", _alter_lader)


async def _referenz(ds, tag: date) -> dict[int, object]:
    """Die Mischzeilen von ``tage-werte`` am Tag (``stunden_der_kanal_tage``, Gruppen der Sichten) je Stunde."""
    zeilen = await _alter_lader(ds.db, ds.aid, tag, tag + timedelta(days=1))
    je_tag: dict = {}
    for z in zeilen:
        je_tag.setdefault(z.datum, []).append(z)
    return {m.stunde: m for m in (await ks.stunden_der_kanal_tage(ds.db, ds.aid, [tag], je_tag))[tag]}


def _pruefe_mengen_wie_tage_werte(zeilen: list, ref: dict, felder=BILANZ) -> int:
    """Jede Zeile des Kanal-Tags ist eine Mischzeile mit den Mengen der ``tage-werte``-Mischzeile derselben Stunde."""
    assert zeilen, "der Leser bekam keine Stunden des Kanal-Tags"
    for z in zeilen:
        assert ist_beginn_raster(z), (z.datum, z.stunde)
        for f in felder:
            assert getattr(z, f) == getattr(ref[z.stunde], f), (z.stunde, f)
    return len(zeilen)


async def _kanal_loeschen(ds, *, vor: date | None = None) -> None:
    """Die Kanalzeilen der Anlage löschen (alle bzw. die vor ``vor`` 00:00) — danach liest der Tag als Bestand."""
    ids = select(Kanal.id).where(Kanal.anlage_id == ds.aid)
    q = delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(ids))
    if vor is not None:
        q = q.where(KanalStatistik.start_ts < int(datetime.combine(vor, datetime.min.time()).timestamp()))
    await ds.db.execute(q)
    await ds.db.commit()


def _gleich(a, b) -> bool:
    """Bitgleich (Floats ``==``) über Dataclasses, Pydantic-Modelle und schlichte Objekte mit Attributen."""
    if dataclasses.is_dataclass(a) and dataclasses.is_dataclass(b):
        return dataclasses.asdict(a) == dataclasses.asdict(b)
    if hasattr(a, "model_dump") and hasattr(b, "model_dump"):
        return a.model_dump() == b.model_dump()
    if hasattr(a, "__dict__") and hasattr(b, "__dict__") and type(a) is type(b) and not isinstance(a, (list, dict)):
        return vars(a).keys() == vars(b).keys() and all(_gleich(vars(a)[k], vars(b)[k]) for k in vars(a))
    if getattr(type(a), "__slots__", None) and type(a) is type(b):
        return all(_gleich(getattr(a, k), getattr(b, k)) for k in type(a).__slots__)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_gleich(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_gleich(x, y) for x, y in zip(a, b))
    return a == b


# ── die Ladefunktion ────────────────────────────────────────────────────────


def test_lade_hinweis_bestimmt_die_gruppen():
    assert ks.gruppen_des_hinweises(None) == ("bilanz", "wp", "emob")
    assert ks.gruppen_des_hinweises(("pv_kw", "soc_prozent")) == ("bilanz",)
    assert ks.gruppen_des_hinweises(("waermepumpe_kw",)) == ("bilanz", "wp")
    assert ks.gruppen_des_hinweises(("wallbox_kw", "waermepumpe_kw")) == ("bilanz", "emob", "wp")


async def test_bestand_dieselben_zeilen_wie_die_abfrage(db):
    """(a) ohne Kanal: dieselben Zeilen wie ``select(TagesEnergieProfil)`` — ohne Hinweis die ORM-Zeilen selbst, mit
    Hinweis die Werte der genannten Spalten; der Folgetag (S4-R-3b) gehört nicht zur Antwort; ``None`` = Bereich der
    Stundenzeilen."""
    a = Anlage(anlagenname="Bestand", leistung_kwp=5.0)
    db.add(a)
    await db.flush()
    for d in (TAG - timedelta(days=1), TAG, TAG + timedelta(days=1)):
        for h in range(24):
            db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=h, pv_kw=h / 10, netzbezug_kw=0.3,
                                      soc_prozent=50.0 + h, spannen={"pv": 2} if h == 3 else None,
                                      source_provenance={}))
    await db.commit()
    alt = await _alter_lader(db, a.id, TAG - timedelta(days=1), TAG)
    assert await ks.stunden_der_tage(db, a.id, TAG - timedelta(days=1), TAG) == alt
    mit = await ks.stunden_der_tage(db, a.id, TAG - timedelta(days=1), TAG, felder=("pv_kw", "soc_prozent"))
    assert [(z.datum, z.stunde, z.pv_kw, z.soc_prozent, z.spannen, z.created_at) for z in mit] == [
        (z.datum, z.stunde, z.pv_kw, z.soc_prozent, z.spannen, z.created_at) for z in alt]
    assert len(await ks.stunden_der_tage(db, a.id, None, None, felder=("pv_kw",))) == 72
    assert await ks.stunden_der_tage(db, a.id, date(2020, 1, 1), date(2020, 1, 2)) == []


async def test_kanal_tag_mischzeilen_wie_tage_werte(uhr):
    """(b) am Kanal-Tag die 24 Mischzeilen von ``tage-werte`` — Mengen aus dem Kanal, Stunde 23 auf dem Beginn mit den
    Backward-Bahnen aus Slot 0 des Folgetags (S4-R-3b), Ladestand zeilengleich."""
    async with kg.datenstand("achsen", "M04", "HA") as ds:
        zeilen = await ks.stunden_der_tage(ds.db, ds.aid, TAG, TAG, felder=(*BILANZ, "soc_prozent", "temperatur_c"))
        ref = await _referenz(ds, TAG)
        tep = {(z.datum, z.stunde): z for z in await _alter_lader(ds.db, ds.aid, TAG, TAG + timedelta(days=1))}
    assert [z.stunde for z in zeilen] == list(range(24))
    _pruefe_mengen_wie_tage_werte(zeilen, ref)
    assert zeilen[23].temperatur_c == tep[(TAG + timedelta(days=1), 0)].temperatur_c
    assert [z.soc_prozent for z in zeilen] == [tep[(TAG, h)].soc_prozent for h in range(24)]


async def test_gemischter_bereich_ohne_doppelzaehlung(uhr):
    """(c) Bestand → Kanal-Naht: vor dem 12.06. ohne Kanalzeilen ⇒ Stundenzeilen, danach Mischzeilen; jede (Tag, Stunde)
    einmal, die Tage = Tage mit Stundenzeile ∪ Kanal-Tage; die Mengen der Kanal-Tage wie ``tage-werte``."""
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _kanal_loeschen(ds, vor=date(2026, 6, 12))
        kanal = set(await bilanz_leser.kanal_tage(ds.db, ds.aid, VON, BIS))
        zeilen = await ks.stunden_der_tage(ds.db, ds.aid, VON, BIS, felder=BILANZ)
        tep_tage = {z.datum for z in await _alter_lader(ds.db, ds.aid, VON, BIS)}
        refs = {d: await _referenz(ds, d) for d in sorted(kanal)}
    assert kanal and min(kanal) >= date(2026, 6, 12) and date(2026, 6, 11) not in kanal
    schluessel = [(z.datum, z.stunde) for z in zeilen]
    assert len(schluessel) == len(set(schluessel)) and schluessel == sorted(schluessel)
    assert {z.datum for z in zeilen} == tep_tage | kanal
    for z in zeilen:
        assert ist_beginn_raster(z) == (z.datum in kanal)
    for d in kanal:
        _pruefe_mengen_wie_tage_werte([z for z in zeilen if z.datum == d], refs[d])


# ── die Leser: (b) am Kanal-Tag, (a) danach ohne Kanal ───────────────────────


def _leser_m04(ds, tarif):
    """Die Leser auf der Form M04 (zwei Speicher, Netzladung, Flex-Tarif mit Preissensor) — Name → Aufruf."""
    from backend.api.routes.aktueller_monat.vergleich import _load_grundlast_nacht_kw
    from backend.api.routes.energie_profil.serien import get_komponenten_serien, get_wochenmuster
    from backend.services import strompreis_aggregator as sa
    from backend.services.energie_profil.vergleichstage import tage_ohne_tagesvergleich
    from backend.services.speicher_potential_service import lade_potential_auswertung
    from backend.services.speicher_sizing_service import lade_sizing_auswertung
    from backend.services.speicher_wirtschaftlichkeit import berechne_effektiver_ladepreis
    from backend.services.verbrauch_prognose_service import get_verbrauch_prognose

    db, aid = ds.db, ds.aid
    return {
        "L1 effektiver Ladepreis": lambda: berechne_effektiver_ladepreis(db, anlage_id=aid, von=VON, bis=BIS),
        "L3 Sizing": lambda: lade_sizing_auswertung(db, aid, VON, BIS),
        "L4 Potenzial": lambda: lade_potential_auswertung(db, aid, VON, BIS, kapazitaet_brutto_kwh=15.0,
                                                          leer_schwelle_prozent=10.0),
        "L5 Preis-Aggregat": lambda: sa.lade_preis_aggregate_je_monat(db, aid),
        "L5 Monats-Ø": lambda: sa.berechne_monats_durchschnittspreis(aid, 2026, 6, db),
        "L5 Slot-Kosten": lambda: sa.lade_slot_kosten_je_tag(db, aid, von=VON, bis=BIS, tarif_fuer=lambda _t: tarif),
        "L7 Verbrauchsprognose": lambda: get_verbrauch_prognose(aid, date(2026, 6, 25), db),
        "L20 Grundlast Nacht": lambda: _load_grundlast_nacht_kw(aid, 2026, 6, db),
        "L23 Tagesvergleich": lambda: tage_ohne_tagesvergleich(db, aid, "pv", von=VON, bis=BIS),
        "L25 Wochenmuster": lambda: get_wochenmuster(anlage_id=aid, von=VON, bis=BIS, db=db),
        "L26 Komponenten-Serien": lambda: get_komponenten_serien(anlage_id=aid, von=VON, bis=BIS, db=db),
    }


#: Leser, deren Stunden durch `stunden_der_tage` laufen (L26 liest nur Tagesmengen).
_STUNDEN_LESER = ("L1", "L3", "L4", "L5", "L7", "L20", "L23", "L25")
#: Monats-Preisleser, deren Kanal-Monat der Kosten-Kanal deckt (HA-Bauform E4e) — sie fragen dort keine Stunden.
_UEBER_KOSTEN_KANAL = ("L5 Preis-Aggregat", "L5 Monats-Ø")


async def _tarif(ds):
    from backend.api.routes.strompreise import lade_tarife_fuer_anlage

    return (await lade_tarife_fuer_anlage(ds.db, ds.aid, TAG)).get("allgemein")


async def test_leser_m04_kanal_tag_und_bestand(uhr, monkeypatch):
    """M04: (b) jeder Leser bekommt am Kanal-Tag die Mischzeilen von ``tage-werte`` (Mengen, Raster); (a) nach dem
    Löschen der Kanalzeilen rechnet jeder Leser mit der Ladefunktion dasselbe wie mit dem heutigen Lader."""
    async with kg.datenstand("achsen", "M04", "HA") as ds:
        ref = await _referenz(ds, TAG)
        tarif = await _tarif(ds)
        for name, aufruf in _leser_m04(ds, tarif).items():
            with monkeypatch.context() as m:
                spion = _Spion(m)
                await aufruf()
                if name in _UEBER_KOSTEN_KANAL:
                    # E4e: den Juni deckt der Kosten-Kanal — das Aggregat kommt aus den Kanal-Δ, keine Stunde nötig.
                    from backend.services.kanal.preis_leser import preis_monate

                    assert (2026, 6) in (await preis_monate(ds.db, ds.aid))[0] and not spion.zeilen_am(TAG), name
                elif name.split()[0] in _STUNDEN_LESER:
                    _pruefe_mengen_wie_tage_werte(spion.zeilen_am(TAG), ref,
                                                  felder=("netzbezug_kw",) if name.startswith("L5") else BILANZ)

        await _kanal_loeschen(ds)
        assert not await bilanz_leser.kanal_tage(ds.db, ds.aid, VON, BIS)
        for name, aufruf in _leser_m04(ds, tarif).items():
            neu = await aufruf()
            with monkeypatch.context() as m:
                _alter_lader_setzen(m)
                alt = await aufruf()
            assert _gleich(neu, alt), name


async def test_kanal_tag_tagesmengen_wie_cockpit_tag(uhr):
    """(b) Tagesmengen: PV-IST (L11/L12/L14) = Σ PV des Kanal-Tags (``kanal_tage``, die Erzeugung von ``tage-werte``),
    Grundlast (L20) aus den Mischzeilen 0–4, Komponenten-Schlüssel (L26) mit den Kanal-Schlüsseln; (a) ohne Kanal die
    Tageszeile."""
    from backend.api.routes.aktueller_monat.vergleich import _load_grundlast_nacht_kw
    from backend.api.routes.energie_profil.tage import get_tage_werte

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        tz = (await ds.db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum.between(VON, BIS)))).scalars().all()
        kanal = await bilanz_leser.kanal_tage(ds.db, ds.aid, VON, BIS)
        ist = await ks.pv_ist_je_tag(ds.db, ds.aid, tz)
        zeile = {z.datum: z for z in await get_tage_werte(ds.aid, TAG, TAG, ds.db)}[TAG]
        nacht = await _load_grundlast_nacht_kw(ds.aid, 2026, 6, ds.db)
        misch = await ks.stunden_der_tage(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30), felder=("verbrauch_kw",))
        komp = await ks.komponenten_der_tage(ds.db, ds.aid, VON, BIS, {z.datum: z.komponenten_kwh for z in tz})
        await _kanal_loeschen(ds)
        ist_bestand = await ks.pv_ist_je_tag(ds.db, ds.aid, tz)
        komp_bestand = await ks.komponenten_der_tage(ds.db, ds.aid, VON, BIS, {z.datum: z.komponenten_kwh for z in tz})
    assert TAG in kanal
    assert ist[TAG] == pytest.approx(summe_pv_bkw_kwh(kanal[TAG].komponenten_kwh))
    assert ist[TAG] == pytest.approx(zeile.pv_anlage + zeile.bkw, abs=0.01)
    assert nacht == [float(r.verbrauch_kw) for r in misch if r.stunde < 5 and (r.verbrauch_kw or 0) > 0]
    assert set(kanal[TAG].komponenten_kwh) <= set(komp[TAG])
    assert ist_bestand == {z.datum: (summe_pv_bkw_kwh(z.komponenten_kwh) if z.komponenten_kwh else None) for z in tz}
    assert komp_bestand == {z.datum: z.komponenten_kwh for z in tz}


async def test_wallbox_stunden_am_kanal_tag_auf_dem_beginn(uhr):
    """L6 (M08): die Wallbox-Stunden eines Kanal-Tags aus den Mischzeilen der E-Mob-Gruppe — Beginn ``D + h``, Menge =
    Kanal; ohne Kanal die Stundenzeile mit dem Backward-Slot (``stunden_beginn``)."""
    from backend.services.emob_ladebloecke import stunden_beginn
    from backend.services.emob_ladebloecke_speicher import wallbox_stunden_gespeichert

    async with kg.datenstand("achsen", "M08", "HA") as ds:
        misch = {z.stunde: z for z in await ks.stunden_der_tage(ds.db, ds.aid, TAG, TAG, felder=("wallbox_kw",))}
        kanal = await wallbox_stunden_gespeichert(ds.db, ds.aid, TAG)
        await _kanal_loeschen(ds)
        bestand = await wallbox_stunden_gespeichert(ds.db, ds.aid, TAG)
        tep = {z.stunde: z for z in await _alter_lader(ds.db, ds.aid, TAG, TAG)}
    assert kanal and all(ist_beginn_raster(m) for m in misch.values())
    t0 = datetime(TAG.year, TAG.month, TAG.day)
    assert [(s.beginn, s.kwh) for s in kanal] == [
        (t0 + timedelta(hours=h), float(m.wallbox_kw)) for h, m in sorted(misch.items()) if (m.wallbox_kw or 0) > 0]
    assert [(s.beginn, s.kwh) for s in bestand] == [
        (stunden_beginn(TAG, h), float(z.wallbox_kw)) for h, z in sorted(tep.items()) if (z.wallbox_kw or 0) > 0]


async def test_verbrauchsprofil_kanal_tag_und_bestand(uhr, monkeypatch):
    """L8 (M05, Wärmepumpe): das Lernprofil liest am Kanal-Tag die Mischzeilen (Verbrauch und WP-Strom aus den Kanälen,
    WP-Gruppe über den Lade-Hinweis); ohne Kanal dasselbe Profil wie mit dem heutigen Lader."""
    from backend.services import live_verbrauchsprofil_service as lvps

    monkeypatch.setattr(lvps, "date", _Tag)
    async with kg.datenstand("achsen", "M05", "HA") as ds:
        tag = date(2026, 7, 1)
        ref = await _referenz(ds, tag)
        with monkeypatch.context() as m:
            spion = _Spion(m)
            gelernt = await lvps._profil_from_db(ds.aid, ds.db)
        zeilen = spion.zeilen_am(tag)
        _pruefe_mengen_wie_tage_werte(zeilen, ref, felder=("verbrauch_kw", "waermepumpe_kw"))
        await _kanal_loeschen(ds)
        neu = await lvps._profil_from_db(ds.aid, ds.db)
        with monkeypatch.context() as m:
            _alter_lader_setzen(m)
            alt = await lvps._profil_from_db(ds.aid, ds.db)
    assert gelernt is not None and neu == alt


async def _lern_soll_saeen(ds) -> None:
    """Lern-SOLL und Day-Ahead-Profil je Tag (Glocke, 0,9 × PV) — Eingang des Korrekturprofils und der Stratifizierung."""
    glocke = [0.0] * 6 + [0.2, 0.6, 1.2, 1.8, 2.2, 2.4, 2.4, 2.2, 1.8, 1.2, 0.6, 0.2] + [0.0] * 6
    await ds.db.execute(update(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == ds.aid).values(
        lern_soll_kwh=sum(glocke), lern_soll_stundenprofil_kwh=glocke, pv_prognose_kwh=sum(glocke),
        pv_prognose_stundenprofil=glocke))
    await ds.db.execute(update(Anlage).where(Anlage.id == ds.aid).values(latitude=51.0, longitude=11.0))
    await ds.db.commit()


async def test_korrekturprofil_stunden_auf_dem_slot(uhr, monkeypatch):
    """L9/L24 (M01): die IST-Stunden des Korrekturprofils und der Stratifizierung kommen am Kanal-Tag aus den
    Mischzeilen und liegen auf dem Slot des Lern-SOLL (Stunde ``h`` ⇒ ``(D, h+1)``, Stunde 23 ⇒ ``(D+1, 0)``); das
    Tages-IST der Skalar-Stufe ist Σ der Mischzeilen; ohne Kanal dieselben Zeilen und Faktoren wie mit dem heutigen
    Lader."""
    from backend.api.routes import korrekturprofil as route
    from backend.services import korrekturprofil_aggregator as ka

    monkeypatch.setattr(route, "date", _Tag)
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _lern_soll_saeen(ds)
        # Gegenprobe: die gefaltete PV der Stundenzeilen des Kanal-Tags verfälscht — ein Leser auf der Stundenzeile fiele auf.
        await ds.db.execute(update(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == TAG,
            TagesEnergieProfil.stunde.between(8, 16)).values(pv_kw=TagesEnergieProfil.pv_kw + 5.0))
        await ds.db.commit()
        misch = {z.stunde: z for z in await ks.stunden_der_tage(ds.db, ds.aid, TAG, TAG, felder=("pv_kw",))}
        stunden = [s for s in await ka.lade_ist_wetter_stunden(ds.db, ds.aid, [TAG, TAG + timedelta(days=1)])
                   if s[0] == TAG + timedelta(days=1) and s[1] == 0 or s[0] == TAG]
        skalar = await ka._lade_tagesist_skalar(ds.db, ds.aid, TAG, TAG + timedelta(days=1))
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        ref = await _referenz(ds, TAG)
        for name, aufruf in (
            ("L9 Korrekturprofil", lambda: ka.aggregiere_korrekturprofil_anlage(anlage, ds.db, heute=date(2026, 7, 4))),
            ("L24 Stratifizierung", lambda: route.stratifizierung_endpoint(anlage_id=ds.aid, tage=60, db=ds.db)),
        ):
            with monkeypatch.context() as m:
                spion = _Spion(m)
                await aufruf()
                # die IST-Stunden der Bin-Stufen (Lade-Hinweis mit Wetter), nicht nur das Tages-IST der Skalar-Stufe
                _pruefe_mengen_wie_tage_werte(spion.zeilen_am(TAG, mit_feld="bewoelkung_prozent"), ref, felder=("pv_kw",))
        await _kanal_loeschen(ds)
        neu = (await ka.lade_ist_wetter_stunden(ds.db, ds.aid, [TAG]),
               await ka._lade_tagesist_skalar(ds.db, ds.aid, VON, BIS),
               await ka.aggregiere_korrekturprofil_anlage(anlage, ds.db, heute=date(2026, 7, 4)),
               (await route.stratifizierung_endpoint(anlage_id=ds.aid, tage=60, db=ds.db)).model_dump())
        with monkeypatch.context() as m:
            _alter_lader_setzen(m)
            alt = (await ka.lade_ist_wetter_stunden(ds.db, ds.aid, [TAG]),
                   await ka._lade_tagesist_skalar(ds.db, ds.aid, VON, BIS),
                   await ka.aggregiere_korrekturprofil_anlage(anlage, ds.db, heute=date(2026, 7, 4)),
                   (await route.stratifizierung_endpoint(anlage_id=ds.aid, tage=60, db=ds.db)).model_dump())
    assert all(ist_beginn_raster(m) for m in misch.values())
    soll = {bestandszeile_fuer_stundenbeginn(TAG, h): m.pv_kw for h, m in misch.items()}
    assert {(s[0], s[1]): s[2] for s in stunden if (s[0], s[1]) in soll} == soll
    assert skalar[TAG][0] == pytest.approx(sum(m.pv_kw for m in misch.values() if (m.pv_kw or 0) > 0))
    assert neu[0] and neu[1] and neu[2]["status"] == "ok"
    for a, b in zip(neu, alt):
        assert _gleich(a, b)


async def test_prognose_leser_pv_ist_am_kanal_tag(uhr, monkeypatch):
    """L11/L12/L14 (M01): MAE des HA-Exports, *Prognosen → Genauigkeit* und Lernfaktor nehmen das PV-IST am Kanal-Tag aus
    ``kanal_tage`` (``pv_ist_je_tag``); die IST-Stunden von heute (Prognosen → Vergleich) kommen aus der Ladefunktion;
    ohne Kanal dieselben Ergebnisse wie mit der Tageszeile."""
    from backend.api.routes import live_wetter, prognosen
    from backend.services import prognose_genauigkeit_service as pg

    monkeypatch.setattr(prognosen, "date", _Tag)

    async def faktor(*_a, **_k):
        return 1.0

    monkeypatch.setattr(live_wetter, "_get_lernfaktor", faktor)
    heute = date(2026, 7, 4)
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _lern_soll_saeen(ds)
        # Gegenprobe: die Tageszeile des Kanal-Tags trägt eine falsche PV — der Kanal-Tag nimmt sie nicht.
        tz_tag = (await ds.db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG))).scalar_one()
        falsch = {k: (v * 3 if k.startswith(("pv_", "bkw_")) else v) for k, v in (tz_tag.komponenten_kwh or {}).items()}
        await ds.db.execute(update(TagesZusammenfassung).where(TagesZusammenfassung.id == tz_tag.id).values(
            komponenten_kwh=falsch))
        await ds.db.commit()
        live_wetter._lernfaktor_cache.clear()
        tz = (await ds.db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid))).scalars().all()
        kanal = await bilanz_leser.kanal_tage(ds.db, ds.aid, date(2026, 6, 1), date(2026, 7, 3))
        ist = await ks.pv_ist_je_tag(ds.db, ds.aid, tz)
        gen = await prognosen.get_prognosen_genauigkeit(anlage_id=ds.aid, tage=30, ausreisser_ausblenden=False,
                                                        db=ds.db)
        heute_zeilen = await prognosen.stunden_der_tage(ds.db, ds.aid, date(2026, 7, 3), date(2026, 7, 3),
                                                        felder=("pv_kw",))
        mae_kanal = await pg.eedc_mae_prozent(ds.db, ds.aid, heute=heute)
        lf_kanal = await live_wetter._get_lernfaktor_detail(ds.aid, ds.db, heute=heute)
        await _kanal_loeschen(ds)
        live_wetter._lernfaktor_cache.clear()
        neu = (await pg.eedc_mae_prozent(ds.db, ds.aid, heute=heute),
               (await prognosen.get_prognosen_genauigkeit(anlage_id=ds.aid, tage=30, ausreisser_ausblenden=False,
                                                          db=ds.db)).model_dump(),
               await live_wetter._get_lernfaktor_detail(ds.aid, ds.db, heute=heute))
        live_wetter._lernfaktor_cache.clear()
        bestand_ist = await ks.pv_ist_je_tag(ds.db, ds.aid, tz)
    assert kanal and all(ist[d] == pytest.approx(summe_pv_bkw_kwh(k.komponenten_kwh)) for d, k in kanal.items() if d in ist)
    eintrag = {e.datum: e for e in gen.tage}[TAG.isoformat()]
    assert eintrag.ist_kwh == round(ist[TAG], 1)
    assert heute_zeilen and all(ist_beginn_raster(z) for z in heute_zeilen)
    assert bestand_ist == {z.datum: (summe_pv_bkw_kwh(z.komponenten_kwh) if z.komponenten_kwh else None) for z in tz}
    assert neu[0][1] > 0 and neu[2].faktor is not None
    # Die verfälschte Tageszeile (PV × 3) wirkt nur ohne Kanal: am Kanal-Tag sind MAE und Lernfaktor andere Zahlen als
    # am Bestandstag mit derselben Tageszeile (L11/L14), und die Genauigkeit nennt das Kanal-IST (L12, oben).
    assert summe_pv_bkw_kwh(falsch) == pytest.approx(3 * ist[TAG], rel=1e-6) and eintrag.ist_kwh != round(summe_pv_bkw_kwh(falsch), 1)
    assert mae_kanal != neu[0] and lf_kanal != neu[2]   # Lernfaktor: der Legacy-Skalar (delta_o12_pct) sieht den Tag


async def test_tagesvergleich_kanal_tag_traegt_energie_bestandstag_buendel_bleibt(uhr):
    """(e) ``tage_ohne_tagesvergleich``: am Kanal-Tag trägt die gefaltete Stundenzeile ein Mitternachtsbündel mit Energie
    und die Tageszeile ``verworfen.pv`` — der Tag bleibt im Vergleich (die Kanal-Stunden tragen kein Bündel, der Kanal
    verwirft nichts); derselbe Befund an einem Bestandstag nimmt ihn und den Vortag heraus."""
    from backend.services.energie_profil.vergleichstage import tage_ohne_tagesvergleich

    kanal_tag, bestand_tag = date(2026, 6, 20), date(2026, 6, 8)
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _kanal_loeschen(ds, vor=date(2026, 6, 12))
        for d in (kanal_tag, bestand_tag):
            await ds.db.execute(update(TagesEnergieProfil).where(
                TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == d,
                TagesEnergieProfil.stunde == 0).values(spannen={"pv": 3}, pv_kw=1.5))
        await ds.db.execute(update(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == kanal_tag + timedelta(days=2),
        ).values(verworfen={"pv": {"grund": "probe"}}))
        await ds.db.commit()
        kanal = set(await bilanz_leser.kanal_tage(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30)))
        ohne = await tage_ohne_tagesvergleich(ds.db, ds.aid, "pv", von=date(2026, 6, 1), bis=date(2026, 6, 30))
    assert {kanal_tag, kanal_tag + timedelta(days=2)} <= kanal and bestand_tag not in kanal
    assert kanal_tag not in ohne and kanal_tag - timedelta(days=1) not in ohne
    assert kanal_tag + timedelta(days=2) not in ohne
    assert {bestand_tag, bestand_tag - timedelta(days=1)} <= ohne


async def test_verworfen_der_tage_kanal_tag_ohne_bilanz_achsen(db, uhr):
    """``verworfen_der_tage``: an einem Kanal-Tag fallen die Bilanz-Achsen weg (``mische_verworfen``), andere Achsen und
    Bestandstage bleiben."""
    a = Anlage(anlagenname="Marke", leistung_kwp=5.0)
    db.add(a)
    await db.flush()
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG, verworfen={"pv": 1, "waermepumpe": 2}))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG + timedelta(days=1), verworfen={"pv": 1}))
    await db.commit()
    assert await ks.verworfen_der_tage(db, a.id, TAG, TAG + timedelta(days=1), kanal=[TAG]) == {
        TAG: {"waermepumpe": 2}, TAG + timedelta(days=1): {"pv": 1}}
    assert await ks.verworfen_der_tage(db, a.id, TAG, TAG + timedelta(days=1)) == {
        TAG: {"pv": 1, "waermepumpe": 2}, TAG + timedelta(days=1): {"pv": 1}}


async def test_bezugspreis_boersenmittel_kanal_tag_zeilengleich(uhr):
    """L17 (M04): das Börsenmittel des HA-Exports paart am Kanal-Tag Bezug und Börse derselben Mischzeile (beide
    ``[h, h+1)``); ohne Kanal dasselbe Mittel wie mit dem heutigen Lader (Börse forward → Slot h+1)."""
    from backend.services import ha_export_bezugspreis as hb

    async with kg.datenstand("achsen", "M04", "HA") as ds:
        await ds.db.execute(update(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == ds.aid).values(
            boersenpreis_cent=TagesEnergieProfil.stunde + 5.0))
        await ds.db.commit()
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        misch = await ks.stunden_der_tage(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30),
                                          felder=("netzbezug_kw", "boersenpreis_cent"))
        kanal_mittel = await hb._boersenmittel_monat(ds.db, anlage, None, 2026, 6)
    paare = [(z.boersenpreis_cent, z.netzbezug_kw) for z in misch if (z.netzbezug_kw or 0) > 0]
    from backend.core.berechnungen.preis_reihe import boersenmittel_gewichtet

    assert all(ist_beginn_raster(z) for z in misch)
    assert kanal_mittel[0] == boersenmittel_gewichtet(paare)


def test_spion_und_alter_lader_sind_schaerfer_als_ein_name():
    """Werkzeug-Selbstprobe: ``_pruefe_mengen_wie_tage_werte`` schlägt an, wenn eine Zeile keine Mischzeile ist oder eine
    Menge abweicht — sonst bewiese (b) nichts."""
    ref = {0: SimpleNamespace(**{f: 1.0 for f in BILANZ})}
    with pytest.raises(AssertionError):
        _pruefe_mengen_wie_tage_werte([SimpleNamespace(datum=TAG, stunde=0, **{f: 1.0 for f in BILANZ})], ref)
    with pytest.raises(AssertionError):
        _pruefe_mengen_wie_tage_werte([], ref)
    falsch = SimpleNamespace(datum=TAG, stunde=0, raster="beginn", **{f: 2.0 for f in BILANZ})
    with pytest.raises(AssertionError):
        _pruefe_mengen_wie_tage_werte([falsch], ref)


async def test_zeitfenster_preis_gewichtet_mit_den_mischzeilen(uhr, monkeypatch):
    """L5 ``wirksamer_arbeitspreis_cent`` (T4, HT/NT): deckt kein Netzbezugs-Kanal den Monat, gewichtet der Preis die
    Stunden aus der Ladefunktion — am Kanal-Tag die Mischzeilen, jede mit dem Preis IHRER Uhrstunde (Beginn ``h``, über
    ``bestandszeile_fuer_stundenbeginn`` auf den Slot gelegt); Soll unabhängig vom Produktcode
    (``achsen_matrix.preis_zeitfenster``). Ohne Kanal wie mit dem heutigen Lader."""
    from backend.api.routes.strompreise import lade_tarife_fuer_anlage
    from backend.services import strompreis_aggregator as sa
    from backend.services.kanal import preis_leser
    from backend.tests import achsen_matrix as am

    async def _keine(*_a, **_k):
        return None

    monkeypatch.setattr(preis_leser, "netzbezug_zellen_des_monats", _keine)
    async with kg.datenstand("achsen", "T4", "HA") as ds:
        tarif = (await lade_tarife_fuer_anlage(ds.db, ds.aid, TAG)).get("allgemein")
        kanal = await bilanz_leser.kanal_tage(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30))
        wert = await sa.wirksamer_arbeitspreis_cent(ds.db, ds.aid, 2026, 6, tarif)
        misch = await ks.stunden_der_tage(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30), felder=("netzbezug_kw",))
        await _kanal_loeschen(ds)
        neu = await sa.wirksamer_arbeitspreis_cent(ds.db, ds.aid, 2026, 6, tarif)
        with monkeypatch.context() as m:
            _alter_lader_setzen(m)
            alt = await sa.wirksamer_arbeitspreis_cent(ds.db, ds.aid, 2026, 6, tarif)
    assert len(kanal) == 30 and all(ist_beginn_raster(z) for z in misch)
    menge = [(max(0.0, z.netzbezug_kw), am.preis_zeitfenster(z.stunde)) for z in misch if z.netzbezug_kw is not None]
    soll = sum(k * p for k, p in menge) / sum(k for k, _ in menge)
    assert wert == pytest.approx(round(soll, 4), abs=1e-4)
    assert neu == alt


async def test_ist_heute_regelmarke_wie_tage_werte(uhr, monkeypatch):
    """L12 *Prognosen → Vergleich* (M01): die IST-Stunden von heute aus der Ladefunktion; ``verworfen.pv`` der heutigen
    Tageszeile macht den Kanal-Tag nicht unvollständig (der Kanal verwirft nichts), den Bestandstag weiter schon."""
    from backend.api.routes import prognosen

    heute = date(2026, 7, 2)
    jetzt = datetime(2026, 7, 2, 23, 30)
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await ds.db.execute(update(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == heute,
        ).values(verworfen={"pv": {"grund": "probe"}}))
        await ds.db.commit()
        zeilen = await prognosen.stunden_der_tage(ds.db, ds.aid, heute, heute, felder=("pv_kw",))
        kanal = await prognosen._ist_heute(ds.db, ds.aid, heute, jetzt, zeilen)
        await _kanal_loeschen(ds)
        zeilen_b = await prognosen.stunden_der_tage(ds.db, ds.aid, heute, heute, felder=("pv_kw",))
        bestand = await prognosen._ist_heute(ds.db, ds.aid, heute, jetzt, zeilen_b)
    assert zeilen and all(ist_beginn_raster(z) for z in zeilen)
    assert kanal.ist_heute_kwh == pytest.approx(sum(z.pv_kw for z in zeilen if z.pv_kw is not None))
    assert not kanal.ist_unvollstaendig
    assert bestand.ist_unvollstaendig and not any(ist_beginn_raster(z) for z in zeilen_b)
