"""N-799 Sitzung 3 «Benennung» (Bauplan Fassung 3, E-10, §7): der Daten-Checker-Befund ``erfassung_stillstand``.

* **Der Tages-Satz hängt am Kennzeichen der Tagesbilanz**, nicht an der Fensterliste: ``fenster`` ⇒ «aus den Zählerständen
  gerechnet» (mit Mindest-Netzladung, wenn die Begrenzung griff), ``nicht_rechenbar`` ⇒ der Grund und «die drei Spalten
  bleiben leer», ein Stillstand mit gepaarter Nachtragsstunde (``voll``) ⇒ «wie an jedem anderen Tag gerechnet».
  Sprengsatz: ein Satz an der Fensterliste nennte am ``voll``-Tag die Zähler-Rechnung.
* **Zwei Lagen in einem Code:** Tagesliste (höchstens zehn) und «regelmäßig» (Häufigkeits- bzw. Grob-Sperre).
* **Immer eine Zeile:** ohne Fund eine OK-Zeile desselben Codes — die Tagestabelle verlinkt jeden gekennzeichneten Tag mit
  ``befund=erfassung_stillstand``, auch ältere als 90 Tage (Vitest ``DatenCheckerTeile.befund-link.test.tsx``).
* **Dieselbe Rechnung wie die Tagestabelle:** am Kanal-Tag nennt der Befund genau die Tage, die ``tage-werte`` kennzeichnet.
* **Nicht doppelt mit N-567:** nennt der Befund einen Tag, lässt N-567 ihn aus.

Zeitpunkte im Juni (fern jeder Umstellung); einmal in ``Pacific/Auckland`` und ``UTC`` gefahren.

Schwesterdateien: test_n799_s2_leser.py (Kennzeichen und Grund der Tagestabelle), test_n799_stillstand_lesestelle.py (die
Fenster), test_n567_nachtrag_benannt.py (N-567), test_daten_checker_codes.py (W-1/W-3, Katalog).
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from backend.core.berechnungen.spannen import SPERRE_GROB, SPERRE_HAEUFIG, StillstandFenster
from backend.core.berechnungen.tagesbilanz import PAARUNG_FENSTER, PAARUNG_NICHT_RECHENBAR, bilanz_aus_stundenrows
from backend.services.daten_checker import erfassung_stillstand as es
from backend.services.daten_checker.handgriffe import HANDGRIFFE

TAG = date(2026, 6, 20)


def _z(stunde, pv, v, e, n, spannen=None, ladung=None, entladung=None):
    return SimpleNamespace(stunde=stunde, raster="beginn", pv_kw=pv, verbrauch_kw=v, einspeisung_kw=e, netzbezug_kw=n,
                           batterie_kw=None if ladung is None else (entladung or 0.0) - ladung, waermepumpe_kw=None,
                           spannen=spannen, speicher_ladung_kw=ladung, speicher_entladung_kw=entladung, datum=TAG)


def _fenster(von_h, k, sperre=None, tag=TAG):
    von = int(datetime(tag.year, tag.month, tag.day, von_h).timestamp())
    return StillstandFenster(von, von + k * 3600, k, frozenset({"pv", "einspeisung", "netzbezug"}), sperre)


def _vier(n):
    return {"pv": n, "einspeisung": n, "netzbezug": n, "batterie": n}


def _tag(zeilen, fenster=()):
    b = bilanz_aus_stundenrows(zeilen)
    return es._Tag(TAG, b, es._stellen_des_tages(TAG, zeilen, list(fenster), b))


# ── Satz am Kennzeichen ──────────────────────────────────────────────────────────────────────────────────────────────

def test_fenster_satz_mit_stunden_und_mengen():
    z = [_z(9, 1.0, 1.0, 0.0, 0.0), _z(13, 20.0, 8.0, 10.0, 0.5, _vier(4), 2.0, 0.5)]
    t = _tag(z, [_fenster(10, 3)])
    text_ = es._tag_text(t)
    assert t.bilanz.stundenpaarung == PAARUNG_FENSTER
    assert text_.startswith("20.06.2026: Für die Stunden von 10 bis 14 Uhr stand die Erfassung; nachgetragen: PV 20,0 kWh")
    assert "Speicher-Ladung 2,0 kWh, Speicher-Entladung 0,5 kWh." in text_
    assert es.SATZ_FENSTER in text_ and "aus dem Netz geladen" not in text_


def test_mindest_netzladung_bei_begrenzung():
    z = [_z(13, 33.0, 10.0, 28.0, 35.0, _vier(4), 30.0, 0.0)]
    text_ = es._tag_text(_tag(z, [_fenster(10, 3)]))
    assert es.SATZ_FENSTER in text_
    assert "mindestens 25,0 kWh aus dem Netz geladen; der Überschuss ist auf die PV-Menge begrenzt." in text_


def test_voll_gepaarter_stillstand_nennt_keine_zaehler_rechnung():
    """15.7.2026 (Produktiv): ein Fenster, die Nachtragsstunde trägt PV ≤ 0,1 kWh ⇒ gepaart (``voll``). Sprengsatz: der
    Satz an der Fensterliste statt am Kennzeichen nennte hier die Zähler-Rechnung."""
    z = [_z(5, 0.064, 3.0, 0.03, 0.04, _vier(6), 0.0, 2.9)]
    t = _tag(z, [_fenster(0, 5)])
    text_ = es._tag_text(t)
    assert t.bilanz.stundenpaarung == "voll"
    assert es.SATZ_FENSTER not in text_
    assert es.SATZ_VOLL.format(was="PV") in text_
    assert "Für die Stunden von 0 bis 6 Uhr stand die Erfassung" in text_


def test_k1_nachgetragen_nennt_nur_gebuendelte_zaehler():
    """K1 (Nachmessung F1, 6.11.2025): Einspeisung und Netzbezug n = 9, PV und Speicher jede Stunde eine Zeile ⇒ «nachgetragen»
    nennt nur Einspeisung und Netzbezug. Sprengsatz: ohne die Auswahl stünden PV 4,4 und Speicher-Ladung 4,2 kWh als Nachtrag
    da. Gleiche n (Stillstand) ⇒ alle Zähler. Mengen einheitlich mit einer Nachkommastelle, unter 0,05 kWh «unter 0,1 kWh»."""
    z = _z(9, 4.433, None, 0.054, 4.266, {"einspeisung": 9, "netzbezug": 9}, 4.16, 0.0)
    text_ = es._tag_text(_tag([z]))
    assert "nachgetragen: Einspeisung 0,1 kWh, Netzbezug 4,3 kWh." in text_
    assert "PV 4,4" not in text_ and "Speicher-Ladung" not in text_
    gleich = es._mengen(_z(13, 20.0, 8.0, 0.04, 0.003, _vier(4), 2.0, -0.001))
    assert gleich == ("PV 20,0 kWh, Einspeisung unter 0,1 kWh, Netzbezug 0,0 kWh, Speicher-Ladung 2,0 kWh, "
                      "Speicher-Entladung 0,0 kWh")


def test_nicht_rechenbar_ungleich_und_saldiert():
    ungleich = [_z(9, 4.4, None, 0.05, 4.3, {"einspeisung": 9, "netzbezug": 9}, 4.2, 0.04)]
    t = _tag(ungleich)
    assert t.bilanz.stundenpaarung == PAARUNG_NICHT_RECHENBAR
    text_ = es._tag_text(t)
    assert "Für die Stunden von 1 bis 10 Uhr fehlten Stundenwerte" in text_ and es.SATZ_UNGLEICH in text_
    saldiert = SimpleNamespace(**{**vars(_z(13, 20.0, 8.0, 10.0, 0.5, _vier(4))), "batterie_kw": -1.5})
    t2 = _tag([saldiert])
    assert t2.bilanz.stundenpaarung == PAARUNG_NICHT_RECHENBAR
    assert es.SATZ_SALDIERT in es._tag_text(t2)


def test_mehrtaegiges_fenster():
    """Ein Fenster über mehrere Tage (5.11.2025: 31.10. 10 Uhr bis 5.11. 19 Uhr) — die Menge mehrerer Tage steht am
    Nachtragstag; bei Zähler-Rechnung der Satz zur Richtung über mehrere Tage."""
    lang = [_z(18, 134.3, 122.1, 63.4, 67.3, _vier(129), 52.4, 36.3)]
    text_ = es._tag_text(_tag(lang))
    assert "vom 15.6. 10 Uhr bis 20.6. 19 Uhr fehlten Stundenwerte" in text_
    assert es.SATZ_MEHRTAEGIG.format(von="15.06.2026", tag="20.06.2026") in text_ and es.SATZ_MEHRERE_TAGE in text_
    kurz = [_z(3, 4.8, 6.0, 0.0, 1.1, _vier(6), 0.0, 0.2)]          # 21 Uhr Vortag bis 4 Uhr: über Mitternacht, < 24 h
    text_ = es._tag_text(_tag(kurz))
    assert es.SATZ_MEHRTAEGIG.format(von="19.06.2026", tag="20.06.2026") in text_ and es.SATZ_MEHRERE_TAGE not in text_


# ── Lagen, Meldung, OK-Zeile ─────────────────────────────────────────────────────────────────────────────────────────

def test_tagesliste_hoechstens_zehn_und_regelmaessig():
    tage = []
    for i in range(12):
        z = [_z(13, 20.0, 8.0, 10.0, 0.5, _vier(4), 2.0, 0.5)]
        z[0].datum = date(2026, 6, 1 + i)
        b = bilanz_aus_stundenrows(z)
        tage.append(es._Tag(date(2026, 6, 1 + i), b, es._stellen_des_tages(date(2026, 6, 1 + i), z, [], b)))
    gesperrt = [_fenster(10, 2, SPERRE_HAEUFIG)] * 7 + [_fenster(21, 2, SPERRE_GROB)]
    e = es._ergebnis(tage, gesperrt)
    assert e.code == es.CODE and e.schwere.value == "info"
    assert e.meldung == "12 Tag(e) mit Stunden ohne Stundenwerte (01.06.2026 … 12.06.2026) — dazu steht die Erfassung regelmäßig still"
    assert e.details.index("12.06.2026:") < e.details.index("03.06.2026:")      # neueste zuerst
    assert "02.06.2026:" not in e.details and "… und 2 weitere Tage." in e.details
    assert es.SATZ_HAEUFIG.format(n=7) in e.details and es.SATZ_GROB.format(n=1) in e.details
    assert e.werte["regelmaessig_haeufig"] == 7 and e.werte["regelmaessig_grob"] == 1 and e.werte["tage"] == 12
    nur = es._ergebnis([], gesperrt[:1])
    assert nur.meldung == "Die Erfassung steht regelmäßig mehrere Stunden still"
    assert es.EINLEITUNG not in nur.details and es.SATZ_HAEUFIG.format(n=1) in nur.details


def test_katalog_auskunft_was_gilt():
    hg = HANDGRIFFE[es.CODE]
    assert hg.klasse == "auskunft" and hg.knopf == "Was gilt" and hg.handbuch_anker == "47-energieprofil--plausibilitaet"


# ── DB: Kanal-Tag (M07) ──────────────────────────────────────────────────────────────────────────────────────────────

from backend.services.kanal import bilanz_leser, merken  # noqa: E402
from backend.tests import kanal_bilanz_gleichheit as kg  # noqa: E402
from backend.tests.test_n799_stillstand_lesestelle import _einfrieren, _fein, _kid  # noqa: E402


@pytest.fixture
def uhr(monkeypatch):
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)
    merken.leeren()
    yield
    merken.leeren()


async def _anlage(ds):
    from sqlalchemy import select

    from backend.models.anlage import Anlage

    return (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()


async def test_ohne_fund_eine_ok_zeile(uhr):
    from backend.services.daten_checker import DatenChecker

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        (e,) = await DatenChecker(ds.db)._check_erfassung_stillstand(await _anlage(ds), heute=date(2026, 6, 30))
    assert e.code == es.CODE and e.schwere.value == "ok" and e.meldung == es.OK_MELDUNG
    assert e.knopf is None


async def test_kanal_tag_wie_die_tagestabelle(uhr):
    """Stillstand 20.06. 10–12 Uhr und eine echte Lücke (Netz/Einspeisung ohne Zeilen) am 24.06. — der Befund nennt genau
    die Tage, die ``tage-werte`` kennzeichnet, mit dem Satz zu deren Kennzeichen."""
    from backend.services.daten_checker import DatenChecker
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 6, 20, 10), 3)
        for key in ("basis:netzbezug", "basis:einspeisung"):
            await ds.db.execute(text("DELETE FROM kanal_statistik WHERE kanal_id = :k AND start_ts >= :a AND start_ts < :b"),
                                {"k": await _kid(ds, key), "a": int(datetime(2026, 6, 24, 10).timestamp()),
                                 "b": int(datetime(2026, 6, 24, 13).timestamp())})
        await ds.db.commit()
        merken.invalidiere(ds.aid)
        anlage = await _anlage(ds)
        tabelle = {z.datum: z.stundenpaarung for z in await baue_tage_werte(ds.db, anlage, date(2026, 6, 1), date(2026, 6, 30))
                   if z.stundenpaarung}
        dc = DatenChecker(ds.db)
        (e,) = await dc._check_erfassung_stillstand(anlage, heute=date(2026, 6, 30))
    assert tabelle == {date(2026, 6, 20): PAARUNG_FENSTER, date(2026, 6, 24): PAARUNG_NICHT_RECHENBAR}
    assert dc._erfassung_stillstand_tage == set(tabelle)
    assert e.schwere.value == "info" and e.meldung.startswith("2 Tag(e) mit Stunden ohne Stundenwerte (20.06.2026 … 24.06.2026)")
    assert "20.06.2026: Für die Stunden von 10 bis 14 Uhr stand die Erfassung; nachgetragen:" in e.details
    assert "24.06.2026: Für die Stunden von 10 bis 14 Uhr fehlten Stundenwerte" in e.details
    assert e.details.count(es.SATZ_FENSTER) == 1 and e.details.count(es.SATZ_UNGLEICH) == 1
    assert e.werte["stillstand_tage"] == 1 and e.werte["luecken_tage"] == 1


# ── N-567 nicht doppelt ──────────────────────────────────────────────────────────────────────────────────────────────

async def test_n567_laesst_die_tage_des_befunds_aus(db):
    """Nennt ``erfassung_stillstand`` einen Tag, erscheint N-567 dort nicht (Sprengsatz: ohne die Menge erscheint er)."""
    from backend.models import Anlage
    from backend.models.tages_energie_profil import TagesZusammenfassung
    from backend.services.daten_checker import DatenChecker

    a = Anlage(anlagenname="S3", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG, verworfen={}, nachtrag={"pv": 37.0}))
    await db.commit()
    dc = DatenChecker(db)
    assert len(await dc._check_nachtrag_nach_eingefrorenem_zaehler(a)) == 1
    dc._erfassung_stillstand_tage = {TAG}
    assert await dc._check_nachtrag_nach_eingefrorenem_zaehler(a) == []


# ── §7: Grund-Satz der Tageszeile (Mindest-Netzladung, Nulltage) ─────────────────────────────────────────────────────

def test_grund_satz_nennt_mindest_netzladung_und_vortage():
    """Die Tagestabelle zeigt die Mindest-Netzladung im Grund-Satz (der Client rechnet nichts) und nennt bei einem Fenster,
    das vor dem Tag beginnt, dass die Tage davor für diese Stunden nichts zeigen (Nulltage). Sprengsatz: ohne Begrenzung
    bzw. innerhalb des Tages fehlen beide Sätze."""
    from backend.services.energie_profil.stundenpaarung import GRUND_MEHRTAEGIG, grund_satz

    begrenzt = bilanz_aus_stundenrows([_z(13, 33.0, 10.0, 28.0, 35.0, _vier(4), 30.0, 0.0)])
    satz = grund_satz(TAG, begrenzt)
    assert "mindestens 25,0 kWh aus dem Netz geladen" in satz and GRUND_MEHRTAEGIG not in satz
    frei = bilanz_aus_stundenrows([_z(13, 20.0, 8.0, 10.0, 0.5, _vier(4), 2.0, 0.5)])
    assert "aus dem Netz geladen" not in grund_satz(TAG, frei)
    lang = bilanz_aus_stundenrows([_z(10, 30.0, 25.0, 12.0, 9.0, _vier(40), 3.0, 2.0)])
    assert grund_satz(TAG, lang).startswith("Für die Stunden vom 18.6. 19 Uhr bis 20.6. 11 Uhr")
    assert GRUND_MEHRTAEGIG in grund_satz(TAG, lang)


async def test_tagesvergleich_bereich_endet_im_fenster(uhr, monkeypatch):
    """§7: ein Bereich, der mitten in einem Fenster endet (13.06. 10 Uhr bis 16.06. 10 Uhr, Bereich bis 14.06.), lässt die
    berührten Tage aus dem Vergleich. Sprengsatz: ohne ``ueber_bis`` bleiben 13./14.06. drin (Stand Sitzung 2)."""
    from backend.services.energie_profil.vergleichstage import tage_ohne_tagesvergleich
    from backend.services.kanal import stillstand

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 6, 13, 10), 72)
        aus = await tage_ohne_tagesvergleich(ds.db, ds.aid, "pv", von=date(2026, 6, 10), bis=date(2026, 6, 14))
        voll = await tage_ohne_tagesvergleich(ds.db, ds.aid, "pv", von=date(2026, 6, 10), bis=date(2026, 6, 20))
        merken.leeren()
        echt = stillstand.erster_tag_der_fenster_ueber_mitternacht

        async def _ohne(db, aid, von, bis, **_kw):
            return await echt(db, aid, von, bis)
        monkeypatch.setattr(stillstand, "erster_tag_der_fenster_ueber_mitternacht", _ohne)
        alt = await tage_ohne_tagesvergleich(ds.db, ds.aid, "pv", von=date(2026, 6, 10), bis=date(2026, 6, 14))
    assert {date(2026, 6, 13), date(2026, 6, 14)} <= aus and max(aus) <= date(2026, 6, 14)
    assert aus == {t for t in voll if t <= date(2026, 6, 14)}                 # Bereich ≡ Ausschnitt des längeren Bereichs
    assert not {date(2026, 6, 13), date(2026, 6, 14)} <= alt



# ── K3 / K9: Grenze des Fensters, Reihenfolge, gesperrte Fenster ─────────────────────────────────────────────────────

async def test_k3_neunzig_tage_grenze(uhr):
    """K3: der Tag heute − 89 wird genannt, heute − 90 nicht (rot bei ``FENSTER_TAGE`` 365 bzw. 30)."""
    from datetime import timedelta

    from backend.services.daten_checker import DatenChecker

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 6, 20, 10), 3)
        anlage = await _anlage(ds)
        (drin,) = await DatenChecker(ds.db)._check_erfassung_stillstand(anlage, heute=TAG + timedelta(days=89))
        (raus,) = await DatenChecker(ds.db)._check_erfassung_stillstand(anlage, heute=TAG + timedelta(days=90))
    assert drin.schwere.value == "info" and "20.06.2026:" in drin.details
    assert raus.schwere.value == "ok"


async def test_k9_gesperrte_fenster_werden_gelesen(monkeypatch):
    """K9: die Lage «regelmäßig» kommt aus den gesperrten Fenstern der Lesestelle (``mit_gesperrten=True``). Sprengsatz:
    ohne den Schalter liefert die Lesestelle sie nicht ⇒ die Lage fehlt."""
    from backend.services.energie_profil import kanal_stunden
    from backend.services.kanal import stillstand

    gesperrt = [_fenster(10, 2, SPERRE_HAEUFIG)]

    async def _fenster_im_bereich(db, aid, von, bis, *, mit_gesperrten=False):
        return gesperrt if mit_gesperrten else []

    async def _keine_zeilen(*_a, **_k):
        return []

    monkeypatch.setattr(stillstand, "fenster_im_bereich", _fenster_im_bereich)
    monkeypatch.setattr(kanal_stunden, "stunden_der_tage", _keine_zeilen)
    tage, lage = await es.tage_ohne_stundenwerte(None, 1, TAG, TAG)
    assert tage == [] and lage == gesperrt


async def test_k9_reihenfolge_n567_nach_dem_befund(db, monkeypatch):
    """K9: in ``check_anlage`` läuft ``erfassung_stillstand`` vor N-567 — sonst kennt N-567 die genannten Tage noch nicht
    und nennt sie doppelt (Sprengsatz: Reihenfolge getauscht ⇒ N-567 nennt den Tag)."""
    from backend.models import Anlage
    from backend.models.tages_energie_profil import TagesZusammenfassung
    from backend.services.daten_checker import DatenChecker

    a = Anlage(anlagenname="S3 Reihenfolge", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG, verworfen={}, nachtrag={"pv": 37.0}))
    await db.commit()

    async def _nennt_den_tag(self, anlage, heute=None):
        self._erfassung_stillstand_tage = {TAG}
        return []

    monkeypatch.setattr(DatenChecker, "_check_erfassung_stillstand", _nennt_den_tag)
    codes = [e.code for e in (await DatenChecker(db).check_anlage(a.id)).ergebnisse]
    assert "nachtrag_nach_eingefrorenem_zaehler" not in codes
