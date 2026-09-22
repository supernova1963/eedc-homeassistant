"""S3b/B1 — der Bezugspreis je Stunde: Handrechnung, Symmetrie, Degradation.

Der Layer `core/berechnungen/preis_reihe.py` + `speicher_kosten.py`. Geprüft
werden die drei Dinge, an denen eine Preisformel scheitert:

1. **Die Zahl selbst** — gegen die Handrechnung aus dem Entscheid vom 22.09.
   (Ø 27,66 · Börsenmittel 8,00 · USt 19 ⇒ Aufschlag 18,14 ⇒ eine Stunde mit
   5,00 ct Börse kostet 24,09).
2. **Die Symmetrie** — die ableitbare Reihe ist Slot für Slot dasselbe wie
   `zeittarif.preis_je_slot`. Es gibt keinen zweiten Endpreis-Rechner, und das
   ist keine Absprache, sondern Bauform.
3. **Die Ränder** — negative Börse, `None`, 0 ct, USt 20 (AT), zu wenige Paare,
   Ausreißer, 23-/25-Stunden-Tage.

Schwesterdateien: `test_s3b_preise_speicher_sensoren.py` (dieselben Formeln an
den neun Sensoren, mit Degradations-Matrix), `test_n544_fenster_achse_backward.py`
(die Achse, auf der diese Reihen liegen), `test_fenster_rechner.py` (der
Fenster-Layer, der ihre Preise mischt).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional

import pytest

from backend.core.berechnungen.preis_reihe import (
    MINDEST_PAARE,
    UST_DEFAULT_PROZENT,
    aufschlag_aus_abrechnung,
    aufschlag_aus_stunden,
    bezugspreis_reihe,
    boersenmittel_gewichtet,
    endpreis_reihe,
    ist_dynamisch,
    wert_je_kwh,
)
from backend.core.berechnungen.speicher_kosten import eta_anlage, speicher_kwh_kosten
from backend.core.berechnungen.zeittarif import preis_je_slot

HEUTE = date(2026, 9, 22)          # ein Dienstag
SAMSTAG = date(2026, 9, 26)


# ── Tarif-Attrappen (kein DB-Zugriff — der Layer braucht keinen) ────────────

@dataclass
class _Fenster:
    von_stunde: int
    bis_stunde: int
    arbeitspreis_cent_kwh: float
    nur_wochenende: bool = False

    def deckt_uhrzeit(self, zeitpunkt: datetime) -> bool:
        if self.nur_wochenende and zeitpunkt.weekday() < 5:
            return False
        h = zeitpunkt.hour
        if self.von_stunde <= self.bis_stunde:
            return self.von_stunde <= h < self.bis_stunde
        return h >= self.von_stunde or h < self.bis_stunde   # über Mitternacht


@dataclass
class _Tarif:
    netzbezug_arbeitspreis_cent_kwh: float = 30.0
    einspeiseverguetung_cent_kwh: float = 8.0
    vertragsart: Optional[str] = None
    zeitfenster: tuple = ()
    gueltig_ab: date = date(2020, 1, 1)


# ── 1 · Das Regime ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("vertragsart,erwartet", [
    ("dynamisch", True), ("fest", False), ("sondervertrag", False),
    ("", False), (None, False),
])
def test_ist_dynamisch_kennt_genau_einen_wert(vertragsart, erwartet):
    assert ist_dynamisch(_Tarif(vertragsart=vertragsart)) is erwartet


def test_ohne_tarif_ist_nichts_dynamisch():
    """`None` ist kein dynamischer Tarif — ohne Tarif gibt es gar keinen Preis."""
    assert ist_dynamisch(None) is False


def test_der_baum_hat_keinen_zweiten_diskriminator():
    """⭐ Wächter: `vertragsart == "dynamisch"` steht nirgends mehr ausgeschrieben.

    Fünf Kopien einer Ja/Nein-Frage sind fünf Stellen, an denen eine sechste
    Schreibweise vorbeigeht. Die Gegenprobe steht darunter — ein Wächter, der
    nur grün kann, beweist nichts.
    """
    import re
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1]
    muster = re.compile(r'vertragsart\s*==\s*["\']dynamisch["\']')
    erlaubt = {"core/berechnungen/preis_reihe.py"}      # die Heimat der Regel

    verstoesse = []
    for pfad in wurzel.rglob("*.py"):
        rel = pfad.relative_to(wurzel).as_posix()
        if rel.startswith("tests/") or rel.startswith("venv/") or rel in erlaubt:
            continue
        for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
            # Kommentare und Docstring-Zeilen dürfen die Regel ZITIEREN.
            nackt = zeile.strip()
            if nackt.startswith("#") or nackt.startswith("*") or "``" in zeile or "`Strompreis." in zeile:
                continue
            if muster.search(zeile):
                verstoesse.append(f"{rel}:{nr}  {nackt}")
    assert not verstoesse, (
        "Zweiter Diskriminator statt `ist_dynamisch(tarif)`:\n  " + "\n  ".join(verstoesse)
    )


def test_waechter_kann_rot_melden():
    """Gegenprobe zum Muster darüber — beide Richtungen."""
    import re
    muster = re.compile(r'vertragsart\s*==\s*["\']dynamisch["\']')
    assert muster.search('if tarif.vertragsart == "dynamisch":')
    assert muster.search("hat = t.vertragsart == 'dynamisch'")
    assert not muster.search("if ist_dynamisch(tarif):")
    assert not muster.search('if tarif.vertragsart == "fest":')


# ── 2 · Die ableitbare Reihe: Symmetrie gegen `preis_je_slot` ───────────────

@pytest.mark.parametrize("laenge", [25, 48])
def test_festpreis_reihe_ist_slot_fuer_slot_der_tarifpreis(laenge):
    tarif = _Tarif(netzbezug_arbeitspreis_cent_kwh=31.95, vertragsart="fest")
    reihe = bezugspreis_reihe(tarif=tarif, heute=HEUTE, laenge=laenge)

    assert reihe.quelle == "vertrag"
    assert reihe.preis_cent == [31.95] * laenge
    assert not any(reihe.guenstig), "ohne Fenster ist keine Stunde günstiger als sonst"
    assert reihe.ist_vollstaendig


def test_zeitfenster_reihe_ist_symmetrisch_zum_slotpreis_ueber_mitternacht():
    """Die Kernprobe von B1 — Slot für Slot dasselbe wie der SoT, auch nachts um 0 Uhr.

    Das Fenster 22–06 Uhr läuft über Mitternacht; auf der backward-Achse fällt
    seine Kante nicht auf einen Tagesrand, sondern mitten hinein. Genau dort
    würde ein nachgebauter Rechner abweichen.
    """
    tarif = _Tarif(
        netzbezug_arbeitspreis_cent_kwh=32.0, vertragsart="fest",
        zeitfenster=(_Fenster(22, 6, 21.0),),
    )
    reihe = bezugspreis_reihe(tarif=tarif, heute=HEUTE, laenge=48)

    from datetime import timedelta
    for s in range(48):
        tag = HEUTE + timedelta(days=s // 24)
        assert reihe.preis_cent[s] == preis_je_slot(tarif, tag, s % 24), f"Slot {s}"
    assert reihe.quelle == "zeitfenster"
    # Slot 1 = 00:00–01:00 liegt im Niedertarif, Slot 12 = 11:00–12:00 nicht.
    assert reihe.guenstig[1] is True and reihe.preis_cent[1] == 21.0
    assert reihe.guenstig[12] is False and reihe.preis_cent[12] == 32.0


def test_wochenend_fenster_greift_am_richtigen_tag():
    """Die Achse trägt den Tagesübergang — und damit auch den Wochentagswechsel.

    Freitag 22 Uhr ist noch Werktag, Samstag 00 Uhr nicht mehr. Ein Rechner, der
    den Slot nur modulo 24 nähme, verlöre den Tag.
    """
    tarif = _Tarif(
        netzbezug_arbeitspreis_cent_kwh=30.0, vertragsart="fest",
        zeitfenster=(_Fenster(0, 24, 18.0, nur_wochenende=True),),
    )
    freitag = date(2026, 9, 25)
    reihe = bezugspreis_reihe(tarif=tarif, heute=freitag, laenge=48)

    assert reihe.preis_cent[12] == 30.0, "Freitag 11–12 Uhr: Werktag"
    assert reihe.preis_cent[25] == 18.0, "Samstag 00–01 Uhr: Wochenende"


def test_ohne_tarif_gibt_es_keinen_preis():
    reihe = bezugspreis_reihe(tarif=None, heute=HEUTE, laenge=25)
    assert reihe.quelle == "keine"
    assert reihe.preis_cent == [None] * 25
    assert not reihe.hat_preis
    assert not reihe.ist_vollstaendig


# ── 3 · Der dynamische Fall ─────────────────────────────────────────────────

def test_dynamisch_ohne_aufschlag_ist_die_nackte_boerse_und_sagt_es():
    boerse = [None] + [5.0] * 24
    reihe = bezugspreis_reihe(
        tarif=_Tarif(vertragsart="dynamisch"), heute=HEUTE, laenge=25,
        boerse_backward=boerse,
    )
    assert reihe.quelle == "boersenpreis"
    assert reihe.preis_cent[1] == 5.0
    assert reihe.preis_cent[0] is None
    assert not reihe.ist_vollstaendig, "eine Näherung ist kein Endpreis (Flex §3 T-1)"


def test_dynamisch_mit_aufschlag_ist_das_chat_beispiel():
    """Ø 27,66 · Börsenmittel 8,00 · USt 19 ⇒ Aufschlag 18,14 ⇒ 5,00 ct Börse = 24,09."""
    aufschlag = aufschlag_aus_abrechnung(27.66, 8.00, 19.0)
    assert aufschlag == 18.14

    reihe = bezugspreis_reihe(
        tarif=_Tarif(vertragsart="dynamisch"), heute=HEUTE, laenge=25,
        boerse_backward=[None] + [5.0] * 24,
        aufschlag_cent=aufschlag, ust_prozent=19.0,
    )
    assert reihe.quelle == "boerse_plus_aufschlag"
    assert reihe.preis_cent[1] == 24.09      # 1,19 × 5,00 + 18,14
    assert reihe.ist_vollstaendig


def test_dynamisch_gewinnt_gegen_gepflegte_zeitfenster():
    """Mischform: der Marktpreis ist die Wirklichkeit, die Fenster sind Altlast.

    Beides gleichzeitig wäre nicht entscheidbar — und ein Zeitfenster-Preis auf
    einem Tibber-Vertrag ist eine Zahl, die der Anwender nie bezahlt.
    """
    tarif = _Tarif(vertragsart="dynamisch", zeitfenster=(_Fenster(22, 6, 21.0),))
    reihe = bezugspreis_reihe(
        tarif=tarif, heute=HEUTE, laenge=25, boerse_backward=[None] + [7.0] * 24,
    )
    assert reihe.quelle == "boersenpreis"
    assert reihe.preis_cent[1] == 7.0


# ── 4 · `endpreis_reihe` — die Ränder ───────────────────────────────────────

def test_negative_boerse_bleibt_negativ_und_der_endpreis_darf_darunter_fallen():
    """Flex P-8 — genau so rechnet ein dynamischer Versorger ab.

    −10 ct Börse: 1,19 × (−10) + 18,14 = 6,24. Wer hier bei 0 abschnitte, nähme
    dem Anwender die Stunden, in denen sich Verbrauchen am meisten lohnt.
    """
    assert endpreis_reihe([-10.0], 18.14, 19.0) == [6.24]
    # …und tief genug ist der Endpreis auch negativ.
    assert endpreis_reihe([-20.0], 5.0, 19.0) == [-18.8]


def test_none_bleibt_none():
    assert endpreis_reihe([None, 5.0, None], 10.0, 19.0) == [None, 15.95, None]


def test_ust_20_fuer_oesterreich():
    """AT pflegt 20 % an der Anlage — dieselbe Formel, anderer Faktor."""
    assert endpreis_reihe([10.0], 15.0, 20.0) == [27.0]      # 1,20 × 10 + 15
    assert endpreis_reihe([10.0], 15.0, 19.0) == [26.9]      # 1,19 × 10 + 15


@pytest.mark.parametrize("ust", [None, "", "unsinn", -5.0, 120.0])
def test_kaputte_ust_faellt_auf_19_zurueck(ust):
    assert endpreis_reihe([10.0], 0.0, ust) == endpreis_reihe([10.0], 0.0, UST_DEFAULT_PROZENT)


def test_ust_null_ist_ein_gepflegter_wert():
    """0 % USt (Kleinunternehmer) ist eine Angabe, kein fehlender Wert."""
    assert endpreis_reihe([10.0], 5.0, 0.0) == [15.0]


# ── 5 · Das gewichtete Börsenmittel ─────────────────────────────────────────

def test_boersenmittel_wird_mit_dem_bezug_gewichtet():
    """Σ(Börse × Bezug) ÷ Σ Bezug — nicht der arithmetische Schnitt.

    Zwei Stunden: 4 ct bei 10 kWh, 20 ct bei 1 kWh. Arithmetisch 12 ct,
    gewichtet (40 + 20) ÷ 11 = 5,4545. Der Anwender hat den zweiten Preis fast
    nicht bezahlt.
    """
    assert boersenmittel_gewichtet([(4.0, 10.0), (20.0, 1.0)]) == pytest.approx(5.4545, abs=1e-4)


def test_negativer_bezug_wird_geklemmt():
    """Ein Zähler-Glitch darf das Mittel nicht ins Gegenteil ziehen."""
    assert boersenmittel_gewichtet([(10.0, 5.0), (30.0, -5.0)]) == 10.0


def test_ohne_bezug_gibt_es_kein_mittel():
    """`None` heißt „nicht gewichtbar" — nicht 0 ct."""
    assert boersenmittel_gewichtet([]) is None
    assert boersenmittel_gewichtet([(10.0, 0.0), (20.0, 0.0)]) is None
    assert boersenmittel_gewichtet([(10.0, None), (None, 5.0)]) is None


