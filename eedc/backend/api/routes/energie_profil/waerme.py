"""Energie-Profil — Waerme/Klima-Verlauf und -Verteilung (Konzept Waerme/Klima §8).

GET /api/energie-profil/{anlage_id}/waerme-verlauf         — Tagesreihe des Verlaufs (Cockpit → Monat)
GET /api/energie-profil/{anlage_id}/waerme-verlauf-stunden — 24 Stunden eines Tages (Cockpit → Tag)
GET /api/energie-profil/{anlage_id}/waerme-verteilung      — Verteilung des Waerme/Klima-Stroms (Tag · Monat · Jahr)
"""
# Reiner Umzug aus `api/routes/energie_profil/views.py` (18.09.2026, Vorlage 4 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `views.py` haengt den Router ein und
# exportiert die Endpunkt-Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.exceptions import bad_request, not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from ._shared import (
    VerteilungPeriodeResponse,
    VerteilungSegmentResponse,
    VerteilungVerlaufResponse,
    WaermeVerlaufStundeResponse,
    WaermeVerlaufStundenResponse,
    WaermeVerlaufTagResponse,
)

router = APIRouter()


@router.get(
    "/{anlage_id}/waerme-verlauf",
    response_model=list[WaermeVerlaufTagResponse],
)
async def get_waerme_verlauf(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """Die Tagesreihe des Wärme/Klima-Verlaufs für *Cockpit → Monat*.

    **Warum eine eigene Route neben ``/tage-werte``** (Konzept §8, Bauschnitt 4):
    Jene Route beliefert fünf Konsumenten — die Monats- und die Tagessicht, die
    Auswertungen-Tabelle mit bis zu 366 Tagen und den Monatsbericht — und ihr
    Schema ist an die Frontend-Registry gekoppelt. Ihr ``wp_strom`` ist die Σ
    der Stundenspalte ``waermepumpe_kw`` — ⚠ hier stand bis 11.09.2026
    „Leistungspfad", richtig ist: **Zählerpfad im Rückwärts-Raster**; der
    Unterschied zu ``komponenten_kwh`` ist das Fenster (N-434). Der Verlauf
    nimmt ``komponenten_kwh``, weil die Aufteilung darunter damit rechnet.
    Zwei Zahlen für dieselbe Größe in **einem** Bild wären genau W-17b, den
    dietmar1968 gemeldet hat.

    ⚠ **Der Zeitraum ist auf einen Monat begrenzt.** Die Wärme entsteht aus
    Zähler-Randständen; über ein Jahr wären das Reihen, die niemand für eine
    Linie braucht — die Jahressicht hat ihre eigene Quelle (Monatszeilen).
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    if (bis - von).days > 31:
        raise bad_request("Zeitraum darf maximal 31 Tage umfassen")

    from backend.services.energie_profil.waerme_verlauf import lade_waerme_verlauf

    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}
    zeilen = await lade_waerme_verlauf(
        db, anlage, investitionen_by_id, von, bis,
    )
    return [
        WaermeVerlaufTagResponse(
            datum=z.datum,
            wp_strom_kwh=z.strom_kwh,
            wp_waerme_kwh=z.waerme_kwh,
            wp_kaelte_kwh=z.kaelte_kwh,
            temperatur_c=(
                round(z.temperatur_c, 1) if z.temperatur_c is not None else None
            ),
            # ⚠ **Alles-oder-nichts je Tag** — dieselbe Bauform wie in der
            # Tagesantwort: Wo es keine Aufteilung gibt, stehen `None` statt
            # sechs Nullen. Eine Null sähe aus wie „nichts gelaufen", während
            # die Kachel Strom zeigt.
            wp_modus_strom_heizen_kwh=(
                round(z.stapel.heizen_kwh, 2) if z.stapel.hat_split else None
            ),
            wp_modus_strom_warmwasser_kwh=(
                round(z.stapel.warmwasser_kwh, 2) if z.stapel.hat_split else None
            ),
            wp_modus_strom_kuehlen_kwh=(
                round(z.stapel.kuehlen_kwh, 2) if z.stapel.hat_split else None
            ),
            wp_modus_strom_lueften_kwh=(
                round(z.stapel.lueften_kwh, 2) if z.stapel.hat_split else None
            ),
            wp_modus_strom_entfeuchten_kwh=(
                round(z.stapel.entfeuchten_kwh, 2) if z.stapel.hat_split else None
            ),
            wp_modus_nicht_aufgeteilt_kwh=(
                round(z.stapel.nicht_aufgeteilt_kwh, 2) if z.stapel.hat_split else None
            ),
            wp_modus_strom_bezug_kwh=(
                round(z.stapel.bezug_kwh, 2) if z.stapel.hat_split else None
            ),
            wp_modus_abdeckung_h=(
                round(z.stapel.abdeckung_h, 1) if z.stapel.hat_split else None
            ),
            wp_modus_gemessen=z.stapel.hat_gemessen if z.stapel.hat_split else None,
        )
        for z in zeilen
    ]

@router.get(
    "/{anlage_id}/waerme-verlauf-stunden",
    response_model=WaermeVerlaufStundenResponse,
)
async def get_waerme_verlauf_stunden(
    anlage_id: int,
    datum: date = Query(..., description="Tag (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """Der Wärme/Klima-Verlauf von *Cockpit → Tag* — 24 Stunden (Bauschnitt 5).

    **Warum eine eigene Route und nicht ``tag-detail``** (Entscheid Gernot
    11.09.2026): ``tag-detail`` wird im Client mit ``.catch(() => null)``
    geladen — ein Fehler im Stundenteil nähme den ganzen Wärmepumpen-Block des
    Tages mit. Und die Stundenform kostet beim ersten Aufruf je Zähler 25
    Stände; die Kacheln sollen darauf nicht warten. Präzedenz: der Monat.

    ⭐ **Die Stunde verteilt den Tag** (``core/berechnungen/tages_stapel.py``):
    dieselbe Geräte-Auswahl wie ``tag-detail`` (``beitraege_des_tages``), dieselbe
    Tageszeile, dasselbe Fenster (N-434/N-435) — die Summe der 24 Stunden ist
    der Balken darunter. Temperatur liefert die Stundenantwort, nicht diese.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    from backend.core.berechnungen import waermepumpe_kwh_je_investition
    from backend.core.berechnungen.tages_stapel import (
        STUNDEN,
        StundenFormen,
        beitraege_des_tages,
        verteile_felder_auf_stunden,
        verteile_tages_stapel_auf_stunden,
    )
    from backend.core.berechnungen.waermepumpe_kennzahl import (
        geraete_mit_gesamtwaerme,
    )
    from backend.services.energie_profil import (
        lade_modus_split_tag,
        lade_modus_stunden_tag,
    )
    from backend.services.snapshot.aggregator import (
        TAGESDETAIL_AUSGABE,
        WAERME_AUSGABE_KEYS,
        get_betriebsart_strom_tageswerte,
        get_tagesdetail_kwh,
        get_wp_strom_stufe_je_investition,
    )
    from backend.services.snapshot.boundary_range import tageszeile_ist_rueckwaerts
    from backend.services.snapshot.keys import extract_quellen_energy, feld_hat_zaehler
    from backend.services.snapshot.komponenten_beitraege import investition_beitraege
    from backend.services.snapshot.reader import mqtt_zaehler_keys
    from backend.services.snapshot.stunden_leser import lade_stundenformen

    inv_result = await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))
    investitionen_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}

    # ── Der Tag: dieselben Eingänge wie `tag-detail` ─────────────────────────
    tz_zeile = (await db.execute(
        select(
            TagesZusammenfassung.komponenten_kwh,
            TagesZusammenfassung.source_provenance,
            TagesZusammenfassung.verworfen,
        ).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum == datum,
        )
    )).one_or_none()
    tz_rueckwaerts = tageszeile_ist_rueckwaerts(
        tz_zeile[1] if tz_zeile else None, tz_zeile[2] if tz_zeile else None,
    )
    wp_kwh_je_inv = waermepumpe_kwh_je_investition((tz_zeile[0] if tz_zeile else None) or {})
    gemessen_je_inv = await get_betriebsart_strom_tageswerte(
        db, anlage, investitionen_by_id, datum, rueckwaerts=tz_rueckwaerts,
    )
    beitraege = beitraege_des_tages(
        gemessen_je_inv, wp_kwh_je_inv,
        await lade_modus_split_tag(db, anlage_id, datum),
        investitionen_by_id, datum,
        # N-462: dieselbe Stufe wie im Tag-Detail — sonst nennt derselbe Tag
        # zwei verschiedene Abzüge.
        stufe_je_inv=await get_wp_strom_stufe_je_investition(
            db, anlage, investitionen_by_id,
        ),
    )
    detail = await get_tagesdetail_kwh(
        db, anlage, investitionen_by_id, datum,
        tageszeile_rueckwaerts=tz_rueckwaerts,
    )

    # ── Die Form: je Zähler die 24 Slots aus derselben Standreihe ───────────
    mapping = (anlage.sensor_mapping or {}).get("investitionen", {}) or {}
    quellen_energy = extract_quellen_energy(anlage)
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)

    def _zaehler(inv_id: str, feld: str):
        cfg = ((mapping.get(inv_id) or {}).get("felder") or {}).get(feld)
        key = f"inv:{inv_id}:{feld}"
        if not feld_hat_zaehler(cfg, key, quellen_energy, mqtt_keys):
            return None
        return key, (cfg.get("sensor_id") if isinstance(cfg, dict) else None)

    zaehler: dict[str, tuple[str, object]] = {}
    gesamt_felder: dict[str, list[str]] = {}
    for b in beitraege:
        if not b.gemessen:
            continue
        for feld in b.felder:
            z = _zaehler(b.inv_id, feld)
            if z:
                zaehler[z[0]] = z
        inv = investitionen_by_id.get(b.inv_id)
        felder_cfg = (mapping.get(b.inv_id) or {}).get("felder") or {}
        gesamt_felder[b.inv_id] = [
            beitrag.feld for beitrag in investition_beitraege(
                inv, mapping.get(b.inv_id) or {},
                ist_verfuegbar=lambda f, _c=felder_cfg, _i=b.inv_id: feld_hat_zaehler(
                    _c.get(f), f"inv:{_i}:{f}", quellen_energy, mqtt_keys,
                ),
            )
        ]
        for feld in gesamt_felder[b.inv_id]:
            z = _zaehler(b.inv_id, feld)
            if z:
                zaehler[z[0]] = z
    # ── Linien (Wärme, Kälte): nur die Felder, die den TAGESWERT trugen ──
    # N-437: Bis 11.09.2026 las diese Schleife die Form JEDES zugeordneten
    # Wärmezählers — auch eines Geräts, dessen Tageswert wegen Rücksprung oder
    # Tagesreset verworfen war —, und nur das exakte Gerätefeld (Kälte je
    # Innengerät bekam keine Form). `felder_je_inv` ist genau die Schlüsselmenge,
    # mit der der Tag aufgelöst hat.
    # ⭐ Seit WK-09 B2 stehen hier auch die **Funktions**-Zähler
    # (`strom_heizen_kwh`/`strom_warmwasser_kwh`, SOLL §3.3/S2a). Sie brauchen
    # dieselbe Stundenform aus derselben Standreihe wie die Linien — eine
    # zweite Leseschleife wäre die F-56-Klasse.
    verteilte_felder = {
        ausgabe: detail.felder_je_inv.get(ausgabe, {})
        for ausgabe in (
            *sorted(WAERME_AUSGABE_KEYS), "wp_waerme_kwh", "wp_kaelte_kwh",
            "wp_strom_heizen_kwh", "wp_strom_warmwasser_kwh",
        )
    }
    for je_inv in verteilte_felder.values():
        for inv_id, felder in je_inv.items():
            for feld in felder:
                z = _zaehler(inv_id, feld)
                if z:
                    zaehler[z[0]] = z
    formen_je_key = await lade_stundenformen(db, anlage, datum, list(zaehler.values()))

    def _summe_je_slot(keys: list[str]) -> list:
        reihen = [formen_je_key[k] for k in keys if k in formen_je_key]
        if not reihen:
            return [None] * STUNDEN
        return [
            (sum(r[h] for r in reihen if r[h] is not None)
             if any(r[h] is not None for r in reihen) else None)
            for h in range(STUNDEN)
        ]

    modus_stunden, _ = await lade_modus_stunden_tag(db, anlage_id, datum)
    formen = StundenFormen(
        felder_je_inv={
            b.inv_id: {
                feld: formen_je_key.get(f"inv:{b.inv_id}:{feld}", [None] * STUNDEN)
                for feld in b.felder
            }
            for b in beitraege if b.gemessen
        },
        gesamt_je_inv={
            inv_id: _summe_je_slot([f"inv:{inv_id}:{f}" for f in felder])
            for inv_id, felder in gesamt_felder.items()
        },
        modus_stunden_je_inv=modus_stunden,
    )
    verteilung = verteile_tages_stapel_auf_stunden(beitraege, formen)

    # ── Linien: je Gerät, je Feld verteilt, je Stunde aufgelöst (N-437) ────
    # Die Bauform des Stapels (`verteile_felder_auf_stunden`). Was keine Form
    # hat, wird NICHT still fallen gelassen, sondern je Größe genannt
    # (`*_ohne_stundenform_kwh`, Entscheid E6 (a), BS5 W1).
    # ⛔ Hier stand bis 11.09.2026: „Fehlt einem Schlüssel die Form, bekommt er
    # KEINE Linie" — die ganze Wärme eines Keys verschwand, und die Linie war
    # kleiner als die Kachel, ohne Hinweis (gemessen: Tag 7,0, Linie 2,0).
    # S4 bleibt gewahrt: Ohne jede verteilte Menge entsteht keine Linie aus
    # Nullen — dann steht nur der genannte Rest da.
    basis_je_ausgabe = {
        ausgabe: feld for (t, feld), ausgabe in TAGESDETAIL_AUSGABE.items()
        if t == "waermepumpe"
    }

    def _linie(ausgaben, *, nur_geraete=None) -> tuple[list, float]:
        """Eine Linie über die genannten Ausgabe-Keys.

        ``nur_geraete`` schränkt **je Ausgabe-Key** auf eine Geräte-Menge ein
        (fehlt der Key darin, zählen alle Geräte). Die Wärme braucht das, weil
        D1 je Gerät entscheidet, WELCHE Zähler es zeichnen — s. u.
        """
        summe = [0.0] * STUNDEN
        ohne_linie = 0.0
        for ausgabe in ausgaben:
            je_inv = verteilte_felder.get(ausgabe) or {}
            _erlaubt = (nur_geraete or {}).get(ausgabe)
            if _erlaubt is not None:
                je_inv = {i: f for i, f in je_inv.items() if i in _erlaubt}
            werte, rest = verteile_felder_auf_stunden(
                je_inv,
                {
                    inv_id: {
                        f: formen_je_key.get(f"inv:{inv_id}:{f}", [None] * STUNDEN)
                        for f in felder
                    }
                    for inv_id, felder in je_inv.items()
                },
                basis_je_ausgabe[ausgabe],
            )
            summe = [summe[h] + werte[h] for h in range(STUNDEN)]
            ohne_linie += rest
        return (summe if sum(summe) > 1e-9 else [None] * STUNDEN), ohne_linie

    # N-391/D1 — **Gesamtwert vor Summanden, auch in der Linie.** Der gemeinsame
    # Wärmemengenzähler steht bewusst NICHT in `WAERME_AUSGABE_KEYS`: die Menge
    # dort wird **summiert**, und ein Gerät mit Gesamtzähler UND Aufteilung
    # zeichnete seine Wärme dann zweimal. Gemessen wird deshalb dieselbe
    # Vorrangfrage wie im Monat — trug der Gesamtzähler den Tageswert, ist er
    # die Linie; sonst sind es die beiden Achsen.
    #
    # ⛔ **N-391b: die Frage wird je GERÄT gestellt, nicht für die Anlage.** Hier
    # stand bis zum 14.09.2026 ein Alles-oder-nichts: *trägt IRGENDEIN Gerät
    # `wp_waerme_kwh`, zeichne für ALLE nur den Gesamtschlüssel.* Bei zwei
    # verschieden zählenden Wärmepumpen fiel damit die ganze Wärme der zweiten
    # aus der Linie — sie stand weder im Balken noch im genannten Rest, weil das
    # Feld gar nicht erst gelesen wurde. Jetzt bekommt jedes Gerät den Zähler,
    # den D1 für es wählt: die Summe je Slot ist Σ je Gerät nach D1.
    _gesamt_geraete = geraete_mit_gesamtwaerme(
        detail.werte_je_inv.get("wp_waerme_kwh"),
    )
    _achsen_geraete = frozenset(
        inv_id
        for key in WAERME_AUSGABE_KEYS
        for inv_id in (verteilte_felder.get(key) or {})
    ) - _gesamt_geraete
    waerme_je_slot, waerme_ohne = _linie(
        (*sorted(WAERME_AUSGABE_KEYS), "wp_waerme_kwh"),
        nur_geraete={
            **{key: _achsen_geraete for key in WAERME_AUSGABE_KEYS},
            "wp_waerme_kwh": _gesamt_geraete,
        },
    )
    kaelte_je_slot, kaelte_ohne = _linie(("wp_kaelte_kwh",))

    # ── Der Funktions-Stapel (WK-09 B2, SOLL §3.3/S2a) ─────────────────────
    #
    # **Dieselbe Verteilung wie die Linien**, nur eine andere Familie: Heizen und
    # Warmwasser sind **Summanden** des Gesamtstroms, während der Betriebsart-
    # Stapel darüber **Teilmengen** führt (SOLL §3.2). Beide gleichzeitig zu
    # stapeln hieße, Teilmengen zu Summanden zu addieren — deshalb schaltet der
    # Verlauf um, statt zu überlagern (S2a), und deshalb tragen die Felder
    # eigene Namen.
    #
    # ⚠ `_linie` gibt `[None] * 24` zurück, wenn nichts verteilt wurde. Für einen
    # **Stapel** ist das kein brauchbarer Eingang (eine Stunde ohne Warmwasser
    # ist eine echte 0, keine fehlende Aussage) — die Segmente werden deshalb
    # unten gegen `funktions_stapel_verfuegbar` aufgelöst, wie der
    # Betriebsart-Stapel gegen `hat_split`.
    funk_heizen, funk_heizen_ohne = _linie(("wp_strom_heizen_kwh",))
    funk_ww, funk_ww_ohne = _linie(("wp_strom_warmwasser_kwh",))
    # „Nach Funktion" gibt es nur, wo Funktions-Zähler gepflegt sind — sonst hat
    # die Sicht nichts zu sagen (S2a). Maßgeblich ist der TAGESWERT, nicht die
    # Stundenform: ein Zähler ohne Form wird unten genannt, nicht verschwiegen.
    funktions_stapel_verfuegbar = any(
        (detail.werte.get(k) or 0.0) > 0.0
        for k in ("wp_strom_heizen_kwh", "wp_strom_warmwasser_kwh")
    )
    funktion_ohne = funk_heizen_ohne + funk_ww_ohne

    # Die Zählerspalte des Slots — ihre Summe ist die Kachel „Strom verbraucht".
    wp_kw = {
        r.stunde: r.waermepumpe_kw
        for r in (await db.execute(
            select(TagesEnergieProfil.stunde, TagesEnergieProfil.waermepumpe_kw).where(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum == datum,
            )
        )).all()
    }

    def _r(v: float, hat: bool, stellen: int = 3):
        return round(v, stellen) if hat else None

    def _funktions_segmente(h: int) -> dict:
        """Die drei Segmente der Funktions-Sicht eines Slots.

        ⭐ **Die Stapelhöhe ist der Gesamtstrom** (SOLL §3.3/S2a, K1): `uebrige`
        füllt auf, was die Funktions-Zähler nicht erklären — Standby, ein
        zweites Gerät ohne solche Zähler. Bezug ist **`wp_strom_kwh` dieses
        Slots**, also genau die Größe, deren Summe die Kachel „Strom
        verbraucht" ist; hier entsteht kein zweiter Gesamtstrom.

        ⚠ **`bezug_kwh` des Betriebsart-Stapels wäre hier falsch:** die Größe
        zählt nur Geräte, die eine **Betriebsart**-Aufteilung beigesteuert
        haben. Ein Gerät mit Funktions-Zählern, aber ohne Betriebsart-Zähler und
        ohne Modus-Signal (Sprosse **F5**) trägt dort 0 bei — der Rest wäre
        negativ, und genau diese Lage ist der Anlass von B2.
        """
        if not funktions_stapel_verfuegbar:
            return {}
        heizen = funk_heizen[h] or 0.0
        warmwasser = funk_ww[h] or 0.0
        gesamt = wp_kw.get(h)
        return {
            "wp_funktion_strom_heizen_kwh": round(heizen, 3),
            "wp_funktion_strom_warmwasser_kwh": round(warmwasser, 3),
            # Ohne Gesamtstrom in diesem Slot gibt es keinen Rest zu benennen —
            # `None` heißt „keine Aussage", nicht 0 (ADR-002/P4).
            "wp_funktion_uebrige_kwh": (
                round(max(0.0, gesamt - heizen - warmwasser), 3)
                if gesamt is not None else None
            ),
        }

    zeilen = []
    for h, s in enumerate(verteilung.stunden):
        hat = s.hat_split
        zeilen.append(WaermeVerlaufStundeResponse(
            stunde=h,
            wp_strom_kwh=(round(wp_kw[h], 3) if wp_kw.get(h) is not None else None),
            wp_waerme_kwh=(
                round(waerme_je_slot[h], 3) if waerme_je_slot[h] is not None else None
            ),
            wp_kaelte_kwh=(
                round(kaelte_je_slot[h], 3) if kaelte_je_slot[h] is not None else None
            ),
            wp_modus_strom_heizen_kwh=_r(s.heizen_kwh, hat),
            wp_modus_strom_warmwasser_kwh=_r(s.warmwasser_kwh, hat),
            wp_modus_strom_kuehlen_kwh=_r(s.kuehlen_kwh, hat),
            wp_modus_strom_lueften_kwh=_r(s.lueften_kwh, hat),
            wp_modus_strom_entfeuchten_kwh=_r(s.entfeuchten_kwh, hat),
            wp_modus_nicht_aufgeteilt_kwh=_r(s.nicht_aufgeteilt_kwh, hat),
            wp_modus_strom_bezug_kwh=_r(s.bezug_kwh, hat),
            wp_modus_abdeckung_h=_r(s.abdeckung_h, hat, 1),
            wp_modus_gemessen=s.hat_gemessen if hat else None,
            **_funktions_segmente(h),
        ))
    ohne = verteilung.ohne_stundenform_kwh
    return WaermeVerlaufStundenResponse(
        stunden=zeilen,
        ohne_stundenform_kwh=round(ohne, 2) if ohne > 0.005 else None,
        waerme_ohne_stundenform_kwh=round(waerme_ohne, 2) if waerme_ohne > 0.005 else None,
        kaelte_ohne_stundenform_kwh=round(kaelte_ohne, 2) if kaelte_ohne > 0.005 else None,
        funktions_stapel_verfuegbar=funktions_stapel_verfuegbar,
        funktion_ohne_stundenform_kwh=(
            round(funktion_ohne, 2) if funktion_ohne > 0.005 else None
        ),
    )

