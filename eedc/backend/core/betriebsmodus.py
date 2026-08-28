"""Betriebsmodus einer Wärmepumpe/Klimaanlage — Kanon und Normalisierung (#263 K-2, S1).

**Warum es diese Datei gibt.** Eine Split-Klimaanlage ist physikalisch eine
Luft-Luft-Wärmepumpe: dasselbe Gerät heizt im Winter und kühlt im Sommer, über
**denselben** Stromzähler (Konzept `docs/KONZEPT-263-klima-split.md`, D4). Die
Aufteilung „was ging ins Heizen, was ins Kühlen" ist aus keinem vorhandenen Feld
rekonstruierbar — sie entsteht nur, wenn eedc den Betriebsmodus **zur Messzeit**
mitschreibt.

**Der Lesepfad ist bewusst eng gehalten** (Konzept §3.3): eine feste Wertemenge,
eine Normalisierungstabelle Hersteller→Kanon, sonst nichts. Ein zweiter
Anwendungsfall für einen generischen Zustandssensor existiert nicht, und die
P-11-Lehre lautet: nicht auf Vorrat bauen.

**Was hier NICHT passiert:** Es wird nichts geraten. `auto`/`heat_cool` und jeder
unbekannte Wert werden zu `unbestimmt` — sie einer Seite zuzuschlagen wäre eine
erfundene Aufteilung (ADR-002/P4). `unbestimmt` fällt später in die abgeleitete
Zeile „nicht aufgeteilt", zusammen mit Entfeuchten, Lüften und Standby.

⚠ **`hvac_action` (der Ist-Betrieb) wird NICHT verlangt** (Konzept D2): in
HA-Core definiert nur `AtwDeviceZoneClimate` (Luft-**Wasser**) die Property;
`AtaDeviceClimate` (Luft-Luft, also genau der Klimaanlagen-Fall) und die
Basisklasse nicht. Wer sie verlangt, baut für Daikin und sperrt den Rest aus.
Wo sie vorhanden ist, **verfeinert** sie — deshalb der optionale zweite
Parameter, nie eine Bedingung.
"""

from typing import Final, Optional

# ── Kanon ────────────────────────────────────────────────────────────────────
#
# Sieben Werte. Gespeichert und ausgewiesen werden die Teilmengen zu `heizen`,
# `warmwasser` und `kuehlen`; die vier übrigen Klassen fallen in „nicht
# aufgeteilt".
#
# ⭐ **`warmwasser` kam am 27.08.2026 dazu (N-336) — es hätte von Anfang an hier
# stehen müssen.** Der Kanon ist aus HA-`HVACMode` abgeleitet, und der kennt die
# Trinkwassererwärmung nicht: Home Assistant führt sie in einer eigenen Domäne
# (`water_heater`). Für HA ist das richtig. Übernommen wurde es, ohne es je
# gegen **eedcs eigene** Funktionsliste zu halten — und die führt Warmwasser an
# vier Stellen: `strom_warmwasser_kwh` · `warmwasser_kwh` · das Live-Feld
# „Leistung Warmwasser" · `arbeitszahl_je_funktion`. Zwei Vokabulare für
# dieselbe Sache, nie abgeglichen.
#
# ⛔ **Der Beleg für die alte Fassung war eine Aufzählung, kein Ausschluss.**
# Hier stand: *„belegt durch D11: in der Praxis fahren die drei Melder nur
# Heizen und Kühlen"*. Das war für eine **Split-Klimaanlage** richtig — dafür
# ist KONZEPT-263 geschrieben, und die hat keinen Warmwasserkreis. Als Vokabular
# der ganzen Wärme/Klima-Fläche trägt der Satz nicht: `soll-waerme-klima.md`
# §7/A8 sagt zu D11 ausdrücklich *„belegt es für drei Melder — keine
# Allgemeinaussage"*, und §3.2a führt Warmwasser als eigene Funktion mit `E_ww`
# und `Q_ww`. Am 27.08. haben es zwei Melder unabhängig hingeschrieben:
# dietmar1968 mit Begründung (T89667 #225 — ein Kältekreis, ein Umschaltventil,
# darum schließen sich die drei Betriebsformen aus) und MartyBr (#230: *„die WP
# heizt, macht WW oder kühlt"*).
#
# ⚠ **Und eedc hat es selbst verlangt, bevor es das Wort kannte:** Die
# Template-Vorlage im Handbuch (`dd5bbe41`, 27.08.) weist Anwender an, einen
# Sensor zu bauen, der `warmwasser` ausgibt — den `normalisiere_betriebsmodus`
# dann zu `unbestimmt` machte. Eine Anleitung, deren Ergebnis wir wegwerfen.
HEIZEN: Final[str] = "heizen"
WARMWASSER: Final[str] = "warmwasser"
KUEHLEN: Final[str] = "kuehlen"
ENTFEUCHTEN: Final[str] = "entfeuchten"
LUEFTEN: Final[str] = "lueften"
AUS: Final[str] = "aus"
UNBESTIMMT: Final[str] = "unbestimmt"

