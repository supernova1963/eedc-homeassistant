"""Energie-Profil — Monatsauswertung.

GET /api/energie-profil/{anlage_id}/monat — Heatmap + KPIs + Peaks + Kategorien (auch Quelle des Monatsberichts)

Dazu `ENERGIE_KATEGORIEN`, der Backend-Spiegel von `frontend/src/lib/colors.ts::ENERGIE_KATEGORIE`
(gehalten durch `npm run check:spiegel-backend`, das diese Datei liest).
"""
# Reiner Umzug aus `api/routes/energie_profil/views.py` (18.09.2026, Vorlage 4 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `views.py` haengt den Router ein und
# exportiert die Endpunkt-Namen weiter, die Aufrufer und Tests bisher von dort importierten.

import calendar
import re
from collections import defaultdict
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.berechnungen import bilanz_aus_stundenrows, monatsbilanz_aus_tagen
from backend.core.berechnungen.spannen import verbrauch_gebuendelt, zeile_gebuendelt
from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.einspeise_erloes_service import neg_preis_einspeisung_tageswert
from ._shared import (
    HeatmapZelle,
    KategorieSumme,
    KomponentenEintrag,
    MonatsAuswertungResponse,
    PeakStunde,
    TagesprofilStunde,
    _key_to_serie_info,
    detail_kategorie,
)

router = APIRouter()


#: Energie-Kategorien der Monatsauswertung: Schlüssel → (Label, Gruppe).
#:
#: **Spiegel von** ``frontend/src/lib/colors.ts::ENERGIE_KATEGORIE`` — dessen
#: Docstring nennt diese Datei seit jeher als „Backend-Producer", die Schlüssel
#: lagen hier aber als **funktionslokale Literale** in
#: :func:`get_monatsauswertung`, und **Labels gab es backendseitig gar nicht**.
#: Der Monatsbericht braucht sie (PDF/Markdown haben kein `lib/colors.ts`), und
#: eine dritte Liste im Builder wäre die Drift, die ``check:label-maps`` im
#: Frontend gerade verhindert. ⇒ Schlüssel und Label stehen hier zusammen,
#: die lokalen Sets leiten sich daraus ab.
#:
#: Der dritte Eintrag ist die **Farbe als Hex** — der Client führt an dieser
#: Stelle Tailwind-Klassen (``bg-amber-400``), ein PDF braucht den Ton selbst.
#: ⛔ **Keine neuen Töne:** jeder Wert stammt aus der Komponenten-Identität in
#: ``lib/colors.ts`` (``KOMPONENTEN_FARBEN`` bzw. ``SONSTIGES_ERZEUGER_FARBE``),
#: auf die die Client-Map verweist. Beim ersten Bau standen hier drei
#: **erfundene** Farben (Cyan fürs Balkonkraftwerk, Grau für sonstige Erzeuger,
#: Blau für die Wallbox) — Regel 0a („eine Datenrolle = eine Farbe") war damit
#: zwischen Bildschirm und PDF gebrochen, ohne dass ein Prüfer es sah.
#:
#: Der Abgleich mit der Client-Map hält ``npm run check:spiegel-backend`` fest —
#: **einschließlich der Farbe**, aufgelöst über die Konstante, auf die die
#: Client-Map zeigt.
ENERGIE_KATEGORIEN: dict[str, tuple[str, str, str]] = {
    "pv_module": ("PV-Module", "erzeuger", "#f59e0b"),
    "bkw": ("Balkonkraftwerk", "erzeuger", "#fbbf24"),
    "sonstige_erzeuger": ("Sonstige Erzeuger", "erzeuger", "#84cc16"),
    "waermepumpe": ("Wärmepumpe", "verbraucher", "#ef4444"),
    "wallbox_eauto": ("Wallbox / E-Auto", "verbraucher", "#06b6d4"),
    "haushalt": ("Restverbrauch", "verbraucher", "#64748b"),  # N-603: Label, Schlüssel bleibt
    "sonstige_verbraucher": ("Sonstige Verbraucher", "verbraucher", "#6b7280"),
    # §9.2 (05.09.2026) — Abgabe an Dritte: Verwendungsseite, aber kein
    # Eigenverbrauch; dieselbe Farbe wie das Sonstiges-Gerät (Regel 0a).
    "sonstige_abgabe": ("Abgabe an Dritte", "verbraucher", "#6b7280"),
}

