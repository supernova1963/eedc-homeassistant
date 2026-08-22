"""N-314 — die Obergrenze des PV-Ladeanteils ist geerbt, und niemand hielt sie fest.

**Entstehung, weil sie zum Wert dieser Datei gehört.** Die Fundregister-Inventur
(Runde B, 22.08.2026) fand, dass ``ist_pv_ladeanteil_prozent`` im
``Returns:``-Block ``0…100`` verspricht und selbst ungeklemmt rechnet
(``Σ pv ÷ Σ ladung × 100``). Der Verdacht: ein erfasster Datensatz mit
``ladung_pv_kwh > ladung_kwh`` — an Anlage 1 real vorhanden (2026-06: **100,5
kWh PV bei 86,0 kWh Gesamt**) — erzeugt 116,9 %, und weil der Wert ein
Rechen-**Eingang** ist (``crud.py`` → ``calculations.py``:
``netz_anteil = 1 − pv_anteil/100``), würde daraus ein negativer Faktor: das
Laden verdiente Geld.

⛔ **Am Code gemessen war der Verdacht falsch, und der Beleg steht unten als
erster Test.** Die Fakten-Schicht lässt den Widerspruch gar nicht durch:

* ``summiere_emob_quelle`` **konstruiert** ``ladung_kwh`` als ``pv + netz`` —
  es liest das Feld nicht.
* ``get_emob_pv_netz_kwh`` klemmt den *abgeleiteten* Netz-Anteil mit
  ``max(0, total − pv)``.

Zusammen gilt ``ladung_kwh ≥ pv`` strukturell, die Quote ist damit ≤ 100 %.
Das war der **#262**-Befund (junky84, evcc-Import ohne ``ladung_netz_kwh``) und
ist dort gelöst — *„feldweises ``max()`` über getrennte Töpfe konnte einen
PV-Anteil > 100 % erzeugen"*, sagt der ``EmobFakten``-Docstring selbst.

**Was trotzdem fehlte und wofür diese Datei da ist:** Die Garantie war
**unbelegt und ungewächtert**. Keine Probe hielt fest, dass die Trias die
Obergrenze trägt. Wer ``get_emob_pv_netz_kwh`` umbaut — etwa den
``max(0, …)``-Zweig gegen eine Direktlesung tauscht —, bricht eine Zusage, die
zwei Dateien weiter im Docstring steht, und **nichts** hätte es gemeldet.

⚠ **Ein Deckel in ``ist_pv_ladeanteil_prozent`` wäre der falsche Schutz gewesen**
und ist deshalb bewusst *nicht* gebaut: er finge einen Zustand ab, den es nicht
mehr gibt, und verstellte die Sicht auf die echte Garantie — bräche jemand die
Schicht darunter, bliebe der Fehler unter dem Deckel unsichtbar. Eine Probe,
die sich einen in der Produktion unerreichbaren Zustand herstellt, schützt am
Ende die Falschaussage.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.field_definitions import get_emob_pv_netz_kwh
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten
from backend.services.eauto_wirtschaftlichkeit import summiere_emob_quelle
from backend.services.monats_fakten import (
    ist_pv_ladeanteil_prozent,
    lade_monats_fakten,
)

JAHR, MONAT = 2026, 6

#: Der real vorhandene Widerspruch von Anlage 1 (2026-06), Grundlage von N-201.
WIDERSPRUCH = {"ladung_kwh": 86.0, "ladung_pv_kwh": 100.5}


async def _anlage_mit_wallbox(db: AsyncSession, name: str, vd: dict) -> Anlage:
    """Anlage mit EINER Wallbox-Zeile — die Wallbox ist die Pool-Quelle (#262)."""
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
                       netzbezug_kwh=0.0, einspeisung_kwh=0.0))
    inv = Investition(
        anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox-N314",
        anschaffungsdatum=date(2023, 1, 1),
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten=vd))
    await db.commit()
    return anlage


# ───────────────── Die Garantie, an der Stelle wo sie entsteht ────────────────


def test_die_trias_schliesst_den_widerspruch_statt_ihn_durchzureichen():
    """``ladung_kwh`` wird als ``pv + netz`` gebaut, nicht aus dem Feld gelesen.

    **Der Kern der ganzen Datei.** Die Eingabe trägt ``86,0`` als Gesamtladung
    und ``100,5`` als PV-Anteil — widersprüchlich. Die Ausgabe trägt ``100,5``
    als Gesamt: nicht weil jemand PV gekappt hätte, sondern weil das Feld
    ``ladung_kwh`` **gar nicht gelesen** wird. Damit ist ``pv ≤ ladung_kwh``
    keine Prüfung, sondern eine Bauform.
    """
    pool = summiere_emob_quelle([WIDERSPRUCH])

    assert pool.ladung_kwh == pool.pv_kwh + pool.netz_kwh, (
        "Die Trias ist offen — `summiere_emob_quelle` konstruiert `ladung_kwh` "
        "nicht mehr aus `pv + netz`. Ab hier kann der PV-Anteil 100 % übersteigen "
        "(#262), und `ist_pv_ladeanteil_prozent` verspricht in seinem Docstring "
        "trotzdem weiter `0…100`"
    )
    assert pool.pv_kwh <= pool.ladung_kwh
    assert pool.ladung_kwh == 100.5, (
        "Erwartet wird die PV-Menge als Gesamt (86,0 wird nicht gelesen) — "
        f"geliefert: {pool.ladung_kwh}"
    )


