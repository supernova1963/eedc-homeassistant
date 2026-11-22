<!-- anker: 48l-zaehlerstaende--daten-vor-der-aenderung-geloescht -->
### 4.8l Zählerstände – Daten vor der Änderung gelöscht <a name="48l-zaehlerstaende--daten-vor-der-aenderung-geloescht"></a>

Wechselt die Quelle eines Felds, das schon eigene Werte hat, fragt eedc: «Bisherige Werte bleiben» oder «Daten vor der Änderung
löschen». Mit «löschen» gehen nur die Daten dieses Felds aus der Zeit vor der Änderung weg; das Feld verhält sich danach, als
wäre der neue Sensor von Anfang an zugeordnet — was Home Assistant für ihn führt, übernimmt eedc, davor zeigt das Feld «—».
Diese Kategorie nennt je solchem Feld eine Auskunft: wann gelöscht wurde, seit wann Home Assistant den neuen Sensor führt, ob
der erste Tag für das Feld nur teilweise zählt (der Sensor beginnt in Home Assistant mitten am Tag — eedc zählt den Tag wie Home
Assistant ab dieser Stunde), und die Monate mit gespeichertem Monatswert, die bleiben. Nach einer ersten Zuordnung ohne
«löschen» gibt es diese Auskunft nicht, auch wenn der erste Tag dort ebenso nur ab der ersten Stunde der Statistik zählt
([Handbuch Einstellungen §7.7c](HANDBUCH_EINSTELLUNGEN.md#77c-was-passiert-wenn)).

---
