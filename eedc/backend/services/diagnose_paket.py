"""
Diagnose-Paket — ein Text, aus dem wir Version, Lage und den wirksamen Schritt lesen (Etappe E1, Konzept Daten-Checker §8).

Markdown mit fester Abschnittsfolge (Konzept §8.2, 13 Abschnitte) und der Kopfmarke ``<!-- eedc-diagnose v3 -->`` (v2 seit E2:
Befund-Schlüssel und Handgriff-Klasse je Befund; v3 seit E5: Abschnitt 6 mit Kategorie-Köpfen, ohne Altfelder, mit den
nicht ausführbaren Prüfungen). Der Anwender
kopiert es in eine PN oder ein Issue (Einstellungen → Daten → Daten-Checker → Diagnose-Paket); eedc überträgt nichts.

**Nur lesend.** Kein Abgleich mit HA, kein Festschreiben, keine Protokollzeile: die Zuordnungen kommen aus
``datenquellen_felder.zuordnungen_lesen`` (ohne ``_festschreiben``, E0 §(7)), die Befunde aus ``DatenChecker.check_anlage``
(dieselben HA-Aufrufe wie die Checker-Route). Lesende HA-Aufrufe: ``/config`` im Kopf (Version, Zeitzone), ein ``/states``-Batch
für die Zuordnungen, die Prüfungen des Checkers — der Kopf nennt sie.

**Rechnet nichts** (Rechenstellen-Wächter): jede Zahl steht so im Paket, wie eedc sie gespeichert oder der Checker sie
gemeldet hat; Gleitkommazahlen werden nur für die Anzeige gerundet.

**Nie hinein** (Konzept §8.4, Wächter W-7 in ``tests/test_diagnose_paket.py``): Token, ``settings.ha_remote``, MQTT-Passwörter,
``connector_config`` (nur der Provider-Name), ``sensor_mapping.solcast_config`` (die Zuordnungen lesen nur die Feld-Quellen,
nie die Rohspalte), ``anlagen.versorger_daten``, ``community_hash``, E-Mail, Fotos, Stunden- und Spiegel-Stundenzeilen, die
Datenbank. Anlage und Komponenten laufen über Allowlists; Log-Zeilen werden von URLs und Token-Mustern bereinigt.

**Größe** (Entscheid Gernot 10.11.2026, Konzept §11 Nr. 4): die Datei ist ungekürzt; die Kopieren-Fassung ist hart
≤ ``GRENZE_KOPIE_BYTES``. Kürzungsfolge (E3.0 nach Lab rc29): Log → Tagesreihen 2 → 1 Monat → Spiegel-Abschnitte →
Checker-OK-Zeilen → Zuordnungen nur Felder mit Quelle → Komponenten ohne Parameter → Checker nur WARNING/ERROR → Tagesreihen
ganz weg; danach fallen ganze Abschnitte von hinten nach Priorität weg (13, 11, 5, 10, 3, 9, 4, 2 — nie 1, 6, 7, 8, 12), erst
zuletzt schneidet der Text am Ende. Jede Kürzung steht im Kopf. Gemessen E0 §(6): simon42 (Discourse 2026.7.3) erlaubt ``max_post_length`` = 150 000 Zeichen — die
Grenze bleibt trotzdem bei 20 KB (Lesbarkeit einer PN, nicht das Forum-Limit).
"""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.activity_log import ActivityLog
from backend.models.anlage import Anlage
from backend.models.investition import TYP_LABELS, Investition, InvestitionMonatsdaten
from backend.models.kanal import Kanal, KanalNachfuellung, KanalQuelle, KanalStatistik
from backend.models.monatsdaten import Monatsdaten
from backend.models.strompreis import Strompreis
from backend.models.tages_energie_profil import TagesZusammenfassung

KOPFMARKE = "<!-- eedc-diagnose v3 -->"
#: Harte Grenze der Kopieren-Fassung in Bytes (UTF-8). 20 000 statt 20 480: hält beide Lesarten von «20 KB».
GRENZE_KOPIE_BYTES = 20_000
#: Fenster der Kanal-Tage (Abschnitt 9) und Zahl der Monate der Tagesreihen (Abschnitt 11).
KANAL_FENSTER_TAGE = 90
TAGESREIHEN_MONATE = 2
PROTOKOLL_ZEILEN = 10
LOG_ZEILEN = 30

#: Die 13 Abschnitte (Konzept §8.2) — Nummer → Name.
ABSCHNITT_NAMEN = {
    1: "Kopf", 2: "Anlage", 3: "Komponenten", 4: "Zuordnungen", 5: "Strompreise", 6: "Daten-Checker", 7: "HA-Spiegel",
    8: "Nachtlauf und Reparaturen", 9: "Kanal-Tage", 10: "Monate", 11: "Tagesreihen", 12: "Zeitpläne",
    13: "Log (WARNING und höher)",
}
#: Harter Schnitt (E3.0, Lab rc29): ganze Abschnitte fallen von hinten nach Priorität weg — nie 1 Kopf, 6 Daten-Checker,
#: 7 HA-Spiegel, 8 Nachtlauf/Reparaturen, 12 Zeitpläne (die Diagnose-Abschnitte). Erst danach schneidet der Text am Ende.
WEGFALL_REIHENFOLGE = (13, 11, 5, 10, 3, 9, 4, 2)
NIE_WEG = frozenset({1, 6, 7, 8, 12})

