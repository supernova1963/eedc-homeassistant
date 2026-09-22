"""S3b — die neun Preis- und Speicher-Sensoren: die Degradations-Matrix, Zeile für Zeile.

**Die Probenklasse, um die es hier geht** (dieselbe wie in
`test_s2_entscheidungs_sensoren.py`): Ein Sensor, der bei fehlendem Eingang eine
0 meldet, ist schlimmer als keiner — in HA landet die 0 in der
Langzeitstatistik, eine Automation hält sie für eine Messung, und niemand sieht,
dass sie eine Annahme war. Jede Zeile prüft deshalb **beide** Richtungen: der
Sensor entsteht mit vollständigem Eingang, und er fehlt **ganz**, sobald einer
fehlt.

**Was hier NICHT geprüft werden kann und warum das gesagt gehört:** Die
Speicher-Simulation läuft nur mit einem Ladestand aus den letzten zwei Tagen
(`ha_export_prognose._aktueller_speicher`: `datum >= heute − 1`). Die drei
Demo-Kopien tragen seit dem 23.06.2026 keinen — der Golden Master sieht
`eedc_speicher_leer_um_ts` und `…_reicht_bis_mitternacht` deshalb **strukturell
nie**. Ihre Deckung sind die gesäten Proben hier unten, nicht das Gate.

⛔ **Kein Netz, kein Broker, keine echte Uhr.** Prognose und Preis werden
gestellt (`monkeypatch`), die Zeit kommt als Parameter (N-167), und die
Markt-API bekommt einen Fake-Client.

Schwesterdateien: `test_s3b_preis_reihe_layer.py` (die Formeln darunter),
`test_s2_entscheidungs_sensoren.py` (die Phase davor, deren Fixtures diese hier
nachnutzt), `test_n544_fenster_achse_backward.py` (die Achse).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pytest

from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten
from backend.models.strompreis import Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil

#: Gestellte Uhr aller Proben — ein Werktag, 14:30. Backward ist das Slot 15.
JETZT = datetime(2026, 9, 22, 14, 30)
HEUTE = JETZT.date()
JETZT_SLOT = JETZT.hour + 1


# ── Aufbau ──────────────────────────────────────────────────────────────────

async def _anlage(db, *, ust=19.0, koordinaten=True, **kwargs) -> Anlage:
    anlage = Anlage(
        anlagenname="S3b-Probe", leistung_kwp=10.0,
        installationsdatum=date(2023, 1, 1),
        latitude=48.1 if koordinaten else None,
        longitude=11.5 if koordinaten else None,
        ust_satz_prozent=ust,
        **kwargs,
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=200.0))
    await db.commit()
    return anlage


async def _tarif(db, anlage_id, *, verwendung="allgemein", bezug=30.0, verguetung=8.0,
                 vertragsart=None, gueltig_ab=date(2023, 1, 1), gueltig_bis=None,
                 variabel=False) -> Strompreis:
    t = Strompreis(
        anlage_id=anlage_id, verwendung=verwendung,
        netzbezug_arbeitspreis_cent_kwh=bezug,
        einspeiseverguetung_cent_kwh=verguetung,
        vertragsart=vertragsart, gueltig_ab=gueltig_ab, gueltig_bis=gueltig_bis,
        einspeisung_variabel=variabel,
    )
    db.add(t)
    await db.commit()
    return t


async def _speicher(db, anlage_id, *, kapazitaet=10.0, eta=95.0, laedt_aus_netz=True,
                    anschaffung=date(2023, 1, 1), imd_monate=0,
                    ladung=100.0, entladung=85.0) -> Investition:
    inv = Investition(
        anlage_id=anlage_id, bezeichnung="Speicher", typ="speicher", aktiv=True,
        anschaffungsdatum=anschaffung, anschaffungskosten_gesamt=5000.0,
        parameter={"kapazitaet_kwh": kapazitaet, "wirkungsgrad_prozent": eta,
                   "laedt_aus_netz": laedt_aus_netz},
    )
    db.add(inv)
    await db.flush()
    jahr, monat = 2023, 1
    for _ in range(imd_monate):
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=jahr, monat=monat,
            verbrauch_daten={"ladung_kwh": ladung, "entladung_kwh": entladung},
        ))
        monat += 1
        if monat > 12:
            jahr, monat = jahr + 1, 1
    await db.commit()
    return inv


def _preis(*, preise=None, morgen=False, markt="DE") -> dict:
    """Ein Preis-Dict mit **forward** beschrifteten Börsenstunden."""
    preise = preise or {}

    def _profil():
        return [{"stunde": h, "preis_cent": preise.get(h, 20.0),
                 "unter_schwelle": preise.get(h, 20.0) < 10.0} for h in range(24)]

    # Das vollstaendige Preis-Dict kommt aus der Schwesterprobe — `berechne_preis_export`
    # liefert ein gutes Dutzend Pflichtschluessel, und wer hier einen vergisst, misst
    # einen KeyError statt eines Sensors.
    from backend.tests.test_s2_entscheidungs_sensoren import _preis as _basis_preis

    out = _basis_preis(
        rang_profil=_profil(),
        preis_aktuell_cent=preise.get(JETZT.hour, 20.0),
        guenstig_schwelle_cent=10.0,
    )
    out["markt"] = markt
    if morgen:
        out["rang_profil_morgen"] = _profil()
        out["morgen_verfuegbar"] = True
    return out


def _prognose(**ueberschreiben) -> dict:
    from backend.tests.test_s2_entscheidungs_sensoren import _prognose as _basis

    return _basis(**ueberschreiben)


def _stelle(monkeypatch, prognose, preis):
    from backend.api.routes.ha_export import anlage_sensorwerte

    async def _p(db, anlage, *, skip_jitter=False):
        return prognose

    async def _q(db, anlage):
        return preis

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _p)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _q)


def _cache_leeren():
    """Der Aufschlag-Cache ist prozessweit — sonst verkleben die Proben einander."""
    from backend.services import ha_export_bezugspreis as hb

    hb._aufschlag_cache.clear()
    hb._markt_nachgeholt.clear()


@pytest.fixture(autouse=True)
def _sauber():
    _cache_leeren()
    yield
    _cache_leeren()


async def _rechne(db, anlage, jetzt=JETZT) -> dict:
    from backend.api.routes.ha_export import calculate_anlage_sensors

    werte = await calculate_anlage_sensors(db, anlage, skip_jitter=True, jetzt=jetzt)
    return {sv.definition.key: sv for sv in werte}


# ═══════════════════════════════════════════════════════════════════════════
# 1 · Bezugspreis — die vier Regime
# ═══════════════════════════════════════════════════════════════════════════

async def test_kein_tarif_kein_preis(db, monkeypatch):
    """Ohne Tarif gibt es keinen Preis, den eedc behaupten dürfte — und keinen Sensor."""
    anlage = await _anlage(db)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    assert "eedc_bezugspreis_jetzt_cent" not in sv
    assert "eedc_einspeiseverguetung_cent" not in sv
    assert "eedc_eigenverbrauch_wert_cent" not in sv


async def test_festpreis_ist_exakt_der_tarifpreis(db, monkeypatch):
    """Für den Festtarif-Haushalt entsteht der Preis, den er **zahlt** — nicht die Börse."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=31.95, verguetung=8.0, vertragsart="fest")
    _stelle(monkeypatch, _prognose(), _preis(preise={h: 5.0 for h in range(24)}))
    sv = await _rechne(db, anlage)

    preis = sv["eedc_bezugspreis_jetzt_cent"]
    assert preis.value == 31.95, "die Börse steht bei 5 ct — der Haushalt zahlt 31,95"
    assert preis.zusatz_attribute["preisquelle"] == "vertrag"
    assert "aufschlag_cent" not in preis.zusatz_attribute
    assert "markt" not in preis.zusatz_attribute, "kein Markt, wo kein Marktpreis drinsteht"
    assert preis.zusatz_attribute["slot_konvention"] == "backward"
    assert len(preis.zusatz_attribute["stundenprofil_cent"]) == 24

    assert sv["eedc_einspeiseverguetung_cent"].value == 8.0
    assert sv["eedc_eigenverbrauch_wert_cent"].value == 23.95   # 31,95 − 8,00


