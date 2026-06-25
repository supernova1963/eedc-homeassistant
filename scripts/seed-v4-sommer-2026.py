"""Plausible Sommer-Demo-Daten für Apr–Jun 2026 (Gernot 2026-06-25).

Problem: Der `+175-Tage`-Aussicht-Seed bildet Herbst/Winter 2025 (Sep–Dez) auf
Frühling/Sommer 2026 (Apr–Jun) ab — saisonal rückwärts: „Juni 2026" zeigte in
Wahrheit Dezember-Daten (−3,9 °C, ~16 kWh PV/Tag, ~0 Einspeisung), und die
Performance Ratio war gar nicht berechenbar (Aggregat nie gelaufen).

Dieses Script erzeugt für jeden Tag im +175-Fenster (2026-04-08 .. 2026-06-23)
plausible Sommer-Werte und schreibt sie in die TEP-Stundenzeilen + die
Tageszusammenfassung — OHNE Open-Meteo (offline, auch auf der Guest-Box):

  • PV (pv_kw):   sommerliche Tageskurve (Sonnenauf-/-untergang nach Datum),
                  Tagessumme saisonal (Apr ~60 → Jun ~92 kWh, Wolken-streuung).
  • Verbrauch:    UNVERÄNDERT übernommen (Verbrauchshistorie ist der Zweck des
                  +175-Seeds und liegt mit ~19 kWh/Tag bereits sommer-plausibel).
  • Speicher/Netz: aus PV − Verbrauch über eine Batterie-Simulation
                  (BYD HVS 15.4 kWh, 10 kW, 95 %) → echte Einspeisung sobald der
                  Mittags-Überschuss den Speicher füllt; nachts wenig Netzbezug.
  • Wetter:       Temperatur (sommerlicher Tagesgang), Globalstrahlung (folgt der
                  PV-Kurve), Bewölkung/Wetter-Code aus dem Wolkenfaktor.
  • TZ-Aggregate: performance_ratio, peak_*_kw, temperatur_min/max_c,
                  strahlung_summe_wh_m2, pv_prognose_kwh — konsistent gesetzt.
                  PR & Strahlung erfüllen „Ertrag ÷ (Einstrahlung × kWp)", damit
                  der Formel-Tooltip stimmig ist.

Determinismus: pro Tag aus dem Datum geseedeter RNG → reproduzierbar (idempotent,
beliebig oft ausführbar). DB-Pfad via EEDC_RESEED_DB (Default Dev-Box).
"""
import os
import json
import math
import sqlite3
from datetime import date, timedelta

DB = os.environ.get("EEDC_RESEED_DB", "/tmp/eedc_v4devbox.db")
ANLAGE = 1
KWP = 20.0                      # Demo-Anlage Gesamt-kWp (DC)
INV_MAX = 10.5                  # Fronius Symo GEN24 10.0 → AC-Clipping ~10 kW
BATT_KWH = 15.4                 # BYD HVS 15.4
BATT_RATE = 10.0               # kW Lade-/Entladegrenze
BATT_EFF = 0.95                 # Entlade-Wirkungsgrad
COP_HEIZ = 4.0                  # Sommer/Übergang: hohe Quelltemperatur → guter COP
COP_WW = 2.8                    # Warmwasser braucht höhere Vorlauftemperatur
WP_BASIS_TEMP = 15.0            # ab Ø-Tagestemperatur ≥ 15 °C keine Raumheizung mehr
WP_HEIZ_FAKTOR = 3.0            # kWh therm. Raumheizung je °C unter der Basistemperatur
WP_WW_THERM = 4.0               # kWh therm. Warmwasser/Tag (ganzjährig)
# Stundenprofil des WP-Stroms (morgens/abends mehr, mittags wenig) — nur kosmetisch
# für die Stunden-WP-Serie; die Energie-Bilanz nutzt verbrauch_kw (unverändert).
WP_PROFIL = [.5, .5, .5, .5, .6, .9, 1.2, 1.3, 1.0, .6, .4, .3,
             .3, .3, .3, .4, .6, .9, 1.2, 1.3, 1.0, .8, .6, .5]
VON, BIS = date(2026, 4, 8), date(2026, 6, 23)   # +175-Fenster

con = sqlite3.connect(DB)
cur = con.cursor()


def lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))


def tagesprofil(d: date):
    """Saisonale Tagesparameter, linear über das Fenster interpoliert."""
    t = (d - VON).days / max(1, (BIS - VON).days)        # 0 (Apr 8) .. 1 (Jun 23)
    return {
        "sonnenaufgang": lerp(6.6, 5.25, t),             # h (CEST)
        "sonnenuntergang": lerp(19.9, 21.4, t),
        "pv_klar_kwh": lerp(60.0, 92.0, t),              # Tagessumme klarer Tag
        "temp_min": lerp(4.0, 13.0, t),
        "temp_max": lerp(15.0, 27.0, t),
    }


