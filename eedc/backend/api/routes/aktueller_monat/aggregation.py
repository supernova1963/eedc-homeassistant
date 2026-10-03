"""Aggregation von *Cockpit → Monat*: die Investitions-Felder je Typ auf Anlagenebene, der E-Mob-Heimlade-Pool, die
Werte-Extraktion (mit `get_val`) und die berechneten Bilanzwerte.
"""
# Vorlage 2 des Refactorings grosser Dateien (18.09.2026): Abschnitte des Endpunkts
# `get_aktueller_monat` byte-identisch als Funktionen, Schnittstelle als Schluesselwort-
# Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel — Gate ist
# `plans/skript-golden-master-aktueller-monat.py` (alte gegen neue Antworten, bitgleich).
from typing import Optional
from backend.core.berechnungen.waermepumpe_kennzahl import heizwaerme_kwh, waerme_gesamt_kwh
from backend.core.berechnungen import (
    berechne_verbrauchs_kennzahlen,
    erzeugung_hinter_zaehler_kwh,
)
from backend.services.monats_fakten import pv_unvollstaendig_hinweis
from backend.core.betriebsmodus import (
    BETRIEBSART_NUTZENERGIE_FELD,
    BETRIEBSART_STROM_FELD,
    HEIZEN as BM_HEIZEN,
    MESSBARE_MODI,
)
from backend.core.field_definitions import (
    FEINE_STROM_FELDER,
    basis_feld_key,
    get_wp_strom_kwh,
    wp_strom_aufteilung,
)
from backend.core.investition_parameter import ist_dienstlich


#: Der Schluessel, unter dem die **Vorausloesung** der Waerme je Geraet ihr
#: Ergebnis in ``resolved`` ablegt (N-391/D1, 14.09.2026).
#:
#: ⚠ **Kein Registry-Feld und keine Groesse der Anlage** — er entsteht in dieser
#: Route und lebt nur zwischen ``_wp_waerme_d1`` und ``typ_aggregation``. Der
#: Praefix ``_`` haelt ihn auseinander von den Feldnamen aus
#: ``INVESTITION_FELDER``, die in ``resolved`` daneben stehen; ein Sensor- oder
#: MQTT-Feld dieses Namens gibt es nicht und darf es nicht geben, sonst
#: ueberschriebe eine Quelle die aufgeloeste Zahl.
_WP_WAERME_D1_SUFFIX: str = "_waerme_d1_kwh"

#: Der Zwilling auf der **Strom**seite: der Schluessel, unter dem die
#: K3-Vorausloesung je Geraet ihr Ergebnis ablegt (N-451b, 14.09.2026).
#:
#: ⚠ Dieselbe Warnung wie oben — **kein Registry-Feld**, kein Sensor- oder
#: MQTT-Name; er lebt nur zwischen ``_wp_strom_k3`` und ``typ_aggregation``.
_WP_STROM_K3_SUFFIX: str = "_strom_k3_kwh"