BETRIEBSMODUS_KANON: Final[tuple[str, ...]] = (
    HEIZEN, WARMWASSER, KUEHLEN, ENTFEUCHTEN, LUEFTEN, AUS, UNBESTIMMT,
)

#: Die Klassen, für die es eine eigene Teilmenge gibt.
#:
#: ⛔ **`AUFGETEILTE_MODI` ist KEINE Teilmenge von `MESSBARE_MODI`, und das ist
#: Absicht** (N-336). Die beiden Mengen beantworten verschiedene Fragen:
#: *„welche Betriebsart kann eedc aus einem Modus-Signal ABLEITEN?"* gegen
#: *„für welche Betriebsart bietet eedc einen eigenen ZÄHLER an?"* Warmwasser
#: kann eedc ableiten, bekommt aber **kein** `betriebsart_strom_warmwasser_kwh`
#: — die Begründung steht bei `MESSBARE_MODI`. Wer die eine Menge aus der
#: anderen ableiten will, macht aus zwei Fragen eine.
AUFGETEILTE_MODI: Final[frozenset[str]] = frozenset({HEIZEN, WARMWASSER, KUEHLEN})

#: Kanon → deutscher Klartext für die **Zuordnungs-Fläche** (F-52/F-53).
#:
#: **Warum das hier steht und nicht im Frontend:** Es ist keine Formatierung,
#: sondern die Deutung eines Kanon-Werts — und der Kanon liegt in dieser Datei.
#: Eine zweite Tabelle im Client wäre genau die Drift, gegen die `MODUS_STROM_FELD`
#: einen Wächter hat. Die Zahlen-Labels der Auswertung („davon Heizen") sind
#: davon unberührt: sie beschriften eine **Menge**, nicht einen Zustand.
BETRIEBSMODUS_LABEL: Final[dict[str, str]] = {
    HEIZEN: "Heizen",
    WARMWASSER: "Warmwasser",
    KUEHLEN: "Kühlen",
    ENTFEUCHTEN: "Entfeuchten",
    LUEFTEN: "Lüften",
    AUS: "Aus",
    UNBESTIMMT: "Unbestimmt",
}


#: Kanon → Symbolname für die Sichten, die **jetzt** meinen (#398 Stufe 2/3).
#:
#: **Warum hier und nicht im Frontend:** dieselbe Begründung wie bei
#: `BETRIEBSMODUS_LABEL` — es ist die Deutung eines Kanon-Werts, und der Kanon
#: liegt in dieser Datei. Die Namen sind die des Client-Icon-Registers
#: (`EnergieFluss.tsx::ICON_MAP`), das sie auf Lucide-Komponenten abbildet.
#:
#: ⛔ **`aus` und `unbestimmt` stehen bewusst NICHT drin.** Für sie gibt es kein
#: eigenes Symbol: das Gerät zeigt dann sein **Typ-Icon** wie bisher. Ein
#: Sondersymbol für „ich weiß es nicht" wäre eine Aussage, die eedc nicht hat.
#:
#: ⚠ **`entfeuchten` ist NICHT `droplets`** — das trägt im Live-Bild bereits die
#: **Warmwasser**-Rolle (`live_komponenten_builder`). Zwei Bedeutungen auf einem
#: Symbol sind genau die Drift, gegen die Regel 0a steht („eine Datenrolle, ein
#: Symbol"), deshalb `waves`.
#:
#: ⭐ **Und genau deshalb ist `warmwasser` hier `droplets`** (N-336, 27.08.):
#: Die Zeile darüber hat den Tropfen für diese Rolle freigehalten, bevor es den
#: Kanon-Wert dazu gab. Regel 0a, andere Richtung — dieselbe Datenrolle, dasselbe
#: Symbol, auch wenn sie über zwei Quellen ins Bild kommt (Leistungssensor oder
#: Betriebsmodus).
BETRIEBSMODUS_ICON: Final[dict[str, str]] = {
    HEIZEN: "flame",
    WARMWASSER: "droplets",
    KUEHLEN: "snowflake",
    ENTFEUCHTEN: "waves",
    LUEFTEN: "fan",
}