def pv_string_anteile(d: date):
    """Anteil je PV-Komponente (pv_*) am Tages-PV aus den Bestandsdaten."""
    rows = cur.execute(
        "SELECT komponenten FROM tages_energie_profil WHERE anlage_id=? AND datum=? AND komponenten IS NOT NULL",
        (ANLAGE, d.isoformat()),
    ).fetchall()
    summe = {}
    for (kj,) in rows:
        try:
            for k, v in json.loads(kj).items():
                if k.startswith("pv_") and isinstance(v, (int, float)):
                    summe[k] = summe.get(k, 0.0) + max(0.0, v)
        except (json.JSONDecodeError, TypeError):
            continue
    total = sum(summe.values())
    if total <= 0:
        return {"pv_6": 0.26, "pv_7": 0.31, "pv_8": 0.38, "pv_9": 0.05}
    return {k: v / total for k, v in summe.items()}


def bell_gewichte(aufgang: float, untergang: float):
    """Normierte stündliche PV-Gewichte (0 nachts, Glocke tagsüber)."""
    w = []
    for h in range(24):
        x = (h + 0.5 - aufgang) / max(0.5, (untergang - aufgang))
        # Exponent 2.2 → spitze Mittagskurve, sodass der Rohpeak an klaren Tagen
        # die WR-Grenze übersteigt (realistisches Clipping-Plateau bei ~10 kW).
        w.append(math.sin(math.pi * x) ** 2.2 if 0.0 < x < 1.0 else 0.0)
    s = sum(w) or 1.0
    return [x / s for x in w]


def temp_stunde(h, tmin, tmax):
    """Sinus-Tagesgang: Minimum ~5 Uhr, Maximum ~15 Uhr."""
    phase = math.cos((h - 15) / 24 * 2 * math.pi)        # +1 um 15 Uhr
    return round(tmin + (tmax - tmin) * (phase + 1) / 2, 1)


