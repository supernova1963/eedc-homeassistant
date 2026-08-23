# Lokale Test-Fixtures

Dieser Ordner ist per `.gitignore` aus dem Repo ausgeschlossen — alles ausser
dieser README und `.gitignore` selbst.

Hier kannst du echte eedc-Backup-Exporte ablegen, gegen die Tests laufen
sollen (z.B. zur Diagnose eines konkreten User-Setups), ohne dass
personenbezogene Daten in git wandern.

## Verwendung

Lege eine Backup-Datei hier ab und schreibe den Test, der sie liest, **in der
Sitzung, in der du sie brauchst** — als Diagnose-Werkzeug, nicht als Bestandteil
der Suite.

> ⚠ **Kein Dauertest gegen diesen Ordner.** Bis zum 2026-08-23 stand hier
> `test_H8_optional_aus_lokalem_backup` (in `test_emob_km_uebersicht_bug.py`)
> und las `backup.json`. Da der Ordner git-ignoriert ist, existierte die Datei
> auf keinem anderen Rechner und in keinem CI-Lauf — der Test kehrte still
> zurück und wurde als *passed* gezählt, ohne etwas zu messen. Ein Test, dessen
> Eingabe per Konstruktion nirgends vorhanden sein kann, ist kein Test, sondern
> eine grüne Zeile. Er ist deshalb entfallen (M4, Etappe E1).