#: Modi, die im **Live-Bild** keinen Klartext bekommen (MartyBr, T89667 #230).
#:
#: ⭐ **Dieselbe Regel wie bei `BETRIEBSMODUS_ICON` — und für Text wiegt sie
#: schwerer.** Dort steht als Begründung: *„Ein Sondersymbol für ‚ich weiß es
#: nicht' wäre eine Aussage, die eedc nicht hat."* Der Satz gilt für ein Wort
#: erst recht: Ein Symbol kann man übersehen, „Unbestimmt" liest man. Auf
#: MartyBrs Bildschirm stand es unter einer Wärmepumpe mit 0 W — eine Kachel,
#: die nichts behaupten musste, behauptete Unwissen.
#:
#: ⚠ **`aus` steht bewusst NICHT hier.** „Aus" ist eine Aussage: das Gerät läuft
#: nicht. Nur `unbestimmt` ist die Abwesenheit einer Aussage.
#:
#: ⛔ **`BETRIEBSMODUS_LABEL` bleibt vollständig.** Dort beschriftet der Text
#: einen **Wert** auf der Zuordnungs-Fläche („eedc versteht das als:
#: Unbestimmt") — eine richtige und nötige Auskunft. Hier behauptet er einen
#: **Zustand jetzt**. Dieselbe Trennung wie zwischen `BETRIEBSMODUS_LABEL` und
#: `BETRIEBSART_LABEL`: Zustand gegen Menge, und keiner der beiden Texte ist
#: eine Formatierung des anderen.
BETRIEBSMODUS_LIVE_OHNE_KLARTEXT: Final[frozenset[str]] = frozenset({UNBESTIMMT})


# ── Feldnamen der Teilmengen (#263 K-2, S3) ──────────────────────────────────
#
# **Warum eigene Namen und nicht `strom_heizen_kwh`** (Entscheid E-G, gemessen
# 2026-08-18; das Konzept empfahl in §3.2 noch die Wiederverwendung): Dieses
# Feld gibt es bereits, aber es trägt dort eine **andere** Bedeutung — bei
# `getrennte_strommessung=True` ist es ein **Summand**
# (`Gesamt = strom_heizen + strom_warmwasser`), hier wäre es eine **Teilmenge**
# von `stromverbrauch_kwh`. Drei Stellen schließen aus seiner bloßen
# **Anwesenheit** auf die getrennte Messung und würden mitkippen:
# `investitionen/dashboards.py` (`if 'strom_heizen_kwh' in d`) → daran hängt
# `cop_heizen`, und daran wiederum `WaermepumpeHubBloecke.tsx`
# (`hatGetrennteStrom`). Mit abgeleiteter Wärme (§3.4) käme dort als „JAZ"
# exakt die gepflegte JAZ heraus — der §3.5-Verstoß, gegen den S3 gebaut ist.
# Eigene Namen machen die Kollision **strukturell** unmöglich, statt sie an
# vier Stellen abzufangen; und eine WP mit getrennter Messung **und**
# Modus-Sensor behält beide Angaben nebeneinander.
#
# ⚑ **Die Namen sind an den Kanon gebunden, nicht frei gewählt.** Sie stehen
# hier ausgeschrieben (nicht generiert), weil dieses Projekt von der
# Grep-Barkeit lebt — aber `test_263_k2_modus_split.py::test_feldnamen_folgen_dem_kanon`
# hält sie gegen `AUFGETEILTE_MODI`: für jeden aufgeteilten Modus genau ein
# Feld, und jeder Name genau `modus_strom_<modus>_kwh`. Eine siebte
# Betriebsart kostet damit **einen Eintrag oben** — und der Wächter sagt
# sofort, was dazu fehlt. Ohne ihn wäre „eine spätere Betriebsart kostet ein
# Feld, keine Migration" (Konzept §3.1, Folge 4) eine Behauptung.
MODUS_STROM_FELD: Final[dict[str, str]] = {
    HEIZEN: "modus_strom_heizen_kwh",
    WARMWASSER: "modus_strom_warmwasser_kwh",
    KUEHLEN: "modus_strom_kuehlen_kwh",
}


