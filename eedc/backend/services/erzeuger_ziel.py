"""Ziel-Erzeuger einer Datenquelle auflösen — der eine SoT dafür (N-229, #349).

Eine Hersteller-Wolke führt je Wechselrichter eine eigene „Station"; in eedc
gehören diese Geräte in **eine** Anlage (ein Standort, ein Hausanschluss). Damit
zwei Quellen dieselbe Anlage beliefern können, ohne sich zu überschreiben, muss
jede sagen können: *ich messe genau dieses Gerät*.

Das Ziel ist dabei **nicht** das PV-Modul, sondern das Gerät, unter dem die
Module hängen — der Wechselrichter bzw. das Balkonkraftwerk. Empfänger sind
seine Kinder. Genau diese Struktur schreibt `ERLAUBTE_PARENT_TYPEN` vor, und die
erlaubte Ziel-Typmenge wird von dort **abgeleitet** statt danebengeschrieben.

Zwei Aufrufer teilen sich die Auflösung — der Verlaufs-Import
(`api/routes/data_import.py`) und der Monatsabschluss-Cloudabruf
(`api/routes/monatsabschluss/views.py`). Vor N-229 gab es sie nur im ersten;
die zweite Kopie wäre die klassische Aggregations-Drift geworden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from backend.models.investition import Investition, ERLAUBTE_PARENT_TYPEN

# Typen, die als Ziel taugen: genau die, unter denen PV-Module bzw. Speicher
# hängen dürfen. Abgeleitet, damit die Menge nicht danebenläuft, wenn im
# Parent-SoT ein Typ dazukommt.
ZIEL_ERLAUBTE_TYPEN: tuple[str, ...] = tuple(sorted({
    typ for erlaubte in ERLAUBTE_PARENT_TYPEN.values() for typ in erlaubte
}))


class ZielFehler(ValueError):
    """Das Ziel ist nicht auflösbar — die Meldung ist für den Anwender gedacht.

    Trägt `status_code`, damit die HTTP-Schicht nicht raten muss: 404, wenn die
    Investition gar nicht zur Anlage gehört, sonst 400.
    """

    def __init__(self, meldung: str, status_code: int = 400) -> None:
        super().__init__(meldung)
        self.status_code = status_code


@dataclass(frozen=True)
class ZielEmpfaenger:
    """Das Ziel und die Investitionen, die seine Werte tragen."""

    ziel: Investition
    pv_module: list[Investition]
    speicher: list[Investition]

    @property
    def bezeichnung(self) -> str:
        return self.ziel.bezeichnung or self.ziel.typ


def loese_ziel(
    ziel_investition_id: int,
    investitionen: Iterable[Investition],
    *,
    anlage_id: Optional[int] = None,
) -> ZielEmpfaenger:
    """Löst eine Ziel-ID gegen die Investitionen EINER Anlage auf.

    `investitionen` muss die vollständige Liste der Anlage sein — die
    Kind-Beziehung wird darin gesucht, nicht nachgeladen.

    Raises:
        ZielFehler: unbekanntes Ziel (404), falscher Typ (400) oder ein
            Wechselrichter ohne PV-Module (400). Der letzte Fall ist bewusst
            ein Fehler und kein stiller Schreibvorgang: am Wechselrichter
            selbst liest **kein** Monats-Fakten-Pfad die Erzeugung (N-231),
            der Wert läge also an einer Stelle, die niemand auswertet.
    """
    alle = list(investitionen)
    ziel = next((i for i in alle if i.id == ziel_investition_id), None)
    if ziel is None:
        wo = f" zu Anlage {anlage_id}" if anlage_id is not None else ""
        raise ZielFehler(
            f"Investition {ziel_investition_id} gehört nicht{wo}.", status_code=404
        )

    if ziel.typ not in ZIEL_ERLAUBTE_TYPEN:
        raise ZielFehler(
            f"'{ziel.bezeichnung or ziel.typ}' ist vom Typ '{ziel.typ}' und kann kein "
            f"Ziel sein. Wähle den Wechselrichter oder das Balkonkraftwerk, an dem die "
            f"Quelle hängt — die Erträge werden an seinen PV-Modulen geführt."
        )

    kinder = [i for i in alle if i.parent_investition_id == ziel.id]
    pv_module = [i for i in kinder if i.typ == "pv-module"]
    speicher = [i for i in kinder if i.typ == "speicher"]

    # Ein Balkonkraftwerk OHNE Modul-Kinder trägt seine Erzeugung selbst und ist
    # damit sein eigener Empfänger. **Mit** Kindern hat es sie abgetreten (N-266,
    # SoT `core/berechnungen/erzeuger_traeger.py`) und der Import schreibt an die
    # Kinder — genau das leistet dieses `if not pv_module` schon, seit die
    # Zuordnung möglich ist. Bis N-266 stand hier „unter einem BKW dürfen nur
    # Speicher hängen"; die Bedingung war richtig, ihre Begründung nicht mehr.
    if not pv_module and ziel.typ == "balkonkraftwerk":
        pv_module = [ziel]

    if not pv_module:
        raise ZielFehler(
            f"Am Wechselrichter '{ziel.bezeichnung or ziel.typ}' hängen keine PV-Module. "
            f"Die Erzeugung wird an den Modulen geführt, nicht am Wechselrichter — lege "
            f"sie unter ihm an und wiederhole den Vorgang."
        )

    return ZielEmpfaenger(ziel=ziel, pv_module=pv_module, speicher=speicher)
