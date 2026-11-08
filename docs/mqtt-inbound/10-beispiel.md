### Beispiel

Fuer eine Anlage "Meine PV" (ID 1) mit Speicher "BYD HVS" (ID 3):

```
eedc/1_Meine_PV/live/einspeisung_w          → 1100
eedc/1_Meine_PV/live/inv/3_BYD_HVS/leistung_w → -500
eedc/1_Meine_PV/live/inv/3_BYD_HVS/soc      → 72
eedc/1_Meine_PV/energy/pv_gesamt_kwh         → 627.0
eedc/1_Meine_PV/energy/inv/3_BYD_HVS/ladung_kwh → 128.6
```

**Hinweis:** Die numerische ID am Anfang (`1_`, `3_`) ist die DB-ID. Der Name danach ist optional und dient nur der Lesbarkeit. EEDC extrahiert nur die ID.