# ── GEMESSENE Betriebsart-Felder (#263, Fassung 2026-08-21) ──────────────────
#
# **Der Unterschied zu `MODUS_STROM_FELD` ist die Herkunft, nicht die Größe.**
# Dort steht, was eedc aus dem Betriebsmodus **abgeleitet** hat; hier steht,
# was ein Zähler **gemessen** hat. Beides nebeneinander zu führen ist kein
# Doppel, sondern dieselbe Unterscheidung, die eedc bei der Heizwärme längst
# macht (`waerme_abgeleitet`): eine gerechnete Zahl darf nie wie eine gemessene
# aussehen. Der Vorrang liegt an genau einer Stelle
# (`core/berechnungen/imd_monatsaggregat.py`): **gemessen schlägt abgeleitet**,
# nie beides addiert.
#
# **Warum eigene Namen und nicht `strom_heizen_kwh`.** Das gibt es schon und
# bedeutet etwas anderes — bei `getrennte_strommessung=True` ist es ein
# **Summand** (Gesamt = Heizen + Warmwasser), hier wäre es eine **Teilmenge**
# des Gesamtverbrauchs. Drei Stellen schließen aus seiner bloßen Anwesenheit
# auf die getrennte Messung. Dieselbe Begründung wie oben bei
# `MODUS_STROM_FELD`, nur eine Ebene weiter.
#
# **Alle vier Betriebsarten, nicht nur die zwei aufgeteilten.** Der abgeleitete
# Split kann nur Heizen und Kühlen (mehr gibt ein Modus-Signal nicht her, D11);
# ein Zähler kann jede Betriebsart messen, und wer sich per Utility-Meter vier
# Tarife baut, hat vier Zahlen. `AUFGETEILTE_MODI` bleibt davon **unberührt** —
# die abgeleitete Aufteilung ändert sich nicht.
#
# Ausgeschrieben statt generiert, aus demselben Grund wie oben (Grep-Barkeit);
# `test_263_betriebsart_felder.py` hält beide Tabellen gegen den Kanon.

#: Betriebsarten, für die eedc einen eigenen **Betriebsart-Zähler** anbietet.
#:
#: ⛔ **`warmwasser` steht hier bewusst NICHT — obwohl es im Kanon steht und
#: obwohl es messbar ist** (N-336, 27.08.). Die Größe gibt es, sie heißt
#: `strom_warmwasser_kwh`, und sie gehört einer **anderen Familie** an:
#:
#: * `strom_heizen_kwh` / `strom_warmwasser_kwh` sind **Summanden** — bei
#:   `getrennte_strommessung=True` ergeben sie zusammen den Gesamtverbrauch.
#: * `betriebsart_strom_*_kwh` sind **Teilmengen** des Gesamtverbrauchs.
#:
#: Die zwei Familien unbeschriftet nebeneinander anzubieten ist die
#: Zweideutigkeit, an der ein Tester schon einmal zwei Felder addiert hat
#: (Forum simon42 #89667/62) — der Satz steht ausgeschrieben in
#: `field_definitions.py` über `_betriebsart_felder`, und er gilt unverändert.
#: Ein `betriebsart_strom_warmwasser_kwh` wäre der **zweite** Weg zu derselben
#: Zahl, ohne einen einzigen Fall, den der erste nicht kann.
#:
#: ⚠ **Gegengeprüft an einer realen Zuordnungs-Fläche** (MartyBr, T89667 #230):
#: Seine Wärmepumpe führt unter *„Weitere Größen erfassen"* bereits **acht**
#: Einträge, die er nicht braucht. Zwei weitere wären die P-6-Falle — ein
#: Angebot, das niemand einlöst.
#:
#: ⭐ **Nichts geht dabei verloren, und das ist prüfbar:** Es kann heute niemand
#: einen Warmwasser-Betriebsart-Zähler pflegen, also gibt es keine Daten, die
#: unter dem engeren Modell falsch gespeichert würden (`soll-waerme-klima.md`
#: §7, Trennlinie Modell/Ansicht). Ein späteres Hinzufügen wäre rein additiv.
MESSBARE_MODI: Final[tuple[str, ...]] = (HEIZEN, KUEHLEN, LUEFTEN, ENTFEUCHTEN)

#: Gemessener **Strom**verbrauch je Betriebsart (Teilmenge des Gesamtverbrauchs).
BETRIEBSART_STROM_FELD: Final[dict[str, str]] = {
    HEIZEN: "betriebsart_strom_heizen_kwh",
    KUEHLEN: "betriebsart_strom_kuehlen_kwh",
    LUEFTEN: "betriebsart_strom_lueften_kwh",
    ENTFEUCHTEN: "betriebsart_strom_entfeuchten_kwh",
}

#: Gemessene **abgegebene Nutzenergie** je Betriebsart (Wärme bzw. Kälte).
#: Bewusst nicht „waerme": im Kühlbetrieb ist die Nutzenergie Kälte, und ein
#: Feldname, der etwas anderes behauptet als er trägt, ist die Klasse, an der
#: `heizenergie_kwh` schon einmal missverstanden wurde (#120).
BETRIEBSART_NUTZENERGIE_FELD: Final[dict[str, str]] = {
    HEIZEN: "betriebsart_nutzenergie_heizen_kwh",
    KUEHLEN: "betriebsart_nutzenergie_kuehlen_kwh",
    LUEFTEN: "betriebsart_nutzenergie_lueften_kwh",
    ENTFEUCHTEN: "betriebsart_nutzenergie_entfeuchten_kwh",
}

