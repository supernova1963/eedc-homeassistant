"""N-348: **Cockpit → Tag beantwortet die drei Arbeitszahlen je Funktion.**

**Der Fund** (2026-08-29, beim Messen von dietmar1968s WP-Karte, T89667 #245/#248):
Die Blockfabrik `KomponentenSektionen.tsx` ist für Monat und Tag **dieselbe**, und
`jazZeile` rendert eine Zeile erst, wenn **Wert oder Grund** gesetzt ist. Der Monat
ruft `arbeitszahl_je_funktion` **unbedingt** (`aktueller_monat.py:2103`) und liefert
immer beide Hälften; der Tag rief sie nie. Ergebnis: *Arbeitszahl · Heizen /
· Warmwasser / · Kühlen* verschwanden unter *Cockpit → Tag* **ersatzlos** — nicht
als „—", sondern gar nicht.

**Warum das ein Fehler ist und nicht bloß eine Lücke.** SOLL §3.3/**S3**: *„Eine
Sicht, die weniger zeigt als die Nachbarsicht, sagt warum."* Der Kommentar über
`jazZeile` sagt es sogar selbst — *„Eine fehlende Zeile wäre von ‚nicht getrennt
gemessen' nicht zu unterscheiden."* Genau dieser Fall trat ein, und er trifft
beide Datenlagen: mit getrennten Zählern fehlte die Zahl neben ihren eigenen
Zutaten, ohne sie nannte der Monat einen Grund und der Tag schwieg.

⛔ **Warum ein Begründungssatz KEIN Fix gewesen wäre.** „Liegt nur monatlich vor"
ist für Heizen/Warmwasser unwahr: §3.3 stellt den Tag auf *„alles, was aus
stündlichen Zählern entsteht"*, und alle vier Eingänge liegen in der Tagesantwort
(`views.py`, `wp_strom_heizen_kwh` · `wp_strom_warmwasser_kwh` · `wp_heizung_kwh` ·
`wp_warmwasser_kwh`). Die ehrliche Auskunft ist die Rechnung.

## Die Ausnahme, und sie ist gemessen — Kühlen

Für Kühlen gilt das Gegenteil, und deshalb steht dort ein Grund statt einer Zahl:
Die **Kältemenge** (`betriebsart_nutzenergie_kuehlen_kwh`) ist zwar ein stündlicher
Zähler, aber `get_betriebsart_strom_tageswerte` filtert über
`ist_betriebsart_strom_feld` und holt nur den **Nenner**. Der Zähler des Quotienten
hat keinen Tagespfad. `GRUND_KEINE_KAELTEMENGE` („kein Kältemengenzähler
zugeordnet") wäre hier eine **Falschaussage** für jeden, der einen zugeordnet hat.

Schwesterdatei: `test_soll_waerme_klima_w4_arbeitszahl_je_funktion.py` — dort steht
der **Layer**, hier die **Sicht**. Der Layer war nie defekt; genau deshalb hat ihn
keine der acht W-4-Proben gefangen.
"""

from __future__ import annotations

import pytest

from datetime import date, datetime, timedelta

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_FREMDSTROM,
    GRUND_KEINE_KAELTEMENGE,
    GRUND_KEIN_KUEHLBETRIEB,
    GRUND_KUEHLZAHL_NUR_MONAT,
    GRUND_STROM_NICHT_JE_FUNKTION,
)
from backend.core.investition_parameter import ABGRENZUNG_FREMDSTROM
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)

DATUM = date(2025, 6, 15)


async def _anlage(db, *, zaehler, params, wp_tag_kwh=30.0):
    """Anlage + Wärmepumpe mit gemappten Tageszählern.

    `zaehler`: ``{feldname: tages_kwh}`` — je Feld zwei Snapshots an den
    Tagesgrenzen, damit der Boundary-Diff den echten Weg nimmt.
    """
    anlage = Anlage(anlagenname="N348", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=15000.0,
        parameter=params,
    )
    db.add(inv)
    await db.flush()

    felder = {}
    t0 = datetime.combine(DATUM, datetime.min.time())
    for feld, tages_kwh in zaehler.items():
        felder[feld] = {"strategie": "sensor", "sensor_id": f"sensor.wp_{feld}"}
        key = f"inv:{inv.id}:{feld}"
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                              zeitpunkt=t0, wert_kwh=1000.0, quelle="ha_statistics"))
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                              zeitpunkt=t0 + timedelta(days=1),
                              wert_kwh=1000.0 + tages_kwh, quelle="ha_statistics"))

    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": felder}}}
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=DATUM,
        komponenten_kwh={f"waermepumpe_{inv.id}": wp_tag_kwh},
    ))
    await db.commit()
    return anlage, inv


async def _tag(db, **kw):
    from backend.api.routes.energie_profil.views import get_tag_detail
    anlage, _inv = await _anlage(db, **kw)
    return await get_tag_detail(anlage.id, DATUM, db)