# ── 6 · Der Aufschlag aus Stunden ───────────────────────────────────────────

def test_median_haelt_gegen_einen_ausreisser():
    """Eine einzige verrutschte Stunde verschiebt ein Mittel, einen Median nicht.

    24 Stunden mit exakt 18,14 ct Aufschlag, eine davon mit 200 ct. Das Mittel
    läge bei ~25,7; der Median bleibt 18,14.
    """
    paare = [(1.19 * 5.0 + 18.14, 5.0)] * 23 + [(1.19 * 5.0 + 200.0, 5.0)]
    assert aufschlag_aus_stunden(paare, 19.0) == 18.14


def test_zu_wenige_paare_ergeben_nichts():
    """Ein Tag kann vollständig in eine Hochpreisphase fallen — 24 sind das Minimum."""
    paare = [(1.19 * 5.0 + 18.14, 5.0)] * (MINDEST_PAARE - 1)
    assert aufschlag_aus_stunden(paare, 19.0) is None
    assert aufschlag_aus_stunden(paare + paare[:1], 19.0) == 18.14


def test_luecken_zaehlen_nicht_als_paar():
    """Eine Zeile mit nur einer der beiden Zahlen ist kein Paar."""
    echte = [(1.19 * 5.0 + 18.14, 5.0)] * 20
    luecken = [(None, 5.0), (30.0, None)] * 5
    assert aufschlag_aus_stunden(echte + luecken, 19.0) is None, "20 echte Paare reichen nicht"


