"""
Reparatur-Operationen der Daten-Checker-Knöpfe (Etappe E3 des Vorhabens «Daten-Checker: ein Handgriff je Befund»).

Konzept §3.1 R6 («Eine Mechanik»): jede Aktion eines Befunds geht über ``POST /api/repair/plan`` → Vorschau-Kasten →
``POST /api/repair/execute/{plan_id}``. Vier Knöpfe hatten bisher keine Operation, sondern eine eigene Route; sie leben
hier — eigenes Modul, weil ``repair_orchestrator.py`` an seiner Dateilängen-Grenze steht (Bauplan §8; der Orchestrator
trägt nur die Enum-Werte und den Verweis auf ``plan_operation``/``execute_operation``). Muster:
``services/verwerfen_vor_quellbeginn.py`` (Lage lesen → Plan; frisch zählen → Ausführen).

| Operation | params | Plan (schreibt nichts) | Ausführen |
| --- | --- | --- | --- |
| ``TEMPERATUR_AUS_MESSUNG`` | — (Ü5) | leere Monate, davon aus der Messreihe erreichbar | ``monatsdaten_pflege.temperatur_aus_messung`` |
| ``FELDWERT_ENTFERNEN`` | ``investition_id``, ``feld`` | Monate, Werte, Summe; endgültig | ``monatsdaten_pflege.feldwert_entfernen`` |
| ``GERAETEWERTE_LOESCHEN`` | ``jahr``, ``monat`` | Gerätewerte des Monats; endgültig — **nur Werkbank** (W6) | ``monatsdaten_pflege.geraetewerte_loeschen`` |
| ``SPIEGEL_ABGLEICH_TAG`` | ``datum`` | **ohne HA** (W2): Spiegel ja/nein, Kanäle, Abschnitte, letzte Spiegelstunde | Lauf der Route ``spiegel-abgleich-tag`` |

**«Nichts zu tun» statt 409** (Gegenprüfung Ü4): wo die Route mit 409 antwortet (Feld am Gerät vorgesehen, Monat hat
noch eine Zählerzeile) bzw. wo nichts zu ändern ist, meldet der Plan ``operation_preview["nichts_zu_tun"]`` mit dem Satz;
der Vorschau-Kasten zeigt ihn ohne «Anwenden». Seit E5 lehnt ``repair_orchestrator.execute()`` jeden solchen Plan ab
(``repair_protokoll.NichtsZuTun`` ⇒ 409, kein Lauf, keine Protokollzeile). **Protokoll:** die eine Zeile ``repair`` schreibt ``repair_orchestrator.execute()`` (W-12); der Lauf der
Spiegel-Operation baut den Tag ohne eigenen Plan und ohne eigene Zeile (``eigener_lauf=False``).

Werkbank-Warnung nur beim Löschen von Zählerständen (N-312); die eine Vorschau-Zeile in Anwender-Sprache baut der Client aus ``estimated_changes``
(``REPARATUR_AENDERUNG_LABELS``, Wächter W-4). Der Plan rechnet nichts außer Zählern und der Summe der zu entfernenden Werte.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services import monatsdaten_pflege as pflege

if TYPE_CHECKING:
    from backend.services.repair_orchestrator import RepairOperationRequest

TEMPERATUR_AUS_MESSUNG = "temperatur_aus_messung"
FELDWERT_ENTFERNEN = "feldwert_entfernen"
GERAETEWERTE_LOESCHEN = "geraetewerte_loeschen"
SPIEGEL_ABGLEICH_TAG = "spiegel_abgleich_tag"
OPERATIONEN = (TEMPERATUR_AUS_MESSUNG, FELDWERT_ENTFERNEN, GERAETEWERTE_LOESCHEN, SPIEGEL_ABGLEICH_TAG)

Plan = tuple[dict[str, int], list[str], dict[str, Any]]


def _mm(jahr: int, monat: int) -> str:
    return f"{monat:02d}/{jahr}"


def _nichts(satz: str, **vorschau: Any) -> Plan:
    return {}, [], {"nichts_zu_tun": satz, **vorschau}


def _pflicht(req: RepairOperationRequest, *namen: str) -> list[Any]:
    if req.anlage_id is None:
        raise ValueError(f"{req.operation.value.upper()} benötigt anlage_id")
    fehlt = [n for n in namen if req.params.get(n) in (None, "")]
    if fehlt:
        raise ValueError(f"{req.operation.value.upper()} benötigt params.{', params.'.join(fehlt)}")
    return [req.params[n] for n in namen]


# ─── TEMPERATUR_AUS_MESSUNG ───────────────────────────────────────────────────────────────────────────────────────

async def _plan_temperatur(req: RepairOperationRequest, db: AsyncSession) -> Plan:
    _pflicht(req)
    lage = await pflege.temperatur_lage(db, req.anlage_id)
    monate = [_mm(e["jahr"], e["monat"]) for e in lage.erreichbar]
    if not monate:
        return _nichts("Für die Monate ohne Ø Temperatur reicht deine Messreihe nicht zurück — es gibt nichts nachzutragen.",
                       monate_leer=len(lage.leer))
    return ({"monate_temperatur_gefuellt": len(monate), "monate_ohne_temperatur": len(lage.leer)}, [],
            {"monate": monate, "werte": [e["wert"] for e in lage.erreichbar]})


# ─── FELDWERT_ENTFERNEN ───────────────────────────────────────────────────────────────────────────────────────────

async def _plan_feldwert(req: RepairOperationRequest, db: AsyncSession) -> Plan:
    investition_id, feld = _pflicht(req, "investition_id", "feld")
    try:
        lage = await pflege.feldwert_lage(db, int(investition_id), str(feld))
    except pflege.PflegeKonflikt as e:
        return _nichts(str(e))
    if lage.inv.anlage_id != req.anlage_id:
        raise ValueError(f"Investition {investition_id} gehört nicht zu Anlage {req.anlage_id}")
    if not lage.monate:
        return _nichts(f"Kein Monat trägt einen Wert im Feld „{feld}“ — es gibt nichts zu entfernen.")
    zahlen = [m["wert"] for m in lage.monate if isinstance(m["wert"], (int, float)) and not isinstance(m["wert"], bool)]
    return ({"monate_wert_entfernt": len(lage.monate)}, [], {
        "endgueltig": True, "feld": feld, "geraet": lage.inv.bezeichnung,
        "monate": [_mm(m["jahr"], m["monat"]) for m in lage.monate], "werte": [m["wert"] for m in lage.monate],
        "summe": sum(zahlen),
    })


# ─── GERAETEWERTE_LOESCHEN (nur Werkbank) ─────────────────────────────────────────────────────────────────────────

async def _plan_geraetewerte(req: RepairOperationRequest, db: AsyncSession) -> Plan:
    jahr, monat = (int(v) for v in _pflicht(req, "jahr", "monat"))
    try:
        komponenten = await pflege.geraetewerte_lage(db, req.anlage_id, jahr, monat)
    except pflege.PflegeKonflikt as e:
        return _nichts(str(e))
    if not komponenten:
        return _nichts(f"Für {_mm(jahr, monat)} liegen keine Messwerte einzelner Geräte vor — es gibt nichts zu entfernen.")
    zaehler = [k["bezeichnung"] for k in komponenten if k.get("ist_zaehler")]
    # N-312: ein Zählerstand ist der Anfangsstand des Folgemonats — gesagt, nicht verboten (bis E3 die Rückfrage im Checker).
    warnungen = [f"Darunter sind Zählerstände ({', '.join(zaehler)}). Ein Stand ist kein Monatswert, sondern der Anfangsstand "
                 "des Folgemonats: entfernst du ihn, rechnet der nächste Monat gegen den vorletzten Stand und zeigt zwei "
                 "Monate als einen. Für Zähler ist Nachtragen des Monats der richtige Weg."] if zaehler else []
    return ({"geraetewerte_zeilen_geloescht": len(komponenten)}, warnungen, {
        "endgueltig": True, "monat": _mm(jahr, monat), "komponenten": [k["bezeichnung"] for k in komponenten],
    })


# ─── SPIEGEL_ABGLEICH_TAG (Plan ohne HA) ──────────────────────────────────────────────────────────────────────────

async def _plan_spiegel(req: RepairOperationRequest, db: AsyncSession) -> Plan:
    """Nur DB (``kanal``, ``kanal_quelle``, ``kanal_statistik``) — kein HA-Aufruf (Gegenprüfung W2, Halt H-E3-1)."""
    from backend.models.anlage import Anlage
    from backend.models.kanal import ART_STAND, ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
    from backend.services.kanal.nachfuellen import abschnitte

    (datum_text,) = _pflicht(req, "datum")
    datum = date.fromisoformat(str(datum_text))
    if (await db.execute(select(Anlage.id).where(Anlage.id == req.anlage_id))).scalar_one_or_none() is None:
        raise LookupError(f"Anlage {req.anlage_id} nicht gefunden")
    kanaele = (await db.execute(select(Kanal).where(
        Kanal.anlage_id == req.anlage_id, Kanal.art.in_([ART_SUM, ART_STAND])).order_by(Kanal.key))).scalars().all()
    je_kanal = []
    for k in kanaele:
        teile = abschnitte(list((await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all()))
        if not teile:
            continue
        letzte = (await db.execute(select(func.max(KanalStatistik.start_ts)).where(
            KanalStatistik.kanal_id == k.id, KanalStatistik.familie == FAMILIE_SPIEGEL))).scalar_one_or_none()
        je_kanal.append({"key": k.key, "abschnitte": len(teile),
                         "letzte_stunde": datetime.fromtimestamp(letzte).strftime("%Y-%m-%d %H:%M") if letzte else None})
    vorschau = {"datum": datum.isoformat(), "hat_spiegel": bool(je_kanal), "vorbedingung": True, "kanaele": je_kanal}
    return ({"spiegel_kanaele": len(je_kanal), "spiegel_abschnitte": sum(k["abschnitte"] for k in je_kanal),
             "tage_neu_aufgebaut": 1}, [], vorschau)


# ─── Verteiler ───────────────────────────────────────────────────────────────────────────────────────────────────

_PLAENE = {
    TEMPERATUR_AUS_MESSUNG: _plan_temperatur, FELDWERT_ENTFERNEN: _plan_feldwert,
    GERAETEWERTE_LOESCHEN: _plan_geraetewerte, SPIEGEL_ABGLEICH_TAG: _plan_spiegel,
}


def _operation(req: RepairOperationRequest) -> str:
    if req.operation.value not in OPERATIONEN:
        raise ValueError(f"Unbekannte Operation: {req.operation}")
    return req.operation.value


async def plan_operation(req: RepairOperationRequest, db: AsyncSession) -> Plan:
    """Plan einer der vier Operationen (``ValueError`` für jede andere). Schreibt nichts."""
    return await _PLAENE[_operation(req)](req, db)


async def execute_operation(req: RepairOperationRequest, db: AsyncSession) -> dict[str, Any]:
    """Führt aus; das Ergebnis ist die Antwort der bisherigen Route (bitgleich). Ein Plan «nichts zu tun» wirft
    ``ValueError`` — der Konflikt der Route wird nicht ausgeführt."""
    op = _operation(req)
    if op == SPIEGEL_ABGLEICH_TAG:
        from backend.api.routes.energie_profil.repair import spiegel_abgleich_tag_lauf

        (datum_text,) = _pflicht(req, "datum")
        antwort, _erg, _fehler = await spiegel_abgleich_tag_lauf(
            db, req.anlage_id, date.fromisoformat(str(datum_text)), eigener_lauf=False)
        return antwort
    try:
        if op == TEMPERATUR_AUS_MESSUNG:
            _pflicht(req)
            return await pflege.temperatur_aus_messung(db, req.anlage_id)
        if op == FELDWERT_ENTFERNEN:
            investition_id, feld = _pflicht(req, "investition_id", "feld")
            return await pflege.feldwert_entfernen(db, int(investition_id), str(feld))
        jahr, monat = (int(v) for v in _pflicht(req, "jahr", "monat"))
        return await pflege.geraetewerte_loeschen(db, req.anlage_id, jahr, monat)
    except pflege.PflegeKonflikt as e:
        raise ValueError(f"Nichts zu tun: {e}") from e