#: Abschnitt 2 — die Spalten der Anlage, die ins Paket dürfen (Allowlist; alles andere bleibt draußen).
ANLAGE_SPALTEN = (
    "id", "anlagenname", "leistung_kwp", "installationsdatum", "standort_land", "standort_plz", "standort_ort",
    "wetter_provider", "wetter_modell", "prognose_quelle", "prognose_basis",
)
#: Abschnitt 3 — Parameter-Schlüssel, die nie ins Paket dürfen, obwohl sie in der Registry stehen: Verbindungsdaten
#: (``oberflaeche_url`` der Wallbox) und Freitext/Strukturen ohne Diagnosewert (``beschreibung``, ``innengeraete``).
PARAMETER_NIE = frozenset({"oberflaeche_url", "beschreibung", "innengeraete"})
#: Abschnitt 10 — Spalten der Monatszeile, die keine Messfelder sind (nicht in der Feldmaske).
MONAT_META = frozenset({
    "id", "anlage_id", "jahr", "monat", "datenquelle", "notizen", "source_provenance", "source_hash", "geprueft_gegen",
    "created_at", "updated_at", "sonderkosten_beschreibung", "sonstige_positionen",
})
#: Abschnitt 6 — Kategorien, deren Prüfung ohne HA-Verbindung gar nicht läuft (``return []`` am Anfang; gemessen am Code
#: E1: ``datenquelle/tage.py``, ``speicher.py``, ``quellen.py`` (Drift), ``zeitzone.py``, ``klima.py``, ``emob.py``,
#: ``sensoren.py`` (Langzeitstatistik)).
HA_GEBUNDEN = frozenset({
    "tageswerte_fehlen", "batterie_vorzeichen_historie", "datenquelle_drift", "zeitzone_abweichung", "klima_modus_wert",
    "emob_zustand_wert", "sensor_ohne_langzeitstatistik",
})
#: Aktivitätszeilen des Nachtlaufs und der Spiegel-Handgriffe (Abschnitt 8, Konzept §8.2 Nr 8).
PROTOKOLL_MUSTER = ("Kanalstatistik:%", "HA-Spiegel%", "Aus Home Assistant neu übernommen%")

_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_BEARER = re.compile(r"(?i)\bbearer\s+\S+")
_GEHEIM = re.compile(r"(?i)\b\w*(bearer|token|passw|secret|api_?key|apikey|authorization|kundennummer|hash)\w*(\s*[:=]\s*|\s+)\S+")


@dataclass
class Kuerzung:
    """Stufen der Kopieren-Fassung (Konzept §8.2): was weggelassen ist."""

    log: bool = True
    tage_monate: int = TAGESREIHEN_MONATE
    spiegel_abschnitte: bool = True
    ok_zeilen: bool = True
    # E3.0 (Lab rc29): weitere weiche Stufen vor dem harten Schnitt.
    zuordnungen_voll: bool = True
    komponenten_parameter: bool = True
    checker_info: bool = True
    #: Abschnitte, die der harte Schnitt ganz weglässt (Reihenfolge ``WEGFALL_REIHENFOLGE``).
    weggelassen: tuple[int, ...] = ()
    hart: bool = False

    def texte(self) -> list[str]:
        out = []
        if not self.log:
            out.append("Log weggelassen")
        if self.tage_monate == 0:
            out.append("Tagesreihen weggelassen")
        elif self.tage_monate < TAGESREIHEN_MONATE:
            out.append(f"Tagesreihen nur {self.tage_monate} Monat")
        if not self.spiegel_abschnitte:
            out.append("Spiegel-Abschnitte weggelassen")
        if not self.ok_zeilen:
            out.append("Checker-OK-Zeilen weggelassen")
        if not self.zuordnungen_voll:
            out.append("Zuordnungen nur Felder mit Quelle")
        if not self.komponenten_parameter:
            out.append("Komponenten ohne Parameter")
        if not self.checker_info:
            out.append("Checker nur WARNING/ERROR")
        out.extend(f"Abschnitt {nr} {ABSCHNITT_NAMEN[nr]} weggelassen" for nr in self.weggelassen)
        if self.hart:
            out.append(f"am Ende abgeschnitten bei {GRENZE_KOPIE_BYTES} Bytes")
        return out


@dataclass
class _Teile:
    """Die gelesenen Abschnitte vor dem Zusammensetzen (Zeilen je Abschnitt; Kürzung wählt aus)."""

    kopf: list[str] = field(default_factory=list)
    anlage: list[str] = field(default_factory=list)
    komponenten: list[str] = field(default_factory=list)
    zuordnungen: list[str] = field(default_factory=list)
    #: Kurzformen für die Kürzungsstufen (``None`` ⇒ wie die Vollform).
    komponenten_kurz: Optional[list[str]] = None
    zuordnungen_kurz: Optional[list[str]] = None
    strompreise: list[str] = field(default_factory=list)
    checker_kopf: list[str] = field(default_factory=list)
    #: je Befund (Kategorie, Schwere, Zeile) — Abschnitt 6 gruppiert nach Kategorie.
    checker: list[tuple[str, str, str]] = field(default_factory=list)
    checker_fuss: list[str] = field(default_factory=list)
    spiegel: list[tuple[str, list[str]]] = field(default_factory=list)
    protokoll: list[str] = field(default_factory=list)
    kanal_tage: list[str] = field(default_factory=list)
    monate: list[str] = field(default_factory=list)
    tagesreihen: list[tuple[str, list[str]]] = field(default_factory=list)
    zeitplaene: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


@dataclass
class DiagnosePaket:
    text: str
    dateiname: str
    kuerzungen: list[str]
    #: Bytes je Abschnitt (Nummer → Bytes) — für den Bericht und den Wächter W-9.
    bytes_je_abschnitt: dict[int, int]