def test_aufschlag_aus_abrechnung_braucht_beide_seiten():
    assert aufschlag_aus_abrechnung(None, 8.0, 19.0) is None
    assert aufschlag_aus_abrechnung(27.66, None, 19.0) is None


def test_aufschlag_null_ist_ein_ergebnis_kein_fehlen():
    """Ein Versorger, der die nackte Börse durchreicht, hat Aufschlag 0 — und das ist ein Wert."""
    aufschlag = aufschlag_aus_abrechnung(11.9, 10.0, 19.0)
    assert aufschlag == 0.0
    reihe = bezugspreis_reihe(
        tarif=_Tarif(vertragsart="dynamisch"), heute=HEUTE, laenge=25,
        boerse_backward=[None] + [10.0] * 24, aufschlag_cent=aufschlag, ust_prozent=19.0,
    )
    assert reihe.quelle == "boerse_plus_aufschlag", "0 ct Aufschlag ist kein fehlender Aufschlag"
    assert reihe.preis_cent[1] == 11.9


# ── 7 · Was eine Kilowattstunde wert ist ────────────────────────────────────

def test_eigenverbrauchswert_ist_bezug_minus_verguetung():
    assert wert_je_kwh(30.0, 8.1) == 21.9


def test_verguetung_null_ist_ein_wert():
    """Volleinspeisung ohne Vergütung: der ganze Bezugspreis ist die Ersparnis."""
    assert wert_je_kwh(30.0, 0.0) == 30.0


