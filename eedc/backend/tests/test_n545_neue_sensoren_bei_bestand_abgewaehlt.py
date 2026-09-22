"""N-545 — Ein neues Sensor-Paket startet bei **Bestands**installationen abgewählt.

**Der Fall.** v4.0.27 brachte 21 neue Export-Sensoren auf einmal; zwei Melder
binnen 24 Stunden (#400). Rainer will es beim nächsten Mal vorher wissen. Ohne
diesen Schritt bekäme jede Bestandsinstallation mit aktivem Export beim ersten
Auto-Publish nach dem Update 28 neue Entitäten, **bevor** jemand abwählen kann —
und der Registry-Eintrag in HA bleibt danach stehen.

**Was die Proben hier festhalten** (und was sie NICHT sagen):

* Eine **Neuinstallation** bekommt weiterhin alles (Entscheid 28.08.) — Fälle (c)/(d).
* Die Abwahl wird **vereinigt**, nie ersetzt: die Wahl des Anwenders geht nie
  verloren — Fall (a), und Fall (e) hält fest, dass ein wieder angehakter
  Paket-Sensor angehakt **bleibt**.
* Der Mechanismus trägt auch das **nächste** Paket — Fall (f).
* Der Wächter (g) fängt die Drift, die den ganzen Mechanismus entwertet: eine
  neue Definition ohne Paket-Zuordnung erschiene wieder unangekündigt.

⛔ **Was hier bewusst NICHT geprüft wird:** ob der Schritt Topics zurücknimmt.
Er tut es nicht und soll es nicht — bei einer echten Bestandsinstallation wurden
die neuen Schlüssel nie publiziert, es liegt nichts auf dem Broker.
"""

from datetime import date


from backend.services.ha_sensors_export import (
    AKTUELLES_SENSOR_PAKET,
    get_all_sensor_definitions,
)
from backend.services.migrations.migrate_sensor_paket_abwahl import (
    neue_sensoren_bei_bestand_abwaehlen,
)
from backend.services.mqtt_broker_settings import (
    ABWAHL_FELD,
    SENSOR_PAKET_FELD,
    ZULETZT_FELD,
    abgewaehlte_sensoren,
    schreibe_export_settings,
)

# ── Die eingefrorene Liste (§0 des Auftrags) ────────────────────────────────
#
# ⛔ **Sie ist bewusst hier abgeschrieben und wird NICHT aus dem Produktivcode
# abgeleitet.** Eine Liste, die sich `[d.key for d in defs if d.seit_paket == 1]`
# holt, prüft nur, dass der Code mit sich selbst übereinstimmt — sie wäre grün,
# egal welche Definition jemand markiert oder vergisst. Gemessen am 22.09.2026
# gegen `ca6cf36f`: `comm -13` über die `key="…"`-Mengen liefert genau diese 28.
PAKET_1_KEYS: frozenset[str] = frozenset({
    # S2/S3 „eedc@ha, Teil 1" — Steuerungshilfen (13)
    "eedc_ueberschuss_heute_kwh",
    "eedc_ueberschuss_jetzt_kw",
    "eedc_ueberschuss_verfuegbar",
    "eedc_guenstige_stunde",
    "eedc_speicher_voll",
    "eedc_speicher_voll_um_ts",
    "eedc_speicher_soc_prozent",
    "eedc_netzbezug_spitze_heute_kw",
    "eedc_ueberschuss_prognose_heute_kwh",
    "eedc_arbitrage_vorschlag_kwh",
    "eedc_bestes_fenster_ab",
    "eedc_prognose_abweichung_heute_prozent",
    "eedc_prognose_auffaellig",
    # S2/S3 — Wärmepumpe (4)
    "wp_warmwasserbetrieb",
    "wp_warmwasser_fenster_ab",
    "wp_heizfenster_stunden",
    "wp_kuehlfenster_ab",
    # S2/S3 — Sonstige Verbraucher (2)
    "sonstiges_verbrauch_monat_kwh",
    "sonstiges_fenster_ab",
    # S3b „Preise und Speicher" (9)
    "eedc_bezugspreis_jetzt_cent",
    "eedc_einspeiseverguetung_cent",
    "eedc_eigenverbrauch_wert_cent",
    "eedc_speicher_strom_kosten_cent",
    "eedc_speicher_netzladen_kosten_cent",
    "eedc_speicher_leer_um_ts",
    "eedc_speicher_reicht_bis_mitternacht",
    "eedc_abregelung_heute_kwh",
    "eedc_einspeisung_unerwuenscht",
})


