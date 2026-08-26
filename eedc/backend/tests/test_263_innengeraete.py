"""#263: Innengeräte einer Split-Klimaanlage — Felder, Zuordnung, Vorrang.

**Die Fassung, die hier gewächtert wird** (Entscheid Gernots, 2026-08-21):
Eine Split-Klimaanlage kann ihren Verbrauch je Betriebsart **gemessen**
mitbringen — am Gerät oder je Innengerät —, statt ihn eedc aus dem
Betriebsmodus ableiten zu lassen. Der Betriebsmodus selbst bleibt **ein**
Signal je Gerät und unverändert; es gibt keine Faltung über mehrere Modus-
Signale.

**Die Proben zielen auf die ROUTE bzw. den Endpunkt, nicht auf den Layer
allein.** Der Layer wäre in mehreren dieser Fälle grün gewesen, ohne dass ein
Anwender etwas gesehen hätte — genau der Fehler, an dem der `hvac_action`-
Wächter gescheitert ist (Konzept §6).

Konzept: `docs/KONZEPT-263-INNENGERAETE.md`.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.betriebsmodus import (
    BETRIEBSART_NUTZENERGIE_FELD,
    BETRIEBSART_STROM_FELD,
    HEIZEN,
    KUEHLEN,
    MESSBARE_MODI,
    MODUS_ABDECKUNG_FELD,
    MODUS_STROM_FELD,
)
from backend.core.field_definitions import (
    INVESTITION_FELDER,
    LIVE_FELDER_INV,
    basis_feld_key,
    feld_je_innengeraet,
    get_alle_felder_fuer_investition,
    get_live_felder_fuer_investition,
    innengeraet_id_von_feld,
    ist_zustand_feld,
)
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.investition import InvestitionMonatsdaten  # noqa: F401
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)

LUFT_LUFT = {"wp_art": "luft_luft"}
MIT_LISTE = {
    "wp_art": "luft_luft",
    "innengeraete": [
        {"id": 1, "bezeichnung": "Büro"},
        {"id": 3, "bezeichnung": "Wohnzimmer"},
    ],
}


# ─── Der Trenner und seine Auflösung ────────────────────────────────────────

def test_kein_registry_feld_traegt_einen_bindestrich():
    """Der Negativbeweis für den Suffix-Trenner (`-`).

    Die ganze Mechanik hängt daran, dass `basis_feld_key` einen Bindestrich am
    Ende eindeutig als Innengeräte-Adresse lesen darf. Trüge irgendein
    Registry-Feld selbst einen, würde es still zu einem anderen Feld aufgelöst.
    """
    keys: set[str] = set()
    for felder in INVESTITION_FELDER.values():
        listen = list(felder.values()) if isinstance(felder, dict) else [felder]
        for liste in listen:
            keys |= {f["feld"] for f in liste}
    for liste in LIVE_FELDER_INV.values():
        keys |= {f["key"] for f in liste}

    assert keys, "Registry leer — die Probe misst nichts"
    mit_strich = sorted(k for k in keys if "-" in k)
    assert mit_strich == [], (
        "Ein Feld-Key mit Bindestrich macht die Innengeräte-Adresse mehrdeutig: "
        f"{mit_strich}"
    )


@pytest.mark.parametrize("roh,basis,gid", [
    ("betriebsmodus-3", "betriebsmodus", 3),
    ("betriebsart_strom_kuehlen_kwh-11", "betriebsart_strom_kuehlen_kwh", 11),
    ("stromverbrauch_kwh", "stromverbrauch_kwh", None),
    ("", "", None),
])
def test_basis_feld_key_und_id(roh, basis, gid):
    assert basis_feld_key(roh) == basis
    assert innengeraet_id_von_feld(roh) == gid


# ─── Die Felder entstehen aus dem Parameter ─────────────────────────────────

def test_ohne_liste_stehen_die_betriebsart_felder_am_geraet():
    felder = {f["feld"] for f in get_alle_felder_fuer_investition("waermepumpe", LUFT_LUFT)}
    for modus in MESSBARE_MODI:
        assert BETRIEBSART_STROM_FELD[modus] in felder
        assert BETRIEBSART_NUTZENERGIE_FELD[modus] in felder
    assert not any("-" in f for f in felder), "ohne Liste darf es keine Adressen geben"


def test_mit_liste_kommen_die_felder_je_innengeraet_dazu():
    felder = {f["feld"] for f in get_alle_felder_fuer_investition("waermepumpe", MIT_LISTE)}
    for gid in (1, 3):
        assert feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], gid) in felder
    # Das Gerätefeld bleibt stehen — sonst verschwände eine bestehende
    # Zuordnung unsichtbar, sobald jemand ein Innengerät anlegt.
    assert BETRIEBSART_STROM_FELD[KUEHLEN] in felder
    # ID 2 gibt es nicht (gelöscht) — sie darf auch nicht auftauchen.
    assert feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 2) not in felder


def test_das_label_je_innengeraet_traegt_den_raumnamen():
    felder = {f["key"]: f["label"]
              for f in get_live_felder_fuer_investition("waermepumpe", MIT_LISTE)}
    assert felder[feld_je_innengeraet("ist_temperatur_c", 1)] == "Büro: Raumtemperatur"
    assert felder[feld_je_innengeraet("leistung_w", 3)] == "Wohnzimmer: Leistung"


def test_der_betriebsmodus_bleibt_ein_signal_je_geraet():
    """Kein Modus je Innengerät — das ist der Kern der Fassung 2026-08-21.

    Der abgeleitete Split liest genau **eine** `climate`-Entität je Gerät. Gäbe
    es den Modus je Innengerät, müsste irgendjemand n Signale zu einem falten —
    und genau diese Faltung ist gestrichen.
    """
    keys = {f["key"] for f in get_live_felder_fuer_investition("waermepumpe", MIT_LISTE)}
    assert "betriebsmodus" in keys
    assert feld_je_innengeraet("betriebsmodus", 1) not in keys


def test_luft_wasser_stellt_die_betriebsarten_hintan():
    """Eine klassische Wärmepumpe sieht die Betriebsart-Felder **in der zweiten
    Reihe** — nicht mehr gar nicht.

    ⛔ **Diese Probe hieß bis zum 26.08.2026 `test_luft_wasser_bleibt_bitgleich`
    und forderte das Gegenteil:** *„acht Betriebsart-Felder an einer
    Luft-Wasser-Wärmepumpe wären acht Angebote, die niemand einlösen kann."*
    Der Satz stimmt weiter — er trifft nur nicht mehr die richtige Antwort.

    **Melder MartyBr** (T89667 #200, 25.08.): *„Ich habe getrennte Zähler für
    Heizung, Warmwassererwärmung … und seit dem Sommer auch für den
    Kühlbetrieb."* **pipp086** (#199) fragt nach derselben Größe. Seine Anlage
    ist keine Klimaanlage — sein Kühlzähler hatte nirgends einen Platz.

    ⭐ **R1 (SOLL §3.2a) löst die P-6-Falle anders ein:** nicht durch Wegnehmen
    nach Bauart, sondern durch Sichtbarkeit nach Beleglage. Die Felder sind
    `erweitert` markiert und stehen hinter „Weitere Größen erfassen"; die Fläche
    bleibt kurz, **und kein Fall ist ausgeschlossen**.

    ⚠ **Die Raumtemperatur-Felder bleiben hart** — sie sind keine Größe des
    Geräts, sondern die eines Innengeräts. Die Trennlinie verläuft nicht
    zwischen „Bauart" und „kein Filter", sondern zwischen *untypisch* und
    *existiert nicht*.
    """
    energie = {f["feld"]: bool(f.get("erweitert"))
               for f in get_alle_felder_fuer_investition(
                   "waermepumpe", {"wp_art": "luft_wasser"})}
    live = {f["key"] for f in get_live_felder_fuer_investition(
        "waermepumpe", {"wp_art": "luft_wasser"})}

    # In der ersten Reihe steht unverändert genau das, was vorher die ganze
    # Liste war — bis auf `stromverbrauch_kwh`, das ohne Kennzeichen gilt.
    erste_reihe = {f for f, erw in energie.items() if not erw}
    assert erste_reihe == {"stromverbrauch_kwh", "strom_heizen_kwh",
                           "strom_warmwasser_kwh", "heizenergie_kwh",
                           "warmwasser_kwh"}
    # Und alle acht Betriebsart-Felder liegen dahinter, keines davor.
    betriebsart = {f for f in energie if f.startswith("betriebsart_")}
    assert len(betriebsart) == 8
    assert all(energie[f] for f in betriebsart)
    assert "soll_temperatur_c" not in live and "ist_temperatur_c" not in live


# ─── Die Namens-Whitelists quer durchs Backend ──────────────────────────────

def test_ein_modus_je_innengeraet_bliebe_ein_zustandsfeld():
    """Auch wenn es ihn heute nicht gibt: die Auflösung muss ihn kennen.

    Sie ist die Weiche, die eine `climate`-Entität aus dem 5-Sekunden-Poller
    und aus dem MQTT-Topic-Angebot heraushält.
    """
    assert ist_zustand_feld("betriebsmodus-3", "waermepumpe") is True
    assert ist_zustand_feld("betriebsmodus-3") is True
    assert ist_zustand_feld("betriebsart_strom_kuehlen_kwh-3") is False


def test_ein_betriebsart_zaehler_je_innengeraet_wird_gesnapshottet():
    """Ohne Basis-Key-Auflösung wäre er zuordenbar und käme nie an.

    `_is_kumulativ_feld` ist eine Namens-Whitelist über die Basis-Namen; ein
    adressierter Key fiele still durch — mit einer Tages- und Stundenebene,
    die es dann nicht gibt.
    """
    from backend.services.snapshot.keys import _is_kumulativ_feld

    assert _is_kumulativ_feld(BETRIEBSART_STROM_FELD[KUEHLEN]) is True
    assert _is_kumulativ_feld(
        feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3)) is True
    assert _is_kumulativ_feld("speicher_ladepreis_cent-3") is False


async def test_der_zaehler_eines_innengeraets_landet_in_der_schreib_map(db):
    """Die ROUTE dahinter: `_build_counter_map` der Anlage."""
    from backend.services.snapshot.writer import _build_counter_map

    anlage = Anlage(anlagenname="IG", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter=MIT_LISTE,
    )
    db.add(inv)
    await db.flush()
    feld = feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 1)
    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": {
        feld: {"strategie": "sensor", "sensor_id": "sensor.buero_kuehlen"},
    }}}}
    await db.commit()

    karte = _build_counter_map(anlage)
    assert karte.get(f"inv:{inv.id}:{feld}") == "sensor.buero_kuehlen"


async def test_der_daten_checker_sieht_den_modus_auch_adressiert(db):
    """Sonst meldete er „Betriebsmodus nicht zugeordnet" an einer Anlage,
    an der alle Innengeräte zugeordnet sind."""
    from backend.services.daten_checker import DatenChecker

    anlage = Anlage(anlagenname="IG2", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter=MIT_LISTE,
    )
    db.add(inv)
    await db.flush()
    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"live": {
        feld_je_innengeraet("betriebsmodus", 1): "climate.buero",
    }}}}
    await db.commit()

    ergebnisse = await DatenChecker(db)._check_klima_modus_sensor(anlage)
    assert ergebnisse, "der Check liefert nichts — die Probe misst nichts"
    assert all(e.schwere == "ok" for e in ergebnisse), (
        [f"{e.schwere}: {e.meldung}" for e in ergebnisse]
    )


# ─── Gemessen schlägt abgeleitet ────────────────────────────────────────────

def test_gemessen_schlaegt_abgeleitet_und_wird_nie_addiert():
    from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag

    class _Inv:
        typ = "waermepumpe"
        parameter = MIT_LISTE

    daten = {
        "stromverbrauch_kwh": 100.0,
        # abgeleitet (Monatsabschluss)
        MODUS_STROM_FELD[KUEHLEN]: 80.0,
        MODUS_ABDECKUNG_FELD: 500.0,
        # gemessen, je Innengerät
        feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 1): 30.0,
        feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3): 12.0,
    }
    b = imd_typ_beitrag(_Inv(), daten)
    assert b.wp_modus_gemessen is True
    # 42, nicht 122 (Summe) und nicht 80 (der abgeleitete Wert).
    assert b.wp_modus_strom_kuehlen == pytest.approx(42.0)


def test_das_geraetefeld_schlaegt_die_summe_der_innengeraete():
    from backend.core.berechnungen import betriebsart_strom_kwh

    daten = {
        BETRIEBSART_STROM_FELD[KUEHLEN]: 40.0,
        feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 1): 30.0,
    }
    assert betriebsart_strom_kwh(daten, KUEHLEN) == pytest.approx(40.0)


def test_ohne_zaehler_bleibt_die_ableitung_stehen():
    """`None` heißt „kein Zähler", nicht 0 — sonst verdrängte eine fehlende
    Messung die vorhandene Ableitung durch eine Null (die F-42-Klasse)."""
    from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag

    class _Inv:
        typ = "waermepumpe"
        parameter = LUFT_LUFT

    b = imd_typ_beitrag(_Inv(), {
        "stromverbrauch_kwh": 100.0,
        MODUS_STROM_FELD[HEIZEN]: 60.0,
        MODUS_ABDECKUNG_FELD: 500.0,
    })
    assert b.wp_modus_gemessen is False
    assert b.wp_modus_strom_heizen == pytest.approx(60.0)


async def test_die_route_zeigt_eine_gemessene_aufteilung_ohne_abdeckungsstunden(db):
    """**Der Endpunkt**, nicht der Layer: ein Betriebsart-Zähler hat keine
    „Stunden mit Signal". Wer nur `modus_abdeckung_h > 0` prüft, zeigt eine
    gemessene Aufteilung nirgends an."""
    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard

    anlage = Anlage(anlagenname="IG3", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter=MIT_LISTE,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2025, monat=6,
        verbrauch_daten={
            "stromverbrauch_kwh": 100.0,
            feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 1): 30.0,
            feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3): 12.0,
        },
    ))
    await db.commit()

    antwort = await get_waermepumpe_dashboard(anlage.id, strompreis_cent=30.0, db=db)
    assert len(antwort) == 1, "genau eine Wärmepumpe erwartet"
    z = antwort[0].zusammenfassung
    assert z.get("modus_gemessen") is True
    assert z["modus_strom_kuehlen_kwh"] == pytest.approx(42.0)
    assert z["modus_abdeckung_h"] == 0
    # Der Rest ist die Differenz zum Bezug, nicht eine zweite Messung.
    assert z["modus_nicht_aufgeteilt_kwh"] == pytest.approx(58.0)


# ─── Löschen räumt auf ──────────────────────────────────────────────────────

async def test_das_loeschen_eines_innengeraets_entfernt_seine_zuordnung(db):
    """Sonst bliebe sie unsichtbar liegen — das Feld wird nicht mehr erzeugt,
    also lässt sie sich auf der Fläche auch nicht mehr entfernen."""
    from backend.api.routes.investitionen.crud import (
        InvestitionUpdate,
        update_investition,
    )

    anlage = Anlage(anlagenname="IG4", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter=MIT_LISTE,
    )
    db.add(inv)
    await db.flush()
    bleibt = feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 1)
    faellt = feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3)
    anlage.sensor_mapping = {
        "investitionen": {str(inv.id): {"felder": {
            bleibt: {"strategie": "sensor", "sensor_id": "sensor.a"},
            faellt: {"strategie": "sensor", "sensor_id": "sensor.b"},
        }}},
        "quellen": {
            f"inv:{inv.id}:{bleibt}": {"quelle": "ha_app", "entity_id": "sensor.a"},
            f"inv:{inv.id}:{faellt}": {"quelle": "ha_app", "entity_id": "sensor.b"},
        },
    }
    await db.commit()

    await update_investition(
        inv.id,
        InvestitionUpdate(parameter={
            "wp_art": "luft_luft",
            "innengeraete": [{"id": 1, "bezeichnung": "Büro"}],
        }),
        db=db,
    )
    await db.commit()
    await db.refresh(anlage)

    felder = anlage.sensor_mapping["investitionen"][str(inv.id)]["felder"]
    assert bleibt in felder, "eine bleibende Zuordnung darf nicht mitgelöscht werden"
    assert faellt not in felder
    quellen = anlage.sensor_mapping["quellen"]
    assert f"inv:{inv.id}:{bleibt}" in quellen
    assert f"inv:{inv.id}:{faellt}" not in quellen