# Eine Anlage, die alles misst, was der Tag messen kann: 20 kWh Heizstrom für
# 80 kWh Heizwärme (AZ 4,0) und 10 kWh WW-Strom für 20 kWh Warmwasser (AZ 2,0).
# ⭐ Die beiden Zahlen sind bewusst verschieden — genau darum geht es: die
# Gesamtzahl (100 ÷ 30 = 3,33) beschreibt keine der beiden.
VOLL = dict(
    zaehler={
        "strom_heizen_kwh": 20.0, "heizenergie_kwh": 80.0,
        "strom_warmwasser_kwh": 10.0, "warmwasser_kwh": 20.0,
    },
    params={"wp_art": "luft_wasser", "getrennte_strommessung": True},
)


# ── Der Kern: die Zahlen erreichen den Tag ─────────────────────────────────

async def test_n348_der_tag_rechnet_je_funktion(db):
    """Vorher: beide Felder `None`, die Zeilen fielen weg. Jetzt: zwei Zahlen."""
    resp = await _tag(db, **VOLL)

    assert resp.wp_jaz_heizen == 4.0
    assert resp.wp_jaz_warmwasser == 2.0
    # Steht ein Wert, steht kein Grund — nie beides (P4-Bauform).
    assert resp.wp_jaz_heizen_grund is None
    assert resp.wp_jaz_warmwasser_grund is None


async def test_n348_die_gesamtzahl_beschreibt_keine_der_beiden(db):
    """Die fachliche Pointe, an Zahlen festgehalten.

    100 kWh Wärme ÷ 30 kWh Strom = 3,33 — eine Zahl, die weder das gute Heizen
    (4,0) noch das erwartbar schwächere Warmwasser (2,0) beschreibt. Wer nur sie
    sieht, hält eine Anlage mit viel Warmwasseranteil für schlechter, als sie ist.
    """
    resp = await _tag(db, **VOLL)
    assert resp.wp_jaz == pytest.approx(100 / 30)
    assert resp.wp_jaz_heizen > resp.wp_jaz > resp.wp_jaz_warmwasser


# ── S3: auch das gesperrte „—" trägt seinen Grund ──────────────────────────

async def test_n348_ohne_getrennte_messung_steht_der_grund_da(db):
    """Die Lage, in der der Monat antwortete und der Tag schwieg.

    Ohne `getrennte_strommessung` gibt es E je Funktion nicht. Der Monat schreibt
    dann „— (Strom nicht getrennt je Funktion gemessen)"; der Tag ließ die Zeile
    ersatzlos weg — von „nicht getrennt gemessen" nicht zu unterscheiden.
    """
    resp = await _tag(
        db,
        zaehler={"heizenergie_kwh": 80.0, "warmwasser_kwh": 20.0},
        params={"wp_art": "luft_wasser"},   # kein getrennte_strommessung
    )

    assert resp.wp_jaz_heizen is None
    assert resp.wp_jaz_warmwasser is None
    assert resp.wp_jaz_heizen_grund == GRUND_STROM_NICHT_JE_FUNKTION
    assert resp.wp_jaz_warmwasser_grund == GRUND_STROM_NICHT_JE_FUNKTION


async def test_n348_die_r2_sperren_gelten_auch_im_tag(db):
    """Kein zweiter Rechenweg: der Helfer bringt seine Sperren mit.

    Ein Heizstab auf dem WP-Zähler sperrt die Gesamtzahl — und muss beide
    Funktionszahlen mitsperren. Genau das war der W-3-Befund am Hub: dieselbe
    Anlage, zwei Aussagen. Hier ist es dieselbe Anlage, dieselbe Sicht.
    """
    resp = await _tag(
        db,
        zaehler={
            "strom_heizen_kwh": 20.0, "heizenergie_kwh": 80.0,
            "strom_warmwasser_kwh": 10.0, "warmwasser_kwh": 20.0,
        },
        params={"wp_art": "luft_wasser", "getrennte_strommessung": True,
                "abgrenzung": ABGRENZUNG_FREMDSTROM},
    )

    assert resp.wp_jaz is None and resp.wp_jaz_grund == GRUND_FREMDSTROM
    assert resp.wp_jaz_heizen is None
    assert resp.wp_jaz_warmwasser is None
    assert resp.wp_jaz_heizen_grund == GRUND_FREMDSTROM
    assert resp.wp_jaz_warmwasser_grund == GRUND_FREMDSTROM


# ── Kühlen: der Grund sagt die Wahrheit, nicht die bequeme Antwort ─────────

