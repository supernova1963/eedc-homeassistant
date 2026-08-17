"""Passt die gespeicherte PVGIS-Prognose noch zur Anlage? (#363)

**Der SoT für genau eine Frage.** Sowohl der automatische Neuabruf
(`services/scheduler.py::pvgis_aktualitaet_job`) als auch die Statusanzeige der
Einstellungs-Kachel lesen hier — zwei Sichten, eine Regel. Wer die Prüfung an
einer der beiden Stellen nachbaut, erzeugt genau die Drift, die dieses Projekt
schon zehnmal aus Aggregaten holen musste.

## Warum es die Prüfung überhaupt gibt

Eine PVGIS-Prognose ist die SOLL-Seite jeder Auswertung: Prognose-vs-IST, der
Monatsbericht, der Performance-Ratio-Wächter im Daten-Checker. Sie wird beim
Abruf eingefroren — ändert der Nutzer danach die Anlage, rechnet eedc weiter
gegen die alte Anlage. Im gemeldeten Extremfall (#363) stand für ein 2,4-kWp-
Balkonkraftwerk ein Jahres-SOLL von 357 MWh, weil die gespeicherte Prognose zu
einem weit größeren System gehörte.

## Was NICHT geprüft wird, und warum

**Das Alter der Prognose.** Am 2026-08-07 gegen die echte API gemessen: PVGIS
rechnet auf einem abgeschlossenen Klimamittel (v5_2 → PVGIS-SARAH2 2005-2020,
v5_3 → PVGIS-SARAH3 2005-2023). Bei unveränderten Eingaben liefert ein zweiter
Abruf dieselbe Zahl — ein turnusmäßiger Neuabruf wäre Last ohne Wirkung. Der
Datensatz wechselt bei PVGIS mit der API-Version, also durch einen Eingriff im
Code und nicht durch Zeitablauf; dafür steht `raddatabase`.

**Die Systemverluste.** Sie sind kein Anlagen-Stammdatum, sondern eine Eingabe
beim Abruf — es gibt keinen Ist-Wert, gegen den man sie halten könnte. Sie sind
deshalb der Wert, der beim Neuabruf ERHALTEN wird (`system_losses` unten), nicht
einer, der eine Abweichung begründet.

## Grenze, die bewusst offen bleibt

Ohne turnusmäßigen Abruf wird ein künftiger PVGIS-seitiger Datensatzwechsel erst
bemerkt, wenn ohnehin abgerufen wird. Das ist der Preis dafür, keine wirkungslose
Last zu erzeugen; `PVGIS_ERWARTETER_DATENSATZ` macht ihn beim Versionswechsel im
Code sichtbar, und `test_pvgis_aktualitaet.py` hält Version und Datensatz
zusammen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.investition_kennwerte import get_erzeuger_kwp
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.services.pv_orientation import get_pv_neigung
from backend.utils.investition_filter import aktiv_jetzt

logger = logging.getLogger(__name__)

# Welcher Strahlungsdatensatz zu welcher API-Version gehört. Beim Heben der
# Version in `core/config.py::pvgis_api_url` wird dieser Eintrag mitgepflegt —
# `test_pvgis_aktualitaet.py::test_erwarteter_datensatz_passt_zur_api_version`
# lässt die beiden nicht auseinanderlaufen. Werte am 2026-08-07 gegen die echte
# API gemessen (`inputs.meteo_data.radiation_db`).
DATENSATZ_JE_API_VERSION = {
    "v5_2": "PVGIS-SARAH2",
    "v5_3": "PVGIS-SARAH3",
}


def api_version() -> str:
    """Die konfigurierte PVGIS-API-Version (`v5_3`), aus der URL gelesen."""
    return settings.pvgis_api_url.rstrip("/").rsplit("/", 1)[-1]


def erwarteter_datensatz() -> Optional[str]:
    """Strahlungsdatensatz, den die konfigurierte API-Version liefert.

    ``None`` bei einer unbekannten Version — dann wird der Datensatz NICHT als
    Abweichungsgrund gewertet. Lieber keine Aussage als eine falsche: eine
    unbekannte Version würde sonst bei jedem Nutzer einen Neuabruf auslösen,
    ohne dass irgendjemand weiß, ob sich etwas geändert hat.
    """
    return DATENSATZ_JE_API_VERSION.get(api_version())


# Toleranzen. Die gespeicherten Werte sind gerundet (kWp auf 3, Winkel auf 1
# Nachkommastelle) — ohne Toleranz meldete jede Prognose sich selbst als
# abweichend und löste bei jedem Lauf einen Abruf aus.
TOLERANZ_KWP = 0.01
TOLERANZ_GRAD = 0.15
TOLERANZ_KOORDINATE = 0.0001


@dataclass
class PrognoseAbweichung:
    """Warum die gespeicherte Prognose nicht mehr zur Anlage passt.

    `gruende` ist für Menschen (Kachel-Hinweis, Log-Eintrag) und nie leer, wenn
    diese Klasse überhaupt entsteht. `system_losses` trägt die Verluste der
    bestehenden Prognose in den Neuabruf — ohne sie fiele der Nutzer
    stillschweigend auf den Default zurück (#363: „eingestellte Verluste
    bleiben erhalten").
    """

    prognose_id: int
    gruende: list[str] = field(default_factory=list)
    system_losses: float = 14.0

    @property
    def text(self) -> str:
        return " · ".join(self.gruende)


def _gewichtete_winkel(
    module: list[Investition], gesamt_kwp: float
) -> tuple[float, float]:
    """Neigung und Azimut nach kWp gewichtet — wie im Speicherpfad.

    Bewusst dieselbe Rechnung wie `api/routes/pvgis.py::speichere_pvgis_prognose`
    (dort über die Response-Objekte). Beide müssen übereinstimmen, sonst meldet
    eine frisch gespeicherte Prognose sich selbst als abweichend. Genau das
    prüft `test_frische_prognose_meldet_keine_abweichung`.
    """
    from backend.api.routes.pvgis import ausrichtung_zu_azimut, DEFAULT_TILT

    if gesamt_kwp <= 0:
        return 0.0, 0.0

    neigung = 0.0
    azimut = 0.0
    for modul in module:
        kwp = get_erzeuger_kwp(modul)
        if kwp <= 0:
            continue
        gewicht = kwp / gesamt_kwp
        params = modul.parameter or {}
        exakt = params.get("ausrichtung_grad")
        modul_azimut = exakt if exakt is not None else ausrichtung_zu_azimut(modul.ausrichtung)
        neigung += get_pv_neigung(modul, default=int(DEFAULT_TILT)) * gewicht
        azimut += modul_azimut * gewicht
    return round(neigung, 1), round(azimut, 1)


async def pruefe_prognose(
    db: AsyncSession, anlage_id: int
) -> Optional[PrognoseAbweichung]:
    """Prüft die AKTIVE Prognose einer Anlage gegen deren heutigen Zustand.

    Returns:
        ``None``, wenn die Prognose passt — oder wenn es gar keine gibt (dann
        ist nichts nachzuziehen; wer nie abgerufen hat, hat es vielleicht mit
        Absicht nicht getan, und die Kachel sagt das bereits selbst).
        Sonst eine `PrognoseAbweichung` mit den Gründen im Klartext.
    """
    from backend.api.routes.pvgis import PVGIS_ERZEUGER_TYPEN

    prognose: Optional[PVGISPrognose] = await lade_aktive_prognose(db, anlage_id)
    if prognose is None:
        return None

    anlage = (
        await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    ).scalar_one_or_none()
    if anlage is None:
        return None

    # N-266: `erzeuger_traeger` — ein Balkonkraftwerk mit Modul-Kindern hat kWp
    # UND Ausrichtung abgetreten. Bliebe es drin, meldete diese Prüfung nach dem
    # Anlegen der Kinder eine „Abweichung" gegen die Prognose, die es nie gab:
    # doppelte Nennleistung und eine zusätzliche Ausrichtung.
    module = erzeuger_traeger(
        (
            await db.execute(
                select(Investition)
                .where(Investition.anlage_id == anlage_id)
                .where(Investition.typ.in_(PVGIS_ERZEUGER_TYPEN))
                .where(aktiv_jetzt())
            )
        ).scalars().all()
    )

    gruende: list[str] = []

    # 1. Nennleistung — der gemeldete Fall (#363: 357 MWh für 2,4 kWp).
    ist_kwp = round(sum(get_erzeuger_kwp(m) for m in module), 3)
    war_kwp = prognose.gesamt_leistung_kwp
    # Ältere Prognosen (vor v2.3.2) tragen die Spalte nicht — dann sagt der
    # Vergleich nichts, und Schweigen ist richtiger als ein erfundener Grund.
    if war_kwp is not None and abs(ist_kwp - war_kwp) > TOLERANZ_KWP:
        gruende.append(f"Nennleistung {war_kwp:.2f} → {ist_kwp:.2f} kWp")

    # 2. Ausrichtung und Neigung — ein umgesetzter oder umgerichteter String
    #    ändert den Ertrag, ohne dass sich die kWp bewegen.
    if ist_kwp > 0:
        ist_neigung, ist_azimut = _gewichtete_winkel(module, ist_kwp)
        if abs(ist_neigung - prognose.neigung_grad) > TOLERANZ_GRAD:
            gruende.append(
                f"Neigung {prognose.neigung_grad:.0f}° → {ist_neigung:.0f}°"
            )
        if abs(ist_azimut - prognose.ausrichtung_grad) > TOLERANZ_GRAD:
            gruende.append(
                f"Ausrichtung {prognose.ausrichtung_grad:.0f}° → {ist_azimut:.0f}°"
            )

    # 3. Standort — eine korrigierte Koordinate verschiebt die Einstrahlung.
    if anlage.latitude is not None and anlage.longitude is not None:
        if (
            abs(anlage.latitude - prognose.latitude) > TOLERANZ_KOORDINATE
            or abs(anlage.longitude - prognose.longitude) > TOLERANZ_KOORDINATE
        ):
            gruende.append("Standort geändert")

    # 4. Horizontprofil — hochgeladen oder entfernt.
    hat_horizont = bool(anlage.horizont_daten)
    if hat_horizont != bool(prognose.horizont_verwendet):
        gruende.append(
            "Horizontprofil hinzugekommen" if hat_horizont else "Horizontprofil entfernt"
        )

    # 5. Strahlungsdatensatz — der einzige Grund, der NICHT an den Stammdaten
    #    hängt. NULL heißt „vor v4.0.11 geschrieben", also PVGIS-SARAH2.
    erwartet = erwarteter_datensatz()
    if erwartet is not None and prognose.raddatabase != erwartet:
        alt = prognose.raddatabase or "PVGIS-SARAH2"
        gruende.append(f"Strahlungsdatensatz {alt} → {erwartet}")

    if not gruende:
        return None

    return PrognoseAbweichung(
        prognose_id=prognose.id,
        gruende=gruende,
        system_losses=prognose.system_losses,
    )
