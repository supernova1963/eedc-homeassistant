#!/usr/bin/env bash
# EEDC Entwicklungsrechner Setup-Script
# Ubuntu 24.04 | Führe aus: bash setup-devmachine.sh
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
section() { echo -e "\n${YELLOW}=== $1 ===${NC}"; }

section "1. System-Pakete"
sudo apt update -q && sudo apt install -y \
  git curl python3.12 python3.12-venv python3-pip build-essential
info "System-Pakete installiert"

section "2. NVM + Node.js 20"
if [ ! -d "$HOME/.nvm" ]; then
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  info "NVM installiert"
else
  info "NVM bereits vorhanden"
fi

# NVM in aktuelle Shell laden
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

nvm install 20 --silent
nvm use 20
nvm alias default 20
info "Node.js $(node --version) aktiv"

section "3. Claude Code"
if ! command -v claude &>/dev/null; then
  npm install -g @anthropic-ai/claude-code --silent
  info "Claude Code $(claude --version) installiert"
else
  info "Claude Code bereits installiert: $(claude --version)"
fi

section "4. Git konfigurieren"
CURRENT_EMAIL=$(git config --global user.email 2>/dev/null || echo "")
if [ -z "$CURRENT_EMAIL" ]; then
  git config --global user.name "supernova1963"
  git config --global user.email "supernova1963@users.noreply.github.com"
  git config --global init.defaultBranch main
  info "Git konfiguriert"
else
  info "Git bereits konfiguriert: $CURRENT_EMAIL"
fi

section "5. VS Code"
if ! command -v code &>/dev/null; then
  warn "VS Code nicht gefunden – bitte manuell installieren:"
  warn "  https://code.visualstudio.com/download"
  warn "Danach dieses Script erneut ausführen oder Extensions manuell installieren."
else
  info "VS Code gefunden: $(code --version | head -1)"

  section "6. VS Code Erweiterungen"
  EXTENSIONS=(
    anthropic.claude-code
    andrepimenta.claude-code-chat
    ms-python.python
    ms-python.vscode-pylance
    ms-python.debugpy
    ms-python.vscode-python-envs
    charliermarsh.ruff
    esbenp.prettier-vscode
    dbaeumer.vscode-eslint
    bradlc.vscode-tailwindcss
    eamodio.gitlens
    usernamehw.errorlens
    qwtel.sqlite-viewer
    redhat.vscode-yaml
    ms-vscode-remote.remote-ssh
    ms-vscode-remote.remote-ssh-edit
    ms-vscode.remote-explorer
    ms-azuretools.vscode-docker
    ms-azuretools.vscode-containers
    christian-kohler.path-intellisense
  )

  INSTALLED=$(code --list-extensions 2>/dev/null)
  for EXT in "${EXTENSIONS[@]}"; do
    if echo "$INSTALLED" | grep -qi "^${EXT}$"; then
      info "  $EXT (bereits installiert)"
    else
      code --install-extension "$EXT" --force &>/dev/null && info "  $EXT installiert"
    fi
  done

  section "7. VS Code Einstellungen"
  mkdir -p ~/.config/Code/User
  SETTINGS_FILE=~/.config/Code/User/settings.json
  if [ ! -f "$SETTINGS_FILE" ]; then
    cat > "$SETTINGS_FILE" << 'SETTINGS'
{
    "claudeCodeChat.thinking.intensity": "ultrathink",
    "claudeCode.preferredLocation": "panel",
    "redhat.telemetry.enabled": false
}
SETTINGS
    info "VS Code Einstellungen geschrieben"
  else
    info "VS Code Einstellungen bereits vorhanden (nicht überschrieben)"
  fi
fi

section "8. Projekte klonen"
mkdir -p ~/claude
cd ~/claude

if [ ! -d "eedc-homeassistant" ]; then
  git clone https://github.com/supernova1963/eedc-homeassistant.git
  info "eedc-homeassistant geklont"
else
  info "eedc-homeassistant bereits vorhanden – git pull..."
  git -C eedc-homeassistant pull --ff-only 2>/dev/null || warn "Pull nicht möglich (lokale Änderungen?)"
fi

if [ ! -d "eedc-community" ]; then
  git clone https://github.com/supernova1963/eedc-community.git
  info "eedc-community geklont"
else
  info "eedc-community bereits vorhanden – git pull..."
  git -C eedc-community pull --ff-only 2>/dev/null || warn "Pull nicht möglich (lokale Änderungen?)"
fi

section "9. Python venv einrichten"
VENV_PATH=~/claude/eedc-homeassistant/eedc/backend/venv
if [ ! -d "$VENV_PATH" ]; then
  python3 -m venv "$VENV_PATH"
  source "$VENV_PATH/bin/activate"
  pip install -q -r ~/claude/eedc-homeassistant/eedc/backend/requirements.txt
  deactivate
  info "Python venv erstellt und Dependencies installiert"
else
  info "Python venv bereits vorhanden"
fi

section "10. Frontend npm install"
FRONTEND_PATH=~/claude/eedc-homeassistant/eedc/frontend
if [ ! -d "$FRONTEND_PATH/node_modules" ]; then
  cd "$FRONTEND_PATH"
  npm install --silent
  info "Frontend node_modules installiert"
else
  info "Frontend node_modules bereits vorhanden"
fi

# Abschluss
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Setup abgeschlossen! Nächste Schritte:         ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                                  ║${NC}"
echo -e "${GREEN}║  Backend starten:                                ║${NC}"
echo -e "${GREEN}║    cd ~/claude/eedc-homeassistant/eedc           ║${NC}"
echo -e "${GREEN}║    source backend/venv/bin/activate              ║${NC}"
echo -e "${GREEN}║    uvicorn backend.main:app --reload --port 8099 ║${NC}"
echo -e "${GREEN}║                                                  ║${NC}"
echo -e "${GREEN}║  Frontend starten (neues Terminal):              ║${NC}"
echo -e "${GREEN}║    cd ~/claude/eedc-homeassistant/eedc/frontend  ║${NC}"
echo -e "${GREEN}║    npm run dev                                   ║${NC}"
echo -e "${GREEN}║                                                  ║${NC}"
echo -e "${GREEN}║  Browser: http://localhost:3000                  ║${NC}"
echo -e "${GREEN}║                                                  ║${NC}"
echo -e "${GREEN}║  Falls NVM nicht gefunden:                       ║${NC}"
echo -e "${GREEN}║    source ~/.bashrc && nvm use 20                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
