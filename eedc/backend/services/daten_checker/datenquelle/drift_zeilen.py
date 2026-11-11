"""Daten-Checker — die Zeilen der Drift-Prüfung (Etappe E5 des Vorhabens «Daten-Checker: ein Handgriff je Befund», Konzept §6 V2).

Umzug aus ``quellen.py`` (Bauplan §3.1: Drift-Gruppenbau in eigener Datei): die Tageszeilen der ersten Achse (PV/BKW je Tag,
höchstens 20, die übrigen als ``werte.weitere`` — die Gruppenzeile «n Tage weichen von Home Assistant ab» baut
``gruppen.py``) und die Zeilen der zweiten Achse (je Komponente eine). Texte, Zahlen und Handgriffe unverändert; die
frühere Restzeile «… plus n weitere Tag(e) mit Drift» ist entfallen (Teil B Nr 23).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from backend.core.zahlenformat import fmt_pct, fmt_zahl
from backend.services.daten_checker.kategorien import (
    Aktion,
    CheckErgebnis,
    CheckSeverity,
    aktion_spiegel_abgleich_tag,
)

if TYPE_CHECKING:
    from backend.services.daten_checker.datenquelle.quellen import _DriftKontext


#: N-790: der Details-Text einer Drift-Tageszeile an einer Anlage mit HA-Spiegel (die Zahlen stehen in der Meldung).
_TEXT_SPIEGEL_TAG = (
    "Für diesen Tag steht in eedc ein anderer Wert als in Home Assistant. „Aus Home Assistant neu übernehmen“ holt die "
    "Statistik aller gespiegelten Zähler der Anlage ab der ersten Abweichung neu und baut den Tag danach auf — der Tag "
    "zeigt dann, was Home Assistant zeigt. Hast du in Home Assistant korrigiert, ist das der Weg."
)


#: N-791: der Details-Text an einem Bestand-Tag (die Gruppe liest den Tag nicht aus dem HA-Spiegel) — die Aktion ist
#: dieselbe; die Neu-Aggregation schreibt den Tag aus der Zählerstatistik, auch ohne Leistungskurve.
_TEXT_BESTAND_TAG = (
    "Für diesen Tag steht in eedc ein anderer Wert als in Home Assistant. „Aus Home Assistant neu übernehmen“ holt die "
    "Zählerstatistik dieses Tages neu und baut Tag und Gerätewerte; ein gespeicherter Leistungsverlauf bleibt stehen."
)


def _bestand_tag(ctx: "_DriftKontext", datum_: date, schluessel: str | None = None) -> bool:
    """Liest die Gruppe (Bilanz bzw. die des Geräte-Schlüssels) an ``datum_`` aus dem Bestand statt aus dem Spiegel?"""
    from backend.services.energie_profil.kanal_stunden import GRUPPE_BILANZ, gruppen_der_schluessel

    gruppe = gruppen_der_schluessel([schluessel])[-1] if schluessel else GRUPPE_BILANZ
    return gruppe not in ctx.kanal_gruppen.get(datum_, ())


def _drift_aktion(ctx: "_DriftKontext", datum_: date) -> Aktion:
    """Der Handgriff einer Drift-Zeile (N-790): mit HA-Spiegel «Aus Home Assistant neu übernehmen» (Abgleich, danach
    der Tag neu aufgebaut), ohne Spiegel «Tag reparieren» (Neu-Aggregation des Tages) wie bisher."""
    if ctx.hat_spiegel:
        return aktion_spiegel_abgleich_tag(ctx.anlage.id, datum_)
    return Aktion("reaggregate_day", {"datum": datum_.isoformat()})


def drift_tageszeilen(ctx: "_DriftKontext") -> list[CheckErgebnis]:
    """Die Tageszeilen der ersten Achse samt Handgriff (mit HA-Spiegel «Aus Home Assistant neu übernehmen», sonst
    «Tag neu aufbauen», N-790); höchstens 20 (|Δ| absteigend), die übrigen als ``werte.weitere`` (E5 V2)."""
    kat, drift_pro_tag = ctx.kat, ctx.drift_pro_tag

    # Sortierung nach |Δ| desc, max 20 Einträge
    drift_pro_tag.sort(key=lambda x: abs(x[1] - x[2]), reverse=True)
    gekuerzt = drift_pro_tag[:20]
    rest = len(drift_pro_tag) - len(gekuerzt)

    weitere = {"weitere": rest} if rest else {}
    ergebnisse: list[CheckErgebnis] = []
    for datum_, eedc, ha in gekuerzt:
        delta_signed = ha - eedc
        rel_signed = (delta_signed / max(eedc, ha)) * 100 if max(eedc, ha) > 0 else 0.0
        details = (_TEXT_BESTAND_TAG if _bestand_tag(ctx, datum_) else _TEXT_SPIEGEL_TAG) if ctx.hat_spiegel else (
            f"Dein eedc-Wert für {datum_.isoformat()} ist {fmt_zahl(eedc, 2)} kWh PV-Erzeugung. "
            f"Die HA-Statistics liefert für denselben Tag {fmt_zahl(ha, 2)} kWh. "
            f"Mit „Tag neu aufbauen“ schreibt eedc den Wert aus HA-Statistics "
            f"in deine Tages-Zusammenfassung."
        )
        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.INFO.value,
            meldung=(
                f"{datum_.isoformat()}: PV {fmt_zahl(eedc, 1)} → HA {fmt_zahl(ha, 1)} kWh "
                f"(Δ {fmt_zahl(delta_signed, 1, vorzeichen=True)} kWh, "
                f"{fmt_pct(rel_signed, 1, vorzeichen=True)})"
            ),
            details=details,
            action=_drift_aktion(ctx, datum_),
            code="drift_tag",
            werte={"datum": datum_.isoformat(), "achse": "pv", "eedc": eedc, "ha": ha, "delta": delta_signed,
                   "prozent": rel_signed, **weitere},
        ))

    return ergebnisse

def drift_komponentenzeilen(ctx: "_DriftKontext") -> list[CheckErgebnis]:
    """Die Zeilen der zweiten Achse (N-201): je Komponente EIN Eintrag, die größte Abweichung zuerst."""
    kat, alle_invs, drift_komponente = ctx.kat, ctx.alle_invs, ctx.drift_komponente

    # N-201: je Komponente EIN Eintrag — mit dem schlimmsten Tag als
    # Beleg und als Reparatur-Ziel. Dreißig gleichlautende Tageszeilen für
    # eine Wallbox wären keine Auskunft, sondern Rauschen.
    from backend.services.snapshot.komponenten_beitraege import komponenten_key_label
    ergebnisse: list[CheckErgebnis] = []

    inv_je_id = {str(inv.id): inv for inv in alle_invs}
    for key in sorted(
        drift_komponente,
        key=lambda k: max(abs(e - h) for _, e, h in drift_komponente[k]),
        reverse=True,
    ):
        tage = drift_komponente[key]
        _, _, rest_id = key.rpartition("_")
        label = komponenten_key_label(key, inv_je_id.get(rest_id))
        schlimmster = max(tage, key=lambda t: abs(t[1] - t[2]))
        datum_, eedc, ha = schlimmster
        delta_signed = ha - eedc
        rel_signed = (delta_signed / max(eedc, ha)) * 100 if max(eedc, ha) > 0 else 0.0
        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.INFO.value,
            meldung=(
                f"{label}: {len(tage)} Tag(e) weichen von HA-Statistics ab "
                f"(größte Abweichung {datum_.isoformat()}: "
                f"{fmt_zahl(eedc, 1)} → {fmt_zahl(ha, 1)} kWh, "
                f"Δ {fmt_zahl(delta_signed, 1, vorzeichen=True)} kWh, "
                f"{fmt_pct(rel_signed, 1, vorzeichen=True)})"
            ),
            details=(
                f"Für diese Komponente steht in eedc an {len(tage)} Tag(en) ein anderer Wert als in "
                f"Home Assistant. Diese Werte tragen die Wirtschaftlichkeits- und CO₂-Rechnung mit. "
                f"„Aus Home Assistant neu übernehmen“ holt die Zählerstatistik des Tages {datum_.isoformat()} "
                f"neu und baut Tag und Gerätewerte; ein gespeicherter Leistungsverlauf bleibt stehen."
            ) if ctx.hat_spiegel and _bestand_tag(ctx, datum_, key) else (
                f"Für diese Komponente steht in eedc an {len(tage)} Tag(en) ein anderer Wert als in "
                f"Home Assistant. Diese Werte tragen die Wirtschaftlichkeits- und CO₂-Rechnung mit. "
                f"„Aus Home Assistant neu übernehmen“ holt die Statistik aller gespiegelten Zähler der Anlage ab "
                f"der ersten Abweichung neu und baut den Tag {datum_.isoformat()} danach auf — die Tage zeigen dann, "
                f"was Home Assistant zeigt. Hast du in Home Assistant korrigiert, ist das der Weg."
            ) if ctx.hat_spiegel else (
                f"Für diese Komponente steht in deiner Tages-Zusammenfassung "
                f"an {len(tage)} Tag(en) ein anderer Wert als in den "
                f"HA-Statistics. Diese Werte tragen die Wirtschaftlichkeits- "
                f"und CO₂-Rechnung mit. „Tag neu aufbauen“ schreibt den Tag "
                f"{datum_.isoformat()} aus HA-Statistics neu; für alle Tage "
                f"auf einmal: „Mehrere Tage neu aggregieren“ in der "
                f"Reparatur-Werkbank."
            ),
            action=_drift_aktion(ctx, datum_),
            investition_id=(
                int(rest_id) if rest_id.isdigit() else None
            ),
            code="drift_komponente",
            werte={"komponente": key, "tage": len(tage), "datum": datum_.isoformat(), "eedc": eedc, "ha": ha,
                   "delta": delta_signed, "prozent": rel_signed},
        ))

    return ergebnisse
