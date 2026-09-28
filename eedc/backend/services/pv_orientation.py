"""Zentrale Helper für PV-Ausrichtung (Azimut) und Neigung.

Hintergrund: Die Investition speichert PV-Parameter an zwei Stellen, die
historisch gewachsen sind:

1. Top-Level-Spalten auf der Investition-Tabelle:
   - `Investition.leistung_kwp` (Float)
   - `Investition.neigung_grad` (Float)
   - `Investition.ausrichtung` (String, z.B. "Süd")

2. Im `parameter`-JSON:
   - `kwp` (Float) — alternative Quelle für Leistung
   - `neigung_grad` / `neigung` — alternative Quelle für Neigung
   - `ausrichtung_grad` (int) — exakter Azimut aus dem PV-Modul-Formular
   - `ausrichtung` — redundanter String als Fallback

Die Prognose-Pfade (Tagesprognose, Aussichten-Kurzfristig, Prefetch) lasen
ursprünglich nur aus dem parameter-JSON und fielen dadurch stumm auf
Defaults (Neigung=35°, Azimut=0°) zurück, wenn die Werte nur in den
Top-Level-Spalten vorhanden waren.

Dieser Helper vereinheitlicht das Lesen über alle drei Pfade.

Die kWp-Helper selbst liegen seit A24-1 in `core/investition_kennwerte.py`
(`get_pv_kwp` · `get_bkw_kwp` · `get_erzeuger_kwp`) und werden hier
re-exportiert; Neigung und Azimut bleiben hier.
"""
import math
from dataclasses import dataclass
from typing import Any, Optional

# `get_pv_kwp` lebt seit A24-1 in `core/investition_kennwerte.py` (zusammen mit
# `get_bkw_kwp`/`get_erzeuger_kwp`), weil der Berechnungs-Layer die Helper
# braucht und `core/` laut ADR-001 nicht auf `services/` zeigen darf. Hier steht
# nur noch der Re-Export, damit die bestehenden Importeure unberührt bleiben —
# KEINE Kopie, es gibt genau eine Implementierung.
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.investition_kennwerte import (  # noqa: F401
    get_erzeuger_kwp,
    get_pv_kwp,
)

# Mapping für Ausrichtung-Strings → Azimut-Grad (EEDC/PVGIS-Konvention:
# 0=Süd, -90=Ost, 90=West, 180/-180=Nord).
AUSRICHTUNG_MAP = {
    "sued": 0, "süd": 0, "s": 0, "south": 0,
    "ost": -90, "o": -90, "e": -90, "east": -90,
    "west": 90, "w": 90,
    "nord": 180, "n": 180, "north": 180,
    "suedost": -45, "südost": -45, "so": -45, "se": -45,
    "suedwest": 45, "südwest": 45, "sw": 45,
    "nordost": -135, "no": -135, "ne": -135,
    "nordwest": 135, "nw": 135,
}


def get_pv_neigung(inv: Any, default: int = 35) -> int:
    """Neigung in Grad. Priorität: Top-Level → parameter.neigung_grad →
    parameter.neigung → Default."""
    direct = getattr(inv, "neigung_grad", None)
    if direct is not None:
        try:
            return int(direct)
        except (TypeError, ValueError):
            pass
    params = getattr(inv, "parameter", None) or {}
    for key in ("neigung_grad", "neigung"):
        val = params.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return default


