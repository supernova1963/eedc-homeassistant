"""Hat ein Gerät einen **Stromzähler für den Kühlbetrieb**? (Wärme/Klima R1, E6)

⭐ **Warum das seit dem 21.09.2026 eine Funktion auf Modulebene ist.** Die Regel
lebte als verschachtelte Closure in
``daten_checker/datenquelle/klima.py::_check_klima_kuehlanteil_geschaetzt`` und
hing an drei lokalen Namen. Das Kühlfenster des HA-Exports (S3/P8) braucht
**dieselbe** Frage: es entsteht nur an einem Gerät, dessen Kühl-Achse am Zähler
liegt. Ein Nachbau dort hätte genau die Drift erzeugt, gegen die R1 geschrieben
ist — der Daten-Checker sagt „Kühlanteil wird geschätzt", und der Sensor
daneben tut so, als wäre er gemessen.

⚠ **Enger als eine „Kühl-Spur".** Eine Kältemenge und erst recht ein gepflegtes
``leistung_kuehlen_w`` sind **kein** kWh-Zähler und lösen den Fall nicht auf.
Genau diese Unterscheidung ist der Grund, warum der Daten-Checker den Hinweis
überhaupt gibt — und warum P8 **beide** Kriterien verlangt (Zähler *und*
gepflegte Kühlleistung): der Zähler sagt, dass die Achse gemessen ist, die
Leistung sagt, wie viel in ein Fenster passt.
"""

from __future__ import annotations

from typing import Iterable, Optional


def hat_kuehl_zaehler(
    inv_id: int,
    *,
    imd_zeilen: Iterable,
    mapping: Optional[dict] = None,
    quellen: Optional[dict] = None,
) -> bool:
    """Ist an diesem Gerät ein Stromzähler *Kühlbetrieb* zugeordnet oder gepflegt?

    Drei Wege, und alle drei zählen — sie sind die drei Arten, wie eine Größe
    in eedc an ein Gerät kommt:

    1. **gepflegt** — eine Monatszeile trägt den Kühlstrom (auch als 0: eine
       gepflegte 0 ist eine Aussage);
    2. **zugeordnet über das Sensor-Mapping** — ``felder`` mit Strategie
       ``sensor`` und einer ``sensor_id``;
    3. **zugeordnet über die Datenquellen-Fläche** — ``quellen`` mit einer
       Quelle ungleich ``"keine"``.

    Args:
        inv_id: die Investition.
        imd_zeilen: ``InvestitionMonatsdaten`` (beliebige Geräte — gefiltert wird hier).
        mapping: ``Anlage.sensor_mapping["investitionen"]``.
        quellen: ``Anlage.sensor_mapping["quellen"]``.
    """
    from backend.core.berechnungen.betriebsart_gemessen import betriebsart_strom_kwh
    from backend.core.betriebsmodus import BETRIEBSART_STROM_FELD, KUEHLEN
    from backend.core.field_definitions import basis_feld_key

    if any(
        getattr(imd, "investition_id", None) == inv_id
        and betriebsart_strom_kwh(imd.verbrauch_daten or {}, KUEHLEN) is not None
        for imd in imd_zeilen
    ):
        return True

    feld = BETRIEBSART_STROM_FELD[KUEHLEN]
    eintrag = (mapping or {}).get(str(inv_id))
    if isinstance(eintrag, dict):
        for k, m in (eintrag.get("felder") or {}).items():
            if basis_feld_key(k) == feld and isinstance(m, dict) \
                    and m.get("strategie") == "sensor" and m.get("sensor_id"):
                return True

    praefix = f"inv_energy_{inv_id}_"
    for feld_id, q in (quellen or {}).items():
        if isinstance(feld_id, str) and feld_id.startswith(praefix) \
                and basis_feld_key(feld_id[len(praefix):]) == feld:
            quelle = (q or {}).get("quelle") if isinstance(q, dict) else None
            if quelle and quelle != "keine":
                return True
    return False