async def test_n348_kuehlen_ohne_kuehlbetrieb_sagt_das(db):
    """Eine Luft-Wasser-WP, die nie kühlt, liest keinen Aggregations-Hinweis.

    ⭐ Die erste Fassung setzte `GRUND_KUEHLZAHL_NUR_MONAT` **unbedingt** — dann
    hätte jede reine Heizungs-Wärmepumpe einen Hinweis auf eine Lücke gelesen,
    die sie nichts angeht. Der Tag kennt den Kühlstrom und kann die
    aussagekräftigere Antwort geben; die Reihenfolge ist dieselbe wie in
    `arbeitszahl_kuehlen` selbst.
    """
    resp = await _tag(db, **VOLL)

    assert resp.wp_jaz_kuehlen is None
    assert resp.wp_jaz_kuehlen_grund == GRUND_KEIN_KUEHLBETRIEB


async def test_n348_kuehlen_mit_kuehlbetrieb_nennt_die_echte_luecke(db):
    """Bei geflossenem Kühlstrom fehlt wirklich nur der Zähler des Quotienten.

    ⛔ Hier NICHT „kein Kältemengenzähler zugeordnet" — dieser Anlage ist einer
    zugeordnet (`betriebsart_nutzenergie_kuehlen_kwh` unten), er erreicht den Tag
    nur nicht. Der Satz würde sie an der falschen Stelle suchen lassen.
    """
    resp = await _tag(
        db,
        zaehler={
            "strom_heizen_kwh": 20.0, "heizenergie_kwh": 80.0,
            "betriebsart_strom_kuehlen_kwh": 6.0,
            "betriebsart_nutzenergie_kuehlen_kwh": 18.0,
        },
        params={"wp_art": "luft_luft", "getrennte_strommessung": True},
    )

    assert resp.wp_modus_strom_kuehlen_kwh == 6.0, "Nenner ist im Tag da"
    assert resp.wp_jaz_kuehlen is None
    assert resp.wp_jaz_kuehlen_grund == GRUND_KUEHLZAHL_NUR_MONAT

    # ⛔ **DIESE ZEILE IST DER EIGENTLICHE WÄCHTER, und sie steht hier, weil die
    # Probe ohne sie NICHTS GEMESSEN HAT.** Die Gegenprobe vom 29.08. hat es
    # gezeigt: Wer `GRUND_KUEHLZAHL_NUR_MONAT = GRUND_KEINE_KAELTEMENGE` setzt —
    # also genau den bequemen Weg geht, den dieser Test verhindern soll —,
    # ändert **beide Seiten** der Assertion darüber mit. Sie blieb grün.
    # Dieselbe Klasse wie N-132: ein Wächter, der eine Konstante gegen sich
    # selbst hält, hält gar nichts. Geprüft wird deshalb die AUSSAGE:
    # Diese Anlage HAT einen Kältemengenzähler zugeordnet — ihr zu sagen, sie
    # habe keinen, schickt sie an die falsche Stelle.
    assert resp.wp_jaz_kuehlen_grund != GRUND_KEINE_KAELTEMENGE
    assert GRUND_KUEHLZAHL_NUR_MONAT != GRUND_KEINE_KAELTEMENGE


# ── Der Wächter gegen den Rückfall ─────────────────────────────────────────

async def test_n348_keine_der_drei_zeilen_ist_je_stumm(db):
    """**Die Regel selbst**, nicht ihre drei Ausprägungen.

    Der Defekt war nicht „die Zahl fehlt", sondern „die Zeile verschwindet
    lautlos". Die geteilte Blockfabrik rendert nichts, wenn Wert UND Grund fehlen
    — dieser Test hält deshalb fest, dass **je Funktion immer genau eines von
    beidem** gesetzt ist, in jeder Datenlage.

    ⚑ Er fängt damit auch eine vierte Funktion, die es heute noch nicht gibt:
    wer eine hinzufügt und die Antwort vergisst, bekommt hier rot — die Fassung
    „prüfe die drei bekannten Felder" könnte das nicht.
    """
    lagen = [
        ("alles gemessen", VOLL),
        ("ohne getrennte Messung", dict(
            zaehler={"heizenergie_kwh": 80.0, "warmwasser_kwh": 20.0},
            params={"wp_art": "luft_wasser"})),
        ("ohne jeden Wärmezähler", dict(
            zaehler={"strom_heizen_kwh": 20.0, "strom_warmwasser_kwh": 10.0},
            params={"wp_art": "luft_wasser", "getrennte_strommessung": True})),
        ("Heizstab am Zähler", dict(
            zaehler={"strom_heizen_kwh": 20.0, "heizenergie_kwh": 80.0},
            params={"wp_art": "luft_wasser", "getrennte_strommessung": True,
                    "abgrenzung": ABGRENZUNG_FREMDSTROM})),
    ]
    for name, kw in lagen:
        resp = await _tag(db, **kw)
        for funktion in ("heizen", "warmwasser", "kuehlen"):
            wert = getattr(resp, f"wp_jaz_{funktion}")
            grund = getattr(resp, f"wp_jaz_{funktion}_grund")
            assert wert is not None or grund, (
                f"[{name}] wp_jaz_{funktion}: weder Wert noch Grund — die Zeile "
                f"verschwindet in der Tagessicht lautlos (N-348/S3)"
            )