async def test_leere_vertragsart_ist_ableitbar(db, monkeypatch):
    """Die drei Demo-Kopien tragen `vertragsart` leer — das ist ein Festpreis, kein Sonderfall."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0, vertragsart=None)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    assert sv["eedc_bezugspreis_jetzt_cent"].value == 30.0
    assert sv["eedc_bezugspreis_jetzt_cent"].zusatz_attribute["preisquelle"] == "vertrag"


async def test_dynamisch_ohne_ableitbaren_aufschlag_ist_boerse_und_sagt_es(db, monkeypatch):
    """Nackte Börse ⇒ **kein** Eigenverbrauchs-Wert (Flex P-5) — mit genanntem Grund."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0, verguetung=8.0, vertragsart="dynamisch")
    _stelle(monkeypatch, _prognose(), _preis(preise={JETZT.hour: 7.5}))
    sv = await _rechne(db, anlage)

    preis = sv["eedc_bezugspreis_jetzt_cent"]
    assert preis.value == 7.5, "die Börse der laufenden Stunde (forward 14 → Slot 15)"
    assert preis.zusatz_attribute["preisquelle"] == "boersenpreis"
    assert preis.zusatz_attribute["aufschlag_quelle"] == "keiner"
    assert preis.zusatz_attribute["markt"] == "DE"
    assert "eigenverbrauch_wert_grund" in preis.zusatz_attribute

    assert "eedc_eigenverbrauch_wert_cent" not in sv, (
        "eine Differenz aus nackter Börse und Vertragsvergütung wäre keine Näherung"
    )
    # Die Vergütung selbst gibt es trotzdem — sie hängt nicht am Bezugspreis.
    assert sv["eedc_einspeiseverguetung_cent"].value == 8.0