def ist_betriebsart_strom_feld(feld: str) -> bool:
    """Ist dieser Feld-Key ein **gemessener** Betriebsart-Stromzähler? (F-60)

    Die Frage, die eine **Zuordnung** beantwortet — im Gegensatz zu
    ``berechnungen.hat_gemessene_betriebsart``, das eine **Zeile** befragt.
    Beide werden gebraucht und beantworten Verschiedenes: ob ein Weg
    eingerichtet ist, und ob auf ihm schon etwas angekommen ist.

    ⚠ **Suffix-tolerant**, denn es gibt diese Zähler je Innengerät
    (``betriebsart_strom_kuehlen_kwh-3``). Bauform wie ``ist_stand_feld`` und
    ``ist_zustand_feld``: *Eigenschaft am Feld, ein Leser* — statt an jeder
    Prüfstelle eine Namensliste samt Suffix-Wissen nachzubauen. Lokaler Import,
    weil ``field_definitions`` diese Datei bereits liest.
    """
    from backend.core.field_definitions import basis_feld_key

    return basis_feld_key(feld) in frozenset(BETRIEBSART_STROM_FELD.values())


#: Deutsche Bezeichnung der Betriebsart für Feld-Labels. Getrennt von
#: `BETRIEBSMODUS_LABEL`, weil das dort ein **Zustand** ist („Kühlen") und hier
#: eine **Betriebsphase** benannt wird („Kühlbetrieb") — dieselbe Trennung, die
#: `betriebsmodus_klartext` von den Mengen-Labels trennt.
BETRIEBSART_LABEL: Final[dict[str, str]] = {
    HEIZEN: "Heizbetrieb",
    KUEHLEN: "Kühlbetrieb",
    LUEFTEN: "Lüftbetrieb",
    ENTFEUCHTEN: "Entfeuchtungsbetrieb",
}

#: Stunden des Monats mit **gültigem Modus-Signal** — das Qualitätsmaß neben
#: den zwei Mengen (Konzept §3.3). Es trennt die zwei Fälle, die der Anwender
#: unterscheiden können muss: „lief in anderen Betriebsarten" (Abdeckung hoch,
#: Rest > 0) gegen „eedc hat nicht hingesehen" (Abdeckung niedrig).
#: Zugleich die Zeitbasis der Kuehl-Kennzahl.
#:
#: ⚠ Hier stand „die Zeitbasis, die K-1 (SEER) ohnehin braucht“. K-1 ist
#: seit dem 26.08.2026 beantwortet — als ``arbeitszahl_kuehlen`` und ausdruecklich
#: **nicht** unter dem Namen SEER (der ist eine genormte Pruefstandsgroesse, dies
#: ein gemessener Quotient ueber einen Zeitraum). Ein Verweis auf eine offene
#: Massnahme, die keine mehr ist, laedt zum Nachbauen ein.
MODUS_ABDECKUNG_FELD: Final[str] = "modus_abdeckung_h"

#: Alle drei Felder, die der Modus-Split in `verbrauch_daten` schreibt — für
#: Schreibpfad, Wächter und die Stellen, die sie **nicht** als Bilanzgröße
#: behandeln dürfen.
MODUS_SPLIT_FELDER: Final[tuple[str, ...]] = (
    *sorted(MODUS_STROM_FELD.values()), MODUS_ABDECKUNG_FELD,
)


