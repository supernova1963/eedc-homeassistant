"""Zuordnungsänderung ⇒ Hinweis auf die unberührte Historie (Konzept #192 B).

**Das Problem.** Die gespeicherten Tages- und Stundenwerte tragen die Zuordnung,
die zum **Aggregationszeitpunkt** galt (`services/energie_profil/aggregator.py`
liest `anlage.sensor_mapping` bei jedem Lauf). Wer heute einen Sensor zuordnet,
hat ab heute korrekte Werte — die Vergangenheit bleibt, wie sie gerechnet wurde,
und ändert sich erst durch ein erneutes Aggregieren. Bis 2026-08-13 sagte eedc
dazu **nichts**: der Quellen-Endpunkt quittierte mit ``{"gespeichert": true}``,
und der Anwender erfuhr es über Drift oder gar nicht.

⚠ **Die ursprüngliche Regel-Tabelle aus #192 B ist widerlegt** (gemessen
2026-08-13). Sie führte Live-Sensoren als „Historie nicht betroffen — nur
Live-Pfad". Tatsächlich landet **jede** Feldklasse dieser Fläche in den
gespeicherten Tageswerten:

* ``*_energy_*`` — Stunden-kWh je Kategorie (``snapshot/lts_aggregator.py`` über
  ``basis_hourly_eintraege`` / ``investition_hourly_eintraege``)
* ``*_live_*`` (Leistung) — die **Kurvenform** der Stunden
  (``get_tagesverlauf`` → ``aggregate_day``)
* ``*_live_*`` (SoC) — Stunden-SoC je Speicher (``_get_soc_history``, N-239)
* ``basis_preis_*`` — Stunden-Strompreis (``_get_strompreis_stunden``)

Deshalb klassifiziert diese Datei **nicht**, welches Feld wirkt: es wirken alle,
die auf der Fläche stehen (``nur_manuell``-Felder sind dort ohnehin
ausgefiltert). Eine Whitelist wäre eine Behauptung, die bei jedem neuen Feld
still falsch würde — [[feedback_aggregations_drift]].

**Was hier NICHT passiert.** Kein Automatismus, der die Historie nachzieht
([[feedback_kein_grosser_heiler_knopf]]): der Hinweis benennt den Zustand und
führt zur Bereichs-Reparatur, die der Anwender selbst auslöst.
"""

from __future__ import annotations

from typing import Any, Optional

#: Schlüssel des Vermerks in ``anlage.sensor_mapping``. Additiv wie
#: ``quellen``/``invertieren`` — bestehende Strukturen bleiben unberührt.
HISTORIE_HINWEIS_KEY = "historie_hinweis"

# ⚠ Wie viele Felder der Block einzeln benennt, entscheidet der **Client**
# (`MAX_BENANNTE_FELDER` in `DatenquellenZuordnung.tsx`). Der Vermerk trägt alle:
# eine zweite Kürzungsgrenze hier wäre eine Kopie, die still auseinanderläuft
# (die offene Vokabular-Kopplung N-35/N-40).


def ist_echte_aenderung(vorher: Optional[dict], nachher: Optional[dict]) -> bool:
    """Hat sich an der Quelle eines Feldes etwas geändert, das Werte bewegt?

    Verglichen wird der **Quellen-Eintrag** des Feldes, nicht das ganze Mapping.
    Ein erneutes Speichern derselben Wahl (der Anwender öffnet den Picker und
    bestätigt) ist keine Änderung — sonst meldete sich der Hinweis bei jedem
    Klick, und ein Hinweis, der ohne Anlass erscheint, wird weggeklickt statt
    gelesen.

    ``None`` und ``{}`` gelten als gleich: beides heißt „kein eigener Eintrag"
    (Quelle = Grundeinstellung).
    """
    return _norm(vorher) != _norm(nachher)


def _norm(eintrag: Optional[dict]) -> dict:
    """Vergleichsform eines Quellen-Eintrags.

    ``mapping_id`` fliegt raus: sie ist die Zeilen-ID der Gateway-Zuordnung und
    wechselt beim Upsert, ohne dass sich für die Werte etwas ändert.
    """
    if not eintrag:
        return {}
    return {k: v for k, v in eintrag.items() if k != "mapping_id"}


def vermerk_lesen(mapping: Optional[dict]) -> Optional[dict]:
    """Der offene Vermerk — ``None``, wenn keiner aussteht."""
    if not mapping:
        return None
    vermerk = mapping.get(HISTORIE_HINWEIS_KEY)
    if not isinstance(vermerk, dict) or not vermerk.get("felder"):
        return None
    return vermerk


def vermerk_ergaenzen(
    mapping: dict, *, field_id: str, label: str, jetzt_iso: str,
) -> dict:
    """Trägt ein geändertes Feld in den Vermerk ein (in-place) und gibt ihn zurück.

    Mehrere Änderungen sammeln sich in **einem** Vermerk: wer eine neue
    Komponente einrichtet, ordnet fünf Felder hintereinander zu und soll
    danach einen Hinweis sehen, nicht fünf.

    ``seit`` bleibt beim **ersten** Eintrag stehen — es ist der Zeitpunkt, ab
    dem die Werte neu sind, und damit die Grenze, die der Anwender für die
    Bereichs-Reparatur braucht.

    Der Aufrufer ist für ``flag_modified`` + ``commit`` zuständig.
    """
    vermerk = mapping.get(HISTORIE_HINWEIS_KEY)
    if not isinstance(vermerk, dict) or not isinstance(vermerk.get("felder"), list):
        vermerk = {"felder": [], "seit": jetzt_iso}
    felder: list[dict[str, Any]] = [
        f for f in vermerk["felder"] if isinstance(f, dict) and f.get("id") != field_id
    ]
    felder.append({"id": field_id, "label": label})
    vermerk["felder"] = felder
    vermerk.setdefault("seit", jetzt_iso)
    mapping[HISTORIE_HINWEIS_KEY] = vermerk
    return vermerk


def vermerk_leeren(mapping: dict) -> bool:
    """Entfernt den Vermerk (Quittung des Anwenders). True, wenn einer da war.

    ⚠ **Bewusst nicht automatisch nach einer Bereichs-Reparatur.** Die ist auf
    31 Tage je Lauf gedeckelt (``repair_orchestrator.REAGGREGATE_RANGE_MAX_DAYS``);
    wer zwei Jahre Historie hat, ist nach einem Lauf gerade am Anfang. Ein
    Vermerk, der dann verschwände, behauptete „erledigt" für einen Zustand, den
    niemand geprüft hat — die Sorte Pseudo-Bestätigung, die
    [[feedback_daten_checker_kein_akzeptiert]] meint. Der Anwender entscheidet
    selbst, wann er genug nachgezogen hat.
    """
    return mapping.pop(HISTORIE_HINWEIS_KEY, None) is not None
