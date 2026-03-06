# EEDC installieren - Schritt-für-Schritt-Anleitung

Diese Anleitung richtet sich an Einsteiger ohne Vorkenntnisse.
EEDC läuft in einem sogenannten "Container" - dafür wird Docker benötigt.

---

## Schritt 1: Docker installieren

### Windows 10/11

1. **Docker Desktop herunterladen:**
   - Öffne https://www.docker.com/products/docker-desktop/
   - Klicke auf **"Download for Windows"**

2. **Installieren:**
   - Doppelklicke die heruntergeladene Datei `Docker Desktop Installer.exe`
   - Folge dem Installationsassistenten (alle Voreinstellungen beibehalten)
   - Am Ende: **Neustart des PCs** durchführen

3. **Docker starten:**
   - Nach dem Neustart: Docker Desktop über das Startmenü öffnen
   - Beim ersten Start dauert es 1-2 Minuten - warte bis unten links **"Docker Desktop is running"** steht
   - Docker Desktop muss im Hintergrund laufen, damit EEDC funktioniert

4. **Terminal öffnen:**
   - Drücke `Windows-Taste + R`, tippe `cmd` und drücke Enter

### macOS

1. **Docker Desktop herunterladen:**
   - Öffne https://www.docker.com/products/docker-desktop/
   - Klicke auf **"Download for Mac"**
   - Wähle **Apple Chip** (neuere Macs ab 2020) oder **Intel Chip** (ältere Macs)
   - Unsicher? Klicke oben links auf das Apple-Symbol > "Über diesen Mac"

2. **Installieren:**
   - Öffne die heruntergeladene `.dmg`-Datei
   - Ziehe das Docker-Symbol in den Programme-Ordner

3. **Docker starten:**
   - Öffne Docker aus dem Programme-Ordner
   - Bestätige die Sicherheitsabfrage mit "Öffnen"
   - Warte bis das Docker-Symbol oben in der Menüleiste **nicht mehr animiert** ist

4. **Terminal öffnen:**
   - Drücke `Cmd + Leertaste`, tippe `Terminal` und drücke Enter

### Linux (Ubuntu/Debian)

Öffne ein Terminal und führe diese Befehle nacheinander aus:

```bash
# Docker installieren
curl -fsSL https://get.docker.com | sudo sh

# Deinen Benutzer zur Docker-Gruppe hinzufügen (damit du kein sudo brauchst)
sudo usermod -aG docker $USER

# WICHTIG: Einmal ab- und wieder anmelden, damit die Gruppenzugehörigkeit wirkt
```

Nach dem erneuten Anmelden ein neues Terminal öffnen.

---

## Schritt 2: Prüfen ob Docker funktioniert

Tippe im Terminal folgenden Befehl ein und drücke Enter:

```bash
docker --version
```

Es sollte etwas wie `Docker version 27.x.x` erscheinen.
Wenn eine Fehlermeldung kommt: Stelle sicher, dass Docker Desktop läuft (Windows/Mac)
bzw. der Docker-Dienst gestartet ist (Linux).

---

## Schritt 3: EEDC starten

Tippe im Terminal folgenden Befehl ein und drücke Enter:

```bash
docker run -d --name eedc -p 8099:8099 -v eedc-data:/data --restart unless-stopped ghcr.io/supernova1963/eedc:latest
```

Was passiert:
- Docker lädt EEDC automatisch herunter (beim ersten Mal ca. 200-400 MB)
- Der Container wird gestartet und läuft im Hintergrund
- Deine Daten werden dauerhaft gespeichert (auch nach Neustart)

Das Herunterladen dauert je nach Internetverbindung 1-5 Minuten.
Warte, bis der Befehl abgeschlossen ist (du siehst wieder die Eingabeaufforderung).

---

## Schritt 4: EEDC öffnen

Öffne deinen Browser und gehe zu:

**http://localhost:8099**

Fertig! Du kannst jetzt mit EEDC arbeiten.

---

## EEDC aktualisieren

Wenn eine neue Version verfügbar ist:

```bash
docker pull ghcr.io/supernova1963/eedc:latest
docker stop eedc
docker rm eedc
docker run -d --name eedc -p 8099:8099 -v eedc-data:/data --restart unless-stopped ghcr.io/supernova1963/eedc:latest
```

Deine Daten bleiben dabei erhalten.

---

## EEDC stoppen und wieder starten

```bash
# Stoppen
docker stop eedc

# Wieder starten
docker start eedc
```

---

## Problembehebung

| Problem | Lösung |
|---------|--------|
| "docker: command not found" | Docker Desktop starten (Windows/Mac) oder `sudo systemctl start docker` (Linux) |
| "port is already allocated" | Ein anderes Programm nutzt Port 8099. Verwende einen anderen Port: `-p 9099:8099` und öffne dann `http://localhost:9099` |
| Seite lädt nicht | Warte 10 Sekunden nach dem Start, dann nochmal versuchen |
| "permission denied" (Linux) | Ab- und wieder anmelden nach der Installation, oder `sudo` vor den docker-Befehl setzen |

---

## Alles entfernen (Deinstallation)

```bash
# EEDC Container und Daten löschen
docker stop eedc
docker rm eedc
docker volume rm eedc-data
docker rmi ghcr.io/supernova1963/eedc:latest

# Docker Desktop kann danach normal über die Systemeinstellungen deinstalliert werden
```
