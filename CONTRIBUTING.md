# Beitragen zu eedc

eedc ist ein Solo-Open-Source-Projekt und seit Oktober 2026 im **Wartungsmodus**: Fehler werden behoben,
neue Funktionen nicht mehr geplant. Fehlerberichte haben Vorrang und sind willkommen. Wünsche sammelt
[#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) ohne Termin.

Sicherheitslücken bitte **nicht** als öffentliches Issue — siehe [SECURITY.md](SECURITY.md).

## Wo eedc entwickelt wird

| Repository | Rolle |
| --- | --- |
| [eedc-homeassistant](https://github.com/supernova1963/eedc-homeassistant) | **Hier** entsteht alles: Home-Assistant-Add-on, Standalone-Code, Website, Dokumentation. Issues und Pull Requests gehören hierher. |
| [eedc](https://github.com/supernova1963/eedc) | Spiegel für das Standalone-Deployment (Docker). Wird nur vom Release-Skript geschrieben; Pull Requests dort können nicht angenommen werden. |
| [eedc-card](https://github.com/supernova1963/eedc-card) | Karte für das HA-Dashboard, eigenes Repository. |

## Einen Fehler melden

Ein [GitHub-Issue](https://github.com/supernova1963/eedc-homeassistant/issues/new) hilft am meisten, wenn es enthält:

1. **Betriebsart:** Home-Assistant-Add-on oder Standalone (Docker). Beim Add-on auch die HA-Version,
   beim Standalone das Image-Tag bzw. den Stand aus `docker compose`.
2. **eedc-Version** — steht in der Fußzeile der Oberfläche und oben im [CHANGELOG](CHANGELOG.md).
3. **Was du erwartet hast und was eedc zeigt** — bei einer falschen Zahl möglichst die Zahl, die du für
   richtig hältst, und woher sie kommt (Wechselrichter-App, Zähler, HA-Energie-Dashboard).
4. **Screenshot** der Stelle, inklusive der Seite und des Zeitraums.
5. **Daten-Checker:** *Einstellungen → Daten-Checker* nennt fehlende oder widersprüchliche Werte.
   Oft ist der Befund dort die Antwort — eedc rechnet mit dem, was es hat, und zeigt an, was fehlt.
6. **Log-Auszug** aus der Zeit des Fehlers: Add-on unter *Einstellungen → Add-ons → eedc → Protokoll*,
   Standalone mit `docker compose logs eedc`. Eigene Zugangsdaten und Token vorher schwärzen.

Was eedc rechnet und welche Daten es dafür voraussetzt, steht in
[docs/BERECHNUNGEN.md](docs/BERECHNUNGEN.md) und den Handbüchern unter [docs/](docs/).
Ein Blick dorthin vor dem Melden spart oft eine Rückfrage.

## Pull Requests

Vor einem Pull Request bitte ein Issue, damit klar ist, ob die Änderung in den Wartungsmodus passt.
Kleine, abgegrenzte Änderungen mit einem Zweck haben die beste Chance. Was ein Pull Request mitbringen muss:

- **Entwicklungsumgebung** nach [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md); die Code-Regeln dort
  (Abschnitte *Code-Konventionen* und *Kritische Code-Patterns*) gelten — Monatswerte nur aus den
  Monats-Fakten, Kennwerte nur über die Helfer, eine Formel an einem Ort.
- **Gates grün**, lokal vor dem Einreichen:

  ```bash
  cd eedc && source backend/venv/bin/activate
  ruff check backend                       # Lint (Pyflakes + Syntax, eedc/ruff.toml)
  python -m pytest backend/tests -q -n 3   # Backend-Suite (rund 9 Minuten)
  cd frontend && npm run lint && npx tsc --noEmit && npm run test
  ```

- **Keine Repo-weiten Reformatierungen** und keine Umbenennungen ohne Anlass — die Suite und die
  Wächter in `backend/tests` sowie `npm run check:*` prüfen Invarianten, die daran hängen.
- **Abhängigkeiten:** Backend-Pakete stehen in `backend/requirements.txt`; danach das Lock neu erzeugen
  (Anleitung im Kopf der Datei). Beide Dockerfiles installieren nur das Lock.
- **Dokumentation gehört zur Änderung:** Eintrag unter `[Unreleased]` im [CHANGELOG](CHANGELOG.md),
  bei sichtbarer Wirkung [docs/WAS-IST-NEU.md](docs/WAS-IST-NEU.md) und das betroffene Handbuch;
  `./scripts/sync-help.sh` spiegelt die Hilfe in die Oberfläche.
- **Commit-Botschaften auf Deutsch**, der Betreff nennt die Wirkung für den Anwender, nicht die Technik.
- Oberfläche und Dokumentation sind **deutsch**; es gibt keine Übersetzungsschicht.

Releases, Tags und das Spiegeln nach `eedc` macht der Maintainer über `scripts/release.sh`.

## Lizenz

Mit einem Beitrag stimmst du zu, dass er unter der [MIT-Lizenz](LICENSE) des Projekts veröffentlicht wird.
