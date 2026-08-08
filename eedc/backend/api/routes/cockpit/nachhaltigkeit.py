"""
Cockpit Nachhaltigkeit — CO2-Bilanz Zeitreihe.

Die Zeitreihe faltet seit 2026-07-31 **nichts mehr selbst** (Befund **F-1** der
Drift-Inventur, ADR-002/**P10**). Vorher baute dieser Endpoint die komplette
Monatsaggregation nach — ohne einen einzigen Zeilen-SoT — und rechnete

    direktverbrauch = max(0, pv − einspeisung − speicher_ladung)
    eigenverbrauch  = direktverbrauch + speicher_entladung

selbst. Gegenüber dem Kanon fehlten dabei **V2H** (#304), die **Erzeugung hinter
dem Zähler** (BHKW/Mini-KWK, v3.45.4), die **Mehrfahrzeug-Attribution** des
E-Mob-Pools (#262), der **Dienstwagen-Filter** und die **PV-Auflösung** (P7) —
eine Anlage, die ihre Erzeugung nur als Anlagen-Aggregat pflegt, bekam hier gar
keine Zeitreihe, weil ohne Pro-Modul-Zeile kein Monat entstand.

Alles davon steckt jetzt in ``lade_monats_fakten``; CO₂ selbst kommt aus dem
kanonischen ``berechne_co2_bilanz`` (ADR-001, DI-2) statt aus drei lokalen
Formeln — damit nennt diese Sicht dieselben Zahlen wie Cockpit/Übersicht und
HA-Export.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.investition import Investition
from backend.core.calculations import berechne_co2_bilanz
from backend.services.eauto_wirtschaftlichkeit import (
    fossil_getankte_liter,
    km_gewichtete_eauto_params,
)
from backend.services.monats_fakten import MonatsFakt, lade_monats_fakten
from backend.api.routes.cockpit._shared import MONATSNAMEN

router = APIRouter()


class NachhaltigkeitMonat(BaseModel):
    """CO2-Bilanz für einen Monat."""
    jahr: int
    monat: int
    monat_name: str
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    co2_gesamt_kg: float
    co2_kumuliert_kg: float
    autarkie_prozent: float


class NachhaltigkeitResponse(BaseModel):
    """Nachhaltigkeits-Übersicht mit Zeitreihe."""
    anlage_id: int
    co2_gesamt_kg: float
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    aequivalent_baeume: int
    aequivalent_auto_km: int
    aequivalent_fluege_km: int
    monatswerte: list[NachhaltigkeitMonat]
    autarkie_durchschnitt_prozent: float


def _hat_substanz(fakt: MonatsFakt) -> bool:
    """Trägt der Monat überhaupt etwas zur CO₂-Bilanz oder zur Autarkie bei?

    Die Monats-Fakten liefern **jeden** Monat mit einer Spur — auch einen, für
    den es nur eine Zählerzeile gibt (Netzbezug vor der Anschaffung, ein Monat
    ohne jede Komponente). Ungefiltert wären das Null-Zeilen im Verlauf, und sie
    würden den Ø-Autarkiegrad nach unten ziehen. Geprüft wird deshalb genau das,
    woraus dieser Endpoint seine Werte bildet — nicht die Existenz einer Zeile.
    """
    return (
        fakt.erzeugung.hinter_zaehler_kwh > 0
        or fakt.speicher.entladung_kwh > 0
        or fakt.wp.waerme_kwh > 0
        or fakt.emob.km > 0
    )


@router.get("/nachhaltigkeit/{anlage_id}", response_model=NachhaltigkeitResponse)
async def get_nachhaltigkeit(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Nachhaltigkeits-Übersicht mit CO2-Zeitreihe."""
    # KEIN `aktiv`-Filter auf der Abfrage (Issue #123): die CO2-Zeitreihe ist
    # historisch, eine Stilllegung darf vergangene Einsparungen nicht rückwirkend
    # entfernen. Die Sichtbarkeit je Monat entscheidet `ist_aktiv_im_monat` — und
    # das tut die Schicht, an genau einer Stelle.
    fakten = await lade_monats_fakten(db, anlage_id)

    # Der Vergleichs-Verbrenner wird je Fahrzeug mit DESSEN gepflegtem
    # `vergleich_verbrauch_l_100km` gerechnet (km-gewichtet, G20-2). Bis
    # 2026-07-31 standen hier hartkodierte 7 l/100 km — der gepflegte Wert wurde
    # ignoriert, und der kanonische Default sind 7,5 l.
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    eauto_parameter = {
        i.id: i.parameter for i in inv_result.scalars().all() if i.typ == "e-auto"
    }

    monatswerte = []
    co2_kumuliert = 0.0
    co2_pv_total = 0.0
    co2_wp_total = 0.0
    co2_emob_total = 0.0
    autarkie_summe = 0.0
    autarkie_count = 0

    for fakt in fakten:
        if not _hat_substanz(fakt):
            continue

        vergleich_l_100km, _ = km_gewichtete_eauto_params(
            eauto_params_und_km=[
                (eauto_parameter.get(inv_id), km)
                for inv_id, km in fakt.emob.km_je_fahrzeug.items()
            ]
        )

        # DI-2: die EINE Konstruktions-Stelle der CO₂-Kennzahl. Der
        # Eigenverbrauch kommt aus den Monats-Fakten und trägt damit V2H, den
        # Erzeuger hinter dem Zähler und die P7-Auflösung; die Netzladung ist der
        # attribuierte Pool-Anteil (#262), nicht `ladung − pv`.
        bilanz = berechne_co2_bilanz(
            eigenverbrauch_kwh=fakt.kennzahlen.eigenverbrauch_kwh,
            wp_waerme_kwh=fakt.wp.waerme_kwh,
            wp_strom_kwh=fakt.wp.strom_kwh,
            emob_km=fakt.emob.km,
            emob_netz_ladung_kwh=fakt.emob.ladung_netz_kwh,
            benzin_verbrauch_liter=fakt.emob.km / 100 * vergleich_l_100km,
            # #331: der real getankte Anteil eines Plug-in-Hybrids mindert die
            # vermiedene Emission. Für ein BEV ist er 0.
            fossil_getankt_liter=fossil_getankte_liter(
                km_je_fahrzeug=fakt.emob.km_je_fahrzeug,
                fahrverbrauch_je_fahrzeug=fakt.emob.fahrverbrauch_je_fahrzeug,
                params_je_fahrzeug=eauto_parameter,
            ),
        )

        # Die Komponenten werden hier geklemmt ausgewiesen — anders als im
        # Cockpit, das sie roh zeigt. Grund: dieser Endpoint stellt sie als
        # Stapel gegen `co2_gesamt_kg`, und `co2_gesamt_kg` ist selbst die Summe
        # der geklemmten Anteile (`Co2Bilanz`). Ein roher Negativwert stünde
        # neben einer Summe, die ihn nicht enthält.
        co2_pv = bilanz.co2_pv_kg
        co2_wp = max(0.0, bilanz.co2_wp_kg)
        co2_emob = max(0.0, bilanz.co2_emob_kg)
        co2_monat = bilanz.co2_gesamt_kg
        co2_kumuliert += co2_monat

        autarkie = fakt.kennzahlen.autarkie_prozent
        autarkie_summe += autarkie
        autarkie_count += 1

        monatswerte.append(NachhaltigkeitMonat(
            jahr=fakt.jahr,
            monat=fakt.monat,
            monat_name=MONATSNAMEN[fakt.monat],
            co2_pv_kg=round(co2_pv, 1),
            co2_wp_kg=round(co2_wp, 1),
            co2_emob_kg=round(co2_emob, 1),
            co2_gesamt_kg=round(co2_monat, 1),
            co2_kumuliert_kg=round(co2_kumuliert, 1),
            autarkie_prozent=round(autarkie, 1),
        ))

        co2_pv_total += co2_pv
        co2_wp_total += co2_wp
        co2_emob_total += co2_emob

    co2_gesamt = co2_pv_total + co2_wp_total + co2_emob_total
    autarkie_avg = autarkie_summe / autarkie_count if autarkie_count > 0 else 0

    return NachhaltigkeitResponse(
        anlage_id=anlage_id,
        co2_gesamt_kg=round(co2_gesamt, 1),
        co2_pv_kg=round(co2_pv_total, 1),
        co2_wp_kg=round(co2_wp_total, 1),
        co2_emob_kg=round(co2_emob_total, 1),
        aequivalent_baeume=int(co2_gesamt / 20),
        aequivalent_auto_km=int(co2_gesamt / 0.12),
        aequivalent_fluege_km=int(co2_gesamt / 0.25),
        monatswerte=monatswerte,
        autarkie_durchschnitt_prozent=round(autarkie_avg, 1),
    )