# ── Normalisierung Hersteller → Kanon ────────────────────────────────────────
#
# Grundlage ist `HVACMode` aus HA-Core: HA normalisiert die Herstellerwerte
# bereits auf diese sieben Zeichenketten, bevor sie im State stehen. Die
# deutschen Schreibweisen daneben fangen Template-Sensoren ab, mit denen sich
# Anwender den Modus heute selbst bauen (der Weg, den kingcap1 und dietmar1968
# im Forum beschrieben haben).
#
# ⚠ `auto` und `heat_cool` stehen bewusst auf `unbestimmt` und nicht auf einer
# der beiden Seiten: das Gerät entscheidet dort selbst, und ohne `hvac_action`
# weiß eedc nicht, was es gerade tut (D1/D2).
_ZUSTAND_ZU_KANON: Final[dict[str, str]] = {
    # HVACMode (HA-Core)
    "heat": HEIZEN,
    "cool": KUEHLEN,
    "dry": ENTFEUCHTEN,
    "fan_only": LUEFTEN,
    "off": AUS,
    "auto": UNBESTIMMT,
    "heat_cool": UNBESTIMMT,
    # Deutsche Schreibweisen aus selbstgebauten Template-Sensoren
    "heizen": HEIZEN,
    "kuehlen": KUEHLEN,
    "kühlen": KUEHLEN,
    "entfeuchten": ENTFEUCHTEN,
    "lueften": LUEFTEN,
    "lüften": LUEFTEN,
    "aus": AUS,
    "automatik": UNBESTIMMT,
    # Warmwasser (N-336). **In `HVACMode` gibt es dafür nichts** — HA führt die
    # Trinkwassererwärmung in der Domäne `water_heater`. Die Werte hier kommen
    # deshalb aus den zwei Quellen, die es real gibt:
    #   • die deutschen Schreibweisen aus Template-Sensoren — `warmwasser` ist
    #     der Wert, den **eedcs eigene Handbuch-Vorlage** erzeugt;
    #   • die englischen Kurzformen, die Heizungs-Integrationen für
    #     *domestic hot water* verwenden.
    # ⚠ Bewusst NICHT dabei: `water_heater` als Wort und alles, was nur
    # „irgendwas mit Wasser" heißt. eedc rät nicht — wer einen Wert braucht, der
    # hier fehlt, bekommt `unbestimmt` und die Werte-Tabelle im Handbuch.
    "warmwasser": WARMWASSER,
    "brauchwasser": WARMWASSER,
    "trinkwasser": WARMWASSER,
    "dhw": WARMWASSER,
    "hot_water": WARMWASSER,
    "water_heating": WARMWASSER,
}

# `HVACAction` (HA-Core) — nur wo die Integration sie überhaupt liefert.
# Sie beschreibt den **Ist**-Betrieb und **verfeinert** damit den eingestellten
# Modus (D2). Jeder Wert hier nennt eine **Richtung**: Wo eine steht, schlägt
# sie den eingestellten Modus, denn sie sagt, was das Gerät wirklich tut.
#
# ⛔ **`idle` steht bewusst NICHT in dieser Tabelle — bis zum 28.08.2026 stand
# es hier auf `UNBESTIMMT`, und das war der Fehler aus Issue #399.** `idle`
# nennt keine Richtung; es sagt *„gerade läuft der Verdichter nicht"*. Damit
# **verfeinerte** es nichts, es **verwarf** — und zwar den einzigen Wert, der
# die Richtung kannte.
#
# ⭐ **Der Melder hat es fotografiert** (Klausnn, #399/#263, Panasonic
# Multisplit): *Zustand Roh* = `cool`, *Aktuelle Aktion* = `Leerlauf` — und
# Home Assistant selbst beschriftet die Kachel mit **„Leerlauf (Kühlbetrieb)"**.
# HA behält den Modus, wenn das Gerät taktet; eedc warf ihn weg. Bei einem
# taktenden Gerät ist das nicht eine Stunde, sondern der **Großteil** — der
# Strom fiel in „nicht aufgeteilt".
#
# ⚠ **Der Konzepttext stand die ganze Zeit auf der Seite des Melders:**
# *„`hvac_action` wird nicht verlangt (D2); wo es vorhanden ist, **verfeinert**
# es"* (`KONZEPT-263-klima-split.md`). Der Code machte daraus ein Überschreiben.
# Dieser Fix stellt die Regel her, er ändert sie nicht.
#
# ⛔ **`off` bleibt drin, `idle` nicht — der Unterschied ist keine Feinheit:**
# `off` ist eine vollständige Aussage über das Gerät („es läuft nicht"), `idle`
# eine über den Augenblick („es läuft gerade nicht"). D6 bleibt gedeckt, weil
# die Rückfallebene ihrerseits `unbestimmt` liefert, wo kein Modus dasteht.
_AKTION_ZU_KANON: Final[dict[str, str]] = {
    "heating": HEIZEN,
    "preheating": HEIZEN,
    "defrosting": HEIZEN,
    "cooling": KUEHLEN,
    "drying": ENTFEUCHTEN,
    "fan": LUEFTEN,
    "off": AUS,
}

#: Ist-Betriebsarten, die **keine Richtung** nennen und deshalb auf den
#: eingestellten Modus zurückfallen, statt ihn zu verwerfen (#399).
#:
#: ⚠ **Eine eigene Menge und kein `if aktion == "idle"`.** HA-Integrationen
#: melden denselben Zustand unter mehreren Namen; wer hier einen zweiten Fall
#: findet, trägt ihn ein, statt eine zweite Bedingung danebenzustellen — das
#: ist dieselbe Bauform wie `_KEIN_ZUSTAND` darunter.
_AKTION_OHNE_RICHTUNG: Final[frozenset[str]] = frozenset({"idle"})

