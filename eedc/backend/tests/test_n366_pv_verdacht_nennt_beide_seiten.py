"""Die Doppelerfassungs-Meldung nennt beide Seiten des PR-Bruchs (#353).

**Der Fall** (coolxmad, 2026-09-01): Der Daten-Check meldete „Verdacht auf
PV-Doppelerfassung". Er hat die drei genannten Ursachen einzeln geprüft und
alle drei ausgeschlossen — kein Balkonkraftwerk, keine doppelte Zuordnung,
kWp korrekt. Danach hatte er **keinen nächsten Schritt** und ist den
Log-Meldungen nachgegangen, die mit seiner Frage nichts zu tun hatten.

**Warum die Liste unvollständig war:** Die Performance Ratio ist
``Ertrag ÷ (Einstrahlung × kWp)`` (``energie_profil/aggregator.py``). Sie kann
über 1 gehen, weil der Zähler zu groß ist — oder weil der **Nenner** zu klein
ist, und der hat *zwei* Faktoren. Die Liste nannte nur ``kWp``. Dass die
Einstrahlungsseite in der Praxis trägt, steht im Baum: der Kommentar an der
PR-Rechenstelle nennt GTI-bedingte PR-Werte von 1,5–2,8 (#139), und v4.0.21 hat
einen Standort behoben, an dem gar keine Strahlung ankam.

⚠ Diese Probe prüft den **Text**, nicht die Schwellen — an der Erkennung wurde
nichts geändert.
"""

from __future__ import annotations

import inspect
import re

from backend.services.daten_checker.energieprofil import EnergieprofilChecks


def _meldungs_quelltext() -> str:
    return inspect.getsource(EnergieprofilChecks._check_pv_ueber_erfassung)


def _aufzaehlungspunkte(details: str) -> list[str]:
    """Die „• …"-Punkte der Ursachenliste, je Punkt eine zusammengefügte Zeile.

    ⚠ **Nicht auf das blosse Wort prüfen.** Ein erster Entwurf dieser Datei
    fragte `"Einstrahlung" in details` — und blieb grün, als der Sprengsatz den
    Aufzählungspunkt entfernte, weil das Wort auch in der Erklärung des Bruchs
    steht. Ein Prüfer, der nicht rot werden kann, beweist nichts (gemessen
    2026-09-02).
    """
    # ⚠ Erst auf den Ursachen-Block schneiden: die Marker-Zeilen darüber werden
    # ebenfalls mit „• " aufgebaut (f-String) und zählten sonst mit.
    block = details.split("Mögliche Ursachen")[-1].split("Tage mit bekanntem")[0]
    return [stueck.split("\\n\\n")[0] for stueck in block.split("• ")[1:]]


def test_die_ursachenliste_nennt_die_einstrahlung():
    """Die vierte Ursache steht als eigener Aufzählungspunkt im Anwender-Text."""
    details = _meldungs_quelltext().split(
        'meldung="Verdacht auf PV-Doppelerfassung')[-1]
    punkte = _aufzaehlungspunkte(details)
    treffer = [p for p in punkte if "Einstrahlung" in p]
    assert treffer, (
        "Kein Aufzählungspunkt nennt die Einstrahlungsseite des PR-Bruchs — "
        "wer die anderen Ursachen ausschließt, hat keinen nächsten Schritt. "
        f"Gefundene Punkte: {[p[:40] for p in punkte]}"
    )


def test_vier_ursachen_statt_drei():
    """Die Liste hat vier Punkte — Zähler (2), kWp, Einstrahlung.

    Zweite Diskriminierung gegen die Wort-Falle: Sie zählt, statt zu suchen.
    """
    details = _meldungs_quelltext().split(
        'meldung="Verdacht auf PV-Doppelerfassung')[-1]
    punkte = _aufzaehlungspunkte(details)
    assert len(punkte) == 4, (
        f"Erwartet vier Ursachen, gefunden {len(punkte)}: "
        f"{[p[:40] for p in punkte]}"
    )


def test_die_liste_nennt_auch_einen_pruefweg_dorthin():
    """Ein Ursachen-Name ohne Weg ist für den Anwender eine Suchaufgabe.

    Der Weg muss **im selben Punkt** stehen, nicht irgendwo im Text.
    """
    details = _meldungs_quelltext().split(
        'meldung="Verdacht auf PV-Doppelerfassung')[-1]
    punkt = next(
        (p for p in _aufzaehlungspunkte(details) if "Einstrahlung" in p), ""
    )
    assert re.search(r"Ausrichtung", punkt), (
        "Die Einstrahlungs-Ursache nennt keinen Prüfweg (Ausrichtung/Neigung)."
    )


def test_beide_seiten_des_bruchs_kommen_vor():
    """Diskriminierung: Zähler-Seite UND Nenner-Seite müssen vertreten sein.

    Ohne diese Probe wäre eine Liste grün, die die alten drei Ursachen durch
    die neue **ersetzt** statt sie zu ergänzen.
    """
    details = _meldungs_quelltext().split(
        'meldung="Verdacht auf PV-Doppelerfassung')[-1]
    zaehler_seite = "Balkonkraftwerk" in details and "zweimal zugeordnet" in details
    nenner_seite = "kWp ist zu niedrig" in details and "Einstrahlung" in details
    assert zaehler_seite, "Die Zähler-Ursachen sind verlorengegangen"
    assert nenner_seite, "Der Nenner ist nur halb beschrieben"
