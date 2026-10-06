"""Monats-Fakten — die EINE Aufbereitung der Monatszeile vor jeder Read-Site.

**Warum es diesen Service gibt.** Die Drift-Inventur vom 2026-07-31 (23 Sichten
× 18 kanonische Größen, 72 Kandidaten-Zellen) fand **keinen einzigen Rechenfehler**
im Berechnungs-Layer. Sie fand sechsmal dieselbe Struktur: *jede Sicht faltet die
Rohdaten selbst zu Monatswerten*, und dabei fällt jedes Mal etwas anderes weg —
mal V2H, mal der Erzeuger hinter dem Zähler, mal der Aggregat-Fallback, mal der
Monatstarif, mal der Dienstwagen-Filter. Der härteste Beleg (F-5), an einer Anlage
gemessen, die nur das Anlagen-Aggregat pflegt:

===========================  ==========  ==============
Sicht                        PV          Netto-Ertrag
===========================  ==========  ==============
Cockpit · HA-Export          1.000 kWh   212,00 €
Aussichten · Jahresbericht    0 kWh       32,00 €
===========================  ==========  ==============

85 % Abweichung — weil zwei Sichten ``lade_pv_je_monat`` nutzen und fünf roh
``verbrauch_daten["pv_erzeugung_kwh"]`` summieren.

**Das hier ist keine Erfindung, sondern eine Verallgemeinerung.**
``services/pv_monatswerte.py`` ist bereits genau diese Schicht — für genau EINE
Größe, mit derselben Begründung im Docstring („die Eingabe musste bisher jede
Read-Site selbst zusammensuchen … zwei davon sind an der Formel vorbeigelaufen").
Seit es ihn gibt, ist in der PV-Auflösung keine neue Drift entstanden; die
verbleibenden Befunde sind genau die Sichten, die ihn *nicht* benutzen. Dieses
Modul zieht dieselbe Bauform von einer Größe auf die ganze Monatszeile
(``docs/KONZEPT-MONATS-FAKTEN.md``, ADR-002/**P10**).

**Schichtung (ADR-001).** Die Schicht ist **Eingabe-Aufbereitung, keine Formel**:
sie enthält keine einzige Aggregat-Formel, sondern lädt, filtert und *ruft* die
SoT-Helfer aus ``core/berechnungen/`` (``imd_typ_beitrag``, ``bkw_finanz_beitrag``,
``erzeugung_hinter_zaehler_kwh``, ``berechne_verbrauchs_kennzahlen``) sowie die
bestehenden Service-SoT (``lade_pv_je_monat``, ``get_emob_heimladung_canonical``,
``lade_tarife_fuer_anlage``, ``get_neg_preis_einspeisung_je_monat``). DB-I/O gehört
laut ADR-001 in ``services/`` — deshalb liegt sie hier und nicht in ``core/``.

**Alle Zeitfilter (``aktiv`` · Anschaffung · Stilllegung) und der
Dienstwagen-Filter werden GENAU HIER angewandt, einmal** (#153/#155/#236/#308,
[[feedback_anschaffungsdatum_grenze]], [[feedback_dienstwagen_alle_checks]]).

**Was die Schicht bewusst NICHT tut** (``KONZEPT-MONATS-FAKTEN.md`` §4):
Live, Prognose und **jeden Schreibpfad** — sie ist reines Lesen. Sie rechnet auch
keine Euro-Beträge aus, für die es einen Formel-Helfer gibt: der Aufrufer bekommt
die Mengen *und* den Monatstarif und ruft den Helfer selbst.

**Eine Grenze ist seit N-121 (2026-08-03) verschoben, und zwar bewusst.** Bis
dahin stand hier „keine Tages-/Stundenebene — der Tag hat mit
``bilanz_aus_stundenrows`` eine eigene, korrekte Quelle". Das stimmt weiterhin
für die *Formel*: gefaltet wird nach wie vor mit genau diesem Layer-Helfer, hier
entsteht keine zweite Faltung. Was sich geändert hat, ist die **Grundgesamtheit**:
mit ``inkl_nur_tageswerte=True`` kennt die Schicht auch Monate, deren einzige Spur
die Tagesebene ist, und füllt damit die Lücken der übrigen. Auslöser war, dass es
**keinen automatischen Monatsabschluss** gibt — der laufende Monat hat nie eine
``Monatsdaten``-Zeile und fehlte im Jahres-Verlauf deshalb immer. Der Default
bleibt **aus**; Datensatz-Listen sehen unverändert nur, was wirklich in der DB
steht. Details, Messwerte und die Grenzen der Quelle:
``energie_profil/monats_aus_tagen.py``.

Seit 19.09.2026 ein Paket (Vorlage 10 des Refactorings grosser Dateien, reiner Umzug): ``fakten`` (die Feldgruppen) ·
``fakten_wp`` (Waermepumpe) · ``roh`` (der Rohmonat und die Lader) · ``tarif`` (der Monatstarif) · ``bau`` (Rohmonat →
Fakt) · ``laden`` (der Orchestrator ``lade_monats_fakten``) · ``ableitungen`` (was Aufrufer aus einem Fakt ableiten).
Diese Fassade exportiert die bisherigen Namen weiter; der P10-Waechter nimmt das ganze Paket als Schicht aus.
"""

