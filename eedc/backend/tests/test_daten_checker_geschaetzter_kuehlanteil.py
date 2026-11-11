"""Daten-Checker: der Kühlanteil wird geschätzt, und niemand sagte es (WK-06).

## Warum diese Datei nötig ist

Eine Wärmepumpe mit **getrennter Strommessung** (F5: eigene Zähler für Heizen
und Warmwasser) **plus** einem Betriebsmodus-Sensor teilt ihren Strom aus dem
Modus auf. Für den **Kühlbetrieb** gibt es dabei keinen eigenen Zähler — eedc
verteilt den vorhandenen Gesamtstrom, es liest ihn nicht ab.

Seit **SOLL-§9-E7/Option A** (12.09.2026) hat das eine sichtbare Folge: Der so
geschätzte Kühlanteil kürzt den Nenner der Arbeitszahl **nicht** mehr
(*abgezogen wird nur, was im Nenner steht*). Dieselbe Anlage **mit** Kühlzähler
zeigt dieselbe Zahl — vorher war sie ohne Zähler 12 % besser.

⭐ **Der Anwender muss das erfahren, und zwar mit dem Handgriff daneben**
(`[[feedback_eedc_rechnet_voraussetzungen_handgriff]]`): *Ordne „Strom
Kühlbetrieb" zu, dann liest eedc ab, statt zu verteilen.* Bis dahin meldete die
Kategorie `KLIMA_MODUS_SENSOR` für genau diese Anlagen **„Betriebsmodus ist
zugeordnet — OK"** und schwieg über die Schätzung daneben.

⛔ **Kein zweiter Turm** (N-346): derselbe Check, dieselbe Kategorie, ein
zusätzlicher INFO-Befund. Keine neue `CheckKategorie`.

## Die vier Klauseln, und warum jede ihre eigene Probe hat

Die Bedingung ist eine Konjunktion. Ein grüner Lauf beweist nur dann etwas,
wenn **jede** Klausel allein rot melden kann — sonst wäre eine zu breite
Fassung (die etwa jede kühlende Anlage meldet) ebenso grün.

| Klausel | Gegenprobe |
| --- | --- |
| getrennte Strommessung (F5) | `test_ohne_getrennte_strommessung_schweigt_er` |
| abgeleiteter Split (Abdeckung > 0) | `test_ohne_modus_abdeckung_schweigt_er` · `test_ein_kuehlwert_ohne_abdeckung_ist_keine_aufteilung` |
| Kühlanteil > 0 | `test_ohne_kuehlanteil_schweigt_er` |
| kein Kühl-**Zähler** zugeordnet | `test_mit_gemessenem_kuehlzaehler_schweigt_er` · `test_mit_zugeordnetem_kuehlzaehler_schweigt_er` |

Schwesterdateien: `test_n445_kuehlstrom_im_f5_heizstrom.py` (die Rechnung, die
dieser Hinweis erklärt) und `test_daten_checker_modus_quelle_mehrdeutig.py`
(dieselbe Bauform, dieselbe Kategorie).
"""

from __future__ import annotations

from backend.tests.werkzeug_befund import befund_link
from datetime import date

from backend.models import Anlage, Investition
from backend.services.daten_checker import CheckKategorie, DatenChecker
from backend.models.investition import InvestitionMonatsdaten


#: F5 + abgeleiteter Split mit Kühlanteil — die Zeile aus der WK-06-Fixture.
ZEILE_F5_ABGELEITET = {
    "strom_heizen_kwh": 750.0,
    "strom_warmwasser_kwh": 200.0,
    "heizenergie_kwh": 3000.0,
    "warmwasser_kwh": 600.0,
    "modus_strom_heizen_kwh": 700.0,
    "modus_strom_warmwasser_kwh": 150.0,
    "modus_strom_kuehlen_kwh": 100.0,
    "modus_abdeckung_h": 700.0,
}


async def _anlage(
    db, verbrauch_daten: dict, *, parameter: dict | None = None,
    mapping: dict | None = None,
) -> Anlage:
    anlage = Anlage(anlagenname="W", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Wärmepumpe",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=20000.0,
        parameter=parameter if parameter is not None
        else {"getrennte_strommessung": True},
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=2,
        verbrauch_daten=verbrauch_daten,
    ))
    if mapping is not None:
        anlage.sensor_mapping = {"investitionen": {str(inv.id): mapping}}
    await db.commit()
    return anlage


async def _befunde(db, anlage):
    return await DatenChecker(db=db)._check_klima_modus_sensor(anlage)


