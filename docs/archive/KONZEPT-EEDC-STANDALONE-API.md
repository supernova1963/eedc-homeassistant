# Konzept (Stub): EEDC Standalone vollwertig — WebSocket-API statt Filesystem-Direktread

> Status: **Stub**, nicht ausgearbeitet. Trigger und Reife siehe §6.

## 1. Motivation

EEDC ist „Standalone-First" konzipiert (siehe CLAUDE.md), aber in der Praxis
hängt der **HA-Statistics-Import** an einem Filesystem-Direktread:

```python
# eedc/backend/services/ha_statistics_service.py:31
HA_DB_PATH = Path("/config/home-assistant_v2.db")
```

Der funktioniert nur im HA-Add-on-Modus, weil dort `/config` aus dem
HA-Container gemountet ist. Standalone-Anwender (Docker auf separatem
Host) müssen heute auf den `HA_RECORDER_DB_URL`-Pfad ausweichen — also HA
auf MariaDB/MySQL umstellen — oder ganz auf HA-Statistics verzichten.

Für die Mehrheit der HA-Nutzer (SQLite-Default-Recorder) ist das eine
echte Hürde, weil HA-DB-Migration nicht trivial ist.

### Auslöser

- **Wiederkehrende Frage in Forum/PN** zur Standalone-Variante mit
  HA-Anbindung. Aktuelle PN-Antrieb 2026-04-30 (Gernot-Notiz: „die Frage
  gab es bereits").
- **iFrame-Card-Idee:** im HA-Add-on-Kontext nicht stabil umsetzbar
  (rotierender Ingress-Token); Standalone-mit-LLT wäre der saubere Weg
  für Anwender, die EEDC-Sub-Seiten in Lovelace einbetten wollen.
- **Strategisch:** API-First-Architektur statt internem DB-Schema. HA
  kann Recorder-Schema jederzeit migrieren — ein API-Pfad ist robuster.

### Abgrenzung

- **Kein Wechsel weg vom HA-Add-on-Modus.** Add-on bleibt der
  empfohlene, einfachste Setup-Weg für die Mehrheit der Anwender.
- **Kein WebSocket-Auth-System für andere Tools.** Nur EEDC selbst nutzt
  die HA-API für eigene Zwecke; kein Token-Provisioning für Dritte.
- **Keine eigene Auth-Schicht in EEDC** als Teil dieses Konzepts. Falls
  Standalone hinter Reverse Proxy mit eigener Auth läuft, ist das
  Anwender-Verantwortung. Eigene Auth-Schicht ist eigene Konzept-Story.

---

## 2. Bestandsaufnahme

### Was hängt heute am Supervisor-Token?

| Komponente | Datei | Was tut sie |
|---|---|---|
| `ha_state_service` | `services/ha_state_service.py` | Aktuelle States (`/api/states`), History (`/api/history/period`) — funktional identisch über LLT erreichbar |
| `solcast_service` (HA-Sensor-Pfad) | `services/solcast_service.py` | Liest Solcast-HA-Sensor-Werte — funktional identisch über LLT |
| `system_logs` | `routes/system_logs.py` | Liest **Supervisor-Logs** über `/supervisor/...` — wirklich Supervisor-spezifisch, im Standalone nicht abbildbar |
| `sensor_mapping` (Sensor-Discovery) | `routes/sensor_mapping.py` | `/api/states` für Sensor-Listen — LLT genügt |
| `ha_integration` | `routes/ha_integration.py` | Generischer HA-API-Wrapper — LLT genügt |
| **`ha_statistics_service`** | `services/ha_statistics_service.py` | **Direkt-Read von `/config/home-assistant_v2.db`** — Filesystem-Zwang |

Der Add-on-Zwang sitzt also an genau zwei Stellen:

1. **HA-Statistics** (Filesystem-Direktread) — die kritische Schwelle
2. **Supervisor-Logs** (Supervisor-API-Endpoint) — entbehrlich, im
   Standalone einfach weglassen oder durch generische Log-Anzeige
   ersetzen

### Was Standalone heute schon kann

- `HA_RECORDER_DB_URL` (Env-Var, `core/config.py:71`) für externe
  MariaDB/MySQL-Connection. Funktioniert, aber setzt HA-Recorder-DB-
  Migration voraus.
- API-Pfade (`/api/states` etc.) wären schon LLT-fähig, **wenn**
  `ha_api_url` flexibel wäre — heute fest auf `http://supervisor/core/api`.

---

## 3. Vorschlag

### Saubere Lösung: WebSocket `recorder/get_statistics`

HA bietet die Statistics-Tabelle über die WebSocket-API auch von außen an:

```
{"type": "recorder/get_statistics_during_period",
 "start_time": "2026-04-01T00:00:00Z",
 "end_time": "2026-04-30T23:59:59Z",
 "statistic_ids": ["sensor.pv_erzeugung_kwh"],
 "period": "hour"}
```

Authentifiziert via Bearer Token im WebSocket-Auth-Flow — LLT geht hier
genauso wie Supervisor-Token.

`ha_statistics_service` würde umgebaut:
- DB-Direktread bleibt als Add-on-Schnellpfad (Performance)
- WebSocket-Pfad neu für Standalone-Modus
- Selektion über `HA_INTEGRATION_AVAILABLE` + Konfigurations-Flag

### Standalone-Konfiguration

Drei neue Env-Vars (alle optional):

```
HA_URL=http://homeassistant.local:8123       # Default heute hardcoded supervisor
HA_TOKEN=<long-lived-token>                  # Default heute SUPERVISOR_TOKEN
HA_INTEGRATION_MODE=auto|addon|standalone    # auto = aus SUPERVISOR_TOKEN-Präsenz
```

`HA_INTEGRATION_AVAILABLE` würde von einer reinen Token-Prüfung auf
`(addon-mode AND SUPERVISOR_TOKEN) OR (standalone-mode AND HA_URL AND HA_TOKEN)`
erweitert.

---

## 4. Offene Architektur-Fragen

- **Hybrid-Pfad oder einheitlich?**
  - Hybrid: Add-on schnell (DB), Standalone API (WebSocket). Pro: keine
    Performance-Regression im Add-on. Contra: zwei Code-Pfade dauerhaft.
  - Einheitlich: alle nutzen WebSocket. Pro: ein Code-Pfad, weniger
    DB-Schema-Risiko. Contra: ein 12-Monate-Backfill von Sekunden auf
    Minuten gestreckt.
- **WebSocket-Persistierung.** Eine offene Connection pro Anlage oder
  pro Request neu auf? Ressourcen vs. Latenz.
- **Pagination.** `recorder/get_statistics` limitiert auf ~1000
  Datenpunkte/Request. Für Multi-Sensor-Mehrjahres-Backfills nötig.
- **System-Logs-Funktion** im Standalone: weglassen oder generische
  EEDC-Logs-Anzeige?
- **MQTT-Inbound-Anlagen** sind heute schon Standalone-fähig (kein
  HA-Zugriff). Standalone-mit-HA-API ist eine **dritte Variante** —
  Anwender-Setup-Doku braucht klare Entscheidungshilfe.

---

## 5. Folgen, die mitgedacht werden müssen

1. **Anwender-Setup-Komplexität wächst.** LLT erzeugen, HA-URL/Port
   konfigurieren, ggf. CORS klären, ggf. Reverse-Proxy für HTTPS.
   Power-User-Territorium.
2. **HA-Erreichbarkeit als Laufzeit-Annahme.** Im Add-on synchronisieren
   sich HA und EEDC beim Restart; Standalone muss WebSocket-Drops und
   Auth-Refresh sauber handhaben.
3. **Performance-Regression im Add-on**, falls einheitlich umgestellt.
   12-Monats-Backfill von Sekunden auf Minuten.
4. **Doku-Aufwand.** Eine vollständige Standalone-mit-HA-API-Doku in
   `HANDBUCH_INSTALLATION.md` ist nicht trivial; es gibt heute nur die
   Add-on-Anleitung in voller Tiefe.

---

## 6. Trigger / Wann umsetzen

**Heute (2026-05-01) noch nicht.** Voraussetzungen:

- ≥ 2 weitere Forum/PN-Anfragen zur Standalone-mit-HA-Anbindung. Eine
  Anfrage allein rechtfertigt 1–2 Tage Refactoring nicht.
- ODER: jemand will EEDC explizit per Reverse-Proxy mit eigener Domain
  einbetten und braucht stabile URLs (iframe-Cards-Anwendungsfall).
- ODER: die HA-Recorder-DB-Schema-Stabilität wird zum Problem (HA-
  Update bricht den DB-Direktread).

**Vor Umsetzung zu klären:**

- Hybrid- oder einheitlicher Pfad (siehe §4)
- Welche WebSocket-Library (`aiohttp` reicht; oder `homeassistant-api`
  als bestehender Wrapper)
- Doku-Strategie: erweiterte `HANDBUCH_INSTALLATION.md` vs. eigenes
  `HANDBUCH_STANDALONE_HA_API.md`

---

## 7. Out of Scope

- **Kein eigener Auth-Layer in EEDC.** Wenn Standalone öffentlich
  erreichbar sein soll, ist das Anwender-Verantwortung (Reverse Proxy).
- **Kein automatisches LLT-Provisioning.** Anwender erzeugt selbst,
  trägt selbst ein.
- **Keine Multi-HA-Unterstützung** in v1. Eine HA-Instanz pro
  EEDC-Instanz.
- **Keine Migration vom Add-on-Modus** für Bestandsanwender. Wer im
  Add-on glücklich ist, bleibt dort.

---

## Anhang: Verweise

- `eedc/backend/services/ha_statistics_service.py:31` — kritische Stelle
- `eedc/backend/core/config.py:74` — `ha_api_url` heute hardcoded
- `eedc/backend/core/config.py:71` — `HA_RECORDER_DB_URL` als heutiger
  Standalone-Workaround (MariaDB-only)
- HA-Doku: `recorder/get_statistics_during_period` WebSocket-API
- [docs/drafts/KONZEPT-LIVE-SNAPSHOT-5MIN.md](KONZEPT-LIVE-SNAPSHOT-5MIN.md) —
  parallele Refactoring-Story, gleicher Geist (API-First statt
  Datenquelle-Hack)
