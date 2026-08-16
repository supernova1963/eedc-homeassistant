"""
Per-Typ-Komponenten-Beitrag-Helper (v3.33.0).

Single Source of Truth dafür, welche Sensor-Felder (per Investitions-Typ)
in `TagesZusammenfassung.komponenten_kwh` einfließen und mit welchem
Vorzeichen — gemeinsam genutzt von Snapshot-Aggregator
(`services.snapshot.aggregator.get_komponenten_tageskwh`) und LTS-Aggregator
(`services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts`).

Hintergrund (Issue #290): Vor v3.33.0 lief die LTS-Variante über eine
generische Schleife über alle gemappten Felder. Speicher mit
`ladung_netz_kwh`-Mapping, Wallbox mit `ladung_pv_kwh`/`ladung_netz_kwh`,
E-Auto mit Split-Sensoren und Wärmepumpe mit thermischen oder Counter-
Sensoren produzierten dadurch Doppelzählungen (Faktor 2–10×). Die Per-Typ-
Whitelist hier spiegelt exakt die Snapshot-Variante als semantische
Wahrheit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable, Optional

from backend.services.snapshot.keys import BASIS_ZAEHLER_FELDER, _categorize_counter

# Das Feld, mit dem ein Erzeuger seinen EIGENEN kumulativen PV-Zähler trägt.
# Gegenspieler des Anlagen-Aggregats `basis:pv_gesamt` (s. `basis_beitraege`).
_PV_JE_INVESTITION_FELD = "pv_erzeugung_kwh"


# Investitions-Typ → Komponenten-Key-Präfix in komponenten_kwh.
# Spiegel zu PV_KOMPONENTEN_PREFIXE in core/berechnungen/energie.py +
# frontend/src/lib/constants.ts.
_TYP_KEY_PREFIX: dict[str, str] = {
    "pv-module": "pv_",
    "balkonkraftwerk": "bkw_",
    "speicher": "batterie_",
    "waermepumpe": "waermepumpe_",
    "wallbox": "wallbox_",
    "e-auto": "eauto_",
    "sonstiges": "sonstige_",
}


@dataclass(frozen=True)
class KomponentenBeitrag:
    """Ein Sensor-Beitrag zu einem Komponenten-Key in komponenten_kwh.

    - `feld`: das Mapping-Feld (z. B. `ladung_kwh`, `stromverbrauch_kwh`)
    - `target_key`: der Ziel-Schlüssel im JSON-Feld
      (z. B. `wallbox_2`, `einspeisung`)
    - `vorzeichen`: +1 oder -1 (Speicher-Entladung, Sonstiges-Verbraucher)
    - `fallback_gruppe`: optional — Either-Or-Markierung für E-Auto
      (mehrere Beiträge mit identischer Gruppe; der Aggregator nimmt
      nur den ersten, der ein Delta != None liefert).
    """

    feld: str
    target_key: str
    vorzeichen: int = +1
    fallback_gruppe: Optional[str] = None


def _is_sensor_mapping(cfg) -> bool:
    """True wenn ein Feld-Mapping als gültiger Sensor konfiguriert ist."""
    return (
        isinstance(cfg, dict)
        and cfg.get("strategie") == "sensor"
        and bool(cfg.get("sensor_id"))
    )


def pv_je_investition_belegt_in_map(
    investitionen_map: dict,
    mqtt_felder_je_investition: Optional[dict[str, set[str]]] = None,
) -> bool:
    """Wie `pv_je_investition_belegt`, aber auf `sensor_mapping["investitionen"]`.

    Zwei Einstiege, weil die Aufrufer verschieden tief stehen: die Aggregatoren
    halten das ganze `sensor_mapping`, `mqtt_hourly_eintraege` bekommt nur den
    Teilbaum durchgereicht. Eine der beiden Formen nachzubauen wäre die
    Kopie, die hier vermieden werden soll.
    """
    if isinstance(investitionen_map, dict):
        for inv_data in investitionen_map.values():
            if not isinstance(inv_data, dict):
                continue
            felder = inv_data.get("felder") or {}
            if _is_sensor_mapping(felder.get(_PV_JE_INVESTITION_FELD)):
                return True
    for felder_vorhanden in (mqtt_felder_je_investition or {}).values():
        if _PV_JE_INVESTITION_FELD in felder_vorhanden:
            return True
    return False


def pv_je_investition_belegt(
    sensor_mapping: dict,
    mqtt_felder_je_investition: Optional[dict[str, set[str]]] = None,
) -> bool:
    """Trägt mindestens ein Erzeuger einen EIGENEN kumulativen PV-Zähler?

    Die Frage entscheidet, ob der Anlagen-Zählerstand `basis:pv_gesamt` auf der
    Tages-/Stundenebene mitzählt (s. `basis_beitraege`). Sie ist bewusst
    **quellen-übergreifend** gestellt: ein Erzeuger kann seinen Zähler als
    HA-Sensor im `sensor_mapping` haben **oder** ihn per MQTT publizieren, ohne
    im Mapping aufzutauchen — der MQTT-/Standalone-Pfad leitet Verfügbarkeit
    seit #317 ausdrücklich aus den gesehenen Topics ab
    (`mqtt_hourly_eintraege`). Wer nur das Mapping befragt, zählt bei einer
    gemischten Installation (Aggregat aus HA, Strings aus MQTT) doppelt.

    Args:
        sensor_mapping: `anlage.sensor_mapping`.
        mqtt_felder_je_investition: `{inv_id: {feld, …}}` der zuletzt per MQTT
            gesehenen Felder — optional, weil der HA-LTS-Pfad keine MQTT-Zähler
            kennt und dort auch keine sehen kann.
    """
    return pv_je_investition_belegt_in_map(
        (sensor_mapping or {}).get("investitionen") or {},
        mqtt_felder_je_investition,
    )


def pv_je_investition_in_sensor_keys(sensor_keys: Iterable[str]) -> bool:
    """Trägt einer der `sensor_key`s einen eigenen PV-Zähler je Erzeuger?

    Die Form, die die beiden Snapshot-Aufrufer brauchen: sie halten die
    MQTT-Keys bereits als flache `inv:<id>:<feld>`-Liste und müssen die
    Alles-oder-nichts-Frage stellen, **bevor** sie den Basis-Beitrag bauen
    (s. `basis_beitraege`).
    """
    suffix = f":{_PV_JE_INVESTITION_FELD}"
    return any(
        sk.startswith("inv:") and sk.endswith(suffix) for sk in sensor_keys
    )


def basis_beitraege(
    sensor_mapping: dict,
    *,
    pv_je_investition_extern: bool = False,
) -> list[KomponentenBeitrag]:
    """Basis-Zähler aus dem `basis`-Mapping (`BASIS_ZAEHLER_FELDER`).

    Liefert für jeden konfigurierten Basis-Zähler einen `+1`-Beitrag mit
    Target-Key = Feldname (`einspeisung` / `netzbezug` / `pv_gesamt`).

    **`pv_gesamt` gilt alles-oder-nichts** (Stufe 1 zu F-7, 2026-08-07): der
    Anlagen-Zählerstand zählt nur mit, solange KEIN Erzeuger einen eigenen
    `pv_erzeugung_kwh`-Zähler trägt. Genau so hält es der Live-Pfad seit jeher
    (`live_tagesverlauf_service:267` / `live_history_service:341`,
    `not has_individual_pv`) — dieselbe Regel, damit dieselbe Anlage in Live
    und Tag nicht verschieden rechnet.

    Warum nicht anteilig auffüllen wie im Monat? `resolve_pv_je_modul` (P7)
    darf das, weil es einer Investition einen Wert **zuweist**. Hier gibt es
    diesen Adressaten nicht: `komponenten_kwh` kennt nur einen flachen
    Keyspace, und `summe_pv_bkw_kwh` summiert **alles** mit Präfix `pv_`.
    Stünde `pv_gesamt` neben `pv_7`, wäre die Anlagensumme neben ihrem eigenen
    Summanden gebucht — die Doppelzähl-Klasse aus #290/#298. Eine
    kWp-Verteilung auf Tagesebene ist ausdrücklich verworfen (Entscheid Gernot
    2026-08-07): sie erfände Messwerte, die niemand gemessen hat.

    ⚠ **Folge für die Oberfläche:** wer einem von mehreren Erzeugern einen
    eigenen Zähler zuordnet, schaltet das Aggregat für Tag und Stunde ab und
    sieht danach nur noch die gemessenen Erzeuger. Die Zuordnungs-Fläche muss
    das sagen — `datenquellen_validierung.finde_aggregat_teilweise_verdraengt`
    warnt genau in dieser Lage.

    Args:
        sensor_mapping: `anlage.sensor_mapping`.
        pv_je_investition_extern: True, wenn der Aufrufer aus einer Quelle
            **außerhalb** des Mappings weiß, dass ein Erzeuger seinen eigenen
            PV-Zähler hat (MQTT-Topics). Siehe `pv_je_investition_belegt`.
    """
    beitraege: list[KomponentenBeitrag] = []
    basis = (sensor_mapping or {}).get("basis", {}) or {}
    pv_verdraengt = pv_je_investition_extern or pv_je_investition_belegt(sensor_mapping)
    for feld in BASIS_ZAEHLER_FELDER:
        if feld == "pv_gesamt" and pv_verdraengt:
            continue
        cfg = basis.get(feld)
        if _is_sensor_mapping(cfg):
            beitraege.append(KomponentenBeitrag(feld=feld, target_key=feld))
    return beitraege


def wallbox_deckt_ladung_ab(
    investitionen: Iterable,
    sensor_mapping: Optional[dict],
    *,
    ist_verfuegbar: Optional[Callable[[Any, str], bool]] = None,
) -> bool:
    """Trägt irgendeine Wallbox der Anlage einen kWh-Ladezähler? (N-196)

    Die strukturelle Quellen-Regel der E-Mob-Fläche, hier für den **Zähler**-
    pfad. Sie existierte bis 2026-08-08 nur im Leistungspfad
    (`services/live_sensor_config.py`) und auf der Monatsebene
    (`eauto_wirtschaftlichkeit.get_emob_heimladung_canonical`) — der Zählerpfad
    schützte allein über ``parent_investition_id``.

    Bewusst **strukturell** (gibt es einen Wallbox-Ladezähler?) und nicht
    magnitudenabhängig (wer misst mehr?): bei Streudaten wählt der Vergleich
    die falsche Quelle, das war der Befund von #262.

    Args:
        investitionen: alle Investitionen der Anlage (der Aufrufer filtert
            nicht — Aktivität spielt für die Existenz eines Zählers keine
            Rolle, und ein stillgelegtes Gerät hat keine Tageswerte mehr).
        sensor_mapping: ``anlage.sensor_mapping``.
        ist_verfuegbar: ``(inv, feld) -> bool`` für den MQTT-/Standalone-Pfad,
            der seine Verfügbarkeit nicht aus dem Sensor-Mapping zieht.
    """
    inv_map = ((sensor_mapping or {}).get("investitionen") or {})
    for inv in investitionen or ():
        if getattr(inv, "typ", None) != "wallbox":
            continue
        if ist_verfuegbar is not None:
            if ist_verfuegbar(inv, "ladung_kwh"):
                return True
            continue
        felder = (inv_map.get(str(getattr(inv, "id", ""))) or {}).get("felder") or {}
        if _is_sensor_mapping(felder.get("ladung_kwh")):
            return True
    return False


def investition_beitraege(
    inv,
    sensor_mapping_for_inv: dict,
    *,
    ist_verfuegbar: Optional[Callable[[str], bool]] = None,
    wallbox_deckt_ladung: bool = False,
) -> list[KomponentenBeitrag]:
    """Per-Typ-Beiträge einer Investition zur `komponenten_kwh`.

    Quelle der Wahrheit ist die Snapshot-Variante
    (`services.snapshot.aggregator.get_komponenten_tageskwh:444-516`).
    Diese Funktion ist die einzige Stelle, wo die Per-Typ-Auswahl lebt.

    Args:
        inv: Investitions-Objekt mit Attributen `id`, `typ`, `parameter`,
            `parent_investition_id` (für E-Auto: Skip wenn parent vorhanden).
        sensor_mapping_for_inv: `{"felder": {feld: {strategie, sensor_id, ...}}}`
            Dict aus `sensor_mapping["investitionen"][str(inv.id)]`.
        ist_verfuegbar: optionales Verfügbarkeits-Prädikat `feld -> bool`. Default
            (None) = HA-Sensor-Mapping (`_is_sensor_mapping`). Der MQTT-/Standalone-
            Pfad (#317) reicht „MQTT-Key vorhanden" durch, damit Whitelist +
            Either-Or + parent-Skip quellen-agnostisch über DIESELBE Funktion
            laufen statt über rohe `_categorize_counter`-Aufrufe.

    Returns:
        Liste der Beiträge. Leer wenn keinem der zulässigen Felder ein
        Sensor/MQTT-Key zugeordnet ist (oder wenn E-Auto-Skip greift).
    """
    typ = getattr(inv, "typ", None)
    prefix = _TYP_KEY_PREFIX.get(typ)
    if prefix is None:
        return []

    felder = (sensor_mapping_for_inv or {}).get("felder", {}) or {}
    if ist_verfuegbar is None:
        def ist_verfuegbar(feld: str) -> bool:
            return _is_sensor_mapping(felder.get(feld))
    inv_id_str = str(getattr(inv, "id", ""))
    target_key = f"{prefix}{inv_id_str}"

    def _add(feld: str, vorzeichen: int = +1, fallback_gruppe: Optional[str] = None):
        if ist_verfuegbar(feld):
            beitraege.append(
                KomponentenBeitrag(
                    feld=feld,
                    target_key=target_key,
                    vorzeichen=vorzeichen,
                    fallback_gruppe=fallback_gruppe,
                )
            )

    beitraege: list[KomponentenBeitrag] = []

    if typ in ("pv-module", "balkonkraftwerk"):
        # Ein Balkonkraftwerk trägt GENAU EINEN Ziel-Key: `bkw_{id}`, Erzeugung.
        # Paket D gab ihm kurzzeitig einen zweiten (`batterie_{id}`) für die
        # BKW-eigenen Speicher-Felder — zurückgenommen mit dem Kanon-Entscheid am
        # selben Tag: ein BKW-Akku wird als eigene Speicher-Investition mit
        # Parent Balkonkraftwerk erfasst und läuft damit durch den `speicher`-Zweig
        # unten, mitsamt Live-Leistung, SoC und Energiefluss-Knoten.
        # Warum die Speicher-Hälfte NIE auf `bkw_{id}` durfte, bleibt wissenswert:
        # dieser Präfix steht in PV_KOMPONENTEN_PREFIXE und wird als *Erzeugung*
        # summiert (`summe_pv_bkw_kwh`, nur-positiv) — eine Entladung landete dort
        # als PV-Erzeugung, eine Ladung hätte die BKW-Erzeugung still gekürzt,
        # exakt die Klasse des BKW-Bugs vom 2026-05-19 (Rainer-PN).
        _add("pv_erzeugung_kwh")

    elif typ == "speicher":
        # ladung_netz_kwh ist semantisch Teilmenge von ladung_kwh — NICHT
        # zusätzlich aufaddieren (sonst Doppelzählung für Arbitrage-Anwender).
        # Vorzeichen-Konvention der batterie_*-Komponente: ENTLADUNG positiv
        # (Quelle), LADUNG negativ (Senke) — identisch zur batterie_kw-Spalte
        # (SoT: core.berechnungen.batterie_kw_spalte). So sind komponenten_kwh
        # (Boundary) und der Live-/komponenten-JSON-Pfad (−serie_sum) vorzeichen-
        # gleich; beide Achse-2-/TZ-Invarianten bleiben konsistent.
        _add("ladung_kwh", vorzeichen=-1)
        _add("entladung_kwh", vorzeichen=+1)

    elif typ == "waermepumpe":
        # Nur elektrischer Verbrauch. heizenergie_kwh/warmwasser_kwh sind
        # *thermische* Werte (~ Strom × COP) und gehören nicht in die
        # Bilanz. wp_starts_anzahl/wp_betriebsstunden sind reine Counter
        # (eigener Pfad in `get_daily_counter_deltas_by_inv`).
        params = getattr(inv, "parameter", None) or {}
        if isinstance(params, dict) and params.get("getrennte_strommessung"):
            _add("strom_heizen_kwh")
            _add("strom_warmwasser_kwh")
        else:
            _add("stromverbrauch_kwh")

    elif typ == "wallbox":
        # ladung_pv_kwh / ladung_netz_kwh sind Teilmengen von ladung_kwh —
        # NICHT zusätzlich addieren (sonst Doppelzählung wie bei Gernots
        # Wallbox: 14 + 9,24 = 23,24 statt korrekt 14).
        _add("ladung_kwh")

    elif typ == "e-auto":
        # Wenn parent_investition_id gesetzt ist, misst die Wallbox bereits
        # die Ladung — wir überspringen das E-Auto, damit nicht doppelt
        # gezählt wird (spiegelt Live-Pfad).
        if getattr(inv, "parent_investition_id", None) is not None:
            return []
        # N-196: dieselbe STRUKTURELLE Regel wie im Leistungspfad
        # (`live_sensor_config.py`, F-14/#356) — trägt eine Wallbox die
        # Ladeenergie, ist sie die Quelle, auch ohne gesetzten Parent.
        #
        # Der Zählerpfad kannte bis 2026-08-08 nur die Parent-Bedingung eine
        # Zeile höher. Ein E-Auto mit eigenem kWh-Zähler **ohne** Parent lief
        # deshalb an ihr vorbei und schrieb denselben Ladevorgang ein zweites
        # Mal in `komponenten_kwh` — genau die Masche, durch die F-14 im
        # Leistungspfad fiel (29,32 statt 12,00 kWh an einem Tag).
        #
        # ⚠ **Ohne heute messbaren Schaden, und das steht hier bewusst:** an
        # der einzigen vermessenen Anlage hat das E-Auto gar keinen kWh-Zähler
        # gemappt, die Doppelzählung lief dort über `leistung_w`. Das ist ein
        # Argument für Symmetrie, nicht gegen sie — eine Regel, die nur einer
        # von zwei Pfaden kennt, ist die nächste Drift-Quelle.
        if wallbox_deckt_ladung:
            return []
        # Either-Or: erst ladung_kwh, sonst fallback verbrauch_kwh — vom
        # Aggregator über `fallback_gruppe` ausgewertet (genau ein Delta
        # pro Gruppe).
        gruppe = f"eauto_either_or_{inv_id_str}"
        _add("ladung_kwh", fallback_gruppe=gruppe)
        _add("verbrauch_kwh", fallback_gruppe=gruppe)

    elif typ == "sonstiges":
        # Pro Investition genau ein Komponenten-Wert, immer mit positivem
        # Vorzeichen — auch bei Verbraucher-Kategorie. Die Seite leitet das
        # Frontend aus `inv.parameter.kategorie` ab. Wahl primary/secondary
        # spiegelt Snapshot-Variante.
        # ⚑ **N-259 (Melder rapahl, 16.08.2026): der Verbrauchs-Feldname war
        # falsch.** Hier stand `verbrauch_kwh` — ein Name, den die Feld-Registry
        # für diesen Typ **nicht kennt**. Ein *Sonstiges*-Verbraucher heißt dort
        # `verbrauch_sonstig_kwh`, und genau diesen Key legt die
        # Zuordnungsfläche ins `sensor_mapping`. `_add("verbrauch_kwh")` prüfte
        # also auf ein Feld, das nie belegt ist ⇒ **kein Beitrag, kein
        # `sonstige_<id>` in `komponenten_kwh`, kein Stunden- und kein
        # Tageswert.** Der Monat kam trotzdem an (`get_sonstiges_verbrauch_kwh`
        # liest beide Namen) — deshalb sah es nach „Tageswert fehlt" statt nach
        # „Feld wird nirgends gefunden" aus.
        # Der Sonstiges-**Erzeuger** war nie betroffen: `erzeugung_kwh` heißt in
        # beiden Welten gleich.
        # Der Legacy-Name bleibt als zweiter Kandidat derselben Either-Or-Gruppe
        # stehen (Altbestand im Mapping), er kann nicht zusätzlich zählen.
        params = getattr(inv, "parameter", None)
        kategorie = (
            params.get("kategorie", "verbraucher")
            if isinstance(params, dict)
            else "verbraucher"
        )
        verbrauch_felder = ("verbrauch_sonstig_kwh", "verbrauch_kwh")
        reihenfolge = (
            ("erzeugung_kwh", *verbrauch_felder)
            if kategorie == "erzeuger"
            else (*verbrauch_felder, "erzeugung_kwh")
        )
        gruppe = f"sonstiges_either_or_{inv_id_str}"
        for feld in reihenfolge:
            _add(feld, fallback_gruppe=gruppe)

    return beitraege


# ── Was die Zuordnung für EINEN Tag verspricht (N-57) ───────────────────────


def erwartete_komponenten_keys(
    sensor_mapping: dict,
    investitionen_by_id: dict,
    tag: date,
) -> dict[str, Any]:
    """`{target_key: Investition | None}` — was die Zuordnung für **diesen Tag**
    verspricht. Basis-Zähler (Einspeisung/Netzbezug) tragen `None`.

    **Tagesabhängig, und das ist der Punkt:** `energie_profil.aggregator.
    aggregate_day` lädt seine Investitionen mit `aktiv_am_tag(datum)`. Eine
    Komponente, die an diesem Tag noch nicht angeschafft, bereits stillgelegt
    oder auf `aktiv=False` gesetzt war, bekommt vom Lauf nichts geschrieben —
    also darf ihr Key für diesen Tag auch nichts versprechen. Wer die Menge
    einmal für ein ganzes Fenster baut, meldet für solche Tage eine Lücke und
    bietet eine Reparatur an, die der Lauf nicht einlösen kann (N-57,
    dietmar1968, Forum simon42 #89667/83).

    Der Filter ist `Investition.ist_aktiv_an(tag)` — die In-Memory-Zwillings-
    Definition von `utils.investition_filter.aktiv_am_tag` (dort im Docstring
    als identisch festgehalten), weil die Investitionen hier bereits geladen
    sind und keine zweite Query brauchen.

    Zwei Konsumenten, damit Versprechen und Rückmeldung dieselbe Menge
    benutzen: der Daten-Checker (`daten_checker.datenquelle.
    _check_leere_tage_trotz_zaehler`) und die Tages-Reparatur
    (`repair_orchestrator._execute_reaggregate_day`, N-58).
    """
    erwartet: dict[str, Any] = {
        b.target_key: None for b in basis_beitraege(sensor_mapping)
    }
    investitionen = (sensor_mapping or {}).get("investitionen") or {}
    for inv_id_str, inv_data in investitionen.items():
        if not isinstance(inv_data, dict):
            continue
        inv = investitionen_by_id.get(str(inv_id_str))
        if inv is None:
            continue
        if not inv.ist_aktiv_an(tag):
            continue
        for b in investition_beitraege(inv, inv_data):
            erwartet[b.target_key] = inv
    return erwartet


def komponenten_key_label(key: str, inv: Any = None) -> str:
    """Anwender-Name eines Komponenten-Keys (`pv_7` → „Dach Süd").

    Geteilt von Daten-Checker-Meldung und Reparatur-Rückmeldung — ein Anwender
    darf dieselbe Komponente nicht in zwei Sichten verschieden heißen sehen.
    Ohne Bezeichnung bleibt der Präfix (`waermepumpe_7` → „waermepumpe").
    """
    if key in ("einspeisung", "netzbezug"):
        return key.capitalize()
    bezeichnung = getattr(inv, "bezeichnung", None) if inv is not None else None
    if bezeichnung:
        return bezeichnung
    praefix, _, _rest = key.rpartition("_")
    return praefix or key


# ── Hourly-Normalisierung (Phase C v3.35.0, Issue #298) ─────────────────────
#
# Pattern-Klasse: Aggregator-Drift bei parallelen Pfaden ([[feedback_aggregator_symmetrie]],
# Audit-§6.2). Vor v3.35.0 sammelten die beiden Hourly-Aggregatoren
# (`snapshot.aggregator.get_hourly_kwh_by_category` +
# `snapshot.lts_aggregator.get_hourly_kwh_by_category_lts`) ihre Counter-
# Einträge, indem sie `keys._categorize_counter` ROH pro gemapptem Feld
# aufriefen. Das umging die Either-Or- + parent-Skip-Whitelist, die der Daily-
# Pfad seit v3.33.0 über `investition_beitraege` zentral hat — Folge: ein
# E-Auto mit BEIDEN Gesamt-Zählern (`verbrauch_kwh` UND `ladung_kwh`, evcc-
# Muster, #262 junky84) wurde in der Stunden-Bilanz doppelt gezählt
# (`_categorize_counter` mappt beide auf `verbrauch_eauto`), während der Daily-
# Pfad nur einen nahm.
#
# Variante 2 (PLAN §3 C.1): NICHT `_categorize_counter` patchen (sechster
# Schutz), sondern die Feld-Auswahl strukturell durch DIESELBE Normalisierung
# wie der Daily-Pfad routen — `investition_beitraege`/`basis_beitraege` sind
# damit die einzige Whitelist+Either-Or+parent-Skip-Quelle für Daily UND
# Hourly. `_categorize_counter` ist hier auf seine reine Aufgabe reduziert:
# Feld → Energiefluss-Kategorie (kein Whitelist-Gatekeeper mehr).


@dataclass(frozen=True)
class HourlyEintrag:
    """Ein normalisierter Counter-Eintrag für die Hourly-Aggregation.

    - `feld`: das Mapping-Feld (z. B. `ladung_kwh`) — zum Auflösen der
      `sensor_id`/`entity_id` aus dem jeweiligen Mapping-Dict.
    - `kategorie`: Energiefluss-Kategorie (`_categorize_counter`-Rückgabe,
      z. B. `verbrauch_eauto`, `ladung_batterie`).
    - `fallback_gruppe`: optionale Either-Or-Markierung (identisch zur
      `KomponentenBeitrag.fallback_gruppe` des Daily-Pfads). Der Aggregator
      nimmt pro Gruppe nur den ersten Eintrag mit Tages-Sensordaten — exakt
      wie `get_komponenten_tageskwh{,_lts}`.
    """

    feld: str
    kategorie: str
    fallback_gruppe: Optional[str] = None


def basis_hourly_eintraege(
    sensor_mapping: dict,
    *,
    pv_je_investition_extern: bool = False,
) -> list[HourlyEintrag]:
    """Hourly-Einträge der Basis-Zähler (Einspeisung/Netzbezug/PV gesamt).

    Spiegelt `basis_beitraege` auf die Energiefluss-Kategorie-Ebene —
    einschließlich der Alles-oder-nichts-Regel für `pv_gesamt`; das Flag wird
    unverändert durchgereicht.
    """
    out: list[HourlyEintrag] = []
    for b in basis_beitraege(
        sensor_mapping, pv_je_investition_extern=pv_je_investition_extern
    ):
        kat = _categorize_counter(b.feld, None, None)
        if kat:
            out.append(HourlyEintrag(feld=b.feld, kategorie=kat,
                                     fallback_gruppe=b.fallback_gruppe))
    return out


def investition_hourly_eintraege(
    inv,
    sensor_mapping_for_inv: dict,
    *,
    ist_verfuegbar: Optional[Callable[[str], bool]] = None,
) -> list[HourlyEintrag]:
    """Hourly-Einträge einer Investition — Whitelist + Either-Or + parent-Skip
    aus `investition_beitraege` (Daily-SoT), gemappt auf die Energiefluss-
    Kategorie via `_categorize_counter`.

    Dadurch konsumieren Daily- und Hourly-Pfad dieselbe einzige Auflösungs-
    Quelle (Issue #298 / Audit-§6.2). Felder, deren Kategorie `None` ist,
    werden weggelassen (defensiv; `investition_beitraege` emittiert ohnehin nur
    Felder mit gültiger Kategorie).

    `ist_verfuegbar` wird an `investition_beitraege` durchgereicht — der MQTT-/
    Standalone-Pfad (#317) nutzt das, um dieselbe Normalisierung quellen-agnostisch
    zu fahren.
    """
    typ = getattr(inv, "typ", None)
    parameter = getattr(inv, "parameter", None)
    out: list[HourlyEintrag] = []
    for b in investition_beitraege(inv, sensor_mapping_for_inv, ist_verfuegbar=ist_verfuegbar):
        kat = _categorize_counter(b.feld, typ, parameter)
        if kat:
            out.append(HourlyEintrag(feld=b.feld, kategorie=kat,
                                     fallback_gruppe=b.fallback_gruppe))
    return out


def mqtt_hourly_eintraege(
    mqtt_sensor_keys: Iterable[str],
    investitionen_by_id: dict,
    investitionen_map: dict,
) -> list[tuple[str, str, Optional[str]]]:
    """MQTT-/Standalone-Counter normalisiert wie der HA-gemappte Pfad (#317).

    Geteilte Quelle für die beiden Snapshot-Hourly-Konsumenten
    (`snapshot.aggregator.get_hourly_kwh_by_category` +
    `snapshot.reaggregator.get_reaggregate_preview`). Vor #317 hängten beide
    MQTT-Zweige ihre Einträge mit `fallback_gruppe=None` an — ein E-Auto, das
    via MQTT BEIDE Gesamt-Zähler publiziert (`ladung_kwh` UND `verbrauch_kwh`,
    evcc-Bridge), wurde so in der Stunden-Bilanz doppelt gezählt (gleiche
    #298-Klasse, nur auf dem MQTT-Pfad). Inv-Keys laufen jetzt durch
    `investition_hourly_eintraege` mit „MQTT-Key vorhanden" als Verfügbarkeits-
    Quelle → Whitelist + Either-Or + parent-Skip greifen identisch zum HA-Pfad.

    Basis-Keys haben keinen Either-Or-Partner und werden direkt kategorisiert
    (`fallback_gruppe=None`). **Ausnahme `basis:pv_gesamt`** (Stufe 1 zu F-7):
    der Anlagen-Zählerstand fällt weg, sobald ein Erzeuger seinen eigenen
    PV-Zähler trägt — geprüft über BEIDE Quellen (`sensor_mapping` und die hier
    gesehenen MQTT-Keys), s. `pv_je_investition_belegt`.

    ⚠ Die Verdrängung ist **keine** Either-Or-Gruppe: `resolve_either_or_eintraege`
    ist 1-aus-n und würde bei zwei Modulen plus Aggregat eines der beiden
    Module verlieren. Hier ist die Regel n-schlägt-1.

    Args:
        mqtt_sensor_keys: bereits via `_mqtt_key_to_sensor_key` aufgelöste,
            seen-gefilterte Sensor-Keys (`basis:<feld>` / `inv:<id>:<feld>`).
        investitionen_by_id: `{str(inv_id): Investition}` (für typ/parameter/parent).
        investitionen_map: `sensor_mapping["investitionen"]` (inv_data für typ-
            unabhängige Felder; Verfügbarkeit kommt aus den MQTT-Keys).

    Returns:
        `[(sensor_key, kategorie, fallback_gruppe)]` — entity_id ist beim Aufrufer
        immer None (MQTT-Fallback im Snapshot-Reader).
    """
    basis_felder: set[str] = set()
    inv_felder: dict[str, set[str]] = {}
    for sk in mqtt_sensor_keys:
        if sk.startswith("basis:"):
            basis_felder.add(sk.split(":", 1)[1])
        elif sk.startswith("inv:"):
            _, inv_id, feld = sk.split(":", 2)
            inv_felder.setdefault(inv_id, set()).add(feld)

    pv_verdraengt = pv_je_investition_belegt_in_map(investitionen_map, inv_felder)

    out: list[tuple[str, str, Optional[str]]] = []
    for feld in basis_felder:
        if feld == "pv_gesamt" and pv_verdraengt:
            continue
        kat = _categorize_counter(feld, None, None)
        if kat:
            out.append((f"basis:{feld}", kat, None))

    for inv_id, felder_vorhanden in inv_felder.items():
        inv = investitionen_by_id.get(inv_id) or investitionen_by_id.get(str(inv_id))
        if inv is None:
            continue
        inv_data = (investitionen_map or {}).get(inv_id) \
            or (investitionen_map or {}).get(str(inv_id)) or {}
        for he in investition_hourly_eintraege(
            inv, inv_data,
            ist_verfuegbar=lambda feld, _s=felder_vorhanden: feld in _s,
        ):
            out.append((f"inv:{inv_id}:{he.feld}", he.kategorie, he.fallback_gruppe))
    return out


def resolve_either_or_eintraege(eintraege, gruppe_fn, hat_tagesdaten_fn):
    """Either-Or-Auflösung auf TAGES-Ebene — single source für alle drei
    Hourly-Counter-Konsumenten (snapshot-/lts-Aggregator + reaggregator-
    Vorschau), Issue #298.

    Pro `fallback_gruppe` überlebt der ERSTE Eintrag, dessen Sensor an diesem
    Tag überhaupt Daten liefert (`hat_tagesdaten_fn(eintrag) -> bool`); die
    übrigen Gruppen-Mitglieder fallen raus. Einträge ohne Gruppe
    (`gruppe_fn(eintrag)` falsy — z. B. MQTT-Quellen) bleiben unberührt.

    Spiegelt exakt die Daily-Auflösung (`get_komponenten_tageskwh{,_lts}`):
    Tages-Ebene statt pro Stunde, damit die Sensor-Wahl über alle 24 Slots
    stabil bleibt und Σ Hourly == Tages-Boundary gilt. Reihenfolge-erhaltend
    (primärer Beitrag zuerst — z. B. E-Auto `ladung_kwh` vor `verbrauch_kwh`).

    Args:
        eintraege: beliebige Eintrags-Sequenz (Tupel/Objekte).
        gruppe_fn: extrahiert die `fallback_gruppe` eines Eintrags (oder None).
        hat_tagesdaten_fn: Tages-Verfügbarkeit des Sensors eines Eintrags.
    """
    out = []
    genommen: set[str] = set()
    for e in eintraege:
        grp = gruppe_fn(e)
        if grp and grp in genommen:
            continue
        if grp:
            if not hat_tagesdaten_fn(e):
                continue
            genommen.add(grp)
        out.append(e)
    return out
