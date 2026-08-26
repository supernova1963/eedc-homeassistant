"""Per-Zeilen-Resolver für monatliche per-Typ-IMD-Aggregate (Schläfer-Abbau Block 1).

Single Source of Truth dafür, **welche Felder** eine `InvestitionMonatsdaten`-
Zeile pro Investitions-Typ zu den Monats-Aggregaten beiträgt und **mit welchem
Resolver** sie gelesen werden. Vor dieser Konsolidierung dupliziert jede der
Read-Sites (`aktueller_monat`, `monatsdaten`-`/aggregiert`, `cockpit/komponenten`,
`cockpit/uebersicht`) dieselbe `if inv.typ == "..."`-Schleife — die größte
Drift-Klasse der Read-Pfade (Pool-Bug, #289, #290; siehe
`docs/drafts/archive/BLOCK1-FELD-MATRIX-20260614.md`).

Diese Funktion ist **rein** (kein DB-/Service-I/O, ADR-001): sie nimmt eine
Investition + ihr `verbrauch_daten`-Dict und gibt einen `ImdTypBeitrag` mit allen
kanonisch aufgelösten Skalar-Beiträgen zurück. Jede Read-Site faltet den Beitrag
in ihre eigene Form (flach / pro-Monat-Dict / kumuliert+by_ym) und nimmt die
Felder, die sie braucht. Aktiv-/Stilllegungs- und Dienstwagen-Filter bleiben
**Caller-Sache** (Verhalten je Site erhalten).

NICHT hier: der E-Mob-Heimladungs-**Pool** (`get_emob_heimladung_canonical` /
`compute_emob_pool_attribution`) — der braucht ALLE E-Auto-/Wallbox-Zeilen
zusammen und ist bereits SoT. Dieser Resolver liefert nur die per-Zeilen-
Skalare (km, Fahrverbrauch, V2H) sowie die roh-/kanonisch gelesenen Lade-
Felder, die einzelne Sites direkt (ohne Pool) verwenden.

D1-Entscheid (2026-06-14): WP-Heizung/Wärme werden hier **kanonisch** gelesen
(`get_wp_heizenergie_kwh` inkl. `heizung_kwh`-Legacy-Fallback; `wp_waerme` =
`waerme_kwh` oder `heizung + warmwasser`). Sites, die vorher roh lasen
(`/aggregiert`, Vorjahr-Variante), übernehmen damit die kanonische Semantik.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.core.berechnungen.betriebsart_gemessen import (
    betriebsart_nutzenergie_kwh,
    modus_strom_zeile,
)
from backend.core.berechnungen.modus_split import heizwaerme_ist_abgeleitet
from backend.core.berechnungen.waermepumpe_kennzahl import waerme_gesamt_kwh
from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD, MODUS_STROM_FELD
from backend.core.betriebsmodus import HEIZEN as _HEIZEN
from backend.core.betriebsmodus import KUEHLEN as _KUEHLEN
from backend.core.field_definitions import (
    get_eauto_ladung_kwh,
    get_pv_erzeugung_kwh,
    get_sonstiges_verbrauch_kwh,
    ist_zaehler_kategorie,
    get_speicher_netzladung_kwh,
    get_wp_heizenergie_kwh,
    get_wp_strom_kwh,
)
from backend.core.investition_parameter import abgrenzung_stoerung


@dataclass(frozen=True)
class ImdTypBeitrag:
    """Kanonisch aufgelöste Skalar-Beiträge EINER IMD-Zeile.

    Alle Felder default 0.0/0/False — pro Typ werden nur die relevanten gesetzt.
    `typ` erlaubt dem Caller typ-spezifische Faltung (z. B. Pool-Sammlung) ohne
    eigene `inv.typ`-Abfrage.
    """

    typ: str | None = None

    # PV-Module
    pv_erzeugung: float = 0.0

    # Balkonkraftwerk (BKW) — separat von pv-module gehalten; Caller entscheidet,
    # ob die BKW-Erzeugung zusätzlich in die Gesamt-PV einfließt.
    bkw_erzeugung: float = 0.0
    bkw_eigenverbrauch: float = 0.0
    bkw_speicher_ladung: float = 0.0
    bkw_speicher_entladung: float = 0.0

    # Speicher
    speicher_ladung: float = 0.0
    speicher_entladung: float = 0.0
    speicher_arbitrage: float = 0.0       # Netzladung (get_speicher_netzladung_kwh)
    speicher_ladepreis_cent: float = 0.0  # für gewichteten Ø Ladepreis

    # Wärmepumpe (kanonisch, D1)
    wp_strom: float = 0.0
    wp_heizung: float = 0.0
    wp_warmwasser: float = 0.0
    wp_waerme: float = 0.0
    wp_strom_heizen: float = 0.0
    wp_strom_warmwasser: float = 0.0
    wp_hat_split: bool = False            # getrennte_strommessung aktiv
    # #263 K-2 (S3): der Modus-Split. NICHT mit `wp_strom_heizen` verwechseln —
    # das ist der SUMMAND bei getrennter Strommessung (zwei physische Zähler),
    # dies hier sind TEILMENGEN von `wp_strom` (ein Zähler, Modus mitgeschrieben).
    # Genau diese Zweideutigkeit war der Grund für eigene Feldnamen (E-G).
    wp_modus_strom_heizen: float = 0.0
    wp_modus_strom_kuehlen: float = 0.0
    #: E4 (Konzept §2.3): **nur aus gemessenen Zählern.** Der abgeleitete Split
    #: kann sie nicht (``AUFGETEILTE_MODI``, D11) und lässt sie bei 0 — das ist
    #: die Aussage, keine Lücke. Sie sind *erfassbar, aber keine bewertete
    #: Funktion*: sie erscheinen in der Aufteilung und fallen über
    #: ``ModusStromZeile.funktionsfremd_kwh`` aus dem Nenner der Arbeitszahl.
    wp_modus_strom_lueften: float = 0.0
    wp_modus_strom_entfeuchten: float = 0.0
    #: W-5 (SOLL §4.1): die **Kältemenge** — abgegebene Nutzenergie im
    #: Kühlbetrieb. Bewusst nicht „waerme": im Kühlbetrieb ist die Nutzenergie
    #: Kälte, und ein Feldname, der etwas anderes behauptet als er trägt, ist
    #: die Klasse, an der `heizenergie_kwh` schon einmal missverstanden wurde
    #: (#120). **Nur gemessen** — es gibt keinen Weg, sie abzuleiten.
    #:
    #: ⚠ **Nur Kühlen von den vier Betriebsarten.** Heizen wäre redundant zu
    #: `heizenergie_kwh` (Wärmemengenzähler), Lüften und Entfeuchten sind nach
    #: E4 ausdrücklich **nicht bewertet** — für sie gibt es keine Kennzahl, für
    #: die man eine Nutzenergie bräuchte.
    wp_nutzenergie_kuehlen: float = 0.0
    wp_modus_abdeckung_h: float = 0.0
    #: #263 — die Aufteilung dieser Zeile ist **gemessen**, nicht abgeleitet.
    #: Trägt zwei Folgen: der aus dem Betriebsmodus gerechnete Split darf hier
    #: nicht zusätzlich angewandt werden (sonst steht die Menge zweimal), und
    #: die Aufteilung ist zu zeigen, obwohl `wp_modus_abdeckung_h` 0 ist —
    #: ein Zähler hat keine „Stunden mit Signal".
    wp_modus_gemessen: bool = False
    #: Der **Gesamtstrom dieser Zeile**, aber nur wenn sie einen Modus-Split
    #: trägt. Er ist die Bezugsgröße für „nicht aufgeteilt".
    #:
    #: ⚠ **Ohne ihn wird die Restmenge auf Anlagenebene falsch.** An einer
    #: Instanz gemessen: eine Anlage mit einer Klimaanlage (Split, 191,2 kWh)
    #: **und** einer Luft-Wasser-WP ohne Modus-Sensor (90 kWh) wies
    #: „nicht aufgeteilt 96,4 kWh" aus — 90 davon gehörten dem anderen Gerät,
    #: das gar keine Aufteilung hat. `Gesamt − Σ Teilmengen` ist nur je Gerät
    #: richtig; anlagenweit braucht es diesen Bezug.
    wp_modus_strom_bezug: float = 0.0
    # Der Anteil von `wp_waerme`, der aus `Strom × JAZ` stammt statt aus einem
    # Wärmemengenzähler (Konzept §3.4). Er trägt die JAZ-Sperre aus §3.5 zu
    # allen Lesestellen — ohne ihn müsste jede Stelle die Provenance selbst
    # lesen, und die erste, die es vergisst, zeigt die gepflegte JAZ als
    # gemessene an.
    wp_waerme_abgeleitet: float = 0.0
    # R2/W-7 + R2/F12 (SOLL Wärme/Klima §3.2b): Die vom Anwender gemeldete
    # Abgrenzungs-Störung dieses Geräts — `"fremdstrom"`, `"fremdwaerme"` oder
    # `None`. Sie hängt am **Gerät**, nicht an der Monatszeile: ein Heizstab am
    # WP-Zähler bleibt es auch im nächsten Monat.
    #
    # ⚠ Sie ändert **keine Menge**. Sie sagt nur, dass Zähler und Nutzen dieses
    # Geräts für verschiedene Dinge stehen — die Mengen bleiben, die Kennzahl
    # entfällt (SOLL §4.2: „die Mengen und den Grund, nie den Quotienten").
    wp_abgrenzung: Optional[str] = None

    # E-Mobilität (Skalar-Summen; Heimladungs-Pool bleibt separat)
    eauto_km: float = 0.0
    eauto_verbrauch: float = 0.0          # gemessener Fahrverbrauch
    eauto_v2h: float = 0.0
    eauto_ladung_kanonisch: float = 0.0   # get_eauto_ladung_kwh (Vorjahr-max-Logik)
    eauto_ladung_pv_netz: float = 0.0     # ladung_pv + ladung_netz (/aggregiert)
    wallbox_ladung: float = 0.0
    wallbox_ladung_pv: float = 0.0

    # Sonstiges
    sonstiges_erzeugung: float = 0.0
    sonstiges_verbrauch: float = 0.0
    # C1d: die Detail-Größen der Sonstiges-Zeile. Sie folgen derselben
    # Kategorie-Regel wie `erzeugung`/`verbrauch` — ein Erzeuger hat keinen
    # Bezug, ein Verbraucher speist nicht ein. Bis C1d las die Monatsroute sie
    # roh und ohne Kategorie aus `verbrauch_daten`; genau diese Doppel-Lesart
    # ist die Klasse, gegen die P10 gebaut ist.
    sonstiges_eigenverbrauch: float = 0.0
    sonstiges_einspeisung: float = 0.0
    sonstiges_bezug_pv: float = 0.0
    sonstiges_bezug_netz: float = 0.0
    #: Konzept §9 Weg 2: Erlös DIESES Erzeugers in € (eigener Einspeisetarif,
    #: den eedc nicht kennen kann — es gibt einen Satz je Anlage). Folgt der
    #: Kategorie-Regel wie Eigenverbrauch/Einspeisung: ein Verbraucher hat
    #: keinen Einspeise-Erlös.
    sonstiges_einspeise_erloes_euro: float = 0.0


def _f(data: dict, key: str) -> float:
    """`data.get(key)` als float mit 0-Default (None/fehlend → 0.0)."""
    return float(data.get(key, 0) or 0)


def imd_typ_beitrag(
    inv, data: dict | None, source_provenance: dict | None = None
) -> ImdTypBeitrag:
    """Kanonischer per-Zeilen-Beitrag einer IMD-Zeile (`inv`, `data`).

    `inv` braucht `typ` und (für WP-Split) `parameter`. `data` ist das
    `verbrauch_daten`-Dict (oder None/{}).

    `source_provenance` ist optional und wird **nur** für die Frage gebraucht,
    ob die Heizwärme gemessen oder abgeleitet ist (#263 K-2, Konzept §3.5).
    Ohne sie bleibt `wp_waerme_abgeleitet` 0 — das ist der bisherige Zustand
    und für jede Zeile ohne Modus-Split auch der richtige. Die Funktion bleibt
    damit rein: sie liest ein zweites Dict, sie holt es nicht.
    """
    data = data or {}
    typ = getattr(inv, "typ", None)

    if typ == "pv-module":
        return ImdTypBeitrag(typ=typ, pv_erzeugung=_f(data, "pv_erzeugung_kwh"))

    if typ == "balkonkraftwerk":
        return ImdTypBeitrag(
            typ=typ,
            bkw_erzeugung=get_pv_erzeugung_kwh(data),
            bkw_eigenverbrauch=_f(data, "eigenverbrauch_kwh"),
            bkw_speicher_ladung=_f(data, "speicher_ladung_kwh"),
            bkw_speicher_entladung=_f(data, "speicher_entladung_kwh"),
        )

    if typ == "speicher":
        return ImdTypBeitrag(
            typ=typ,
            speicher_ladung=_f(data, "ladung_kwh"),
            speicher_entladung=_f(data, "entladung_kwh"),
            speicher_arbitrage=get_speicher_netzladung_kwh(data),
            speicher_ladepreis_cent=_f(data, "speicher_ladepreis_cent"),
        )

    if typ == "waermepumpe":
        params = getattr(inv, "parameter", None) or {}
        hat_split = bool(params.get("getrennte_strommessung"))
        heizung = get_wp_heizenergie_kwh(data)
        warmwasser = _f(data, "warmwasser_kwh")
        # D1: waerme_kwh hat Vorrang, sonst Heizung + Warmwasser (kanonisch).
        # Seit 2026-08-26 im Layer-SoT `waermepumpe_kennzahl.waerme_gesamt_kwh`
        # — der Client hatte dieselbe Regel als zweite Stelle (Befund W-9).
        waerme = waerme_gesamt_kwh(_f(data, "waerme_kwh"), heizung, warmwasser)
        # F-56: die Weiche liegt im Layer-SoT `modus_strom_zeile` — sie stand
        # bis dahin hier inline und war im HA-Export daneben nachgebaut, ohne
        # den Gemessen-Zweig. Eine Regel, zwei Codestellen, eine Drift.
        _modus = modus_strom_zeile(data)
        _gemessen = _modus.gemessen
        return ImdTypBeitrag(
            typ=typ,
            wp_strom=get_wp_strom_kwh(data, params),
            wp_heizung=heizung,
            wp_warmwasser=warmwasser,
            wp_waerme=waerme,
            wp_strom_heizen=_f(data, "strom_heizen_kwh"),
            wp_strom_warmwasser=_f(data, "strom_warmwasser_kwh"),
            wp_hat_split=hat_split,
            # #263 — **gemessen schlägt abgeleitet** (ADR-002/P8), und zwar
            # **ganz oder gar nicht je Zeile**.
            #
            # ⚠ Der naheliegende Weg wäre je Betriebsart: Kühlen gemessen,
            # Heizen aus dem Modus nachgereicht. Er ist beim Durchspielen der
            # Varianten durchgefallen — dann steht in **einem** Balken die
            # eine Hälfte aus einem Zähler und die andere aus einer Rechnung,
            # während `wp_modus_gemessen` für beide „gemessen" sagt. Ein
            # halbwahres Etikett ist schlechter als eine fehlende Zahl
            # (ADR-002/P4). Wer Kühlen misst und Heizen nicht, sieht Heizen
            # deshalb nicht in dieser Zeile — nicht als 0 mit falscher
            # Herkunft.
            #
            # Zugleich ist es die Regel, die `monats_fakten` für den
            # *gerechneten* Split ohnehin schon anwendet (`hat_gemessene_
            # betriebsart` sperrt ihn je Gerät). Beide Wege sagen jetzt
            # dasselbe, statt sich je nach Fläche zu unterscheiden.
            wp_modus_strom_heizen=_modus.heizen_kwh,
            wp_modus_strom_kuehlen=_modus.kuehlen_kwh,
            wp_modus_strom_lueften=_modus.lueften_kwh,
            wp_modus_strom_entfeuchten=_modus.entfeuchten_kwh,
            wp_nutzenergie_kuehlen=(
                betriebsart_nutzenergie_kwh(data, _KUEHLEN) or 0.0
            ),
            wp_modus_abdeckung_h=_f(data, MODUS_ABDECKUNG_FELD),
            wp_modus_gemessen=_gemessen,
            wp_modus_strom_bezug=(
                get_wp_strom_kwh(data, params)
                if (_f(data, MODUS_ABDECKUNG_FELD) > 0 or _gemessen) else 0.0
            ),
            # Ist die Heizwärme abgeleitet, ist der abgeleitete Anteil die
            # ganze Heizwärme dieser Zeile — es gibt keine Mischung je Zeile.
            wp_waerme_abgeleitet=(
                heizung if heizwaerme_ist_abgeleitet(source_provenance) else 0.0
            ),
            wp_abgrenzung=abgrenzung_stoerung(params),
        )

    if typ == "e-auto":
        return ImdTypBeitrag(
            typ=typ,
            eauto_km=_f(data, "km_gefahren"),
            eauto_verbrauch=_f(data, "verbrauch_kwh"),
            eauto_v2h=_f(data, "v2h_entladung_kwh"),
            eauto_ladung_kanonisch=get_eauto_ladung_kwh(data),
            eauto_ladung_pv_netz=_f(data, "ladung_pv_kwh") + _f(data, "ladung_netz_kwh"),
        )

    if typ == "wallbox":
        return ImdTypBeitrag(
            typ=typ,
            wallbox_ladung=_f(data, "ladung_kwh"),
            wallbox_ladung_pv=_f(data, "ladung_pv_kwh"),
        )

    if typ == "sonstiges":
        params = getattr(inv, "parameter", None) or {}
        kategorie = params.get("kategorie", "")
        erzeugung = _f(data, "erzeugung_kwh")
        verbrauch = get_sonstiges_verbrauch_kwh(data)
        # C1d: Detail-Größen. Eigenverbrauch/Einspeisung gehören zur
        # Erzeugerseite, Bezug PV/Netz zur Verbraucherseite — sie werden
        # zusammen mit ihrer Hauptgröße stummgeschaltet, sonst trüge ein
        # Erzeuger einen Netzbezug, den seine eigene Zeile gar nicht ausweist.
        eigenverbrauch = _f(data, "eigenverbrauch_kwh")
        einspeisung = _f(data, "einspeisung_kwh")
        bezug_pv = _f(data, "bezug_pv_kwh")
        bezug_netz = _f(data, "bezug_netz_kwh")
        erloes_euro = _f(data, "einspeise_erloes_euro")
        if ist_zaehler_kategorie(kategorie):
            # #377 — ein Zähler trägt **nichts** zur Energiebilanz bei, und das
            # steht hier ausdrücklich statt sich aus leeren Feldern zu ergeben.
            #
            # ⚠ **Der Unterschied ist nicht akademisch.** Ein neu angelegter
            # Zähler hat ohnehin keine Energiefelder — aber wer ein
            # BESTEHENDES *Sonstiges*-Gerät auf „Zähler" umstellt (etwa weil er
            # den Gasverbrauch bisher als Verbraucher gepflegt hat), trägt
            # seine alten `verbrauch_sonstig_kwh`-Zeilen weiter in der
            # IMD-Zeile. Ohne diesen Zweig liefen sie unverändert in
            # Hausverbrauch und Autarkie ein — die Kategorie sagte „kein
            # Strom", die Zahlen sagten weiter etwas anderes.
            erzeugung = verbrauch = 0.0
            eigenverbrauch = einspeisung = 0.0
            bezug_pv = bezug_netz = 0.0
            erloes_euro = 0.0
        elif kategorie == "erzeuger":
            verbrauch = 0.0
            bezug_pv = bezug_netz = 0.0
        elif kategorie == "verbraucher":
            erzeugung = 0.0
            eigenverbrauch = einspeisung = 0.0
            # Ein Verbraucher speist nicht ein und hat deshalb auch keinen
            # Einspeise-Erlös — dieselbe Stummschaltung wie oben (C1d).
            erloes_euro = 0.0
        # sonst (leere Kategorie): beide Werte mitnehmen (Site-3-Verhalten)
        return ImdTypBeitrag(
            typ=typ,
            sonstiges_erzeugung=erzeugung,
            sonstiges_verbrauch=verbrauch,
            sonstiges_eigenverbrauch=eigenverbrauch,
            sonstiges_einspeisung=einspeisung,
            sonstiges_bezug_pv=bezug_pv,
            sonstiges_bezug_netz=bezug_netz,
            sonstiges_einspeise_erloes_euro=erloes_euro,
        )

    return ImdTypBeitrag(typ=typ)
