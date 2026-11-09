"""CO₂-Äquivalente — eine vermiedene CO₂-Menge in anschaulichen Größen (ADR-001, DI-2).

Die eine Bildungsstelle für «Bäume», «Auto-km», «Kurzstreckenflüge» und «Flug-km». Bis Päckchen Y (9.11.2026)
gab es zwei Faktorensätze und keinen im Layer: *Auswertungen → CO₂* rechnete im Client (12,5 kg je Baum,
0,12 kg je km, 230 kg je Flug), die Route ``/cockpit/nachhaltigkeit`` mit eigenen Zahlen (÷ 20 für Bäume) — die
Route-Felder las keine Sicht. Jetzt liefert die Route die Äquivalente je Monat und gesamt aus dieser Funktion, der
Client summiert und zeigt nur (Wächter ``check:co2-roh``, Regel 2).

**Faktoren** (Entscheid Gernot 9.11.2026: die heute gezeigten Zahlen bleiben; Regel-Abschnitt
``docs/BERECHNUNGEN.md`` §3.8 «Äquivalente»):

- ``KG_CO2_JE_BAUM_JAHR = 12,5`` kg CO₂ Bindung je Baum und Jahr,
- ``KG_CO2_JE_AUTO_KM = 0,12`` kg CO₂ je Pkw-Kilometer (120 g/km),
- ``KM_JE_KURZSTRECKENFLUG = 1000`` km (die Unterzeile der Kachel «à 1000 km») und ``KG_CO2_JE_FLUG_KM = 0,23`` kg CO₂ je
  Flug-Kilometer ⇒ **230 kg je Kurzstreckenflug** — Flug und Flug-km hängen an denselben zwei Konstanten (Entscheid
  Master 9.11.2026: die sichtbare Unterzeile ist die Wahrheit; bis dahin rechnete die Route Flug-km mit 0,25 kg/km).

**Herkunft, gemessen:** Anschauungswerte der Auswertung seit Februar 2026 (``a3884af5c``: «Ein Baum bindet ca.
12.5 kg CO2/Jahr», «ca. 120g CO2/km»; die 230 kg je Flug kamen im selben Monat dazu); eine Literaturquelle nennt
weder der Code noch die Commit-Historie — die Faktoren sind eine **Annahme**. Es sind Größenordnungen zum Veranschaulichen, keine Bilanzgrößen — die
Bilanz selbst ist ``berechne_co2_bilanz``.

Alle vier Größen sind linear in der CO₂-Menge: die Summe der Monats-Äquivalente ist das Äquivalent der Summe.
Darauf baut der Client (er summiert die Monate des gewählten Jahres wie die kg).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

KG_CO2_JE_BAUM_JAHR = 12.5
KG_CO2_JE_AUTO_KM = 0.12
KG_CO2_JE_FLUG_KM = 0.23
KM_JE_KURZSTRECKENFLUG = 1000.0


@dataclass(frozen=True)
class Co2Faktoren:
    """Die Faktoren der Äquivalente — für Methodik-Texte, damit der Client keine Zahl selbst hinschreibt."""

    kg_co2_je_baum_jahr: float
    kg_co2_je_auto_km: float
    kg_co2_je_flug_km: float
    km_je_kurzstreckenflug: float
    #: ``kg_co2_je_flug_km × km_je_kurzstreckenflug`` — abgeleitet, nicht gepflegt.
    kg_co2_je_flug: float


CO2_FAKTOREN = Co2Faktoren(
    kg_co2_je_baum_jahr=KG_CO2_JE_BAUM_JAHR,
    kg_co2_je_auto_km=KG_CO2_JE_AUTO_KM,
    kg_co2_je_flug_km=KG_CO2_JE_FLUG_KM,
    km_je_kurzstreckenflug=KM_JE_KURZSTRECKENFLUG,
    kg_co2_je_flug=KG_CO2_JE_FLUG_KM * KM_JE_KURZSTRECKENFLUG,   # 0,23 × 1000 = 230,0 (in Gleitkomma exakt)
)


@dataclass(frozen=True)
class Co2Aequivalente:
    """Eine CO₂-Menge in vier Anschauungsgrößen, ungerundet (gerundet wird bei der Anzeige)."""

    baeume: float
    auto_km: float
    fluege: float
    fluege_km: float
    faktoren: Co2Faktoren


def co2_aequivalente(co2_kg: Optional[float]) -> Co2Aequivalente:
    """Äquivalente einer vermiedenen CO₂-Menge in kg.

    ``None`` und negative Mengen ergeben 0 — wie die Bilanz, deren Gesamtwert die geklemmten Anteile summiert
    (``berechne_co2_bilanz``); ein «negativer Baum» ist keine Aussage.
    """
    kg = co2_kg if co2_kg is not None and co2_kg > 0 else 0.0
    f = CO2_FAKTOREN
    return Co2Aequivalente(
        baeume=kg / f.kg_co2_je_baum_jahr,
        auto_km=kg / f.kg_co2_je_auto_km,
        fluege=kg / f.kg_co2_je_flug,
        fluege_km=kg / f.kg_co2_je_flug_km,
        faktoren=f,
    )
