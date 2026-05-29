
# eedc Handbuch — Prognosen

**Version 3.34.1** | Stand: Mai 2026

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Energieprofil](HANDBUCH_ENERGIEPROFIL.md) | [Teil III: Einstellungen & Sensormapping](HANDBUCH_EINSTELLUNGEN.md) | [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) | [Berechnungen & Kennzahlen](BERECHNUNGEN.md) | [Sensor-Referenz](SENSOR-REFERENZ.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was sind die Prognosen?](#1-was-sind-die-prognosen)
2. [Die vier Quellen — und woher sie kommen](#2-die-vier-quellen--und-woher-sie-kommen)
3. [Wo die Prognosen in der App erscheinen](#3-wo-die-prognosen-in-der-app-erscheinen)
4. [Die Physik dahinter — GTI, Ausrichtung, Wettermodell](#4-die-physik-dahinter--gti-ausrichtung-wettermodell)
5. [Lernfaktor & Korrekturprofil — wie eedc dazulernt](#5-lernfaktor--korrekturprofil--wie-eedc-dazulernt)
6. [Genauigkeits-Tracking (MAE & Bias)](#6-genauigkeits-tracking-mae--bias)
7. [Was du konfigurieren musst (Abhängigkeiten)](#7-was-du-konfigurieren-musst-abhaengigkeiten)
8. [Bekannte Probleme & Fehlerbilder](#8-bekannte-probleme--fehlerbilder)

---

## 1. Was sind die Prognosen?

Die Prognosen schätzen, **wie viel PV-Strom deine Anlage erzeugen wird** — für heute, morgen, übermorgen und auf längere Sicht. eedc verlässt sich dabei nicht auf eine einzige Quelle, sondern **vergleicht mehrere nebeneinander** und misst laufend, welche bei *deiner* Anlage am besten trifft.

Der Kern-Gedanke: Eine Prognose ist nur so gut, wie sie zur Realität passt. Deshalb stellt eedc jeder Prognose den **tatsächlich gemessenen Ertrag (IST)** gegenüber, lernt aus der Abweichung (**Lernfaktor / Korrekturprofil**) und macht die verbleibende Ungenauigkeit transparent sichtbar (**Genauigkeits-Tracking**).

> **Wichtigste Abhängigkeit vorweg:** Ohne **gemappte PV-Zähler** gibt es kein IST — und ohne IST kann eedc weder lernen noch die Genauigkeit zeigen. Die Prognosen hängen also direkt am [Energieprofil](HANDBUCH_ENERGIEPROFIL.md).

---

## 2. Die vier Quellen — und woher sie kommen

Im Prognosen-Vergleich stehen vier Spalten nebeneinander:

| Quelle | Herkunft | API-Key nötig? | Besonderheit |
|--------|----------|----------------|--------------|
| **OpenMeteo** | Wetter-API Open-Meteo (Globalstrahlung auf die geneigte Modulfläche, GTI) | nein | immer verfügbar, die Basis aller eigenen Berechnungen |
| **eedc** | OpenMeteo **× Lernfaktor** deiner Anlage | nein | die kalibrierte Default-Quelle (siehe [§5](#5-lernfaktor--korrekturprofil--wie-eedc-dazulernt)) |
| **Solcast** | Solcast-Forecast (optional) | ja, im Standalone | liefert Konfidenzband p10–p90 |
| **IST** | dein gemessener Ertrag aus dem Energieprofil | — | die Referenz, an der sich alles misst |

### 2.1 OpenMeteo (roh) — die Basis

eedc holt von Open-Meteo die **GTI** (Strahlung auf die geneigte Modulfläche), dazu Temperatur, Bewölkung, Niederschlag und Wettercode. Aktualisierung alle ~45 Minuten, kein API-Key, keine Konfiguration nötig außer den Anlagendaten. OpenMeteo ist **die Grundlage**, auf der eedc seine eigene Prognose aufbaut.

### 2.2 eedc (kalibriert) — die Default-Quelle

> **eedc = OpenMeteo × Lernfaktor.**

Die „eedc"-Spalte ist **kein eigenes Wettermodell**, sondern die OpenMeteo-Prognose, korrigiert um das, was eedc aus dem Vergleich Prognose↔IST über deine konkrete Anlage gelernt hat. Im Live-Pfad wird statt eines einzelnen Faktors sogar ein **stündliches Korrekturprofil** angewendet (siehe [§5](#5-lernfaktor--korrekturprofil--wie-eedc-dazulernt)). Diese Quelle ist der Standard.

### 2.3 Solcast — optional, dritte Meinung

Solcast ist ein spezialisierter PV-Forecast-Dienst und liefert ein Konfidenzband (p10/p50/p90). Wie eedc ihn anbindet, hängt von der Installation ab:

- **HA-Add-on:** über die Solcast-HACS-Integration (BJReplay), automatisch erkannt. **Kein** eigener Key in eedc nötig.
- **Standalone:** über die Solcast-REST-API mit eigenem `api_key` + `resource_ids` (im Sensor-Mapping hinterlegt). Achtung Free-Tier-Limit (10 Abrufe/Tag) — eedc cached entsprechend.

Solcast läuft **ohne** Lernfaktor (es ist bereits ein fertig kalibrierter Dienst). Fehlt der Key oder ist HA nicht erreichbar, fällt eedc still auf die eedc-Quelle zurück und zeigt einen Hinweistext.

### 2.4 IST — die Referenz

Der tatsächliche Ertrag kommt aus dem [Energieprofil](HANDBUCH_ENERGIEPROFIL.md): stündlich aus den PV-Stundenwerten, als Tagessumme über alle Komponenten mit Präfix `pv_`/`bkw_`. Fehlt der PV-Zähler, ist IST unvollständig (eedc markiert betroffene Stunden als Lücke) — und damit fällt die Lerngrundlage weg.

### 2.5 SFML (Solar Forecast ML) — wählbar, aber bewusst nicht im Vergleich

> **Zwei verschiedene Dinge nicht verwechseln:** Die **vier Spalten oben** sind der *Vergleich* (was steht nebeneinander zur Beurteilung). Davon getrennt gibt es die **operative Prognosequelle** — die *eine* Quelle, die deine Tagesprognose, Batteriesimulation und (geplant) den HA-Export tatsächlich speist. Diese wählst du unter **Einstellungen → Anlage → Prognosequelle**.

Als operative Prognosequelle stehen zur Wahl:

- **eedc** (Default) — OpenMeteo × Lernfaktor.
- **Solcast** — Solcast pur, ohne eedc-Korrektur.
- **SFML (Solar Forecast ML)** — die HA-Integration von Tom-HA, pur und ohne eedc-Korrektur (das ML-Modell kalibriert sich selbst). **Nur im HA-Add-on auswählbar**; im Standalone ist die Option deaktiviert. Ist SFML gewählt, aber kein HA verfügbar, fällt eedc neutral auf die eedc-Quelle zurück.

**SFML erscheint absichtlich *nicht* in der Vier-Spalten-Vergleichsmatrix.** eedc positioniert sich bewusst nicht vergleichend gegen eine spezialisierte Profi-Prognosequelle. SFML wirkt also als *aktive* Quelle (treibt deine operative Prognose), wird aber nicht Spalte an Spalte gegen OpenMeteo/eedc/Solcast gestellt. Das ist so gewollt — kein Fehler.

- **PVGIS** liefert zusätzlich die **Langfrist-**Sicht (12 Monate, Finanzprognose) aus typischen Meteojahren — eine eigene Quelle, ebenfalls kein Teil der Vier-Spalten-Matrix.

---

## 3. Wo die Prognosen in der App erscheinen

### Aussichten → Prognosen — die Vergleichssicht

Das Herzstück. Von oben nach unten:

- **KPI-Matrix:** Quellen (Spalten) × Zeiträume (Zeilen: Heute, ↳ Verbleibend, Vormittag/Nachmittag, Morgen, Übermorgen).
  - **„Verbleibend"** = bereits gemessener IST + beste Prognose für die Reststunden.
  - **„Vormittag / Nachmittag"** wird am **Sonnenhöchststand** (Solar Noon) getrennt, nicht stur um 12:00 Uhr.
- **Lernfaktor-/Restzeit-Banner:** Solange noch keine valide Lerngrundlage da ist, steht hier „benötigt mindestens 7 Tage mit IST-Ertragsdaten (X von 7 Tagen)".
- **Korrekturprofil-Stratifizierung:** stündliche Day-Ahead-Genauigkeit nach Wetterklasse.
- **Tagesverlauf-Chart:** Stundenlinien IST / eedc / Solcast / OpenMeteo (Solcast mit p10/p90-Band).
- **24-Stunden- und 7-Tage-Vergleichstabellen** mit Abweichungs-Badges.
- **Genauigkeits-Tracking** (siehe [§6](#6-genauigkeits-tracking-mae--bias)).
- **Korrekturprofil-Heatmap:** Sonnenstand (Azimut × Höhe) × Wetterklasse als Farbkacheln — rein diagnostisch.

### Aussichten → Kurzfrist / Langfrist / Trend / Finanzen

- **Kurzfrist:** 7–16-Tage-Prognose aus OpenMeteo.
- **Langfrist:** 12-Monats-Prognose aus PVGIS-Meteojahren × historischer Performance Ratio, mit Konfidenzband ±15 %.
- **Trend:** Jahresvergleich, spezifischer Ertrag, geschätzte Degradation.
- **Finanzen:** Amortisations-/Ertragsprognose (folgt der PVGIS-Langfristsicht).

### Auswertung → Energieprofil → Prognose

Die **Tagesprognose mit Batteriesimulation**: stündliche Bilanz aus PV-Prognose und typischem Verbrauchsprofil, inklusive geschätztem „Speicher voll um" / „Speicher leer um", Autarkie und Eigenverbrauch für den Tag.

> **Hinweis (geplant, noch nicht verfügbar):** Der Export von Prognosewerten **als HA-Sensoren** (z. B. `eedc_speicher_voll_um`) ist vorgesehen (#150), aber noch nicht umgesetzt. Aktuell sind diese Werte nur in der App sichtbar, nicht als HA-Entität.

---

## 4. Die Physik dahinter — GTI, Ausrichtung, Wettermodell

### 4.1 GTI statt GHI

Es gibt zwei Strahlungsgrößen:

- **GHI** (Globalstrahlung) — auf die *horizontale* Fläche.
- **GTI** (Global Tilted Irradiance) — auf die *geneigte Modulfläche*, also das, was deine Panels tatsächlich sehen.

eedc rechnet mit **GTI**. Der Grund ist im Winter dramatisch: Bei steilen Modulen und tiefer Sonne kann GTI das 2–3-fache von GHI betragen. Rechnet man (wie früher) mit GHI, kam ein **physikalisch unmöglicher** „theoretischer Ertrag" heraus und die Performance Ratio sprang über 1,0 (z. B. PR 2,16 statt 0,85 an einem klaren Wintertag). Seit GTI ist die PR wieder physikalisch sinnvoll.

Die Ertragsformel (vereinfacht):

```
Ertrag [kWh] = (GTI [Wh/m²] / 1000) × kWp × (1 − Systemverluste)
               × Temperaturkorrektur × ggf. Schneeabschlag
```

Systemverluste sind standardmäßig 14 %; über 25 °C Modultemperatur fällt der Ertrag um ~0,4 %/°C.

### 4.2 Ausrichtung & Neigung

Damit die GTI-Projektion stimmt, braucht eedc pro PV-String **Azimut und Neigung**. Konvention (wie PVGIS/Open-Meteo):

> **0° = Süd, −90° = Ost, +90° = West, 180° = Nord.**

Fehlen die Werte, nimmt eedc **Süd / 35°** als Default an — das funktioniert, erzeugt bei abweichender realer Ausrichtung aber einen **systematischen Fehler**. Bei Ost-West- oder Mehrfach-Strings rechnet eedc je Orientierungsgruppe getrennt und kombiniert kWp-gewichtet.

### 4.3 Wettermodell-Kaskade

eedc kann verschiedene Open-Meteo-Modelle nutzen (`auto` = bestes Match, oder gezielt ICON-D2/EU, ECMWF, MeteoSwiss …). Modelle mit kurzem Horizont (z. B. ICON-D2 = 2 Tage) werden automatisch durch ein längerreichendes Fallback-Modell ergänzt, damit die Mehrtagessicht nicht abreißt. Das Modell wählst du pro Anlage.

---

## 5. Lernfaktor & Korrekturprofil — wie eedc dazulernt

Das ist der Teil, der eedc von einer reinen Wetter-API unterscheidet.

### 5.1 Der Lernfaktor (skalar)

eedc vergleicht über mehrere Tage Prognose und IST und bildet einen Korrekturfaktor `Σ(IST) / Σ(Prognose)`. Damit das robust ist:

- Es zählen **nur Tage mit Prognose > 0,5 kWh *und* IST > 0,5 kWh** (Nacht/Schlechtwetter raus).
- IST = nur echte PV-Erzeugung (Präfixe `pv_`/`bkw_`) — Batterie-Entladung oder WP-Verbrauch werden **nicht** mitgezählt (sonst sähe die Prognose künstlich besser aus).
- **Saisonale Kaskade:** bevorzugt gleicher Kalendermonat (≥ 15 Tage), sonst gleiches Quartal, sonst rollierend die letzten 30 Tage (≥ 7 Tage). Vorher: kein Faktor.
- Der Faktor ist auf **[0,5 ; 1,3]** begrenzt und ändert sich höchstens einmal pro Tag.

> Deshalb das **„7 von X Tagen"-Banner**: Vor 7 verwertbaren Tagen gibt es keinen Lernfaktor — die eedc-Spalte bleibt dann leer und zeigt einfach die OpenMeteo-Basis.

### 5.2 O1 + O2 — die heute aktive Kalibrierung

Der einfache Skalar gewichtet alle Tage gleich. eedc nutzt **live** eine verbesserte Variante (intern „O1+O2"):

- **O1 (Recency):** Tage jünger als 30 Tage zählen stärker (×1,3) — die Anlage „von heute" wiegt mehr als die von vor drei Monaten.
- **O2 (Trim-Mean):** die extremsten 10 % der Tages-Verhältnisse oben und unten werden verworfen — einzelne Ausreißertage (Verschattung, Sensorhänger) verzerren den Faktor nicht.

> **Hinweis:** Ältere Konzept-Dokumente beschreiben O1+O2 als „nur Diagnose, live läuft der alte Skalar". Das ist überholt — **O1+O2 ist die aktive Live-Kalibrierung** (mit Fallback auf den alten Skalar, falls O1+O2 mal keinen Wert liefert).

### 5.3 Das Korrekturprofil (Sonnenstand × Wetter)

Ein einzelner Faktor korrigiert nur die *Tagessumme*, nicht den *Tagesgang*. Wenn OpenMeteo z. B. systematisch vormittags zu hoch und nachmittags zu niedrig liegt, hilft ein Skalar nicht. Dafür baut eedc ein **mehrdimensionales Korrekturprofil**:

- Für jede Stunde wird der **Sonnenstand** (Azimut/Höhe in 10°-Bins) und die **Wetterklasse** (`klar` < 30 % Bewölkung, `diffus` > 70 %, sonst `wechselhaft`) bestimmt.
- Pro Kombination lernt eedc einen eigenen Korrekturfaktor (`Σ IST / Σ Prognose`, begrenzt auf [0,5 ; 1,3]).
- Im Live-Pfad gilt eine **Fallback-Kaskade**: erst das feine Sonnenstand-×-Wetter-Profil, dann ein gröberes Sonnenstand-Profil, dann der Skalar-Lernfaktor — je nachdem, wie viele Datenpunkte schon vorliegen.

Die **Korrekturprofil-Heatmap** im Prognosen-Tab visualisiert genau das (rot = Prognose war zu hoch, grün = zu niedrig, grau = passt).

---

## 6. Genauigkeits-Tracking (MAE & Bias)

eedc trennt zwei Fehlerarten — das ist entscheidend für die Deutung:

| Kennzahl | Bedeutung |
|----------|-----------|
| **MAE** (Mean Absolute Error) | wie groß die **Streuung** ist — im Mittel daneben, egal in welche Richtung. |
| **Bias / MBE** (Mean Bias Error) | der **systematische** Versatz. **Positiv = Prognose war zu hoch**, negativ = zu niedrig. |

Faustregel für die Deutung:

- **|Bias| ≪ MAE** → die Prognose streut, aber im Mittel stimmt sie → reines Wetterrauschen, ein Lernfaktor hilft kaum.
- **|Bias| ≈ MAE** → systematischer Versatz → genau hier wirkt der Lernfaktor / das Korrekturprofil.

Der Bias ist in der UI **neutral grau** gefärbt: ein Vorzeichen ist eine Information, keine „schlechte Note". Die Tabelle zeigt MAE und Bias für OpenMeteo, eedc und Solcast nebeneinander; sie bleibt auch dann stabil und lesbar, wenn für eedc noch kein Lernfaktor vorliegt (dann bleibt nur die eedc-Spalte leer).

Im Diagnose-Modus zeigt eedc zusätzlich die **Asymmetrie** — getrennt, wie stark und an wie vielen Tagen die Prognose *über* bzw. *unter* dem IST lag. So wird z. B. ein reiner Vormittags-Bias sichtbar.

---

## 7. Was du konfigurieren musst (Abhängigkeiten)

| Voraussetzung | Wofür | Fehlt → |
|---------------|-------|---------|
| **Koordinaten** (Breite/Länge) | jede OpenMeteo-/eedc-/PVGIS-Prognose | keine Prognose; Daten-Checker meldet es |
| **PV-Leistung (kWp)** | jede Ertragsumrechnung, Performance Ratio | keine Prognose; Daten-Checker meldet „Anlagenleistung fehlt" |
| **Ausrichtung & Neigung je String** | korrekte GTI-Projektion | Default Süd/35° → systematischer Bias |
| **Systemverluste** (PVGIS-Eintrag) | Ertragshöhe | Default 14 %; bei PR > 1,1 Hinweis im Daten-Checker |
| **Gemappte PV-Zähler (IST)** | IST-Spalte, Lernfaktor, Korrekturprofil, Genauigkeit | alles Lern-/Vergleichsbezogene bleibt leer |
| **≥ 7 Tage mit IST > 0,5 kWh** | eedc-Lernfaktor | eedc-Spalte zeigt „—", Restzeit-Banner |
| **Solcast-Key / HA-Integration** (optional) | Solcast-Spalte | still Fallback auf eedc + Hinweistext |
| **Wettermodell** (pro Anlage) | Mehrtagessicht | `auto` = sinnvoller Default |

Kurz: **Stammdaten (kWp, Koordinaten, Ausrichtung) + gemappte PV-Zähler** sind die Pflicht. Solcast ist Kür.

---

## 8. Bekannte Probleme & Fehlerbilder

| Symptom | Ursache | Was tun |
|---------|---------|---------|
| **eedc-Spalte leer / „X von 7 Tagen"** | noch keine 7 verwertbaren IST-Tage | abwarten — eedc zeigt solange die OpenMeteo-Basis. Prüfen, dass PV-Zähler gemappt ist. |
| **Prognose systematisch zu hoch/niedrig** | falsche Ausrichtung/Neigung, oder Lernfaktor noch im Aufbau | Ausrichtung/Neigung je String korrekt pflegen; Bias im Genauigkeits-Tracking beobachten — das Korrekturprofil zieht nach. |
| **Vormittags daneben, Tagessumme stimmt** | OpenMeteo-Tagesgang-Bias; ein Skalar korrigiert nur die Summe | das Sonnenstand-×-Wetter-Korrekturprofil greift hier — sichtbar in der Heatmap und der Asymmetrie-Diagnose. |
| **Performance Ratio > 1** | nur bei alten Versionen (GHI statt GTI) | auf aktuelle Version updaten; danach betroffene Tage neu aggregieren. |
| **Prognose-/IST-Linien um eine Stunde versetzt** | Slot-Versatz zwischen Quellen (Backward-Konvention) | in aktuellen Versionen einheitlich; nach Update auf v3.20.0 ggf. einmal den Verlauf neu berechnen. |
| **Solcast-Spalte fehlt** | kein Key (Standalone) / HA-Integration nicht da / Tageslimit erreicht | Status-Hinweis im Tab beachten; Key + Resource-IDs im Sensor-Mapping prüfen. |
| **IST-Lücken im Tagesverlauf** | PV-Stundenwert fehlt (kein Zähler / HA-Neustart) | betroffenen Tag über die [Reparatur-Werkbank](HANDBUCH_ENERGIEPROFIL.md#6-die-reparatur-werkzeuge) neu aggregieren. |
| **Keine Prognose, „keine Koordinaten"** | Standort fehlt in den Stammdaten | Koordinaten in den Anlagen-Stammdaten eintragen. |

### Robustheit

Die Vergleichssicht ruft alle Quellen **parallel** ab. Hängt eine Quelle (Solcast-Timeout, OpenMeteo langsam), bricht nicht der ganze Tab ab — die betroffene Spalte bleibt einfach leer, die übrigen werden angezeigt.

> **Zusammenhang im Blick behalten:** Prognose-Probleme haben oft ihre Wurzel im IST. Wenn die Genauigkeit unerklärlich schlecht ist, lohnt der Blick ins [Energieprofil](HANDBUCH_ENERGIEPROFIL.md) und den [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) — stimmt das IST nicht, kann auch die beste Prognose nicht „richtig" aussehen.