def aggregiere_typen(*, investitionen, jahr, monat, resolved, teilzeitraum):
    """Investitions-Felder in Top-Level aggregieren (typabhaengig) — inkl. der D1-/K3-Vorausloesung je Waermepumpe.

    Aus `get_aktueller_monat` Zeilen 754-1019 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── Investitions-Felder in Top-Level aggregieren (typabhängig) ──
    # Nur aggregieren wenn kein direkter Top-Level-Wert existiert (sonst Doppelzählung!)
    # Direkte Werte kommen z.B. aus gespeicherten Aggregaten oder MQTT pv_gesamt_kwh.
    # Werte sind **Tupel von Zielfeldern** — ein Investitionsfeld darf in mehr
    # als eine Top-Level-Größe einlaufen (siehe BKW unten).
    typ_aggregation: dict[str, dict[str, tuple[str, ...]]] = {
        "pv-module": {"pv_erzeugung_kwh": ("pv_erzeugung_kwh",)},
        "speicher": {
            "ladung_kwh": ("speicher_ladung_kwh",),
            "entladung_kwh": ("speicher_entladung_kwh",),
        },
        "waermepumpe": {
            # ⛔ **Der Strom steht hier NICHT als drei Summanden.**
            # `stromverbrauch_kwh`, `strom_heizen_kwh` und
            # `strom_warmwasser_kwh` standen bis 14.09.2026 alle drei an dieser
            # Stelle und wurden **addiert** — der Gesamtzaehler UND die
            # Aufteilung darunter. Die Lesetuer `get_wp_strom_kwh`
            # (K3, `wp_strom_aufteilung`) tut genau das nicht: ein
            # Gesamtzaehler IST die Menge (K1), die feinen Achsen stehen
            # daneben — addiert wird nie, ersetzt schon.
            # Gemessen ueber die echte Route (eine WP, HA-Statistik liefert
            # 1000 + 600 + 400, `getrennte_strommessung=True`):
            # `wp_strom_kwh` **2000 statt 1000**, `wp_jaz` **1,5 statt 3,0** —
            # den ganzen laufenden Monat lang, und beim Monatsabschluss heilte
            # es sich von selbst (der DB-Zweig geht durch dieselbe Lesetuer und
            # nennt fuer dieselben Werte 1000/3,0). Die Anlage sah halb so gut
            # aus, wie sie ist.
            # ⚠ Das Kennzeichen half nicht: ohne `getrennte_strommessung` sind
            # die feinen Felder gar keine Summanden — die Tabelle addierte sie
            # trotzdem (gemessen: ebenfalls 2000).
            # K3 faellt deshalb **je Geraet** in `_wp_strom_k3` unten; hier
            # steht nur noch dessen Ergebnis, und diese Tabelle summiert es.
            _WP_STROM_K3_SUFFIX: ("wp_strom_kwh",),
            # ⛔ **Die Waerme steht hier NICHT als zwei (oder drei) Summanden.**
            # `heizenergie_kwh` und `warmwasser_kwh` standen bis 14.09.2026 an
            # dieser Stelle, `waerme_kwh` fehlte ganz — wer seine Waerme ueber
            # EINEN Waermemengenzaehler fuehrt (Feld seit WK-14b) und fuer den
            # laufenden Monat noch keine gespeicherte Zeile hat, sah in
            # *Cockpit → Monat* **keine Waerme** (gemessen: `wp_waerme_kwh`
            # None statt 3000). `waerme_kwh` als dritten Summanden nachzutragen
            # waere die Gegenrichtung desselben Fehlers: Wer Gesamtzaehler
            # **und** Aufteilung pflegt, zaehlte 3000 + 2100 + 900 = 6000.
            # D1 faellt deshalb **je Geraet** in `_wp_waerme_d1` unten; hier
            # steht nur noch dessen Ergebnis, und diese Tabelle summiert es —
            # wie im DB-Zweig, wo `monats_fakten` je IMD-Zeile aufloest und
            # erst danach addiert.
            _WP_WAERME_D1_SUFFIX: ("wp_waerme_kwh",),
        },
        # E-Auto und Wallbox NICHT hier — sie messen denselben Stromfluss aus
        # zwei Perspektiven (Vehicle vs. Loadpoint). Aufsummieren über beide
        # Typen würde Pool-Doppelzählung produzieren (Joachim/Gernot
        # 2026-05-02). Aggregation passiert unten in `emob_heimladung_pool`
        # über den SoT `get_emob_heimladung_canonical` — dieselbe strukturelle
        # Regel wie Monats-Fakten und `cockpit/uebersicht.py`.
        # BKW zählt in ZWEI Größen, und das ist keine Doppelzählung:
        # `bkw_erzeugung_kwh` ist die **eigene Zeile** (ROI/Finanz — dort hat das
        # BKW eine getrennte Position, s. [[project_bkw_erzeuger_abgrenzung]]),
        # `pv_erzeugung_kwh` ist die **PV-Achse der Anlage**. Der Kanon verlangt
        # beides: `monats_fakten.ErzeugungFakten.pv_kwh` ist ausdrücklich
        # „Module + Balkonkraftwerk", und der DB-Zweig oben (`_collect_saved_data`)
        # setzt `pv_erzeugung_kwh = fakt.erzeugung.pv_kwh` genau so.
        # ⛔ Bis 2026-08-14 stand hier nur `bkw_erzeugung_kwh` — dadurch fehlte das
        # BKW in der PV-Erzeugung **nur im laufenden Monat** (Sensor-Zweig), während
        # derselbe Monat nach dem Abschluss plötzlich richtig rechnete. Gemeldet von
        # dietmar1968 (Forum T77723 #775): 679 statt 724 kWh in Kennzahl und
        # Energie-Bilanz, während der Kategorien-Block die 45 kWh korrekt auswies.
        "balkonkraftwerk": {"pv_erzeugung_kwh": ("bkw_erzeugung_kwh", "pv_erzeugung_kwh")},
    }

    # Top-Level-Felder die bereits direkt von Collectoren gesetzt wurden
    # → nicht nochmal aus Einzel-Investitionen aufaddieren.
    #
    # #361 (coolxmad #353): Ein Connector-Delta ohne Abdeckung des
    # Monatsanfangs misst nur Stunden bis Tage und ist als Anlagen-Gesamtwert
    # kein Ersatz für die Komponenten-Summe — es sperrt die Aggregation daher
    # NICHT. Der Bruchstück-Wert wird beim ersten aggregierten Beitrag ersetzt
    # (nicht addiert, das wäre die Doppelzählung, die die Sperre verhindert).
    direct_fields = set(resolved.keys()) - teilzeitraum
    ersetzbar = set(teilzeitraum)

    def _wp_heizwaerme_eintrag(inv_id: int):
        """Die Heizwaerme dieses Geraets aus den Nicht-DB-Quellen (N-398).

        Dieselbe Weiche wie im Layer ({@link heizwaerme_kwh}), nur auf der
        anderen Datenform: ``resolved`` traegt ``inv_<id>_<feld>`` statt einer
        ``verbrauch_daten``-Zeile. Der **Regel**-Teil bleibt im Layer — hier
        wird nur die Zeile zusammengesetzt, die er lesen kann.

        ⚠ **Ohne das faellt der laufende Monat hinter den abgeschlossenen
        zurueck.** Der DB-Zweig kommt ueber die Monats-Fakten und hat die
        Aufloesung seit dem Layer-Eingriff; eine Klimaanlage, die ihre
        Nutzenergie je Innengeraet ueber MQTT oder HA meldet, saehe sonst im
        laufenden Monat 0 und im Folgemonat die Zahl — zwei Sichten, zwei
        Auskuenfte (Konzept §6/S1).

        Returns:
            ``(menge, DatenquelleInfo)`` wie jeder andere ``resolved``-Eintrag,
            oder ``None``.
        """
        direkt = resolved.get(f"inv_{inv_id}_heizenergie_kwh")
        if direkt is not None:
            return direkt
        praefix = f"inv_{inv_id}_"
        zeile = {
            k[len(praefix):]: v[0]
            for k, v in resolved.items() if k.startswith(praefix)
        }
        menge = heizwaerme_kwh(zeile)
        if menge is None:
            return None
        # Die Herkunfts-Marke des Wertes, der die Menge getragen hat — bei
        # mehreren Innengeraeten die des ersten gefundenen (dieselbe Naeherung,
        # die `_wp_waerme_d1` darunter fuer die Summanden macht).
        quelle = next(
            (v[1] for k, v in resolved.items()
             if k.startswith(praefix)
             and basis_feld_key(k[len(praefix):])
             == BETRIEBSART_NUTZENERGIE_FELD[BM_HEIZEN]),
            None,
        )
        return (menge, quelle) if quelle is not None else None

    def _wp_waerme_d1(inv_id: int) -> None:
        """D1 je Geraet — der Gesamtwert verdraengt nur die EIGENE Aufteilung.

        Legt das Ergebnis unter ``inv_<id>_<_WP_WAERME_D1_SUFFIX>`` ab, damit
        ``typ_aggregation`` darueber nur noch **summieren** muss. Die Regel
        selbst bleibt die eine Stelle (``waerme_gesamt_kwh``); dass sie **je
        Geraet** faellt und nicht auf der Anlagensumme, ist dieselbe Lehre wie
        im Tagespfad (N-391b): ``waerme_kwh`` ist ein Feld **am Geraet**, und
        eine Aufloesung ueber den Summen liesse die Aufteilung des zweiten
        Geraets still hinter dem Gesamtwert des ersten verschwinden (P4).

        Die Herkunfts-Marke ist die des Wertes, der D1 tatsaechlich gewonnen
        hat — bei den Summanden die des **letzten** vorhandenen, wie es die
        frueheren zwei ``_aggregate``-Aufrufe hinterliessen (verhaltensgleich).
        """
        _gesamt = resolved.get(f"inv_{inv_id}_waerme_kwh")
        _teile = [
            _wp_heizwaerme_eintrag(inv_id),
            resolved.get(f"inv_{inv_id}_warmwasser_kwh"),
        ]
        if _gesamt is None and all(t is None for t in _teile):
            return
        # Dieselbe Form wie im Layer-Zwilling `waerme_gesamt_je_geraet`: die
        # Summanden werden **vorher** addiert und als EIN Argument uebergeben.
        # Sonst haengt der Aufruf an der Laenge des Tupels darueber und eine
        # dritte Waermeachse liesse ihn umfallen, statt mitzuzaehlen.
        _wert = waerme_gesamt_kwh(
            _gesamt[0] if _gesamt is not None else None,
            sum(t[0] for t in _teile if t is not None),
            None,
        )
        if _gesamt is not None and _gesamt[0]:
            _quelle = _gesamt[1]
        else:
            _quelle = next(
                (t[1] for t in reversed(_teile) if t is not None), None
            )
            if _quelle is None:          # nur eine gemessene 0 im Gesamtfeld
                _quelle = _gesamt[1]
        resolved[f"inv_{inv_id}_{_WP_WAERME_D1_SUFFIX}"] = (_wert, _quelle)

    def _wp_strom_k3(inv_id: int, parameter: Optional[dict]) -> None:
        """K3 je Geraet — Gesamtzaehler und feine Aufteilung sind KEINE Summanden.

        Der Zwilling zu {@link _wp_waerme_d1} auf der Stromseite, und aus
        demselben Grund **je Geraet**: Die Stufenregel haengt an
        ``Investition.parameter`` (``getrennte_strommessung``) und an den
        Werten *dieses* Geraets. Auf der Anlagensumme gestellt, waere sie fuer
        eine Waermepumpe neben einer Split-Klimaanlage gar nicht beantwortbar.

        ⛔ **Die Regel selbst bleibt die eine Stelle** (``get_wp_strom_kwh`` /
        ``wp_strom_aufteilung``, K3/N-451/WK-16d). Hier wird sie nur
        **gerufen** — mit denselben Werten fuer Menge und Marke, auch fuer
        die Herkunfts-Marke, statt ihre Bedingung lokal nachzubauen: ein
        Nachbau derselben Bedingung faellt erfahrungsgemaess anders aus als das
        Original (die Lehre aus Sprengsatz S7 in N-391c).

        ⚠ **Der Monat fragt „steht ein Wert?", nicht „ist ein Zaehler
        zugeordnet?"** (Konzept Kap. 3). Fuer den laufenden Monat aus
        Nicht-DB-Quellen gilt die **Monats**frage: Was keine Quelle geliefert
        hat, steht nicht in ``resolved`` und ist damit unbelegt — genau die
        Ebene, auf der ``get_wp_strom_kwh`` an einer IMD-Zeile entscheidet.

        ⭐ **Seit dem 15.09.2026 stehen die Betriebsart-Zaehler mit in der
        Feldliste (R-1/K3 Regel 4, N-486).** Bis dahin stand hier: *„bewusst nur
        die drei Achsen, die die Tabelle vorher trug"* — mit der Begruendung,
        dieser Bau solle **eine** Verhaltensaenderung tragen (Summe → K3). Die
        Begruendung war fuer WK-12c richtig und ist mit R-1 verbraucht: Ein
        Geraet, dessen einzige Messung die Betriebsart-Zaehler sind, saehe im
        laufenden Monat sonst **0 kWh**, waehrend der abgeschlossene Monat
        daneben seine Menge traegt — genau der S1-Bruch zwischen zwei Sichten,
        gegen den K3 gebaut ist. ⚠ Die Felder muessen dafuer nichts Neues
        liefern: Steht kein ``inv_<id>_betriebsart_strom_*_kwh`` in
        ``resolved``, ist die Liste leer wie vorher und der Lauf bitgleich.
        """
        _felder = (
            "stromverbrauch_kwh", *FEINE_STROM_FELDER,
            *(BETRIEBSART_STROM_FELD[_m] for _m in MESSBARE_MODI),
        )
        _eintraege = {
            f: resolved[f"inv_{inv_id}_{f}"]
            for f in _felder
            if f"inv_{inv_id}_{f}" in resolved
        }
        if not _eintraege:
            return
        _wert = get_wp_strom_kwh(
            {f: e[0] for f, e in _eintraege.items()}, parameter,
        )
        # Die Marke ist die des Wertes, der K3 gewonnen hat — bei der feinen
        # Aufteilung die der **letzten** vorhandenen Achse, wie es die frueheren
        # drei `_aggregate`-Aufrufe hinterliessen (verhaltensgleich).
        _stufe = wp_strom_aufteilung(
            {f: e[0] for f, e in _eintraege.items()}, parameter,
        ).stufe
        _traeger = {
            "gesamt": ("stromverbrauch_kwh",),
            "fein": FEINE_STROM_FELDER,
            # K3 Regel 4 (R-1): dann traegt die Marke der Betriebsart-Zaehler,
            # nicht die einer Achse, die gar nichts beigesteuert hat.
            "betriebsart": tuple(
                BETRIEBSART_STROM_FELD[_m] for _m in MESSBARE_MODI
            ),
        }[_stufe]
        _quelle = next(
            (_eintraege[f][1] for f in reversed(_traeger) if f in _eintraege),
            None,
        )
        if _quelle is None:
            # Stufe „gesamt" ohne Gesamtzaehler gibt es nicht, Stufe „fein"
            # ohne eine einzige feine Achse auch nicht — bleibt der Fall, dass
            # eine kuenftige Achse hinzukommt. Dann traegt die Marke, was da ist.
            _quelle = next(iter(_eintraege.values()))[1]
        resolved[f"inv_{inv_id}_{_WP_STROM_K3_SUFFIX}"] = (_wert, _quelle)

    def _aggregate(top_level_feld: str, inv_key: str) -> None:
        if inv_key not in resolved:
            return
        if top_level_feld in direct_fields:
            return  # Bereits direkt gesetzt → nicht doppelt zählen
        val = resolved[inv_key][0]
        quelle_info = resolved[inv_key][1]
        if top_level_feld not in resolved or top_level_feld in ersetzbar:
            ersetzbar.discard(top_level_feld)
            resolved[top_level_feld] = (val, quelle_info)
        else:
            resolved[top_level_feld] = (resolved[top_level_feld][0] + val, quelle_info)

    # #239 detLAN-Folge: HA-Statistics-/MQTT-Sensoren liefern Werte auch in
    # Monaten vor Anschaffung der EEDC-Investition (Sensor existierte in HA
    # schon vorher). Vor-Anschaffungs-/Nach-Stilllegungs-Monate hier
    # rausfiltern, sonst tauchen WP-Werte (z.B. 145 kWh Strom für März bei
    # Anschaffungsdatum April) im Monatsbericht auf.
    for inv in investitionen:
        if not inv.ist_aktiv_im_monat(jahr, monat):
            continue
        if inv.typ == "waermepumpe":
            _wp_waerme_d1(inv.id)
            _wp_strom_k3(inv.id, inv.parameter)
        agg_map = typ_aggregation.get(inv.typ, {})
        for inv_suffix, ziel_felder in agg_map.items():
            for top_level_feld in ziel_felder:
                _aggregate(top_level_feld, f"inv_{inv.id}_{inv_suffix}")
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("direct_fields",) if k in _loc}


async def emob_bloecke_des_monats(db, anlage_id, investitionen, jahr, monat) -> dict:
    """N-555 Stufe 3: ``{inv_id: BlockMonat}`` der geltenden Ladeblöcke des Monats.

    Nur mit E-Auto **und** Wallbox (sonst keine Abfrage); die Tages-Bedingung W-C prüft
    ``monats_aus_tagen.emob_je_auto``.
    """
    typen = {getattr(i, "typ", None) for i in investitionen}
    if not {"e-auto", "wallbox"} <= typen:
        return {}
    from backend.services.energie_profil.monats_aus_tagen import emob_je_auto

    return await emob_je_auto(db, anlage_id, investitionen, jahr, monat)


async def emob_heimlade_quellen(db, anlage, investitionen, jahr, monat) -> frozenset:
    """Die Heimlade-Felder mit zugeordneter Quelle — nur für den **laufenden** Monat.

    Die Regel steht in ``services/emob_heimlade_quellen.py`` (N-555, Konzept Regel 1);
    die Monats-Fakten fragen für den laufenden Monat dieselbe Funktion.
    """
    from backend.services.emob_heimlade_quellen import lade_emob_heimlade_quellen

    return await lade_emob_heimlade_quellen(db, anlage, investitionen, jahr, monat)


def emob_heimladung_pool(
    *, direct_fields, investitionen, jahr, monat, resolved,
    monats_fakt=None, ist_aktueller_monat=True,
    heimlade_quellen=frozenset(), ha_felder_mit_daten=frozenset(),
    bloecke=None,
):
    """E-Mobilitaet: Heimladung nach der **einen Funktion** (veraendert `resolved` in place).

    ⭐ **Seit N-555 (Konzept Heimladung/Fahrverbrauch, Regel 1 + 2-Ü + 6) entscheidet
    hier dieselbe Funktion wie in jeder anderen Sicht:**
    ``eauto_wirtschaftlichkeit.entscheide_emob_heimladung``. Bis dahin lief dieser Zweig
    über ``get_emob_heimladung_canonical`` mit dem Fahrverbrauch des E-Autos als
    „Ladung" — hatte die Wallbox im Monat 0 kWh geladen, stand der Fahrverbrauch als
    Heimladung da (Johnny_1993: 1.364 kWh). N-554 hatte vorher die Groessen-Heuristik
    ``max(eauto, wallbox)`` abgeloest; allein loeste das den Fall nicht.

    **Wann hier gar nicht gerechnet wird:** Die gespeicherte Zeile hat den Monat
    **gemessen** entschieden (Wallbox oder E-Auto, Menge ueber 0) — dann steht ihr
    Wert wie bisher als direkter Wert in ``resolved``. Im **abgeschlossenen** Monat
    gilt auch eine gespeicherte **0** (Regel 1: nur nach dem gespeicherten Wert).

    **Sonst** entscheidet die Funktion ueber die gespeicherte Zeile je Geraet,
    ergaenzt um die Werte aus ``resolved`` (``inv_<id>_<feld>``: Live, MQTT,
    HA-Statistik — im laufenden Monat gewinnen sie, im abgeschlossenen fuellen sie
    nur Luecken, dieselbe Praezedenz wie ``merge_datenquellen``), um die HA-Felder mit
    Daten, aber 0 (``ha_felder_mit_daten``: ein Wert, kein Loch) und im laufenden
    Monat um die Heimlade-Quellen (``heimlade_quellen``). Das deckt auch den Monat,
    dessen gespeicherte Zeile nur eine **Schaetzung** ergab: ein HA-Wert der Wallbox
    zaehlt dort wie ein gespeicherter (Konzept Regel 1).

    Dienstwagen und vor der Anschaffung liegende Monate bleiben wie bisher draussen.
    Die Buchhaltung der Datenquelle (``emob_quelle``) ist unveraendert. N-557: die
    externe Ladung (kWh) des Pools wird wie die externen Kosten weitergereicht.

    Returns:
        ``{"emob_entscheid": …}``, wenn hier entschieden wurde — die Geraete-Sicht
        nimmt PV/Netz/Extern dann von dort statt aus der gespeicherten Zeile.
    """
    from backend.core.field_definitions import HEIMLADE_FELDER
    from backend.services.eauto_wirtschaftlichkeit import (
        QUELLE_EAUTO,
        QUELLE_NULL,
        QUELLE_SCHAETZUNG,
        QUELLE_WALLBOX,
        entscheide_emob_heimladung,
    )

    gespeichert = monats_fakt.emob if monats_fakt is not None else None
    gespeichert_quelle = gespeichert.quelle if gespeichert is not None else None
    if "emob_ladung_kwh" in direct_fields and gespeichert_quelle in (QUELLE_WALLBOX, QUELLE_EAUTO):
        return {}
    if "emob_ladung_kwh" in direct_fields and gespeichert_quelle != QUELLE_SCHAETZUNG:
        return {}  # Fremdquelle (kein Fakten-Wert) — wie bisher unangetastet
    if not ist_aktueller_monat and gespeichert_quelle == QUELLE_NULL:
        # Abgeschlossener Monat, gespeicherte Entscheidung: 0. `_collect_saved_data`
        # fuehrt nur Werte ueber 0 — ohne diese Zeile fiele der Monat an die
        # HA-Statistik zurueck und bekaeme dort wieder den Fahrverbrauch.
        resolved["emob_ladung_kwh"] = (0.0, _gespeichert_info(resolved))
        return {}

    gespeicherte_zeilen = dict(gespeichert.ladedaten_je_inv) if gespeichert is not None else {}
    # N-555 Stufe 2: auch die dienstlichen Zeilen (Regel 3) und die Herkunft von
    # „Heim: gesamt" (Regel 8) — dieselben Eingänge wie die Monats-Fakten.
    gespeicherte_dienstlich = (
        dict(gespeichert.dienstlich_ladedaten_je_inv) if gespeichert is not None else {}
    )
    heim_gesamt: set[int] = set(gespeichert.heim_gesamt_ids) if gespeichert is not None else set()
    eauto_je_inv: dict[int, dict] = {}
    wallbox_daten: list[dict] = []
    dienstwagen_je_inv: dict[int, dict] = {}
    dienstliche_wallbox_je_inv: dict[int, dict] = {}
    wallbox_ids: set[int] = set()
    eauto_km = 0.0
    emob_quelle: Optional[tuple] = None
    wallbox_in_betrieb = False
    for inv in investitionen:
        # #239 detLAN-Folge: HA-Statistics-Werte aus vor-Anschaffungs-
        # Monaten nicht in den Monatsbericht-Pool aggregieren.
        if not inv.ist_aktiv_im_monat(jahr, monat):
            continue
        if inv.typ not in ("e-auto", "wallbox"):
            continue
        dienstlich = ist_dienstlich(inv)
        praefix = f"inv_{inv.id}_"
        werte = {k[len(praefix):]: v for k, v in resolved.items() if k.startswith(praefix)}
        gespeicherte_zeile = (
            (gespeicherte_dienstlich if dienstlich else gespeicherte_zeilen).get(inv.id) or {}
        )
        zeile = dict(gespeicherte_zeile)
        for feld, eintrag in werte.items():
            if ist_aktueller_monat:
                zeile[feld] = eintrag[0]
            else:
                zeile.setdefault(feld, eintrag[0])
        # HA-Statistik mit Daten, aber 0: ein Wert (Regel 1), kein Loch.
        for feld in HEIMLADE_FELDER[inv.typ]:
            if f"{praefix}{feld}" in ha_felder_mit_daten:
                zeile.setdefault(feld, 0.0)
        # Regel 8: ein `ladung_kwh` am Auto, das aus einer Quelle (HA, MQTT, Live) in die
        # Zeile kam, ist „Heim: gesamt" — nur der gespeicherte alte Gesamtwert ohne
        # Herkunft ist es nicht (sein Status steht in `heim_gesamt_ids` der Schicht).
        if inv.typ == "e-auto":
            gespeichert_ladung = gespeicherte_zeile.get("ladung_kwh")
            aus_quelle = (
                ("ladung_kwh" in werte and (ist_aktueller_monat or gespeichert_ladung is None))
                or (f"{praefix}ladung_kwh" in ha_felder_mit_daten and gespeichert_ladung is None)
            )
            if aus_quelle:
                heim_gesamt.add(inv.id)
        if dienstlich:
            if inv.typ == "e-auto":
                dienstwagen_je_inv[inv.id] = zeile
            else:
                dienstliche_wallbox_je_inv[inv.id] = zeile
            continue
        if inv.typ == "e-auto":
            eauto_je_inv[inv.id] = zeile
            # N-555: auch „Heim: PV/Netz" und Extern tragen die Herkunft — bis
            # 25.09.2026 zählten hier nur `ladung_kwh`/`verbrauch_kwh`, und ein
            # Steckerlader mit PV-/Netz-Sensor bekam im laufenden Monat gar keine
            # Heimladung ausgewiesen (der Topf rechnete sie, die Herkunft fehlte).
            for suffix in ("ladung_kwh", "verbrauch_kwh", "ladung_netz_kwh",
                           "ladung_pv_kwh", "ladung_extern_kwh"):
                if werte.get(suffix):
                    emob_quelle = werte[suffix][1]
                    break
            km_entry = werte.get("km_gefahren")
            if km_entry:
                eauto_km += km_entry[0]
                emob_quelle = km_entry[1]
        else:
            wallbox_in_betrieb = True
            wallbox_ids.add(inv.id)
            wallbox_daten.append(zeile)
            for suffix in ("ladung_kwh", "ladung_pv_kwh"):
                if werte.get(suffix):
                    emob_quelle = werte[suffix][1]
                    break
    entscheid = entscheide_emob_heimladung(
        eauto_je_inv=eauto_je_inv,
        wallbox_zeilen=wallbox_daten,
        wallbox_in_betrieb=wallbox_in_betrieb,
        dienstwagen_je_inv=dienstwagen_je_inv,
        dienstliche_wallbox_je_inv=dienstliche_wallbox_je_inv,
        heim_gesamt=heim_gesamt,
        wallbox_ids=wallbox_ids,
        heimlade_quellen=heimlade_quellen if ist_aktueller_monat else (),
        # N-555 Stufe 3 (Regel 9 Punkt 3): geltende Ladeblöcke sind die Messung je Auto.
        bloecke=bloecke,
        # Die Quote der gespeicherten Schaetzung gilt weiter; eine andere kennt
        # dieser Zweig nicht (die Tagesebene liest die Schicht).
        pv_quote=(
            gespeichert.ladung_pv_kwh / gespeichert.ladung_kwh
            if gespeichert is not None and gespeichert_quelle == QUELLE_SCHAETZUNG
            and gespeichert.ladung_anteil_abgeleitet and gespeichert.ladung_kwh > 0
            else None
        ),
    )
    pool = entscheid.pool
    if gespeichert_quelle == QUELLE_SCHAETZUNG:
        # Die gespeicherte Schaetzung stand als direkter Wert in `resolved` —
        # sie gilt nur, wenn die Funktion bei ihr bleibt.
        resolved.pop("emob_ladung_kwh", None)
        resolved.pop("emob_pv_ladung_kwh", None)
        if emob_quelle is None and pool.ladung_kwh > 0:
            emob_quelle = _gespeichert_info(resolved)
        if pool.pv_kwh > 0 and emob_quelle is not None:
            resolved["emob_pv_ladung_kwh"] = (pool.pv_kwh, emob_quelle)
    if pool.ladung_kwh > 0 and emob_quelle is not None:
        resolved["emob_ladung_kwh"] = (pool.ladung_kwh, emob_quelle)
    elif entscheid.quelle == QUELLE_NULL:
        # N-555: „die Wallbox hat nicht geladen" ist eine Zahl, kein Loch — sofern
        # der Monat überhaupt etwas geliefert hat (ein E-Mob-Wert aus einer Quelle
        # oder eine gespeicherte Zeile). Ein ganz leerer laufender Monat mit bloß
        # zugeordneter Quelle bleibt „—": sonst stünde eine 0 da, die nichts
        # gemessen hat, und die Route hielte den Monat für belegt
        # (`monatswert_grund`), obwohl keine Quelle einen Wert gab.
        info = emob_quelle or (_gespeichert_info(resolved) if gespeicherte_zeilen else None)
        if info is not None:
            resolved["emob_ladung_kwh"] = (0.0, info)
    if "emob_km" not in direct_fields and eauto_km > 0 and emob_quelle is not None:
        resolved["emob_km"] = (eauto_km, emob_quelle)
    # #260: externe Lade-Kosten — der SoT nimmt die Quelle mit den hoeheren Kosten.
    if "emob_ladung_extern_euro" not in direct_fields:
        if pool.extern_euro > 0 and emob_quelle is not None:
            resolved["emob_ladung_extern_euro"] = (pool.extern_euro, emob_quelle)
    # N-557: dasselbe Paar in kWh — „Ladung gesamt" zaehlt Extern mit, sobald ein
    # Sensor es liefert (Konzept Regel 10), nicht erst ab dem Monatsabschluss.
    if "emob_ladung_extern_kwh" not in direct_fields:
        if pool.extern_kwh > 0 and emob_quelle is not None:
            resolved["emob_ladung_extern_kwh"] = (pool.extern_kwh, emob_quelle)
    return {"emob_entscheid": entscheid}


def _gespeichert_info(resolved):
    """Die DatenquelleInfo fuer eine 0, die die Route selbst setzt (N-555).

    Die der E-Mob-Felder des Monats, wenn es sie gibt — sonst die der gespeicherten
    Zeile (Konfidenz 85, wie ``_collect_saved_data``)."""
    from backend.api.routes.aktueller_monat.schemas import DatenquelleInfo

    for feld in ("emob_km", "emob_ladung_extern_euro", "emob_verbrauch_kwh"):
        if feld in resolved:
            return resolved[feld][1]
    return DatenquelleInfo(quelle="gespeichert", konfidenz=85)


def extrahiere_werte(*, monats_fakt, resolved):
    """Werte aus `resolved` extrahieren; liefert `get_val` als Closure fuer die spaeteren Abschnitte.

    Aus `get_aktueller_monat` Zeilen 1072-1108 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── Werte extrahieren ──
    def get_val(feld: str) -> Optional[float]:
        entry = resolved.get(feld)
        return round(entry[0], 2) if entry else None

    pv = get_val("pv_erzeugung_kwh")
    # P4/§3 Regel 2: das Provenance-Flag der Schicht wird ausgeliefert, nicht
    # nur gesetzt. ⚠ Diese Route mischt VIER Quellen und die Schicht kennt nur
    # EINE (die DB, KONZEPT-MONATS-FAKTEN §4). `pv_vollstaendig` beschreibt
    # deshalb ausschließlich den gespeicherten Wert — hat der Sensor- oder
    # Connector-Zweig die Präzedenz gewonnen, wäre der Hinweis eine Aussage
    # über eine Zahl, die gar nicht angezeigt wird.
    _pv_entry = resolved.get("pv_erzeugung_kwh")
    hinweise = [
        h for h in (
            pv_unvollstaendig_hinweis([monats_fakt])
            if monats_fakt is not None
            and _pv_entry is not None
            and _pv_entry[1].quelle == "gespeichert"
            else None,
        ) if h
    ]
    einspeisung = get_val("einspeisung_kwh")
    netzbezug = get_val("netzbezug_kwh")
    speicher_ladung = get_val("speicher_ladung_kwh")
    speicher_entladung = get_val("speicher_entladung_kwh")

    # Sonstige Erzeuger (z. B. BHKW) speisen hinter den Hauszähler → ihre Erzeugung
    # gehört in die Netzpunkt-Bilanz, sonst drückt der gemessene Einspeise-Zähler
    # die PV-Bilanz still zu niedrig (Konzept Sonstiger Erzeuger 2026-06-22).
    # `pv` (Anzeige + PV-Kennzahlen) bleibt rein. Der Wert wird in
    # `_collect_saved_data` aktiv-/anschaffungsdatum-gefiltert aggregiert
    # ([[feedback_anschaffungsdatum_grenze]]).
    sonstiges_erz_bilanz = get_val("sonstiges_erzeugung_kwh") or 0
    abgabe_dritte = get_val("sonstiges_abgabe_kwh") or 0
    erzeugung_bilanz = erzeugung_hinter_zaehler_kwh(pv, sonstiges_erz_bilanz)
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("abgabe_dritte", "einspeisung", "erzeugung_bilanz", "get_val", "hinweise", "netzbezug", "pv", "sonstiges_erz_bilanz", "speicher_entladung", "speicher_ladung",) if k in _loc}


