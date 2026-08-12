"""Der Monatsabschluss-Cloudabruf zieht ALLE gespeicherten Quellen (N-229, #349).

Der Abruf las bis v4.0.11 genau ein gespeichertes Konto
(`connector_config["cloud_import"]`). Wer zwei Wechselrichter mit je eigener
Hersteller-„Station" betreibt — OliS2811s Fall —, bekam damit jeden Monat nur
die Hälfte seiner Erzeugung vorgeschlagen, ohne dass irgendetwas das gesagt
hätte.

Die drei Zusicherungen hier sind die, an denen sich das entscheidet:

1. beide Quellen werden abgerufen, und **jede** Zahl landet an dem Gerät, das
   ihre Quelle misst — nicht anteilig auf beiden;
2. **Hauszähler-Größen** (Netzbezug, Einspeisung) kommen nur von einer Quelle
   **ohne** Ziel; misst keine Quelle das Haus, bleibt `basis` leer **und sagt
   es** — eine Teilsumme, die wie ein Gesamtwert aussieht, ist schlimmer als
   eine fehlende Zahl (P4);
3. fällt **eine** Quelle aus, liefert die andere trotzdem — mit Hinweis.

Die Route wird direkt aufgerufen, der Provider ist eine Attrappe (gleiches
Muster wie `test_cloud_import_async_job`).
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from backend.api.routes.monatsabschluss import views as ma_views
from backend.models import Anlage, Investition
from backend.services.cloud_import.base import CloudProviderInfo
from backend.services.import_parsers.base import ParsedMonthData
from backend.services.cloud_import.quellen import setze_quelle


class _FakeProvider:
    """Antwortet je nach `station_id` in den Credentials — so lässt sich
    belegen, dass wirklich BEIDE Konten angesprochen wurden."""

    def __init__(self, je_station: dict, fehler_bei: set[str] | None = None):
        self._je_station = je_station
        self._fehler_bei = fehler_bei or set()
        self.gefragt: list[str] = []

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="fake", name="Fake", hersteller="X", beschreibung="", anleitung="",
        )

    async def fetch_monthly_data(self, creds, sy, sm, ey, em):
        station = creds.get("station_id", "?")
        self.gefragt.append(station)
        if station in self._fehler_bei:
            raise RuntimeError(f"Station {station} nicht erreichbar")
        daten = self._je_station.get(station)
        return [daten] if daten else []


async def _anlage(db, *, mit_speicher: bool = False) -> dict:
    anlage = Anlage(anlagenname="Zwei Sofar", leistung_kwp=8.0)
    db.add(anlage)
    await db.flush()

    ids: dict = {"anlage": anlage.id}
    for name, kwp in (("Sofar 2200", 5.0), ("Sofar 1100", 3.0)):
        wr = Investition(
            anlage_id=anlage.id, typ="wechselrichter", bezeichnung=name,
            anschaffungsdatum=date(2023, 1, 1),
        )
        db.add(wr)
        await db.flush()
        modul = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=f"String {name}",
            anschaffungsdatum=date(2023, 1, 1), leistung_kwp=kwp,
            parent_investition_id=wr.id,
        )
        db.add(modul)
        await db.flush()
        ids[name] = {"wr": wr.id, "modul": modul.id}
        if mit_speicher:
            sp = Investition(
                anlage_id=anlage.id, typ="speicher", bezeichnung=f"Akku {name}",
                anschaffungsdatum=date(2023, 1, 1), parent_investition_id=wr.id,
                parameter={"kapazitaet_kwh": 5.0},
            )
            db.add(sp)
            await db.flush()
            ids[name]["speicher"] = sp.id

    await db.commit()
    return ids


async def _quellen_speichern(db, ids, *, eintraege) -> None:
    """eintraege = [(station_id, ziel_investition_id oder None)]"""
    anlage = await db.get(Anlage, ids["anlage"])
    config = anlage.connector_config
    for station, ziel in eintraege:
        config = setze_quelle(
            config, provider_id="fake",
            credentials={"station_id": station}, ziel_investition_id=ziel,
        )
    anlage.connector_config = config
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(anlage, "connector_config")
    await db.commit()


def _monat(**werte) -> ParsedMonthData:
    return ParsedMonthData(jahr=2025, monat=6, **werte)


def _pv_je_inv(antwort) -> dict[int, float]:
    werte: dict[int, float] = {}
    for eintrag in antwort.investitionen:
        for feld in eintrag["felder"]:
            if feld["feld"] == "pv_erzeugung_kwh":
                werte[eintrag["investition_id"]] = feld["wert"]
    return werte


# ─── Der Kernfall ────────────────────────────────────────────────────────────


async def test_beide_stationen_werden_abgerufen_und_getrennt_zugeordnet(db, monkeypatch):
    ids = await _anlage(db)
    await _quellen_speichern(db, ids, eintraege=[
        ("111", ids["Sofar 2200"]["wr"]),
        ("222", ids["Sofar 1100"]["wr"]),
    ])

    provider = _FakeProvider({
        "111": _monat(pv_erzeugung_kwh=1000.0),
        "222": _monat(pv_erzeugung_kwh=600.0),
    })
    monkeypatch.setattr(
        "backend.services.cloud_import.get_provider", lambda _id: provider
    )

    antwort = await ma_views.fetch_cloud_monatswerte(
        anlage_id=ids["anlage"], jahr=2025, monat=6, db=db,
    )

    assert sorted(provider.gefragt) == ["111", "222"], "Beide Konten angesprochen."
    assert _pv_je_inv(antwort) == {
        ids["Sofar 2200"]["modul"]: 1000.0,
        ids["Sofar 1100"]["modul"]: 600.0,
    }

    # Kein Wert ist eine Zerlegung — jede Zahl ist die Messung ihrer Station.
    for eintrag in antwort.investitionen:
        for feld in eintrag["felder"]:
            assert feld["abgeleitet"] is None, feld


async def test_stationen_liefern_die_hauszaehler_werte_und_melden_abweichung(
    db, monkeypatch
):
    """Auch ohne eigene „Haus"-Quelle bekommt der Monatsabschluss Vorschläge.

    ⚠ **Dieser Test stand bis 2026-08-12 auf dem Kopf** (`..._bleibt_basis_leer`,
    Zusicherung `antwort.basis == []`) — begründet mit „ein Stations-Netzbezug
    ist kein Hauszähler-Wert". Ein Wechselrichter *misst* Netzbezug und
    Einspeisung aber gar nicht: er liest den Zähler am Hausanschluss. Der Wert
    einer Station IST der Hauszähler-Wert (Gernot, 12.08.). Wer wie der Melder
    ausschließlich zugeordnete Stationen führt, bekam sonst nie einen Vorschlag
    und stand ohne Monatsabschluss da (#349).

    Die beiden Quellen hier melden **verschiedene** Einspeisungen (700 gegen
    300) — das darf nicht still entschieden werden.
    """
    ids = await _anlage(db)
    await _quellen_speichern(db, ids, eintraege=[
        ("111", ids["Sofar 2200"]["wr"]),
        ("222", ids["Sofar 1100"]["wr"]),
    ])

    provider = _FakeProvider({
        "111": _monat(pv_erzeugung_kwh=1000.0, netzbezug_kwh=400.0, einspeisung_kwh=700.0),
        "222": _monat(pv_erzeugung_kwh=600.0, netzbezug_kwh=400.0, einspeisung_kwh=300.0),
    })
    monkeypatch.setattr(
        "backend.services.cloud_import.get_provider", lambda _id: provider
    )

    antwort = await ma_views.fetch_cloud_monatswerte(
        anlage_id=ids["anlage"], jahr=2025, monat=6, db=db,
    )

    werte = {f.feld: f.wert for f in antwort.basis}
    assert werte == {"einspeisung_kwh": 700.0, "netzbezug_kwh": 400.0}, (
        "Die Stationswerte erreichen den Monatsabschluss nicht — Ollis Symptom."
    )
    # 700 + 300 wären 1000: der Hausanschluss hat aber nur einmal eingespeist.
    assert werte["einspeisung_kwh"] != 1000.0, "Die Quellen wurden summiert."
    assert any("Zähler" in h for h in antwort.hinweise), antwort.hinweise


async def test_quelle_ohne_ziel_liefert_die_hauszaehler_werte(db, monkeypatch):
    """Gemischter Aufbau: eine Quelle misst das Haus, eine nur ein Gerät."""
    ids = await _anlage(db)
    await _quellen_speichern(db, ids, eintraege=[
        ("haus", None),
        ("222", ids["Sofar 1100"]["wr"]),
    ])

    provider = _FakeProvider({
        "haus": _monat(netzbezug_kwh=400.0, einspeisung_kwh=700.0),
        "222": _monat(pv_erzeugung_kwh=600.0),
    })
    monkeypatch.setattr(
        "backend.services.cloud_import.get_provider", lambda _id: provider
    )

    antwort = await ma_views.fetch_cloud_monatswerte(
        anlage_id=ids["anlage"], jahr=2025, monat=6, db=db,
    )

    assert {f.feld: f.wert for f in antwort.basis} == {
        "netzbezug_kwh": 400.0, "einspeisung_kwh": 700.0,
    }
    assert _pv_je_inv(antwort) == {ids["Sofar 1100"]["modul"]: 600.0}


async def test_speicherwerte_gehen_an_den_speicher_der_quelle(db, monkeypatch):
    ids = await _anlage(db, mit_speicher=True)
    await _quellen_speichern(db, ids, eintraege=[
        ("111", ids["Sofar 2200"]["wr"]),
        ("222", ids["Sofar 1100"]["wr"]),
    ])

    provider = _FakeProvider({
        "111": _monat(pv_erzeugung_kwh=1000.0, batterie_ladung_kwh=300.0),
        "222": _monat(pv_erzeugung_kwh=600.0),
    })
    monkeypatch.setattr(
        "backend.services.cloud_import.get_provider", lambda _id: provider
    )

    antwort = await ma_views.fetch_cloud_monatswerte(
        anlage_id=ids["anlage"], jahr=2025, monat=6, db=db,
    )

    ladung = {
        e["investition_id"]: f["wert"]
        for e in antwort.investitionen for f in e["felder"]
        if f["feld"] == "ladung_kwh"
    }
    assert ladung == {ids["Sofar 2200"]["speicher"]: 300.0}


# ─── Teilausfall ─────────────────────────────────────────────────────────────


async def test_eine_quelle_faellt_aus_die_andere_liefert_trotzdem(db, monkeypatch):
    """Ein Ausfall darf die andere Station nicht mitreißen — aber er darf auch
    nicht verschwiegen werden, sonst sieht die Hälfte wie das Ganze aus (P4)."""
    ids = await _anlage(db)
    await _quellen_speichern(db, ids, eintraege=[
        ("111", ids["Sofar 2200"]["wr"]),
        ("222", ids["Sofar 1100"]["wr"]),
    ])

    provider = _FakeProvider(
        {"111": _monat(pv_erzeugung_kwh=1000.0)}, fehler_bei={"222"},
    )
    monkeypatch.setattr(
        "backend.services.cloud_import.get_provider", lambda _id: provider
    )

    antwort = await ma_views.fetch_cloud_monatswerte(
        anlage_id=ids["anlage"], jahr=2025, monat=6, db=db,
    )

    assert _pv_je_inv(antwort) == {ids["Sofar 2200"]["modul"]: 1000.0}
    assert any("nicht erreichbar" in h for h in antwort.hinweise), antwort.hinweise
    assert any("Sofar 1100" in h for h in antwort.hinweise), antwort.hinweise


async def test_alle_quellen_gescheitert_ist_ein_fehler(db, monkeypatch):
    ids = await _anlage(db)
    await _quellen_speichern(db, ids, eintraege=[("111", ids["Sofar 2200"]["wr"])])

    provider = _FakeProvider({}, fehler_bei={"111"})
    monkeypatch.setattr(
        "backend.services.cloud_import.get_provider", lambda _id: provider
    )

    with pytest.raises(HTTPException) as exc:
        await ma_views.fetch_cloud_monatswerte(
            anlage_id=ids["anlage"], jahr=2025, monat=6, db=db,
        )
    assert exc.value.status_code == 400
    assert "nicht erreichbar" in exc.value.detail


async def test_altbestand_eine_quelle_ohne_ziel_rechnet_wie_bisher(db, monkeypatch):
    """Die alte Ein-Objekt-Form: EIN Anlagen-Gesamtwert, nach kWp auf beide
    Stränge zerlegt und als zerlegt gekennzeichnet. Unverändertes Verhalten."""
    ids = await _anlage(db)
    anlage = await db.get(Anlage, ids["anlage"])
    anlage.connector_config = {
        "cloud_import": {"provider_id": "fake", "credentials": {"station_id": "alt"}}
    }
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(anlage, "connector_config")
    await db.commit()

    provider = _FakeProvider({"alt": _monat(pv_erzeugung_kwh=1600.0, netzbezug_kwh=400.0)})
    monkeypatch.setattr(
        "backend.services.cloud_import.get_provider", lambda _id: provider
    )

    antwort = await ma_views.fetch_cloud_monatswerte(
        anlage_id=ids["anlage"], jahr=2025, monat=6, db=db,
    )

    # 5 kWp / 3 kWp ⇒ 1000 / 600
    assert _pv_je_inv(antwort) == {
        ids["Sofar 2200"]["modul"]: 1000.0,
        ids["Sofar 1100"]["modul"]: 600.0,
    }
    assert {f.feld for f in antwort.basis} == {"netzbezug_kwh"}
    assert all(
        f["abgeleitet"] is not None
        for e in antwort.investitionen for f in e["felder"]
    ), "Der zerlegte Wert muss als zerlegt gekennzeichnet bleiben (#352)."