def _gepflegter_azimut(inv: Any) -> Optional[int]:
    """Der GEPFLEGTE Azimut in Grad (0=Süd) — ``None``, wenn keiner lesbar ist.

    Der eine Leser hinter ``get_pv_azimut`` (der daraus mit seinem Default eine
    Zahl macht) und ``ausrichtung_label`` (der den Default gerade NICHT will).
    Priorität: parameter.ausrichtung_grad → Top-Level-String →
    parameter.ausrichtung (String oder Zahl). ⛔ ``ausrichtung_grad = 0`` ist ein
    gepflegtes Süd — geprüft wird ``is not None``, nie die Wahrheit des Werts.
    """
    params = getattr(inv, "parameter", None) or {}
    val = params.get("ausrichtung_grad")
    if val is not None:
        try:
            return int(val)
        except (TypeError, ValueError):
            pass
    direct_str = getattr(inv, "ausrichtung", None)
    if isinstance(direct_str, str) and direct_str:
        mapped = AUSRICHTUNG_MAP.get(direct_str.lower())
        if mapped is not None:
            return mapped
    param_val = params.get("ausrichtung")
    if isinstance(param_val, str) and param_val:
        mapped = AUSRICHTUNG_MAP.get(param_val.lower())
        if mapped is not None:
            return mapped
    elif isinstance(param_val, (int, float)):
        return int(param_val)
    return None


def get_pv_azimut(inv: Any, default: int = 0) -> int:
    """Azimut in Grad (0=Süd). Priorität: parameter.ausrichtung_grad →
    Top-Level-String → parameter.ausrichtung (String oder Zahl) → Default."""
    azimut = _gepflegter_azimut(inv)
    return default if azimut is None else azimut


def ausrichtung_text(inv: Any) -> Optional[str]:
    """Roh-Ausrichtung als Text: Top-Level-Spalte → ``parameter.ausrichtung`` → ``None``.

    N-528: das Balkonkraftwerk aus dem Einrichtungsassistenten trägt seine
    Ausrichtung **nur** im ``parameter``-JSON (``PARAM_BALKONKRAFTWERK["AUSRICHTUNG"]``);
    das Bearbeiten-Formular schreibt zusätzlich die Spalte. Wer nur die Spalte
    liest (so die PVGIS-Route bis 18.09.2026), rechnet ein Assistenten-BKW als
    Süd — dieselbe #229-Lage wie bei der kWp. Dieselbe Reihenfolge wie
    ``get_pv_azimut`` für den Text-Zweig.
    """
    direct = getattr(inv, "ausrichtung", None)
    if isinstance(direct, str) and direct.strip():
        return direct
    params = getattr(inv, "parameter", None) or {}
    val = params.get("ausrichtung")
    if isinstance(val, str) and val.strip():
        return val
    return None


#: PVGIS-Konvention: Ost = -90°, West = +90° — die zwei halben Anlagen einer
#: Ost-West-Komponente (gleiche Neigung, je kWp/2).
OST_WEST_AZIMUTE: tuple[int, int] = (-90, 90)


def ist_ost_west(ausrichtung: Optional[str]) -> bool:
    """Beschreibt der Ausrichtungstext eine Ost-West-Anlage?

    SoT für **beide** Prognosepfade: ``api/routes/pvgis._ist_ost_west``
    delegiert hierher (bis N-143 stand die Regel dort zweimal), und die
    Wetterprognose (N-527) fragt dieselbe Funktion. Die Formularoption heißt
    ``Ost-West`` („Ost-West (gemischt)"); Import und Altbestand kennen
    ``east-west``, ``OW``, ``O-W``.
    """
    if not ausrichtung:
        return False
    al = ausrichtung.lower().strip()
    return al in ("ost-west", "east-west", "ow", "o-w") or "ost-west" in al or "east-west" in al


#: Die acht Himmelsrichtungen ab Süd im Uhrzeigersinn der Azimut-Konvention
#: (0 = Süd, +45 = Südwest, +90 = West … −90 = Ost, −45 = Südost).
_HIMMELSRICHTUNGEN: tuple[str, ...] = (
    "Süd", "Südwest", "West", "Nordwest", "Nord", "Nordost", "Ost", "Südost",
)
#: Das EINE Label einer Ost-West-Komponente (#348). Sie ist eine Kachel mit
#: einer kWp — anders als im Prognosepfad, der sie in zwei halbe Abrufe teilt.
OST_WEST_LABEL = "Ost-West"


