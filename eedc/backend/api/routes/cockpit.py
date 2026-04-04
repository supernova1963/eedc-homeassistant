"""
Backward-compatibility shim — bitte aus backend.api.routes.cockpit importieren.

HINWEIS: Diese Datei sollte nicht mehr direkt importiert werden.
main.py importiert `cockpit.router` — da cockpit/ ein Package ist,
wird automatisch cockpit/__init__.py geladen. Diese Datei ist redundant
und kann entfernt werden sobald sichergestellt ist dass keine externen
Importe mehr auf cockpit.py zeigen.
"""
# Dieses Shim ist leer — main.py lädt cockpit/__init__.py (Package hat Vorrang)
