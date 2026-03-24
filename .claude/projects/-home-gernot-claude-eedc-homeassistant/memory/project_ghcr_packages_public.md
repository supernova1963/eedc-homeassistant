---
name: ghcr.io Packages auf Public stellen
description: Nach dem ersten Release mit Docker-Build müssen die neuen ghcr.io Packages einmalig auf Public gestellt werden
type: project
---

Nach dem ersten Release das den neuen Docker-Build-Workflow nutzt (ab v3.4.19+), müssen die zwei neuen ghcr.io Packages einmalig auf **public** gestellt werden, sonst können HA-Nutzer die Images nicht pullen.

Packages: `eedc-homeassistant-amd64` und `eedc-homeassistant-aarch64`
Ort: GitHub Profil → Packages → Package Settings → Visibility → Public

**Why:** Neue GitHub Packages sind standardmäßig privat. HA-Nutzer pullen ohne Auth.
**How to apply:** Bei jedem Release-Vorgang prüfen ob dies das erste Release mit Docker-Build ist, und den User aktiv daran erinnern.
