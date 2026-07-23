
# eedc Handbuch — Prognosen

**Version 4.0** | Stand: 2026-07-25

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Energieprofil](HANDBUCH_ENERGIEPROFIL.md) | [Teil III: Einstellungen & Datenquellen](HANDBUCH_EINSTELLUNGEN.md) | [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) | [Berechnungen & Kennzahlen](BERECHNUNGEN.md) | [Sensor-Referenz](SENSOR-REFERENZ.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was sind die Prognosen?](#1-was-sind-die-prognosen)
2. [Die vier Quellen — und woher sie kommen](#2-die-vier-quellen--und-woher-sie-kommen)
3. [Wo die Prognosen in der App erscheinen](#3-wo-die-prognosen-in-der-app-erscheinen)
4. [Die Physik dahinter — GTI, Ausrichtung, Wettermodell](#4-die-physik-dahinter--gti-ausrichtung-wettermodell)
5. [Lernfaktor & Korrekturprofil — wie eedc dazulernt](#5-lernfaktor--korrekturprofil--wie-eedc-dazulernt)
6. [Genauigkeits-Tracking (MAE & Bias)](#6-genauigkeits-tracking-mae--bias)
7. [Was du konfigurieren musst (Abhängigkeiten)](#7-was-du-konfigurieren-musst-abhängigkeiten)
8. [Bekannte Probleme & Fehlerbilder](#8-bekannte-probleme--fehlerbilder)

---

## 1. Was sind die Prognosen?

Die Prognosen schätzen, **wie viel PV-Strom deine Anlage erzeugen wird** — für heute, morgen, übermorgen und auf längere Sicht. eedc verlässt sich dabei nicht auf eine einzige Quelle, sondern **vergleicht mehrere nebeneinander** und misst laufend, welche bei *deiner* Anlage am besten trifft.

Der Kern-Gedanke: Eine Prognose ist nur so gut, wie sie zur Realität passt. Deshalb stellt eedc jeder Prognose den **tatsächlich gemessenen Ertrag (IST)** gegenüber, lernt aus der Abweichung (**Lernfaktor / Korrekturprofil**) und macht die verbleibende Ungenauigkeit transparent sichtbar (**Genauigkeits-Tracking**).

> **Wichtigste Abhängigkeit vorweg:** Ohne **zugeordnete PV-Zähler** gibt es kein IST — und ohne IST kann eedc weder lernen noch die Genauigkeit zeigen. Die Prognosen hängen also direkt am [Energieprofil](HANDBUCH_ENERGIEPROFIL.md). Die Feld-Zuordnung pflegst du unter [Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung).

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

> **Ein Wert überall.** Die „PV-Tagesprognose heute" (und Rest heute, morgen/übermorgen, Vor-/Nachmittag, Stundenprofil) wird über **einen** kanonischen Rechenweg gebildet und ist deshalb auf **allen** Sichten identisch — Cockpit/Live, Aussicht, Auswertungen, die „eedc"-Spalte im Prognosen-Vergleich, der gespeicherte Tageswert **und** die MQTT-Sensoren. Bei mehreren Dachflächen (z. B. Ost/West) wird jede Orientierung getrennt gerechnet und dann summiert (Multi-String); die Korrektur sitzt **pro Stunden-Slot auf der Energie** (Tageswert = Summe der Stunden-Slots). Der Wert **rollt** über den Tag mit OpenMeteo mit — aber überall **synchron**, nicht mehr je Seite anders.

### 2.3 Solcast — optional, dritte Meinung

Solcast ist ein spezialisierter PV-Forecast-Dienst und liefert ein Konfidenzband (p10/p50/p90). Wie eedc ihn anbindet, hängt von der Installation ab:

- **HA-Add-on:** über die Solcast-HACS-Integration (BJReplay), automatisch erkannt. **Kein** eigener Key in eedc nötig.
- **Standalone:** über die Solcast-REST-API mit eigenem `api_key` + `resource_ids`, hinterlegt in den Anlagenstammdaten ([Einstellungen → Stammdaten → Solarprognose](HANDBUCH_EINSTELLUNGEN.md#23-solarprognose)). Achtung Free-Tier-Limit (10 Abrufe/Tag) — eedc cached entsprechend.

Solcast läuft **ohne** Lernfaktor (es ist bereits ein fertig kalibrierter Dienst). Fehlt der Key oder ist HA nicht erreichbar, fällt eedc still auf die eedc-Quelle zurück und zeigt einen Hinweistext.

### 2.4 IST — die Referenz

Der tatsächliche Ertrag kommt aus dem [Energieprofil](HANDBUCH_ENERGIEPROFIL.md): stündlich aus den PV-Stundenwerten, als Tagessumme über alle Komponenten mit Präfix `pv_`/`bkw_`. Fehlt der PV-Zähler, ist IST unvollständig (eedc markiert betroffene Stunden als Lücke) — und damit fällt die Lerngrundlage weg.

### 2.5 SFML (Solar Forecast ML) — wählbar, aber bewusst nicht im Vergleich

> **Zwei verschiedene Dinge nicht verwechseln:** Die **vier Spalten oben** sind der *Vergleich* (was steht nebeneinander zur Beurteilung). Davon getrennt gibt es die **operative Prognosequelle** — die *eine* Quelle, die deine Tagesprognose, Batteriesimulation und den HA-Export tatsächlich speist. Diese wählst du unter **Einstellungen → Stammdaten → Anlage** im Feld **„PV-Prognose-Quelle für diese Anlage"**.

Als operative Prognosequelle stehen zur Wahl:

- **eedc-optimiert** (Default) — OpenMeteo × Lernfaktor.
- **Solcast** (pur, ohne eedc-Korrektur).
- **Solar Forecast ML (SFML)** — die HA-Integration von Tom-HA, pur und ohne eedc-Korrektur (das ML-Modell kalibriert sich selbst). **Nur im HA-Add-on auswählbar**; im Standalone ist die Option deaktiviert. Ist SFML gewählt, aber kein HA verfügbar, fällt eedc neutral auf die eedc-Quelle zurück.

**SFML erscheint absichtlich *nicht* in der Vier-Spalten-Vergleichsmatrix.** eedc positioniert sich bewusst nicht vergleichend gegen eine spezialisierte Profi-Prognosequelle. SFML wirkt also als *aktive* Quelle (treibt deine operative Prognose), wird aber nicht Spalte an Spalte gegen OpenMeteo/eedc/Solcast gestellt. Das ist so gewollt — kein Fehler.

> **Echte Stundenauflösung:** Ist SFML als Quelle gewählt, nutzt eedc SFMLs **eigenes Stundenprofil** (bis zu 3 Tage, stündlich — aus dem evcc-Prognose-Sensor `…_evcc_solar_prognose`). Die SFML-Kurve im Tagesverlauf zeigt also SFMLs eigene Form, nicht die über die OpenMeteo-Strahlungskurve „verschmierte" Tagessumme. Fehlt dieser Sensor, fällt eedc auf das Tagesprofil `prognose_heute` (24 h) und notfalls auf die alte GTI-Verteilung zurück. (Das ist reine Treue zur selbstgewählten Quelle, **kein** Genauigkeits-Vergleich.)

- **PVGIS** liefert zusätzlich die **Langfrist-**Sicht (12 Monate, Finanzprognose) aus typischen Meteojahren — eine eigene Quelle, ebenfalls kein Teil der Vier-Spalten-Matrix.

<!-- [T20-Review] Cross-Doc-Konsistenz: HANDBUCH_EINSTELLUNGEN.md §2.1 beschreibt dasselbe Feld
     als „Prognose-Basis (OpenMeteo/Solcast); SFML im Code als künftige Erweiterung vorbereitet".
     Der GEBAUTE Code (frontend/src/components/forms/AnlageForm.tsx:222-230, Feld `prognose_quelle`)
     bietet real die drei operativen Optionen eedc / solcast / sfml (sfml nur im HA-Add-on,
     sonst disabled). Beide Formulierungen im Flip-Push-Zug angleichen — hier steht die
     code-genaue Fassung. -->

---

## 3. Wo die Prognosen in der App erscheinen

In der neuen Oberfläche sind die Prognose-Sichten nach dem Grundsatz **„Vorschau vorwärts / Bewertung gegen IST"** getrennt:

- **Cockpit → Aussicht** — die *vorwärtsgerichtete* Sicht (heute bis Jahresprognose).
- **Auswertungen → Prognose** — die *Vergleichs- und Genauigkeits-Fläche* (mehrere Quellen gegen IST).

### Cockpit → Aussicht — die Vorschau

Die [Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) bündelt alle vorwärtsgerichteten Analysen auf einer Seite; über einen **Horizont-Selektor** wählst du, wie weit du blickst:

- **Kurzfristig (7–14 Tage):** tägliche Erzeugungsschätzung aus OpenMeteo, kalibriert mit dem eedc-Lernfaktor, mit Wettersymbolen und Datenquelle-Kürzel je Tag (MS/D2/EU/EC/BM). Ist **SFML** als Quelle konfiguriert, erscheint eine zweite KI-basierte Ertragslinie.
- **Langfristig:** PVGIS-basierte 12-Monats-Prognose (Erwartungswerte/TMY) mit historischer Performance Ratio (GTI-basiert) und monatlicher Aufschlüsselung.
- **Degradation:** geschätzter Leistungsrückgang pro Jahr — primär aus vollständigen Jahren (12 Monate), Fallback über TMY-Auffüllung für unvollständige Jahre.
- **Tagesprognose mit Batteriesimulation:** die stündliche Bilanz aus PV-Prognose und typischem Verbrauchsprofil — inklusive geschätztem „Speicher voll um" / „Speicher leer um", Autarkie und Eigenverbrauch für den Tag. eedc wählt Prognosebasis und Wetterquelle automatisch; die gewählte Basis steht als Beschriftung an der Karte.

### Auswertungen → Prognose — die Vergleichssicht

Die [Prognose-Auswertung](HANDBUCH_BEDIENUNG.md#43-prognose-genauigkeit-gegen-ist) ist das Herzstück der Bewertung. Von oben nach unten:

- **Kennzahl-Matrix:** Quellen (Spalten) × Zeiträume (Zeilen: Heute, ↳ Verbleibend, Vormittag/Nachmittag, Morgen, Übermorgen).
  - **„Verbleibend"** = bereits gemessener IST + beste Prognose für die Reststunden.
  - **„Vormittag / Nachmittag"** wird am **Sonnenhöchststand** (Solar Noon) getrennt, nicht stur um 12:00 Uhr.
- **Lernfaktor-/Restzeit-Banner:** Solange noch keine valide Lerngrundlage da ist, steht hier „benötigt mindestens 7 Tage mit IST-Ertragsdaten (X von 7 Tagen)".
- **Korrekturprofil-Stratifizierung:** stündliche Day-Ahead-Genauigkeit nach Wetterklasse.
- **Tagesverlauf-Chart:** Stundenlinien IST / eedc / Solcast / OpenMeteo (Solcast mit p10/p90-Band).
- **24-Stunden- und 7-Tage-Vergleichstabellen** mit Abweichungs-Badges.
- **Genauigkeits-Tracking** (siehe [§6](#6-genauigkeits-tracking-mae--bias)).
- **Korrekturprofil-Heatmap:** Sonnenstand (Azimut × Höhe) × Wetterklasse als Farbkacheln — rein diagnostisch.

### Auswertungen → Finanzen — die Ertragsprognose

Die frühere „Aussichten → Finanzen"-Sicht ist in die [Finanz-Auswertung](HANDBUCH_BEDIENUNG.md#41-finanzen) gezogen: Amortisations-/Ertragsprognose auf Basis der PVGIS-Langfristsicht, jetzt zeitraum-fähig neben dem Finanz-Abschluss (T-Konto).

> **Hinweis (geplant):** Der Export der Tagesprognose als HA-Sensoren (`eedc_prognose_*`, `eedc_speicher_voll_um`) ist umgesetzt und läuft über [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export) — Details in der [Sensor-Referenz §8a/§11](SENSOR-REFERENZ.md#8a-eedc-pv-prognose-nach-ha-exportieren-mqtt--ha-sensoren).

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

Fehlen die Werte, nimmt eedc **Süd / 35°** als Default an — das funktioniert, erzeugt bei abweichender realer Ausrichtung aber einen **systematischen Fehler**. Bei Ost-West- oder Mehrfach-Strings rechnet eedc je Orientierungsgruppe getrennt und kombiniert kWp-gewichtet. Ausrichtung und Neigung pflegst du **pro PV-Modul** unter [Einstellungen → Komponenten](HANDBUCH_EINSTELLUNGEN.md#34-typ-spezifische-parameter) (nicht mehr an der Anlage).

### 4.3 Wettermodell-Kaskade

eedc kann verschiedene Open-Meteo-Modelle nutzen (`auto` = bestes Match, oder gezielt ICON-D2/EU, ECMWF, MeteoSwiss …). Modelle mit kurzem Horizont (z. B. ICON-D2 = 2 Tage) werden automatisch durch ein längerreichendes Fallback-Modell ergänzt, damit die Mehrtagessicht nicht abreißt. Das Modell wählst du pro Anlage unter [Einstellungen → Stammdaten → Anlage](HANDBUCH_EINSTELLUNGEN.md#21-anlage) („Modell für Solar-Prognose").

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

Die **Korrekturprofil-Heatmap** in der Prognose-Auswertung visualisiert genau das (rot = Prognose war zu hoch, grün = zu niedrig, grau = passt).

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

> **Welcher Prognosewert geht in die Genauigkeit ein?** Der **Anzeige**-Wert rollt über den Tag mit OpenMeteo mit — für den Tagesabschluss wäre ein Zwischenstand vom Mittag aber irreführend. Das Genauigkeits-Tracking nutzt deshalb einen **eigenen, eingefrorenen Endwert**: er rollt mit, bis OpenMeteo für den Tag (nach Sonnenuntergang) konvergiert ist, und wird dann festgeschrieben. So vergleicht das Ranking IST immer gegen den *fertigen* Tagesforecast, während die Anzeige rollend bleibt.

---

## 7. Was du konfigurieren musst (Abhängigkeiten)

| Voraussetzung | Wofür | Fehlt → |
|---------------|-------|---------|
| **Koordinaten** (Breite/Länge) | jede OpenMeteo-/eedc-/PVGIS-Prognose | keine Prognose; Daten-Checker meldet es |
| **PV-Leistung (kWp)** | jede Ertragsumrechnung, Performance Ratio | keine Prognose; Daten-Checker meldet „Anlagenleistung fehlt" |
| **Ausrichtung & Neigung je String** | korrekte GTI-Projektion | Default Süd/35° → systematischer Bias |
| **Systemverluste** (Solarprognose-Eintrag) | Ertragshöhe | Default 14 %; bei PR > 1,1 Hinweis im Daten-Checker |
| **Zugeordnete PV-Zähler (IST)** | IST-Spalte, Lernfaktor, Korrekturprofil, Genauigkeit | alles Lern-/Vergleichsbezogene bleibt leer |
| **≥ 7 Tage mit IST > 0,5 kWh** | eedc-Lernfaktor | eedc-Spalte zeigt „—", Restzeit-Banner |
| **Solcast-Key / HA-Integration** (optional) | Solcast-Spalte | still Fallback auf eedc + Hinweistext |
| **Wettermodell** (pro Anlage) | Mehrtagessicht | `auto` = sinnvoller Default |

Kurz: **Stammdaten (kWp, Koordinaten, Ausrichtung) + zugeordnete PV-Zähler** sind die Pflicht. Solcast ist Kür. Stammdaten pflegst du unter [Einstellungen → Stammdaten](HANDBUCH_EINSTELLUNGEN.md#2-stammdaten), die Zähler-Zuordnung unter [Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung).

---

## 8. Bekannte Probleme & Fehlerbilder

| Symptom | Ursache | Was tun |
|---------|---------|---------|
| **eedc-Spalte leer / „X von 7 Tagen"** | noch keine 7 verwertbaren IST-Tage | abwarten — eedc zeigt solange die OpenMeteo-Basis. Prüfen, dass der PV-Zähler zugeordnet ist. |
| **Prognose systematisch zu hoch/niedrig** | falsche Ausrichtung/Neigung, oder Lernfaktor noch im Aufbau | Ausrichtung/Neigung je String korrekt pflegen; Bias im Genauigkeits-Tracking beobachten — das Korrekturprofil zieht nach. |
| **Vormittags daneben, Tagessumme stimmt** | OpenMeteo-Tagesgang-Bias; ein Skalar korrigiert nur die Summe | das Sonnenstand-×-Wetter-Korrekturprofil greift hier — sichtbar in der Heatmap und der Asymmetrie-Diagnose. |
| **Performance Ratio > 1** | nur bei alten Versionen (GHI statt GTI) | auf aktuelle Version updaten; danach betroffene Tage neu aggregieren. |
| **Prognose-/IST-Linien um eine Stunde versetzt** | Slot-Versatz zwischen Quellen (Backward-Konvention) | in aktuellen Versionen einheitlich; nach Update auf v3.20.0 ggf. einmal den Verlauf neu berechnen. |
| **Solcast-Spalte fehlt** | kein Key (Standalone) / HA-Integration nicht da / Tageslimit erreicht | Status-Hinweis im Tab beachten; Key + Resource-IDs unter [Einstellungen → Stammdaten → Solarprognose](HANDBUCH_EINSTELLUNGEN.md#23-solarprognose) prüfen. |
| **IST-Lücken im Tagesverlauf** | PV-Stundenwert fehlt (kein Zähler / HA-Neustart) | betroffenen Tag über die [Reparatur-Werkbank](HANDBUCH_ENERGIEPROFIL.md#4-reparatur--pflege) neu aggregieren. |
| **Keine Prognose, „keine Koordinaten"** | Standort fehlt in den Stammdaten | Koordinaten unter [Einstellungen → Stammdaten → Anlage](HANDBUCH_EINSTELLUNGEN.md#21-anlage) eintragen. |

### Robustheit

Die Vergleichssicht ruft alle Quellen **parallel** ab. Hängt eine Quelle (Solcast-Timeout, OpenMeteo langsam), bricht nicht der ganze Tab ab — die betroffene Spalte bleibt einfach leer, die übrigen werden angezeigt.

> **Zusammenhang im Blick behalten:** Prognose-Probleme haben oft ihre Wurzel im IST. Wenn die Genauigkeit unerklärlich schlecht ist, lohnt der Blick ins [Energieprofil](HANDBUCH_ENERGIEPROFIL.md) und den [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) — stimmt das IST nicht, kann auch die beste Prognose nicht „richtig" aussehen.

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