# States, die HA für „gerade nichts zu sagen" benutzt. Sie sind **kein**
# Betriebsmodus und dürfen nicht zu `unbestimmt` werden: `unbestimmt` heißt
# „das Gerät lief, eedc kann die Seite nicht zuordnen", diese hier heißen
# „eedc hat gar nicht hingesehen". Der Unterschied trägt später die
# Abdeckungs-Kennzahl (Konzept §3.3).
_KEIN_ZUSTAND: Final[frozenset[str]] = frozenset({"unknown", "unavailable", "none", ""})


def normalisiere_betriebsmodus(
    zustand: Optional[str],
    hvac_action: Optional[str] = None,
) -> Optional[str]:
    """Roher HA-State → Kanon-Wert, oder ``None`` wenn es keinen Modus gibt.

    Args:
        zustand: der State der `climate`-Entität (bzw. eines Template-Sensors),
            z. B. ``"heat"``. Groß-/Kleinschreibung und Randleerzeichen sind egal.
        hvac_action: optional der Ist-Betrieb (Attribut ``hvac_action``). Er
            wird nie verlangt (D2) und **verfeinert**, wo er da ist: Nennt er
            eine **Richtung** (heating/cooling/drying/fan) oder ``off``,
            schlägt er den eingestellten Modus. Nennt er **keine** — heute
            ``idle`` —, fällt die Auswertung auf den eingestellten Modus
            zurück, statt ihn zu verwerfen (**#399**). Ein `hvac_action`, das
            eedc gar nicht kennt, wird ignoriert.

    Returns:
        Einen Wert aus {@link BETRIEBSMODUS_KANON}, oder ``None`` für
        „kein verwertbarer Zustand" (Entity fehlt, `unknown`, `unavailable`).

        ⚠ ``None`` und ``"unbestimmt"`` sind **nicht** dasselbe und dürfen nie
        ineinander übersetzt werden: ``None`` heißt „nicht hingesehen",
        ``unbestimmt`` heißt „hingesehen, Seite nicht zuordenbar". Genau diese
        zwei Fälle muss der Anwender später unterscheiden können.
    """
    # Nennt der Ist-Betrieb eine RICHTUNG, gewinnt er — er sagt, was das Gerät
    # wirklich tut (D2).
    ohne_richtung = False
    if hvac_action is not None:
        aktion = str(hvac_action).strip().lower()
        if aktion in _AKTION_ZU_KANON:
            return _AKTION_ZU_KANON[aktion]
        # #399: `idle` nennt keine Richtung. Es darf den eingestellten Modus
        # nicht verwerfen — es fällt auf ihn zurück. Steht dort eine Richtung
        # (`cool` bei Klausnn), gehört die Stunde dorthin, auch wenn der
        # Verdichter gerade pausiert.
        ohne_richtung = aktion in _AKTION_OHNE_RICHTUNG

    if zustand is None:
        # ⚠ **Der Unterschied, der D6 trägt.** Ohne `idle` heißt „kein
        # Zustand" weiterhin `None` = *„nicht hingesehen"*. Mit `idle` haben
        # wir sehr wohl hingesehen — das Gerät hat sich gemeldet, es lief und
        # wartete (kingcap1s 10 W Standby). Das ist `unbestimmt`, nicht `None`;
        # sonst verlöre die Abdeckungs-Kennzahl genau die Stunden, die sie
        # zählen soll.
        return UNBESTIMMT if ohne_richtung else None
    roh = str(zustand).strip().lower()
    if roh in _KEIN_ZUSTAND:
        return UNBESTIMMT if ohne_richtung else None

    # Unbekannter, aber vorhandener Wert: das Gerät hat etwas gemeldet, eedc
    # kann es nur nicht einordnen. Das ist `unbestimmt`, nicht `None` — sonst
    # sähe die Abdeckungs-Kennzahl aus wie ein Sensor-Ausfall.
    return _ZUSTAND_ZU_KANON.get(roh, UNBESTIMMT)