@router.get("/{anlage_id}/monat", response_model=MonatsAuswertungResponse)
async def get_monatsauswertung(
    anlage_id: int,
    jahr: int = Query(..., ge=2000, le=2100),
    monat: int = Query(..., ge=1, le=12),
    top_n: int = Query(10, ge=1, le=50, description="Anzahl Peak-Stunden (Netzbezug/Einspeisung)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Monatsauswertung aus TagesEnergieProfil + TagesZusammenfassung.

    Liefert Heatmap-Matrix (Tag × Stunde), KPIs, Peak-Stunden,
    Batterie-Vollzyklen-Summe und Ø Performance Ratio für einen Kalendermonat.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    tage_im_monat = calendar.monthrange(jahr, monat)[1]
    von = date(jahr, monat, 1)
    bis = date(jahr, monat, tage_im_monat)

    # Stundenwerte des Monats laden
    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    stunden_rows = result.scalars().all()

    # Tageszusammenfassungen (für Batterie-Zyklen + PR)
    result = await db.execute(
        select(TagesZusammenfassung)
        .where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        )
    )
    tag_rows = result.scalars().all()

    # ── Heatmap + Summen aggregieren ──
    heatmap: list[HeatmapZelle] = []
    # Die Summen und Quoten kommen seit „Zählerlücken wie HA" aus der
    # Tagesfaltung unten (R8) — die Schleife sammelt nur noch Heatmap, Profil,
    # Spitzen und die PV je Tag.

    tage_mit_daten: set[date] = set()
    pv_pro_tag: dict[date, float] = defaultdict(float)

    # Für typisches Tagesprofil: Ø pro Stunde
    profil_pv: dict[int, list[float]] = defaultdict(list)
    profil_verbrauch: dict[int, list[float]] = defaultdict(list)
    # Für Grundbedarf: Nachtstunden 0–5 Uhr
    nacht_verbrauch: list[float] = []

    # Datenqualität (Issue #135): Zähle Stunden mit NULL-Werten
    # als Signal an UI, dass kumulativer Zähler fehlt/lückenhaft ist.
    stunden_fehlend_pv = 0
    stunden_fehlend_verbrauch = 0

    # Peaks sammeln — alle Einträge, später sortieren
    netzbezug_kandidaten: list[PeakStunde] = []
    einspeisung_kandidaten: list[PeakStunde] = []
    peak_pv: Optional[PeakStunde] = None

    for r in stunden_rows:
        tage_mit_daten.add(r.datum)

        # NULL-Handling: Stunde ohne gemapptem Zähler → nicht als 0 zählen
        pv = r.pv_kw
        verbrauch = r.verbrauch_kw
        einspeisung = r.einspeisung_kw
        netzbezug = r.netzbezug_kw

        if pv is None:
            stunden_fehlend_pv += 1
        if verbrauch is None:
            stunden_fehlend_verbrauch += 1

        # PV je Tag (Tagesverteilung): NULL überspringt still, statt 0 zu zählen
        if pv is not None:
            pv_pro_tag[r.datum] += pv

        # Überschuss der Stunde (Heatmap) nur wenn beide Werte da
        ueberschuss: Optional[float] = None
        if pv is not None and verbrauch is not None:
            ueberschuss = pv - verbrauch

        # Profilsammlung. ⚠ Zählerlücken wie HA (§2): eine Zeile, die auf der
        # Achse mehr als eine reale Stunde trägt, ist keine Stunden-Stichprobe —
        # sie fällt aus Profil, Grundbedarf und Spitzen (ihre Energie bleibt in
        # jeder Summe).
        if pv is not None and not zeile_gebuendelt(r, "pv"):
            profil_pv[r.stunde].append(pv)
        if verbrauch is not None and not verbrauch_gebuendelt(r):
            profil_verbrauch[r.stunde].append(verbrauch)
            if 0 <= r.stunde < 5:
                nacht_verbrauch.append(verbrauch)

        heatmap.append(HeatmapZelle(
            tag=r.datum.day,
            stunde=r.stunde,
            pv_kw=round(pv, 3) if pv is not None else None,
            verbrauch_kw=round(verbrauch, 3) if verbrauch is not None else None,
            netzbezug_kw=round(netzbezug, 3) if netzbezug is not None else None,
            einspeisung_kw=round(einspeisung, 3) if einspeisung is not None else None,
            ueberschuss_kw=round(ueberschuss, 3) if ueberschuss is not None else None,
        ))

        if r.netzbezug_kw is not None and r.netzbezug_kw > 0 and not zeile_gebuendelt(r, "netzbezug"):
            netzbezug_kandidaten.append(PeakStunde(
                datum=r.datum, stunde=r.stunde, wert_kw=round(r.netzbezug_kw, 3),
            ))
        if r.einspeisung_kw is not None and r.einspeisung_kw > 0 and not zeile_gebuendelt(r, "einspeisung"):
            einspeisung_kandidaten.append(PeakStunde(
                datum=r.datum, stunde=r.stunde, wert_kw=round(r.einspeisung_kw, 3),
            ))
        if r.pv_kw is not None and r.pv_kw > 0 and not zeile_gebuendelt(r, "pv"):
            if peak_pv is None or r.pv_kw > peak_pv.wert_kw:
                peak_pv = PeakStunde(
                    datum=r.datum, stunde=r.stunde, wert_kw=round(r.pv_kw, 3),
                )

    netzbezug_kandidaten.sort(key=lambda p: p.wert_kw, reverse=True)
    einspeisung_kandidaten.sort(key=lambda p: p.wert_kw, reverse=True)

    # ── KPIs ──
    # Beide Quoten über den Layer-SoT (ADR-001) statt inline: die Formeln standen
    # hier ausgeschrieben und stimmten, aber dieselbe Kennzahl inline zu rechnen
    # ist genau der Weg, auf dem N129 entstanden ist — an der dritten Stelle
    # (Tagesvorschau) wich der Zähler ab, und kein Test sah es.
    #
    # ⚑ **N-92 (2026-08-22): beide Quoten stehen auf einer DIFFERENZ**, und eine
    # Differenz erbt die Unvollständigkeit jedes Summanden
    # (`KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3 Regel 1). Die Summen darüber
    # überspringen NULL-Stunden korrekt — die Differenz erbte das nicht: fehlten
    # der Einspeisung Stunden und der PV keine, war der Eigenverbrauch um genau
    # die ungemessene Einspeisung zu hoch, und war der Netzbezug **gar nicht**
    # erfasst, meldete die Autarkie **100 %**. Der Zwilling im Tages-Layer trägt
    # die Begründung ausführlich; hier steht dieselbe Regel, damit die beiden
    # Sichten nicht auseinanderlaufen (die N-129-Klasse).
    #
    # ⭐ **Zählerlücken wie HA (R8, Vorlage Fassung 7): der Monat faltet
    # TAGESbilanzen**, nicht mehr die rohen Stunden. Jeder Tag rechnet nach
    # seiner Regelmarke (R7 mit Marke, N-92 ohne — E6); der Monat summiert
    # die Mengen, nimmt als Verbrauch Σ der Tages-Gesamtverbräuche und
    # unterdrückt EV/Autarkie nur, wenn kein Tag die Achse hat, ein Tag etwas
    # verworfen hat oder ein Altbestandstag schon unterdrückt war. Ein
    # Total-Fall-Tag propagiert nicht (W4). Die eigene N-92-Zählung dieser
    # Route (`pv_n`/`pv_ein_n`/…) ist damit entfallen — sie war der dritte
    # Ort derselben Regel.
    stunden_je_tag: dict[date, list] = defaultdict(list)
    for r in stunden_rows:
        stunden_je_tag[r.datum].append(r)
    tz_je_tag = {t.datum: t for t in tag_rows}
    # HA-Bauform E4a-2 (Umschaltstelle 4): je Tag EINE Quellenwahl der Bilanz-Gruppe — ein Kanal-Tag bringt Mengen,
    # Eigenverbrauch und Quoten aus den Kanälen (Weg 2, kein Deckel), die stundengepaarten Größen aus den Stunden
    # (B-3, D4). Der Monat faltet die Tage über dieselbe Layer-Funktion wie `monats_aus_tagen.falte_monat`.
    from backend.services.kanal.bilanz_leser import bilanz_ziele, kanal_tage, mische_bilanz, mische_komponenten

    kanal_je_tag = await kanal_tage(db, anlage_id, von, bis)
    ziele_je_tag = await bilanz_ziele(db, anlage_id, kanal_je_tag) if kanal_je_tag else {}

    def _tagesbilanz(d):
        b = bilanz_aus_stundenrows(stunden_je_tag.get(d, []),
                                   verworfen=(tz_je_tag[d].verworfen if d in tz_je_tag else None))
        return mische_bilanz(kanal_je_tag[d].bilanz, b) if d in kanal_je_tag else b

    mb = monatsbilanz_aus_tagen(
        _tagesbilanz(d) for d in sorted(set(stunden_je_tag) | set(kanal_je_tag))
    )
    for d, k in kanal_je_tag.items():
        if k.bilanz.pv_erfasst:
            pv_pro_tag[d] = k.bilanz.erzeugung_kwh
    pv_sum = mb.erzeugung_kwh
    einspeisung_sum = mb.einspeisung_kwh
    netzbezug_sum = mb.netzbezug_kwh
    verbrauch_sum = mb.gesamtverbrauch_kwh or 0.0
    ueberschuss_sum = mb.ueberschuss_kwh
    defizit_sum = mb.defizit_kwh
    direkt_sum = mb.direktverbrauch_kwh
    batt_lade_sum = mb.speicher_ladung_kwh
    batt_entlade_sum = mb.speicher_entladung_kwh
    autarkie = round(mb.autarkie_prozent, 1) if mb.autarkie_prozent is not None else None
    eigenverbrauch = round(mb.ev_quote_prozent, 1) if mb.ev_quote_prozent is not None else None

    grundbedarf = (
        round(sum(nacht_verbrauch) / len(nacht_verbrauch), 3)
        if nacht_verbrauch else None
    )
    batt_wirkungsgrad = (
        round(batt_entlade_sum / batt_lade_sum, 3)
        if batt_lade_sum > 0.1 else None
    )

    # Tagesverteilung PV
    pv_tage = [v for v in pv_pro_tag.values() if v > 0]
    pv_best = round(max(pv_tage), 2) if pv_tage else None
    pv_schlecht = round(min(pv_tage), 2) if pv_tage else None
    pv_schnitt = round(sum(pv_tage) / len(pv_tage), 2) if pv_tage else None

    # Typisches Tagesprofil (Ø pro Stunde)
    tagesprofil: list[TagesprofilStunde] = []
    for s in range(24):
        pv_werte = profil_pv.get(s, [])
        vb_werte = profil_verbrauch.get(s, [])
        tagesprofil.append(TagesprofilStunde(
            stunde=s,
            pv_kw=round(sum(pv_werte) / len(pv_werte), 3) if pv_werte else None,
            verbrauch_kw=round(sum(vb_werte) / len(vb_werte), 3) if vb_werte else None,
        ))

    # ── Batterie-Vollzyklen + PR + Börsenpreis aus TagesZusammenfassung ──
    zyklen_werte = [t.batterie_vollzyklen for t in tag_rows if t.batterie_vollzyklen is not None]
    zyklen_summe = round(sum(zyklen_werte), 2) if zyklen_werte else None

    pr_werte = [t.performance_ratio for t in tag_rows if t.performance_ratio is not None]
    pr_avg = round(sum(pr_werte) / len(pr_werte), 3) if pr_werte else None
    # A6: der Nenner des Ø gehört mit ausgeliefert — er ist `len(pr_werte)` und
    # NICHT `tage_mit_daten` (das zählt Tage mit irgendwelchen Daten).
    pr_tage = len(pr_werte) if pr_werte else None

    # Börsenpreis / Negativpreis (§51 EEG)
    boersen_werte = [t.boersenpreis_avg_cent for t in tag_rows if t.boersenpreis_avg_cent is not None]
    boersenpreis_avg = round(sum(boersen_werte) / len(boersen_werte), 2) if boersen_werte else None
    neg_stunden_werte = [t.negative_preis_stunden for t in tag_rows if t.negative_preis_stunden is not None]
    neg_stunden_summe = sum(neg_stunden_werte) if neg_stunden_werte else None
    # §51-Menge nur bei Anlagen mit gesetztem Schalter (Gate im Erlös-Service);
    # `negative_preis_stunden` oben bleibt ungegatet — Marktinfo, kein Abzug.
    neg_einsp_werte = [
        w for w in (
            neg_preis_einspeisung_tageswert(anlage, t.einspeisung_neg_preis_kwh)
            for t in tag_rows
        ) if w is not None
    ]
    neg_einsp_summe = round(sum(neg_einsp_werte), 2) if neg_einsp_werte else None

    # ── Per-Komponente Aggregation aus komponenten_kwh ──
    # Investments für Label-Auflösung laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    inv_map: dict[int, Investition] = {
        inv.id: inv for inv in inv_result.scalars().all()
    }

    komponenten_sum: dict[str, float] = defaultdict(float)
    _komp_je_tag = {t.datum: t.komponenten_kwh for t in tag_rows}
    for d, k in kanal_je_tag.items():
        _komp_je_tag[d] = mische_komponenten(_komp_je_tag.get(d), k, ziele_je_tag.get(d, set()))
    for _d, _komp in sorted(_komp_je_tag.items()):
        if not _komp:
            continue
        for k, v in _komp.items():
            if v is not None:
                komponenten_sum[k] += v

    # Einträge auflösen + Anteile berechnen. Detail-Kategorie-Mapping liegt im
    # Shared-Helper `detail_kategorie` (ADR-001 testbar, #316).
    komponenten_liste: list[KomponentenEintrag] = []
    kategorie_sum: dict[str, float] = defaultdict(float)

    for key, kwh in komponenten_sum.items():
        info = _key_to_serie_info(key, inv_map)
        if not info:
            continue
        inv = None
        m = re.match(r'^[a-z]+_(\d+)(?:_[a-z]+)?$', key)
        if m:
            inv = inv_map.get(int(m.group(1)))
        det_kat = detail_kategorie(info, inv)
        kategorie_sum[det_kat] += kwh
        komponenten_liste.append(KomponentenEintrag(
            key=key,
            label=info["label"],
            kategorie=det_kat,
            typ=info["typ"],
            seite=info["seite"],
            kwh=round(kwh, 2),
            anteil_prozent=None,  # später setzen
        ))

    # Anteile: Erzeuger → vom Gesamt-PV, Senken → vom Gesamt-Verbrauch
    for e in komponenten_liste:
        if e.seite == "quelle" and pv_sum > 0:
            e.anteil_prozent = round(abs(e.kwh) / pv_sum * 100, 1)
        elif e.seite == "senke" and verbrauch_sum > 0:
            e.anteil_prozent = round(abs(e.kwh) / verbrauch_sum * 100, 1)

    # Sortieren: Erzeuger zuerst (absteigend), dann Verbraucher (absteigend nach Betrag)
    komponenten_liste.sort(key=lambda e: (
        0 if e.seite == "quelle" else (1 if e.seite == "senke" else 2),
        -abs(e.kwh),
    ))

    kategorien_liste: list[KategorieSumme] = []
    ERZEUGER_KAT = {k for k, (_, g, _f) in ENERGIE_KATEGORIEN.items() if g == "erzeuger"}
    VERBRAUCHER_KAT = {k for k, (_, g, _f) in ENERGIE_KATEGORIEN.items() if g == "verbraucher"}
    # Bidirektionale Kategorien (speicher, netz) werden nicht als Erzeuger/Verbraucher-KPI ausgewiesen,
    # tauchen aber in der Geräteliste weiter unten auf.
    BIDI_KAT = {"speicher", "netz"}
    for kat, kwh in sorted(kategorie_sum.items(), key=lambda kv: -abs(kv[1])):
        if kat in BIDI_KAT:
            continue
        anteil = None
        if kat in ERZEUGER_KAT and pv_sum > 0:
            anteil = round(abs(kwh) / pv_sum * 100, 1)
        elif kat in VERBRAUCHER_KAT and verbrauch_sum > 0:
            anteil = round(abs(kwh) / verbrauch_sum * 100, 1)
        kategorien_liste.append(KategorieSumme(
            kategorie=kat,
            kwh=round(kwh, 2),
            anteil_prozent=anteil,
        ))

    return MonatsAuswertungResponse(
        jahr=jahr,
        monat=monat,
        tage_im_monat=tage_im_monat,
        tage_mit_daten=len(tage_mit_daten),
        pv_kwh=round(pv_sum, 2),
        verbrauch_kwh=round(verbrauch_sum, 2),
        einspeisung_kwh=round(einspeisung_sum, 2),
        netzbezug_kwh=round(netzbezug_sum, 2),
        ueberschuss_kwh=round(ueberschuss_sum, 2),
        defizit_kwh=round(defizit_sum, 2),
        autarkie_prozent=autarkie,
        eigenverbrauch_prozent=eigenverbrauch,
        performance_ratio_avg=pr_avg,
        performance_ratio_tage=pr_tage,
        batterie_vollzyklen_summe=zyklen_summe,
        grundbedarf_kw=grundbedarf,
        batterie_ladung_kwh=round(batt_lade_sum, 2) if batt_lade_sum > 0 else None,
        batterie_entladung_kwh=round(batt_entlade_sum, 2) if batt_entlade_sum > 0 else None,
        batterie_wirkungsgrad=batt_wirkungsgrad,
        direkt_eigenverbrauch_kwh=round(direkt_sum, 2) if direkt_sum > 0 else None,
        pv_tag_best_kwh=pv_best,
        pv_tag_schnitt_kwh=pv_schnitt,
        pv_tag_schlecht_kwh=pv_schlecht,
        typisches_tagesprofil=tagesprofil,
        kategorien=kategorien_liste,
        komponenten=komponenten_liste,
        peak_netzbezug=netzbezug_kandidaten[:top_n],
        peak_einspeisung=einspeisung_kandidaten[:top_n],
        peak_pv=peak_pv,
        heatmap=heatmap,
        boersenpreis_avg_cent=boersenpreis_avg,
        negative_preis_stunden=neg_stunden_summe,
        einspeisung_neg_preis_kwh=neg_einsp_summe,
        stunden_fehlend_pv=stunden_fehlend_pv,
        stunden_fehlend_verbrauch=stunden_fehlend_verbrauch,
    )
