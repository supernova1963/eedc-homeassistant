"""Haltewerte der „Soll unklar"-Sichten beider Abnahme-Matrizen (HA-Bauform E0, eingefroren 05.10.2026).

Eine „Soll unklar"-Sicht wird gemessen und gezeigt, aber nicht bewertet — die Regel legt ihr Soll nicht fest
(``test_pv_achse_matrix.SOLL_UNKLAR``; ``test_achsen_matrix._soll_unklar``: ``SOLL_UNKLAR_MENGE``, die
Klima-Arbeitszahl; die S3-Vor-Regel ``_U_SA_VOR`` ist mit N-758 entfallen). Damit der Umbau auf die HA-Bauform
(``~/.claude/plans/bauplan-ha-bauform-s1-s2.md`` §7, letzte Zeile) sie nicht **still** ändert, steht hier je
Sicht der gemessene Wert gegen HEAD ``263c9d12``; ``test_soll_unklar_haltewert`` in beiden Matrix-Dateien prüft
„gemessen == festgehalten" (``None`` = keine Angabe; Zahl gleich bis 1e-6) und, dass jede „Soll unklar"-Sicht
genau einen Haltewert hat.

**Kein Soll.** Ein Haltewert sagt nicht, dass der Wert richtig ist — die Fachentscheide folgen getrennt. Wer einen
Wert absichtlich ändert (Fachentscheid oder Umbau mit benanntem Zielwert), ändert ihn hier mit Verweis; fällt eine
Sicht aus „Soll unklar" heraus, fällt ihr Haltewert mit.

Erzeugt aus der Messung beider Matrizen (Berlin; ``TZ=UTC`` gemessen identisch), Bericht
``~/.claude/plans/opus-berichte/HA-BAUFORM-E0.md`` Punkt 4.
"""

from __future__ import annotations

from typing import Optional

#: ``(Form, Weg, Invariante, Sicht) → gemessener Wert`` — PV-Matrix. Seit N-758 (17.10.2026, Konzept R-11/E6, Freigabe
#: Master) leer: die 116 Sichten der S3-Vor-Regel ``_U_SA_VOR`` (29 Formen × I2/I3/I5/I6, alle ``None``) haben das Soll
#: der normalen Regel — vor dem Streichen je Sicht alt/neu/Fakten geprüft, 0 rot
#: (``~/.claude/plans/ha-bauform-werkzeug/fund-n758/haltewerte_alt_neu.md``). Früher entfallen: ``bkw_hub:*`` (K4,
#: N-664/N-671), das CO₂ der ROI-Zeile (B7, N-647).
PV_HALTEWERTE: dict[tuple[str, str, str, str], Optional[float]] = {}