def betriebsmodus_klartext(zustand: Optional[str]) -> Optional[str]:
    """Roher HA-State → deutscher Klartext für die Zuordnungs-Fläche (F-53).

    Args:
        zustand: der State der zugeordneten Entität, z. B. ``"cool"``.

    Returns:
        Den Klartext aus {@link BETRIEBSMODUS_LABEL}, oder ``None``, wenn es
        keinen verwertbaren Zustand gibt (`unknown`, `unavailable`, leer).

    ⚑ **Warum der Klartext und nicht der Rohwert allein:** Die Fläche soll
    nicht nur zeigen, dass *etwas* ankommt, sondern ob eedc es **versteht**.
    Eine unbekannte Herstellerschreibweise erscheint hier als „Unbestimmt" —
    und genau die landet später in der Zeile „nicht aufgeteilt", statt einer
    Seite zugeschlagen zu werden. Wer nur ``cool`` läse, sähe den Unterschied
    zwischen „verstanden" und „durchgewinkt" nicht.

    ⚠ Bewusst **ohne** ``hvac_action``: die Fläche zeigt, was an *diesem* Feld
    zugeordnet ist. Die Verfeinerung durch den Ist-Betrieb passiert im
    Aggregator, nicht in der Anzeige.
    """
    kanon = normalisiere_betriebsmodus(zustand)
    if kanon is None:
        return None
    # ⚑ **Direkt indiziert, kein `.get(..., fallback)`.** Der erste Entwurf
    # hatte einen — und ein Sprengsatz darauf blieb STUMM: `normalisiere_…`
    # liefert ausschließlich Kanon-Werte, und die stehen vollzählig in
    # `BETRIEBSMODUS_LABEL`. Der Fallback war damit unerreichbarer Code, der
    # aussah wie eine Absicherung. Die echte Gefahr ist eine **siebte
    # Betriebsart ohne Label**, und die fängt kein Fallback, sondern der
    # Wächter `test_jeder_kanon_wert_hat_ein_label` — hier knallt sie dann
    # sichtbar statt still ein falsches Wort anzuzeigen.
    return BETRIEBSMODUS_LABEL[kanon]


#: Der Feld-Key der Modus-Zuordnung — mit Innengeräte-Liste heißt er
#: `betriebsmodus-3`, deshalb wird überall über `basis_feld_key` verglichen.
MODUS_FELD_KEY: Final[str] = "betriebsmodus"


def modus_quelle(live: Optional[dict]) -> Optional[str]:
    """Die **eine** Modus-Quelle eines Geräts — oder ``None``.

    Args:
        live: der ``live``-Block **einer** Investition aus dem
            ``sensor_mapping`` (``{feld_key: entity_id}``).

    Returns:
        Die Entity-ID der Modus-Quelle, oder ``None``, wenn es **keine** oder
        **mehr als eine verschiedene** gibt.

    ⭐ **Warum es diese Funktion gibt und warum sie hier steht** (N-340). Der
    Zähler dieses Geräts ist **einer** — bei externer Messung eine Steckdose
    am Außengerät. Die Aufteilung schreibt ``modus_strom_*_kwh`` je
    **Investition**. Zwischen N Signalen und einer Zahl muss also eine Regel
    stehen; bis zum 27.08.2026 stand dort **keine**, sondern die
    Einfüge-Reihenfolge des Mappings (``ergebnis[inv_id] = modus``, an
    **beiden** Lesestellen — die letzte Entität gewann, still).

    ⚠ **Mehrere Zuordnungen auf DIESELBE Entität sind eine Quelle**, und das
    ist der Normalfall: Der Modus gehört dem Außengerät, nicht dem Innengerät
    (Konzept D3 — in einer 2-Rohr-Anlage tut ein Innengerät auf „Heizen"
    zwischen kühlenden nichts). Wer alle drei Innengeräte auf dieselbe
    `climate`-Entität legt, bekommt seine Aufteilung wie bisher.

    ⛔ **Verschiedene Entitäten ergeben KEINEN Anlagen-Modus, und eedc rät
    keinen** (ADR-002/P4). Die Zusammenführung bräuchte ein physikalisches
    Modell der fremden Maschine — ob ein lüftendes Innengerät neben einem
    heizenden vorkommt, ob das Außengerät beim Enteisen etwas meldet, ob
    `dry` kühlseitig läuft. Das weiß der Anlagenbesitzer, nicht eedc. Er baut
    sich die Zusammenführung als Template-Sensor in Home Assistant und ordnet
    **dessen** Ergebnis zu; das Handbuch führt die Vorlage. **Der
    Daten-Checker nennt den Fall**, damit die Lücke nicht schweigt.
    """
    if not isinstance(live, dict):
        return None
    # Lokaler Import: `field_definitions` importiert seinerseits aus dieser
    # Datei (der Kanon ist die Quelle der Feldnamen) — ein Top-Level-Import
    # wäre ein Zyklus. Dasselbe Muster wie bei `_KANON_RANG`.
    from backend.core.field_definitions import basis_feld_key

    quellen = {
        str(entity)
        for feld, entity in live.items()
        if entity and basis_feld_key(str(feld)) == MODUS_FELD_KEY
    }
    return quellen.pop() if len(quellen) == 1 else None
