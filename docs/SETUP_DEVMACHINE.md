# EEDC Entwicklungsrechner einrichten

Anleitung zum Aufsetzen einer identischen Entwicklungsumgebung auf einem neuen Ubuntu 24.04 Rechner.

---

## Schnellstart: Setup-Script ausführen

```bash
# Script herunterladen und ausführen
curl -fsSL https://raw.githubusercontent.com/supernova1963/eedc-homeassistant/main/docs/setup-devmachine.sh | bash
```

Oder manuell Schritt für Schritt nach dieser Anleitung.

---

## 1. System-Pakete

```bash
sudo apt update && sudo apt install -y \
  git \
  curl \
  python3.12 \
  python3.12-venv \
  python3-pip \
  build-essential
```

---

## 2. Node.js via NVM

```bash
# NVM installieren
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash

# Shell neu laden
source ~/.bashrc   # oder: source ~/.zshrc

# Node.js 20 installieren und als Standard setzen
nvm install 20
nvm use 20
nvm alias default 20

# Prüfen
node --version   # → v20.x.x
npm --version    # → 10.x.x
```

---

## 3. Claude Code installieren

```bash
npm install -g @anthropic-ai/claude-code

# Prüfen
claude --version   # → 2.1.50 (oder neuer)
```

Bei der ersten Verwendung: `claude` ausführen und mit Anthropic-Account authentifizieren.

---

## 4. Git konfigurieren

```bash
git config --global user.name "supernova1963"
git config --global user.email "supernova1963@users.noreply.github.com"
git config --global init.defaultBranch main

# GitHub SSH-Key einrichten (empfohlen)
ssh-keygen -t ed25519 -C "supernova1963@users.noreply.github.com"
cat ~/.ssh/id_ed25519.pub
# → Public Key zu GitHub hinzufügen: https://github.com/settings/keys
```

---

## 5. VS Code installieren

```bash
# .deb-Paket herunterladen und installieren
curl -L "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64" -o /tmp/vscode.deb
sudo dpkg -i /tmp/vscode.deb
sudo apt install -f  # ggf. fehlende Dependencies nachinstallieren
```

---

## 6. VS Code Erweiterungen installieren

```bash
# Alle Extensions auf einmal installieren:
code --install-extension anthropic.claude-code
code --install-extension andrepimenta.claude-code-chat
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension ms-python.debugpy
code --install-extension ms-python.vscode-python-envs
code --install-extension charliermarsh.ruff
code --install-extension esbenp.prettier-vscode
code --install-extension dbaeumer.vscode-eslint
code --install-extension bradlc.vscode-tailwindcss
code --install-extension eamodio.gitlens
code --install-extension usernamehw.errorlens
code --install-extension qwtel.sqlite-viewer
code --install-extension redhat.vscode-yaml
code --install-extension ms-vscode-remote.remote-ssh
code --install-extension ms-vscode-remote.remote-ssh-edit
code --install-extension ms-vscode.remote-explorer
code --install-extension ms-azuretools.vscode-docker
code --install-extension ms-azuretools.vscode-containers
code --install-extension christian-kohler.path-intellisense
```

### Erweiterungs-Übersicht

| Extension | Zweck |
|-----------|-------|
| `anthropic.claude-code` | Claude Code (KI-Assistent) |
| `andrepimenta.claude-code-chat` | Claude Code Chat-Panel |
| `ms-python.python` + `pylance` + `debugpy` | Python-Stack |
| `ms-python.vscode-python-envs` | Virtuelle Environments |
| `charliermarsh.ruff` | Python Linter/Formatter |
| `esbenp.prettier-vscode` | Code-Formatierung (JS/TS) |
| `dbaeumer.vscode-eslint` | TypeScript/JS Linting |
| `bradlc.vscode-tailwindcss` | Tailwind CSS Autocomplete |
| `eamodio.gitlens` | Git-Verlauf und Blame |
| `usernamehw.errorlens` | Fehler direkt im Code |
| `qwtel.sqlite-viewer` | SQLite-Datenbank anzeigen |
| `redhat.vscode-yaml` | YAML-Unterstützung |
| `ms-vscode-remote.remote-ssh` | SSH-Fernzugriff (z.B. Server 192.168.1.3) |
| `ms-azuretools.vscode-docker` | Docker-Integration |
| `christian-kohler.path-intellisense` | Pfad-Autocomplete |