# ─── kleine Helfer ───────────────────────────────────────────────────────────────────────────────────────────────

def _kurz(wert: Any) -> Any:
    """Gleitkommazahlen für die Anzeige auf drei Stellen runden (rekursiv) — keine Rechnung, nur Darstellung."""
    if isinstance(wert, float):
        return round(wert, 3)
    if isinstance(wert, dict):
        return {k: _kurz(v) for k, v in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [_kurz(v) for v in wert]
    return wert


def _json(wert: Any) -> str:
    return json.dumps(_kurz(wert), ensure_ascii=False, separators=(",", ":"), default=str)


def _zeile(text: Optional[str]) -> str:
    return " ".join(str(text or "").split())


def _ts(unix: Optional[int]) -> str:
    return datetime.fromtimestamp(unix).strftime("%Y-%m-%d %H:%M") if unix is not None else "—"


def bereinige_log(text: str) -> str:
    """Log-Zeile ohne URLs und ohne Token-/Passwort-Muster (W-7) — eine Remote-HA-URL kann Zugangsdaten tragen."""
    return _GEHEIM.sub("<geschwärzt>", _BEARER.sub("<geschwärzt>", _URL.sub("<url>", text)))


def _bereiche(tage: list[date]) -> list[str]:
    """Aufeinanderfolgende Tage zu «von … bis (n)» zusammenfassen."""
    out: list[str] = []
    start = vorher = None
    n = 0
    for t in sorted(tage):
        if vorher is not None and t == vorher + timedelta(days=1):
            vorher, n = t, n + 1
            continue
        if start is not None:
            out.append(f"{start.isoformat()} … {vorher.isoformat()} ({n})" if n > 1 else start.isoformat())
        start = vorher = t
        n = 1
    if start is not None:
        out.append(f"{start.isoformat()} … {vorher.isoformat()} ({n})" if n > 1 else start.isoformat())
    return out


# ─── Abschnitt 1: Kopf ───────────────────────────────────────────────────────────────────────────────────────────

async def ha_info(db: AsyncSession) -> dict:
    """Betriebsart und HA-Lage: Add-on (Supervisor), Remote-HA oder ohne HA; Version und Zeitzone aus ``/config`` (lesend).
    Nie die URL oder den Token zurückgeben."""
    from backend.core import config
    from backend.services.ha_connection import resolve_ha_connection

    api_url, token, kind = await resolve_ha_connection(db)
    info: dict = {"addon": bool(config.HA_INTEGRATION_AVAILABLE), "kind": kind, "erreichbar": False,
                  "version": None, "zeitzone": None}
    if not (api_url and token):
        return info
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{api_url}/config", headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 200:
            daten = resp.json() or {}
            info.update(erreichbar=True, version=daten.get("version"), zeitzone=daten.get("time_zone"))
    except Exception:  # noqa: BLE001 — nicht erreichbar ⇒ steht so im Kopf
        pass
    return info


def _kopf(app_version: str, info: dict, jetzt: datetime, fassung: str, monate_text: str) -> list[str]:
    if info["addon"]:
        betriebsart = "Add-on (Home Assistant)"
    elif info["kind"] == "ha_connector":
        betriebsart = "Standalone mit Home Assistant (Remote)"
    else:
        betriebsart = "Standalone"
    if not info["kind"]:
        ha = "HA: nicht verbunden"
    else:
        ha = f"HA: erreichbar {'ja' if info['erreichbar'] else 'nein'}"
        if info["version"]:
            ha += f" · HA-Version {info['version']}"
    lokal = jetzt.astimezone()
    return [
        f"- eedc-Version: {app_version}",
        f"- Betriebsart: {betriebsart}",
        f"- {ha}",
        f"- Zeitzone eedc: {lokal.tzname()} (UTC{lokal.strftime('%z')}) · HA: {info['zeitzone'] or '—'}",
        f"- Erzeugt am: {jetzt.strftime('%Y-%m-%d %H:%M')}",
        f"- Fassung: {'Kopieren (höchstens 20 KB)' if fassung == 'kopie' else 'Datei (ungekürzt)'}",
        f"- Tagesreihen: {monate_text}",
        "- Lesend erhoben: Version und Zeitzone (HA `/config`), Zuordnungen (ein HA-`/states`-Abruf), Prüfungen des "
        "Daten-Checkers — kein Abgleich, nichts gespeichert.",
    ]


# ─── Abschnitte 2, 3, 5: Anlage, Komponenten, Strompreise ────────────────────────────────────────────────────────

def _anlage(anlage: Anlage) -> list[str]:
    out = [f"- {s}: {getattr(anlage, s)}" for s in ANLAGE_SPALTEN]
    connector = (anlage.connector_config or {}).get("connector_id")
    out.append(f"- Geräte-Connector: {connector or '—'}")
    return out


def _parameter_erlaubt() -> frozenset[str]:
    """Allowlist = alle Schlüssel der Parameter-Registry (``core/investition_parameter.py``) ohne ``PARAMETER_NIE``."""
    from backend.core import investition_parameter as reg

    schluessel: set[str] = set()
    for name in dir(reg):
        wert = getattr(reg, name)
        if name.startswith("PARAM_") and not name.endswith("_DEFAULTS") and isinstance(wert, dict):
            schluessel.update(str(v) for v in wert.values())
    return frozenset(schluessel - PARAMETER_NIE)


def _kennwert(inv: Investition) -> str:
    from backend.core.investition_kennwerte import get_erzeuger_kwp, get_speicher_kapazitaet_kwh, get_wr_grenze_kw

    if inv.typ in ("pv-module", "balkonkraftwerk"):
        return f"{_kurz(get_erzeuger_kwp(inv))} kWp"
    if inv.typ == "speicher":
        return f"{_kurz(get_speicher_kapazitaet_kwh(inv))} kWh"
    if inv.typ == "wechselrichter":
        return f"{_kurz(get_wr_grenze_kw(inv))} kW"
    return ""


async def _komponenten(db: AsyncSession, anlage_id: int) -> tuple[list[str], list[str]]:
    """Abschnitt 3: Vollform (mit Parameter-Liste) und Kurzform (ohne, Kürzungsstufe E3.0)."""
    from backend.utils.investition_filter import sort_investitionen_nach_typ

    invs = sort_investitionen_nach_typ((await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all())
    erlaubt = _parameter_erlaubt()
    out: list[str] = []
    kurz: list[str] = []
    for inv in invs:
        params = {k: v for k, v in sorted((inv.parameter or {}).items())
                  if k in erlaubt and isinstance(v, (str, int, float, bool)) and v != ""}
        teile = [f"#{inv.id} {TYP_LABELS.get(inv.typ, inv.typ)} «{_zeile(inv.bezeichnung)}»",
                 f"aktiv {'ja' if inv.aktiv else 'nein'}",
                 f"{inv.anschaffungsdatum or '—'} … {inv.stilllegungsdatum or 'offen'}"]
        if inv.parent_investition_id is not None:
            teile.append(f"gehört zu #{inv.parent_investition_id}")
        if (kw := _kennwert(inv)):
            teile.append(kw)
        kurz.append("- " + " · ".join(teile))
        if params:
            teile.append("Parameter " + ", ".join(f"{k}={_kurz(v)}" for k, v in params.items()))
        out.append("- " + " · ".join(teile))
    return out or ["- keine"], kurz or ["- keine"]


async def _strompreise(db: AsyncSession, anlage_id: int) -> list[str]:
    zeilen = (await db.execute(select(Strompreis).where(Strompreis.anlage_id == anlage_id)
                               .order_by(Strompreis.verwendung, Strompreis.gueltig_ab))).scalars().all()
    out = []
    for p in zeilen:
        out.append(f"- #{p.id} {p.verwendung} · {p.vertragsart or '—'} · gültig {p.gueltig_ab} … {p.gueltig_bis or 'offen'}"
                   f" · Arbeitspreis {p.netzbezug_arbeitspreis_cent_kwh} ct/kWh · Einspeisung "
                   f"{p.einspeiseverguetung_cent_kwh} ct/kWh · Grundpreis {p.grundpreis_euro_monat} €/Monat")
    return out or ["- keine"]


# ─── Abschnitt 4: Zuordnungen ────────────────────────────────────────────────────────────────────────────────────

def _ziel(e: dict) -> str:
    """Entity bzw. Gateway-Topic; das Standard-Topic folgt aus Registry und Anlagenname (Kopfzeile des Abschnitts)."""
    if e.get("ha_entity") or e.get("gateway_topic"):
        return f" → {e.get('ha_entity') or e.get('gateway_topic')}"
    return ""


def _zuordnung_feld(f: dict, neu: set[str], kurz: bool = False) -> str:
    """Eine Feldzeile; ``kurz`` (Kürzungsstufe E3.0) ohne Label und Einheit — der Schlüssel nennt das Feld."""
    if kurz:
        zeile = f"- {f['id']}: {f.get('quelle')}{_ziel(f)}"
    else:
        zeile = f"- {f['id']} «{_zeile(f.get('label'))}» [{f.get('einheit') or '—'}]: {f.get('quelle')}{_ziel(f)}"
    if f["id"] in neu:
        zeile += " (aufgelöst, nicht gespeichert)"
    if f.get("bedarf") == "pflicht":
        zeile += " · Pflicht"
    arten = [p.get("art") for p in f.get("probleme") or [] if isinstance(p, dict)]
    if arten:
        zeile += " · Probleme: " + ", ".join(str(a) for a in arten)
    return zeile


async def _zuordnungen(db: AsyncSession, anlage_id: int) -> tuple[list[str], list[str]]:
    from backend.services.datenquellen_felder import zuordnungen_lesen

    ctx, gruppen = await zuordnungen_lesen(db, anlage_id)
    neu = set(ctx.neu_persistieren)
    return zuordnungen_zeilen(gruppen, neu), zuordnungen_zeilen(gruppen, neu, kurz=True)


def zuordnungen_zeilen(gruppen: list[dict], neu: set[str], kurz: bool = False) -> list[str]:
    """Abschnitt 4 aus den Gruppen von ``zuordnungen_lesen``. Vollform: Felder mit Quelle und Pflichtfelder; Kurzform
    (Kürzungsstufe E3.0): nur Felder mit Quelle, ohne Label und Einheit. Felder ohne Quelle stehen je Gruppe als eine
    Zählzeile."""
    from backend.services.datenquellen_felder import QUELLE_KEINE

    beispiel = next((f.get("standard_topic") for g in gruppen for f in g["felder"] if f.get("standard_topic")), None)
    out = [f"Standard-Topics (Quelle mqtt_inbound_standard) nach dem Muster {beispiel or '—'}"]
    for g in gruppen:
        felder = [f for f in g["felder"]
                  if f.get("quelle") != QUELLE_KEINE or (f.get("bedarf") == "pflicht" and not kurz)]
        ohne = len(g["felder"]) - len(felder)
        out.append(f"### {_zeile(g.get('titel'))} ({g.get('id')})")
        out.extend(_zuordnung_feld(f, neu, kurz) for f in felder)
        for thema in g.get("themen") or []:
            for e in thema.get("eintraege") or []:
                if e.get("quelle") != QUELLE_KEINE:
                    out.append(f"- Thema «{_zeile(thema.get('name'))}» {e.get('feld_id')}: {e.get('quelle')}{_ziel(e)}")
        if ohne:
            out.append(f"- ({ohne} weitere Felder ohne Quelle)")
    return out if len(out) > 1 else ["- keine Felder"]


# ─── Abschnitt 6: Daten-Checker ──────────────────────────────────────────────────────────────────────────────────

#: Laufzeit-Klasse, die der Katalog-Klasse entspricht, obwohl der Name anders ist (eine OK-Zeile trägt keinen Handgriff —
#: zur Laufzeit «auskunft»).
_KLASSE_GLEICH = {("ok", "auskunft")}


def _klasse(e) -> str:
    """`` · Klasse <Laufzeit> (Katalog <Soll>)`` nur, wenn die Laufzeit-Klasse vom Katalog abweicht — sonst steht sie im
    Katalog (``handgriffe.py``), und der Handgriff-Pfad steht im Code (E3.0: Abschnitt 6 kompakter)."""
    from backend.services.daten_checker.handgriffe import handgriff

    soll = handgriff(e.code)
    if soll is None or soll.klasse == e.klasse or (soll.klasse, e.klasse) in _KLASSE_GLEICH:
        return ""
    return f" · Klasse {e.klasse} (Katalog {soll.klasse})"


def _checker_zeilen(result, ha_verbunden: bool) -> tuple[list[str], list[tuple[str, str, str]], list[str]]:
    """Abschnitt 6: Kopf, je Befund ``(Kategorie, Schwere, Zeile)`` mit Zeile ``- [schwere] code — Meldung · werte``,
    Fuß (nicht ausgeführte Prüfungen)."""
    from backend.services.daten_checker import CheckKategorie

    z = result.zusammenfassung
    kopf = [f"- Zusammenfassung: error {z.get('error', 0)} · warning {z.get('warning', 0)} · info {z.get('info', 0)} · "
            f"ok {z.get('ok', 0)}"]
    if result.monatsdaten_abdeckung is not None:
        a = result.monatsdaten_abdeckung
        kopf.append(f"- Monatsdaten-Abdeckung: {a.vorhanden} von {a.erwartet} ({a.prozent} %)")
    zeilen = []
    for e in result.ergebnisse:
        schwere = getattr(e.schwere, "value", e.schwere)
        kategorie = getattr(e.kategorie, "value", e.kategorie)
        zeile = f"- [{schwere}] {e.code or '—'}"
        if e.investition_id is not None:
            zeile += f" · Gerät #{e.investition_id}"
        zeile += f" — {_zeile(e.meldung)}"
        if e.werte:
            zeile += f" · werte {_json(e.werte)}"
        zeilen.append((kategorie, schwere, zeile + _klasse(e)))
    gesehen = {getattr(e.kategorie, "value", e.kategorie) for e in result.ergebnisse}
    fuss = [f"Nicht ausführbar: {n['pruefung']} ({n['grund']})" for n in getattr(result, "nicht_ausfuehrbar", [])]
    fuss.append("Nicht ausgeführt oder ohne Befund:")
    for k in CheckKategorie:
        if k.value in gesehen:
            continue
        grund = "braucht Home Assistant (nicht verbunden)" if k.value in HA_GEBUNDEN and not ha_verbunden else "ohne Befund"
        fuss.append(f"- {k.value}: {grund}")
    return kopf, zeilen, fuss


# ─── Abschnitte 7, 8: HA-Spiegel, Nachtlauf und Reparaturen ──────────────────────────────────────────────────────

async def _spiegel(db: AsyncSession, anlage_id: int) -> list[tuple[str, list[str]]]:
    kanaele = (await db.execute(select(Kanal).where(Kanal.anlage_id == anlage_id).order_by(Kanal.key))).scalars().all()
    if not kanaele:
        return []
    ids = [k.id for k in kanaele]
    stat = {kid: (n, a, b) for kid, n, a, b in (await db.execute(
        select(KanalStatistik.kanal_id, func.count(), func.min(KanalStatistik.start_ts), func.max(KanalStatistik.start_ts))
        .where(KanalStatistik.kanal_id.in_(ids)).group_by(KanalStatistik.kanal_id))).all()}
    nachf = dict((await db.execute(
        select(KanalNachfuellung.kanal_id, func.max(KanalNachfuellung.abgeschlossen_ts))
        .where(KanalNachfuellung.kanal_id.in_(ids)).group_by(KanalNachfuellung.kanal_id))).all())
    quellen: dict[int, list[str]] = {}
    for q in (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id.in_(ids))
                               .order_by(KanalQuelle.kanal_id, KanalQuelle.gueltig_ab))).scalars().all():
        zeile = f"  - Abschnitt {q.familie} {q.statistic_id or '—'} gültig ab {_ts(q.gueltig_ab)}"
        if q.verworfen_ts is not None:
            zeile += f" · verworfen am {_ts(q.verworfen_ts)}"
        quellen.setdefault(q.kanal_id, []).append(zeile)
    out = []
    for k in kanaele:
        n, erste, letzte = stat.get(k.id, (0, None, None))
        out.append((f"- {k.key} ({k.einheit or '—'}, {k.art}): {n} Stunden, {_ts(erste)} … {_ts(letzte)}"
                    f" · letzte Nachfüllung {_ts(nachf.get(k.id))}", quellen.get(k.id, [])))
    return out