def test_ohne_eine_der_beiden_seiten_kein_wert():
    assert wert_je_kwh(None, 8.0) is None
    assert wert_je_kwh(30.0, None) is None


# ── 8 · Speicherkosten ──────────────────────────────────────────────────────

def test_speicherkosten_sind_preis_durch_eta():
    """Die Demo-Anlage: 8,1 ct Vergütung ÷ 85,0 % gemessenem η = 9,53 ct."""
    assert speicher_kwh_kosten(8.1, 85.006) == 9.53
    # pruef-Anlage: 8,0 ÷ 90 (gepflegt) = 8,89
    assert speicher_kwh_kosten(8.0, 90.0) == 8.89


def test_speicherkosten_bei_null_cent_sind_null():
    """0 ct ist ein gepflegter Wert — `is not None`, nie truthy."""
    assert speicher_kwh_kosten(0.0, 90.0) == 0.0


@pytest.mark.parametrize("preis,eta", [(None, 90.0), (8.0, None), (8.0, 0.0), (8.0, -5.0)])
def test_speicherkosten_ohne_gueltige_eingaenge(preis, eta):
    assert speicher_kwh_kosten(preis, eta) is None


def test_eta_anlage_ist_das_minimum():
    """Die Kette ist nicht besser als ihr schwächstes Glied."""
    assert eta_anlage([95.0, 85.0, 91.0]) == 85.0
    assert eta_anlage([95.0]) == 95.0


def test_eta_anlage_ist_none_sobald_ein_glied_fehlt():
    """⭐ Nicht „das Minimum der bekannten" — sonst stünde eine Zahl für die halbe Anlage."""
    assert eta_anlage([95.0, None]) is None
    assert eta_anlage([None]) is None


def test_eta_anlage_ohne_speicher():
    assert eta_anlage([]) is None