def berechne_bilanzwerte(*, abgabe_dritte, einspeisung, erzeugung_bilanz, netzbezug, pv, sonstiges_erz_bilanz, speicher_entladung, speicher_ladung, v2h_entladung=0.0):
    """Berechnete Werte: Eigenverbrauch, Direktverbrauch, Gesamtverbrauch, Autarkie, EV-Quote — ÜBER DEN LAYER.

    N-610 (03.10.2026): bis dahin stand hier eine eigene Formel (`direkt + speicher_entladung − abgabe`) — die Kopie, die
    die V2H-Erweiterung des Layers nie bekam: ein E-Auto, das ins Haus zurückspeist, fehlte im Eigenverbrauch von
    Cockpit → Monat und → Jahr (r28 A1 2025: Σ 6 996,5 kWh gegen 7 331,4 kWh in Übersicht und Monatsreihe; Δ = 335 kWh V2H).
    Jetzt ruft die Route `core/berechnungen/verbrauch.py::berechne_verbrauchs_kennzahlen` — dieselbe Funktion wie die
    Monats-Fakten, Übersicht, Monatsreihe, PDF und HA-Export (ADR-001 Pflicht 2). Die V2H-Menge kommt aus dem Monats-Fakt
    (`monats_fakt.emob.v2h_entladung_kwh`, gespeicherte Gerätewerte); die Vier-Quellen-Auflösung kennt kein V2H-Feld —
    im laufenden Monat ohne gespeicherten Wert ist sie 0.

    Die None-Gates der Route bleiben UM den Aufruf: keine Bilanz ohne Erzeugung bzw. Einspeisung; Gesamtverbrauch und
    Autarkie nur mit Netzbezug; EV-Quote nur mit Erzeugung > 0. Gerundet wird am Rand wie bisher (2 Stellen bzw. 1 Stelle).
    """
    # ── Berechnete Werte ──
    eigenverbrauch = None
    direktverbrauch = None
    gesamtverbrauch = None
    autarkie = None
    ev_quote = None

    if (pv is not None or sonstiges_erz_bilanz > 0) and einspeisung is not None:
        kz = berechne_verbrauchs_kennzahlen(
            pv_erzeugung_kwh=erzeugung_bilanz,
            einspeisung_kwh=einspeisung,
            netzbezug_kwh=netzbezug or 0.0,
            speicher_ladung_kwh=speicher_ladung or 0.0,
            speicher_entladung_kwh=speicher_entladung or 0.0,
            v2h_entladung_kwh=v2h_entladung or 0.0,
            abgabe_dritte_kwh=abgabe_dritte or 0.0,
        )
        direktverbrauch = round(kz.direktverbrauch_kwh, 2)
        eigenverbrauch = round(kz.eigenverbrauch_kwh, 2)

        if netzbezug is not None:
            gesamtverbrauch = round(kz.gesamtverbrauch_kwh, 2)
            if kz.gesamtverbrauch_kwh > 0:
                autarkie = round(kz.autarkie_prozent, 1)

        if erzeugung_bilanz > 0:
            ev_quote = round(kz.eigenverbrauchsquote_prozent, 1)
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("autarkie", "direktverbrauch", "eigenverbrauch", "ev_quote", "gesamtverbrauch",) if k in _loc}