def _aktivitaet(z: ActivityLog) -> str:
    zeile = (f"- {z.timestamp.strftime('%Y-%m-%d %H:%M') if z.timestamp else '—'} · {z.kategorie} · "
             f"{'ok' if z.erfolg else 'Fehler'} · {_zeile(z.aktion)}")
    if z.details:
        zeile += f" — {_zeile(z.details)[:240]}"
    return zeile


async def _protokoll(db: AsyncSession, anlage_id: int) -> list[str]:
    eigene = or_(ActivityLog.anlage_id == anlage_id, ActivityLog.anlage_id.is_(None))
    nacht = (await db.execute(select(ActivityLog).where(eigene, or_(*(ActivityLog.aktion.like(m) for m in PROTOKOLL_MUSTER)))
                              .order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc()).limit(PROTOKOLL_ZEILEN))).scalars().all()
    repair = (await db.execute(select(ActivityLog).where(eigene, ActivityLog.kategorie == "repair")
                               .order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc()).limit(PROTOKOLL_ZEILEN))).scalars().all()
    out = ["Nachtlauf und HA-Spiegel (neueste zuerst):"]
    out += [_aktivitaet(z) for z in nacht] or ["- keine Zeile"]
    out.append("Reparaturen (neueste zuerst):")
    out += [_aktivitaet(z) for z in repair] or ["- keine Zeile"]
    return out