def _geschaetzt(befunde):
    return [b for b in befunde if "geschätzt" in b.meldung]


# ── Der Befund selbst ──────────────────────────────────────────────────────


async def test_der_geschaetzte_kuehlanteil_wird_gemeldet(db):
    """**Der Fund**: F5 + Betriebsmodus, kein Kühlzähler ⇒ ein INFO-Hinweis.

    Bis zum 12.09.2026 meldete diese Anlage ausschließlich „Betriebsmodus ist
    zugeordnet — OK". Dass daneben eine Größe geschätzt wird, stand nirgends.
    """
    anlage = await _anlage(db, ZEILE_F5_ABGELEITET)
    treffer = _geschaetzt(await _befunde(db, anlage))

    assert len(treffer) == 1
    b = treffer[0]
    assert b.kategorie == CheckKategorie.KLIMA_MODUS_SENSOR.value
    assert b.schwere == "info"
    assert "Wärmepumpe" in b.meldung
    assert "Stromzähler für den Kühlbetrieb" in b.meldung


async def test_der_hinweis_traegt_den_handgriff_und_keinen_akzeptiert_knopf(db):
    """Was eedc rechnet · was es voraussetzt · was zu tun ist.

    ⛔ Kein „Akzeptiert" (`[[feedback_daten_checker_kein_akzeptiert]]`) — der
    Fall hat einen Weg, und der steht im Text.
    """
    anlage = await _anlage(db, ZEILE_F5_ABGELEITET)
    b = _geschaetzt(await _befunde(db, anlage))[0]

    assert "schätzen" in b.details            # was eedc rechnet
    assert "Strom Kühlbetrieb" in b.details   # der Handgriff
    assert befund_link(b).endswith("&feld=betriebsart_strom_kuehlen_kwh")  # E4: der Knopf ist der Weg, kein Menüweg im Text
    assert "Mengen stimmen weiterhin" in b.details  # was sich NICHT ändert (K1)
    assert befund_link(b)


async def test_er_steht_neben_der_ok_meldung_nicht_statt_ihrer(db):
    """Beide Aussagen sind wahr: der Modus **ist** zugeordnet, und trotzdem
    wird geschätzt. Der Hinweis verdrängt die OK-Meldung nicht.
    """
    anlage = await _anlage(
        db, ZEILE_F5_ABGELEITET,
        parameter={"getrennte_strommessung": True, "wp_art": "luft_luft"},
        mapping={"live": {"betriebsmodus": "climate.wp"}},
    )
    befunde = await _befunde(db, anlage)

    assert len(_geschaetzt(befunde)) == 1
    assert any(b.schwere == "ok" for b in befunde), (
        "Die bestehende Auskunft muss stehen bleiben — sie ist nicht falsch."
    )


# ── Klausel 1: getrennte Strommessung ──────────────────────────────────────


async def test_ohne_getrennte_strommessung_schweigt_er(db):
    """**Der W-14-Fall bleibt unberührt.**

    Ohne F5 ist der Nenner der Zählerstand des ganzen Geräts — der Kühlbetrieb
    steckt darin, der Abzug ist richtig, und es gibt nichts zu erklären. Ein
    Hinweis hier wäre die P-6-Falle: ein Weg ohne Wirkung.
    """
    anlage = await _anlage(
        db,
        {
            "stromverbrauch_kwh": 1050.0, "heizenergie_kwh": 3000.0,
            "modus_strom_heizen_kwh": 800.0, "modus_strom_kuehlen_kwh": 100.0,
            "modus_abdeckung_h": 700.0,
        },
        parameter={},
    )
    assert _geschaetzt(await _befunde(db, anlage)) == []


# ── Klausel 2: abgeleiteter Split vorhanden ────────────────────────────────


async def test_ohne_modus_abdeckung_schweigt_er(db):
    """Kein Betriebsmodus-Sensor ⇒ keine Aufteilung ⇒ nichts zu schätzen.

    Diese Anlage bekommt den **anderen** Hinweis („Betriebsmodus nicht
    zugeordnet"), sofern sie überhaupt als kühlfähig erkannt wird — aber nicht
    diesen.
    """
    ohne_modus = {
        k: v for k, v in ZEILE_F5_ABGELEITET.items()
        if not k.startswith("modus_")
    }
    anlage = await _anlage(db, ohne_modus)
    assert _geschaetzt(await _befunde(db, anlage)) == []


