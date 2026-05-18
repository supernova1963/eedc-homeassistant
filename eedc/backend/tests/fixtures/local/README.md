# Lokale Test-Fixtures

Dieser Ordner ist per `.gitignore` aus dem Repo ausgeschlossen — alles ausser
dieser README und `.gitignore` selbst.

Hier kannst du echte eedc-Backup-Exporte ablegen, gegen die Tests laufen
sollen (z.B. zur Diagnose eines konkreten User-Setups), ohne dass
personenbezogene Daten in git wandern.

## Verwendung

Speichere deine Backup-Datei als `backup.json` in diesem Ordner. `test_H8_optional_aus_lokalem_backup`
in [test_emob_km_uebersicht_bug.py](../../test_emob_km_uebersicht_bug.py)
lädt sie automatisch und prüft das Cockpit-Übersicht-Verhalten gegen die
ungefilterte IMD-Summe. Ohne Datei → Test wird übersprungen.
