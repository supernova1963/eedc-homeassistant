"""Konformitäts-Test K3 (N-595, #422) — jede Spalte der Stundenzeile hat ein Schicksal.

Schwester von K2 (`test_konformitaet_tz_felder.py`), eine Ebene tiefer: `aggregate_day`
schreibt `TagesEnergieProfil` per Delete+Insert neu. Jede Spalte gehört deshalb zu
genau einer von drei Mengen:

(a) **neu berechnet** — `aggregate_day` setzt sie in jedem Lauf aus einer Quelle, die
    beim Neuschreiben noch liefert (Zählerpfad, Leistungspfad, Wetter, Börse, Counter);
(b) **gerettet, wenn leer** — ihre Quelle VERFÄLLT (HAs Recorder-Verlauf), der Wert
    überlebt das Neuschreiben nur über `_STUNDEN_FELDER_RETTEN` im Aggregator. Der Test
    liest **diese** Konstante, keine Kopie davon;
(c) **Identität/ORM** — Schlüssel, Schreibzeit, Herkunft.

Eine neue Spalte ohne Klasse macht den Test rot und zwingt zur Entscheidung, ob ihre
Quelle beim Neu-Aggregieren noch liefert. Genau diese Frage war bei
`betriebsmodus_je_wp` nie gestellt worden: Konzept 263 D9 bedachte den Erstabruf
(„kein Backfill"), nicht das Neuschreiben — Folge war der Verlust der Aufteilung
Heizen/Kühlen bei jedem Monatsabschluss (#422).
"""

from __future__ import annotations

import ast
import inspect

# (a) — von `baue_stundenzeile` in jedem Lauf neu gesetzt. Hand-gepflegt wie K2; dass die
# Liste stimmt, prüft `test_k3_a_und_b_sind_genau_der_konstruktor` am Quelltext.
_NEU_BERECHNET: frozenset[str] = frozenset({
    # Zählerpfad (HA-LTS bzw. Snapshots — rückwirkend lesbar)
    "pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw",
    "waermepumpe_kw", "wallbox_kw", "spannen", "ueberschuss_kw", "defizit_kw",
    # Wetter (Open-Meteo-Archiv, rückwirkend abrufbar)
    "temperatur_c", "globalstrahlung_wm2", "bewoelkung_prozent", "niederschlag_mm",
    "wetter_code",
    # Börse (aWATTar/EPEX, rückwirkend abrufbar — bewusst NICHT gerettet, Vorlage §6)
    "boersenpreis_cent",
    # Leistungspfad (Vollbackfill reicht ihn aus HA-LTS durch)
    "komponenten",
    # Counter (Snapshots, Boundary-Diff)
    "wp_starts_anzahl", "wp_betriebsstunden",
})

# (c) — Identität und ORM.
_IDENTITAET_ORM: frozenset[str] = frozenset({
    "id", "anlage_id", "datum", "stunde",
    "created_at",          # default datetime.now — trägt die Slot-Konvention (N-387/N-595)
    "source_provenance",   # seed_tep_provenance + gerettete Herkunft (N-595 S4)
})


def _gerettet() -> frozenset[str]:
    from backend.services.energie_profil.aggregator import _STUNDEN_FELDER_RETTEN

    return frozenset(_STUNDEN_FELDER_RETTEN)


def _tep_spalten() -> set[str]:
    from backend.models.tages_energie_profil import TagesEnergieProfil

    return {col.name for col in TagesEnergieProfil.__table__.columns}


def _unklassifiziert(spalten: set[str], gerettet: frozenset[str]) -> set[str]:
    return spalten - (_NEU_BERECHNET | gerettet | _IDENTITAET_ORM)


def test_k3_alle_tep_spalten_klassifiziert():
    fehlt = _unklassifiziert(_tep_spalten(), _gerettet())
    assert not fehlt, (
        "K3-Drift: TagesEnergieProfil hat Spalte(n) ohne Klassifikation: "
        f"{sorted(fehlt)}.\n\nEntscheiden: liefert ihre Quelle beim Neu-Aggregieren eines "
        "alten Tages noch?\n"
        "  ja   → (a) `_NEU_BERECHNET` hier + in `baue_stundenzeile` setzen;\n"
        "  nein → (b) `_STUNDEN_FELDER_RETTEN` im Aggregator + Zusammenführung in "
        "`fuehre_gerettete_stunden_zusammen`;\n"
        "  ORM  → (c) `_IDENTITAET_ORM` mit Begründung."
    )
    abgelaufen = (_NEU_BERECHNET | _gerettet() | _IDENTITAET_ORM) - _tep_spalten()
    assert not abgelaufen, f"K3: Klassifikation nennt Phantom-Spalten: {sorted(abgelaufen)}"


def test_k3_klassen_disjunkt():
    gerettet = _gerettet()
    assert not _NEU_BERECHNET & gerettet, sorted(_NEU_BERECHNET & gerettet)
    assert not _NEU_BERECHNET & _IDENTITAET_ORM, sorted(_NEU_BERECHNET & _IDENTITAET_ORM)
    assert not gerettet & _IDENTITAET_ORM, sorted(gerettet & _IDENTITAET_ORM)


def test_k3_a_und_b_sind_genau_der_konstruktor():
    """(a) ∪ (b) = die Datenspalten, die `baue_stundenzeile` setzt — am Quelltext gezählt.

    Ohne diese Probe könnte (a) eine Spalte behaupten, die der Aggregator gar nicht
    schreibt (dann wäre sie beim Neuschreiben still NULL) — die Hand-Liste allein
    prüft nur Vollständigkeit, nicht Wahrheit.
    """
    from backend.services.energie_profil import aggregator

    baum = ast.parse(inspect.getsource(aggregator.baue_stundenzeile))
    aufrufe = [
        n for n in ast.walk(baum)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "TagesEnergieProfil"
    ]
    assert len(aufrufe) == 1, "baue_stundenzeile baut genau eine Stundenzeile"
    gesetzt = {kw.arg for kw in aufrufe[0].keywords} - {"anlage_id", "datum", "stunde"}
    assert gesetzt == _NEU_BERECHNET | _gerettet(), (
        f"nur Konstruktor: {sorted(gesetzt - (_NEU_BERECHNET | _gerettet()))} · "
        f"nur Klassen: {sorted((_NEU_BERECHNET | _gerettet()) - gesetzt)}"
    )


def test_k3_gegenprobe_der_pruefer_kann_rot_melden():
    """Eine Spalte, die keiner Klasse angehört, und eine aus (b) entfernte — beide fallen auf."""
    spalten = _tep_spalten() | {"neue_spalte_ohne_entscheid"}
    assert _unklassifiziert(spalten, _gerettet()) == {"neue_spalte_ohne_entscheid"}
    ohne_modus = _gerettet() - {"betriebsmodus_je_wp"}
    assert _unklassifiziert(_tep_spalten(), ohne_modus) == {"betriebsmodus_je_wp"}