async def test_dynamisch_mit_abrechnung_traegt_den_endpreis(db, monkeypatch):
    """Die Kernprobe von B2b: Ø 27,66 · Börsenmittel 8,00 · USt 19 ⇒ 18,14 ct Aufschlag.

    Gesät: ein abgerechneter Vormonat mit `netzbezug_durchschnittspreis_cent`
    **und** Börsenstunden im Tagesprofil, gegen die das verbrauchsgewichtete
    Mittel gebildet wird.
    """
    anlage = await _anlage(db, ust=19.0)
    await _tarif(db, anlage.id, bezug=30.0, verguetung=8.0, vertragsart="dynamisch",
                 gueltig_ab=date(2026, 1, 1))
    # Abrechnungsmonat August 2026: jede Stunde 8,00 ct Börse, jede Stunde 1 kWh Bezug.
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=8,
                       netzbezug_kwh=744.0, netzbezug_durchschnittspreis_cent=27.66))
    tag = date(2026, 8, 1)
    while tag.month == 8:
        for h in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=tag, stunde=h,
                netzbezug_kw=1.0, boersenpreis_cent=8.0,
            ))
        tag += timedelta(days=1)
    await db.commit()

    _stelle(monkeypatch, _prognose(), _preis(preise={JETZT.hour: 5.0}))
    sv = await _rechne(db, anlage)

    preis = sv["eedc_bezugspreis_jetzt_cent"]
    assert preis.zusatz_attribute["preisquelle"] == "boerse_plus_aufschlag"
    assert preis.zusatz_attribute["aufschlag_cent"] == 18.14
    assert preis.zusatz_attribute["aufschlag_quelle"] == "abrechnung 2026-08"
    assert preis.zusatz_attribute["ust_prozent"] == 19.0
    assert preis.value == 24.09, "1,19 × 5,00 + 18,14"

    # …und jetzt IST der Preis vollständig ⇒ der Eigenverbrauchs-Wert entsteht.
    assert sv["eedc_eigenverbrauch_wert_cent"].value == 16.09    # 24,09 − 8,00


async def test_dynamisch_mit_sensorpaaren_wenn_keine_abrechnung_da_ist(db, monkeypatch):
    """Stufe 2 der Kaskade — Median über gemessene Stunden, ≥ 24 Paare."""
    anlage = await _anlage(db, ust=19.0)
    await _tarif(db, anlage.id, vertragsart="dynamisch", gueltig_ab=date(2026, 1, 1))
    # Sieben Tage mit je 24 Stunden: Endpreis = 1,19 × Börse + 18,14.
    for tag_offset in range(1, 6):
        tag = HEUTE - timedelta(days=tag_offset)
        for h in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=tag, stunde=h,
                boersenpreis_cent=6.0, strompreis_cent=round(1.19 * 6.0 + 18.14, 2),
            ))
    await db.commit()

    _stelle(monkeypatch, _prognose(), _preis(preise={JETZT.hour: 5.0}))
    sv = await _rechne(db, anlage)

    preis = sv["eedc_bezugspreis_jetzt_cent"]
    assert preis.zusatz_attribute["aufschlag_quelle"] == "sensor 7 tage"
    assert preis.zusatz_attribute["aufschlag_cent"] == pytest.approx(18.14, abs=0.02)
    assert preis.value == pytest.approx(24.09, abs=0.02)


async def test_abrechnung_vor_dem_tarifwechsel_zaehlt_nicht(db, monkeypatch):
    """ADR-002/P8: ein Ø aus der Zeit vor `gueltig_ab` beschreibt einen anderen Vertrag."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, vertragsart="dynamisch", gueltig_ab=date(2026, 9, 1))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=7,
                       netzbezug_kwh=744.0, netzbezug_durchschnittspreis_cent=27.66))
    tag = date(2026, 7, 1)
    while tag.month == 7:
        for h in range(24):
            db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=tag, stunde=h,
                                      netzbezug_kw=1.0, boersenpreis_cent=8.0))
        tag += timedelta(days=1)
    await db.commit()

    _stelle(monkeypatch, _prognose(), _preis(preise={JETZT.hour: 5.0}))
    sv = await _rechne(db, anlage)

    preis = sv["eedc_bezugspreis_jetzt_cent"]
    assert preis.zusatz_attribute["preisquelle"] == "boersenpreis"
    assert preis.zusatz_attribute["aufschlag_quelle"] == "keiner"


async def test_der_laufende_monat_ist_nicht_abgerechnet(db, monkeypatch):
    """⭐ Ein Ø über einen halben Monat ist kein Abrechnungs-Ø.

    `Monatsdaten.netzbezug_durchschnittspreis_cent` des LAUFENDEN Monats ist ein
    Zwischenstand — er beschreibt die bisherigen Stunden, nicht den Vertrag. Ihn
    als Abrechnung zu nehmen, hieße: der abgeleitete Aufschlag springt jeden
    Tag, bis der Monat vorbei ist.
    """
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, vertragsart="dynamisch", gueltig_ab=date(2026, 1, 1))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=HEUTE.year, monat=HEUTE.month,
                       netzbezug_kwh=300.0, netzbezug_durchschnittspreis_cent=27.66))
    tag = HEUTE.replace(day=1)
    while tag <= HEUTE:
        for h in range(24):
            db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=tag, stunde=h,
                                      netzbezug_kw=1.0, boersenpreis_cent=8.0))
        tag += timedelta(days=1)
    await db.commit()

    _stelle(monkeypatch, _prognose(), _preis(preise={JETZT.hour: 5.0}))
    sv = await _rechne(db, anlage)

    preis = sv["eedc_bezugspreis_jetzt_cent"]
    assert preis.zusatz_attribute["aufschlag_quelle"] == "keiner", (
        "der laufende Monat darf keinen Aufschlag begründen"
    )
    assert preis.zusatz_attribute["preisquelle"] == "boersenpreis"


async def test_dynamisch_mit_zeitfenstern_nimmt_die_boerse_und_sagt_es(db, monkeypatch):
    """Mischform: der Marktpreis ist die Wirklichkeit, gepflegte Fenster sind Altlast."""
    from backend.models.strompreis import StrompreisZeitfenster

    anlage = await _anlage(db)
    tarif = await _tarif(db, anlage.id, bezug=30.0, vertragsart="dynamisch")
    db.add(StrompreisZeitfenster(
        strompreis_id=tarif.id, von_stunde=22, bis_stunde=6,
        arbeitspreis_cent_kwh=21.0,
    ))
    await db.commit()

    _stelle(monkeypatch, _prognose(), _preis(preise={JETZT.hour: 7.0}))
    sv = await _rechne(db, anlage)

    preis = sv["eedc_bezugspreis_jetzt_cent"]
    assert preis.value == 7.0
    assert preis.zusatz_attribute["preisquelle"] == "boersenpreis"
    assert preis.zusatz_attribute["zeitfenster_ignoriert"] is True


async def test_dynamisch_ohne_boerse_kein_preis(db, monkeypatch):
    """Der Börsenabruf ist ausgefallen — dann gibt es für einen dynamischen Tarif nichts."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, vertragsart="dynamisch")
    _stelle(monkeypatch, _prognose(), None)
    sv = await _rechne(db, anlage)

    assert "eedc_bezugspreis_jetzt_cent" not in sv
    # Die Vergütung hängt nicht an der Börse und bleibt.
    assert sv["eedc_einspeiseverguetung_cent"].value == 8.0


