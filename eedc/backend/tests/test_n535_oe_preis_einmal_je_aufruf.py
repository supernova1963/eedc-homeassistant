"""N-535: Der gemessene Monats-Ø wird je Anfrage EINMAL gerechnet, nicht zweimal.

`berechne_monats_durchschnittspreis` beantwortet im Monatsabschluss **zwei**
Fragen mit demselben Ergebnis:

1. *Erscheint das Feld „Ø Strompreis" überhaupt?* — die Freischaltfrage
   `hat_gemessene_preise` in `lade_basis_feldliste` (N-432/#412).
2. *Welchen Wert schlagen wir vor?* — der erste Vorschlag in
   `_bedingte_basis_vorschlaege`.

Bis zum 19.09.2026 rief **jede** dieser Stellen den Aggregator selbst auf, mit
identischen Argumenten `(anlage_id, jahr, monat, db)` und ohne Cache — je Aufruf
des Formulars also eine überflüssige `TagesEnergieProfil`-Abfrage über den ganzen
Monat. Und zwar genau dann, wenn der erste Aufruf eine Messung geliefert hat:
ohne Messung erscheint das Feld nicht und der zweite Aufruf unterbleibt. Kein
falscher Wert — Laufzeit (P5).

⚠ **Die Probe misst den Aufruf, nicht die Zeit.** Eine Laufzeitmessung wäre auf
einer geteilten Box eine Wette; die Anzahl der Aggregator-Aufrufe ist die Größe,
um die es geht, und sie ist reproduzierbar.

⭐ **Warum der Zähler greift:** beide Aufrufstellen importieren den Aggregator
**funktionslokal** (`from backend.services.strompreis_aggregator import …`
innerhalb der Funktion). Der Name wird damit erst beim Aufruf aus dem Modul
geholt — ein `monkeypatch.setattr` auf das **definierende Modul** wirkt.
Derselbe Mechanismus, auf dem `test_n156_ha_wege_ohne_supervisor.py` steht;
würde der Import auf Modulebene „aufgeräumt", wäre dieser Zähler still blind.

Schwestern: `test_monatsabschluss_feld_dyn_tarif.py` (die Freischaltfrage, #412 /
N-432 — Vorbild für die Datenlage hier), `test_flex_tarife_kaskade.py`
(derselbe Aggregator in der Preis-Kaskade),
`test_monatsabschluss_mqtt_block.py`.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.monatsabschluss.views import get_monatsabschluss
from backend.models import Anlage, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services import strompreis_aggregator as aggregator_modul

FELD = "netzbezug_durchschnittspreis_cent"
JAHR, MONAT = 2025, 6
#: 24 Stunden zu 22,0 ct bei 1,0 kW Bezug — der gewichtete Ø ist damit 22,0.
PREIS_CENT = 22.0


@pytest.fixture
def aggregator_aufrufe(monkeypatch) -> list[tuple[int, int, int]]:
    """Zählt die Aufrufe von `berechne_monats_durchschnittspreis` mit Argumenten.

    Der echte Aggregator läuft weiter — die Probe soll die Zahl messen, nicht
    das Ergebnis ersetzen.
    """
    aufrufe: list[tuple[int, int, int]] = []
    echt = aggregator_modul.berechne_monats_durchschnittspreis

    async def zaehlend(anlage_id, jahr, monat, db):
        aufrufe.append((anlage_id, jahr, monat))
        return await echt(anlage_id, jahr, monat, db)

    monkeypatch.setattr(
        aggregator_modul, "berechne_monats_durchschnittspreis", zaehlend
    )
    return aufrufe


async def _anlage_mit_stundenpreisen(db) -> int:
    """Ein Monat mit gemessenen Stundenpreisen — der Fall, in dem beide Fragen anfallen.

    Die Preise entstehen als `TagesEnergieProfil`-Zeilen, also auf dem Weg, auf
    dem sie produktiv entstehen (dieselbe Fixture-Bauart wie
    `test_monatsabschluss_feld_dyn_tarif.py`).
    """
    anlage = Anlage(anlagenname="Stundenpreise N-535", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2025, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        # vertragsart bewusst NICHT gesetzt — die Messung allein schaltet frei (#412).
    ))
    for stunde in range(24):
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=date(JAHR, MONAT, 1),
            stunde=stunde, strompreis_cent=PREIS_CENT, netzbezug_kw=1.0,
        ))
    await db.flush()
    return anlage.id


def _ist_feld(antwort):
    (feld,) = [f for f in antwort.basis_felder if f.feld == FELD]
    return feld


async def test_der_aggregator_laeuft_genau_einmal(db, aggregator_aufrufe):
    """Eine Anfrage, eine Messung — nicht zwei mit identischen Argumenten."""
    anlage_id = await _anlage_mit_stundenpreisen(db)

    await get_monatsabschluss(anlage_id=anlage_id, jahr=JAHR, monat=MONAT, db=db)

    assert aggregator_aufrufe == [(anlage_id, JAHR, MONAT)], (
        f"{len(aggregator_aufrufe)} Aufrufe statt einem: {aggregator_aufrufe} — "
        "Freischaltfrage und Vorschlagswert brauchen dieselbe Zahl, also "
        "dieselbe Rechnung (N-535)."
    )


async def test_der_vorschlag_bleibt_derselbe(db, aggregator_aufrufe):
    """Die Gegenprobe zur Zahl oben: dieselbe Rechnung heißt derselbe Vorschlag.

    Ein Zähler allein könnte auch grün werden, indem der Vorschlag verschwindet.
    """
    anlage_id = await _anlage_mit_stundenpreisen(db)

    antwort = await get_monatsabschluss(anlage_id=anlage_id, jahr=JAHR, monat=MONAT, db=db)

    feld = _ist_feld(antwort)
    (aggr_vorschlag,) = [v for v in feld.vorschlaege if v.quelle == "berechnung"]
    assert aggr_vorschlag.wert == PREIS_CENT
    assert aggr_vorschlag.konfidenz == 60
    assert aggr_vorschlag.beschreibung == (
        "Verbrauchsgewichteter Ø aus 24 Stundenpreisen (3 % Abdeckung)"
    )
    # Und er steht vorn — die Messung schlägt jede historische Quelle.
    assert feld.vorschlaege[0] is aggr_vorschlag


async def test_ohne_messung_faellt_auch_der_eine_aufruf_nicht_weg(db, aggregator_aufrufe):
    """Gegenrichtung: die Freischaltfrage wird IMMER gestellt.

    Ein Monat ohne Stundenpreise beantwortet sie mit „nein", das Feld erscheint
    nicht — aber gefragt wird trotzdem, sonst hinge die Freischaltung am Zufall.
    """
    anlage_id = await _anlage_mit_stundenpreisen(db)

    antwort = await get_monatsabschluss(anlage_id=anlage_id, jahr=JAHR, monat=9, db=db)

    assert aggregator_aufrufe == [(anlage_id, JAHR, 9)]
    assert FELD not in {f.feld for f in antwort.basis_felder}