# ─── Abschnitte 9, 10, 11: Kanal-Tage, Monate, Tagesreihen ───────────────────────────────────────────────────────

async def _kanal_tage(db: AsyncSession, anlage_id: int, von: date, bis: date) -> set[date]:
    from backend.services.kanal.bilanz_leser import kanal_tage

    return set(await kanal_tage(db, anlage_id, von, bis))


async def _tage_lage(db: AsyncSession, anlage_id: int, heute: date) -> list[str]:
    bis = heute - timedelta(days=1)
    von = heute - timedelta(days=KANAL_FENSTER_TAGE)
    kanal = await _kanal_tage(db, anlage_id, von, bis)
    tz = set((await db.execute(select(TagesZusammenfassung.datum).where(
        TagesZusammenfassung.anlage_id == anlage_id, TagesZusammenfassung.datum >= von,
        TagesZusammenfassung.datum <= bis))).scalars().all())
    alle, t = [], von
    while t <= bis:
        alle.append(t)
        t += timedelta(days=1)
    kopf = f"Fenster {von.isoformat()} … {bis.isoformat()} ({KANAL_FENSTER_TAGE} Tage)"
    return [kopf,
            "- Kanal-Tage (aus dem HA-Spiegel): " + (", ".join(_bereiche(sorted(kanal))) or "keine"),
            "- Bestandstage (Tageszeile, kein Kanal): " + (", ".join(_bereiche([d for d in alle if d in tz and d not in kanal])) or "keine"),
            "- Tage ohne Zeile: " + (", ".join(_bereiche([d for d in alle if d not in tz and d not in kanal])) or "keine")]