def ausrichtung_label(inv: Any) -> Optional[str]:
    """Die gepflegte Ausrichtung als Gruppen-Label (#348) — ``None`` ohne Pflege.

    Das Merkmal, nach dem der Live-Energiefluss PV-Kacheln gruppiert, wenn die
    Reihe nicht reicht. Gleiche Gruppe ⇔ gleiches Label.

    ⛔ **Kein Süd-Default** (anders als ``get_pv_azimut``): eine Anlage ohne
    jede Ausrichtungsangabe landete sonst geschlossen in einer Gruppe „Süd" und
    behauptete etwas, das niemand eingegeben hat — die Ausrichtungs-Stufe liefe
    nie leer, die Träger-Stufe wäre tot. ``None`` schickt die Kachel in die
    Restgruppe „Weitere".

    ⛔ **Präzedenz wie ``erzeuger_abrufe`` (N-527), NICHT wie ``get_pv_azimut``:**
    zuerst der Ost-West-Text — er gewinnt vor einem liegengebliebenen
    ``ausrichtung_grad`` (das Formular schreibt den Grad bei Ost-West nicht,
    s. ``erzeuger_abrufe``); ``get_pv_azimut`` läse den Alt-Grad zuerst und
    machte aus der Ost-West-Anlage „Süd". Danach der gepflegte Azimut
    (``_gepflegter_azimut``, ``0`` ist Süd), gerundet auf die nächste der acht
    Himmelsrichtungen. Ein Text, der weder Ost-West noch über
    ``AUSRICHTUNG_MAP`` lesbar ist („Süd-Ost", „SSW"), zählt als **nicht
    gepflegt** — nie als eigenes Roh-Text-Label, sonst entstünden zwei Gruppen
    für eine Richtung.

    ⛔ ``orientierungs_gruppen()`` ist bewusst NICHT die Quelle: sie spaltet eine
    Ost-West-Komponente in zwei halbe Anlagen (richtig für den Wetterabruf, eine
    Gruppe zu viel und eine halbierte kWp für eine Live-Kachel). Geteilt werden
    die Leser (``ausrichtung_text``, ``ist_ost_west``, ``_gepflegter_azimut``),
    nicht die Gruppierung.
    """
    if ist_ost_west(ausrichtung_text(inv)):
        return OST_WEST_LABEL
    azimut = _gepflegter_azimut(inv)
    if azimut is None:
        return None
    # Sektoren zu je 45° um die acht Richtungen; die Grenze (±22,5°) gehört
    # der im Uhrzeigersinn folgenden Richtung — deterministisch, ohne das
    # Banker's Rounding von ``round``.
    return _HIMMELSRICHTUNGEN[math.floor((azimut + 22.5) / 45) % 8]


def hat_ausrichtung(inv: Any) -> bool:
    """Ist für diesen Erzeuger eine Ausrichtung gepflegt? (#348, ohne Süd-Default)

    Dasselbe Urteil wie ``ausrichtung_label`` — ein zweites Prädikat mit
    eigener Lese-Logik wäre die Drift, gegen die dieses Modul gebaut ist.
    """
    return ausrichtung_label(inv) is not None


@dataclass(frozen=True)
class Abruf:
    """Ein Wetter-/PVGIS-Abruf: kWp auf einer (Neigung, Azimut)."""

    kwp: float
    neigung: int
    ausrichtung: int