async def test_nur_wp_tarif_ohne_allgemeinen(db, monkeypatch):
    """⭐ `allgemein` bleibt `None`, die Wärmepumpe hat trotzdem einen Preis.

    `tarife_zum_stichtag` lässt den Fallback nur in **eine** Richtung laufen
    (WP → allgemein). Ohne allgemeine Zeile gibt es anlagenweit keinen Preis —
    das Heizfenster muss es trotzdem geben.
    """
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, verwendung="waermepumpe", bezug=22.0)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    assert "eedc_bezugspreis_jetzt_cent" not in sv, "kein allgemeiner Tarif, kein anlagenweiter Preis"

    from backend.api.routes.ha_export import calculate_anlage_sensors
    kontext: dict = {}
    await calculate_anlage_sensors(db, anlage, skip_jitter=True, jetzt=JETZT,
                                   kontext_out=kontext)
    ctx = kontext["fenster"]
    assert ctx.hat_preis_fuer("waermepumpe") is True
    assert ctx.preis_fuer("waermepumpe")[JETZT_SLOT] == 22.0


async def test_eigener_wp_tarif_steht_als_attribut_daneben(db, monkeypatch):
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0)
    await _tarif(db, anlage.id, verwendung="waermepumpe", bezug=22.0)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    preis = sv["eedc_bezugspreis_jetzt_cent"]
    assert preis.value == 30.0
    assert preis.zusatz_attribute["waermepumpe_cent"] == 22.0


async def test_ohne_eigenen_wp_tarif_kein_zweiter_wert(db, monkeypatch):
    """Eine zweite Zahl, die dieselbe ist, ist keine Information — sondern eine Frage."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    assert "waermepumpe_cent" not in sv["eedc_bezugspreis_jetzt_cent"].zusatz_attribute


# ═══════════════════════════════════════════════════════════════════════════
# 2 · Vergütung
# ═══════════════════════════════════════════════════════════════════════════

async def test_variable_verguetung_ohne_monatswert_gibt_es_nicht(db, monkeypatch):
    """#392: Wer „variabel" gepflegt hat, sagt damit, dass der Stammwert den Monat nicht beschreibt.

    Ihn trotzdem auszugeben wäre die stille Ersetzung, gegen die Flex §8 steht.
    """
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, verguetung=8.0, variabel=True)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    assert "eedc_einspeiseverguetung_cent" not in sv
    assert "eedc_eigenverbrauch_wert_cent" not in sv
    grund = sv["eedc_bezugspreis_jetzt_cent"].zusatz_attribute["verguetung_grund"]
    assert "variable Vergütung" in grund and "2026-09" in grund


async def test_variable_verguetung_mit_monatswert(db, monkeypatch):
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0, verguetung=8.0, variabel=True)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=HEUTE.year, monat=HEUTE.month,
                       einspeise_durchschnittspreis_cent=6.4))
    await db.commit()
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    verg = sv["eedc_einspeiseverguetung_cent"]
    assert verg.value == 6.4, "der Monatswert, nicht der Stammwert 8,0"
    assert verg.zusatz_attribute["verguetung_quelle"] == "monatswert"
    assert sv["eedc_eigenverbrauch_wert_cent"].value == 23.6    # 30,0 − 6,4


async def test_null_cent_verguetung_ist_ein_wert(db, monkeypatch):
    """Volleinspeisung ohne Vergütung: `is not None`, nie truthy."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0, verguetung=0.0)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    assert sv["eedc_einspeiseverguetung_cent"].value == 0.0
    assert sv["eedc_eigenverbrauch_wert_cent"].value == 30.0