@router.get(
    "/{anlage_id}/waerme-verteilung",
    response_model=VerteilungVerlaufResponse,
)
async def get_waerme_verteilung(
    anlage_id: int,
    sicht: str = Query(
        ..., description="tag | monat | jahr — die Cockpit-Sicht",
    ),
    jahr: Optional[int] = Query(None, description="Jahr (Sicht monat/jahr)"),
    monat: Optional[int] = Query(None, description="Monat 1–12 (Sicht monat)"),
    datum: Optional[date] = Query(None, description="Tag (Sicht tag)"),
    db: AsyncSession = Depends(get_db),
):
    """Verteilung des Wärme/Klima-Stroms und ihr Verlauf (WK-16c).

    **Eine Route für alle drei Cockpit-Sichten** — die Auflösung der Perioden
    folgt aus ``sicht`` (Jahr → Monate, Monat → Tage, Tag → Stunden). Drei
    Routen wären dreimal dieselbe Regel; die Rechnung selbst steht ohnehin an
    **einer** Stelle (``services/waerme_verteilung.py``).

    ⚠ **Sie lädt NEBEN der Sicht**, wie der Wärme/Klima-Verlauf daneben: Bleibt
    sie aus, fehlt genau dieser Blockteil und sonst nichts.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    if sicht not in ("tag", "monat", "jahr"):
        raise bad_request("sicht muss tag, monat oder jahr sein")
    if sicht in ("monat", "jahr") and jahr is None:
        raise bad_request("jahr ist für diese Sicht erforderlich")
    if sicht == "monat" and not (monat and 1 <= monat <= 12):
        raise bad_request("monat (1–12) ist für die Monatssicht erforderlich")
    if sicht == "tag" and datum is None:
        raise bad_request("datum ist für die Tagessicht erforderlich")

    from backend.services.waerme_verteilung import lade_verteilung_verlauf

    v = await lade_verteilung_verlauf(
        db, anlage, sicht=sicht, jahr=jahr, monat=monat, datum=datum,
    )
    return VerteilungVerlaufResponse(
        sicht=v.sicht,
        stufe=v.stufe,
        segmente=[VerteilungSegmentResponse(**vars(s)) for s in v.segmente],
        perioden=[VerteilungPeriodeResponse(**vars(p)) for p in v.perioden],
        menge_kwh=v.menge_kwh,
        aufgeteilt_kwh=v.aufgeteilt_kwh,
        kosten_gesamt_euro=v.kosten_gesamt_euro,
        verlauf_kwh=v.verlauf_kwh,
        ohne_stundenform_kwh=v.ohne_stundenform_kwh,
    )
