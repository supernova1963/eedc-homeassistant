"""SOLL Wärme/Klima — **nachgestellte Anlagen**: kommt die Kennzahl bis zur Route an?

## Warum diese Datei neben den sechs SOLL-Wächtern steht

Die Wächter `test_soll_waerme_klima_achse*` und `…_w4/_w5/_e4` prüfen **Regeln
und Formeln**: Sie rufen `arbeitszahl(...)` bzw. bauen `WpFakten(...)` und
fragen, ob der Layer richtig rechnet. Gemessen am 2026-08-26: keine der drei
zuletzt gebauten Dateien (E4 · W-4 · W-5) enthält auch nur einen Treffer für
`Anlage(`, `InvestitionMonatsdaten(`, `client.get` oder `AsyncSession`.

**Hier steht die andere Frage:** Kommt die Zahl bei einer *echten Datenlage* auf
der *echten Fläche* an — vom Feld in `verbrauch_daten` über die Monats-Fakten
bis in die Antwort der Route?

⭐ **Warum das auf dieser Fläche mehr wiegt als anderswo.** Bei jeder anderen
Größe ist der Maintainer die letzte Instanz: Er sieht seine Anlage und merkt,
wenn eine Zahl nicht stimmt. Hier nicht — er besitzt weder Wärmepumpe noch
Klimaanlage noch Heizstab. **Diese nachgestellten Anlagen sind der Ersatz für
den fehlenden Gegenprüfer**, nicht eine zusätzliche Bequemlichkeit.

## Die belegte Lücke, die diese Datei schließt

| Größe | Layer geprüft | Route geprüft (vorher) |
| --- | --- | --- |
| **E4** Lüften/Entfeuchten in der Aufteilung | ✓ | ✓ `test_263_innengeraete_varianten` |
| **E4** dieselben fallen aus dem **Nenner** | ✓ | ✗ |
| **W-4** `jaz_heizen` / `jaz_warmwasser` | ✓ | ✗ — **kein einziger Backend-Treffer** |
| **W-5** `jaz_kuehlen` | ✓ | ✗ |

## Die vier Anlagen — jede bildet eine reale Bauform ab

Sie sind **nicht erfunden**: A1–A3 stammen aus dem Forum-Thread 89667 vom
25./26.08.2026, A4 ist der Fall, für den W-5 überhaupt gebaut wurde.

| | Bauform | Was sie beweisen muss |
| --- | --- | --- |
| **A1** | Luft-Wasser-WP **+** Luft-Luft-Klimaanlage; nur die WP meldet Wärme | Die anlagenweite Arbeitszahl **fällt weg** und wird durch den Grund ersetzt — das **einzelne** Gerät behält seine Zahl |
| **A2** | drei getrennte Zähler (Heizung · Warmwasser · Kühlen), Strom je Funktion | `jaz_heizen` und `jaz_warmwasser` erscheinen **getrennt**; der Kühlstrom steht in **keinem** der Nenner |
| **A3** | eine WP, kühlt ohne getrennte Messung | Keine Aufteilung, keine Kühl-Kennzahl — und die Gesamtzahl bleibt **unverfälscht** |
| **A4** | WP mit **Kältemengenzähler** | `jaz_kuehlen` erscheint; ohne den Zähler steht dort ein **Grund** statt einer Zahl |

⛔ **Die Erwartungen sind von Hand gerechnet und stehen als Formel im Kommentar,
nicht als eingefrorener Messwert.** Eine Probe, die den heutigen Ausgabewert
festschreibt, bestätigt jeden Fehler, den er schon enthält — genau der Fehler,
der am 26.08. an der ersten W-5-Probe gefunden wurde (sie baute `WpFakten`
direkt und blieb bei der Gegenprobe grün).

## Was diese Datei gefunden hat

Beim ersten Lauf waren zwei Proben rot — und beide Male hatte die **Probe** recht.
Die drei Befunde stehen im Flächen-Register `~/.claude/plans/ist-waerme-klima.md` §6
als **W-15** (Hub rechnet selbst · 2,31 gegen 3,00 · weder Grund noch Heizstab-Hinweis),
**W-16** (Kühlstrom fehlt im WP-Verbrauch) und **W-16b** (derselbe Strom zweimal
abgezogen). Die betroffenen Proben tragen sie als OFFEN und melden sich beim Bau.

Schwesterdateien: `test_soll_waerme_klima_w4_arbeitszahl_je_funktion.py` ·
`test_soll_waerme_klima_w5_arbeitszahl_kuehlen.py` ·
`test_soll_waerme_klima_e4_lueften_entfeuchten.py` ·
`test_263_innengeraete_varianten.py` (dasselbe Matrix-Muster, andere Achse).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_GERAETE_OHNE_WAERME,
)
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.investition import InvestitionMonatsdaten  # noqa: F401
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)

JAHR, MONAT = 2025, 7


# ─── Fixture-Bau ────────────────────────────────────────────────────────────

async def _anlage(db, name: str) -> Anlage:
    a = Anlage(anlagenname=name, leistung_kwp=10.0,
               installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    return a


async def _geraet(db, anlage, bezeichnung: str, parameter: dict, daten: dict):
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung=bezeichnung,
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=JAHR, monat=MONAT, verbrauch_daten=daten,
    ))
    return inv


async def _hub(db, anlage_id):
    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard
    return await get_waermepumpe_dashboard(anlage_id, strompreis_cent=30.0, db=db)


async def _monat(db, anlage_id):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    return await get_aktueller_monat(anlage_id, jahr=JAHR, monat=MONAT, db=db)


# ═══ A1 — dietmar1968: WP meldet Wärme, Klimaanlage nicht ═══════════════════
#
# Forum 89667 #201: „Ist es nicht sinnvoller die Luft Wasser Wärmepumpe von der
# Luft Luft Klimaanlage komplett zu trennen und jenes nicht zu vermischen."
#
# Zahlen: WP 3000 kWh Wärme auf 800 kWh Strom · Klimaanlage 200 kWh Strom, keine
# Wärme. Anlagenweit stünden 3000 ÷ 1000 = 3,0 — eine Zahl, die es nicht geben
# darf, weil im Nenner der Strom von zwei Geräten und im Zähler die Wärme von
# einem steht.

async def _baue_a1(db):
    a = await _anlage(db, "A1 dietmar")
    wp = await _geraet(db, a, "Wärmepumpe",
                       {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"},
                       {"stromverbrauch_kwh": 800.0, "heizenergie_kwh": 3000.0})
    await _geraet(db, a, "Klimaanlage",
                  {"wp_art": "luft_luft", "effizienz_modus": "gesamt_jaz"},
                  {"stromverbrauch_kwh": 200.0})
    await db.commit()
    return a, wp


async def test_a1_anlagenweite_arbeitszahl_faellt_weg_mit_grund(db):
    """Die vermischte Zahl darf NICHT erscheinen — der Grund tritt an ihre Stelle."""
    a, _wp = await _baue_a1(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz is None, (
        "3000 ÷ 1000 = 3,0 wurde gebildet, obwohl die Klimaanlage keine Wärme "
        "meldet — genau die Vermischung, die dietmar1968 gemeldet hat")
    assert antwort.wp_jaz_grund == GRUND_GERAETE_OHNE_WAERME


async def test_a1_die_mengen_bleiben_unveraendert(db):
    """Gesperrt wird die Kennzahl, nicht die Messung (SOLL §3.2b)."""
    a, _wp = await _baue_a1(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_strom_kwh == pytest.approx(1000.0), "800 + 200"
    assert antwort.wp_waerme_kwh == pytest.approx(3000.0)


async def test_a1_das_einzelne_geraet_behaelt_seine_zahl(db):
    """⭐ Die anlagenweite Sperre ist am EINZELNEN Gerät gegenstandslos.

    Diese Probe hält die Zusage fest, die dem Melder gegeben wird: Unter
    *Komponenten → Wärmepumpe* steht jedes Gerät einzeln — und dort ist die
    Wärmepumpe für sich sauber abgegrenzt (3000 ÷ 800 = 3,75).
    """
    a, _wp = await _baue_a1(db)
    blocks = await _hub(db, a.id)

    wp_block = next(b for b in blocks if b.investition.bezeichnung == "Wärmepumpe")
    # ⚠ Der Schlüssel heißt im Hub `durchschnitt_cop` — der alte Name, den W-4
    # bei den Funktions-Kennzahlen gerade abgelöst hat (`cop_*` → `jaz_*`).
    # Die Gesamt-Kennzahl trägt ihn weiter; s. W-15.
    assert wp_block.zusammenfassung.get("durchschnitt_cop") == pytest.approx(3.75), (
        "3000 ÷ 800 — die Klimaanlage gehört nicht in diese Rechnung")


# ═══ A2 — MartyBr: drei getrennte Zähler ═══════════════════════════════════
#
# Forum 89667 #200: „Ich habe getrennte Zähler für Heizung, Warmwassererwärmung
# … und seit dem Sommer auch für den Kühlbetrieb."
#
# Zahlen: Heizen 3000 kWh Wärme auf 750 kWh Strom (JAZ 4,0) · Warmwasser
# 600 kWh auf 200 kWh (JAZ 3,0) · Kühlen 100 kWh Strom ohne Kältemenge.
# Gesamtstrom 1050 kWh. Die Gesamt-Arbeitszahl rechnet 3600 ÷ (1050 − 100).

_A2_DATEN = {
    "stromverbrauch_kwh": 1050.0,
    "heizenergie_kwh": 3000.0,
    "strom_heizen_kwh": 750.0,
    "warmwasser_kwh": 600.0,
    "strom_warmwasser_kwh": 200.0,
    "betriebsart_strom_heizen_kwh": 950.0,
    "betriebsart_strom_kuehlen_kwh": 100.0,
}


async def _baue_a2(db):
    a = await _anlage(db, "A2 MartyBr")
    wp = await _geraet(db, a, "Wärmepumpe",
                       {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz",
                        "getrennte_strommessung": True},
                       dict(_A2_DATEN))
    await db.commit()
    return a, wp


async def test_a2_jaz_je_funktion_erscheint_im_hub(db):
    """W-4: zwei getrennte Zahlen, nicht eine gemittelte."""
    a, _wp = await _baue_a2(db)
    z = (await _hub(db, a.id))[0].zusammenfassung

    assert z.get("jaz_heizen") == pytest.approx(4.0), "3000 ÷ 750"
    assert z.get("jaz_warmwasser") == pytest.approx(3.0), "600 ÷ 200"


async def test_a2_jaz_je_funktion_erscheint_auch_im_cockpit(db):
    """W-4: dieselbe Anlage darf auf zwei Flächen nicht zwei Aussagen tragen.

    Bis zum 26.08. gab es die getrennten Zahlen **nur** im Hub — im Cockpit
    fehlten sie ganz, obwohl dieselben Daten dort vorliegen.
    """
    a, _wp = await _baue_a2(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz_heizen == pytest.approx(4.0)
    assert antwort.wp_jaz_warmwasser == pytest.approx(3.0)


async def test_a2_kuehlstrom_steht_in_keinem_nenner(db):
    """✅ **W-16b gebaut (26.08.): der Kühlstrom wird genau EINMAL abgezogen.**

    **3600 ÷ 950 = 3,789.** Der Nenner ist der Strom für Heizen und Warmwasser;
    der Kühlstrom (100 kWh) gehört nicht hinein — aber auch nicht zweimal weg.

    **Vorher: 3600 ÷ 850 = 4,235** — die Anlage sah **12 % besser** aus, als
    sie ist.

    **Ursache, am Code gemessen:** Bei ``getrennte_strommessung=True`` bildet
    ``get_wp_strom_kwh`` (``field_definitions.py:2467``) den Gesamtstrom aus
    ``strom_heizen_kwh + strom_warmwasser_kwh`` = 950 und **ignoriert**
    ``stromverbrauch_kwh`` bewusst (#183). Der Kühlstrom ist darin also nie
    enthalten — ``arbeitszahl(...)`` zieht ihn über
    ``strom_funktionsfremd_kwh`` trotzdem ab.

    ⭐ **Genau davor warnt der Docstring von ``arbeitszahl_je_funktion``**
    („Ihn hier abzuziehen zöge dieselbe Menge zweimal ab") — für die
    Funktions-Kennzahlen wurde die Falle gesehen, für die Gesamtzahl nicht.

    ⚠ **Der Abzug ist nicht generell falsch:** Ohne getrennte Strommessung
    kommt der Nenner aus ``stromverbrauch_kwh`` und enthält den Kühlstrom
    sehr wohl — dort ist der Abzug richtig (A4 belegt das). Die Bedingung
    fehlt, nicht der Abzug.

    ⭐ **Diese Probe hat den Befund gefunden.** Sie stand zuerst auf der
    Soll-Zeile, wurde rot — und beim Nachmessen hatte sie recht, nicht der
    Code. Der Gegenbeweis steht in `test_a4_der_kuehlstrom_bleibt_aus_der_heiz_kennzahl`:
    **ohne** getrennte Strommessung ist derselbe Abzug richtig.
    """
    a, _wp = await _baue_a2(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz == pytest.approx(3600.0 / 950.0, rel=1e-3)
    assert antwort.wp_jaz != pytest.approx(3600.0 / 850.0, rel=1e-3), (
        "der doppelte Abzug ist zurück")


async def test_a2_der_wp_stromverbrauch_verliert_den_kuehlstrom(db):
    """✅ **W-16 gebaut (26.08.): der Kühlstrom zählt im WP-Verbrauch mit.**

    Dieselbe Ursache wie W-16b, aber eine Ebene früher und mit größerer Reichweite:
    ``get_wp_strom_kwh`` summiert bei getrennter Strommessung nur Heizen und
    Warmwasser. Wer **zusätzlich** einen Kühlzähler führt — die Bauform, die
    R1/W-2 gerade erst an jeder Wärmepumpe möglich gemacht hat —, dessen
    Kühlstrom taucht im WP-Stromverbrauch **gar nicht** auf.

    **1050 kWh** = 750 (Heizen) + 200 (Warmwasser) + 100 (Kühlen). Vorher
    standen dort 950 kWh — und das trug in alles weiter, was auf dem
    WP-Stromverbrauch aufsetzt: Kosten, CO₂, Anteil an der Verbrauchsseite.

    ⚠ **Addiert wird nur ein GEMESSENER Betriebsart-Split.** Ein abgeleiteter
    verteilt den vorhandenen Gesamtstrom und ist in den 950 bereits enthalten;
    ihn zu addieren wäre dieselbe Doppelzählung, nur andersherum.
    """
    a, _wp = await _baue_a2(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_strom_kwh == pytest.approx(1050.0)


async def test_a2_der_hub_traegt_grund_und_heizstab_hinweis(db):
    """✅ **W-15/W-6: Der Hub liefert jetzt auch Grund und Hinweis.**

    ⭐ **Diese Probe deckt eine Melder-Zusage.** Die Antwort an dietmar1968
    sagt wörtlich: *„Schaust du unter Komponenten → Wärmepumpe auf das einzelne
    Gerät, gibt es dort eine Arbeitszahl — und die trägt dann genau diesen
    Heizstab-Satz."* Bis zum 26.08. gab es `wp_jaz_hinweis` **nur** im Cockpit;
    im Hub kein einziges Vorkommen. Die Zusage war ungedeckt.

    Geprüft wird die **Anwesenheit der Schlüssel**, nicht ein Textinhalt — der
    Wortlaut gehört dem Layer (`HEIZSTAB_HINWEIS`), und ihn hier zu wiederholen
    wäre eine zweite Wahrheit.
    """
    a, _wp = await _baue_a2(db)
    z = (await _hub(db, a.id))[0].zusammenfassung

    assert "durchschnitt_cop_grund" in z
    assert "durchschnitt_cop_hinweis" in z


# ═══ A3 — rapahl: kühlt, misst es aber nicht getrennt ══════════════════════
#
# Forum 89667 #202: „Kühlen über die Wärmepumpe erfasse ich nicht getrennt. …
# Ich weiß aber gar nicht, was ich mit diesen Informationen sollte."
#
# Die Zusage an ihn lautet: Wer nicht getrennt misst, verliert nichts — der
# Kühlstrom steckt im Gesamtverbrauch. Diese Probe hält fest, dass eedc dann
# auch keine Aufteilung und keine Kühl-Kennzahl erfindet.

async def _baue_a3(db):
    a = await _anlage(db, "A3 rapahl")
    wp = await _geraet(db, a, "Wärmepumpe",
                       {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"},
                       {"stromverbrauch_kwh": 1000.0, "heizenergie_kwh": 3500.0})
    await db.commit()
    return a, wp


async def test_a3_ohne_getrennte_messung_keine_erfundene_aufteilung(db):
    a, _wp = await _baue_a3(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_modus_strom_kuehlen_kwh is None
    assert antwort.wp_jaz_kuehlen is None, (
        "eine Kühl-Kennzahl ohne jede Kühl-Messung wäre erfunden")


async def test_a3_die_gesamtzahl_bleibt_unverfaelscht(db):
    """3500 ÷ 1000 = 3,5 — nichts wird abgezogen, was nicht gemessen ist."""
    a, _wp = await _baue_a3(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz == pytest.approx(3.5)


# ═══ A4 — Kältemengenzähler: der Fall, für den W-5 gebaut wurde ════════════
#
# Zahlen: 900 kWh abgeführte Kälte auf 300 kWh Kühlstrom ⇒ Arbeitszahl 3,0.

_A4_DATEN = {
    "stromverbrauch_kwh": 1300.0,
    "heizenergie_kwh": 3000.0,
    "betriebsart_strom_heizen_kwh": 1000.0,
    "betriebsart_strom_kuehlen_kwh": 300.0,
    "betriebsart_nutzenergie_kuehlen_kwh": 900.0,
}


async def _baue_a4(db, mit_kaeltemenge: bool):
    daten = dict(_A4_DATEN)
    if not mit_kaeltemenge:
        daten.pop("betriebsart_nutzenergie_kuehlen_kwh")
    a = await _anlage(db, "A4 Kaeltemenge")
    wp = await _geraet(db, a, "Wärmepumpe",
                       {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"},
                       daten)
    await db.commit()
    return a, wp


async def test_a4_arbeitszahl_kuehlen_erscheint_im_hub(db):
    """W-5: 900 ÷ 300 = 3,0 — der Quotient zweier Zähler, kein Schätzwert."""
    a, _wp = await _baue_a4(db, mit_kaeltemenge=True)
    z = (await _hub(db, a.id))[0].zusammenfassung

    assert z.get("jaz_kuehlen") == pytest.approx(3.0)


async def test_a4_arbeitszahl_kuehlen_erscheint_auch_im_cockpit(db):
    a, _wp = await _baue_a4(db, mit_kaeltemenge=True)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz_kuehlen == pytest.approx(3.0)


async def test_a4_ohne_kaeltemengenzaehler_steht_dort_ein_grund(db):
    """⭐ Kein geschätzter Wert und keine 0 — beides wäre eine Falschaussage.

    Eine 0 hieße „Arbeitszahl null" statt „unbekannt" (ADR-002/P4), und ein
    aus einem angenommenen Wirkungsgrad gerechneter Wert gäbe genau den
    Faktor zurück, mit dem gerechnet wurde.
    """
    a, _wp = await _baue_a4(db, mit_kaeltemenge=False)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz_kuehlen is None
    assert antwort.wp_jaz_kuehlen_grund, (
        "ohne Zahl muss der Grund dastehen, sonst ist die Lücke stumm")


async def test_a4_hub_und_cockpit_nennen_dieselbe_arbeitszahl(db):
    """✅ **W-15 gebaut (26.08.): beide Flächen nennen dieselbe Zahl.**

    **3,00 auf beiden** (3000 ÷ 1000). Vorher sagte der Komponenten-Hub
    **2,31** (3000 ÷ 1300, Kühlstrom im Nenner) — dieselbe Anlage, derselbe
    Monat, zwei Aussagen.

    **Ursache:** ``dashboards.py:893`` rechnet
    ``durchschnitt_cop = gesamt_waerme / gesamt_strom`` **selbst**, statt
    ``arbeitszahl(...)`` zu rufen. Damit fehlen dort **alle** R2-Sperren außer
    der abgeleiteten Wärme: kein Abzug des funktionsfremden Stroms, keine
    Anwender-Angabe „Fremdanteil auf den Zählern", kein Zeitraum-Versatz.

    ⭐ **Das ist wortgleich die Mängelliste von W-4** — nur an der
    Gesamt-Kennzahl statt an den Funktions-Kennzahlen. W-4 hat ``cop_heizen``
    und ``cop_warmwasser`` auf den Layer gehoben und ``durchschnitt_cop``
    daneben stehen lassen. Der Widerspruch ist dadurch **sichtbarer** geworden:
    Im selben Block steht jetzt „JAZ Kühlen 3,0" (Layer, richtig) neben
    „JAZ 2,31" (selbst gerechnet, falsch).

    ⭐ **Die Probe prüft die Gleichheit, nicht zwei Einzelwerte.** Eine
    Kennzahl, die auf zwei Flächen aus derselben Quelle kommt, darf nie wieder
    auseinanderlaufen — auch nicht auf einen anderen, ebenfalls plausiblen Wert.
    """
    a, _wp = await _baue_a4(db, mit_kaeltemenge=True)
    z = (await _hub(db, a.id))[0].zusammenfassung
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz == pytest.approx(3.0), "3000 ÷ 1000"
    assert z.get("durchschnitt_cop") == pytest.approx(antwort.wp_jaz), (
        "Hub und Cockpit nennen wieder verschiedene Arbeitszahlen")


async def test_a4_der_kuehlstrom_bleibt_aus_der_heiz_kennzahl(db):
    """Auch MIT Kältemengenzähler: 3000 ÷ (1300 − 300), nicht ÷ 1300.

    Die Kälte ist eine eigene Nutzenergie mit eigener Kennzahl — sie in den
    Nenner der Wärme-Kennzahl zu ziehen wäre der Kategorienfehler, nur
    andersherum.
    """
    a, _wp = await _baue_a4(db, mit_kaeltemenge=True)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz == pytest.approx(3.0), "3000 ÷ 1000"