import random
tep_upd = tz_upd = tz_ins = 0
wp_gew = [w / sum(WP_PROFIL) for w in WP_PROFIL]          # normiertes WP-Stundenprofil
heiz_day: dict[str, float] = {}                          # therm. Heizung/Tag (für Snapshots)
ww_day: dict[str, float] = {}                            # therm. Warmwasser/Tag
d = VON
while d <= BIS:
    rng = random.Random(d.toordinal())                   # reproduzierbar je Tag
    prof = tagesprofil(d)
    anteile = pv_string_anteile(d)
    gew = bell_gewichte(prof["sonnenaufgang"], prof["sonnenuntergang"])

    # Wolkenfaktor: zu hellen Tagen geneigt (max zweier Uniforms), gelegentlich trüb.
    cf = 0.55 + 0.45 * max(rng.random(), rng.random())
    pv_ziel = prof["pv_klar_kwh"] * cf * rng.uniform(0.95, 1.05)
    pr = max(0.72, min(0.87, 0.87 - 0.13 * (1 - cf)))    # klar→0.87, trüb→tiefer

    # PV-Stundenkurve + WR-Clipping → tatsächliche Tagessumme (Clipping-Verlust).
    pv_arr = [min(pv_ziel * g, INV_MAX) for g in gew]
    pv_tag_ist = sum(pv_arr)
    strahlung_tag = pv_tag_ist / (pr * KWP) * 1000.0      # Wh/m², erfüllt PR-Formel
    tmin = prof["temp_min"]
    tmax = prof["temp_max"] - (1 - cf) * 6               # bewölkt = kühler

    # ── Wärmepumpe sommer-plausibel: Raumheizung temperaturabhängig (Juni ~0),
    #    Warmwasser ganzjährig; Strom = Wärme/COP → konsistente Tages-JAZ.
    #    verbrauch_kw bleibt unverändert (Energie-Bilanz!), nur die WP-Teil-Last
    #    + die thermischen Snapshots werden saisonal korrigiert. ────────────────
    temp_avg = (tmin + tmax) / 2
    heiz_therm = max(0.0, WP_BASIS_TEMP - temp_avg) * WP_HEIZ_FAKTOR
    wp_strom_tag = heiz_therm / COP_HEIZ + WP_WW_THERM / COP_WW
    heiz_day[d.isoformat()] = heiz_therm
    ww_day[d.isoformat()] = WP_WW_THERM

    # Tageszeilen einmal holen; Verbrauch bleibt unverändert (Historie).
    tagesrows = {
        r[0]: r for r in cur.execute(
            """SELECT stunde, verbrauch_kw, waermepumpe_kw, wallbox_kw, komponenten
               FROM tages_energie_profil WHERE anlage_id=? AND datum=?""",
            (ANLAGE, d.isoformat()),
        ).fetchall()
    }
    verbr = {h: (tagesrows[h][1] or 0.0) if h in tagesrows else 0.0 for h in range(24)}

    # EIN Speicher-Zyklus pro Tag: nur so viel laden, wie abends/nachts wieder
    # entladen wird → netto ~0 ⇒ Eigenverbrauch ≈ Verbrauch (nie > Verbrauch),
    # Wirkungsgrad ~95 %, Einspeisung ≈ Überschuss (statt dauerhaft geschluckt).
    ueberschuss_tag = sum(max(0.0, pv_arr[h] - verbr[h]) for h in range(24))
    # Speicher deckt das ABEND-/Nacht-Defizit (nach dem Laden) — nur so viel laden,
    # wie danach wieder entladen wird ⇒ Entladung ≤ Ladung, η ≈ 95 % (nie > 100 %),
    # ein sauberer Tageszyklus. Das kleine Früh-Defizit (Speicher morgens leer)
    # geht ans Netz — realistisch. Start leer; Überschuss/Kapazität begrenzen.
    nacht_defizit = sum(max(0.0, verbr[h] - pv_arr[h]) for h in range(15, 24))
    lade_budget = min(nacht_defizit / BATT_EFF, ueberschuss_tag, BATT_KWH)

    soc = 0.0                                            # je Tag frisch (ein Zyklus)
    rest_lade = lade_budget
    peak_pv = peak_einsp = peak_netz = 0.0
    str_summe = 0.0

    for h in range(24):
        row = tagesrows.get(h)
        verbrauch = verbr[h]
        pv = round(pv_arr[h], 3)
        ghi = round(strahlung_tag * gew[h], 1)
        str_summe += ghi

        # ── Speicher: tagsüber laden (bis Budget), sonst Überschuss einspeisen;
        #    Defizit aus dem Speicher decken, Rest aus dem Netz ───────────────
        net = pv - verbrauch
        if net > 0:
            laden = min(net, BATT_RATE, rest_lade, BATT_KWH - soc)
            soc += laden
            rest_lade -= laden
            batt = -round(laden, 3)                       # negativ = laden
            einsp = round(net - laden, 3)
            netz = 0.0
        elif net < 0:
            bedarf = -net
            liefer = min(bedarf, BATT_RATE, soc * BATT_EFF)
            soc -= liefer / BATT_EFF if BATT_EFF else 0.0
            batt = round(liefer, 3)                       # positiv = entladen (Busbar)
            netz = round(bedarf - liefer, 3)
            einsp = 0.0
        else:
            batt = einsp = netz = 0.0

        peak_pv = max(peak_pv, pv)
        peak_einsp = max(peak_einsp, einsp)
        peak_netz = max(peak_netz, netz)

        temp = temp_stunde(h, tmin, tmax)
        bewoelkung = round((1 - cf) * 100)
        wcode = 0 if cf > 0.85 else 1 if cf > 0.7 else 2 if cf > 0.55 else 3

        # ── komponenten neu: PV-Strings + Batterie, Verbraucher unverändert ──
        komp = {}
        try:
            komp = {k: v for k, v in json.loads((row[4] if row else "") or "{}").items()
                    if not k.startswith("pv_") and not k.startswith("batterie_")}
        except (json.JSONDecodeError, TypeError):
            komp = {}
        for k, anteil in anteile.items():
            komp[k] = round(pv * anteil, 3)
        komp["batterie_2"] = batt
        wp = round(wp_strom_tag * wp_gew[h], 3)           # WP-Strom sommer-niedrig
        komp["waermepumpe_4"] = -wp

        cur.execute(
            """UPDATE tages_energie_profil
               SET pv_kw=?, einspeisung_kw=?, netzbezug_kw=?, batterie_kw=?,
                   soc_prozent=?, ueberschuss_kw=?, defizit_kw=?, waermepumpe_kw=?,
                   temperatur_c=?, globalstrahlung_wm2=?, bewoelkung_prozent=?,
                   niederschlag_mm=?, wetter_code=?, komponenten=?
               WHERE anlage_id=? AND datum=? AND stunde=?""",
            (pv, einsp, netz, batt, round(soc / BATT_KWH * 100, 1),
             round(max(net, 0.0), 3), round(max(-net, 0.0), 3), wp,
             temp, ghi, bewoelkung, 0.0, wcode, json.dumps(komp),
             ANLAGE, d.isoformat(), h),
        )
        tep_upd += 1

    # ── TZ-Aggregate (tag-native Felder) konsistent setzen ───────────────────
    fields = dict(
        performance_ratio=round(pr, 3),
        peak_pv_kw=round(peak_pv, 3),
        peak_einspeisung_kw=round(peak_einsp, 3),
        peak_netzbezug_kw=round(peak_netz, 3),
        temperatur_min_c=round(tmin, 1),
        temperatur_max_c=round(tmax, 1),
        strahlung_summe_wh_m2=round(str_summe, 1),
        pv_prognose_kwh=round(pv_tag_ist / 0.95, 1),
        komponenten_kwh=json.dumps({"pv": round(pv_tag_ist, 2)}),
    )
    exists = cur.execute(
        "SELECT id FROM tages_zusammenfassung WHERE anlage_id=? AND datum=?",
        (ANLAGE, d.isoformat()),
    ).fetchone()
    if exists:
        cur.execute(
            f"UPDATE tages_zusammenfassung SET {', '.join(k+'=?' for k in fields)} WHERE id=?",
            (*fields.values(), exists[0]),
        )
        tz_upd += 1
    else:
        cols = "anlage_id, datum, stunden_verfuegbar, source_provenance, " + ", ".join(fields)
        cur.execute(
            f"INSERT INTO tages_zusammenfassung ({cols}) VALUES ({', '.join(['?']*(4+len(fields)))})",
            (ANLAGE, d.isoformat(), 24, "{}", *fields.values()),
        )
        tz_ins += 1

    d += timedelta(days=1)

