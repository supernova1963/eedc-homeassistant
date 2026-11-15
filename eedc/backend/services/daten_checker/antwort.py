"""Antwort des Daten-Checkers — **eine** Serialisierung für die Route und das Diagnose-Paket (Diagnose-Paket v4, Testpunkt 1).

``GET /api/system/daten-check/{anlage_id}`` (``api/routes/daten_checker.py``) und ``lage.daten_checker`` des Diagnose-Pakets
(``services/diagnose_paket/lage.py``) bauen ihre Antwort beide über ``checker_antwort(result)``; das Paket schreibt
``checker_antwort(result).model_dump(mode="json")``. Die Modelle standen bis v4.3.0 in der Route und sind unverändert umgezogen.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from backend.services.daten_checker.kategorien import DatenCheckResult


class ZielResponse(BaseModel):
    """E2: Sprung-Ziel eines Befunds (`services/daten_checker/ziele.py`); den Pfad bildet der Client (`lib/zielPfad.ts`, Wächter W-5)."""
    bereich: str
    block: Optional[str] = None
    params: dict = {}
    anker: Optional[str] = None


class AktionResponse(BaseModel):
    """E2: Inline-Handgriff eines Befunds. E3: Plan/Execute-Form (`operation` = Reparatur-Operation, `params` =
    Plan-Parameter); `label` ist der Knopf-Text aus dem Katalog (= `knopf` des Befunds)."""
    operation: str
    params: dict
    label: str


class GruppeResponse(BaseModel):
    """E5 V2: Gruppenzeile eines Befunds (`services/daten_checker/gruppen.py`) — gleiche `schluessel` = eine Zeile."""
    schluessel: str
    titel: str
    glied: str
    weitere: int = 0
    details: Optional[str] = None


class CheckErgebnisResponse(BaseModel):
    """Ein Befund. Seit E5 ohne die Altfelder `link`/`action_*` (Wächter W-3): der Handgriff steht in `ziel` (Sprung)
    bzw. `action` (Aktion), der Knopf-Text aller Klassen in `knopf` (E5.7 L1)."""
    kategorie: str
    schwere: str
    meldung: str
    details: Optional[str] = None
    # IA-V4 #243: Komponenten-Zuordnung für den Komponenten-Hub-Filter.
    investition_id: Optional[int] = None
    # E1 «Diagnose-Paket»: die Zahlen der Meldung strukturiert und der Befund-Schlüssel.
    werte: Optional[dict] = None
    code: Optional[str] = None
    # E2 (Befund-Schlüssel, Ziel-Bauer): Sprung-Ziel bzw. Aktion (Plan/Execute-Form seit E3).
    ziel: Optional[ZielResponse] = None
    action: Optional[AktionResponse] = None
    knopf: Optional[str] = None
    gruppe: Optional[GruppeResponse] = None


class NichtAusfuehrbarResponse(BaseModel):
    """E5 V4: eine Prüfung, die in dieser Installation nicht laufen kann."""
    pruefung: str
    grund: str


class MonatsdatenAbdeckungResponse(BaseModel):
    vorhanden: int
    erwartet: int
    prozent: float


class DatenCheckResponse(BaseModel):
    anlage_id: int
    anlage_name: str
    ergebnisse: list[CheckErgebnisResponse]
    zusammenfassung: dict
    monatsdaten_abdeckung: Optional[MonatsdatenAbdeckungResponse] = None
    nicht_ausfuehrbar: list[NichtAusfuehrbarResponse] = []


def checker_antwort(result: DatenCheckResult) -> DatenCheckResponse:
    """Das Ergebnis von ``DatenChecker.check_anlage`` als Antwort der Route (und des Pakets)."""
    return DatenCheckResponse(
        anlage_id=result.anlage_id,
        anlage_name=result.anlage_name,
        ergebnisse=[
            CheckErgebnisResponse(
                kategorie=e.kategorie,
                schwere=e.schwere,
                meldung=e.meldung,
                details=e.details,
                investition_id=e.investition_id,
                werte=e.werte,
                code=e.code,
                ziel=ZielResponse(**vars(e.ziel)) if e.ziel else None,
                action=AktionResponse(**vars(e.action), label=e.knopf) if e.action else None,
                knopf=e.knopf,
                gruppe=GruppeResponse(**vars(e.gruppe)) if e.gruppe else None,
            )
            for e in result.ergebnisse
        ],
        zusammenfassung=result.zusammenfassung,
        monatsdaten_abdeckung=MonatsdatenAbdeckungResponse(
            vorhanden=result.monatsdaten_abdeckung.vorhanden,
            erwartet=result.monatsdaten_abdeckung.erwartet,
            prozent=result.monatsdaten_abdeckung.prozent,
        ) if result.monatsdaten_abdeckung else None,
        nicht_ausfuehrbar=[NichtAusfuehrbarResponse(**n) for n in result.nicht_ausfuehrbar],
    )
