"""
Victron VRM Cloud-Import-Provider.

Holt historische Monats-Energiedaten aus dem Victron VRM Portal über die
VRM API v2 (https://vrm-api-docs.victronenergy.com/). Damit lassen sich
auch Daten aus der Zeit vor der HA-Anbindung nachholen — der Live-Pfad
(HA-Add-on + ha-victron-mqtt) bleibt davon unberührt (Issue #255).

Auth: Access-Token im Header `x-authorization: Token <token>`. Wird im
VRM-Portal unter Preferences → Integrations → Access tokens erzeugt; es
wird kein Passwort gespeichert. (`Bearer`-Tokens sind in der VRM-API zum
2026-06-01 deprecated — `Token` ist der richtige Weg.)

Discovery: idSite wird aus dem Token abgeleitet:
  GET /users/me                       → user.id (idUser)
  GET /users/{idUser}/installations   → Liste mit idSite/name/timezone/…
Das credential_field `installation_id` ist **optional** und nur nötig,
wenn der Account mehrere Anlagen verwaltet.

Datenquelle:
  GET /installations/{idSite}/stats?type=kwh&interval=months
- Doku-Limit: max. 24 Monate pro Aufruf für interval=months
  (`StatsCommand.yaml`); längere Zeiträume werden in 24-Monats-Fenstern
  geblockt — ein Call deckt für die meisten Anwender den Gesamtzeitraum.
- Response-Struktur: `records` ist
  `{attribut: [[ts, mean, min?, max?], …] | False}` — `False` markiert
  Attribute ohne Datenpunkt im Zeitraum, `mean` an Index 1.

Mapping: VRM `type=kwh` liefert die **Energiefluss-Matrix** in 2-Buchstaben-
Codes (Source × Target), siehe FELD_AUS_CODES. Verifiziert mit kingcap1s
Log-Auszug 2026-05-22 in #255 (`Gb`, `Pc`, `Pb`, `Bc`, `Pg`, `Bg`, `Gc`,
`kwh`). Pro eedc-Feld werden alle passenden Matrix-Zellen aufsummiert.

Wenn ein Block antwortet, aber KEIN bekannter Code im Mapping greift,
gibt der Provider eine WARNING mit der Liste der erhaltenen Keys aus —
damit das Mapping ohne Raten punktgenau erweitert werden kann.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from backend.services.import_parsers.base import ParsedMonthData

from .base import (
    CloudImportProvider,
    CloudProviderInfo,
    CloudConnectionTestResult,
    CredentialField,
)
from .registry import register_provider

logger = logging.getLogger(__name__)

API_BASE = "https://vrmapi.victronenergy.com/v2"

# VRM stats: max. 24 Monate pro Aufruf für interval=months (StatsCommand.yaml).
MAX_MONTHS_PER_CALL = 24

# VRM-Energiefluss-Matrix (records-Keys bei type=kwh).
#
# Jede Zelle ist die kWh-Summe, die im Zeitraum von SOURCE → TARGET geflossen
# ist. SOURCES: G=Grid, P=PV, B=Batterie. TARGETS: c=consumer, g=grid,
# b=battery. Sieben physikalisch sinnvolle Zellen (Gg und Bb fallen weg).
#
# Mapping auf eedc-Felder: pro Feld werden ALLE passenden Matrix-Zellen
# aufsummiert. Beispiel: pv_erzeugung_kwh = Pc + Pg + Pb (alles, was PV
# erzeugt hat — egal wohin geflossen).
FELD_AUS_CODES: dict[str, tuple[str, ...]] = {
    "pv_erzeugung_kwh":       ("Pc", "Pg", "Pb"),  # PV nach Verbraucher/Netz/Batterie
    "einspeisung_kwh":        ("Pg", "Bg"),         # alles, was ins Netz floss
    "netzbezug_kwh":          ("Gc", "Gb"),         # alles, was aus dem Netz kam
    "batterie_ladung_kwh":    ("Pb", "Gb"),         # Lade-Quellen
    "batterie_entladung_kwh": ("Bc", "Bg"),         # Entlade-Ziele
    "eigenverbrauch_kwh":     ("Pc", "Bc", "Gc"),   # alles, was Verbrauch erreichte
}

# Sammlung aller Matrix-Codes plus dokumentierte Begleit-Keys, die wir
# bewusst nicht auf ein Feld mappen (z. B. `kwh` als Aggregat-Marker —
# Wert nicht eindeutig, daher als bekannt-aber-ignoriert führen).
_MATRIX_CODES: frozenset[str] = frozenset(
    c for codes in FELD_AUS_CODES.values() for c in codes
)
BEKANNTE_CODES: frozenset[str] = _MATRIX_CODES | frozenset({"kwh"})


def _ts_to_year_month(ts: float) -> tuple[int, int]:
    """VRM-Record-Zeitstempel → (Jahr, Monat).

    Standard: Sekunden. Ältere Endpunkte gelegentlich Millisekunden — wird
    am Größenvergleich erkannt. Für interval=months markiert der Zeitstempel
    den Monatsanfang in der Anlagen-Zeitzone; ein 15-Tage-Puffer fängt die
    ±14 h-Streuung sauber im Zielmonat ab.
    """
    if ts > 1e12:  # Millisekunden
        ts = ts / 1000.0
    dt = datetime.fromtimestamp(ts + 15 * 86400, tz=timezone.utc)
    return dt.year, dt.month


def _records_to_monthly_data(
    records: dict,
) -> tuple[list[ParsedMonthData], list[str]]:
    """Wandelt das VRM-`records`-Objekt (type=kwh) in ParsedMonthData um.

    Liefert zusätzlich die Liste der erhaltenen Attribut-Keys, die NICHT
    in BEKANNTE_CODES vorkommen — damit der Aufrufer diagnostizieren kann,
    dass die API antwortet, aber das Mapping nicht trifft.

    Pure Funktion ohne Netzwerk — direkt testbar.
    """
    # monats[(jahr, monat)][matrix_code] = kWh
    monats: dict[tuple[int, int], dict[str, float]] = {}
    unbekannte_keys: list[str] = []

    for attr, serie in records.items():
        # VRM liefert `False`, wenn ein Attribut im Zeitraum keine Daten hat
        # — nicht als Fehler werten, einfach überspringen.
        if not isinstance(serie, list):
            continue
        if attr not in BEKANNTE_CODES:
            unbekannte_keys.append(attr)
            continue
        if attr not in _MATRIX_CODES:
            # bekannt, aber bewusst nicht gemappt (z. B. `kwh`-Aggregat).
            continue
        for punkt in serie:
            if not isinstance(punkt, (list, tuple)) or len(punkt) < 2:
                continue
            ts, mean = punkt[0], punkt[1]
            if ts is None or mean is None:
                continue
            jahr, monat = _ts_to_year_month(float(ts))
            # Jede (Monat, Matrix-Code)-Kombination ist ein eigener Messwert —
            # zuweisen, nicht summieren. Aggregation findet pro Feld statt.
            monats.setdefault((jahr, monat), {})[attr] = float(mean)

    results: list[ParsedMonthData] = []
    for (jahr, monat) in sorted(monats.keys()):
        code_werte = monats[(jahr, monat)]

        feld_werte: dict[str, Optional[float]] = {}
        for feld, codes in FELD_AUS_CODES.items():
            teile = [code_werte[c] for c in codes if c in code_werte]
            feld_werte[feld] = round(sum(teile), 2) if teile else None

        month_data = ParsedMonthData(
            jahr=jahr,
            monat=monat,
            pv_erzeugung_kwh=feld_werte["pv_erzeugung_kwh"],
            einspeisung_kwh=feld_werte["einspeisung_kwh"],
            netzbezug_kwh=feld_werte["netzbezug_kwh"],
            batterie_ladung_kwh=feld_werte["batterie_ladung_kwh"],
            batterie_entladung_kwh=feld_werte["batterie_entladung_kwh"],
            eigenverbrauch_kwh=feld_werte["eigenverbrauch_kwh"],
        )
        if month_data.has_data():
            results.append(month_data)

    return results, unbekannte_keys


def _advance_months(dt: datetime, monate: int) -> datetime:
    """`dt` um `monate` Monate nach vorne setzen (Monatsanfang bleibt)."""
    gesamt = (dt.month - 1) + monate
    return datetime(
        dt.year + gesamt // 12, gesamt % 12 + 1, 1, tzinfo=dt.tzinfo,
    )


@register_provider
class VictronVRMProvider(CloudImportProvider):
    """Cloud-Import-Provider für das Victron VRM Portal."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="victron_vrm",
            name="Victron VRM",
            hersteller="Victron Energy",
            beschreibung=(
                "Importiert historische Monats-Energiedaten (PV-Erzeugung, "
                "Einspeisung, Netzbezug, Batterie) aus dem Victron VRM Portal "
                "über die VRM API v2. Für das Nachholen von Daten aus der Zeit "
                "vor der HA-Anbindung."
            ),
            anleitung=(
                "1. Im VRM Portal einloggen (vrm.victronenergy.com)\n"
                "2. Preferences → Integrations → Access tokens → neuen Token "
                "erstellen und kopieren\n"
                "3. Die Installation wird automatisch erkannt. Nur wenn dein "
                "Account mehrere Anlagen verwaltet, bitte die Installation-ID "
                "(Zahl nach /installation/ in der Portal-URL) eintragen."
            ),
            credential_fields=[
                CredentialField(
                    id="access_token",
                    label="Access Token",
                    type="password",
                    placeholder="Ihr VRM Access Token",
                    required=True,
                ),
                CredentialField(
                    id="installation_id",
                    label="Installation-ID (optional)",
                    type="text",
                    placeholder="leer lassen für automatische Erkennung",
                    required=False,
                ),
            ],
            # Verifiziert 2026-05-23 (kingcap1, Issue #255):
            # Vollständiger Import von 48 Monaten gegen idSite=183075 grün,
            # Energiefluss-Matrix-Mapping (Pc/Pg/Pb/Gc/Gb/Bc/Bg → eedc-Felder)
            # mit echten Account-Daten bestätigt.
            getestet=True,
        )

    def _auth_headers(self, access_token: str) -> dict:
        # VRM-Doku schreibt `x-authorization` klein. HTTP-Header sind
        # case-insensitive, httpx normalisiert ohnehin.
        return {"x-authorization": f"Token {access_token}"}

    async def _get_user_id(
        self, client: httpx.AsyncClient, access_token: str,
    ) -> Optional[int]:
        """GET /users/me → user.id, oder None bei Fehler."""
        resp = await client.get(
            f"{API_BASE}/users/me", headers=self._auth_headers(access_token),
        )
        logger.info(
            "VRM /users/me: http=%s, body=%s",
            resp.status_code, resp.text[:300],
        )
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        if not data.get("success"):
            return None
        return (data.get("user") or {}).get("id")

    async def _list_installations(
        self, client: httpx.AsyncClient, access_token: str, id_user: int,
    ) -> list[dict]:
        """GET /users/{idUser}/installations → Liste."""
        resp = await client.get(
            f"{API_BASE}/users/{id_user}/installations",
            headers=self._auth_headers(access_token),
        )
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        if not data.get("success"):
            return []
        return list(data.get("records") or [])

    async def _resolve_site(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        installation_id: str,
    ) -> tuple[int, str, list[dict]]:
        """Liefert (idSite, Name, Anlagen-Liste).

        - `installation_id` gesetzt → muss in den Anlagen des Tokens sein
          (sonst ValueError mit Liste der verfügbaren IDs).
        - Leer + genau eine Anlage → Auto-Pick.
        - Leer + mehrere Anlagen → ValueError mit Liste der verfügbaren IDs.
        """
        id_user = await self._get_user_id(client, access_token)
        if id_user is None:
            raise ValueError(
                "Access Token wird vom VRM-Portal nicht akzeptiert "
                "(`/users/me` lieferte keine User-ID)."
            )

        anlagen = await self._list_installations(client, access_token, id_user)
        if not anlagen:
            raise ValueError("Keine Anlagen für diesen Access Token gefunden.")

        def _liste_fuer_fehler() -> str:
            return ", ".join(
                f"{a.get('idSite')} ({a.get('name') or '—'})" for a in anlagen
            )

        if installation_id:
            try:
                gewuenscht = int(installation_id)
            except ValueError:
                raise ValueError(
                    f"Installation-ID `{installation_id}` ist keine Zahl."
                )
            for a in anlagen:
                if a.get("idSite") == gewuenscht:
                    return (
                        gewuenscht,
                        a.get("name") or f"Installation {gewuenscht}",
                        anlagen,
                    )
            raise ValueError(
                f"Installation-ID {gewuenscht} ist mit diesem Token nicht "
                f"zugreifbar. Verfügbar: {_liste_fuer_fehler()}"
            )

        if len(anlagen) == 1:
            a = anlagen[0]
            id_site = a.get("idSite")
            return id_site, a.get("name") or f"Installation {id_site}", anlagen

        raise ValueError(
            f"Dieser Account hat {len(anlagen)} Anlagen — bitte Installation-ID "
            f"angeben. Verfügbar: {_liste_fuer_fehler()}"
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        access_token = (credentials.get("access_token") or "").strip()
        installation_id = (credentials.get("installation_id") or "").strip()

        if not access_token:
            return CloudConnectionTestResult(
                erfolg=False, fehler="Access Token ist erforderlich.",
            )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                id_site, name, anlagen = await self._resolve_site(
                    client, access_token, installation_id,
                )
                # Optional: system-overview für reichere UI-Info.
                geraete = 0
                try:
                    sov = await client.get(
                        f"{API_BASE}/installations/{id_site}/system-overview",
                        headers=self._auth_headers(access_token),
                    )
                    if sov.status_code == 200:
                        sov_data = sov.json()
                        if sov_data.get("success"):
                            geraete = len(
                                (sov_data.get("records") or {}).get("devices") or []
                            )
                except Exception:
                    # system-overview ist nur Bonus — Verbindung steht bereits.
                    pass

            verfuegbar = f"Installation {id_site}"
            if geraete:
                verfuegbar += f", {geraete} Gerät(e)"
            if len(anlagen) > 1:
                verfuegbar += f" (von {len(anlagen)} im Account)"

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name=name,
                geraet_typ="Victron VRM",
                seriennummer=str(id_site),
                verfuegbare_daten=verfuegbar,
            )

        except ValueError as e:
            return CloudConnectionTestResult(erfolg=False, fehler=str(e))
        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur VRM API.",
            )
        except Exception as e:
            logger.exception("VRM API Verbindungstest fehlgeschlagen")
            return CloudConnectionTestResult(
                erfolg=False, fehler=f"Verbindungsfehler: {str(e)}",
            )

    async def fetch_monthly_data(
        self,
        credentials: dict,
        start_year: int,
        start_month: int,
        end_year: int,
        end_month: int,
    ) -> list[ParsedMonthData]:
        """Holt historische Monatsdaten aus dem VRM Portal.

        Erst Discovery (Token → idSite), dann stats?type=kwh&interval=months
        in 24-Monats-Fenstern. Wenn alle Calls erfolgreich antworten, aber
        KEIN Attribut in der bekannten VRM-Matrix vorkommt, wird das mit
        einer WARNING samt erhaltener Key-Liste sichtbar gemacht.
        """
        access_token = (credentials.get("access_token") or "").strip()
        installation_id = (credentials.get("installation_id") or "").strip()
        if not access_token:
            return []

        gesamt_start = datetime(start_year, start_month, 1, tzinfo=timezone.utc)
        gesamt_end = _advance_months(
            datetime(end_year, end_month, 1, tzinfo=timezone.utc), 1
        )

        results: list[ParsedMonthData] = []
        gesehene_keys: set[str] = set()
        unbekannte_keys: set[str] = set()
        id_site: Optional[int] = None

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                id_site, _, _ = await self._resolve_site(
                    client, access_token, installation_id,
                )
            except ValueError as e:
                logger.warning(
                    f"VRM fetch_monthly_data: Discovery fehlgeschlagen: {e}"
                )
                return []

            block_start = gesamt_start
            while block_start < gesamt_end:
                block_end = min(
                    _advance_months(block_start, MAX_MONTHS_PER_CALL),
                    gesamt_end,
                )
                try:
                    block_results, keys_seen, keys_unknown = (
                        await self._fetch_stats_block(
                            client, access_token, id_site, block_start, block_end,
                        )
                    )
                    results.extend(block_results)
                    gesehene_keys.update(keys_seen)
                    unbekannte_keys.update(keys_unknown)
                except Exception as e:
                    logger.warning(
                        f"VRM Stats-Block {block_start:%Y-%m}–{block_end:%Y-%m} "
                        f"(idSite={id_site}) fehlgeschlagen: {e}"
                    )
                block_start = block_end

        # Lautes Scheitern, wenn die API antwortet, das Mapping aber leer
        # ausgeht: dann hat diese Anlage andere Attribut-Codes als die
        # bekannte VRM-Matrix.
        if not results and gesehene_keys:
            logger.warning(
                "VRM-Import idSite=%s lieferte 0 verwertbare Monatswerte. "
                "Erhaltene Attribut-Codes: %s. Davon nicht in der VRM-Matrix: %s. "
                "Bitte FELD_AUS_CODES in victron_vrm.py um die echten Codes "
                "erweitern (oder im Issue posten — der Log liegt damit vor).",
                id_site, sorted(gesehene_keys), sorted(unbekannte_keys),
            )

        return results

    async def _fetch_stats_block(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        id_site: int,
        block_start: datetime,
        block_end: datetime,
    ) -> tuple[list[ParsedMonthData], list[str], list[str]]:
        """Holt einen Stats-Block.

        Liefert (Monatswerte, alle Keys aus records, nicht-bekannte Keys).
        """
        params = {
            "type": "kwh",
            "interval": "months",
            "start": int(block_start.timestamp()),
            # Eine Sekunde vor Folgemonat → letzter Monat inklusive, ohne
            # den darauffolgenden anzuziehen.
            "end": int(block_end.timestamp()) - 1,
        }

        resp = await client.get(
            f"{API_BASE}/installations/{id_site}/stats",
            params=params,
            headers=self._auth_headers(access_token),
        )

        if resp.status_code == 401:
            raise Exception("HTTP 401: Access Token ungültig oder abgelaufen.")
        if resp.status_code == 403:
            raise Exception(
                f"HTTP 403: Kein Zugriff auf Installation {id_site}."
            )
        if resp.status_code == 429:
            raise Exception("HTTP 429: VRM-Rate-Limit erreicht (~3 req/s).")
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        if not data.get("success", False):
            err = data.get("errors") or data.get("error") or "Unbekannt"
            raise Exception(f"VRM-API-Fehler: {err}")

        records = data.get("records", {})
        if not isinstance(records, dict):
            return [], [], []

        # Diagnose: tatsächliche Attribut-Keys auf INFO loggen.
        alle_keys = list(records.keys())
        logger.info(
            "VRM stats records keys (idSite=%s, %s–%s): %s",
            id_site, block_start.date(), block_end.date(), alle_keys,
        )

        monthly, unbekannte = _records_to_monthly_data(records)
        return monthly, alle_keys, unbekannte
