"""Eine Zeile, zwei Uhren — und wer paart, rechnet um (N-387).

**Der Befund** (Inventur zu N-382, vorgelegt 22.09.2026): In einer
``TagesEnergieProfil``-Zeile liegen alle ``*_kw``-Spalten **backward**
(Zeile ``s`` = Intervall ``[s-1, s)``), aber ``soc_prozent`` /
``soc_je_speicher`` / ``strompreis_cent`` / ``boersenpreis_cent`` **forward**
(Zeile ``s`` = ``[s, s+1)``). Zehn Stellen in sieben Dateien stellten beide
Hälften **derselben Zeile** nebeneinander und verrechneten sie:

* das Speicher-**Potential** zählte die Einspeisung der Stunde **vor** dem
  Vollwerden als „Überschuss bei vollem Speicher",
* das **Sizing** kalibrierte gegen den Ladestand der Nachbarstunde,
* der effektive **Ladepreis** (und der Entladewert) zahlte den Preis der
  Nachbarstunde — auf einem dynamischen Tarif die volle Differenz,
* **Monats-Ø-Preis**, **Slot-Kosten je Tag** (Flex-Kaskade: Tageskosten,
  EV-Ersparnis) und der **§51-Einspeiseerlös** ebenso.

Geprüft wird hier die **eine** Umrechnung
(``slot_konvention.forward_werte_je_backward_zeile``) und ihre Wirkung an den
Konsumenten. Schwesterdateien: ``test_slot_konvention_quellen.py`` (dass alle
Quellen dasselbe Backward-Raster treffen), ``test_slot_konvention_leistungspfad.py``
(N-382, die fünfte Bahn), ``test_n544_*`` (dieselbe Klasse im HA-Export).

⚠ **Die Saat beschreibt Stunden, nicht Zeilen** — gemeinsamer Helfer
``tests/slot_saat.py``. Eine Probe, die Menge und Preis in dieselbe Zeile legt,
prüft den Versatz, den sie widerlegen soll.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.core.berechnungen.slot_konvention import (
    SLOT_PAARUNG_VORZEILE_AB,
    forward_werte_je_backward_zeile,
)
from backend.models import Anlage, Investition, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.speicher_potential_service import lade_potential_auswertung
from backend.services.speicher_sizing_service import _als_sizing_stunde
from backend.services.speicher_wirtschaftlichkeit import berechne_effektiver_ladepreis
from backend.services.strompreis_aggregator import (
    berechne_monats_durchschnittspreis,
    lade_preis_aggregate_je_monat,
    lade_slot_kosten_je_tag,
)
from backend.tests.slot_saat import tep_zeilen

TAG = date(2026, 5, 10)
#: Nach der Bestandsgrenze — der Normalfall. Fest statt `datetime.now()` (N-167).
AGGREGIERT_AM = datetime(2026, 7, 1, 12, 0)


class _Zeile:
    """Das Nötigste für den Helfer: Datum, Stunde, Schreibzeit, ein Feld."""

    def __init__(self, tag: date, stunde: int, wert, created_at=AGGREGIERT_AM):
        self.datum, self.stunde, self.wert, self.created_at = tag, stunde, wert, created_at


# ---------------------------------------------------------------------------
# B1 — der Helfer selbst
# ---------------------------------------------------------------------------

class TestDerHelfer:
    def test_die_erste_zeile_hat_keine_vorzeile(self):
        """Kein Wert ist besser als der eigene — sonst bliebe der alte Versatz."""
        zeilen = [_Zeile(TAG, 5, 10.0), _Zeile(TAG, 6, 20.0)]
        assert forward_werte_je_backward_zeile(zeilen, "wert") == [None, 10.0]

    def test_ueber_die_tagesgrenze_gilt_die_23_des_vortags(self):
        zeilen = [_Zeile(TAG - timedelta(days=1), 23, 99.0), _Zeile(TAG, 0, 11.0)]
        assert forward_werte_je_backward_zeile(zeilen, "wert") == [None, 99.0]

    def test_eine_luecke_liefert_none_und_nicht_den_naechstbesten(self):
        """⛔ Keine stille Nachbar-Übernahme: der Preis der übernächsten Stunde
        ist keine Messung dieser Stunde."""
        zeilen = [_Zeile(TAG, 5, 10.0), _Zeile(TAG, 8, 20.0), _Zeile(TAG, 9, 30.0)]
        assert forward_werte_je_backward_zeile(zeilen, "wert") == [None, None, 20.0]

    def test_ein_tagessprung_ist_auch_eine_luecke(self):
        zeilen = [_Zeile(TAG, 23, 10.0), _Zeile(TAG + timedelta(days=2), 0, 20.0)]
        assert forward_werte_je_backward_zeile(zeilen, "wert") == [None, None]

    def test_altbestand_bleibt_bei_der_zeilen_paarung(self):
        """Vor `SLOT_PAARUNG_VORZEILE_AB` lagen die `*_kw` selbst forward.

        Entschieden wird an der **Aggregationszeit** der Zeile, nicht an ihrem
        Datum: `aggregate_day` löscht den Tag und schreibt ihn neu — *neu
        aggregieren stellt einen alten Tag um*.
        """
        alt = datetime.combine(SLOT_PAARUNG_VORZEILE_AB - timedelta(days=1), datetime.min.time())
        zeilen = [_Zeile(TAG, 5, 10.0, alt), _Zeile(TAG, 6, 20.0, alt)]
        assert forward_werte_je_backward_zeile(zeilen, "wert") == [10.0, 20.0]

    def test_ohne_schreibzeit_entscheidet_das_datum(self):
        zeilen = [_Zeile(date(2026, 1, 5), 5, 10.0, None), _Zeile(date(2026, 1, 5), 6, 20.0, None)]
        assert forward_werte_je_backward_zeile(zeilen, "wert") == [10.0, 20.0]


# ---------------------------------------------------------------------------
# B2 — Speicher-Potential und Sizing
# ---------------------------------------------------------------------------

async def _anlage_mit_speicher(db, *, kapazitaet=10.0) -> int:
    anlage = Anlage(anlagenname="N-387", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"kapazitaet_kwh": kapazitaet},
    ))
    await db.flush()
    return anlage.id


async def _saee(db, anlage_id: int, stunden: list[dict]):
    db.add_all(tep_zeilen(anlage_id, stunden, created_at=AGGREGIERT_AM))
    await db.flush()


@pytest.mark.asyncio
async def test_der_ueberschuss_zaehlt_erst_ab_der_stunde_nach_dem_vollwerden(db):
    """⭐ Der Kern am Potential: voll wird der Speicher **in** Stunde 11.

    Die Einspeisung von Stunde 11 (Backward-Slot 11 = ``[10, 11)``) fiel an,
    **während** noch geladen wurde — sie ist kein Überschuss bei vollem
    Speicher. Erst die Stunden 12 und 13 zählen. Vor diesem Bau waren es 11,
    12 und 13, also eine Stunde Einspeisung zu viel.
    """
    anlage_id = await _anlage_mit_speicher(db)
    # Voll wird der Speicher am Ende der Stunde 11; die Einspeisung steigt mit
    # jeder Stunde, damit eine Verschiebung des Fensters die **Summe** ändert
    # und nicht nur ihre Zusammensetzung.
    await _saee(db, anlage_id, [
        {"datum": TAG, "stunde": h, "soc_prozent": soc, "einspeisung_kw": einsp,
         "netzbezug_kw": 0.0}
        for h, soc, einsp in (
            (10, 80.0, 1.0), (11, 80.0, 2.0), (12, 100.0, 4.0), (13, 100.0, 8.0),
        )
    ])

    erg = await lade_potential_auswertung(db, anlage_id, kapazitaet_brutto_kwh=10.0)

    assert erg.gesamt.stunden_voll == 2, "die Stunden 12 und 13"
    assert erg.gesamt.ueberschuss_gesamt_kwh == pytest.approx(12.0), (
        "4 + 8 kWh — mit der Zeilen-Paarung wären es 2 + 4 = 6 kWh gewesen, "
        "also das Fenster um eine Stunde nach vorn"
    )


@pytest.mark.asyncio
async def test_die_fehlmenge_spiegelt_den_versatz_auf_der_leeren_seite(db):
    """Dasselbe umgekehrt: der Netzbezug der Stunde, **in** der er leerläuft,
    zählt noch nicht als Fehlmenge."""
    anlage_id = await _anlage_mit_speicher(db)
    # Eine Fehlmenge gibt es nur nach einem Überschuss (Layer-Regel) — deshalb
    # erst der volle Mittag, dann die Nacht, in der der Speicher leerläuft.
    await _saee(db, anlage_id, [
        {"datum": TAG, "stunde": h, "soc_prozent": soc,
         "einspeisung_kw": einsp, "netzbezug_kw": netz}
        for h, soc, einsp, netz in (
            (11, 80.0, 5.0, 0.0), (12, 100.0, 5.0, 0.0), (13, 100.0, 5.0, 0.0),
            (20, 30.0, 0.0, 1.0), (21, 30.0, 0.0, 2.0),
            (22, 2.0, 0.0, 4.0), (23, 2.0, 0.0, 8.0),
        )
    ])

    erg = await lade_potential_auswertung(db, anlage_id, kapazitaet_brutto_kwh=10.0)

    (zyklus,) = erg.gesamt.zyklen
    assert zyklus.lief_leer is True
    assert zyklus.fehlmenge_kwh == pytest.approx(12.0), (
        "4 + 8 kWh in den Stunden 22 und 23 — leer wird der Speicher erst am "
        "Ende der 21 (mit der Zeilen-Paarung wären es 2 + 4 + 8 = 14 kWh)"
    )


@pytest.mark.asyncio
async def test_die_monatsanteile_tragen_dieselbe_uhr_wie_die_stundenzaehler(db):
    """G4: `anteil_voll` zählt die Ladestände, die der Layer daneben bewertet."""
    anlage_id = await _anlage_mit_speicher(db)
    await _saee(db, anlage_id, [
        {"datum": TAG, "stunde": h, "soc_prozent": soc, "einspeisung_kw": 4.0,
         "netzbezug_kw": 0.0}
        for h, soc in ((10, 80.0), (11, 80.0), (12, 100.0), (13, 100.0))
    ])

    erg = await lade_potential_auswertung(db, anlage_id, kapazitaet_brutto_kwh=10.0)

    (monat,) = erg.monate
    assert monat.stunden_voll == 2
    assert monat.stunden_mit_soc == 4
    assert monat.anteil_voll_prozent == 50.0, "2 von 4 — dieselbe Zählung wie oben"


def test_die_sizing_kalibrierung_entscheidet_die_paarung_nicht():
    """⛔ Die **zweite** benannte Ausnahme — und zwar aus einem eigenen Grund.

    `kalibriere_speicher` **paart** nicht, es bildet eine *Differenz zweier
    Stundenmittel* und stellt sie einer **einzelnen** Stundenmenge gegenüber:
    `ΔSoC(s−1 → s) ≈ ½ (b_s + b_{s+1})`, verglichen wird `b_s` allein.

    **Gemessen** (23.09.2026, **reine** Demo-Reihe — 4 800 Stunden, alle mit
    forward-Stundenmittel geseedet; Wahrheit 10,0 kWh je 100 % SoC,
    Roundtrip 1,00):

    * Zeilen-Paarung: 10,03 / 11,11, Roundtrip 1,108 ⇒ **None**
    * Vorzeile: 12,44 / 13,62, Roundtrip 1,095 ⇒ **None**

    **Beide verfehlen gleich** und fallen aus dem Plausibilitätsband; am
    Endpunkt bewegt sich in keiner der beiden Fassungen eine Zahl. Die Lösung
    ist deshalb **die Formel, nicht die Paarung** — der Hub gehört gegen das
    *Mittel der zwei angrenzenden Stundenmengen*; das ist ein Layer-Eingriff
    (ADR-001) und als **eigener Fund** vorzulegen.

    Diese Probe hält fest, dass hier bewusst nichts verschoben ist — sie meldet
    rot, sobald jemand es doch tut, ohne die Formel anzufassen.
    """
    zeile = TagesEnergieProfil(
        anlage_id=1, datum=TAG, stunde=6, batterie_kw=-1.0, soc_prozent=55.0,
        created_at=AGGREGIERT_AM,
    )
    stunde = _als_sizing_stunde(zeile)

    assert stunde.soc_prozent == 55.0, "der Ladestand DIESER Zeile"
    assert stunde.zeit == datetime(2026, 5, 10, 6), "der Zeitstempel bleibt backward"



# ---------------------------------------------------------------------------
# B3 — die Preise
# ---------------------------------------------------------------------------

async def _anlage_mit_tarif(db, *, dynamisch: bool = True) -> int:
    anlage = Anlage(anlagenname="N-387 Preis", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        vertragsart="dynamisch" if dynamisch else None,
        verwendung="allgemein",
    ))
    await db.flush()
    return anlage.id


@pytest.mark.asyncio
async def test_die_netzladung_zahlt_den_preis_ihrer_eigenen_stunde(db):
    """Zwei Nachbarstunden, zwei Preise — geladen wird in der billigen.

    Stunde 3 lädt 2 kWh aus dem Netz und kostet 10 ct; Stunde 4 lädt nichts und
    kostet 40 ct. Vor diesem Bau bezahlte die Ladung der Stunde 3 die 40 ct der
    Stunde 4 — der ganze Unterschied zwischen billig und teuer.
    """
    anlage_id = await _anlage_mit_tarif(db)
    await _saee(db, anlage_id, [
        {"datum": TAG, "stunde": 3, "batterie_kw": -2.0, "netzbezug_kw": 2.0,
         "strompreis_cent": 10.0},
        {"datum": TAG, "stunde": 4, "batterie_kw": 0.0, "netzbezug_kw": 0.0,
         "strompreis_cent": 40.0},
    ])

    erg = await berechne_effektiver_ladepreis(db, anlage_id=anlage_id, von=TAG, bis=TAG)

    assert erg.effektiver_ladepreis_cent == pytest.approx(10.0)
    assert erg.netzlade_stunden_mit_preis == 1


@pytest.mark.asyncio
async def test_bei_festpreis_bewegt_sich_keine_zahl(db):
    """**Die Regression**: wo jede Stunde denselben Preis trägt, ändert die
    Umrechnung nichts — der Bau trifft nur dynamische Tarife."""
    anlage_id = await _anlage_mit_tarif(db, dynamisch=False)
    await _saee(db, anlage_id, [
        {"datum": TAG, "stunde": h, "batterie_kw": -1.0, "netzbezug_kw": 1.0,
         "strompreis_cent": 28.5}
        for h in range(1, 6)
    ])

    erg = await berechne_effektiver_ladepreis(db, anlage_id=anlage_id, von=TAG, bis=TAG)

    assert erg.effektiver_ladepreis_cent == pytest.approx(28.5)
    assert erg.netz_lade_kwh == pytest.approx(5.0), (
        "alle fünf Stunden — die Stunde 1 findet ihren Preis in der Zeile 0"
    )


@pytest.mark.asyncio
async def test_monats_oe_und_slot_kosten_nehmen_denselben_preis_wie_die_menge(db):
    """Beide Ebenen derselben Kaskade, beide Wege des Monats-Ø.

    Der Bezug fällt in Stunde 20 (2 kWh), der teure Preis gehört zu Stunde 19.
    Vor dem Bau kostete der Abendbezug 50 statt 20 ct.
    """
    anlage_id = await _anlage_mit_tarif(db)
    await _saee(db, anlage_id, [
        {"datum": TAG, "stunde": 19, "netzbezug_kw": 0.0, "strompreis_cent": 50.0},
        {"datum": TAG, "stunde": 20, "netzbezug_kw": 2.0, "strompreis_cent": 20.0},
    ])

    einzeln = await berechne_monats_durchschnittspreis(anlage_id, TAG.year, TAG.month, db)
    gruppe = (await lade_preis_aggregate_je_monat(db, anlage_id)).hole(TAG.year, TAG.month)
    slots = (await lade_slot_kosten_je_tag(
        db, anlage_id, von=TAG, bis=TAG, tarif_fuer=lambda _t: None,
    ))[TAG]

    assert einzeln.gewichtet_cent == pytest.approx(20.0)
    assert gruppe.gewichtet_cent == pytest.approx(20.0), "der SQL-Zwilling sagt dasselbe"
    assert slots.kosten_euro == pytest.approx(2.0 * 20.0 / 100)
    assert slots.mittel_cent == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Die benannte Ausnahme (Gegenprüfung G1)
# ---------------------------------------------------------------------------

def test_der_periodenrand_bleibt_bei_der_zeile_und_das_ist_gerechnet():
    """⛔ `_lese_soc_am_periodenrand` wird **nicht** umgestellt.

    Die Stelle paart Kalenderperioden mit **Monatsintegralen**, nicht mit
    Stundenzeilen. Als forward-Stundenmittel beschreibt Zeile 0 das Intervall
    ``[00,01)`` (Schwerpunkt 00:30, **+½ h** nach Periodenbeginn) und Zeile 23
    ``[23,24)`` (Schwerpunkt 23:30, **−½ h** vor Periodenende) — symmetrisch.
    Die Vorzeile machte aus dem Ende 22:30 (**−1½ h**) bei unverändertem Anfang
    und wäre schlechter. Diese Probe hält die Rechnung fest, damit die Ausnahme
    nicht als Versehen gelesen wird.
    """
    schwerpunkt_erste_zeile = 0.5           # h nach 00:00
    schwerpunkt_letzte_zeile = 24 - 0.5     # h nach 00:00, also 23:30
    assert schwerpunkt_erste_zeile == pytest.approx(24 - schwerpunkt_letzte_zeile)

    mit_vorzeile_letzte = 24 - 1.5          # 22:30
    assert abs(24 - mit_vorzeile_letzte) > abs(24 - schwerpunkt_letzte_zeile)


# ---------------------------------------------------------------------------
# G2 — die zwei Paarungen, die die Vorlage nicht nannte
# ---------------------------------------------------------------------------

def test_der_51er_erloes_paart_die_einspeisung_mit_dem_preis_ihrer_stunde():
    """§51 EEG: die Einspeisung des Slots `h` gegen den Börsenpreis von `h-1`.

    Die Stunde `[19, 20)` hat einen negativen Preis; ihre Einspeisung steht im
    **Backward-Slot 20**. Vor diesem Bau zählte stattdessen die Einspeisung des
    Slots 19 — also die der Stunde `[18, 19)`, die noch Geld brachte.

    Der Tages-Ø, das Minimum und die Zahl der negativen Stunden beschreiben
    dagegen den **Preistag** `[00:00, 24:00)` und bleiben unverschoben.
    """
    from backend.services.energie_profil._helpers import StrompreisStunden
    from backend.services.energie_profil.aggregator import TagesAkkumulator, tages_kennzahlen

    akku = TagesAkkumulator()
    akku.einspeisung_pro_stunde = {19: 7.0, 20: 3.0}
    preise = StrompreisStunden(sensor={}, boerse={18: 5.0, 19: -2.0, 20: 4.0})

    (_avg, _min, neg_stunden, einsp_neg_kwh, *_rest) = tages_kennzahlen(
        Anlage(anlagenname="§51", leistung_kwp=10.0), TAG, [], akku, preise,
    )

    assert neg_stunden == 1, "eine negative Preisstunde am Tag"
    assert einsp_neg_kwh == pytest.approx(3.0), (
        "die 3 kWh des Slots 20 — mit der Zeilen-Paarung wären es die 7 kWh des Slots 19"
    )


def test_der_slot_null_holt_seinen_boersenpreis_aus_dem_vortag():
    """Ohne Vortagszeile bleibt Slot 0 unbewertet — keine Nachbar-Übernahme."""
    from backend.services.energie_profil._helpers import StrompreisStunden
    from backend.services.energie_profil.aggregator import TagesAkkumulator, tages_kennzahlen

    akku = TagesAkkumulator()
    akku.einspeisung_pro_stunde = {0: 4.0}
    preise = StrompreisStunden(sensor={}, boerse={0: 9.0})
    anlage = Anlage(anlagenname="§51", leistung_kwp=10.0)

    ohne = tages_kennzahlen(anlage, TAG, [], akku, preise)[3]
    mit = tages_kennzahlen(anlage, TAG, [], akku, preise, -3.0)[3]

    assert ohne is None, "die 9 ct der eigenen Stunde 0 gelten dem Slot 1, nicht dem Slot 0"
    assert mit == pytest.approx(4.0), "der Vortag um 23 Uhr war negativ"


@pytest.mark.asyncio
async def test_der_tages_wirkungsgrad_liest_den_rand_symmetrisch(db):
    """Die Tageszeile: ΔSoC über erste/letzte Zeile gegen Σ `batterie_kw`.

    Die Mengenreihe eines Tages deckt `[Vortag 23:00, 23:00)` ab. Als
    forward-Stundenmittel beschrieb die Zeile 0 dagegen `[00,01)` — **1½ h**
    nach dem Beginn der Mengen — und die Zeile 23 `[23,24)`, also ½ h danach.
    Mit der Vorzeile sind es ½ h auf **beiden** Seiten (Zeile 0 ← Vortag 23).

    Gesät: der Speicher steht den ganzen Tag bei 50 %, nur der **Slot 1**
    (`[00:00, 01:00)`) fällt mit 90 % aus der Reihe. Sein Ladestand steht in
    der Zeile 0 — und darf den Tagesrand trotzdem nicht bestimmen, denn der
    Rand der Mengenreihe liegt bei `Vortag 23:00`.
    """
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    anlage = Anlage(anlagenname="N-387 η", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"kapazitaet_kwh": 10.0, "nutzbare_kapazitaet_kwh": 10.0},
    ))
    await db.flush()
    await _saee(db, anlage.id, [
        *[{"datum": TAG, "stunde": h, "soc_prozent": 90.0 if h == 1 else 50.0,
           "batterie_kw": (-2.0 if 10 <= h <= 14 else (2.0 if 18 <= h <= 21 else 0.0)),
           "pv_kw": 0.0, "verbrauch_kw": 0.0,
           "einspeisung_kw": 0.0, "netzbezug_kw": 0.0}
          for h in range(24)],
    ])

    (zeile,) = await baue_tage_werte(db, anlage, TAG, TAG)

    assert zeile.speicher_ladung == pytest.approx(10.0)
    assert zeile.speicher_entladung == pytest.approx(8.0)
    assert zeile.speicher_effizienz == pytest.approx(80.0), (
        "Rand 50 % → 50 % ⇒ ΔSoC 0 ⇒ 8/10. Mit der Zeilen-Paarung stünden die "
        "90 % der Zeile 0 am Anfang: ΔSoC −4 kWh ⇒ 40 %"
    )


@pytest.mark.asyncio
async def test_ohne_gemessenen_preis_wird_keine_stundenzeile_geladen(db):
    """⭐ Der Vorabtest: eine Festpreis-Anlage zahlt nichts für die Paarung.

    Die Monats-Aggregate liefern ohne gemessenen Preis **gar kein** Ergebnis.
    Seit N-387 paart der Lader in Python statt in SQL und braucht dafür die
    Stundenzeilen — an einer Anlage ohne eine einzige Preiszeile wäre das
    Ladearbeit für ein garantiert leeres Ergebnis (gemessen: 1,4 gegen 19,2 ms
    je Aufruf an einer Demo-Kopie ohne Preise). Ein ``EXISTS`` über dasselbe
    Fenster beantwortet die Frage vorher.

    Geprüft wird **beides**: dass die Zeilen-Abfrage ausbleibt (an der Spalte
    ``created_at``, die nur sie lädt) und dass das Ergebnis dasselbe ist.
    """
    from sqlalchemy import event

    anlage_id = await _anlage_mit_tarif(db, dynamisch=False)
    await _saee(db, anlage_id, [
        {"datum": TAG, "stunde": h, "netzbezug_kw": 1.0} for h in range(1, 6)
    ])

    mitschrift: list[str] = []

    def horcher(conn, cursor, statement, parameters, context, executemany):
        mitschrift.append(" ".join(statement.split()))

    event.listen(db.bind.sync_engine, "after_cursor_execute", horcher)
    try:
        einzeln = await berechne_monats_durchschnittspreis(anlage_id, TAG.year, TAG.month, db)
        gruppe = await lade_preis_aggregate_je_monat(db, anlage_id)
    finally:
        event.remove(db.bind.sync_engine, "after_cursor_execute", horcher)

    assert einzeln is None, "ohne Messung gibt es keinen Monats-Ø — wie vor N-387"
    assert len(gruppe) == 0
    zeilen_ladungen = [
        s for s in mitschrift
        if "tages_energie_profil.created_at" in s and "FROM tages_energie_profil" in s
    ]
    assert zeilen_ladungen == [], (
        "der Vorabtest hat nicht gegriffen — die Stundenzeilen wurden trotzdem geladen"
    )