def erzeuger_abrufe(inv: Any) -> list[Abruf]:
    """Die Abrufe EINES Erzeugers — Ost-West sind zwei halbe Anlagen (N-527).

    Bis 18.09.2026 fiel „Ost-West (gemischt)" im OpenMeteo-Pfad auf Süd (0°)
    zurück: ``AUSRICHTUNG_MAP`` kannte den Wert nicht, und ``get_pv_azimut``
    nahm den Default — während PVGIS dieselbe Komponente seit jeher als Ost
    (-90°) + West (+90°) rechnete (``api/routes/pvgis._kappungs_abrufe``). Live,
    14-Tage-Prognose, Prognose-Kanon, Prefetch und die HA-/MQTT-Prognosesensoren
    trugen damit die Süd-Mittagsspitze einer Anlage, die keine hat; der
    Lernfaktor glich nur die Höhe aus.

    Regeln, dieselben wie in PVGIS:
    * Ost-West gewinnt vor einem gespeicherten ``ausrichtung_grad`` — das
      Formular schreibt den Grad bei Ost-West nicht, ein älterer Wert kann
      liegen bleiben.
    * Neigung wie ``get_pv_neigung`` (Spalte → JSON → 35°), kWp über den
      Typ-Dispatcher ``get_erzeuger_kwp`` (ADR-002/P3-a); kWp ≤ 0 → keine Abrufe.
    * Der Aufrufer filtert die Menge (``erzeuger_traeger``, ``ist_aktiv_an``).
    """
    kwp = get_erzeuger_kwp(inv)
    if kwp <= 0:
        return []
    neigung = int(get_pv_neigung(inv))
    if ist_ost_west(ausrichtung_text(inv)):
        haelfte = kwp / 2
        return [
            Abruf(kwp=haelfte, neigung=neigung, ausrichtung=OST_WEST_AZIMUTE[0]),
            Abruf(kwp=haelfte, neigung=neigung, ausrichtung=OST_WEST_AZIMUTE[1]),
        ]
    return [Abruf(kwp=kwp, neigung=neigung, ausrichtung=int(get_pv_azimut(inv)))]


def erzeuger_string_configs(invs: Any) -> list:
    """``PVStringConfig`` je Abruf — EIN Bauer für ``prefetch_service`` und
    ``/solar-prognose`` (bis N-527 zwei Kopien derselben Schleife, beide ohne
    Ost-West). Die Hälften einer Ost-West-Komponente heißen „<Name> (Ost)" und
    „<Name> (West)". Lokaler Import: ``solar_forecast_service`` importiert
    dieses Modul, ein Modul-Import hier wäre ein Zyklus.
    """
    from backend.services.solar_forecast_service import PVStringConfig

    strings = []
    for pv in invs:
        abrufe = erzeuger_abrufe(pv)
        name = getattr(pv, "bezeichnung", None) or f"String {getattr(pv, 'id', '?')}"
        for a in abrufe:
            zusatz = ""
            if len(abrufe) > 1:
                zusatz = " (Ost)" if a.ausrichtung < 0 else " (West)"
            strings.append(PVStringConfig(
                name=name + zusatz, kwp=a.kwp, neigung=a.neigung, ausrichtung=a.ausrichtung,
            ))
    return strings


@dataclass(frozen=True)
class Orientierungsgruppe:
    """Eine nach (Neigung, Ausrichtung) zusammengefasste PV-String-Gruppe."""

    neigung: int       # Grad (0=horizontal, 90=vertikal)
    ausrichtung: int   # Azimut-Grad (0=Süd, -90=Ost, 90=West, 180=Nord)
    kwp: float         # Summe der kWp aller Module dieser Orientierung