def test_der_abgeleitete_netzanteil_wird_nicht_negativ():
    """``get_emob_pv_netz_kwh`` klemmt mit ``max(0, total − pv)``.

    Die zweite Hälfte der Garantie. Ohne diese Klemmung wäre ``netz`` hier
    ``86,0 − 100,5 = −14,5``, die Trias ergäbe wieder ``86,0`` als Gesamt — und
    die Quote läge bei 116,9 %.
    """
    pv, netz = get_emob_pv_netz_kwh(WIDERSPRUCH, total_kwh=WIDERSPRUCH["ladung_kwh"])

    assert netz >= 0.0, f"netz={netz} — negativ, damit ist `pv ≤ pv + netz` dahin"
    assert (pv, netz) == (100.5, 0.0)


# ───────────────── Die Wirkung, am Konsumenten nachgezogen ───────────────────


async def test_der_widerspruechliche_datensatz_ergibt_hoechstens_100_prozent(db):
    """Ende-zu-Ende: dieselbe Zeile durch die Fakten-Schicht bis zur Quote.

    Diese Probe fällt auch dann, wenn jemand die Garantie an einer *dritten*
    Stelle bricht, die die beiden Tests oben nicht kennen — etwa in der
    Pool-Wahl von ``get_emob_heimladung_canonical``.
    """
    anlage = await _anlage_mit_wallbox(db, "n314-widerspruch", dict(WIDERSPRUCH))

    fakten = await lade_monats_fakten(db, anlage.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))
    assert fakten, "Fakten-Zeile fehlt — der Test prüft sonst eine leere Menge"

    anteil = await ist_pv_ladeanteil_prozent(db, anlage.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))

    assert anteil is not None
    assert anteil <= 100.0, (
        f"Der Docstring verspricht 0…100, geliefert wurden {anteil:.1f} %. "
        "Daraus wird in calculations.py ein NEGATIVER Netz-Anteil — das Laden "
        "verdiente dann Geld (Dienstwagen-Klasse v4.0.5)"
    )


async def test_der_konsument_bekommt_keinen_negativen_netzanteil(db):
    """``1 − pv_anteil/100`` bleibt ein gültiger Faktor.

    Steht als eigene Probe da, damit beim nächsten Eingriff sichtbar bleibt,
    **wofür** die Garantie gebraucht wird: nicht für eine schönere Prozentzahl,
    sondern gegen ein gekipptes Vorzeichen in der Wirtschaftlichkeit.
    """
    anlage = await _anlage_mit_wallbox(db, "n314-netzanteil", dict(WIDERSPRUCH))

    anteil = await ist_pv_ladeanteil_prozent(db, anlage.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))
    netz_anteil = 1 - (anteil or 0.0) / 100

    assert netz_anteil >= 0.0, (
        f"netz_anteil={netz_anteil:.3f} — negativ. In core/calculations.py "
        "multipliziert dieser Faktor den Strombedarf mit dem Arbeitspreis"
    )


# ───────────────── Gegenproben: die Garantie verbiegt nichts ─────────────────


async def test_ein_gewoehnlicher_anteil_wird_NICHT_verbogen(db):
    """Ohne diese Gegenprobe misst die Datei nur, dass irgendetwas begrenzt.

    Lehre aus dem N-92-Bau vom selben Tag: eine Regel, die etwas zurechtrückt,
    muss auch belegen, dass sie das Richtige **stehen lässt**. 74 von 200 sind
    37 % und müssen 37 % bleiben.
    """
    anlage = await _anlage_mit_wallbox(
        db, "n314-normal", {"ladung_kwh": 200.0, "ladung_pv_kwh": 74.0},
    )

    anteil = await ist_pv_ladeanteil_prozent(db, anlage.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))

    assert anteil == 37.0, f"74/200 sind 37 % — geliefert: {anteil}"


async def test_keine_heimladung_bleibt_keine_aussage(db):
    """Der ``None``-Zweig überlebt — 0 % wäre eine Behauptung.

    Der Docstring führt „keine Heimladung im Zeitraum" ausdrücklich als eigene
    Antwort; sie darf nicht zu „0 % aus PV" eingeebnet werden.
    """
    anlage = await _anlage_mit_wallbox(
        db, "n314-keine-ladung", {"ladung_kwh": 0.0, "ladung_pv_kwh": 0.0},
    )

    anteil = await ist_pv_ladeanteil_prozent(db, anlage.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))

    assert anteil is None, "Keine Heimladung ist keine Aussage, nicht 0 %"