async def _monate(db: AsyncSession, anlage_id: int) -> list[str]:
    zeilen = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
                               .order_by(Monatsdaten.jahr, Monatsdaten.monat))).scalars().all()
    geraete: dict[tuple[int, int], list[int]] = {}
    for j, m, iid in (await db.execute(select(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat,
                                              InvestitionMonatsdaten.investition_id)
                                       .join(Investition, Investition.id == InvestitionMonatsdaten.investition_id)
                                       .where(Investition.anlage_id == anlage_id))).all():
        geraete.setdefault((j, m), []).append(iid)
    spalten = [c.name for c in Monatsdaten.__table__.columns if c.name not in MONAT_META]
    masken: dict[str, str] = {}
    je_monat: dict[tuple[int, int], str] = {}
    for md in zeilen:
        maske = ", ".join(s for s in spalten if getattr(md, s) is not None)
        name = masken.setdefault(maske, f"M{len(masken) + 1}")
        je_monat[(md.jahr, md.monat)] = f"Quelle {md.datenquelle or '—'} · Feldmaske {name} · Abschluss ja"
    # Aufeinanderfolgende Monate mit derselben Beschreibung stehen als ein Bereich (Größe, Konzept §8.2 Nr 10).
    laeufe: list[list] = []
    for jm in sorted(set(je_monat) | set(geraete)):
        text = je_monat.get(jm, "keine Monatszeile · Abschluss nein")
        if jm in geraete:
            text += " · Gerätezeilen " + ", ".join(f"#{i}" for i in sorted(geraete[jm]))
        if laeufe and laeufe[-1][2] == text:
            laeufe[-1][1] = jm
        else:
            laeufe.append([jm, jm, text])
    out = [f"- Feldmaske {n}: {m or '(leer)'}" for m, n in masken.items()]
    for von, bis, text in laeufe:
        bereich = f"{von[0]}-{von[1]:02d}" + ("" if von == bis else f" … {bis[0]}-{bis[1]:02d}")
        out.append(f"- {bereich} · {text}")
    return out or ["- keine Monate"]


