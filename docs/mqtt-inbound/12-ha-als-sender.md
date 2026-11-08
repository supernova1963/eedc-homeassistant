## Home Assistant als Sender

Einen eingebauten Automations-Generator gibt es seit der Oberfläche 4.0 nicht mehr. Wer Werte aus Home Assistant
per MQTT an eedc schickt, legt die Automation selbst an — Vorlage im nächsten Abschnitt. Im HA-Add-on ist das
in der Regel unnötig: dort ordnest du HA-Sensoren direkt unter *Einstellungen → Datenquellen* zu, ohne MQTT.
Die erwarteten Topics deiner Anlage zeigt der Block **MQTT-Topics** am Ende der Datenquellen-Fläche zum Kopieren.

