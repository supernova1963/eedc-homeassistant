### Themen je Gerät

An Wärmepumpe, Wallbox und E-Auto kannst du unter *Einstellungen → Datenquellen* **Themen** mit frei gewählten
Einträgen anlegen ([Handbuch Einstellungen §7.11](HANDBUCH_EINSTELLUNGEN.md#711-themen-frei-gewählte-entitäten)). Jeder
Eintrag hat ein eigenes Live-Topic:

```
eedc/{anlage_id}_{anlage_name}/live/inv/{id}_{name}/thema_e{n}
```

- `e{n}` ist die Kennung des Eintrags (`e2`, `e5` …) — sie steht in der Zeile der Zuordnung und bleibt, auch wenn du den
  Eintrag umbenennst oder verschiebst. Eine gelöschte Kennung wird nie wieder vergeben.
- Der Payload ist **Text** und wird **wie geliefert** angezeigt (`locked`, `2.4`, `2026-11-02T07:00:00+00:00`) — keine
  Umrechnung, keine Einheit. Leer, `unknown` und `unavailable` gelten als „kein Wert".
- Publiziere **retained**: eedc liest den letzten Wert aus dem Cache; ohne retained steht nach einem Neustart nichts da.
- Der Wert wird nicht mitgeschrieben (kein Verlauf), und der Daten-Checker erwartet das Topic nicht.
- Über das **Gateway** reicht eedc ein Fremd-Topic als Text an `…/thema_e{n}` weiter (Faktor und Offset gelten nicht).