def monate_aus_befunden(ergebnisse) -> list[tuple[int, int]]:
    """Die betroffenen Monate (jüngste zuerst) aus Datumsangaben in ``werte`` und den Plan-Parametern der Aktion der Befunde ≠ OK."""
    gefunden: set[tuple[int, int]] = set()
    for e in ergebnisse:
        if getattr(e.schwere, "value", e.schwere) == "ok":
            continue
        for quelle in (e.werte or {}, e.action.params if e.action else {}):
            for schluessel in ("datum", "tag", "von", "bis", "bereich_von"):
                wert = quelle.get(schluessel)
                if isinstance(wert, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", wert):
                    gefunden.add((int(wert[:4]), int(wert[5:7])))
    return sorted(gefunden, reverse=True)


async def _tagesreihe(db: AsyncSession, anlage_id: int, jahr: int, monat: int) -> list[str]:
    von = date(jahr, monat, 1)
    bis = date(jahr, monat, calendar.monthrange(jahr, monat)[1])
    kanal = await _kanal_tage(db, anlage_id, von, bis)
    zeilen = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage_id, TagesZusammenfassung.datum >= von,
        TagesZusammenfassung.datum <= bis).order_by(TagesZusammenfassung.datum))).scalars().all()
    out = [f"- {z.datum} · {'Kanal' if z.datum in kanal else 'Bestand'} · {z.datenquelle or '—'} · Stunden "
           f"{z.stunden_verfuegbar} · Überschuss {_kurz(z.ueberschuss_kwh)} · Defizit {_kurz(z.defizit_kwh)} · "
           f"komponenten {_json(z.komponenten_kwh or {})}"
           + (f" · verworfen {_json(z.verworfen)}" if z.verworfen else "")
           + (f" · nachtrag {_json(z.nachtrag)}" if z.nachtrag else "")
           for z in zeilen]
    ohne_zeile = sorted(kanal - {z.datum for z in zeilen})
    if ohne_zeile:
        out.append("- Kanal-Tage ohne Tageszeile: " + ", ".join(_bereiche(ohne_zeile)))
    return out or ["- keine Tageszeilen"]


# ─── Abschnitte 12, 13: Zeitpläne, Log ───────────────────────────────────────────────────────────────────────────

def _zeitplaene() -> list[str]:
    from backend.services.scheduler import get_scheduler

    status = get_scheduler().get_status()
    if not status.get("running"):
        return [f"- Scheduler läuft nicht (verfügbar: {'ja' if status.get('available') else 'nein'})"]
    return [f"- {j.get('name')} ({j.get('id')}): nächster {j.get('next_run') or '—'} · letzter {j.get('last_run') or '—'}"
            f"{'' if j.get('last_ok') is None else (' ok' if j.get('last_ok') else ' Fehler')}"
            for j in status.get("jobs", [])] or ["- keine Jobs"]


def _log() -> list[str]:
    from backend.core.log_buffer import get_log_buffer

    eintraege = get_log_buffer().get_entries(level="WARNING", limit=LOG_ZEILEN)
    return [f"- {e['timestamp'][:19]} {e['level']} {e['logger_name']}: {bereinige_log(_zeile(e['message']))[:300]}"
            for e in eintraege] or ["- keine Zeile WARNING oder höher im Speicher"]


# ─── Zusammensetzen und Kürzen ──────────────────────────────────────────────────────────────────────────────────

_WEG = ["- weggelassen (Kürzung)"]


def _checker_abschnitt(t: _Teile, k: Kuerzung) -> list[str]:
    """Abschnitt 6: Kategorie als Gruppenkopf, darunter die Befunde; OK- bzw. INFO-Zeilen als Zählzeile, wenn gekürzt."""
    behalten = [(kat, sw, z) for kat, sw, z in t.checker
                if (k.ok_zeilen or sw != "ok") and (k.checker_info or sw != "info")]
    out = list(t.checker_kopf)
    for kat in dict.fromkeys(kat for kat, _, _ in behalten):
        out.append(f"### {kat}")
        out.extend(z for kat2, _, z in behalten if kat2 == kat)
    if not k.ok_zeilen:
        out.append(f"- ({sum(1 for _, sw, _ in t.checker if sw == 'ok')} OK-Zeilen weggelassen)")
    if not k.checker_info:
        out.append(f"- ({sum(1 for _, sw, _ in t.checker if sw == 'info')} INFO-Zeilen weggelassen)")
    return out + t.checker_fuss


def _abschnitte(t: _Teile, k: Kuerzung) -> list[tuple[int, str, list[str]]]:
    spiegel: list[str] = []
    for kopf, quellen in t.spiegel:
        spiegel.append(kopf)
        if k.spiegel_abschnitte:
            spiegel.extend(quellen)
    reihen: list[str] = []
    for monat, zeilen in t.tagesreihen[:k.tage_monate]:
        reihen += [f"#### {monat}", *zeilen]
    if not reihen:
        reihen = _WEG if t.tagesreihen else ["- keine betroffenen Monate"]
    kopf = t.kopf + [f"- Kürzungen: {', '.join(k.texte()) or 'keine'}"]
    inhalt = {
        1: kopf, 2: t.anlage,
        3: t.komponenten if k.komponenten_parameter or t.komponenten_kurz is None else t.komponenten_kurz,
        4: t.zuordnungen if k.zuordnungen_voll or t.zuordnungen_kurz is None else t.zuordnungen_kurz,
        5: t.strompreise, 6: _checker_abschnitt(t, k), 7: spiegel or ["- kein HA-Spiegel (keine Kanäle)"],
        8: t.protokoll, 9: t.kanal_tage, 10: t.monate, 11: reihen, 12: t.zeitplaene, 13: t.log if k.log else _WEG,
    }
    return [(nr, ABSCHNITT_NAMEN[nr], _WEG if nr in k.weggelassen else inhalt[nr]) for nr in ABSCHNITT_NAMEN]


