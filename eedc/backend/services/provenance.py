"""
Provenance-Helper für Aggregat-Schreib-Pfade (Etappe 3d Päckchen 1 + 2).

Single-Source-of-Truth-Funktionen: alle Schreiber auf monatsdaten /
investition_monatsdaten / tages_zusammenfassung / tages_energie_profil
gehen ab Päckchen 3 ausschließlich über `write_with_provenance()` bzw.
`write_json_subkey_with_provenance()` (für JSON-Sub-Keys wie in
`InvestitionMonatsdaten.verbrauch_daten`).

Verantwortlichkeiten:
1. Hierarchie-Check (SourcePriority) — höhere/gleiche Priorität schreibt,
   niedrigere wird abgewiesen.
2. No-Op-Detection bei identischem Wert + identischem input_hash —
   Re-Imports sehen ihren eigenen vorherigen Apply.
3. JSON-Spalten-Update mit flag_modified() (CLAUDE.md-Pflicht: ohne
   flag_modified persistiert SQLAlchemy JSON-Mutationen NICHT).
4. Append-Only Audit-Log in DataProvenanceLog für Diagnose.

Konzept: docs/archive/KONZEPT-DATENPIPELINE.md Sektion 3.4 + 4.1.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.core.berechnungen.pv_anteil_ladung import REGEL_EINSPEISE_DECKUNG
from backend.core.source_priority import SOURCE_LABELS, SourcePriority
from backend.models.data_provenance_log import DataProvenanceLog

logger = logging.getLogger(__name__)


# Natural-Key-Felder pro Aggregat-Tabelle (für row_pk_json im Audit-Log).
# Konzept Sektion 3.3: row_pk_json soll User die Frage „wer hat im Februar
# mein Investitions-Monatsdatum überschrieben?" direkt aus dem Log heraus
# beantwortbar machen — also Natural Key statt Surrogate-id.
_NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "monatsdaten": ("anlage_id", "jahr", "monat"),
    "investition_monatsdaten": ("investition_id", "jahr", "monat"),
    "tages_zusammenfassung": ("anlage_id", "datum"),
    "tages_energie_profil": ("anlage_id", "datum", "stunde"),
}


Decision = Literal["applied", "rejected_lower_priority", "no_op_same_value"]


@dataclass
class WriteResult:
    """Ergebnis eines write_with_provenance()-Aufrufs."""
    applied: bool
    decision: Decision
    reason: str
    conflicting_source: Optional[str] = None  # gesetzt bei rejected_lower_priority


def _row_pk_json(obj: Any) -> str:
    """Serialisiert die Natural-Key-Felder eines Aggregat-Objekts als JSON.

    Fällt auf `id` zurück, wenn die Tabelle keinen registrierten Natural-Key hat —
    das deckt zukünftige Aggregat-Tabellen ab, ohne den Helper zu zerbrechen.
    """
    table_name = obj.__tablename__
    natural = _NATURAL_KEYS.get(table_name)
    if natural is None:
        return json.dumps({"id": getattr(obj, "id", None)}, default=str)
    return json.dumps(
        {field: getattr(obj, field, None) for field in natural},
        default=str,
    )


def _json_safe(value: Any) -> Optional[str]:
    """JSON-encodet Diff-Werte für die Audit-Log-Spalten old_value/new_value."""
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def _decide(
    *,
    existing: Optional[dict[str, Any]],
    new_priority: SourcePriority,
    effective_source: str,
    old_value: Any,
    new_value: Any,
    input_hash: Optional[str],
    force_override: bool,
    writer: str,
) -> tuple[Decision, str, Optional[str]]:
    """Hierarchie-Entscheidung. Reine Funktion ohne Seiteneffekte.

    Returns (decision, decision_reason, conflicting_source).
    """
    if force_override:
        return ("applied", f"force_override (writer={writer})", None)

    if existing is None:
        return ("applied", "initial_write", None)

    existing_source = existing.get("source", "")
    existing_priority = SOURCE_LABELS.get(existing_source)
    existing_hash = existing.get("input_hash")

    # FrodoVDR #251: User-Eingabe (manual:*) ist nicht verhandelbar — sie
    # gewinnt IMMER, auch gegen `repair` und gegen historisch falsch
    # gestempelte Provenance. Wenn jemand explizit auf Speichern klickt,
    # muss der Wert in die DB. Hintergrund-Quellen (auto/external/fallback)
    # dürfen keine UI-Eingabe blockieren — Bedienbarkeit > Audit-Symmetrie.
    if effective_source.startswith("manual:"):
        return (
            "applied",
            f"manual override — user-driven write always applied (was {existing_source!r})",
            existing_source if existing_source else None,
        )

    # No-Op-Detection: gleicher Wert + gleicher Input-Hash heißt
    # idempotenter Re-Import. Spart Audit-Log-Spam bei vollem No-Op,
    # dokumentiert aber den Aufruf trotzdem (Diagnose: „liefert der
    # Cloud-Sync was Neues oder nicht?").
    if (
        input_hash is not None
        and existing_hash == input_hash
        and old_value == new_value
    ):
        return (
            "no_op_same_value",
            f"identical value + input_hash from {effective_source}",
            existing_source,
        )

    # Höhere oder gleiche Priorität → schreibt. Niedrigere Zahl =
    # höhere Priorität (siehe SourcePriority IntEnum).
    if existing_priority is None:
        # Bestehende Source kennen wir nicht (Legacy-Daten ohne Provenance,
        # oder Vokabular-Drift). Nicht stilles Fallback — wir schreiben,
        # aber die Decision-Reason macht das Audit-Log diagnose-bar.
        return (
            "applied",
            f"existing source {existing_source!r} unknown to SOURCE_LABELS — applied as fallback",
            existing_source,
        )

    if new_priority < existing_priority:
        return (
            "applied",
            f"priority {int(new_priority)} < existing {existing_source} ({int(existing_priority)})",
            None,
        )

    if new_priority == existing_priority:
        return (
            "applied",
            f"priority {int(new_priority)} == existing {existing_source} ({int(existing_priority)}) — last writer wins",
            None,
        )

    # new_priority > existing_priority → niedrigere Priorität, abweisen.
    return (
        "rejected_lower_priority",
        f"priority {int(new_priority)} > existing {existing_source} ({int(existing_priority)}) — protected",
        existing_source,
    )


def _make_audit_entry(
    *,
    obj: Any,
    provenance_key: str,
    effective_source: str,
    writer: str,
    old_value: Any,
    new_value: Any,
    input_hash: Optional[str],
    decision: Decision,
    decision_reason: str,
) -> DataProvenanceLog:
    """Erzeugt den Audit-Log-Eintrag (Append-Only)."""
    return DataProvenanceLog(
        table_name=obj.__tablename__,
        row_pk_json=_row_pk_json(obj),
        field_name=provenance_key,
        source=effective_source,
        writer=writer,
        old_value=_json_safe(old_value),
        new_value=_json_safe(new_value),
        input_hash=input_hash,
        decision=decision,
        decision_reason=decision_reason,
    )


# Werte für `abgeleitet` — was für eine Rechnung hinter dem Wert steht (#352).
# Der Wert ist KEINE Quelle und keine Priorität: er sagt nur, dass diese Zahl
# nicht am Gerät gemessen, sondern aus einem Anlagen-Gesamtwert zerlegt wurde.
# Deshalb steht er im Eintrag neben `source`, nicht als eigenes SOURCE_LABEL —
# die Verdrängungs-Hierarchie bleibt unberührt (Entscheid Gernot 2026-08-05).
ABGELEITET_KWP_ANTEIL = "kwp_anteil"
ABGELEITET_KAPAZITAET_ANTEIL = "kapazitaet_anteil"

# N-141 Weg (c): der PV-Anteil einer Heimladung ist nirgends gemessen, sondern
# aus den Stundengrößen des Tages abgeleitet. Die Kennung ist DIESELBE
# Zeichenkette wie die Regel im Layer — importiert statt abgeschrieben, damit
# eine Umbenennung nicht zwei Wahrheiten hinterlässt.
ABGELEITET_EINSPEISE_DECKUNG = REGEL_EINSPEISE_DECKUNG
#: Dieselbe Regel, aber nicht jede Ladestunde war gedeckt ⇒ der Wert ist eine
#: **Teilsumme** der Tagesladung. Eigene Marke statt eines Zusatzfeldes: eine
#: Teilsumme, die aussieht wie eine Gesamtsumme, ist genau der Fehler, den die
#: P4-Linie (`docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`) verhindern soll.
ABGELEITET_EINSPEISE_DECKUNG_TEILWEISE = f"{REGEL_EINSPEISE_DECKUNG}_teilweise"

# Positivliste: was ein Client als Ableitungs-Marke melden darf. Sie ist der
# Vertrag zwischen Oberfläche und Provenance — und sie steht hier, nicht in
# den Routen: bis v4.0.8 gab es zwei Schreibpfade für dieselbe Sache (der
# Wizard-Endpoint und `/monatsdaten`), und eine zweite Kopie der Liste hätte
# genau die Drift erzeugt, gegen die dieses Paket gebaut ist.
ERLAUBTE_ABLEITUNGEN = frozenset({
    ABGELEITET_KWP_ANTEIL,
    ABGELEITET_KAPAZITAET_ANTEIL,
})


def gepruefte_ableitung(wert: Any) -> Optional[str]:
    """Nimmt nur bekannte Ableitungs-Marken an (#352).

    Ein unbekannter String käme sonst ungeprüft in die Provenance und gälte
    dort still als Ableitung, die keine Lesezeit auswerten kann. Verworfene
    Marken landen im Log, damit ein Client-/Backend-Versionsversatz sichtbar
    wird statt still geschluckt zu werden.
    """
    if wert is None:
        return None
    if isinstance(wert, str) and wert in ERLAUBTE_ABLEITUNGEN:
        return wert
    logger.warning(
        "Unbekannte Ableitungs-Marke %r verworfen (erlaubt: %s)",
        wert, ", ".join(sorted(ERLAUBTE_ABLEITUNGEN)),
    )
    return None


def gepruefte_ableitungen(werte: Any) -> dict[str, str]:
    """Feldweise Variante von `gepruefte_ableitung` für Payload-Dicts."""
    if not isinstance(werte, dict):
        return {}
    out: dict[str, str] = {}
    for feld, marke in werte.items():
        geprueft = gepruefte_ableitung(marke)
        if geprueft is not None:
            out[str(feld)] = geprueft
    return out


def _provenance_entry(
    effective_source: str,
    writer: str,
    input_hash: Optional[str],
    abgeleitet: Optional[str] = None,
) -> dict[str, Any]:
    """Baut den source_provenance-Eintrag pro Feld.

    Args:
        abgeleitet: gesetzt, wenn der Wert nicht gemessen, sondern aus einem
            Anlagen-Gesamtwert gerechnet wurde (``ABGELEITET_*``). Die
            Lesezeit stuft solche Werte als „verteilt" statt „gemessen" ein
            (#352) — ohne diesen Schlüssel sieht sie keinen Unterschied.
    """
    entry: dict[str, Any] = {
        "source": effective_source,
        "writer": writer,
        "at": datetime.utcnow().isoformat() + "Z",
    }
    if input_hash is not None:
        entry["input_hash"] = input_hash
    if abgeleitet is not None:
        entry["abgeleitet"] = abgeleitet
    return entry


async def write_with_provenance(
    db: AsyncSession,
    obj: Any,
    field: str,
    value: Any,
    source: str,
    writer: str,
    input_hash: Optional[str] = None,
    *,
    force_override: bool = False,
) -> WriteResult:
    """Atomarer Top-Level-Write mit Hierarchie-Check, No-Op-Detection,
    JSON-Provenance-Update und Append-Only Audit-Log.

    Args:
        db: AsyncSession (Caller committet — der Helper schreibt nur Audit-Log
            + obj-Mutationen in die Session).
        obj: Aggregat-ORM-Objekt (Monatsdaten | InvestitionMonatsdaten |
            TagesZusammenfassung | TagesEnergieProfil).
        field: Spaltenname auf obj, z. B. "netzbezug_kwh".
        value: Neuer Wert.
        source: Label aus SOURCE_LABELS. KeyError wenn unbekannt.
        writer: Identität des Schreibers.
        input_hash: Optional, für No-Op-Detection bei idempotenten Re-Imports.
        force_override: NUR Repair-Orchestrator. Durchbricht Hierarchie,
            schreibt Source als "repair".

    Für Schreiber auf JSON-Sub-Keys (wie InvestitionMonatsdaten.verbrauch_daten)
    siehe `write_json_subkey_with_provenance()`.
    """
    effective_source = "repair" if force_override else source
    new_priority = SOURCE_LABELS[effective_source]

    provenance: dict[str, Any] = obj.source_provenance or {}
    existing = provenance.get(field)
    old_value = getattr(obj, field, None)

    decision, decision_reason, conflicting_source = _decide(
        existing=existing,
        new_priority=new_priority,
        effective_source=effective_source,
        old_value=old_value,
        new_value=value,
        input_hash=input_hash,
        force_override=force_override,
        writer=writer,
    )

    if decision == "applied":
        setattr(obj, field, value)
        provenance[field] = _provenance_entry(effective_source, writer, input_hash)
        obj.source_provenance = provenance
        flag_modified(obj, "source_provenance")

    new_value_for_log = value if decision == "applied" else old_value
    db.add(_make_audit_entry(
        obj=obj, provenance_key=field, effective_source=effective_source,
        writer=writer, old_value=old_value, new_value=new_value_for_log,
        input_hash=input_hash, decision=decision, decision_reason=decision_reason,
    ))

    return WriteResult(
        applied=(decision == "applied"),
        decision=decision,
        reason=decision_reason,
        conflicting_source=conflicting_source,
    )


def seed_provenance(
    obj: Any,
    *,
    source: str,
    writer: str,
    fields: Optional[list[str]] = None,
    json_subkeys: Optional[dict[str, list[str]]] = None,
    abgeleitet_je_subkey: Optional[dict[str, str]] = None,
    abgeleitet_je_feld: Optional[dict[str, str]] = None,
) -> None:
    """Setzt source_provenance für eine FRISCHE Row mit bekanntem Initial-Inhalt.

    Anwendung: Backup-Restore + Demo-Daten + andere Initial-Bulk-Pfade.
    Pro fresh-Anlage hunderte Felder einzeln durch write_with_provenance
    zu schicken würde hunderte Audit-Log-Einträge generieren — ohne
    Diagnose-Mehrwert, weil bei einer fresh Row kein Hierarchie-Konflikt
    möglich ist (existing ist überall None).

    Args:
        fields: Top-Level-ORM-Attribute, deren Provenance gesetzt werden soll.
        json_subkeys: dict[json_attr, list[sub_key]] für JSON-Sub-Keys.
        abgeleitet_je_subkey: ``{sub_key: ABGELEITET_*}`` für Werte, die eine
            Zerlegung sind statt einer Messung (#352). Gilt nur für
            ``json_subkeys`` — eine *Gerätezerlegung* betrifft immer einen
            Sub-Key, nie eine Anlagen-Spalte.
        abgeleitet_je_feld: ``{feld: ABGELEITET_*}`` für **Top-Level**-Spalten,
            deren Wert gerechnet statt gemessen ist (N-141 Weg c: der PV-Anteil
            der Heimladung). Bewusst getrennt von ``abgeleitet_je_subkey``: das
            ist eine andere Aussage — nicht „aus einem Anlagenwert zerlegt",
            sondern „aus anderen Größen abgeleitet". Ohne diese Marke trüge der
            Wert das Label des Aggregator-Laufs (``external:ha_statistics:daily``)
            und behauptete damit eine Messung, die es nicht gibt.

    Verhalten:
        - source_provenance wird direkt gesetzt (KEIN Audit-Log).
        - Caller darf optional EIN summarisches Audit-Event über
          `log_payload_noop()` mit decision="applied"-Sentinel ergänzen.
        - SOURCE_LABELS wird trotzdem geprüft — KeyError bei unbekanntem Label.
    """
    _ = SOURCE_LABELS[source]  # KeyError wenn unbekannt, kein silent fallback
    entry = _provenance_entry(source, writer, input_hash=None)

    provenance: dict[str, Any] = obj.source_provenance or {}
    if fields:
        feld_marken = abgeleitet_je_feld or {}
        for field in fields:
            feld_entry = dict(entry)
            if feld_marken.get(field):
                feld_entry["abgeleitet"] = feld_marken[field]
            provenance[field] = feld_entry
    if json_subkeys:
        marken = abgeleitet_je_subkey or {}
        for json_attr, sub_keys in json_subkeys.items():
            for sub_key in sub_keys:
                sub_entry = dict(entry)
                if marken.get(sub_key):
                    sub_entry["abgeleitet"] = marken[sub_key]
                provenance[f"{json_attr}.{sub_key}"] = sub_entry
    obj.source_provenance = provenance
    flag_modified(obj, "source_provenance")


def log_delete(
    db: AsyncSession,
    obj: Any,
    *,
    source: str,
    writer: str,
    decision_reason: str = "manual_delete",
) -> None:
    """Audit-Log-Eintrag für DELETE-Operation auf einer Aggregat-Row.

    DELETE ist auch ein Schreib-Akt: das Entfernen einer Row löscht alle
    Felder gleichzeitig. Wir loggen pro DELETE einen einzigen Eintrag
    mit Sentinel-Key `__row__` und `decision="applied"` — analog zu
    `log_payload_noop` für Re-Imports.

    Anwendung: `routes/monatsdaten.py:delete_monatsdaten` u. ä.
    Aufrufer ruft VOR `db.delete(obj)`, damit `_row_pk_json(obj)` noch
    die Natural-Keys serialisieren kann.
    """
    _ = SOURCE_LABELS[source]  # KeyError bei unbekanntem Label
    db.add(_make_audit_entry(
        obj=obj,
        provenance_key="__row__",
        effective_source=source,
        writer=writer,
        old_value=None,
        new_value=None,
        input_hash=None,
        decision="applied",
        decision_reason=decision_reason,
    ))


def log_payload_noop(
    db: AsyncSession,
    obj: Any,
    *,
    source: str,
    writer: str,
    input_hash: str,
    sentinel_key: str = "__payload__",
) -> None:
    """Loggt ein einzelnes no_op_same_value-Event auf Payload-Ebene.

    Anwendung: Re-Import-Pfade (Cloud-Sync, CSV-Re-Import), die einen
    identischen Payload-Hash erkennen und KEINEN einzelnen Sub-Key durch
    den Resolver schicken müssen. Statt pro Sub-Key zu spammen,
    dokumentieren wir EINEN Audit-Eintrag auf einem Sentinel-Key.

    Diagnose-Frage: „liefert der Cloud-Sync was Neues oder nicht?" lässt
    sich danach via `SELECT decision, COUNT(*) FROM data_provenance_log
    GROUP BY decision` beantworten.
    """
    db.add(_make_audit_entry(
        obj=obj,
        provenance_key=sentinel_key,
        effective_source=source,
        writer=writer,
        old_value=None,
        new_value=None,
        input_hash=input_hash,
        decision="no_op_same_value",
        decision_reason=f"identical payload hash from {source}",
    ))


async def write_json_subkey_with_provenance(
    db: AsyncSession,
    obj: Any,
    json_attr: str,
    sub_key: str,
    value: Any,
    source: str,
    writer: str,
    input_hash: Optional[str] = None,
    *,
    force_override: bool = False,
    abgeleitet: Optional[str] = None,
) -> WriteResult:
    """Per-JSON-Sub-Key-Variante von write_with_provenance.

    Anwendung: InvestitionMonatsdaten.verbrauch_daten ist ein JSON-Dict
    (z. B. {"km_gefahren": 1200, "ladung_kwh": 130, ...}). Provenance soll
    pro Sub-Key getrennt geführt werden, damit ein Cloud-Sync den Sub-Key
    `km_gefahren` nicht überschreibt, wenn der User ihn manuell gepflegt hat —
    während er andere Sub-Keys legitim aktualisiert.

    Implementierung: provenance_key wird `f"{json_attr}.{sub_key}"`,
    z. B. `"verbrauch_daten.ladung_kwh"`. Mutation findet auf dem
    JSON-Dict-Eintrag statt (mit flag_modified auf json_attr).

    Args:
        json_attr: Name der JSON-Spalte auf obj (z. B. "verbrauch_daten").
        sub_key: Schlüssel im Dict (z. B. "ladung_kwh").
        abgeleitet: ``ABGELEITET_*``, wenn der Wert die Zerlegung eines
            Anlagen-Gesamtwerts ist und keine Gerätemessung (#352).
        Restliche Args wie write_with_provenance.
    """
    effective_source = "repair" if force_override else source
    new_priority = SOURCE_LABELS[effective_source]

    provenance_key = f"{json_attr}.{sub_key}"
    provenance: dict[str, Any] = obj.source_provenance or {}
    existing = provenance.get(provenance_key)

    json_dict: dict[str, Any] = dict(getattr(obj, json_attr) or {})
    old_value = json_dict.get(sub_key)

    decision, decision_reason, conflicting_source = _decide(
        existing=existing,
        new_priority=new_priority,
        effective_source=effective_source,
        old_value=old_value,
        new_value=value,
        input_hash=input_hash,
        force_override=force_override,
        writer=writer,
    )

    if decision == "applied":
        json_dict[sub_key] = value
        setattr(obj, json_attr, json_dict)
        flag_modified(obj, json_attr)

        provenance[provenance_key] = _provenance_entry(
            effective_source, writer, input_hash, abgeleitet
        )
        obj.source_provenance = provenance
        flag_modified(obj, "source_provenance")

    new_value_for_log = value if decision == "applied" else old_value
    db.add(_make_audit_entry(
        obj=obj, provenance_key=provenance_key, effective_source=effective_source,
        writer=writer, old_value=old_value, new_value=new_value_for_log,
        input_hash=input_hash, decision=decision, decision_reason=decision_reason,
    ))

    return WriteResult(
        applied=(decision == "applied"),
        decision=decision,
        reason=decision_reason,
        conflicting_source=conflicting_source,
    )