# ── inv:4 Wärme-Snapshots saisonal neu (kumulative Tagesgrenzen) ──────────────
# Der Tag-Reseed baute heizenergie/warmwasser aus den (Winter-)WP-Werten → „Juni"
# zeigte ~49 kWh Heizung. Hier die Grenzen ab VON neu aufbauen, anschließend an
# den Bestand VOR dem Fenster (Kontinuität); Sommer-Heizung ~0, Tag-Diff = Tageswert.
for key, tagwert in (("inv:4:heizenergie_kwh", heiz_day),
                     ("inv:4:warmwasser_kwh", ww_day)):
    start = cur.execute(
        """SELECT wert_kwh FROM sensor_snapshots
           WHERE anlage_id=? AND sensor_key=? AND zeitpunkt<=?
           ORDER BY zeitpunkt DESC LIMIT 1""",
        (ANLAGE, key, f"{VON.isoformat()} 00:00:00"),
    ).fetchone()
    cum = start[0] if start else 0.0
    cur.execute(
        "DELETE FROM sensor_snapshots WHERE anlage_id=? AND sensor_key=? AND zeitpunkt>=?",
        (ANLAGE, key, f"{VON.isoformat()} 00:00:00"),
    )
    snaps, dd = [], VON
    while dd <= BIS:
        snaps.append((ANLAGE, key, f"{dd.isoformat()} 00:00:00", round(cum, 3), "ha_statistics"))
        cum += tagwert.get(dd.isoformat(), 0.0)
        dd += timedelta(days=1)
    snaps.append((ANLAGE, key, f"{(BIS + timedelta(days=1)).isoformat()} 00:00:00", round(cum, 3), "ha_statistics"))
    cur.executemany(
        "INSERT OR REPLACE INTO sensor_snapshots (anlage_id, sensor_key, zeitpunkt, wert_kwh, quelle) VALUES (?,?,?,?,?)",
        snaps,
    )

con.commit()
print(f"Sommer-Reseed {VON}..{BIS}: {tep_upd} TEP-Stunden, TZ {tz_upd} upd / {tz_ins} ins")
print("  WP-Wärme-Snapshots inv:4 neu: Heizung temperaturabhängig (Juni ~0), WW ganzjährig")

# Kurz-Kontrolle (Juni-Plausibilität)
for ym in ("2026-04", "2026-05", "2026-06"):
    r = cur.execute(
        """SELECT ROUND(SUM(pv_kw)/COUNT(DISTINCT datum),0),
                  ROUND(SUM(einspeisung_kw)/COUNT(DISTINCT datum),0),
                  ROUND(AVG(temperatur_c),1)
           FROM tages_energie_profil WHERE anlage_id=? AND datum LIKE ?||'%'""",
        (ANLAGE, ym),
    ).fetchone()
    print(f"  {ym}: PV ~{r[0]} kWh/Tag, Einspeisung ~{r[1]} kWh/Tag, Ø Temp {r[2]} °C")

con.close()