# ═══════════════════════════════════════════════════════════════════════════
# 3 · Speicherkosten und der Wirkungsgrad
# ═══════════════════════════════════════════════════════════════════════════

async def test_ohne_speicher_keine_speicherkosten(db, monkeypatch):
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, verguetung=8.0)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    assert "eedc_speicher_strom_kosten_cent" not in sv
    assert "eedc_speicher_netzladen_kosten_cent" not in sv


async def test_gemessener_wirkungsgrad_schlaegt_den_gepflegten(db, monkeypatch):
    """34 Monate mit 100/85 kWh ⇒ 85,0 % gemessen, nicht die gepflegten 95."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0, verguetung=8.5)
    await _speicher(db, anlage.id, eta=95.0, imd_monate=34, ladung=100.0, entladung=85.0)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    kosten = sv["eedc_speicher_strom_kosten_cent"]
    assert kosten.zusatz_attribute["wirkungsgrad_prozent"] == 85.0
    assert kosten.zusatz_attribute["wirkungsgrad_quelle"] == "gemessen"
    assert kosten.zusatz_attribute["wirkungsgrad_messung"] == "fenster_lang"
    assert kosten.value == 10.0, "8,5 ÷ 0,85"
    assert sv["eedc_speicher_netzladen_kosten_cent"].value == 35.29   # 30,0 ÷ 0,85


async def test_zu_wenig_monate_faellt_auf_den_parameter_und_sagt_warum(db, monkeypatch):
    """Kein stummer Fallback: `wirkungsgrad_messung` nennt den Grund (Flex §8)."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, verguetung=9.0)
    await _speicher(db, anlage.id, eta=90.0, imd_monate=0)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    kosten = sv["eedc_speicher_strom_kosten_cent"]
    assert kosten.zusatz_attribute["wirkungsgrad_quelle"] == "parameter"
    assert kosten.zusatz_attribute["wirkungsgrad_messung"] == "zu-wenig-monate"
    assert kosten.value == 10.0     # 9,0 ÷ 0,90


async def test_eta_ueber_100_prozent_ist_nicht_ermittelbar(db, monkeypatch):
    """#281: ein Wert über 100 % sagt nichts über den Speicher, sondern über die Mengen."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, verguetung=8.0)
    await _speicher(db, anlage.id, eta=80.0, imd_monate=34, ladung=100.0, entladung=110.0)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    kosten = sv["eedc_speicher_strom_kosten_cent"]
    assert kosten.zusatz_attribute["wirkungsgrad_messung"] == "nicht-ermittelbar"
    assert kosten.zusatz_attribute["wirkungsgrad_quelle"] == "parameter"
    assert kosten.value == 10.0     # 8,0 ÷ 0,80


async def test_zwei_speicher_einer_ohne_eta_ergibt_keinen_sensor(db, monkeypatch):
    """⭐ `None`, sobald ein Glied unbekannt ist — nicht „das Minimum der bekannten".

    Sonst stünde eine Zahl, die für die halbe Kapazität nichts aussagt.
    """
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, verguetung=8.0)
    await _speicher(db, anlage.id, eta=90.0, imd_monate=34)
    # Der zweite: gepflegter Wirkungsgrad ausdrücklich ENTFERNT.
    zwei = Investition(
        anlage_id=anlage.id, bezeichnung="Speicher 2", typ="speicher", aktiv=True,
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter={"kapazitaet_kwh": 5.0},
    )
    db.add(zwei)
    await db.commit()

    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    assert "eedc_speicher_strom_kosten_cent" not in sv
    assert "eedc_speicher_netzladen_kosten_cent" not in sv


async def test_netzladen_nur_mit_laedt_aus_netz(db, monkeypatch):
    """Dasselbe Gate wie P3 — ein Speicher, der nie aus dem Netz lädt, hat keine Ladekosten."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0, verguetung=8.0)
    await _speicher(db, anlage.id, eta=90.0, imd_monate=0, laedt_aus_netz=False)
    _stelle(monkeypatch, _prognose(), _preis())
    sv = await _rechne(db, anlage)

    assert "eedc_speicher_strom_kosten_cent" in sv, "die PV-Seite gibt es trotzdem"
    assert "eedc_speicher_netzladen_kosten_cent" not in sv


async def test_p3_ohne_belastbaren_wirkungsgrad_entfaellt(db, monkeypatch):
    """Der Arbitrage-Vorschlag ist eine Differenz ÜBER η — ohne η keine Zahl."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0)
    speicher = Investition(
        anlage_id=anlage.id, bezeichnung="Speicher ohne η", typ="speicher", aktiv=True,
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter={"kapazitaet_kwh": 10.0, "laedt_aus_netz": True},
    )
    db.add(speicher)
    await db.commit()

    _stelle(monkeypatch, _prognose(speicher_soc_prozent=10.0),
            _preis(preise={2: 3.0, 3: 3.0, 18: 45.0, 19: 45.0}))
    sv = await _rechne(db, anlage, jetzt=datetime(2026, 9, 22, 1, 0))

    assert "eedc_arbitrage_vorschlag_kwh" not in sv


# ═══════════════════════════════════════════════════════════════════════════
# 4 · Leer um / reicht bis Mitternacht — eine Regel, ein Lauf
# ═══════════════════════════════════════════════════════════════════════════

def _sim(soc_je_stunde: dict, start: int) -> dict:
    return _prognose(
        speicher_soc_pro_stunde=soc_je_stunde,
        speicher_sim_start_stunde=start,
        speicher_end_soc_prozent=soc_je_stunde[max(soc_je_stunde)],
    )


async def test_uebergang_in_den_leerstand_ergibt_leer_um_und_reicht_aus(db, monkeypatch):
    """Sim ab 09:00, SoC > 2 % um 09:00, ≤ 2 % um 10:00 ⇒ `leer_um` 10:00, `reicht` AUS."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    soc = {h: (50.0 if h <= 9 else 1.0) for h in range(9, 24)}
    _stelle(monkeypatch, _sim(soc, start=9), _preis())
    sv = await _rechne(db, anlage, jetzt=datetime(2026, 9, 22, 9, 30))

    assert sv["eedc_speicher_leer_um_ts"].value[11:16] == "10:00"
    assert sv["eedc_speicher_reicht_bis_mitternacht"].value is False