---

## 7. VS Code User-Einstellungen

Datei: `~/.config/Code/User/settings.json`

```json
{
    "claudeCodeChat.thinking.intensity": "ultrathink",
    "claudeCode.preferredLocation": "panel",
    "redhat.telemetry.enabled": false
}
```

```bash
mkdir -p ~/.config/Code/User
cat > ~/.config/Code/User/settings.json << 'EOF'
{
    "claudeCodeChat.thinking.intensity": "ultrathink",
    "claudeCode.preferredLocation": "panel",
    "redhat.telemetry.enabled": false
}
EOF
```

---

## 8. Projekte klonen

```bash
mkdir -p ~/claude
cd ~/claude

# eedc-homeassistant
git clone git@github.com:supernova1963/eedc-homeassistant.git
# oder HTTPS: git clone https://github.com/supernova1963/eedc-homeassistant.git

# eedc-community
git clone git@github.com:supernova1963/eedc-community.git
# oder HTTPS: git clone https://github.com/supernova1963/eedc-community.git
```

---

## 9. Backend einrichten

```bash
cd ~/claude/eedc-homeassistant

# Python venv erstellen (einmalig)
python3 -m venv eedc/backend/venv

# Dependencies installieren
source eedc/backend/venv/bin/activate
pip install -r eedc/backend/requirements.txt
deactivate
```

---

## 10. Frontend einrichten

```bash
cd ~/claude/eedc-homeassistant/eedc/frontend

# Node.js 20 sicherstellen
nvm use 20

# Dependencies installieren
npm install
```

---

## 11. Entwicklungsserver starten

**Terminal 1 – Backend:**
```bash
cd ~/claude/eedc-homeassistant/eedc
source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099
```

**Terminal 2 – Frontend:**
```bash
cd ~/claude/eedc-homeassistant/eedc/frontend
npm run dev
```

**Browser:**
- Frontend (mit Hot-Reload): http://localhost:3000
- API-Docs: http://localhost:8099/api/docs

**Demo-Daten laden:**
```bash
curl -s -X POST http://localhost:8099/api/import/demo | python3 -m json.tool
```

---

## 12. VS Code Workspace öffnen

```bash
# Beide Projekte als Workspace öffnen
code ~/claude/eedc-homeassistant
# oder beide gleichzeitig:
code ~/claude/eedc-homeassistant ~/claude/eedc-community
```

VS Code erkennt das Python-venv automatisch wenn `eedc/backend/venv/` vorhanden ist.

---

## Überprüfung

```bash
# Alle Versionen prüfen
echo "=== System ==="
python3 --version       # Python 3.12.x
node --version          # v20.x.x
npm --version           # 10.x.x
git --version           # 2.x.x
claude --version        # 2.x.x

echo "=== Projekt ==="
ls ~/claude/eedc-homeassistant/eedc/backend/venv/bin/python3  # venv vorhanden
ls ~/claude/eedc-homeassistant/eedc/frontend/node_modules/.bin/vite  # npm installiert

echo "=== Git ==="
git config --global user.email  # supernova1963@users.noreply.github.com
```

---

## Ports

| Service | Port | URL |
|---------|------|-----|
| Frontend Dev Server (Vite) | 3000 | http://localhost:3000 |
| Backend API (uvicorn) | 8099 | http://localhost:8099 |
| API Docs (Swagger) | 8099 | http://localhost:8099/api/docs |

---

## Notizen

- **Python venv**: liegt unter `eedc/backend/venv/` – nicht committen (in `.gitignore`)
- **node_modules**: liegt unter `eedc/frontend/node_modules/` – nicht committen
- **Datenbank**: liegt unter `eedc/data/eedc.db` (wird beim ersten Start erstellt)
- **NVM**: bei neuen Terminals ggf. `nvm use 20` ausführen, falls Node-Version nicht stimmt
- **VS Code Python Interpreter**: nach dem Öffnen des Projekts unten rechts auf den Interpreter klicken und `eedc/backend/venv/bin/python3` wählen
