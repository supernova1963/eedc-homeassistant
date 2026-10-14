# Sicherheit

## Unterstützte Versionen

Gepflegt wird nur das **aktuelle Release** (oberster Abschnitt im [CHANGELOG](CHANGELOG.md)).
Eine Korrektur erscheint als neues Release; ältere Versionen erhalten keine Nachträge.

## Eine Sicherheitslücke melden

Bitte **nicht** als öffentliches Issue. Nutze die vertrauliche Meldung über GitHub:
*Security → Report a vulnerability* im Repository
[eedc-homeassistant](https://github.com/supernova1963/eedc-homeassistant/security/advisories/new).

Hilfreich sind: Betriebsart (Home-Assistant-Add-on oder Standalone), eedc-Version, der Weg zum
Nachstellen und was ein Angreifer damit erreicht. Du bekommst eine Rückmeldung, sobald der Maintainer
die Meldung gesehen hat; einen festen Zeitplan gibt es in einem Ein-Personen-Projekt nicht. Die Lücke
wird erst nach dem Release mit der Korrektur öffentlich beschrieben.

## Was eedc voraussetzt

eedc ist für das **eigene Heimnetz** gebaut und hat **keine eigene Benutzeranmeldung**. Wer die Oberfläche
erreicht, sieht alle Daten der Anlage. Die **Einstellungs-PIN** (*Einstellungen → Stammdaten*) schützt
das Verändern von Einstellungen, nicht das Lesen.

**Home-Assistant-Add-on.** Die Oberfläche läuft über **Ingress**: Der Browser erreicht eedc nur über
Home Assistant, mit dessen Anmeldung und Benutzerverwaltung. Der Port 8099 ist in der Add-on-Konfiguration
**standardmäßig aus**. Wer ihn freigibt (für den REST-Export nach Home Assistant), öffnet die
Oberfläche und die API für jeden im Netz **ohne** die HA-Anmeldung — dann gilt das Gleiche wie beim
Standalone-Betrieb.

**Standalone (Docker).** Der Container lauscht auf Port 8099 ohne Anmeldung. Er gehört hinter die
Firewall des Heimnetzes oder hinter einen Reverse-Proxy mit Login bzw. in ein VPN — **nie** direkt
ins Internet. Die API erlaubt Cross-Origin-Anfragen ohne Cookies (`allow_origins=["*"]`,
`allow_credentials=False`); eine fremde Webseite im Browser eines Anwenders könnte so Antworten
der API lesen, wenn sie die Adresse im Heimnetz kennt. Ein Reverse-Proxy mit Login schließt das.

**Daten und Zugangsdaten.** Alle Daten liegen lokal in `eedc.db` (SQLite). Zugangsdaten, die du eedc
gibst (Wechselrichter-Konten für den Cloud-Import, MQTT, Geräte-Anbindungen), liegen dort ebenfalls und
sind **nicht verschlüsselt**; ein Backup der Datenbank enthält sie. Das HA-Token des Add-ons stellt der
Supervisor bereit und wird nicht gespeichert.

**Was eedc nicht tut.** eedc steuert keine Geräte und wirkt nicht nach außen; es liest Sensoren, Zähler
und Cloud-Portale und exportiert optional Werte per MQTT oder REST. Die Community-Funktion ist
freiwillig und überträgt nur die anonymisierten Monatswerte, die du vor dem Senden siehst.

## Was keine Sicherheitslücke ist

- Fehlende Anmeldung im Standalone-Betrieb oder bei freigegebenem Port 8099 — das ist das
  beschriebene Betriebsmodell. Ein Login davor ist Aufgabe des Betreibers.
- Lesender Zugriff aus dem eigenen Netz auf Daten der eigenen Anlage.
- Befunde aus automatischen Scannern ohne nachstellbare Wirkung.