#: ``(Form, Größe, Weg, Invariante, Sicht) → gemessener Wert`` — Achsen-Matrix, 415 Sichten (E4d: +26); die 6 Sichten
#: Hub-Verlauf (letzter Block) sind mit N-645 entfallen. Mit N-673 (K5, 11.10.2026) sind 204 Heizung-/Warmwasser-
#: Sichten von M05 (W1, 114) und M07 (W5, 90) entfallen. Mit N-758 (17.10.2026, Freigabe Master) sind die 124 S3-Sichten
#: ``…:cockpit_monat:vor=nach`` der Regel ``_U_SA_VOR`` entfallen (Soll der normalen Regel, alt/neu/Fakten geprüft, 0 rot,
#: ``~/.claude/plans/ha-bauform-werkzeug/fund-n758/haltewerte_alt_neu.md``); die zwei von M05 ``modus_heizen``/
#: ``modus_warmwasser`` bleiben — sie sind über ``SOLL_UNKLAR_MENGE`` (W1) „Soll unklar", nicht über die S3-Regel.
ACHSEN_HALTEWERTE: dict[tuple[str, str, str, str, str], Optional[float]] = {
    ('M05', 'wp', 'HA', 'I1', 'modus_heizen:cockpit_jahr'): 19.5,  # E4d: war None (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'HA', 'I1', 'modus_heizen:fakten_tw'): 19.5,  # S4 E-S4-1: war 19.8 — Kalendermonat ohne die Stunde 30.06. 23:00 (Randstunde, Heizen 0,3 kWh)
    ('M05', 'wp', 'HA', 'I1', 'modus_warmwasser:cockpit_jahr'): 1.8,  # E4d: war None (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'HA', 'I1', 'modus_warmwasser:fakten_tw'): 1.8,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'HA', 'I3', 'modus_heizen:cockpit_monat'): 19.5,  # E4d: war None (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'HA', 'I3', 'modus_heizen:fakten_tw'): 19.5,  # S4 E-S4-1: war 19.8 — Kalendermonat ohne die Stunde 30.06. 23:00 (Randstunde, Heizen 0,3 kWh)
    ('M05', 'wp', 'HA', 'I3', 'modus_warmwasser:cockpit_monat'): 1.8,  # E4d: war None (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'HA', 'I3', 'modus_warmwasser:fakten_tw'): 1.8,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I1', 'modus_heizen:cockpit_jahr'): 198.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I1', 'modus_heizen:cockpit_monat'): 198.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I1', 'modus_heizen:uebersicht'): 217.5,  # S4 E-S4-1: war 217.8 — Kalendermonat ohne die Stunde 30.06. 23:00 (Randstunde, Heizen 0,3 kWh)
    ('M05', 'wp', 'S1', 'I1', 'modus_heizen:zeitreihe'): 198.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I1', 'modus_warmwasser:cockpit_jahr'): 18.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I1', 'modus_warmwasser:cockpit_monat'): 18.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I1', 'modus_warmwasser:uebersicht'): 19.8,  # E4d: war 0.0 (Kanal-Leser; H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I1', 'modus_warmwasser:zeitreihe'): 18.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I2', 'modus_heizen:cockpit_monat:vor=nach'): 198.0,  # E4d: war None (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I2', 'modus_heizen:fakten:tageswert=gespeichert'): 198.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I2', 'modus_warmwasser:cockpit_monat:vor=nach'): 18.0,  # E4d: war None (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I2', 'modus_warmwasser:fakten:tageswert=gespeichert'): 18.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I3', 'modus_heizen:cockpit_monat'): 198.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I3', 'modus_heizen:fakten'): 198.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I3', 'modus_warmwasser:cockpit_monat'): 18.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S1', 'I3', 'modus_warmwasser:fakten'): 18.0,  # E4d: war 0.0 (H-1: Abschluss schreibt den Kanal-Split, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I1', 'modus_heizen:cockpit_jahr'): 198.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I1', 'modus_heizen:cockpit_monat'): 198.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I1', 'modus_heizen:uebersicht'): 217.5,  # S4 E-S4-1: war 217.8 — Kalendermonat ohne die Stunde 30.06. 23:00 (Randstunde, Heizen 0,3 kWh)
    ('M05', 'wp', 'S2', 'I1', 'modus_heizen:zeitreihe'): 198.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I1', 'modus_warmwasser:cockpit_jahr'): 18.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I1', 'modus_warmwasser:cockpit_monat'): 18.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I1', 'modus_warmwasser:uebersicht'): 19.8,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I1', 'modus_warmwasser:zeitreihe'): 18.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I2', 'modus_heizen:cockpit_monat:vor=nach'): 198.0,  # E4d: war None (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I2', 'modus_heizen:fakten:tageswert=gespeichert'): 198.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I2', 'modus_warmwasser:cockpit_monat:vor=nach'): 18.0,  # E4d: war None (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I2', 'modus_warmwasser:fakten:tageswert=gespeichert'): 18.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I3', 'modus_heizen:cockpit_monat'): 198.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I3', 'modus_heizen:fakten'): 198.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I3', 'modus_warmwasser:cockpit_monat'): 18.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S2', 'I3', 'modus_warmwasser:fakten'): 18.0,  # E4d: war 0.0 (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M05', 'wp', 'S3', 'I1', 'modus_heizen:cockpit_jahr'): None,
    ('M05', 'wp', 'S3', 'I1', 'modus_heizen:cockpit_monat'): None,
    ('M05', 'wp', 'S3', 'I1', 'modus_heizen:uebersicht'): None,
    ('M05', 'wp', 'S3', 'I1', 'modus_heizen:zeitreihe'): None,
    ('M05', 'wp', 'S3', 'I1', 'modus_warmwasser:cockpit_jahr'): None,
    ('M05', 'wp', 'S3', 'I1', 'modus_warmwasser:cockpit_monat'): None,
    ('M05', 'wp', 'S3', 'I1', 'modus_warmwasser:uebersicht'): None,
    ('M05', 'wp', 'S3', 'I1', 'modus_warmwasser:zeitreihe'): None,
    ('M05', 'wp', 'S3', 'I2', 'modus_heizen:cockpit_monat:vor=nach'): None,
    ('M05', 'wp', 'S3', 'I2', 'modus_heizen:fakten:tageswert=gespeichert'): 0.0,
    ('M05', 'wp', 'S3', 'I2', 'modus_warmwasser:cockpit_monat:vor=nach'): None,
    ('M05', 'wp', 'S3', 'I2', 'modus_warmwasser:fakten:tageswert=gespeichert'): 0.0,
    ('M05', 'wp', 'S3', 'I3', 'modus_heizen:cockpit_monat'): None,
    ('M05', 'wp', 'S3', 'I3', 'modus_heizen:fakten'): 0.0,
    ('M05', 'wp', 'S3', 'I3', 'modus_warmwasser:cockpit_monat'): None,
    ('M05', 'wp', 'S3', 'I3', 'modus_warmwasser:fakten'): 0.0,
    ('M05', 'wp', 'SA', 'I1', 'modus_heizen:cockpit_jahr'): None,
    ('M05', 'wp', 'SA', 'I1', 'modus_heizen:fakten_tw'): 0.0,
    ('M05', 'wp', 'SA', 'I1', 'modus_warmwasser:cockpit_jahr'): None,
    ('M05', 'wp', 'SA', 'I1', 'modus_warmwasser:fakten_tw'): 0.0,
    ('M05', 'wp', 'SA', 'I3', 'modus_heizen:cockpit_monat'): None,
    ('M05', 'wp', 'SA', 'I3', 'modus_heizen:fakten_tw'): 0.0,
    ('M05', 'wp', 'SA', 'I3', 'modus_warmwasser:cockpit_monat'): None,
    ('M05', 'wp', 'SA', 'I3', 'modus_warmwasser:fakten_tw'): 0.0,
    ('M06', 'wp', 'HA', 'I5', 'cockpit_monat:jaz:Klima'): 3.0,  # E4d: war None (Kanal-Leser, Bericht HA-BAUFORM-E4D)
    ('M06', 'wp', 'S1', 'I5', 'cockpit_monat:jaz:Klima'): 3.0,
    ('M06', 'wp', 'S2', 'I5', 'cockpit_monat:jaz:Klima'): 3.0,
    ('M06', 'wp', 'S3', 'I5', 'cockpit_monat:jaz:Klima'): 3.0,
    ('M06', 'wp', 'SA', 'I5', 'cockpit_monat:jaz:Klima'): 3.0,  # E-S4-3: war None (SA ohne Kanäle); Nachbau 2 ⇒ = HA/S1/S2/S3 (WP-Kanäle, N-750)
    # E4c (W2-E-KATALOG berichtigt): die Menge „verbrauch“ gibt es beim Erzeuger nicht mehr — ihr Haltewert entfällt.
    # HA-Bauform E4d: neue „Soll unklar"-Sichten (W1, M05: der Strom je Betriebsart kommt ohne Abschluss aus dem
    # abgeleiteten Kanal und ist > 0 — I6 „nichts verschwindet" misst ihn jetzt). Bericht HA-BAUFORM-E4D.
    ('M05', 'wp', 'HA', 'I6', 'modus_heizen:cockpit_jahr'): 19.5,
    ('M05', 'wp', 'HA', 'I6', 'modus_heizen:cockpit_monat'): 19.5,
    ('M05', 'wp', 'HA', 'I6', 'modus_heizen:fakten_tw'): 19.5,  # S4 E-S4-1: war 19.8 — Kalendermonat ohne die Stunde 30.06. 23:00 (Randstunde, Heizen 0,3 kWh)
    ('M05', 'wp', 'HA', 'I6', 'modus_warmwasser:cockpit_jahr'): 1.8,
    ('M05', 'wp', 'HA', 'I6', 'modus_warmwasser:cockpit_monat'): 1.8,
    ('M05', 'wp', 'HA', 'I6', 'modus_warmwasser:fakten_tw'): 1.8,
    ('M05', 'wp', 'S1', 'I6', 'modus_heizen:cockpit_jahr'): 198.0,
    ('M05', 'wp', 'S1', 'I6', 'modus_heizen:cockpit_monat'): 198.0,
    ('M05', 'wp', 'S1', 'I6', 'modus_heizen:fakten'): 198.0,
    ('M05', 'wp', 'S1', 'I6', 'modus_heizen:uebersicht'): 217.5,  # S4 E-S4-1: war 217.8 — Kalendermonat ohne die Stunde 30.06. 23:00 (Randstunde, Heizen 0,3 kWh)
    ('M05', 'wp', 'S1', 'I6', 'modus_heizen:zeitreihe'): 198.0,
    ('M05', 'wp', 'S1', 'I6', 'modus_warmwasser:cockpit_jahr'): 18.0,
    ('M05', 'wp', 'S1', 'I6', 'modus_warmwasser:cockpit_monat'): 18.0,
    ('M05', 'wp', 'S1', 'I6', 'modus_warmwasser:fakten'): 18.0,
    ('M05', 'wp', 'S1', 'I6', 'modus_warmwasser:uebersicht'): 19.8,
    ('M05', 'wp', 'S1', 'I6', 'modus_warmwasser:zeitreihe'): 18.0,
    ('M05', 'wp', 'S2', 'I6', 'modus_heizen:cockpit_jahr'): 198.0,
    ('M05', 'wp', 'S2', 'I6', 'modus_heizen:cockpit_monat'): 198.0,
    ('M05', 'wp', 'S2', 'I6', 'modus_heizen:fakten'): 198.0,
    ('M05', 'wp', 'S2', 'I6', 'modus_heizen:uebersicht'): 217.5,  # S4 E-S4-1: war 217.8 — Kalendermonat ohne die Stunde 30.06. 23:00 (Randstunde, Heizen 0,3 kWh)
    ('M05', 'wp', 'S2', 'I6', 'modus_heizen:zeitreihe'): 198.0,
    ('M05', 'wp', 'S2', 'I6', 'modus_warmwasser:cockpit_jahr'): 18.0,
    ('M05', 'wp', 'S2', 'I6', 'modus_warmwasser:cockpit_monat'): 18.0,
    ('M05', 'wp', 'S2', 'I6', 'modus_warmwasser:fakten'): 18.0,
    ('M05', 'wp', 'S2', 'I6', 'modus_warmwasser:uebersicht'): 19.8,
    ('M05', 'wp', 'S2', 'I6', 'modus_warmwasser:zeitreihe'): 18.0,
    # Sicht „Hub-Verlauf": die sechs Haltewerte `verbrauch_verlauf:Σreihe=kopf` (M07 Pool, M10 Sauna; 0,0 gegen Kopf
    # 72 / 24) sind mit N-645 entfallen — Fachentscheid Master 09.10.2026, Soll „Verlauf = Kopf" (Segment „nicht
    # aufgeteilt"); die Sichten sind seither bewertet und grün.
}