async def test_ein_kuehlwert_ohne_abdeckung_ist_keine_aufteilung(db):
    """**Die Klausel „Abdeckung > 0" braucht eine eigene Probe.**

    ⭐ Gemessen am 12.09.2026: Der Sprengsatz „Abdeckungs-Klausel streichen"
    blieb **still**, weil die Probe darüber alle `modus_*`-Schlüssel entfernt
    und damit schon an der Kühlanteil-Klausel hängen bleibt. Ein Prüfer, dessen
    Klausel keine eigene Probe trägt, ist an dieser Stelle ungedeckt.

    Die Lage hier: ein Kühlwert **ohne** Abdeckungs-Stunden. Für eedc ist das
    keine Aufteilung (`ModusStromZeile.hat_aufteilung` — „gemessen oder
    Abdeckung > 0"), der Wert wird nirgends angewandt, und es wird nichts
    geschätzt. Erreichbar an Altmonaten und handgepflegten Zeilen, in denen die
    Abdeckung fehlt.
    """
    ohne_abdeckung = {**ZEILE_F5_ABGELEITET, "modus_abdeckung_h": 0.0}
    anlage = await _anlage(db, ohne_abdeckung)
    assert _geschaetzt(await _befunde(db, anlage)) == []


# ── Klausel 3: es gibt überhaupt einen Kühlanteil ──────────────────────────


async def test_ohne_kuehlanteil_schweigt_er(db):
    """Eine reine Heizanlage mit Modus-Sensor hat nichts zu schätzen.

    ⭐ Ohne diese Gegenprobe wäre auch eine Fassung grün, die **jede** F5-Anlage
    mit Betriebsmodus meldet — die Mehrheit, und für sie wäre der Text falsch.
    """
    ohne_kuehlen = {**ZEILE_F5_ABGELEITET, "modus_strom_kuehlen_kwh": 0.0,
                    "modus_strom_heizen_kwh": 800.0}
    anlage = await _anlage(db, ohne_kuehlen)
    assert _geschaetzt(await _befunde(db, anlage)) == []


# ── Klausel 4: kein Kühl-ZÄHLER ────────────────────────────────────────────


async def test_mit_gemessenem_kuehlzaehler_schweigt_er(db):
    """**MartyBrs Bauform (F5 + F4).** Hier wird nichts geschätzt.

    Der gemessene Zähler verdrängt den abgeleiteten Split ganz (K2), und der
    Abzug bleibt voll (W-16b). Ein Hinweis wäre schlicht falsch.
    """
    mit_f4 = {
        "strom_heizen_kwh": 750.0, "strom_warmwasser_kwh": 200.0,
        "heizenergie_kwh": 3000.0, "warmwasser_kwh": 600.0,
        "betriebsart_strom_kuehlen_kwh": 100.0,
        "modus_abdeckung_h": 700.0,
    }
    anlage = await _anlage(db, mit_f4)
    assert _geschaetzt(await _befunde(db, anlage)) == []


async def test_mit_zugeordnetem_kuehlzaehler_schweigt_er(db):
    """**Zugeordnet, aber noch keine Zahl** — auch das ist kein Fall.

    Wer den Zähler gerade eingerichtet hat, hat den Handgriff getan; ihm zu
    sagen „ordne ihn zu" wäre die Meldung, die in die Irre führt (N-340-Lehre).
    Die Zeile trägt weiter einen abgeleiteten Split aus der Zeit davor.
    """
    anlage = await _anlage(
        db, ZEILE_F5_ABGELEITET,
        mapping={"felder": {"betriebsart_strom_kuehlen_kwh": {
            "strategie": "sensor", "sensor_id": "sensor.kuehlstrom",
        }}},
    )
    assert _geschaetzt(await _befunde(db, anlage)) == []


async def test_eine_kaeltemenge_allein_loest_den_fall_nicht_auf(db):
    """**Enger als `_hat_kuehl_spur`, und das ist der Punkt.**

    Eine gemessene **Kältemenge** ist kein Stromzähler — der Kühl*strom* wird
    weiter geschätzt. Wer die Klausel an der breiteren Kühl-Spur festmachte,
    schwiege ausgerechnet gegenüber dem, der schon halb eingerichtet hat.
    """
    mit_kaelte = {**ZEILE_F5_ABGELEITET, "betriebsart_nutzenergie_kuehlen_kwh": 400.0}
    anlage = await _anlage(db, mit_kaelte)
    assert len(_geschaetzt(await _befunde(db, anlage))) == 1
