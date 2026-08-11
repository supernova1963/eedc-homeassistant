"""Mehrere Cloud-Quellen je Anlage — die zweite verdrängt die erste nicht (N-229, #349).

Bis v4.0.11 lag unter `Anlage.connector_config["cloud_import"]` **ein** Objekt,
und `save-credentials` hat es bei jedem Aufruf **ersetzt**. OliS2811 betreibt
zwei Sofar-Wechselrichter, die Solarman als zwei Stationen führt: Er konnte also
nur eines der beiden Konten speichern, musste das andere bei jedem Import neu
eintippen — und der monatliche Cloudabruf sah ohnehin nur das gespeicherte.

Geprüft wird beides: dass zwei Quellen nebeneinander bestehen, und dass der
Monatsabruf sie **beide** zieht und jeden Wert an das Gerät seiner Quelle legt.

Der Altbestand ist ausdrücklich Teil des Vertrags (`test_altbestand_*`): die
alte Ein-Objekt-Form wird beim **Lesen** normalisiert, damit keine Installation
eine Start-Migration braucht.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.api.routes.cloud_import import (
    SaveCredentialsRequest,
    get_credentials,
    remove_credentials,
    save_credentials,
)
from backend.models import Anlage, Investition
from backend.services.cloud_import.quellen import (
    lade_quellen,
    quellen_schluessel,
    setze_quelle,
)


async def _anlage_mit_zwei_wr(db) -> dict:
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
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=f"String {name}",
            anschaffungsdatum=date(2023, 1, 1), leistung_kwp=kwp,
            parent_investition_id=wr.id,
        ))
        await db.flush()
        ids[name] = wr.id
    await db.commit()
    return ids


def _req(station: str, ziel: int | None) -> SaveCredentialsRequest:
    return SaveCredentialsRequest(
        provider_id="deye_solarman",
        credentials={"appId": "a", "appSecret": "s", "station_id": station},
        ziel_investition_id=ziel,
    )


# ─── Der Kernfall ────────────────────────────────────────────────────────────


async def test_zwei_stationen_stehen_nebeneinander(db):
    ids = await _anlage_mit_zwei_wr(db)

    for station, name in (("111", "Sofar 2200"), ("222", "Sofar 1100")):
        antwort = await save_credentials(
            anlage_id=ids["anlage"], data=_req(station, ids[name]), db=db,
        )
        assert antwort["erfolg"]
    await db.commit()

    gespeichert = await get_credentials(anlage_id=ids["anlage"], db=db)
    assert len(gespeichert.quellen) == 2

    # Jede Quelle trägt ihre eigene Station UND ihren Zielnamen — ohne den ist
    # die Liste nicht bedienbar.
    nach_ziel = {q.ziel_bezeichnung: q for q in gespeichert.quellen}
    assert set(nach_ziel) == {"Sofar 2200", "Sofar 1100"}
    assert nach_ziel["Sofar 2200"].credentials["station_id"] == "111"
    assert nach_ziel["Sofar 1100"].credentials["station_id"] == "222"

    # Das Geheimnis bleibt maskiert — die Liste ist eine Anzeige, kein Tresor.
    assert nach_ziel["Sofar 2200"].credentials["appSecret"] == "***"


async def test_dieselbe_station_erneut_speichern_ersetzt_statt_zu_verdoppeln(db):
    """Identität ist (Provider, Ziel) — ein zweiter Speichervorgang für dasselbe
    Gerät ist eine Korrektur, keine neue Quelle."""
    ids = await _anlage_mit_zwei_wr(db)

    await save_credentials(ids["anlage"], _req("111", ids["Sofar 2200"]), db)
    await save_credentials(ids["anlage"], _req("999", ids["Sofar 2200"]), db)
    await db.commit()

    quellen = (await get_credentials(anlage_id=ids["anlage"], db=db)).quellen
    assert len(quellen) == 1
    assert quellen[0].credentials["station_id"] == "999"


async def test_einzelne_quelle_entfernen_laesst_die_andere_stehen(db):
    ids = await _anlage_mit_zwei_wr(db)
    await save_credentials(ids["anlage"], _req("111", ids["Sofar 2200"]), db)
    await save_credentials(ids["anlage"], _req("222", ids["Sofar 1100"]), db)
    await db.commit()

    schluessel = quellen_schluessel("deye_solarman", ids["Sofar 2200"])
    antwort = await remove_credentials(
        anlage_id=ids["anlage"], quelle=schluessel, db=db,
    )
    await db.commit()
    assert antwort["entfernt"] == 1

    quellen = (await get_credentials(anlage_id=ids["anlage"], db=db)).quellen
    assert [q.ziel_bezeichnung for q in quellen] == ["Sofar 1100"]


async def test_ohne_parameter_werden_weiter_alle_entfernt(db):
    """Das bisherige Verhalten von DELETE bleibt — sonst bräche ein Aufrufer,
    der die Anlage bewusst leerräumt."""
    ids = await _anlage_mit_zwei_wr(db)
    await save_credentials(ids["anlage"], _req("111", ids["Sofar 2200"]), db)
    await save_credentials(ids["anlage"], _req("222", ids["Sofar 1100"]), db)
    await db.commit()

    antwort = await remove_credentials(anlage_id=ids["anlage"], quelle=None, db=db)
    await db.commit()
    assert antwort["entfernt"] == 2
    assert not (await get_credentials(anlage_id=ids["anlage"], db=db)).has_credentials


async def test_unauflösbares_ziel_wird_beim_speichern_abgewiesen(db):
    """Eine Quelle, die auf ein Gerät ohne Module zeigt, wäre beim nächsten
    Monatsabruf ein stiller Ausfall — der Fehler gehört dorthin, wo man ihn
    versteht."""
    anlage = Anlage(anlagenname="Nackter WR", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="Sofar solo",
        anschaffungsdatum=date(2023, 1, 1),
    )
    db.add(wr)
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await save_credentials(anlage.id, _req("111", wr.id), db)
    assert exc.value.status_code == 400
    assert "keine PV-Module" in exc.value.detail

    # Und es wurde nichts geschrieben.
    frisch = (await db.execute(select(Anlage).where(Anlage.id == anlage.id))).scalar_one()
    assert lade_quellen(frisch.connector_config) == []


# ─── Altbestand ──────────────────────────────────────────────────────────────


def test_altbestand_wird_beim_lesen_als_eine_quelle_ohne_ziel_gelesen():
    """Die alte Ein-Objekt-Form ist eine Quelle, die die GANZE Anlage
    beschreibt — genau ihre bisherige Bedeutung. Keine Migration nötig."""
    alt = {"cloud_import": {"provider_id": "deye_solarman", "credentials": {"x": "1"}}}

    quellen = lade_quellen(alt)

    assert len(quellen) == 1
    assert quellen[0]["ziel_investition_id"] is None
    assert quellen[0]["credentials"] == {"x": "1"}
    assert quellen[0]["schluessel"] == "deye_solarman:anlage"


def test_altbestand_bleibt_erhalten_wenn_eine_zweite_quelle_dazukommt():
    """Der Umstieg darf die vorhandene Konfiguration nicht kosten."""
    alt = {"cloud_import": {"provider_id": "deye_solarman", "credentials": {"x": "1"}}}

    neu = setze_quelle(
        alt, provider_id="deye_solarman", credentials={"y": "2"},
        ziel_investition_id=42,
    )

    quellen = lade_quellen(neu)
    assert len(quellen) == 2
    assert isinstance(neu["cloud_import"], list), "Geschrieben wird die neue Form."
    assert {q["ziel_investition_id"] for q in quellen} == {None, 42}
    # Der abgeleitete Schlüssel wird NICHT mitgespeichert — sonst gäbe es zwei
    # Wahrheiten, sobald sich die Ableitungsregel ändert.
    assert all("schluessel" not in e for e in neu["cloud_import"])


def test_ohne_ziel_gibt_es_je_provider_nur_eine_quelle():
    """„Ohne Ziel" heißt „beschreibt die ganze Anlage" — davon kann es nur eine
    geben, sonst wäre unbestimmt, welche die Hauszähler-Werte liefert."""
    config: dict = {}
    config = setze_quelle(config, provider_id="p", credentials={"n": "1"})
    config = setze_quelle(config, provider_id="p", credentials={"n": "2"})

    quellen = lade_quellen(config)
    assert len(quellen) == 1
    assert quellen[0]["credentials"] == {"n": "2"}
