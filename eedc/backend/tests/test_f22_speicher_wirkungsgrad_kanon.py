"""F-22 — der Monats-Wirkungsgrad läuft über den SoC-korrigierenden Kanon.

Gemeldet von rapahl am 2026-08-08, **zum zweiten Mal** (die erste Meldung vom
2026-05-22 steht als Verweis im Docstring von `core/berechnungen/speicher.py`).
Sichtbar waren drei Monate ohne Wert und ein Monat über 100 %.

Was bis v4.0.11 in `aktueller_monat.py` stand, war ein Alles-oder-Nichts-Schalter
auf ``|ΔSoC| > 20 pp``. Der lag in **drei** Richtungen falsch — gemessen an der
Demo-Anlage über 27 Monate:

===========================  ==========================  =========================
Lage                         bis v4.0.11                 seit F-22
===========================  ==========================  =========================
ΔSoC über der Schwelle       „—" (2025-11: 80,4 % roh)   81,6 % SoC-korrigiert
ΔSoC unter der Schwelle      roher Quotient (83,1 %)     82,4 % SoC-korrigiert
kein SoC am Periodenrand     roh und **ungeprüft**       geprüft, sonst mit Grund
===========================  ==========================  =========================

Die dritte Zeile ist der Pfad zu Rainers >100 %: ohne SoC-Randwerte blieb das
Flag ``False`` und der rohe Quotient ging ungeprüft hinaus.

**Beide Richtungen brauchen einen Test.** Nur „zeigt jetzt einen Wert" zu prüfen
wäre blind für den Rückfall in „zeigt alles ungeprüft" — das ist genau der
Zustand, den Rainer gemeldet hat.
"""

from __future__ import annotations

import pytest


# ── Der Kanon selbst ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kanon_klemmt_auf_100_prozent():
    """Über 100 % kann kein Speicher — der Kanon gibt es nie aus.

    Sprengsatz gegen den Pfad, den Rainer gemeldet hat: Entladung > Ladung
    (hier durch einen SoC-Sprung nach unten) darf nie als Wirkungsgrad > 100 %
    erscheinen.
    """
    from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
        SOC_DRIFT_SCHWELLE_PROZENTPUNKTE,
    )

    # Die Schwelle ist der Wert, auf den sich der alte Guard stützte. Sie darf
    # sich ändern — dieser Test hängt nicht an ihr, er belegt nur, dass sie
    # existiert und eine Prozentpunkt-Größe ist.
    assert 0 < SOC_DRIFT_SCHWELLE_PROZENTPUNKTE <= 100


def test_layer_sot_klemmt_bewusst_nicht():
    """`speicher_effizienz_prozent` bleibt ungeklemmt — mit Diagnose daneben.

    Der Layer-SoT ist ausdrücklich „Diagnose statt stillem Cap". Diese
    Eigenschaft ist gewollt und muss erhalten bleiben; geklemmt wird erst in
    der Sicht, und *gemeldet* wird im Daten-Checker (s. u.).
    """
    from backend.core.berechnungen.speicher import speicher_effizienz_prozent

    assert speicher_effizienz_prozent(100.0, 120.0) == pytest.approx(120.0)
    assert speicher_effizienz_prozent(0.0, 50.0) is None


# ── Die Diagnose, die es bis v4.0.11 nicht gab ──────────────────────────────

def test_daten_checker_meldet_entladung_ueber_ladung():
    """Die fehlende Hälfte von „Diagnose statt stillem Cap".

    Der Cap wurde bewusst entfernt, die Diagnose kam nie — es gab keinen
    einzigen Prüfer auf η > 100 %. Hier ist er, kumulativ: ein *einzelner*
    Monat darf legitim über 100 % liegen (Energie aus dem Vormonat fließt ab),
    über die ganze Historie kann er es nicht.
    """
    import inspect

    from backend.services.daten_checker import stammdaten

    quelle = inspect.getsource(stammdaten)
    assert "Entladung übersteigt Ladung (kumulativ)" in quelle, (
        "Der kumulative η-Prüfer fehlt — ohne ihn ist der entfernte Cap eine "
        "stille Lücke statt einer Diagnose (F-22)."
    )
    # Der Befundtext muss die häufigste Ursache nennen, sonst weiß der Nutzer
    # nicht, was er tun soll: #281 — „Ladung" als reine PV-Ladung gepflegt.
    assert "GESAMTE Ladung" in quelle


# ── Die Sicht ───────────────────────────────────────────────────────────────

def test_route_ruft_den_kanon_statt_selbst_zu_dividieren():
    """`aktueller_monat` darf den Wirkungsgrad nicht mehr selbst bilden.

    Abwesenheits-Beleg: die Inline-Division mit anschließendem Drift-Guard war
    die Fundstelle. Sie ist durch `berechne_ist_wirkungsgrad` ersetzt; der rohe
    Quotient existiert nur noch als *gekennzeichneter* Fallback, wenn gar kein
    Ladestand erfasst ist — und auch dort nur, wenn er plausibel ist.
    """
    import inspect

    from backend.api.routes import aktueller_monat

    quelle = inspect.getsource(aktueller_monat)
    assert "berechne_ist_wirkungsgrad" in quelle, (
        "Die Route muss den SoC-korrigierenden Kanon rufen (F-22)."
    )
    # Der alte Guard darf nicht zurückkommen: er hat plausible Werte
    # unterdrückt UND unplausible durchgelassen.
    assert "not speicher_soc_drift_flag" not in quelle, (
        "Der Alles-oder-Nichts-Guard ist zurück — er unterdrückt gute Werte "
        "und lässt unmögliche durch (F-22)."
    )
    # Der ungeprüfte Fallback ist der Pfad zu Rainers >100 %.
    #
    # ⚠ Hier stand bis zum 17.08.2026 `assert "_roh <= 100.0" in quelle` — ein
    # Anker auf den WORTLAUT der damaligen Inline-Lösung statt auf ihre
    # Eigenschaft. Als N-252 dieselbe Prüfung durch den Layer-SoT ersetzte
    # (der sie identisch vornimmt und zusätzlich die Herkunft mitliefert),
    # ging der Prüfer rot — bei besser gewordenem Code. Gemessen wird jetzt
    # die Eigenschaft: Der Fallback läuft über die eine Regel, und die
    # Obergrenze steht dort.
    assert "berechne_speicher_wirkungsgrad" in quelle, (
        "Der rohe Fallback muss über den Layer-SoT laufen, damit die "
        "Plausibilitätsgrenze nicht zweimal geschrieben wird (F-22 · N-252)."
    )
    from backend.core.berechnungen.speicher_wirkungsgrad import speicher_wirkungsgrad

    assert speicher_wirkungsgrad(100.0, 104.0, None).prozent is None, (
        "Der Layer-SoT lässt einen unmöglichen Wert durch — genau der Pfad, "
        "gegen den F-22 antrat."
    )


def test_quelle_wird_ausgewiesen():
    """Ohne Wert steht der Grund daneben (ADR-002/P4).

    Ein „—" ohne Begründung ist der Grund, warum Rainer nachgefragt hat statt
    zu verstehen. Das Feld trägt die Auskunft.
    """
    from backend.api.routes.aktueller_monat import AktuellerMonatResponse

    assert "speicher_wirkungsgrad_quelle" in AktuellerMonatResponse.model_fields