async def _lege_anlage_an(db):
    from backend.models import Anlage

    anlage = Anlage(anlagenname="N-545", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.commit()
    return anlage


async def _stand(db) -> int | None:
    from backend.services.migrations.migrate_sensor_paket_abwahl import (
        _export_settings,
        _gelesener_stand,
    )

    return _gelesener_stand(await _export_settings(db))


# ── (a) Bestand über den expliziten Export-Schalter ─────────────────────────

async def test_a_bestand_bekommt_das_paket_abgewaehlt(db):
    """Die 28 kommen dazu — und die Wahl des Anwenders bleibt unberührt.

    ⛔ **Vereinigung, nicht Ersetzen.** Ein Schritt, der die Liste schriebe
    statt sie zu ergänzen, hätte dem Anwender seinen abgewählten
    `roi_prozent` wortlos zurückgegeben — genau die Klasse, die #400 beim
    Auto-Publish-Toggle schon einmal getroffen hat.
    """
    await _lege_anlage_an(db)
    await schreibe_export_settings(db, enabled=True, **{ABWAHL_FELD: ["roi_prozent"]})

    await neue_sensoren_bei_bestand_abwaehlen(db)

    assert await abgewaehlte_sensoren(db) == PAKET_1_KEYS | {"roi_prozent"}
    assert len(await abgewaehlte_sensoren(db)) == 29
    assert await _stand(db) == AKTUELLES_SENSOR_PAKET


# ── (b) Bestand allein über die Publish-Spur ────────────────────────────────

async def test_b_bestand_erkannt_an_zuletzt_publiziert(db):
    """Ohne `enabled`-Eintrag, aber mit Publish-Historie: auch das ist Bestand.

    Eine Installation, die schon publiziert hat, hat ihre Entitäten in HA —
    sie ist der Fall, um den es geht, auch wenn der Toggle nie explizit
    geschrieben wurde (Default-Auflösung).
    """
    await _lege_anlage_an(db)
    await schreibe_export_settings(db, **{ZULETZT_FELD: {"a1": ["roi_prozent"]}})

    await neue_sensoren_bei_bestand_abwaehlen(db)

    assert await abgewaehlte_sensoren(db) == PAKET_1_KEYS
    assert await _stand(db) == AKTUELLES_SENSOR_PAKET


# ── (c)/(d) Neuinstallation bekommt ALLES ───────────────────────────────────

async def test_c_neuinstallation_ohne_anlage_waehlt_nichts_ab(db):
    """Keine Anlage = frische Box. Der 28.08.-Entscheid gilt ungebrochen."""
    await neue_sensoren_bei_bestand_abwaehlen(db)

    assert await abgewaehlte_sensoren(db) == set()
    assert await _stand(db) == AKTUELLES_SENSOR_PAKET, (
        "der Stand MUSS geschrieben werden — sonst wäre dieselbe Box beim "
        "nächsten Paket plötzlich „Bestand“ und bekäme es abgewählt"
    )


async def test_d_anlage_ohne_je_benutzten_export_ist_keine_bestandsinstallation(db):
    """Anlage ja, Export nie benutzt ⇒ nichts abwählen.

    ⛔ **Das ist der Grund, warum das Kriterium NICHT `export_aktiviert(db)`
    ist.** Die Funktion löst ohne expliziten Eintrag auf einen Default auf
    („HA-Verbindung + Broker ⇒ an"), und im Add-on ist beides ab der ersten
    Minute wahr — diese Probe wäre dort rot, sobald der Anwender seine erste
    Anlage angelegt hat.
    """
    await _lege_anlage_an(db)

    await neue_sensoren_bei_bestand_abwaehlen(db)

    assert await abgewaehlte_sensoren(db) == set()
    assert await _stand(db) == AKTUELLES_SENSOR_PAKET


# ── (e) Idempotenz, auch gegen die Wahl des Anwenders ───────────────────────

async def test_e_zweiter_lauf_aendert_nichts_und_respektiert_die_anwahl(db):
    """Wer einen Paket-Sensor anhakt, behält ihn über jeden Neustart.

    ⛔ **Das ist der Unterschied zwischen „einmal je Paket" und „bei jedem
    Start".** Ein Schritt, der den Stand nicht fortschriebe oder ihn ignorierte,
    würde dem Anwender den eben angehakten Sensor bei jedem Neustart wieder
    abwählen — und er käme nie dahinter, warum.
    """
    await _lege_anlage_an(db)
    await schreibe_export_settings(db, enabled=True)
    await neue_sensoren_bei_bestand_abwaehlen(db)
    assert await abgewaehlte_sensoren(db) == PAKET_1_KEYS

    # Der Anwender hakt einen des Pakets wieder an.
    rest = sorted(PAKET_1_KEYS - {"eedc_speicher_soc_prozent"})
    await schreibe_export_settings(db, **{ABWAHL_FELD: rest})

    await neue_sensoren_bei_bestand_abwaehlen(db)
    await neue_sensoren_bei_bestand_abwaehlen(db)

    assert await abgewaehlte_sensoren(db) == set(rest)
    assert "eedc_speicher_soc_prozent" not in await abgewaehlte_sensoren(db)
    assert await _stand(db) == AKTUELLES_SENSOR_PAKET


# ── (f) Das NÄCHSTE Paket ───────────────────────────────────────────────────

async def test_f_ein_kuenftiges_paket_nimmt_nur_seine_eigenen_keys(db, monkeypatch):
    """Stand 1, Paket 2 ⇒ genau die EINE Definition von Paket 2 kommt dazu.

    Ohne diese Probe wäre der Mechanismus nur für das erste Paket belegt —
    und genau der Teil, der ihn tragen soll (jedes künftige Release), ungemessen.
    """
    from backend.services import ha_sensors_export as hse
    from backend.services.migrations import migrate_sensor_paket_abwahl as schritt

    opfer = "roi_prozent"
    definition = next(d for d in get_all_sensor_definitions() if d.key == opfer)
    assert definition.seit_paket == 0, "Vorbedingung: ein Bestands-Sensor"

    monkeypatch.setattr(hse, "AKTUELLES_SENSOR_PAKET", 2)
    monkeypatch.setattr(schritt, "AKTUELLES_SENSOR_PAKET", 2)
    monkeypatch.setattr(definition, "seit_paket", 2)

    await _lege_anlage_an(db)
    await schreibe_export_settings(db, enabled=True, **{SENSOR_PAKET_FELD: 1})

    await neue_sensoren_bei_bestand_abwaehlen(db)

    assert await abgewaehlte_sensoren(db) == {opfer}, (
        "nur das Paket-2-Key — die 28 aus Paket 1 sind für diese Installation "
        "nicht neu und dürfen nicht nachträglich abgewählt werden"
    )
    assert await _stand(db) == 2


# ── (g) Der Wächter gegen die Drift ─────────────────────────────────────────

def test_g_jede_definition_traegt_ihre_paket_zuordnung():
    """Die 28 tragen Paket 1, ALLE anderen 0 — und keine liegt in der Zukunft.

    ⛔ **Das ist die Drift, die den ganzen Mechanismus entwertet.** Wer eine
    Definition anlegt und `seit_paket` vergisst, bekommt eine, die als
    „seit immer" gilt: sie startet bei jeder Bestandsinstallation **an** und
    erscheint wieder unangekündigt in Home Assistant — der Fall v4.0.27, nur
    diesmal mit einem Mechanismus daneben, der ihn hätte verhindern sollen.
    """
    definitionen = get_all_sensor_definitions()
    je_paket = {d.key: d.seit_paket for d in definitionen}

    assert {k for k, p in je_paket.items() if p == 1} == set(PAKET_1_KEYS)
    assert {k for k, p in je_paket.items() if p != 0} == set(PAKET_1_KEYS), (
        "eine Definition trägt einen Paket-Stand, der nicht zu Paket 1 gehört"
    )
    zu_weit = {k: p for k, p in je_paket.items() if p > AKTUELLES_SENSOR_PAKET}
    assert not zu_weit, f"Paket-Stand über {AKTUELLES_SENSOR_PAKET}: {zu_weit}"
    assert len(PAKET_1_KEYS) == 28
    assert len(definitionen) == len(je_paket), "Sensor-Schlüssel sind nicht eindeutig"


# ── (h) Die Leserichtung der Route ──────────────────────────────────────────

async def test_h_route_traegt_neu_und_neues_paket(db):
    """`GET /mqtt/abwahl` sagt je Sensor „neu" und nennt das Paket im Ganzen.

    Die Oberfläche entscheidet an `neues_paket.abgewaehlt`, ob sie den
    Hinweiskasten zeigt — bei einer Neuinstallation ist die Menge leer und der
    Kasten bliebe eine Meldung über nichts.
    """
    from backend.api.routes.ha_export.konfig import get_sensor_abwahl

    await _lege_anlage_an(db)
    await schreibe_export_settings(db, enabled=True)

    vorher = await get_sensor_abwahl(db)
    assert vorher["neues_paket"]["paket"] == AKTUELLES_SENSOR_PAKET
    assert vorher["neues_paket"]["label"]
    assert set(vorher["neues_paket"]["keys"]) == set(PAKET_1_KEYS)
    assert vorher["neues_paket"]["abgewaehlt"] == [], "noch lief der Schritt nicht"
    assert {s["key"] for s in vorher["sensoren"] if s["neu"]} == set(PAKET_1_KEYS)
    assert all(s["exportiert"] for s in vorher["sensoren"])

    await neue_sensoren_bei_bestand_abwaehlen(db)

    nachher = await get_sensor_abwahl(db)
    assert set(nachher["neues_paket"]["abgewaehlt"]) == set(PAKET_1_KEYS)
    assert {s["key"] for s in nachher["sensoren"] if s["neu"]} == set(PAKET_1_KEYS)
    assert {s["key"] for s in nachher["sensoren"] if not s["exportiert"]} == set(PAKET_1_KEYS)
    # Der Bestand bleibt unberührt — 57 Definitionen exportieren weiter.
    assert sum(1 for s in nachher["sensoren"] if s["exportiert"]) == len(nachher["sensoren"]) - 28