async def test_start_slot_leer_aber_pv_fuellt_wieder_auf(db, monkeypatch):
    """⭐ Ü1 — genau der Fall, an dem die erste Regelfassung gescheitert wäre.

    Der Speicher ist **jetzt** leer (der Start-Slot ist die abgelaufene Stunde),
    die PV füllt ihn bis 11 Uhr, am Ende stehen 60 %. Eine Regel „erster Slot
    ab jetzt ≤ 2 %" hätte „leer um" in die **Vergangenheit** gemeldet und
    daneben „reicht: AUS" — während „voll um 11:00" danebensteht.
    """
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    # ⚠ Der Speicher bleibt noch EINE Stunde leer, bevor die PV greift — genau
    # so sieht ein Morgen aus. Eine Regel „erster Slot ab jetzt ≤ 2 %" würde
    # hier 10:00 melden; die Übergangsregel sieht keinen Übergang (vorher war
    # er schon leer) und meldet richtig gar nichts.
    soc = {9: 1.0, 10: 1.0, 11: 98.0, **{h: 60.0 for h in range(12, 24)}}
    _stelle(monkeypatch, _sim(soc, start=9), _preis())
    sv = await _rechne(db, anlage, jetzt=datetime(2026, 9, 22, 9, 30))

    assert "eedc_speicher_leer_um_ts" not in sv, "kein Übergang nach dem Start ⇒ kein Wert"
    assert sv["eedc_speicher_reicht_bis_mitternacht"].value is True
    assert sv["eedc_speicher_reicht_bis_mitternacht"].zusatz_attribute["end_soc_prozent"] == 60.0


async def test_start_slot_leer_und_bleibt_leer(db, monkeypatch):
    """Kein Übergang, aber der End-Ladestand liegt unter der Schwelle ⇒ `reicht` AUS."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    soc = {h: 1.0 for h in range(9, 24)}
    _stelle(monkeypatch, _sim(soc, start=9), _preis())
    sv = await _rechne(db, anlage, jetzt=datetime(2026, 9, 22, 9, 30))

    assert "eedc_speicher_leer_um_ts" not in sv
    assert sv["eedc_speicher_reicht_bis_mitternacht"].value is False


async def test_ohne_simulation_gibt_es_beide_nicht(db, monkeypatch):
    """Kein Speicher oder kein Ladestand ⇒ kein Lauf ⇒ keine Sensoren."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    _stelle(monkeypatch, _prognose(speicher_soc_pro_stunde=None), _preis())
    sv = await _rechne(db, anlage)

    assert "eedc_speicher_leer_um_ts" not in sv
    assert "eedc_speicher_reicht_bis_mitternacht" not in sv


async def test_leer_und_voll_kommen_aus_demselben_lauf(db, monkeypatch):
    """`eedc_speicher_voll_um_ts` bleibt unberührt — eine Simulation, drei Fragen."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    soc = {9: 50.0, 10: 98.5, **{h: 99.0 for h in range(11, 24)}}
    prognose = _sim(soc, start=9)
    prognose["speicher_voll_um_slot"] = 10
    _stelle(monkeypatch, prognose, _preis())
    sv = await _rechne(db, anlage, jetzt=datetime(2026, 9, 22, 9, 30))

    assert sv["eedc_speicher_voll_um_ts"].value[11:16] == "10:00"
    assert sv["eedc_speicher_reicht_bis_mitternacht"].value is True
    assert "eedc_speicher_leer_um_ts" not in sv


# ═══════════════════════════════════════════════════════════════════════════
# 5 · Abregelung und §51
# ═══════════════════════════════════════════════════════════════════════════

async def test_abregelung_null_ist_ein_wert(db, monkeypatch):
    """**0 ist ein Wert** (ADR-002/P4): „heute wird nichts abgeregelt" ist eine Aussage."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    _stelle(monkeypatch, _prognose(
        abregelung_om_kwh=0.0,
        abregelung_om_stundenprofil_kwh=[0.0] * 24,
        abregelung_grenzen_kw={"wr-1": 8.0},
    ), _preis())
    sv = await _rechne(db, anlage)

    ab = sv["eedc_abregelung_heute_kwh"]
    assert ab.value == 0.0
    assert ab.zusatz_attribute["skala"] == "openmeteo_roh_vor_korrektur"
    assert ab.zusatz_attribute["grenzen_kw"] == {"wr-1": 8.0}


