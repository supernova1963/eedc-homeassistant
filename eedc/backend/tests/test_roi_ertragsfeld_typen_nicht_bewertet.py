"""ROI-Zeile: Wallbox und Sonstiges behaupten keine Zahl, die sie nicht haben.

**Der Anlass (N-351, gemessen 2026-09-01).** Der Sammelzweig für *Wallbox* und
*Sonstiges* war der **einzige** in ``_roi_dashboard``, der ohne gepflegtes
``einsparung_prognose_jahr`` kein ``nicht_bewertet`` setzte. Er lieferte damit
genau die Fake-0, gegen die **N-87** angetreten war und die **N-258** am
16.08.2026 für die Wärmepumpe abgestellt hat — nur an einem anderen Zweig, wo
sie niemandem aufgefallen ist.

An der Demo-Anlage gemessen, alle vier Zeilen ohne gepflegtes Feld::

    Wallbox 800 €          →  „0,00 €"
    Mini-BHKW 8.000 €      →  „−300,00 €"      ← 0 − betriebskosten_jahr
    Heizstab · Gaszähler   →  „0,00 €"

⭐ **Die −300 € sind der Kern.** Eine Zahl in der *Einsparungs*-Spalte sagt „so
viel spart dieses Gerät" — ein negativer Betrag sagt „es kostet dich Geld", und
das ist eine Behauptung über einen Wert, den eedc gar nicht kennt. Der Abzug
selbst war nie falsch (die Betriebskosten fallen real an), er stand nur in der
falschen Spalte; ``_angezeigte_jahres_einsparung`` fängt ihn ausschließlich über
das Flag.

⚑ **Der Gaszähler zeigt, dass es nicht nur Optik ist:** die *Zähler*-Kategorie
unter Sonstiges ist seit v4.0.23 ausdrücklich „nur erfassen und anzeigen, **ohne
Bewertung**". Eine 0 in der Einsparungs-Spalte behauptete dort das Gegenteil.

⛔ **Was hier NICHT geprüft wird, und das ist eine Entscheidung, keine Lücke:**
ob die Wallbox einen **eigenen** gemessenen Zähler bekommen sollte (ihre
Heimlade-Ersparnis gegenüber der öffentlichen Säule, wie sie der Komponenten-Hub
zeigt). **Entscheid Gernot, 2026-09-01: nein.** Die Ersparnis gehört der
E-Mobilität als Ganzes und ist in der E-Auto-Zeile bereits enthalten — deren
Formel rechnet „Benzin minus Heimstrom" und unterstellt damit schon, dass zuhause
geladen wurde (``aussichten.py``, ``jahres_eauto_km_ersparnis``). Ein zweiter
Posten daneben hätte dieselbe Kilowattstunde gegen zwei einander ausschließende
Alternativen gerechnet — die Klasse aus v4.0.20 (55,9 ct für dieselbe kWh).
**Nicht neu aufrollen.**

Schwesterdateien: ``test_roi_klimaanlage_nicht_bewertet.py`` (derselbe Mechanismus
am Wärmepumpen-Zweig — der Symmetriepartner, an dem N-87/N-258 gebaut wurden),
``test_konzept_wirtschaftlichkeit_konformitaet.py`` (die „drei Sichten, eine
Zahl"-Zusicherung für das Feld ``einsparung_prognose_jahr``) und
``test_roi_summe_symmetrie_f37.py`` (Zeilen gegen Anlagensumme).
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition


async def _seed(db, *, typ: str, ertrag_jahr: float | None,
                betriebskosten: float | None = None,
                kosten: float = 800.0) -> int:
    """Anlage mit genau einer Investition des gegebenen Typs."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ=typ,
        bezeichnung=f"Test-{typ}",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=kosten,
        betriebskosten_jahr=betriebskosten,
        einsparung_prognose_jahr=ertrag_jahr,
    ))
    await db.flush()
    return anlage.id


async def _roi(db, anlage_id):
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )


def _zeile(result, typ: str):
    return next(b for b in result.berechnungen if b.investition_typ == typ)


# ============================================================================
# Der Fehler selbst
# ============================================================================


async def test_sonstiges_mit_betriebskosten_zeigt_keine_negative_ersparnis(db):
    """Der teuerste Fall: ``0 − betriebskosten`` stand als „Einsparung" da.

    Das ist der Mini-BHKW der Demo-Anlage (8.000 €, 300 €/Jahr Betriebskosten,
    kein gepflegter Ertrag) — und der Grund, warum dieser Fund nicht nur eine
    Anzeigefrage ist: die −300 € liefen bis 2026-09-01 in die Anlagen-Summe.
    """
    anlage_id = await _seed(db, typ="sonstiges", ertrag_jahr=None,
                            betriebskosten=300.0, kosten=8000.0)
    zeile = _zeile(await _roi(db, anlage_id), "sonstiges")

    assert zeile.jahres_einsparung == 0, (
        "Eine unbewertete Zeile darf keinen negativen Betrag in der "
        "Einsparungs-Spalte tragen — das ist die N-258-Klasse."
    )
    assert zeile.detail_berechnung["nicht_bewertet"] is True


