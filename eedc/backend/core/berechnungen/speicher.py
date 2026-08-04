"""Speicher-Aggregate — Effizienz aus InvestitionMonatsdaten.

Single Source of Truth für die Speicher-Round-Trip-Effizienz.

Round-Trip-Effizienz η = Entladung / Ladung ist nur über ein geschlossenes
Fenster sinnvoll: Ein Akku ist ein *Speicher* (Bestand), Monats-Ladung und
-Entladung sind *Flüsse*. Über eine einzelne Monatsgrenze trägt der SoC einen
Übertrag — ein Monat kann legitim mehr ent- als laden, weil gespeicherte
Energie aus dem Vormonat abfließt (Carry-over). Eine naive Pro-Monats-
Effizienz zappelt dadurch und kann 100 % überschreiten (Rainer-PN 2026-05-22).

Erst über ein langes Fenster mittelt sich ΔSoC aus und entladung/ladung wird
belastbar — vgl. `speicher_wirtschaftlichkeit.WIRKUNGSGRAD_FENSTER_MONATE_MIN`
(dort wird unterhalb von 6 Monaten SoC-korrigiert gerechnet). Dieser Layer
braucht keinen SoC: `gleitende_effizienz` summiert über ein 12-Monats-Fenster,
der einzige Restfehler ist ein ΔSoC über das ganze Fenster — durch die
Kapazität gedeckelt und damit vernachlässigbar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Fensterbreite, ab der entladung/ladung als belastbare Round-Trip-Effizienz
# gilt (darunter dominiert der SoC-Übertrag).
EFFIZIENZ_FENSTER_MONATE: int = 12


@dataclass
class MonatsEffizienz:
    """Gleitende Speicher-Effizienz für einen Kalendermonat."""

    jahr: int
    monat: int
    effizienz_prozent: Optional[float]
    fenster_monate: int  # Anzahl Monate, die ins gleitende Fenster eingingen


def speicher_effizienz_prozent(
    ladung_kwh: float, entladung_kwh: float
) -> Optional[float]:
    """Round-Trip-Effizienz in % über ein Fenster: entladung / ladung × 100.

    Nur belastbar über ein Fenster mit ΔSoC ≈ 0 (langes Fenster). Über eine
    einzelne Monatsgrenze ist der Wert durch den SoC-Übertrag verzerrt und
    kann 100 % überschreiten — dann KEINE Pro-Monats-Effizienz exponieren,
    sondern `gleitende_effizienz()` nutzen. Die Funktion klemmt bewusst NICHT
    (Diagnose statt stillem Cap).

    Gibt `None` zurück, wenn keine Ladung vorliegt.
    """
    if ladung_kwh <= 0:
        return None
    return entladung_kwh / ladung_kwh * 100.0


def vollzyklen(
    entladung_kwh: Optional[float], kapazitaet_kwh: Optional[float]
) -> Optional[float]:
    """Vollzyklen-Äquivalent: **entladene** Energie ÷ Kapazität.

    Der Kanon für alle Sichten (Komponenten-Hub, Cockpit Tag/Monat/Jahr,
    PDF-Jahresbericht, HA-Sensor `speicher_zyklen`). Entscheidung Gernot
    2026-07-28 nach der Erhebung zur Rainer-PN 89768.

    **Warum die Entladung und nicht die Ladung:** ein Vollzyklus meint die
    einmal *entnommene* Kapazität — das ist die Größe, auf die sich
    Hersteller-Garantien beziehen, und sie ist unabhängig von den
    Wandlungsverlusten des Ladepfads. Bis 2026-07-28 rechneten vier von fünf
    Stellen mit der **Ladung** und nur der HA-Sensor mit der Entladung; auf
    derselben Anlage standen dadurch zwei Zahlen unter demselben Namen, die
    genau um den Speicher-Wirkungsgrad auseinanderlagen (gemessen: 10,97 vs.
    8,57 bei η 78 %).

    **Warum die BRUTTO-Kapazität im Nenner:** `nutzbare_kapazitaet_kwh` ist
    optional und bei den meisten Anlagen nicht gepflegt — ein Nenner, der je
    nach Pflegezustand wechselt, wäre schlimmer als ein durchgehend etwas
    konservativer. Siehe `docs/BERECHNUNGEN.md` §3.3.

    **Abgrenzung:** Die ΔSoC-Größe aus dem Energieprofil-Aggregator
    (`TagesZusammenfassung.batterie_vollzyklen`) misst etwas anderes — reale
    SoC-Hübe, die eine 10/90-Fahrweise abbilden. Sie ist ein Bestandsmaß und
    damit nicht additiv über Tage; sie heißt deshalb „SoC-Hübe" und ist
    bewusst KEIN Ersatz für diesen Wert.

    Gibt `None` zurück, wenn keine Kapazität gepflegt ist oder keine Entladung
    vorliegt — bewusst kein 0-Ersatz, sonst sähe „nicht gepflegt" wie „nie
    zyklisiert" aus. Ungerundet; die Anzeige rundet.
    """
    if not kapazitaet_kwh or kapazitaet_kwh <= 0:
        return None
    if not entladung_kwh or entladung_kwh <= 0:
        return None
    return entladung_kwh / kapazitaet_kwh


def auslastungs_basis_kwh(
    kapazitaet_kwh: Optional[float], tage: int
) -> Optional[float]:
    """Theoretisch verfügbare Speichermenge eines Zeitraums: Kapazität × Tage.

    Der Nenner der Auslastung (#358 Phase 1) — bewusst als **eigene, additive
    Größe** und nicht als fertiger Prozentsatz: Auslastungen mehrerer Monate
    lassen sich nicht mitteln (ein Februar wiegt weniger als ein Juli), Summen
    dagegen schon. Wer ein Jahr bildet, summiert Entladung und Basis und teilt
    einmal — genau so, wie die Jahres-Sicht alle anderen Quoten bildet. Ein
    nachgebauter Prozent-Mittelwert wäre die Drift-Klasse, die diese Trennung
    verhindert.

    Kapazität = **brutto**, gleiche Wahl und gleiche Begründung wie bei
    `vollzyklen` (der Netto-Wert ist selten gepflegt; ein Nenner, der je nach
    Pflegezustand wechselt, wäre schlimmer als ein konservativer).

    Gibt `None` ohne gepflegte Kapazität — „unbekannt", nicht 0.
    """
    if not kapazitaet_kwh or kapazitaet_kwh <= 0:
        return None
    if tage <= 0:
        return None
    return kapazitaet_kwh * tage


def auslastung_prozent(
    entladung_kwh: Optional[float], basis_kwh: Optional[float]
) -> Optional[float]:
    """Auslastung in % der theoretisch verfügbaren Speichermenge.

    ``Entladung ÷ (Kapazität × Tage) × 100`` — die Antwort auf „wie viel von
    dem, was der Speicher an Durchsatz hergäbe, wird tatsächlich genutzt".
    Anders als die Vollzyklen ist sie zeitraum-normiert und deshalb zwischen
    Monaten und Jahren vergleichbar.

    **Kein Deckel bei 100 %:** ein Speicher, der an einem Tag mehr als eine
    Kapazität durchsetzt (zwei Zyklen), ist real — die Zahl darf über 100
    gehen und sagt dann genau das.

    Gibt `None`, wenn die Basis fehlt (keine Kapazität gepflegt) oder nichts
    entladen wurde.
    """
    if not basis_kwh or basis_kwh <= 0:
        return None
    if entladung_kwh is None or entladung_kwh <= 0:
        return None
    return entladung_kwh / basis_kwh * 100


def gleitende_effizienz(
    monats_reihe: list[tuple[int, int, float, float]],
    fenster: int = EFFIZIENZ_FENSTER_MONATE,
) -> list[MonatsEffizienz]:
    """Gleitende Round-Trip-Effizienz über `fenster` Monate.

    Args:
        monats_reihe: chronologisch sortierte Tupel
            ``(jahr, monat, ladung_kwh, entladung_kwh)``.
        fenster: Fensterbreite in Monaten (Default `EFFIZIENZ_FENSTER_MONATE`).

    Für jeden Monat: Σentladung / Σladung über die letzten `fenster` Monate
    (inklusive dem Monat selbst); bei kürzerer Historie kumulativ ab Start.
    So mittelt sich der SoC-Übertrag aus — die Reihe zappelt nicht über
    100 %, wie es eine naive Pro-Monats-Effizienz täte.
    """
    ergebnis: list[MonatsEffizienz] = []
    for i, (jahr, monat, _, _) in enumerate(monats_reihe):
        start = max(0, i - fenster + 1)
        fenster_rows = monats_reihe[start : i + 1]
        sum_ladung = sum(r[2] for r in fenster_rows)
        sum_entladung = sum(r[3] for r in fenster_rows)
        ergebnis.append(
            MonatsEffizienz(
                jahr=jahr,
                monat=monat,
                effizienz_prozent=speicher_effizienz_prozent(
                    sum_ladung, sum_entladung
                ),
                fenster_monate=len(fenster_rows),
            )
        )
    return ergebnis