async def test_ohne_kappung_gibt_es_den_sensor_nicht(db, monkeypatch):
    """„An dieser Anlage wird gar nicht gekappt" ist keine 0, sondern kein Sensor."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    _stelle(monkeypatch, _prognose(abregelung_om_kwh=None), _preis())
    sv = await _rechne(db, anlage)

    assert "eedc_abregelung_heute_kwh" not in sv


async def test_einspeisung_unerwuenscht_braucht_beide_bedingungen(db, monkeypatch):
    """Negative Börse **und** erwartete Erzeugung derselben Stunde (§51 als Slot-Regel)."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    pv = [0.0] * JETZT_SLOT + [4.0] + [0.0] * (23 - JETZT_SLOT)
    _stelle(monkeypatch, _prognose(stundenprofil_heute=pv),
            _preis(preise={JETZT.hour: -2.5}))
    sv = await _rechne(db, anlage)

    un = sv["eedc_einspeisung_unerwuenscht"]
    assert un.value is True
    assert un.zusatz_attribute["boersenpreis_cent"] == -2.5
    assert un.zusatz_attribute["pv_prognose_kwh"] == 4.0
    assert un.zusatz_attribute["negative_stunden_heute"] == 1


async def test_negative_boerse_ohne_erzeugung_ist_nicht_unerwuenscht(db, monkeypatch):
    """Nachts um drei ist ein negativer Preis eine gute Nachricht, keine Warnung."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    _stelle(monkeypatch, _prognose(stundenprofil_heute=[0.0] * 24),
            _preis(preise={JETZT.hour: -2.5}))
    sv = await _rechne(db, anlage)

    assert sv["eedc_einspeisung_unerwuenscht"].value is False


async def test_unerwuenscht_ist_nicht_tarifgebunden(db, monkeypatch):
    """§51 trifft jede Anlage in der Direktvermarktung — auch eine mit Festtarif."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=31.95, vertragsart="fest")
    pv = [0.0] * JETZT_SLOT + [4.0] + [0.0] * (23 - JETZT_SLOT)
    _stelle(monkeypatch, _prognose(stundenprofil_heute=pv),
            _preis(preise={JETZT.hour: -2.5}))
    sv = await _rechne(db, anlage)

    assert sv["eedc_einspeisung_unerwuenscht"].value is True
    assert sv["eedc_bezugspreis_jetzt_cent"].zusatz_attribute["preisquelle"] == "vertrag"