from backend.services.monats_fakten.fakten_wp import (  # noqa: F401 — Re-Export
    WpFakten,
)
from backend.services.monats_fakten.fakten import (  # noqa: F401 — Re-Export
    MonatsSchluessel,
    TAGESWERT_ZAEHLER,
    TAGESWERT_PV,
    TAGESWERT_BKW,
    TAGESWERT_SPEICHER,
    TAGESWERT_EMOB_ANTEIL,
    TAGESWERT_EMOB,
    TAGESWERT_SONSTIGES,
    TAGESWERT_WP,
    ZaehlerFakten,
    ErzeugungFakten,
    BkwFakten,
    SpeicherFakten,
    EmobFakten,
    SonstigesGeraetFakten,
    SonstigesFakten,
    TarifFakten,
    EegFakten,
    MetaFakten,
    MonatsFakt,
)
from backend.services.monats_fakten.roh import (  # noqa: F401 — Re-Export
    _RohMonat,
)
from backend.services.monats_fakten.laden import (  # noqa: F401 — Re-Export
    lade_monats_fakten,
)
from backend.services.monats_fakten.bau import (  # noqa: F401 — Re-Export
    sonstiges_aus_zeilen,
    wp_aus_zeilen,
    wp_kanal_zeile,
)
from backend.services.monats_fakten.ableitungen import (  # noqa: F401 — Re-Export
    ist_pv_ladeanteil_prozent,
    finanz_zeile_eingabe,
    kennzahlen_aus_fakten,
    pv_erzeugungs_monate,
    pv_unvollstaendig_monate,
    pv_unvollstaendig_hinweis,
)

__all__ = [
    "WpFakten",
    "MonatsSchluessel",
    "TAGESWERT_ZAEHLER",
    "TAGESWERT_PV",
    "TAGESWERT_BKW",
    "TAGESWERT_SPEICHER",
    "TAGESWERT_EMOB_ANTEIL",
    "TAGESWERT_EMOB",
    "TAGESWERT_SONSTIGES",
    "TAGESWERT_WP",
    "ZaehlerFakten",
    "ErzeugungFakten",
    "BkwFakten",
    "SpeicherFakten",
    "EmobFakten",
    "SonstigesGeraetFakten",
    "SonstigesFakten",
    "TarifFakten",
    "EegFakten",
    "MetaFakten",
    "MonatsFakt",
    "_RohMonat",
    "lade_monats_fakten",
    "sonstiges_aus_zeilen",
    "wp_aus_zeilen",
    "wp_kanal_zeile",
    "ist_pv_ladeanteil_prozent",
    "finanz_zeile_eingabe",
    "kennzahlen_aus_fakten",
    "pv_erzeugungs_monate",
    "pv_unvollstaendig_monate",
    "pv_unvollstaendig_hinweis",
]