def orientierungs_gruppen(invs: Any) -> list[Orientierungsgruppe]:
    """Gruppiert aktive PV-/BKW-Investitionen nach Orientierung (SoT).

    Der Multi-String-Fan-out (live_wetter, prognose_kanon) fragt OpenMeteo pro
    Orientierungsgruppe getrennt ab und kombiniert kWp-gewichtet — eine
    Ost/West-Anlage liefert sonst (über eine gemittelte Ausrichtung) einen
    systematisch falschen Tagesgang.

    Liest kWp/Neigung/Azimut konsistent über die ``get_*``-Helper (Top-Level-
    Spalte → ``parameter``-JSON → Default). Module mit kWp ≤ 0 entfallen.
    Reihenfolge: kWp-stärkste Gruppe zuerst (deterministisch, dominante Gruppe
    führt für Defaults wie Schätzpfad-Wetter).

    kWp über ``get_erzeuger_kwp`` (Typ-Dispatcher), nicht über ``get_pv_kwp``:
    Letzterer kennt den BKW-Zweig ``leistung_wp × anzahl`` nicht, und genau so
    legt das BKW-Formular an (Spalte und ``parameter["kwp"]`` bleiben leer).
    Ein Balkonkraftwerk lieferte hier deshalb 0 und fiel **ganz aus der
    Gruppierung** — im gesamten Kanon-Pfad (Tagesprognose, Stundenprofil,
    Live-Wetter, Prefetch, MQTT-/HA-Prognosesensoren). Bei gemischtem Bestand
    fehlte sein Anteil still; eine reine BKW-Anlage fiel auf die
    Anlagen-Gesamtleistung zurück. Dieselbe Umstellung ist in
    ``aussichten.py`` mit A24-2 gefahren worden und blieb hier liegen —
    dieselbe Klasse wie die zwei Abweichungen, die A20 in
    ``live_wetter._get_pv_orientierungsgruppen`` eingesammelt hat.

    **N-266 — hier wird der Melder-Wunsch überhaupt erst wirksam.** Die Menge
    läuft durch ``erzeuger_traeger``: ein Balkonkraftwerk mit
    `pv-module`-Kindern hat kWp **und** Ausrichtung abgetreten. Bliebe es drin,
    brächte es seine EINE Ausrichtung als eigene Gruppe mit — zusätzlich zu den
    Kindern, also doppelte kWp und genau die Einschränkung, die der Melder
    loswerden wollte. Diese eine Zeile trägt vier Aufrufer: den Fan-out und die
    Tagesgewichte des Prognose-Kanons, *Cockpit → Live* und die
    Energieprofil-Prognose. Der Aufrufer hat vorher zeitlich gefiltert
    (``ist_aktiv_an``/``ist_aktiv_im_zeitraum``); zu einem Zeitpunkt ohne die
    Kinder trägt das BKW seine Ausrichtung damit weiter selbst.
    """
    gruppen: dict[tuple[int, int], float] = {}
    for inv in erzeuger_traeger(invs or []):
        # N-527: eine Ost-West-Komponente liefert ZWEI Abrufe (je kWp/2 auf
        # -90° und +90°) und landet damit in zwei Gruppen — wie in PVGIS. Alle
        # anderen liefern genau einen Abruf mit denselben Werten wie zuvor
        # (kWp-Filter, Neigung, Azimut), die Rechnung bleibt für sie bitgleich.
        for abruf in erzeuger_abrufe(inv):
            key = (abruf.neigung, abruf.ausrichtung)
            gruppen[key] = gruppen.get(key, 0.0) + abruf.kwp
    return [
        Orientierungsgruppe(neigung=n, ausrichtung=a, kwp=kwp)
        for (n, a), kwp in sorted(gruppen.items(), key=lambda kv: kv[1], reverse=True)
    ]


# PVGIS-Standard-Systemverluste (Kabel, Wechselrichter, Verschmutzung).
# Fraktion, nicht Prozent — passt direkt in `ertrag * (1 - system_losses)`.
DEFAULT_SYSTEM_LOSSES = 0.14


def resolve_system_losses(pvgis: Any) -> float:
    """Systemverluste als Fraktion (0..1) aus dem aktiven PVGIS-Eintrag.

    `PVGISPrognose.system_losses` ist in Prozent gepflegt (Setup-Wert) und
    wird hier durch 100 geteilt. Fehlt der Eintrag oder ist der Wert leer/0,
    greift der PVGIS-Standard `DEFAULT_SYSTEM_LOSSES` (14 %).

    Hintergrund: diese Zeile stand als
    `pvgis.system_losses / 100 if pvgis and pvgis.system_losses else 0.14`
    an sechs Read-Sites parallel (prognose_service, prefetch_service,
    prognosen, aussichten, solar_prognose, energie_profil/prognose) plus die
    `0.14`-Konstante 5× definiert — bei Drift hätte ein Setup-Wert nur in
    manchen Sichten gewirkt (siehe `feedback_aggregations_drift`).
    """
    if pvgis is not None and pvgis.system_losses:
        return pvgis.system_losses / 100
    return DEFAULT_SYSTEM_LOSSES