async def test_ohne_boerse_gibt_es_den_schalter_nicht(db, monkeypatch):
    """Ein `binary_sensor` ohne Grundlage wird nicht verfügbar — er entsteht hier nicht."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id)
    _stelle(monkeypatch, _prognose(), None)
    sv = await _rechne(db, anlage)

    assert "eedc_einspeisung_unerwuenscht" not in sv


# ═══════════════════════════════════════════════════════════════════════════
# 6 · Der Publish-Zähler — einmal je Lauf, nicht einmal je Sensor
# ═══════════════════════════════════════════════════════════════════════════

async def test_ein_lauf_holt_jeden_eingang_genau_einmal(db, monkeypatch):
    """⭐ Zwei Phasen brauchen dieselben Eingänge — geholt werden sie **einmal**.

    Gezählt werden: die Tarif-Ladung, der IMD-Select des η-Laders und die
    Aufschlag-Ableitung. Zwei Beschaffungen wären zwei Wahrheiten über denselben
    Moment **und** eine zweite Runde Abfragen bei jedem Publish-Takt.
    """
    from backend.api.routes import strompreise as sp_modul
    from backend.services import ha_export_bezugspreis as hb
    from backend.api.routes.ha_export import anlage_preise_speicher as aps

    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0)
    await _speicher(db, anlage.id, imd_monate=34)
    _stelle(monkeypatch, _prognose(), _preis())

    zaehler = {"tarife": 0, "aufschlag": 0, "eta": 0}
    echt_tarife = sp_modul.lade_tarife_je_stichtag
    echt_aufschlag = hb.lade_aufschlag
    echt_eta = aps.lade_speicher_wirkungsgrade

    async def _t(*a, **kw):
        zaehler["tarife"] += 1
        return await echt_tarife(*a, **kw)

    async def _a(*a, **kw):
        zaehler["aufschlag"] += 1
        return await echt_aufschlag(*a, **kw)

    async def _e(*a, **kw):
        zaehler["eta"] += 1
        return await echt_eta(*a, **kw)

    monkeypatch.setattr(sp_modul, "lade_tarife_je_stichtag", _t)
    monkeypatch.setattr(hb, "lade_aufschlag", _a)
    monkeypatch.setattr("backend.api.routes.ha_export.anlage_sensoren.preise_speicher_sensoren",
                        aps.preise_speicher_sensoren)
    monkeypatch.setattr(aps, "lade_speicher_wirkungsgrade", _e)

    await _rechne(db, anlage)

    assert zaehler["tarife"] == 1, "eine Tarif-Ladung für heute UND morgen"
    assert zaehler["aufschlag"] == 1
    assert zaehler["eta"] == 1, "ein IMD-Select je Lauf, nicht einer je Sensor"


async def test_der_aufschlag_wird_im_prozess_gemerkt(db, monkeypatch):
    """Zwei Publish-Läufe derselben Minute leiten den Aufschlag **einmal** ab."""
    from backend.services import ha_export_bezugspreis as hb

    anlage = await _anlage(db)
    await _tarif(db, anlage.id, vertragsart="dynamisch", gueltig_ab=date(2026, 1, 1))
    _stelle(monkeypatch, _prognose(), _preis())

    zaehler = {"n": 0}
    echt = hb._aufschlag_aus_abrechnung

    async def _z(*a, **kw):
        zaehler["n"] += 1
        return await echt(*a, **kw)

    monkeypatch.setattr(hb, "_aufschlag_aus_abrechnung", _z)

    await _rechne(db, anlage)
    await _rechne(db, anlage)
    assert zaehler["n"] == 1, "der zweite Lauf nimmt den gemerkten Wert"


async def test_markt_api_wird_hoechstens_einmal_je_monat_gefragt(db, monkeypatch):
    """Ein Monat ohne Börsenarchiv darf nicht bei jedem Takt erneut abgefragt werden.

    ⛔ **Fake-Client, nie die echte API** — und er zählt mit.
    """
    from backend.services import ha_export_bezugspreis as hb

    anlage = await _anlage(db)
    await _tarif(db, anlage.id, vertragsart="dynamisch", gueltig_ab=date(2026, 1, 1))
    # Ein Abrechnungsmonat MIT Ø, aber OHNE Börsenstunden ⇒ Nachholen wird versucht.
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=8,
                       netzbezug_kwh=744.0, netzbezug_durchschnittspreis_cent=27.66))
    tag = date(2026, 8, 1)
    while tag.month == 8:
        for h in range(24):
            db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=tag, stunde=h,
                                      netzbezug_kw=1.0))
        tag += timedelta(days=1)
    await db.commit()

    abrufe = {"n": 0}

    async def _fake(datum, markt="DE", timeout=15.0):
        abrufe["n"] += 1
        return {h: 8.0 for h in range(24)}

    monkeypatch.setattr("backend.services.strompreis_markt_service.fetch_marktpreise", _fake)
    _stelle(monkeypatch, _prognose(), _preis(preise={JETZT.hour: 5.0}))

    sv = await _rechne(db, anlage)
    erster_lauf = abrufe["n"]
    assert erster_lauf == 31, "einmal je Tag des Abrechnungsmonats"
    assert sv["eedc_bezugspreis_jetzt_cent"].zusatz_attribute["aufschlag_quelle"] == "abrechnung 2026-08"

    # Cache leeren, damit der Aufschlag neu abgeleitet WÜRDE — der Monat bleibt gesperrt.
    from backend.services import ha_export_bezugspreis as hb2
    hb2._aufschlag_cache.clear()
    await _rechne(db, anlage)
    assert abrufe["n"] == erster_lauf, "kein zweiter Marktabruf für denselben Monat"


# ═══════════════════════════════════════════════════════════════════════════
# 7 · Ohne Koordinaten
# ═══════════════════════════════════════════════════════════════════════════

async def test_ohne_koordinaten_gibt_es_die_preise_trotzdem(db, monkeypatch):
    """Ü3: keine Börse, keine Prognose, keine Sim — der Festtarif-Preis bleibt.

    Er hängt an keiner externen Quelle: `preis_je_slot` braucht nur ein Datum.
    """
    anlage = await _anlage(db, koordinaten=False)
    await _tarif(db, anlage.id, bezug=31.95, verguetung=8.0)
    await _speicher(db, anlage.id, eta=90.0, imd_monate=0)
    _stelle(monkeypatch, None, None)
    sv = await _rechne(db, anlage)

    assert sv["eedc_bezugspreis_jetzt_cent"].value == 31.95
    assert sv["eedc_eigenverbrauch_wert_cent"].value == 23.95
    assert sv["eedc_speicher_strom_kosten_cent"].value == 8.89      # 8,0 ÷ 0,90
    # …aber nichts, was an Börse oder Prognose hängt.
    assert "eedc_einspeisung_unerwuenscht" not in sv
    assert "eedc_abregelung_heute_kwh" not in sv
    assert "eedc_speicher_leer_um_ts" not in sv


# ═══════════════════════════════════════════════════════════════════════════
# 8 · Tarifwechsel morgen (Ü2)
# ═══════════════════════════════════════════════════════════════════════════

async def test_tarifwechsel_morgen_steht_in_der_morgen_reihe(db, monkeypatch):
    """Ein Fenster über Mitternacht sieht den Sprung — sonst stünde morgen der Preis von heute."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0, gueltig_ab=date(2023, 1, 1),
                 gueltig_bis=HEUTE)
    await _tarif(db, anlage.id, bezug=34.0, gueltig_ab=HEUTE + timedelta(days=1))
    _stelle(monkeypatch, _prognose(), _preis(morgen=True))
    sv = await _rechne(db, anlage)

    preis = sv["eedc_bezugspreis_jetzt_cent"]
    assert preis.value == 30.0, "heute gilt der alte Tarif"
    assert preis.zusatz_attribute["stundenprofil_cent"][12] == 30.0
    assert preis.zusatz_attribute["stundenprofil_morgen_cent"][12] == 34.0