def _text(titel: str, abschnitte: list[tuple[int, str, list[str]]]) -> tuple[str, dict[int, int]]:
    teile = [f"{KOPFMARKE}\n# {titel}\n"]
    groessen = {}
    for nr, name, zeilen in abschnitte:
        block = f"\n## {nr}. {name}\n" + "\n".join(zeilen) + "\n"
        groessen[nr] = len(block.encode("utf-8"))
        teile.append(block)
    return "".join(teile), groessen


#: Weiche Stufen der Kopieren-Fassung in dieser Reihenfolge (Konzept §8.2; E3.0 erweitert nach Lab rc29).
WEICHE_STUFEN = (
    dict(log=False), dict(tage_monate=1), dict(spiegel_abschnitte=False), dict(ok_zeilen=False),
    dict(zuordnungen_voll=False), dict(komponenten_parameter=False), dict(checker_info=False), dict(tage_monate=0),
)


def setze_zusammen(t: _Teile, titel: str, fassung: str) -> tuple[str, dict[int, int], list[str]]:
    """Datei: ungekürzt. Kopie: weiche Stufen bis ≤ ``GRENZE_KOPIE_BYTES``, danach ganze Abschnitte von hinten nach
    Priorität (``WEGFALL_REIHENFOLGE``, nie ``NIE_WEG``); erst als letzte Stufe ein harter Schnitt am Textende."""
    k = Kuerzung()
    text, groessen = _text(titel, _abschnitte(t, k))
    if fassung != "kopie":
        return text, groessen, k.texte()
    for stufe in WEICHE_STUFEN:
        if len(text.encode("utf-8")) <= GRENZE_KOPIE_BYTES:
            break
        k = replace(k, **stufe)
        text, groessen = _text(titel, _abschnitte(t, k))
    # Harter Schnitt: Abschnitt für Abschnitt; 13 (Log) und 11 (Tagesreihen) sind nach den weichen Stufen schon leer.
    schon_weg = {13} if not k.log else set()
    schon_weg |= {11} if k.tage_monate == 0 else set()
    for nr in (n for n in WEGFALL_REIHENFOLGE if n not in schon_weg):
        if len(text.encode("utf-8")) <= GRENZE_KOPIE_BYTES:
            break
        k = replace(k, weggelassen=(*k.weggelassen, nr))
        text, groessen = _text(titel, _abschnitte(t, k))
    if len(text.encode("utf-8")) > GRENZE_KOPIE_BYTES:
        k = replace(k, hart=True)
        text, groessen = _text(titel, _abschnitte(t, k))
        ende = "\n… (abgeschnitten)\n"
        roh = text.encode("utf-8")[:GRENZE_KOPIE_BYTES - len(ende.encode("utf-8"))]
        text = roh.decode("utf-8", errors="ignore") + ende
    return text, groessen, k.texte()


async def baue_paket(
    db: AsyncSession, anlage_id: int, *, fassung: str = "datei", monate: Optional[list[tuple[int, int]]] = None,
    jetzt: Optional[datetime] = None,
) -> DiagnosePaket:
    """Das Paket einer Anlage. ``LookupError`` bei unbekannter Anlage. ``monate``: Tagesreihen dieser Monate (höchstens
    ``TAGESREIHEN_MONATE``, die jüngsten), sonst aus den Befunden."""
    from backend.core.config import APP_VERSION
    from backend.services.daten_checker import DatenChecker

    jetzt = jetzt or datetime.now()
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one_or_none()
    if anlage is None:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")
    info = await ha_info(db)
    t = _Teile(anlage=_anlage(anlage))
    t.komponenten, t.komponenten_kurz = await _komponenten(db, anlage_id)
    t.zuordnungen, t.zuordnungen_kurz = await _zuordnungen(db, anlage_id)
    t.strompreise = await _strompreise(db, anlage_id)
    result = await DatenChecker(db).check_anlage(anlage_id)
    t.checker_kopf, t.checker, t.checker_fuss = _checker_zeilen(result, bool(info["kind"]))
    t.spiegel = await _spiegel(db, anlage_id)
    t.protokoll = await _protokoll(db, anlage_id)
    t.kanal_tage = await _tage_lage(db, anlage_id, jetzt.date())
    t.monate = await _monate(db, anlage_id)
    gewaehlt = sorted(set(monate), reverse=True) if monate else monate_aus_befunden(result.ergebnisse)
    gewaehlt = gewaehlt[:TAGESREIHEN_MONATE]
    t.tagesreihen = [(f"{j}-{m:02d}", await _tagesreihe(db, anlage_id, j, m)) for j, m in gewaehlt]
    herkunft = "angefragt" if monate else "aus den Befunden"
    monate_text = (", ".join(f"{j}-{m:02d}" for j, m in gewaehlt) + f" ({herkunft})") if gewaehlt else "keine betroffenen Monate"
    t.kopf = _kopf(APP_VERSION, info, jetzt, fassung, monate_text)
    t.zeitplaene = _zeitplaene()
    t.log = _log()
    titel = f"eedc-Diagnose-Paket — Anlage {anlage.id} «{_zeile(anlage.anlagenname)}»"
    text, groessen, kuerzungen = setze_zusammen(t, titel, fassung)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", anlage.anlagenname or "").strip("-")[:40] or str(anlage.id)
    return DiagnosePaket(text=text, dateiname=f"eedc_diagnose_{slug}_{jetzt.strftime('%Y-%m-%d')}.md",
                         kuerzungen=kuerzungen, bytes_je_abschnitt=groessen)
