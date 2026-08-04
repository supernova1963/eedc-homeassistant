"""AC-Kappung für die PVGIS-Monatsprognose (#354, #367).

**Das Problem.** Die PVGIS-Prognose (`PVcalc`) liefert **Monatssummen**. Eine
Monatssumme lässt sich nicht nachträglich stundenweise kappen — und genau das
müsste sie, denn ein Wechselrichter riegelt die Mittagsspitze ab, nicht den
Monat. Ohne Kappung ist das SOLL einer überbelegten Anlage systematisch
unerreichbar: 22 × 440 Wp an einem 7-kW-Gerät (#354, kingcap1) oder 4 × 500 Wp
an einem 800-W-Mikrowechselrichter (#367, azywietz-web). Der SOLL/IST-Vergleich
zeigt dann ein Minus, das der Anwender nicht zu verantworten hat.

**Der Weg.** PVGIS hat neben `PVcalc` den Endpunkt `seriescalc`, der für
dieselben Parameter ein **stündliches** Jahresprofil liefert. Daraus entsteht
je Monat ein Verhältnis „gekappt zu ungekappt" — der Kappungsfaktor. Auf die
`PVcalc`-Monatssumme angewandt bleibt PVGIS die einzige Ertragsquelle; hier
entsteht **kein** zweiter Ertragswert, nur ein Faktor ≤ 1. Ein selbst gebautes
Klarhimmel-Profil wäre die Alternative gewesen und hätte eine zweite Wahrheit
neben PVGIS gestellt (Entscheid Gernot 2026-08-04).

**Warum drei Jahre und nicht eines.** Gemessen am Demo-Standort (20 kWp DC an
10 kW AC), Faktor je Einzeljahr:

    2016: Jahr 0,898 | April 0,875
    2018: Jahr 0,882 | April 0,827
    2020: Jahr 0,877 | April 0,804

Der Jahresfaktor schwankt um gut 2 Prozentpunkte, der April um **7**. Ein
einzelnes Jahr trüge sein Wetter in eine Zahl, die eine Anlagen-Eigenschaft
beschreiben soll. Gemittelt wird ertragsgewichtet (Σ gekappt über alle Jahre ÷
Σ roh über alle Jahre), nicht als Mittel der Faktoren — sonst zählte ein
trüber April so schwer wie ein heller.

**Kosten.** Ein `seriescalc`-Abruf sind rund 0,8 MB und knapp eine Sekunde; drei
Jahre also ~2,5 MB je Modul. Deshalb passiert das hier **nur**, wenn für die
Anlage überhaupt eine AC-Grenze gepflegt ist — sonst wird der Endpunkt nie
angefasst und die Prognose bleibt bitgleich zu vorher.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from backend.core.berechnungen.wr_kappung import Mitglied, kappe_stunde

logger = logging.getLogger(__name__)

PVGIS_BASE_URL = "https://re.jrc.ec.europa.eu/api/v5_2"

# Letzte drei Jahre, die PVGIS v5.2 im `seriescalc` führt (der Datensatz endet
# 2020; ein späteres Startjahr quittiert die API mit HTTP 400 und dem Hinweis
# „enter an integer between 2005 and 2020"). Wer die API-Version hebt, prüft
# diese Grenze mit.
SERIESCALC_VON_JAHR = 2018
SERIESCALC_BIS_JAHR = 2020

# Ein Abruf über drei Jahre ist rund 2,5 MB — großzügiger als die 30 s der
# Monatsprognose, weil hier deutlich mehr Nutzlast über die Leitung geht.
SERIESCALC_TIMEOUT_S = 90.0


@dataclass
class KappungsModul:
    """Ein Erzeuger, für den ein Kappungsfaktor gebildet werden soll.

    Attributes:
        id: Kennung der Investition (Schlüssel des Ergebnisses).
        kwp: Nennleistung, auf die die PVGIS-Monatswerte gerechnet wurden.
        grenze_kw: AC-Grenze, oder `None` = unbegrenzt.
        grenz_id: geteilte Grenze (mehrere Strings an einem Wechselrichter),
            siehe `core/berechnungen/wr_kappung`.
        abrufe: (kWp, Neigung, Azimut) je PVGIS-Abruf. Mehr als einer bei
            Ost-West-Modulen, die PVGIS als zwei halbe Anlagen rechnet — ihre
            Stundenprofile werden addiert, denn beide Hälften hängen am selben
            Wechselrichter.
    """

    id: Any
    kwp: float
    grenze_kw: Optional[float]
    grenz_id: Optional[str]
    abrufe: list[tuple[float, float, float]] = field(default_factory=list)


async def _fetch_seriescalc(
    latitude: float,
    longitude: float,
    peak_power: float,
    tilt: float,
    azimuth: float,
    losses: float,
    user_horizon: Optional[list[float]] = None,
) -> list[tuple[int, float]]:
    """Stündliches PV-Profil von PVGIS als `[(monat, kW), …]`.

    Dieselben Parameter wie `PVcalc` (`api/routes/pvgis.py::fetch_pvgis_data`),
    damit Faktor und Monatssumme dieselbe Anlage beschreiben — eine Abweichung
    in `losses`, `pvtechchoice` oder Horizont machte den Faktor zur Aussage über
    eine andere Anlage.
    """
    params = {
        "lat": latitude,
        "lon": longitude,
        "peakpower": peak_power,
        "angle": tilt,
        "aspect": azimuth,
        "loss": losses,
        "outputformat": "json",
        "pvtechchoice": "crystSi",
        "mountingplace": "building",
        "usehorizon": 1,
        "pvcalculation": 1,
        "startyear": SERIESCALC_VON_JAHR,
        "endyear": SERIESCALC_BIS_JAHR,
    }
    if user_horizon:
        params["userhorizon"] = ",".join(f"{v:.1f}" for v in user_horizon)

    async with httpx.AsyncClient(timeout=SERIESCALC_TIMEOUT_S) as client:
        response = await client.get(f"{PVGIS_BASE_URL}/seriescalc", params=params)
        response.raise_for_status()
        daten = response.json()

    stunden = daten.get("outputs", {}).get("hourly", []) or []
    profil: list[tuple[int, float]] = []
    for eintrag in stunden:
        zeit = str(eintrag.get("time") or "")
        if len(zeit) < 6:
            continue
        try:
            monat = int(zeit[4:6])
            leistung_kw = float(eintrag.get("P") or 0.0) / 1000.0
        except (TypeError, ValueError):
            continue
        profil.append((monat, leistung_kw))
    return profil


async def _modul_profil(
    latitude: float,
    longitude: float,
    modul: KappungsModul,
    losses: float,
    user_horizon: Optional[list[float]],
) -> list[tuple[int, float]]:
    """Stundenprofil eines Moduls — bei Ost-West die Summe beider Hälften."""
    teile = await asyncio.gather(*[
        _fetch_seriescalc(
            latitude, longitude, kwp, tilt, azimuth, losses, user_horizon,
        )
        for kwp, tilt, azimuth in modul.abrufe
    ])
    teile = [t for t in teile if t]
    if not teile:
        return []
    if len(teile) == 1:
        return teile[0]

    laenge = min(len(t) for t in teile)
    return [
        (teile[0][h][0], sum(t[h][1] for t in teile))
        for h in range(laenge)
    ]


async def monats_kappungsfaktoren(
    latitude: float,
    longitude: float,
    module: list[KappungsModul],
    losses: float,
    user_horizon: Optional[list[float]] = None,
) -> dict[Any, list[float]]:
    """`{modul.id: [12 Faktoren]}` — Index 0 = Januar, 1.0 = nichts gekappt.

    Module ohne AC-Grenze werden **nicht** abgerufen und tauchen im Ergebnis
    nicht auf; der Aufrufer lässt ihre Monatssummen dann unverändert. Wer sich
    einen Wechselrichter teilt, trägt dessen Grenze bereits selbst — das löst
    `wr_kappung.zuordne_grenzen` auf, bevor die Module hier ankommen.

    Fällt der Abruf aus (Netz, Timeout, PVGIS-Fehler), gibt es **keine**
    Faktoren statt geratener: ein ungekapptes SOLL ist eine bekannte Größe, ein
    halb gekapptes wäre keine. Der Fehler steht im Log, die Prognose läuft
    weiter.
    """
    relevant = [m for m in module if m.grenze_kw and m.grenze_kw > 0 and m.abrufe]
    if not relevant:
        return {}

    try:
        profile = await asyncio.gather(*[
            _modul_profil(latitude, longitude, m, losses, user_horizon)
            for m in relevant
        ])
    except Exception as exc:  # noqa: BLE001 — bewusst breit, s. Docstring
        logger.warning(
            "PVGIS-seriescalc für die AC-Kappung fehlgeschlagen (%s) — "
            "das SOLL bleibt ungekappt", exc,
        )
        return {}

    verwendbar = [(m, p) for m, p in zip(relevant, profile) if p]
    if not verwendbar:
        return {}

    laenge = min(len(p) for _m, p in verwendbar)
    kwp_je_modul = [m.kwp for m, _p in verwendbar]
    mitglieder = [
        [Mitglied(kwp=m.kwp, grenze_kw=m.grenze_kw, grenz_id=m.grenz_id)]
        for m, _p in verwendbar
    ]

    roh = [[0.0] * 13 for _ in verwendbar]
    gekappt = [[0.0] * 13 for _ in verwendbar]

    for h in range(laenge):
        monat = verwendbar[0][1][h][0]
        werte = [p[h][1] for _m, p in verwendbar]
        nach = kappe_stunde(werte, kwp_je_modul, mitglieder)
        for i, wert in enumerate(werte):
            roh[i][monat] += wert
            gekappt[i][monat] += nach[i]

    ergebnis: dict[Any, list[float]] = {}
    for i, (modul, _p) in enumerate(verwendbar):
        ergebnis[modul.id] = [
            (gekappt[i][m] / roh[i][m]) if roh[i][m] > 0 else 1.0
            for m in range(1, 13)
        ]
    return ergebnis
