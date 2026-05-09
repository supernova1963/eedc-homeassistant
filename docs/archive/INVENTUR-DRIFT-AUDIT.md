# Drift-Audit Investitions-Berechnungen — Phase 1 Inventur

> Stand: 2026-05-01 · Anlass: Zweiter extremer Drift in Folge (v3.25.0 Investitions-Parameter, v3.25.x WP-Wirtschaftlichkeit / #178). Statt weiter Whack-a-mole pro Forum-Issue eine systematische Audit aller Berechnungen.

## Was ist hier drin

Pro Domäne:
1. **Render-Stellen-Matrix** — alle UI-Stellen die einen Wirtschaftlichkeits-Wert anzeigen + zugrunde-liegende Backend-Quelle
2. **Formel-Vergleich** — welche Formel wird wo verwendet, mit welchen Defaults
3. **Drifts** — Stellen mit abweichender Formel oder hartcodierten/falschen Werten
4. **User-Impact** — was sieht der User falsch
5. **Fix-Vorschlag** — Single Source of Truth (SoT) Helper, kanonische Defaults

## Vorgehen

- Render-Stelle = Frontend-Komponente die einen €/€-pro-X-Wert anzeigt
- Compute-Stelle = Backend-Funktion oder TS-Helper der den Wert berechnet
- Default-Quelle = `eedc/backend/core/investition_parameter.py` + `eedc/frontend/src/lib/investitionParameter.ts` (kanonisch seit v3.25.0)
- Hartcodierte Konstante = magische Zahl direkt im Berechnungs-Code (z.B. `0.9`, `10.0`, `0.08`)

---

## Domäne A1 — Wärmepumpen-Wirtschaftlichkeit (#178 Trigger)

### Render-Stellen-Matrix

| # | Render-Stelle | Backend-Quelle | Wirkungsgrad | Gaspreis-Default | Gaspreis-Override (monatlich) | Strompreis | PV-Anteil-Annahme |
|---|---|---|---|---|---|---|---|
| 1 | Cockpit→Monatsbericht | `aktueller_monat.py:737` | `/0.9` hart | `10.0ct` hart | ❌ ignoriert `Monatsdaten.gaspreis_cent_kwh` | `wp_tarif` mit Fallback `netzbezug_preis` | 0% (100% Netzbezug) |
| 2 | Cockpit→Übersicht | `cockpit/uebersicht.py:294-295` | `/0.9` hart | `10.0ct` hart | ❌ ignoriert | wie #1 | 0% |
| 3 | Cockpit→Wärmepumpe-Detail | `investitionen.py:1500-1508` | **kein** | `params.gas_kwh_preis_cent` def. **12** | ❌ ignoriert | `strompreis_cent` (allgemein, nicht WP) | 0% |
| 4 | Auswertungen→Komponenten | `KomponentenTab.tsx:368` | **kein** | `0.08€` hart | ❌ ignoriert | `strompreis.netzbezug` (allgemein) | 0% |
| 5 | Aussichten→Bisherige | `aussichten.py:1149-1161` | `/0.90` Gas / `/0.85` Öl | `params.alter_preis_cent_kwh` def. **12** (kanon.) | ✅ `Monatsdaten.gaspreis_cent_kwh` | `wp_tarif` mit Fallback | **50%** hart (`wp_netz_anteil = 0.5`) |
| 6 | Aussichten→Jahres-Prognose | `aussichten.py:1340-1349` | wie #5 | wie #5 | gemittelt aus historischen | wie #5 | **50%** hart |
| 7 | PDF-Jahresbericht | `pdf_operations.py:419-446` | `/0.90` Gas / `/0.85` Öl | `params.alter_preis_cent_kwh` def. **12** | ✅ gemittelt | wie #5 | nicht modelliert (verwendet `wp_stromkosten`) |
| 8 | HA-Export Bilanz | `ha_export.py:244-280` | wie #5 | wie #5 | ✅ pro Monat | `netzbezug_preis_cent` (allgemein) | **50%** hart |
| 9 | HA-Sensor `wp_ersparnis_euro` | `ha_export.py:614-639` | `0.85/0.90` | wie #5 | ✅ pro Monat | `netzbezug_preis` (allgemein) | **0%** (100% Netzbezug!) |

### Drifts (geordnet nach User-Impact)

🔥🔥🔥 **Auswertungen→Komponenten — KomponentenTab.tsx:368**
- Hartcodierter Gaspreis 8 ct/kWh, kein Wirkungsgrad
- detLAN-Beispiel (#178): Anzeige 7€ statt 61€ (–54€)
- **Worst case** der ganzen Audit

🔥🔥 **Cockpit→Wärmepumpe-Detail — investitionen.py:1505**
- Falscher Param-Key `gas_kwh_preis_cent` (existiert nicht im Schema → fällt auf Default 12 zurück)
- Kein Wirkungsgrad-Faktor
- detLAN-Beispiel (#178): Anzeige 77€ statt 61€ (+16€)

🔥 **Cockpit→Monatsbericht / Cockpit→Übersicht — aktueller_monat.py:737, cockpit/uebersicht.py:295**
- Hartcodierter Gaspreis 10 ct (kanon ist 12 ct)
- Ignoriert `Monatsdaten.gaspreis_cent_kwh` (User-pflegbar pro Monat!)
- Ignoriert `params.alter_preis_cent_kwh` (User-pflegbar pro Investition)
- detLAN-Beispiel: 61€ — passt nur zufällig zu seiner Konfiguration; bei Usern mit gepflegten Gaspreisen weicht es ab

🟡 **PV-Anteil-Annahme inkonsistent über Stellen**
- 0% (Stellen #1-4, #9): rechnet WP-Strom als 100% Netzbezug, ignoriert dass Tageswerte zeigen wie viel WP-Strom durch PV gedeckt war
- 50% hart (Stellen #5, #6, #8): pauschale 50/50-Annahme
- Korrekt wäre: tatsächlicher Anteil aus `TagesEnergieProfil` oder `InvestitionMonatsdaten.pv_anteil_kwh`

🟡 **WP-Tarif vs. Allgemein-Tarif inkonsistent**
- Stellen #1, #2, #5, #6, #7: lesen `tarife.get("waermepumpe")` mit Fallback (richtig)
- Stellen #3, #4, #8, #9: nehmen direkt `netzbezug_preis_cent` (allgemein) — verfehlen den separaten WP-Stromtarif (Wärmestrom-Tarif ist oft günstiger)

### Soll-Formel

```
wp_ersparnis = (wp_waerme / wirkungsgrad * gaspreis_cent - wp_strom * wp_strompreis_cent) / 100
                                           |
   wirkungsgrad = 0.90 (Gas) / 0.85 (Öl) — kanonisch wie aussichten.py
   gaspreis_cent = Monatsdaten.gaspreis_cent_kwh (monatlich) ODER params.alter_preis_cent_kwh ODER 12
   wp_strom = Strom × (1 - pv_anteil)  — tatsächlicher PV-Anteil aus Daten, nicht hartcodiert
   wp_strompreis_cent = wp_tarif.netzbezug_arbeitspreis_cent_kwh ODER allgemein_tarif (Fallback)
```

### Fix-Vorschlag

**Backend-Helper** `eedc/backend/services/wp_wirtschaftlichkeit.py`:
```python
@dataclass
class WPErsparnis:
    ersparnis_euro: float
    alte_heizung_kosten_euro: float
    wp_kosten_euro: float
    pv_anteil_prozent: float | None  # informativ

async def berechne_wp_ersparnis(
    wp: Investition,
    wp_waerme_kwh: float,
    wp_strom_kwh: float,
    wp_pv_strom_kwh: float | None,    # aus Daten, optional
    tarife: dict[str, Tarif],
    monats_gaspreis_cent: float | None = None,  # für aktuellen Monat
) -> WPErsparnis: ...
```

**Frontend-Helper** `eedc/frontend/src/lib/wpWirtschaftlichkeit.ts` mit gleicher Logik (für KomponentenTab — der hat keinen direkten Backend-Endpoint, rechnet aus Monats-Aggregaten).

**Alternativ pragmatisch:** Backend-Endpoint `/cockpit/komponenten/{anlage_id}/waermepumpen` ergänzen um `ersparnis_euro` (analog zum vorhandenen `/investitionen/zusammenfassung`), KomponentenTab nutzt dann den Backend-Wert statt selbst zu rechnen — eliminiert Frontend-Duplikat.



## Domäne A2 — E-Auto / Wallbox / V2H

### Render-Stellen-Matrix

| # | Render-Stelle | Backend-Quelle | Verbrauch L/100km | Benzinpreis €/L | Strompreis-Quelle |
|---|---|---|---|---|---|
| 1 | Cockpit→Übersicht | `cockpit/uebersicht.py:305-308` | **`7`** hart | **`1.80`** hart | `wallbox_preis_cent` (mit Fallback) |
| 2 | Cockpit→Monatsbericht (Σ) | `aktueller_monat.py:752` | **`7`** hart | **`1.80`** hart | `wallbox_preis_cent` |
| 3 | Cockpit→Monatsbericht pro Inv | `aktueller_monat.py:1066` | **`7`** hart | **`1.80`** hart | `wallbox_preis_cent` |
| 4 | EAutoDashboard (Detail) | `investitionen.py:1337-1347` | `params.vergleich_verbrauch_l_100km` def. **`7.5`** | Query-Param `benzinpreis_euro` | `strompreis_cent` (allgemein) |
| 5 | Aussichten→Bisherige | `aussichten.py:1108-1189` | `params.vergleich_verbrauch_l_100km` def. kanon. **`7.5`** | `params.benzinpreis_euro` def. kanon. **`1.65`** + monatlicher Override aus `Monatsdaten.kraftstoffpreis_euro` | `wallbox_tarif` mit Fallback |
| 6 | Aussichten→Jahres-Prognose | `aussichten.py:1352-1374` | wie #5 | wie #5 (gemittelt aus historischen) | wie #5 |
| 7 | PDF-Jahresbericht | `pdf_operations.py:472-474` | params (kanon.) | params (kanon.) | wallbox-Tarif (kanon.) |
| 8 | V2H-Ersparnis (in Aussichten) | `aussichten.py:1422, 1506` | n/a | n/a | **`netzbezug_preis`** (allgemein, **nicht** wallbox-Tarif!) |
| 9 | Wallbox-Ersparnis (durch Heimladen) | `investitionen.py:1355-1358` | n/a | n/a | **`0.50`** €/kWh hart als Extern-Fallback |

### Drifts

🔥🔥 **Cockpit-Stellen #1, #2, #3 ignorieren User-Werte komplett**
- `7 L/100km` und `1.80 €/L` hartcodiert
- User pflegt `vergleich_verbrauch_l_100km` (kanon. Default 7.5) und `benzinpreis_euro` (kanon. Default 1.65) im Form/Wizard — die Werte landen in der DB, aber Cockpit ignoriert sie
- **Konsequenz:** Cockpit zeigt für **alle** User dieselbe Ersparnis-Schätzung, egal was sie pflegen

🔥 **Default-Drift `7.5` (kanon.) vs. `7` (hart)**
- v3.25.0 hat Investitions-Parameter aufgeräumt, aber Cockpit-Defaults nicht angeglichen
- E-Auto-Detail (`investitionen.py:1337`) liest Param mit Default 7.5 → kanon.
- E-Auto-Aussichten/PDF: kanon. (PARAM_E_AUTO_DEFAULTS)

🟡 **`benzinpreis_euro` Default Drift**
- `cockpit/uebersicht.py:306`: `1.80` hart
- `aktueller_monat.py:752, 1066`: `1.80` hart
- `PARAM_E_AUTO_DEFAULTS.benzinpreis_euro`: `1.65` (kanon.)
- Stellen #1-3 sind ~9% zu hoch im Default

🟡 **V2H-Ersparnis nutzt Allgemein-Strompreis statt Wallbox-Tarif**
- `aussichten.py:1422, 1506`: `netzbezug_preis` (allgemein)
- konsistent wäre: Ersparnis = was hätte das Stromnetz an Stelle des E-Autos geliefert? = wallbox-Tarif **oder** allgemein-Tarif (je nachdem, was die V2H-Energie ersetzt — typisch Haushaltsstrom = allgemein)
- Kann auch korrekt sein, je nach Modell — aber **inkonsistent** zur E-Auto-Lade-Berechnung die Wallbox-Tarif nimmt

🟡 **Wallbox-Ersparnis hartcodiert 0.50 €/kWh extern**
- `investitionen.py:1355`: `extern_preis_kwh = (gesamt_extern_kosten / gesamt_extern_ladung) if gesamt_extern_ladung > 0 else 0.50`
- Fallback-Wert wenn keine externen Lade-Vorgänge in der DB sind → Wallbox-Ersparnis wird mit pauschal 50 ct/kWh extern berechnet
- Kann zu Inflation der Wallbox-Ersparnis führen wenn nie extern geladen wurde
- Sollte: Konstante in `core/wirtschaftlichkeit_defaults.py` mit Kommentar, oder besser: Wallbox-Ersparnis nur ausweisen wenn extern-Daten vorhanden

🟡 **Benzin-CO2-Faktor nicht zentralisiert**
- `investitionen.py:1361`: `2.37 kg CO2/L` hart
- `cockpit/uebersicht.py:401`: `CO2_FAKTOR_BENZIN_KG_LITER` (Konstante!) — schon richtig
- Drift zwischen Cockpit (Konstante) und Investitionen-Detail (hart)

### Soll-Formel (E-Auto)

```python
benzin_kosten = (km_gefahren / 100) * vergleich_verbrauch_l_100km * benzinpreis_euro
                |
   km_gefahren = aus InvestitionMonatsdaten
   vergleich_verbrauch_l_100km = params (def. 7.5 kanon.)
   benzinpreis_euro = Monatsdaten.kraftstoffpreis_euro (monatlich) ODER params.benzinpreis_euro ODER 1.65

strom_kosten = ladung_netz_kwh × wallbox_strompreis / 100 + ladung_extern_euro
ersparnis_vs_benzin = benzin_kosten − strom_kosten
```

### Fix-Vorschlag

**Backend-Helper** `eedc/backend/services/eauto_wirtschaftlichkeit.py`:
```python
def berechne_eauto_ersparnis(
    eauto: Investition,
    km: float,
    ladung_netz: float,
    ladung_extern_euro: float,
    wallbox_strompreis_cent: float,
    monats_benzinpreis: float | None = None,
) -> EAutoErsparnis: ...
```

Cockpit, Monatsbericht, Investitionen-Detail, Aussichten alle umstellen.



## Domäne A3 — Speicher (Eigenverbrauchs-Ersparnis + Arbitrage)

### Render-Stellen-Matrix

| # | Render-Stelle | Backend-Quelle | Modell | Formel |
|---|---|---|---|---|
| 1 | SpeicherDashboard (Detail) | `investitionen.py:1662-1664` | **Spread** | `entladung × (strompreis − einspeiseverguetung)` |
| 2 | Aussichten→Bisherige (impliziert in EV) | `aussichten.py:1239-1314` | **EV-Erhöhung** | aus historischen `speicher_beitrag_kwh` summiert |
| 3 | Aussichten→Jahres-Prognose | `aussichten.py:1410, 1505` | **Voll-Strompreis** | `jahres_speicher_beitrag × netzbezug_preis / 100` |
| 4 | Speicher-Arbitrage (Detail) | `investitionen.py:1659-1668` | Arbitrage-Spread | `arbitrage_kwh × (strompreis − ladepreis_avg) / 100` |
| 5 | Cockpit→Komponenten | `cockpit/komponenten.py:147-180` | (zeigt nur kWh, keine €) | n/a |

### Drifts

🟡 **UI-Label-Lüge im SpeicherDashboard**
- Frontend `SpeicherDashboard.tsx:197`: `formel="Ersparnis = Entladung × Strompreis"`
- Backend `investitionen.py:1664`: `ersparnis = entladung × (strompreis − einspeiseverguetung)`
- Angezeigter Wert ist Spread, Label sagt Voll-Strompreis → User-Verwirrung

🟡 **Zwei verschiedene Ersparnis-Modelle (konzeptioneller Drift)**
- Investitionen-Detail (#1): Spread-Modell — Speicher als Tarif-Hebel zwischen Einspeise und Bezug
- Aussichten (#3): Voll-Strompreis-Modell — Speicher als reiner EV-Multiplikator
- Bei typischem Tarif (30ct/8ct): Spread = 22ct, Voll = 30ct → **36% Differenz** für dieselbe Anlage
- **Entscheidung nötig:** welches Modell ist kanonisch? Empfehlung: Spread (ökonomisch korrekt — Speicher-Energie hätte sonst Einspeise-Vergütung erwirtschaftet)

🟡 **Einspeisevergütung Default `8.2 ct/kWh` mehrfach hartcodiert** (siehe Domäne B)
- 5 Stellen: `cockpit/komponenten.py:262`, `cockpit/uebersicht.py:137, 332`, `aktueller_monat.py:524, 709`

### Soll-Formel (Speicher EV-Ersparnis)

```python
spread_cent = bezug_preis_cent − einspeise_verg_cent
ersparnis = entladung_kwh × spread_cent / 100

# Arbitrage zusätzlich (separater Gewinn-Posten, nicht überlappend mit EV-Ersparnis):
arbitrage_gewinn = arbitrage_kwh × (bezug_preis_cent − arbitrage_lade_preis_cent) / 100
```

### Fix-Vorschlag

**Backend-Helper** `eedc/backend/services/speicher_wirtschaftlichkeit.py` mit Spread-Modell vereinheitlicht.
**Frontend-Label** in `SpeicherDashboard.tsx:197` korrigieren.
**Aussichten-Stellen** (#3) auf Spread-Modell umstellen.

## Domäne A4 — PV-Eigenverbrauch + Einspeise-Erlös

### Render-Stellen-Matrix

| # | Render-Stelle | Backend-Quelle | Einspeise-Tarif-Quelle | Strompreis-Quelle | Default Bezug | Default Einspeise |
|---|---|---|---|---|---|---|
| 1 | Cockpit→Übersicht (Σ) | `cockpit/uebersicht.py:325-344` | pro Monat aus Tarif-Historie, Fallback **8.2** hart | `eff_netzbezug_preis` | n/a | **8.2** hart |
| 2 | Cockpit→Komponenten | `cockpit/komponenten.py:260-270` | pro Monat aus Tarif-Historie, Fallback **8.2** hart | n/a (zeigt nur Erlös) | n/a | **8.2** hart |
| 3 | Cockpit→Monatsbericht | `aktueller_monat.py:698-722` | aktueller Monatstarif, Fallback **8.2** hart | aktueller Monatstarif, Fallback **30.0** hart | **30.0** hart | **8.2** hart |
| 4 | PVAnlageDashboard (jahres) | `investitionen.py:728-730` | `einspeiseverguetung_cent` Query-Param mit Tarif-Fallback | `strompreis_cent` Query-Param mit Tarif-Fallback | tarif | tarif |
| 5 | Aussichten→Bisherige+Jahres | `aussichten.py:862, 1290-1313` | `allgemein_tarif.einspeiseverguetung_cent_kwh`, Fallback **8.2** hart | `netzbezug_preis` | tarif | **8.2** hart |
| 6 | Cockpit→Social | `cockpit/social.py:194` | pro Monat aus Tarif-Historie | aus Tarif-Historie | tarif | tarif |
| 7 | HA-Export | `ha_export.py:200-205` | aus Tarif | aus Tarif | tarif | tarif |
| 8 | Investitionen-Liste | `investitionen.py:1111-1113` | `einspeiseverguetung_cent` | `strompreis_cent` | tarif | tarif |

### Drifts

🟡 **Default-Wert `8.2 ct/kWh` für Einspeisevergütung an 6 Stellen hartcodiert**
- `cockpit/uebersicht.py:137, 332`, `cockpit/komponenten.py:262`, `aktueller_monat.py:524, 709`, `aussichten.py:862`
- Sollte: zentrale Konstante `EINSPEISEVERGUETUNG_DEFAULT_CENT = 8.2` (siehe Domäne B)

🟡 **Default-Wert `30.0 ct/kWh` Netzbezug einmalig hartcodiert**
- `aktueller_monat.py:708`: `netzbezug_preis_cent = ... if ... is not None else 30.0`
- Andere Stellen lassen `None` durch und Frontend zeigt dann „---" — das ist konsistenter
- **Halbwegs-OK**, aber hier nimmt aktueller_monat.py einen einsamen 30ct-Default an, was bei Anlagen ohne Tarif zu falschen Ersparnis-Werten führt

🟢 **Modell ist über Stellen einheitlich**
- Alle Stellen rechnen: `einspeise_erloes = einspeisung × einspeiseverguetung / 100` und `ev_ersparnis = eigenverbrauch × bezug / 100`
- Das ist gut — kein konzeptioneller Drift wie beim Speicher

🟡 **Einspeise-Tarif-Historie inkonsistent angewendet**
- Cockpit (#1, #2, #6) liest pro Monat aus `Tarif`-Historie (richtig — Anlagen mit Tarif-Wechsel werden korrekt bewertet)
- Aussichten (#5) liest nur den **aktuellen** Tarif, ignoriert Tarif-Historie für historische Monate → bei Anlagen mit gestiegener EEG-Vergütung über die Jahre falsche Bisherige-Werte
- Monatsbericht (#3) liest nur den Tarif für den abgefragten Monat (OK weil Single-Monat)

### Soll-Formel

```python
einspeise_erloes = einspeisung × einspeiseverguetung_cent / 100  # historisch korrekt: Tarif-Historie pro Monat
ev_ersparnis = eigenverbrauch × bezug_preis_cent / 100  # historisch korrekt: Tarif-Historie pro Monat
netto_ertrag = einspeise_erloes + ev_ersparnis
```

### Fix-Vorschlag

**Backend-Helper** `eedc/backend/services/pv_wirtschaftlichkeit.py` mit Tarif-Historie-Lookup als Standard.

**Konstanten-Modul** `eedc/backend/core/wirtschaftlichkeit_defaults.py`:
- `EINSPEISEVERGUETUNG_DEFAULT_CENT = 8.2`
- `NETZBEZUG_DEFAULT_CENT = 30.0`
- (siehe Domäne B für komplette Liste)

## Domäne A5 — Balkonkraftwerk (BKW)

### Render-Stellen-Matrix

| # | Render-Stelle | Backend-Quelle | Strompreis | Modell |
|---|---|---|---|---|
| 1 | Cockpit→Übersicht | `cockpit/uebersicht.py:395` | `eff_netzbezug_preis` | `bkw_ev × bezugspreis / 100` |
| 2 | Aussichten→Bisherige | `aussichten.py:1192-1197` | `netzbezug_preis` (allgemein) | `bkw_ev × bezug / 100` |
| 3 | Aussichten→Jahres-Prognose | `aussichten.py:1377-1379` | aus #2 hochgerechnet | `bisherige × 12 / anzahl_monate` |
| 4 | HA-Export Bilanz | `ha_export.py:303-308` | `netzbezug_preis_cent` (allgemein) | wie #2 |

### Drifts

🟢 **Sehr konsistent**
- Alle 4 Stellen rechnen identisch: `eigenverbrauch × bezugspreis`
- Modell ist einfach (BKW hat keine Einspeise-Logik wie PV), keine Drift-Anfälligkeit

🟡 **Kein BKW-Detail-Dashboard** — anders als WP/Speicher/E-Auto kein eigenes BKW-Cockpit
- Kann sein dass das User-seitig fehlt, aber Drift-frei
- BKW-Daten erscheinen im PV-Aggregat (gemeinsam mit Modulen)

### Soll-Formel

Aktuell schon einheitlich, kein Fix nötig.

## Domäne B — Hartcodierte Konstanten (Magic Numbers)

### Bestand

`eedc/backend/core/calculations.py:15-17` definiert bereits:
```python
CO2_FAKTOR_STROM_KG_KWH = 0.38      # deutscher Strommix
CO2_FAKTOR_BENZIN_KG_LITER = 2.37   # kg/L Benzin
CO2_FAKTOR_GAS_KG_KWH = 0.201       # kg/kWh Erdgas
```

`eedc/backend/core/investition_parameter.py:127`:
```python
"alter_preis_cent_kwh": 12  # Default Gas-Endkundenpreis
```

`eedc/frontend/src/lib/investitionParameter.ts:48`:
```typescript
benzinpreis_euro: 1.65
```

### Drift-Liste — Konstanten die hartcodiert sind statt aus dem zentralen Modul gelesen

| Konstante | Korrekt (zentral) | Hartcodierte Stellen | Anzahl |
|---|---|---|---|
| Strom-CO2 `0.38 kg/kWh` | `CO2_FAKTOR_STROM_KG_KWH` | `investitionen.py:1362, 1512, 1989, 2100`, `ha_export.py:208` | 5 |
| Benzin-CO2 `2.37 kg/L` | `CO2_FAKTOR_BENZIN_KG_LITER` | `investitionen.py:1361` | 1 |
| Gas-CO2 `0.2 kg/kWh` (drift!) | `CO2_FAKTOR_GAS_KG_KWH = 0.201` | `investitionen.py:1511` (Kommentar 0.2) | 1 |
| WP-Wirkungsgrad Gas `0.9` | (nirgends zentral) | `cockpit/uebersicht.py:295, 400`, `cockpit/social.py:185`, `cockpit/nachhaltigkeit.py:154`, `aktueller_monat.py:739, 1054`, `aussichten.py:1095`, `ha_export.py:245`, `pdf_operations.py:420` | 9 |
| WP-Wirkungsgrad Öl `0.85` | (nirgends zentral) | `aussichten.py:1104`, `ha_export.py:254, 617`, `pdf_operations.py:429` | 4 |
| Gaspreis-Default `10.0 ct` | (kanon. ist 12) | `cockpit/uebersicht.py:294`, `aktueller_monat.py:737, 1054` | 3 |
| Gaspreis-Default `8 ct` | (kanon. ist 12) | `KomponentenTab.tsx:368` (`0.08 €`) | 1 |
| Gaspreis-Default `12 ct` (kanon.) | `PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"]` | falscher Key in `investitionen.py:1505` (`gas_kwh_preis_cent`) | 1 |
| Einspeisevergütung-Default `8.2 ct` | (nirgends zentral) | `cockpit/uebersicht.py:137, 332`, `cockpit/komponenten.py:262`, `aktueller_monat.py:524, 709`, `aussichten.py:862` | 6 |
| Netzbezug-Default `30.0 ct` | (nirgends zentral) | `aktueller_monat.py:708` | 1 |
| Benzin-Verbrauch `7 L/100km` | (kanon. ist 7.5) | `cockpit/uebersicht.py:305`, `aktueller_monat.py:752, 1066` | 3 |
| Benzin-Preis `1.80 €/L` | (kanon. ist 1.65) | `cockpit/uebersicht.py:306`, `aktueller_monat.py:752, 1066` | 3 |
| Externer Lade-Preis-Fallback `0.50 €/kWh` | (nirgends zentral) | `investitionen.py:1355` | 1 |
| WP-PV-Anteil-Annahme `0.5` (50%) | (nirgends zentral) | `aussichten.py:1158, 1345`, `ha_export.py:276` | 3 |

**Gesamt:** ~42 hartcodierte Stellen, davon ~25 mit existierender zentraler Konstante (Drift) und ~17 ohne zentrale Konstante (kanon. fehlt).

### Drifts (geordnet nach User-Impact)

🔥🔥 **Default-Drift Benzin-Preis 1.80 vs. 1.65 (kanon.)**
- Cockpit-Stellen rechnen 9% zu hoch
- E-Auto-Aussichten und PDF rechnen mit 1.65 (kanon.)
- → Cockpit zeigt 9% mehr Ersparnis als Aussichten

🔥 **Default-Drift Benzin-Verbrauch 7 vs. 7.5 (kanon.)**
- ähnlich, ~7% Abweichung in Cockpit vs. Aussichten

🔥 **Gaspreis-Default 8/10/12 ct über drei Stellen**
- Auswertungen-Komponenten 8, Cockpit 10, kanonisch 12
- 50% Spannweite → User mit 12ct-Default sehen je nach UI-Stelle 0.6×–1.0× der Ersparnis

🟡 **WP-Wirkungsgrad 0.9/0.85 nicht zentral**
- 13 Stellen mit gleichem Wert — keine echte Drift, aber kein „one place to change"
- Sollte: Konstanten in `core/wirtschaftlichkeit_defaults.py`

🟡 **CO2-Konstanten 5× unnötig hart**
- `core/calculations.py` exportiert sie schon, andere Stellen lesen direkt 0.38
- Lokal gleich, aber bei Update der Konstante (z.B. wenn Strommix sich ändert) gehen 5 Stellen verloren

🟡 **WP-PV-Anteil 0.5 hart**
- 50/50-Annahme in Aussichten + HA-Export — könnte aus echten Daten gelesen werden

### Soll-Modul

Neuer File `eedc/backend/core/wirtschaftlichkeit_defaults.py`:
```python
# Wärmepumpen-Wirkungsgrade (alter Energieträger)
WP_WIRKUNGSGRAD_GAS_DEFAULT = 0.90
WP_WIRKUNGSGRAD_OEL_DEFAULT = 0.85

# Energiepreise (Defaults wenn nichts gepflegt)
GASPREIS_DEFAULT_CENT = 12.0
EINSPEISEVERGUETUNG_DEFAULT_CENT = 8.2
NETZBEZUG_DEFAULT_CENT = 30.0
EXTERNE_LADUNG_DEFAULT_EURO_KWH = 0.50

# E-Auto Vergleichswerte
BENZIN_VERBRAUCH_DEFAULT_L_100KM = 7.5
BENZIN_PREIS_DEFAULT_EURO_L = 1.65

# WP-PV-Anteil Default (wenn keine Detail-Daten)
WP_PV_ANTEIL_DEFAULT = 0.5
```

Frontend-Pendant `eedc/frontend/src/lib/wirtschaftlichkeitDefaults.ts` mit gleichen Werten.

## Domäne C — Param-Key-Lookups gegen Schema

### Methodik

Greppe alle `parameter.get("...")` und `params.get("...")` Aufrufe + alle Frontend `inv.parameter?.xxx` und vergleiche gegen `PARAM_*`-Konstanten in `core/investition_parameter.py` und `lib/investitionParameter.ts`.

v3.25.0 hat die großen Brocken erledigt; verbliebene Drifts sind Edge-Cases.

### Verbliebene Param-Key-Drifts

🔥 **`investitionen.py:1505` — `gas_kwh_preis_cent` (toter Key)**
- Form/Wizard schreiben `alter_preis_cent_kwh` (PARAM_WAERMEPUMPE.ALTER_PREIS_CENT_KWH)
- Backend liest `gas_kwh_preis_cent` mit Default 12 → Default-Drift wenn User explizit anderen Gaspreis hinterlegt hat
- Bei `aussichten.py`/`pdf_operations.py`/`ha_export.py` korrekt
- **#178-Bug**: Cockpit→Wärmepumpe-Detail zeigt 77€ statt 61€

🟡 **PV-Modul vs. BKW Ausrichtung-Schema-Mix**
- BKW: `ausrichtung` (String "Süd") + `neigung_grad` (float)
- PV-Modul: `ausrichtung_grad` (float) — separater Schlüssel
- `pv_strings.py:203, 379`: `modul.ausrichtung or params.get("ausrichtung")` — funktioniert für BKW-Param-Daten, nicht für PV-Modul mit `ausrichtung_grad`
- `live_wetter.py:155-161`: liest `neigung_grad` und `ausrichtung_grad` — passt zu PV-Modul-Schema, nicht BKW
- `pv_orientation.py:76-87`: hat Helper-Funktion mit Doppel-Read (`ausrichtung_grad` zuerst, `ausrichtung` als Fallback) — **das ist der pragmatische Weg**, sollte überall genutzt werden statt Ad-hoc-Reads

🟡 **`leistung_wp` Default-Drift**
- `investitionen.py:1104`: `params.get('leistung_wp', 800)` — Default 800
- `investitionen.py:1962`: `params.get('leistung_wp', 0)` — Default 0
- Inkonsistente Defaults für denselben Key. Kein PARAM_BALKONKRAFTWERK_DEFAULTS Eintrag für leistung_wp

🟡 **`anzahl` Default-Drift**
- `investitionen.py:1963`: `params.get('anzahl', 2)` — Default 2 (passt zu PARAM_BALKONKRAFTWERK_DEFAULTS)
- `cockpit/uebersicht.py:274`: `params.get("anzahl", 1) or 1` — Default 1
- Inkonsistent

🟢 **Sonstige PARAM_-Keys sehen sauber aus**
- `vorschlag_service.py` liest WP-Schema mit `getrennte_strommessung`, `effizienz_modus`, `jaz`, `scop_*`, `cop_*` — alle gegen Schema
- `aussichten.py`, `ha_export.py`, `pdf_operations.py` nutzen `PARAM_*`-Konstanten konsequent (v3.25.0 sauber)

### Fix-Vorschlag

1. **#178-Fix**: `investitionen.py:1505` Param-Key korrigieren auf `PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"]` mit kanon. Default 12, plus Wirkungsgrad-Division
2. **PV-Orientation-Helper**: `pv_orientation.get_azimut(params)` und `pv_orientation.get_neigung(params)` als kanon. Reader (gibt es schon teilweise!) — alle Stellen umstellen, ad-hoc-Reads entfernen
3. **BKW-Defaults vervollständigen**: `leistung_wp` und `anzahl` als Default in `PARAM_BALKONKRAFTWERK_DEFAULTS`, alle Stellen darauf umstellen

## Domäne D — Strompreis-Lookups (5 Tarife)

### Tarif-Struktur

EEDC unterscheidet pro Anlage 5 Tarif-Typen:
- `allgemein` — Haushaltsstrom
- `waermepumpe` — separater WP-Strom (oft günstiger)
- `wallbox` — separater E-Auto-Strom
- `einspeise` — Einspeisevergütung (technisch ein Tarif, aber meist nur `einspeiseverguetung_cent_kwh` befüllt)
- `sonstiges` — wenig genutzt

Lookup über `lade_tarife_fuer_anlage(db, anlage_id) -> dict[str, Tarif]`.

### Lookup-Pattern-Inventur

| Stelle | Pattern | Korrekt? |
|---|---|---|
| `aussichten.py:858-864` | `wp_tarif → wp_netzbezug_preis = wp_tarif.netzbezug or netzbezug_preis (allgemein)` | ✅ richtig (mit Fallback) |
| `cockpit/uebersicht.py:136-139` | gleiche Logik mit `wp_preis_cent`, `wallbox_preis_cent` | ✅ |
| `aktueller_monat.py:705-735` | `allgemein_tarif`, `wp_tarif` separat geprüft | ✅ |
| `investitionen.py:512-519` | PV-Endpoint: `strompreis_cent` aus Query, dann allgemein, wp, wallbox | ✅ |
| `investitionen.py:1266-1269` | E-Auto-Endpoint: `wallbox_tarif → allgemein_tarif → 30.0` mit verschachteltem ternär (lesbar?) | 🟡 |
| `investitionen.py:1417-1420` | WP-Endpoint: `wp_tarif → allgemein_tarif → 30.0` | 🟡 |
| `investitionen.py:1752-1755` | Speicher-Endpoint: `wallbox_tarif → allgemein_tarif → 30.0` (warum wallbox??) | 🔥 |
| `ha_export.py:200-205` | nutzt nur `strompreis` global | 🟡 |
| `cockpit/komponenten.py:265` | `resolve_netzbezug_preis_cent(md, ...)` pro Monat | ✅ |
| `cockpit/social.py:193` | gleiche Helfer-Funktion | ✅ |

### Drifts

🔥 **Speicher-Endpoint nutzt Wallbox-Tarif als ersten Fallback (`investitionen.py:1755`)**
- `wallbox_tarif → allgemein_tarif → 30.0`
- Speicher hat nichts mit Wallbox zu tun! Sollte: `allgemein_tarif → 30.0` (oder Wärmepumpen-Tarif wenn Speicher hauptsächlich für WP)
- Vermutlich Copy-Paste-Fehler aus E-Auto-Endpoint (1269) ohne Anpassung
- **Konsequenz:** User mit separatem Wallbox-Tarif sehen falsche Speicher-Ersparnis

🟡 **Verschachtelte ternäre Fallbacks schwer lesbar**
- `investitionen.py:1269, 1420, 1755` haben dreifach-verschachtelte Fallbacks in einer Zeile
- Ein zentraler Helper `resolve_strompreis(tarife, *prefer_keys, fallback=30.0)` würde Konsistenz erzwingen

🟡 **Default-Wert `30.0` ct hartcodiert in jedem Lookup-Fallback**
- Min. 6 Stellen wiederholen `or 30.0`
- Sollte: zentrale Konstante (siehe Domäne B, `NETZBEZUG_DEFAULT_CENT`)

### Fix-Vorschlag

Helper in `eedc/backend/api/routes/strompreise.py` ergänzen:
```python
def resolve_strompreis_for_komponente(
    tarife: dict[str, Tarif],
    komponente: Literal["allgemein", "waermepumpe", "wallbox"],
    fallback: float = NETZBEZUG_DEFAULT_CENT,
) -> float:
    """Liest komponenten-spezifischen Tarif mit Fallback auf allgemein."""
```

Alle Endpoint-Header umstellen, verschachtelte Ternäre raus.

## Domäne E — Anschaffungsdatum-Filter Konsistenz

### Hintergrund (v3.23.1-Lesson)

Aus MEMORY: „Bei Filter-Patches IMMER alle Aggregations-Endpoints greppen, nicht nur die offensichtlichen." v3.23.0 hatte den Filter nur in 2 Endpoints, v3.23.1 zog ihn auf 6+ weitere — aber nicht alle.

Filter-Logik: `Investition.ist_aktiv_an(date)` und manuelle Checks der Form `(imd.jahr, imd.monat) < (anschaffungsdatum.year, anschaffungsdatum.month)`.

### Endpoints mit Anschaffungsdatum-Filter (✅)

- `aussichten.py:891-892, 955-957` ✅
- `aktueller_monat.py:312-313` ✅
- `cockpit/uebersicht.py:182-184, 265, 283, 291, 300, 310` ✅
- `cockpit/komponenten.py:159-161` ✅
- `cockpit/social.py:134-135` ✅
- `cockpit/nachhaltigkeit.py:82-83` ✅
- `investitionen.py:1298, 1467, 1620, 1804, 1855, 1936` ✅ (pro Detail-Endpoint)
- `import_export/pdf_operations.py` ✅ (1 Treffer)

### Endpoints OHNE Anschaffungsdatum-Filter (🔥 potenzielle Drifts)

🔥🔥 **`cockpit/prognose.py:101-106 + 205-210`** — PV-Aggregation für Prognose
- Aggregiert `InvestitionMonatsdaten` für `pv_ids` ohne Anschaffungsdatum-Filter
- **Konsequenz:** WP/E-Auto/Speicher mit gepflegtem Anschaffungsdatum erscheinen in der Cockpit-Prognose; PV-Module die noch nicht angeschafft sind, fließen in historische Aggregate
- **Aber:** Hier geht es um PV-Module, die typischerweise mit der Anlage zusammen angeschafft werden (kein DataDate-Drift) → in der Praxis wenig Impact

🔥🔥 **`ha_export.py:157-182`** — PV + Speicher Aggregation für HA-Sensor-Export
- Aggregiert `InvestitionMonatsdaten` ohne Filter
- **Konsequenz:** HA-Sensoren wie `wp_ersparnis_euro`, `bisherige_*_ersparnis` rechnen auch Monate vor Anschaffung mit — wenn User schon Vor-Daten importiert hat (z.B. via CSV)
- **detLAN-Beispiel #178** könnte hier teilweise Ursache der 77€-Drift sein (HA-Sensor-Pfad zeigt unterschiedliche Werte als Cockpit)

🟡 **`community_service.py:238-340`** — aggregiert InvestitionMonatsdaten für Community-Submission
- Submitted Aggregate für die Anlage; wenn WP frisch installiert mit Vor-Importen drin, gehen Vor-WP-Daten als „WP-Daten" raus
- **Konsequenz:** Community-Server bekommt korrupten Datensatz für betroffene Anlagen
- Fix: gleichen Filter anwenden wie im Cockpit

🟡 **`monatsabschluss.py`** — keine Treffer
- Monatsabschluss arbeitet pro Monat, der User bestätigt explizit; Filter weniger kritisch
- Aber: Wenn User den Wizard für einen Monat vor Anschaffung öffnet, könnte er Komponenten-Felder sehen, die er nicht ausfüllen sollte

### Soll-Pattern

```python
# Helper in models/investition.py existiert schon: ist_aktiv_an(date)
# Pro Monat:
def imd_in_aktivem_zeitraum(imd: InvestitionMonatsdaten, inv: Investition) -> bool:
    monatsanfang = date(imd.jahr, imd.monat, 1)
    return inv.ist_aktiv_an(monatsanfang) or (
        inv.anschaffungsdatum and 
        (imd.jahr, imd.monat) >= (inv.anschaffungsdatum.year, inv.anschaffungsdatum.month)
    )
```

Alle Endpoints die `InvestitionMonatsdaten` aggregieren sollten diesen Helper nutzen statt Ad-hoc-Checks.

### Fix-Vorschlag

1. **Helper-Funktion** `Investition.ist_aktiv_in_monat(jahr, monat)` als Klassen-Methode (analog zu `ist_aktiv_an(date)`)
2. **3 Drift-Endpoints fixen**: `cockpit/prognose.py`, `ha_export.py`, `community_service.py`
3. **Lint-Test** schreiben der prüft: jede `InvestitionMonatsdaten`-Aggregation muss einen Anschaffungsdatum-Check haben

## Domäne F — Defensive Doppel-Reads (Drift-Indikatoren)

### Hintergrund

Defensive Doppel-Reads der Form `data.get("a", 0) or data.get("b", 0)` deuten auf Schema-Drift hin: ein Feld wurde umbenannt, alter Code liest noch beide Varianten als Sicherheitsnetz. Das ist OK als Übergangsmaßnahme, wird aber zu Drift-Indikator wenn:
- Beide Felder gleichzeitig Daten enthalten (welche Quelle gilt?)
- Neue Code-Stellen den Doppel-Read kopieren statt das Schema zu konsolidieren
- Eine Migration den alten Key entfernen sollte, wurde aber nicht ausgeführt

### Inventur — `verbrauch_daten`-JSON-Field-Drifts

Sammlung aller Doppel-Reads in `InvestitionMonatsdaten.verbrauch_daten` und ähnlichen JSON-Feldern:

| Felder-Paar | Typ | Anzahl Stellen | Beispiele |
|---|---|---|---|
| `pv_erzeugung_kwh` ↔ `erzeugung_kwh` | PV-Modul, BKW | 9 | `cockpit/prognose.py:107, 211`, `social.py:139`, `nachhaltigkeit.py:102`, `uebersicht.py:227`, `aktueller_monat.py:473, 1029`, `monatsdaten.py:231`, `investitionen.py:1954` |
| `heizenergie_kwh` ↔ `heizung_kwh` | WP | 8 | `cockpit/komponenten.py:190`, `social.py:146`, `nachhaltigkeit.py:106`, `uebersicht.py:199`, `aktueller_monat.py:332, 840, 1048`, `pdf_operations.py:284` |
| `ladung_kwh` ↔ `verbrauch_kwh` | E-Auto | 6 | `cockpit/komponenten.py:207`, `social.py:156`, `nachhaltigkeit.py:117`, `aktueller_monat.py:486, 1062` |
| `ladung_netz_kwh` ↔ `speicher_ladung_netz_kwh` | Speicher (Arbitrage) | 2 | `cockpit/komponenten.py:180`, `investitionen.py:1640` |
| `verbrauch_sonstig_kwh` ↔ `verbrauch_kwh` | Sonstiges | 2 | `cockpit/komponenten.py:229, 232` |
| `eigenverbrauch_kwh` ↔ `pv_erzeugung_kwh` | PV (Fallback) | 1 | `aktueller_monat.py:1029` (Fallback wenn EV nicht direkt) |

### Drifts

🔥 **`pv_erzeugung_kwh` vs. `erzeugung_kwh` (9 Stellen!)**
- Kein zentraler Reader → Drift-Risiko
- Wenn jemand neu BKW-Code schreibt und nur `erzeugung_kwh` liest, fehlt `pv_erzeugung_kwh`-Daten
- **Fix:** Helper `read_pv_erzeugung(data: dict) -> float` an einer Stelle, alle Aufrufer importieren

🔥 **`heizenergie_kwh` vs. `heizung_kwh` (8 Stellen!)**
- Gleiches Problem
- Schema scheint im Wandel — eventuell stammt `heizung_kwh` aus alter Migration, soll vermutlich entfallen

🟡 **`ladung_kwh` vs. `verbrauch_kwh` (6 Stellen)**
- E-Auto-Energie kann im Form unter `ladung_kwh` ODER `verbrauch_kwh` landen je nach Code-Version

### Soll-Pattern

Zentrale Field-Reader in `eedc/backend/core/field_definitions.py` (existiert schon teilweise) ergänzen:
```python
def get_pv_erzeugung_kwh(data: dict) -> float:
    return data.get("pv_erzeugung_kwh") or data.get("erzeugung_kwh") or 0

def get_heizenergie_kwh(data: dict) -> float:
    return data.get("heizenergie_kwh") or data.get("heizung_kwh") or 0

def get_eauto_ladung_kwh(data: dict) -> float:
    return data.get("ladung_kwh") or data.get("verbrauch_kwh") or 0
```

Alle Doppel-Read-Stellen auf diese Helper umstellen. Falls möglich, **Migration** schreiben die alle alten Keys aus `verbrauch_daten` entfernt und nur kanon. Keys behält.

### Fix-Vorschlag

1. **Field-Reader-Helper** in `core/field_definitions.py` für die 4 großen Drift-Paare
2. **27+ Doppel-Read-Stellen umstellen**
3. **Migration-Skript** (analog `_migrate_investitionen_parameter_keys_v325`) das Legacy-Keys konsolidiert
4. **Lint-Test**: `data.get("pv_erzeugung_kwh"...) or data.get("erzeugung_kwh"...)` als verbotenes Muster im Backend-Code

## Zusammenfassung — Drift-Befunde nach Schwere

### 🔥🔥🔥 Akut (User-sichtbarer Geld-Drift, sofortiger Fix)

1. **WP-Ersparnis 4-Stellen-Drift (#178)** — Auswertungen→Komponenten zeigt 7€ statt 61€, Cockpit→WP zeigt 77€ statt 61€. Falscher Param-Key + hartcodierter 8ct-Gaspreis.
2. **Speicher-Endpoint nutzt Wallbox-Tarif als Fallback** (`investitionen.py:1755`) — Copy-Paste-Bug, betrifft alle User mit separatem Wallbox-Tarif

### 🔥🔥 Hoch (User-sichtbar, Default-Drift)

3. **E-Auto-Defaults Cockpit**: 7 L/100km (kanon. 7.5) und 1.80 €/L (kanon. 1.65) hartcodiert in 3+3 Stellen → ~9% Abweichung Cockpit vs. Aussichten
4. **Cockpit-WP ignoriert User-Gaspreis**: 10ct hartcodiert statt `params.alter_preis_cent_kwh` (kanon. 12) — User-pflegbarer Wert wird ignoriert in 3 Stellen
5. **Cockpit-WP ignoriert monatlichen Gaspreis-Override** (`Monatsdaten.gaspreis_cent_kwh`)

### 🔥 Mittel (Architektur-Schuld, Drift-Anfälligkeit)

6. **Hartcodierte WP-Wirkungsgrade `0.9/0.85`** in 13 Stellen — kein zentrales Modul
7. **CO2-Faktoren in 5 Stellen hart** statt aus `core/calculations.py` importiert
8. **Einspeisevergütung `8.2 ct` in 6 Stellen hart** — kein zentrales Default
9. **Anschaffungsdatum-Filter fehlt in 3 Endpoints**: `cockpit/prognose.py`, `ha_export.py`, `community_service.py`
10. **Speicher-Ersparnis-Modell-Drift** (Spread vs. Voll-Strompreis) zwischen Investitionen-Detail und Aussichten — 36% Differenz für gleiche Anlage

### 🟡 Niedrig (Entwickler-Falle, kein User-Impact heute)

11. **27+ Doppel-Read-Stellen** für JSON-Field-Drifts (`pv_erzeugung_kwh` vs. `erzeugung_kwh`, etc.)
12. **WP-PV-Anteil 0.5 hartcodiert** in Aussichten + HA-Export — sollte aus tatsächlichen Daten
13. **V2H-Strompreis nutzt allgemein-Tarif** statt wallbox-Tarif (konzeptionell unklar)
14. **Wallbox-Ersparnis nutzt 0.50 €/kWh** als Extern-Fallback hart
15. **`leistung_wp` und `anzahl` Default-Drift** für BKW (800 vs. 0, 2 vs. 1)
16. **UI-Label-Lüge im SpeicherDashboard**: Formel-Text und Backend-Berechnung passen nicht zusammen

## Bündel-Plan (Phase 2)

### Bündel A — Akut: WP-Wirtschaftlichkeit SoT (#178-Trigger)

**Aufwand:** ~2h Backend + 30min Frontend + 30min Test
**Release:** v3.25.x

- Konstanten-Modul `core/wirtschaftlichkeit_defaults.py` anlegen (Wirkungsgrade, Gaspreis-Default, Einspeisevergütung-Default, Netzbezug-Default)
- Frontend-Pendant `lib/wirtschaftlichkeitDefaults.ts`
- Backend-Service `services/wp_wirtschaftlichkeit.py` mit `berechne_wp_ersparnis(...)`
- Alle 4 problematischen Render-Stellen (#1-4 aus A1-Inventur) auf den Helper umstellen
- Bonus: Param-Key-Fix `gas_kwh_preis_cent → alter_preis_cent_kwh` in `investitionen.py:1505`
- detLAN testen lassen (#178 close)

### Bündel B — E-Auto/Wallbox SoT

**Aufwand:** ~2h
**Release:** v3.25.x oder v3.26.0

- Backend-Service `services/eauto_wirtschaftlichkeit.py`
- Cockpit + Monatsbericht + Investitionen-Detail umstellen
- 7→7.5 und 1.80→1.65 Defaults harmonisieren
- V2H/Wallbox-Strompreis-Frage klären (allgemein vs. wallbox)

### Bündel C — Hartcodierte Konstanten zentralisieren

**Aufwand:** ~1.5h
**Release:** v3.26.0

- Alle WP-Wirkungsgrade auf Konstanten umstellen (13 Stellen)
- CO2-Faktoren-Imports vervollständigen (5 Stellen)
- Einspeisevergütung-Default zentralisieren (6 Stellen)

### Bündel D — Speicher-Modell-Vereinheitlichung

**Aufwand:** ~1h + Diskussion
**Release:** v3.26.0

- Entscheidung Spread- vs. Voll-Strompreis-Modell (Empfehlung: Spread)
- Aussichten-Stellen umstellen
- SpeicherDashboard-Label korrigieren

### Bündel E — Strompreis-Lookup-Helper

**Aufwand:** ~1h
**Release:** v3.26.0

- `resolve_strompreis_for_komponente(...)` in `strompreise.py` ergänzen
- Wallbox-Bug in Speicher-Endpoint fixen (`investitionen.py:1755`)
- Verschachtelte ternäre Fallbacks bereinigen

### Bündel F — Anschaffungsdatum-Filter Coverage

**Aufwand:** ~1.5h
**Release:** v3.26.0

- `Investition.ist_aktiv_in_monat(jahr, monat)` Methode hinzufügen
- 3 Drift-Endpoints fixen (Prognose, HA-Export, Community)
- Lint-Test schreiben der `InvestitionMonatsdaten`-Aggregation ohne Filter erkennt

### Bündel G — Field-Reader-Helper

**Aufwand:** ~3h (inkl. Migration)
**Release:** v3.26.0 oder v3.27.0

- 4 Reader-Helper in `core/field_definitions.py`
- 27+ Stellen umstellen
- DB-Migration `_migrate_verbrauch_daten_keys` schreibt alte Keys auf kanon. um
- Lint-Test gegen das verbotene `or data.get("...")`-Muster

### Reihenfolge-Empfehlung

1. **Diese Woche:** Bündel A (akut, detLAN wartet, #178)
2. **Nächster Sprint:** Bündel B + C als Doppel-Release (related — beide brauchen das Konstanten-Modul aus A)
3. **Folge-Sprint:** Bündel D + E + F (architekturell related — Strompreis-Helper, Filter, Modell-Cleanup)
4. **Späterer Sprint:** Bündel G (Migration-Risiko, sollte allein laufen)

### Cross-cutting: Tests gegen Re-Drift

Nach jedem Bündel ein Lint-Test ergänzen der das gefixte Pattern verbietet:
- `core/test_no_hardcoded_constants.py` — sucht magische Zahlen in Berechnungen
- `core/test_no_drift_double_read.py` — sucht `data.get("...") or data.get("...")` außerhalb von `field_definitions.py`
- `core/test_anschaffungsdatum_filter.py` — sucht `InvestitionMonatsdaten`-Queries ohne Filter

So wird die Drift nicht von der nächsten Code-Generation re-eingebaut.