async def test_die_unbewertete_zeile_senkt_die_anlagensumme_nicht(db):
    """Die zweite Hälfte von N-258: der Beitrag zur Summe, nicht nur die Zelle."""
    mit_bk = await _seed(db, typ="sonstiges", ertrag_jahr=None,
                         betriebskosten=300.0, kosten=8000.0)
    ohne_bk = await _seed(db, typ="sonstiges", ertrag_jahr=None,
                          betriebskosten=None, kosten=8000.0)

    r_mit, r_ohne = await _roi(db, mit_bk), await _roi(db, ohne_bk)
    assert r_mit.gesamt_jahres_einsparung == r_ohne.gesamt_jahres_einsparung, (
        "Ob Betriebskosten gepflegt sind, darf die Summe einer NICHT BEWERTETEN "
        "Zeile nicht verändern — bewertet wird hier gar nichts."
    )


async def test_wallbox_ohne_ertragsfeld_ist_nicht_bewertet(db):
    """Wallbox: dieselbe Regel, anderer Typ — beide hängen am selben Zweig."""
    anlage_id = await _seed(db, typ="wallbox", ertrag_jahr=None)
    zeile = _zeile(await _roi(db, anlage_id), "wallbox")

    assert zeile.detail_berechnung["nicht_bewertet"] is True
    assert zeile.roi_prozent is None
    assert zeile.amortisation_jahre is None


async def test_der_hinweis_nennt_grund_und_weg_hinaus(db):
    """Ein Befund ohne Handlung ist ein P-6-Fall — der Text muss beides tragen.

    Kein Anker auf einen ganzen Satz: der Wortlaut darf sich ändern, die beiden
    Bestandteile nicht. (Die Lehre aus dem Umbau von
    ``test_roi_klimaanlage_nicht_bewertet.py`` am 16.08.: ein Test, der an einem
    einzelnen Wort hängt, wird rot, obwohl die Aussage stimmt.)
    """
    anlage_id = await _seed(db, typ="wallbox", ertrag_jahr=None)
    hinweis = _zeile(await _roi(db, anlage_id), "wallbox").detail_berechnung["hinweis"]

    assert "Ertrag/Jahr" in hinweis, "Der Hinweis muss das Feld benennen, das fehlt."
    assert "nachtragen" in hinweis or "pflege" in hinweis.lower(), (
        "Der Hinweis muss den Weg hinaus nennen, nicht nur den Mangel."
    )
    assert "Manuelle Prognose" not in hinweis, (
        "Der alte Text behauptete eine verwendete Prognose — es gibt keine."
    )


# ============================================================================
# Gegenproben — der Prüfer muss diskriminieren
# ============================================================================


async def test_gepflegter_ertrag_bleibt_eine_bewertete_zeile(db):
    """Wer einen Betrag pflegt, bekommt ihn — unverändert zu vorher."""
    anlage_id = await _seed(db, typ="wallbox", ertrag_jahr=500.0)
    zeile = _zeile(await _roi(db, anlage_id), "wallbox")

    assert zeile.detail_berechnung.get("nicht_bewertet") is not True
    assert zeile.jahres_einsparung == 500.0
    assert zeile.detail_berechnung["hinweis"] == "Manuelle Prognose verwendet"


async def test_gepflegte_null_ist_eine_aussage_und_keine_luecke(db):
    """CLAUDE.md, 0-Werte: ``is None`` statt truthy.

    Eine gepflegte **0** sagt „dieses Gerät bringt nichts" — das ist die Aussage
    des Anwenders und eine bewertete Zeile. Mit ``or``/truthy wäre sie von einem
    leeren Feld nicht zu unterscheiden gewesen, und der Fix hätte dem Anwender
    seine eigene Angabe weggenommen.
    """
    anlage_id = await _seed(db, typ="sonstiges", ertrag_jahr=0.0, betriebskosten=300.0)
    zeile = _zeile(await _roi(db, anlage_id), "sonstiges")

    assert zeile.detail_berechnung.get("nicht_bewertet") is not True
    assert zeile.jahres_einsparung == -300.0, (
        "Bewertet mit 0 heißt: die Betriebskosten wirken wie bei jeder anderen "
        "bewerteten Zeile auch."
    )


async def test_die_zeile_bleibt_sichtbar_und_traegt_ihre_kosten(db):
    """Unbewertet heißt nicht unsichtbar — der Kapitaleinsatz zählt weiter."""
    anlage_id = await _seed(db, typ="sonstiges", ertrag_jahr=None, kosten=8000.0)
    zeile = _zeile(await _roi(db, anlage_id), "sonstiges")

    assert zeile.anschaffungskosten == 8000.0
    assert zeile.kapitaleinsatz == 8000.0
