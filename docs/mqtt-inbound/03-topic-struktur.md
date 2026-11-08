## Topic-Struktur

EEDC generiert die Topics automatisch aus den angelegten Anlagen und Investitionen. Das Format ist:

```
eedc/{anlage_id}_{name}/
├── live/                              # Momentanwerte (W, °C, %) und der Betriebsmodus
│   ├── einspeisung_w                  → 1100
│   ├── netzbezug_w                    → 0
│   └── inv/{inv_id}_{name}/
│       ├── leistung_w                 → 4200
│       ├── soc                        → 72       (nur Speicher/E-Auto)
│       ├── vorlauf_temperatur_c       → 34.5     (nur Waermepumpe; ebenso ruecklauf_/warmwasser_temperatur_c)
│       └── betriebsmodus              → 1        (nur Waermepumpe: Wort oder Code, siehe unten)
│
└── energy/                            # ZAEHLERSTAENDE (kWh, kumuliert)
    ├── einspeisung_kwh                → 6675.3
    ├── netzbezug_kwh                  → 6424.8
    └── inv/{inv_id}_{name}/
        └── {key}                      → Wert     (siehe Felder-Referenz)
```

