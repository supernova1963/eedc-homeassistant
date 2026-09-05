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

from datetime import date, datetime, timedelta

import pytest

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_BAUARTEN_GEMISCHT,
    GRUND_GERAETE_OHNE_WAERME,
)
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.investition import InvestitionMonatsdaten  # noqa: F401
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
# N-337: der Hub liest `sensor_snapshots` (wp_starts_anzahl). Ohne diesen Import
# steht das Modell nicht in `Base.metadata`, wenn diese Datei ALLEIN laeuft — im
# Gesamtlauf bringt es eine andere Datei mit. Wer hier baut, faehrt genau diese
# Datei einzeln und saehe sonst Rot, das ihm nicht gehoert.
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
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
    """Die vermischte Zahl darf NICHT erscheinen — der Grund tritt an ihre Stelle.

    ⚠ **Der erwartete Grund hat am 28.08.2026 gewechselt, die Aussage nicht.**
    Bis dahin stand hier `GRUND_GERAETE_OHNE_WAERME` („nicht alle Geräte melden
    Wärme"). Gesperrt war die Zahl also schon; **falsch war nur die Auskunft.**
    Der allgemeinere Satz beschreibt einen behebbaren Zustand und riet damit zu
    einer Zuordnung, die es hier nicht geben kann — eine Split-Klimaanlage hat
    bauartbedingt keinen Wärmemengenzähler, und das Investitionsformular sagt
    dem Anwender ausdrücklich zu, es genüge der Stromverbrauchs-Sensor.

    ⛔ **Die Probe wurde deshalb umgestellt, nicht zurückgedreht:** Ihr
    Gegenstand — *die vermischte Zahl darf es nicht geben* — gilt unverändert
    und wird eine Zeile höher weiter geprüft. Nur der Grund ist jetzt der
    konkretere, und der konkretere Grund ist die bessere Auskunft (SOLL §3.3/S3).
    """
    a, _wp = await _baue_a1(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz is None, (
        "3000 ÷ 1000 = 3,0 wurde gebildet, obwohl die Klimaanlage keine Wärme "
        "meldet — genau die Vermischung, die dietmar1968 gemeldet hat")
    assert antwort.wp_jaz_grund == GRUND_BAUARTEN_GEMISCHT


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


# ═══ A5 — dietmar1968, seine TATSÄCHLICHE Bauform (W-17 · W-17b) ════════════
#
# Forum 89667 **#210** (26.08.2026), drei Bilder: Zuordnung, Cockpit → Monat,
# Cockpit → Tag. Sein Block trägt „Aggregiert aus: Wärmepumpe · Klimaanlage".
#
# ⛔ **Der Register-Eintrag zu W-17b behauptete zunächst, nur die Klimaanlage
# melde einen Modus.** Das ist widerlegt, und sein eigenes Tagesbild ist der
# Beweis: Dort standen **36 Stunden**. `falte_modus_split_tag` zählt **eine**
# Stunde je Stundenzeile je Gerät, und `betriebsmodus_je_wp` hat je Investition
# genau **einen** Eintrag pro Stunde — ein einzelnes Gerät kann an einem Tag
# also nie über 24 kommen. **36 Stunden beweisen zwei meldende Geräte.** Seine
# Zuordnung zeigt es auch: Die Wärmepumpe trägt `sensor.boiler_compressor_
# activity` als Betriebsmodus, die Bosch-Klimaanlage ihren eigenen.
# ⭐ *Ein Bild ist eine Messung, wenn man es zu Ende liest.*
#
# Zahlen (gerundet nach seinen Bildern, Verhältnisse erhalten):
#   Wärmepumpe    getrennte Strommessung 800 + 400 kWh · Wärme 2400 + 1000 kWh
#                 · Modus 18 h · Split 30 Heizen / 0 Kühlen
#   Klimaanlage   200 kWh Strom, KEINE Wärme · Modus 18 h · Split 0 / 60 Kühlen
#
# Anlagenweit: Strom 1400 kWh — Modus-Abdeckung **18 h, nicht 36**.

_A5_WP = {
    "strom_heizen_kwh": 800.0,
    "strom_warmwasser_kwh": 400.0,
    "heizenergie_kwh": 2400.0,
    "warmwasser_kwh": 1000.0,
    "modus_abdeckung_h": 18.0,
    "modus_strom_heizen_kwh": 30.0,
    "modus_strom_kuehlen_kwh": 0.0,
}
_A5_KLIMA = {
    "stromverbrauch_kwh": 200.0,
    "modus_abdeckung_h": 18.0,
    "modus_strom_heizen_kwh": 0.0,
    "modus_strom_kuehlen_kwh": 60.0,
}


async def _baue_a5(db):
    a = await _anlage(db, "A5 dietmar zwei Melder")
    wp = await _geraet(db, a, "Wärmepumpe",
                       # ⚠ `getrennte_strommessung` ist Pflicht, sonst liest
                       # `get_wp_strom_kwh` das leere `stromverbrauch_kwh` und
                       # das Gerät trägt 0 kWh bei. Erster Entwurf dieser
                       # Fixture hatte es nicht — und die Probe meldete rot,
                       # zu Recht: nicht der Fix war falsch, die nachgestellte
                       # Anlage war es.
                       {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz",
                        "getrennte_strommessung": True},
                       dict(_A5_WP))
    klima = await _geraet(db, a, "Klimaanlage",
                          {"wp_art": "luft_luft", "effizienz_modus": "gesamt_jaz"},
                          dict(_A5_KLIMA))
    await db.commit()
    return a, wp, klima


async def test_a5_ein_tag_hat_keine_36_stunden(db):
    """**W-17** — der Befund, den dietmars Tagesbild sichtbar gemacht hat.

    ⭐ **Eine Menge ist additiv, ein Zeitraum nicht** (SOLL §2.3). Zwei Geräte
    mit je 18 erfassten Stunden ergeben **nicht 36 Stunden Erkenntnis**.

    ⚠ **Warum die Probe auf dem MONAT sitzt und trotzdem W-17 misst:** Der
    Fehler ist derselbe, nur die Obergrenze ist im Monat unauffällig — dort
    standen bei ihm 372 von 624 möglichen Stunden, plausibel genug für Wochen.
    *Eine Kennzahl ohne erkennbare Obergrenze verbirgt ihren eigenen
    Kategorienfehler.* Deshalb prüft die Probe die **Regel** (Maximum statt
    Summe), nicht die Tagesgrenze.
    """
    a, _wp, _klima = await _baue_a5(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_modus_abdeckung_h == pytest.approx(18.0), (
        "die Abdeckung wurde über die Geräte summiert — 18 + 18 = 36")


async def test_a5_die_mengen_werden_weiterhin_addiert(db):
    """⛔ **Die Gegenrichtung, und sie ist der eigentliche Prüfstein.**

    Das Maximum gilt für die **Zeit** und nur für sie. Wer den Fix zu breit
    anwendet, bekommt eine Aufteilung, die die Kilowattstunden des zweiten
    Geräts verliert — ein stiller Datenverlust, der genauso plausibel aussieht
    wie der Fehler, den er ersetzt hat.
    """
    a, _wp, _klima = await _baue_a5(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_modus_strom_heizen_kwh == pytest.approx(30.0)
    assert antwort.wp_modus_strom_kuehlen_kwh == pytest.approx(60.0)
    assert antwort.wp_strom_kwh == pytest.approx(1400.0), "800 + 400 + 200"


async def test_a5_der_balken_nennt_seine_grundmenge(db):
    """**W-17b** — der Balken beschreibt weniger als die Kachel über ihm.

    Bei dietmar standen 30 kWh Balkensumme unter einer Kachel mit 284 kWh, ohne
    dass die Differenz irgendwo benannt war. Hier ist die Grundmenge **90 kWh**
    (30 Heizen + 60 Kühlen, beide Geräte tragen einen Split bei) gegen
    **1400 kWh** Gesamtstrom.

    ⭐ **Die Zahl war nie falsch — sie hat nur nicht gesagt, worüber sie
    spricht.** Der schmalere Bezug ist eine bewusste Entscheidung mit gemessener
    Begründung (`WpFakten.modus_nicht_aufgeteilt_kwh`: an einer Instanz 96,4
    statt 6,4 kWh). Genau deshalb ist der Fix eine **Benennung** und keine
    Umrechnung.
    """
    a, _wp, _klima = await _baue_a5(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_modus_strom_bezug_kwh is not None, (
        "ohne Grundmenge steht der Balken stumm unter einer größeren Kachel")
    assert antwort.wp_modus_strom_bezug_kwh == pytest.approx(1400.0)
    assert antwort.wp_modus_strom_bezug_kwh <= antwort.wp_strom_kwh + 0.01


async def test_a5_die_anlagenweite_arbeitszahl_bleibt_gesperrt(db):
    """R2 gilt unverändert — ein Gerät meldet Wärme, das andere nicht.

    Diese Probe steht hier, damit der W-17-Fix die **bereits gebaute** Sperre
    nicht beschädigt: Bei ihm stand „JAZ 0,64", weil im Nenner der Strom beider
    Geräte und im Zähler die Wärme von einem lag (3400 ÷ 1400 = 2,43 wäre hier
    die verlockende Falschaussage).
    """
    a, _wp, _klima = await _baue_a5(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz is None, "die vermischte Zahl darf es nicht geben"
    # Grund-Wechsel 28.08.2026, wie bei A1 und aus demselben Grund: dieselbe
    # Bauform (Luft-Wasser + Luft-Luft), dieselbe Sperre, konkretere Auskunft.
    # Die Aussage dieser Probe — kein Quotient — steht unveraendert eine Zeile
    # hoeher; nur der Text daneben ist jetzt der, der dem Melder auch hilft.
    assert antwort.wp_jaz_grund == GRUND_BAUARTEN_GEMISCHT


# ═══ A6 — der Tag sagt, WARUM die Wärme fehlt (W-18) ════════════════════════
#
# Forum 89667 **#210**: *„Ich verstehe beim Vorhandensein folgender Sensoren
# jene Anzeige nicht."* — dazu ein Bild, auf dem *Heizwärme* und *Warmwasser*
# als HA-Sensoren zugeordnet sind (9125,59 und 3927,94 kWh), und ein zweites,
# auf dem *Wärme erzeugt* am Tag „—" zeigt.
#
# ⛔ **Der Tooltip dahinter sagte ihm: „Sensor zuordnen".** Er hatte zugeordnet.
# ⭐ *Eine falsche Ursache ist schlimmer als keine* — ohne Hinweis sucht der
# Anwender, mit einem falschen sucht er an der falschen Stelle und meldet
# danach einen Fehler, den es nicht gibt.
#
# Drei Zustände führen zu demselben „—", und der Erhebungspfad kann sie
# auseinanderhalten (`core/tageswert_grund.py`):
#
#   1. kein Zähler zugeordnet
#   2. zugeordnet, aber für DIESEN Tag keine Zählerstände  ← dietmars Lage
#   3. zugeordnet, Zähler im Tagesfenster zurückgesprungen ← war nur eine Logzeile

_A6_DATUM = date(2025, 6, 15)


async def _baue_a6(db, *, zuordnen: bool, snapshots: str):
    """Eine Wärmepumpe am Tag — `snapshots`: ``"voll"`` · ``"keine"`` · ``"reset"``."""
    from backend.models.sensor_snapshot import SensorSnapshot

    anlage = Anlage(anlagenname="A6 dietmar Tag", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Wärmepumpe",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter={"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"},
    )
    db.add(inv)
    await db.flush()

    felder: dict = {}
    t0 = datetime.combine(_A6_DATUM, datetime.min.time())
    for feld, sensor in (("heizenergie_kwh", "sensor.boiler_energy_heating"),
                         ("warmwasser_kwh", "sensor.boiler_dhw_energy")):
        if not zuordnen:
            continue
        felder[feld] = {"strategie": "sensor", "sensor_id": sensor}
        key = f"inv:{inv.id}:{feld}"
        if snapshots == "keine":
            continue
        # „reset": der Zähler springt im Fenster zurück — der Endstand liegt
        # UNTER dem Startstand, genau die Lage, die `_tageswert_aus_raendern`
        # als Tagesreset erkennt und bewusst nicht beziffert.
        ende = 100.0 - 40.0 if snapshots == "reset" else 100.0 + 40.0
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                              zeitpunkt=t0, wert_kwh=100.0, quelle="ha_statistics"))
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                              zeitpunkt=t0 + timedelta(days=1),
                              wert_kwh=ende, quelle="ha_statistics"))

    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": felder}}}
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=_A6_DATUM,
        komponenten_kwh={f"waermepumpe_{inv.id}": 20.0},
    ))
    await db.commit()
    return anlage, inv


async def _tag(db, anlage_id):
    from backend.api.routes.energie_profil.views import get_tag_detail
    return await get_tag_detail(anlage_id, datum=_A6_DATUM, db=db)


async def test_a6_ohne_zuordnung_nennt_den_zaehler_und_den_weg(db):
    """Zustand 1 — der einzige Fall, den der alte Satz beschrieb. Er bleibt richtig."""
    a, _inv = await _baue_a6(db, zuordnen=False, snapshots="keine")
    antwort = await _tag(db, a.id)

    assert antwort.wp_waerme_kwh is None
    assert antwort.wp_waerme_grund, "ohne Zahl muss der Grund dastehen"
    assert "Kein Zähler zugeordnet" in antwort.wp_waerme_grund
    assert "Datenquellen" in antwort.wp_waerme_grund, (
        "der Grund sagt, was IST — und bei diesem einen Zustand auch, was zu TUN ist")


async def test_a6_zugeordnet_aber_leer_fordert_keine_zuordnung_mehr(db):
    """⭐ **Zustand 2 — dietmars Lage, und der Kern von W-18.**

    Der Zähler ist zugeordnet, für diesen Tag gibt es nur keine Zählerstände.
    Genau hier stand vorher *„Sensor zuordnen"* — eine Aufforderung an jemanden,
    der sie längst befolgt hatte.

    ⚠ **Die Probe prüft die ABWESENHEIT der falschen Auskunft mit**, nicht nur
    die Anwesenheit der richtigen. Ein Grund, der beides sagt, ist keine
    Verbesserung.
    """
    a, _inv = await _baue_a6(db, zuordnen=True, snapshots="keine")
    antwort = await _tag(db, a.id)

    assert antwort.wp_waerme_kwh is None
    assert antwort.wp_waerme_grund
    assert "keine Zählerstände" in antwort.wp_waerme_grund
    assert "zuordnen" not in antwort.wp_waerme_grund, (
        "eedc fordert eine Zuordnung, die es längst gibt — der Melder-Fall selbst")


async def test_a6_zaehlerruecksprung_war_bisher_nur_eine_logzeile(db):
    """Zustand 3 — erkannt, protokolliert und dem Anwender nie gesagt.

    ``_tageswert_aus_raendern`` erkennt den Rücksprung und gibt bewusst ``None``
    zurück (ADR-002/P4: keine Aussage statt einer falschen). Den Grund schrieb
    es bis zum 26.08.2026 ausschließlich ins Log.
    """
    a, _inv = await _baue_a6(db, zuordnen=True, snapshots="reset")
    antwort = await _tag(db, a.id)

    assert antwort.wp_waerme_kwh is None
    assert antwort.wp_waerme_grund
    assert "zurückgesprungen" in antwort.wp_waerme_grund


async def test_a6_die_gesperrte_arbeitszahl_nennt_denselben_grund(db):
    """⛔ **Dieselbe Falschaussage saß eine Ebene tiefer — sichtbar.**

    ``arbeitszahl`` sperrt sich bei fehlender Wärme mit *„kein
    Wärmemengenzähler zugeordnet"*, und dieser Satz steht seit S3 als
    **sichtbarer** Untertitel unter der JAZ-Kachel. Bei dietmar war er falsch.

    ⭐ *Der Layer sieht nur eine Zahl, die nicht da ist — er kann den Grund
    nicht kennen und darf ihn deshalb nicht behaupten.*
    """
    a, _inv = await _baue_a6(db, zuordnen=True, snapshots="keine")
    antwort = await _tag(db, a.id)

    assert antwort.wp_jaz is None
    assert antwort.wp_jaz_grund == "für diesen Tag keine Zählerstände"


async def test_a6_mit_zaehlerstaenden_steht_eine_zahl_und_kein_grund(db):
    """Die Gegenrichtung: **wo ein Wert steht, steht kein Grund.**

    Beides nebeneinander wäre ein Widerspruch auf der Fläche — und die
    naheliegende Bauform, wenn man den Grund unabhängig vom Wert befüllt.
    """
    a, _inv = await _baue_a6(db, zuordnen=True, snapshots="voll")
    antwort = await _tag(db, a.id)

    assert antwort.wp_waerme_kwh == pytest.approx(80.0), "40 Heizwärme + 40 Warmwasser"
    assert antwort.wp_waerme_grund is None
    assert antwort.wp_jaz == pytest.approx(4.0), "80 ÷ 20"


# ═══ A7 — MartyBr: die Wärmepumpe heizt, macht Warmwasser oder kühlt ════════
#
# Forum 89667 #230 (MartyBr, 27.08.2026): *„Wie @rapahl auch sagte, die WP
# heizt, macht WW oder kühlt."* Einen Beitrag davor hat dietmar1968 es begründet
# (#225): Eine konventionelle Wärmepumpe hat **einen** Kältekreis mit **einem**
# Verdichter und ein Umschaltventil — die drei Betriebsformen schließen sich
# gegenseitig aus.
#
# ⛔ **Bis N-336 kannte der Betriebsmodus-Kanon nur Heizen und Kühlen.** Sein
# Warmwasser-Strom fiel in „nicht aufgeteilt" — denselben Topf wie Standby und
# Sensorausfall.
#
# Zahlen (Vitocal-Bauform, ohne getrennte Strommessung): 1000 kWh Strom,
# davon per Modus 600 Heizen · 250 Warmwasser · 100 Kühlen; 2400 kWh Heizwärme
# und 600 kWh Warmwasser-Wärme.

_A7_SPLIT = {
    "modus_strom_heizen_kwh": 600.0,
    "modus_strom_warmwasser_kwh": 250.0,
    "modus_strom_kuehlen_kwh": 100.0,
    "modus_abdeckung_h": 700.0,
}

_A7_BASIS = {
    "stromverbrauch_kwh": 1000.0,
    "heizenergie_kwh": 2400.0,
    "warmwasser_kwh": 600.0,
}


async def _baue_a7(db, *, mit_warmwasser_split: bool = True):
    a = await _anlage(db, "A7 MartyBr Modus")
    split = dict(_A7_SPLIT)
    if not mit_warmwasser_split:
        # Der Zustand VOR N-336: dieselbe Anlage, dieselben Stunden — nur dass
        # eedc die Warmwasser-Stunden nicht benennen konnte.
        split.pop("modus_strom_warmwasser_kwh")
    wp = await _geraet(db, a, "Vitocal 333-G",
                       {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"},
                       {**_A7_BASIS, **split})
    await db.commit()
    return a, wp


async def test_a7_warmwasser_bekommt_eine_eigene_zeile(db):
    """N-336: der gemessene Warmwasser-Strom heißt Warmwasser, nicht „Rest"."""
    a, _wp = await _baue_a7(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_modus_strom_heizen_kwh == pytest.approx(600.0)
    assert antwort.wp_modus_strom_warmwasser_kwh == pytest.approx(250.0)
    assert antwort.wp_modus_strom_kuehlen_kwh == pytest.approx(100.0)


async def test_a7_die_restmenge_traegt_das_warmwasser_nicht_mehr(db):
    """1000 − 600 − 250 − 100 = 50 — und **nicht** 300.

    ⛔ Die 300 wären die Zahl vor N-336: 250 kWh gemessener Warmwasser-Strom,
    ununterscheidbar von Standby und Sensorausfall. Genau das hat MartyBr
    gesehen.
    """
    a, _wp = await _baue_a7(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_modus_nicht_aufgeteilt_kwh == pytest.approx(50.0)


async def test_a7_die_arbeitszahl_aendert_sich_durch_den_split_NICHT(db):
    """⭐ **Die Falle dieses Baus — und der Grund, warum es diese Probe gibt.**

    Warmwasser sieht in der Aufteilung aus wie Kühlen, Lüften und Entfeuchten:
    eine Betriebsart neben dem Heizen. Es ist aber die einzige davon, die eine
    **bewertete Nutzenergie** erzeugt — 600 kWh Warmwasser-Wärme, die über
    ``waerme_gesamt_kwh`` im **Zähler** desselben Quotienten stehen.

    Zöge man den Warmwasser-Strom wie „funktionsfremd" aus dem Nenner, stünde
    die Wärme oben und ihr Strom nirgends:

    * richtig:  3000 ÷ (1000 − 100) = **3,333**
    * falsch:   3000 ÷ (1000 − 100 − 250) = **4,615** — **+38 %** geschenkt

    Diese Probe fährt **dieselbe Anlage zweimal**: einmal mit und einmal ohne
    den Warmwasser-Split. Beide müssen dieselbe Arbeitszahl liefern — denn an
    der gemessenen Energie hat sich nichts geändert, nur an ihrer Beschriftung.
    """
    a_neu, _ = await _baue_a7(db, mit_warmwasser_split=True)
    a_alt, _ = await _baue_a7(db, mit_warmwasser_split=False)

    jaz_neu = (await _monat(db, a_neu.id)).wp_jaz
    jaz_alt = (await _monat(db, a_alt.id)).wp_jaz

    assert jaz_neu == pytest.approx(3000.0 / 900.0), (
        "Wärme 2400 + 600 = 3000; Nenner 1000 − 100 Kühlstrom. Der "
        "Warmwasser-Strom gehört NICHT abgezogen."
    )
    assert jaz_neu == pytest.approx(jaz_alt), (
        "Eine Beschriftung darf keine Kennzahl bewegen — sonst hätte jede "
        "Brauchwasser-Wärmepumpe mit N-336 eine bessere JAZ bekommen, ohne "
        "dass ein einziger Messwert anders wäre"
    )


async def test_a7_die_mengen_summieren_sich_auf_den_bezug(db):
    """K1: die Gesamtmenge bleibt die Wahrheit, die Aufteilung steht daneben."""
    a, _wp = await _baue_a7(db)
    antwort = await _monat(db, a.id)

    teilmengen = (
        antwort.wp_modus_strom_heizen_kwh
        + antwort.wp_modus_strom_warmwasser_kwh
        + antwort.wp_modus_strom_kuehlen_kwh
        + antwort.wp_modus_nicht_aufgeteilt_kwh
    )
    assert teilmengen == pytest.approx(antwort.wp_modus_strom_bezug_kwh)
    assert antwort.wp_strom_kwh == pytest.approx(1000.0), (
        "die Bilanzgröße ist von der Aufteilung unberührt"
    )


# ═══ A8 — dietmar1968, die Bauart-Sperre (R2/§5, gebaut 28.08.2026) ══════════
#
# Forum 89667 **#221/#226/#237**, seine eigene Beschreibung der Anlage:
# *„Ich habe eine konventionelle Bosch Wärmepumpe und eine Bosch Klimaanlage mit
# 3 Innengeräten. Ich kühle nicht mit der Wärmepumpe. Er vermengt vermutlich die
# Anlagen miteinander."*
#
# ⭐ **Warum A1 und A5 diesen Fall NICHT schon abdecken — das ist der ganze
# Punkt dieser Sektion.** Dort meldet die Klimaanlage **keine** Wärme, und damit
# greift bereits `waerme_deckt_nicht_alle_geraete` (Geräte mit Wärme < Geräte
# mit Strom). Die Sperre war also da; **nur ihre Begründung war die falsche.**
#
# Hier steht die Lage, die die alte Sperre **gar nicht** sieht: Beide Geräte
# melden Wärme. `geraete_mit_waerme == geraete_mit_strom` ⇒ kein Grund, und die
# vermischte Zahl erschiene. Möglich ist das, seit eine Klimaanlage ihre
# Nutzenergie erfassen kann (v4.0.24 / W-5) — die Erfassung hat den Fall
# geschaffen, den die Kennzahl-Sperre noch nicht kannte.
#
# Zahlen: WP 3000 kWh Wärme auf 800 kWh Strom (JAZ 3,75) · Klimaanlage 400 kWh
# Wärme auf 200 kWh Strom. Anlagenweit stünden 3400 ÷ 1000 = 3,4 — ein Quotient
# aus zwei Vergleichsmaßstäben, den SOLL §5 ausdrücklich verbietet.

async def _baue_a8(db):
    a = await _anlage(db, "A8 dietmar Bauarten")
    wp = await _geraet(db, a, "Bosch Wärmepumpe",
                       {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"},
                       {"stromverbrauch_kwh": 800.0, "heizenergie_kwh": 3000.0})
    await _geraet(db, a, "Bosch Klimaanlage",
                  {"wp_art": "luft_luft", "effizienz_modus": "gesamt_jaz"},
                  {"stromverbrauch_kwh": 200.0, "heizenergie_kwh": 400.0})
    await db.commit()
    return a, wp


async def test_a8_zwei_bauarten_ergeben_keine_gemeinsame_kennzahl(db):
    """**SOLL §5** — *„Mengen dürfen nebeneinander stehen, eine gemeinsame JAZ nicht."*

    ⛔ **Die Probe, die den Bau trägt.** Ohne die Bauart-Sperre stünde hier
    3400 ÷ 1000 = 3,4, und **keine** der vier bis dahin gebauten §4.2-Lagen
    hätte sie verhindert: Beide Geräte melden Wärme, keiner meldet eine
    Störung, es gibt keinen Zeitraum-Versatz und nichts ist abgeleitet.
    """
    a, _wp = await _baue_a8(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz is None, (
        "3400 ÷ 1000 = 3,4 — eine Luft-Wasser-Wärmepumpe und eine "
        "Split-Klimaanlage in einer Kennzahl, genau die Vermengung, nach der "
        "dietmar1968 in #201 gefragt hat"
    )
    assert antwort.wp_jaz_grund == GRUND_BAUARTEN_GEMISCHT


async def test_a8_die_mengen_stehen_weiter_nebeneinander(db):
    """Gesperrt wird die **Kennzahl**, nicht die Messung — §5 erlaubt die Summen.

    ⚠ Das ist die Grenze des Baus, und sie ist Absicht: Der Balken und die
    Kacheln bleiben gemeinsam. Was fehlte, war nicht die Trennung der Mengen,
    sondern die Auskunft, **welche Geräte** darin stecken — die trägt
    `komponenten_geraete`, seit dem 28.08. auch in der Tagessicht.
    """
    a, _wp = await _baue_a8(db)
    antwort = await _monat(db, a.id)

    assert antwort.wp_strom_kwh == pytest.approx(1000.0), "800 + 200"
    assert antwort.wp_waerme_kwh == pytest.approx(3400.0), "3000 + 400"
    assert "waermepumpe" in (antwort.komponenten_geraete or {}), (
        "der Balken muss seine Geräte nennen können"
    )
    assert sorted(antwort.komponenten_geraete["waermepumpe"]) == [
        "Bosch Klimaanlage", "Bosch Wärmepumpe",
    ]


async def test_a8_das_einzelne_geraet_behaelt_seine_zahl(db):
    """Die anlagenweite Sperre ist am EINZELNEN Gerät gegenstandslos.

    Dieselbe Zusage wie bei A1: Unter *Komponenten → Wärmepumpe* steht jedes
    Gerät für sich, und dort ist die Abgrenzung sauber (3000 ÷ 800 = 3,75).
    **Ohne diese Probe wäre die Sperre eine Verschlechterung** — sie nähme dem
    Melder eine Zahl, die er zu Recht sehen darf.
    """
    a, _wp = await _baue_a8(db)
    blocks = await _hub(db, a.id)

    wp_block = next(b for b in blocks
                    if b.investition.bezeichnung == "Bosch Wärmepumpe")
    assert wp_block.zusammenfassung.get("durchschnitt_cop") == pytest.approx(3.75)


async def test_a8_gegenprobe_eine_bauart_bleibt_unberuehrt(db):
    """**Die Sperre muss diskriminieren** — zwei Luft-Wasser-Geräte sind kein Mix.

    ⛔ Ohne diese Gegenprobe wäre nicht gezeigt, dass die neue Lage die
    **Bauart** prüft und nicht bloß „mehr als ein Gerät". Eine Sperre, die bei
    jeder Zweitanlage zuschlägt, hätte jede Kaskade aus zwei baugleichen
    Wärmepumpen um ihre Kennzahl gebracht.

    ⚠ Und sie zeigt die **Reihenfolge**: Hier meldet das zweite Gerät keine
    Wärme, also gilt weiterhin der allgemeinere Grund — er ist nicht
    verschwunden, er ist nur nachrangig geworden.
    """
    a = await _anlage(db, "A8b zwei Waermepumpen")
    await _geraet(db, a, "Wärmepumpe Haus",
                  {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"},
                  {"stromverbrauch_kwh": 800.0, "heizenergie_kwh": 3000.0})
    await _geraet(db, a, "Wärmepumpe Werkstatt",
                  {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"},
                  {"stromverbrauch_kwh": 200.0})
    await db.commit()
    antwort = await _monat(db, a.id)

    assert antwort.wp_jaz_grund == GRUND_GERAETE_OHNE_WAERME, (
        "zwei Geräte DERSELBEN Bauart — hier gilt die alte, allgemeinere Lage"
    )


# ═══ A9 — dietmar1968 (#295): der Altwert, den das Gerät nicht haben kann ═══
#
# **Die Anlage, die es wirklich gibt.** Bosch Luft-Luft-Klimaanlage mit drei
# Innengeräten, 99 % Kühlbetrieb (T89667 #190/#221/#295). In ihrer Juni-Zeile
# steht ein `warmwasser_kwh` aus der Zeit VOR N-304 (22.08.2026) — seither
# bietet der Monatsabschluss das Feld an einer Split-Klimaanlage nicht mehr an,
# aber der gespeicherte Wert blieb stehen.
#
# **Was er auf seinem Bildschirm anrichtete** (alle vier aus seinem Screenshot):
# „Wärme erzeugt 889 kWh" · JAZ 1,09 · „Ersparnis vs. Gas 38 €" ·
# „CO₂-Ersparnis −112 kg vs. fossile Heizung" — an einem Gerät, das zu 99 %
# Kälte erzeugt hat.
#
# ⭐ **Warum die Probe hierher gehört und nicht zu den Layer-Wächtern.** Der
# Layer ist mit `test_klima_ohne_warmwasser_n304.py` gedeckt. Hier steht die
# andere Frage, für die es diese Datei gibt: *Kommt es auf der Fläche an?* Und
# sie ist auf dieser Achse besonders teuer — der Maintainer hat weder
# Wärmepumpe noch Klimaanlage und kann keine dieser Zahlen gegenprüfen.

WW_ALTWERT_KWH = 889.0
KLIMA_STROM_KWH = 817.0


async def _baue_a9(db):
    a = await _anlage(db, "A9 dietmar Klimaanlage")
    klima = await _geraet(
        db, a, "Klimaanlage",
        # Der alte Energieträger ist gesetzt — genau deshalb stand bei ihm
        # überhaupt eine Gas-Ersparnis da. Ohne ihn griffe schon `bewertbar`,
        # und die Probe bewiese nichts.
        {"wp_art": "luft_luft", "effizienz_modus": "gesamt_jaz",
         "alter_energietraeger": "gas", "alter_preis_cent_kwh": 10.0},
        {"stromverbrauch_kwh": KLIMA_STROM_KWH,
         "warmwasser_kwh": WW_ALTWERT_KWH},
    )
    await db.commit()
    return a, klima


async def test_a9_der_altwert_ist_keine_waerme_dieses_geraets(db):
    """Die Menge: 889 kWh „Warmwasser" an einer Klimaanlage zählen nicht.

    ⛔ Und die Kennzahl steht deshalb NICHT auf 0, sondern auf „keine Aussage"
    mit Grund (ADR-002/P4) — eine 0 hieße „gemessen, es kam nichts heraus".
    """
    a, _klima = await _baue_a9(db)
    block = next(b for b in await _hub(db, a.id)
                 if b.investition.bezeichnung == "Klimaanlage")
    z = block.zusammenfassung

    assert z["gesamt_warmwasser_kwh"] == 0.0
    assert z["gesamt_waerme_kwh"] == 0.0, "„Wärme erzeugt 889 kWh“ war der Befund"
    assert z["durchschnitt_cop"] is None, "1,09 war keine Arbeitszahl, sondern ein Bruch"
    assert z["durchschnitt_cop_grund"], "ohne Zahl gehört der Grund daneben (S3)"


async def test_a9_keine_gas_ersparnis_und_kein_co2_aus_kaelte(db):
    """Die zwei Geldzahlen — genau die, die N-304s Docstring vorhergesagt hat.

    *„Ein an einer Luft-Luft-Anlage gepflegter Warmwasser-Wert erzeugt eine
    Ersparnis für Wärme, die das Gerät nie erzeugt hat."* Sie stand bei dietmar
    mit 38 € und −112 kg auf dem Schirm.
    """
    a, _klima = await _baue_a9(db)
    z = next(b for b in await _hub(db, a.id)
             if b.investition.bezeichnung == "Klimaanlage").zusammenfassung

    assert z["ersparnis_euro"] is None, "„Ersparnis vs. Gas 38 €“ stand da"
    assert z["co2_ersparnis_kg"] is None, "„CO₂-Ersparnis −112 kg vs. fossile Heizung“"
    assert z["wp_kosten_euro"] > 0, (
        "⛔ Der Strom bleibt — er ist geflossen. Nur der Vergleich entfällt."
    )


async def test_a9_die_warmwasser_achse_verschwindet_aus_der_anzeige(db):
    """SOLL §3.3/**S2** — „Ein Balken sagt, was er zeigt."

    Ohne dieses Flag stünde die Aufteilung weiterhin als festes Paar
    Heizung/Warmwasser da, nur mit zwei Nullen. Der Client hängt Spalte, Balken
    und Legende daran.
    """
    a, _klima = await _baue_a9(db)
    z = next(b for b in await _hub(db, a.id)
             if b.investition.bezeichnung == "Klimaanlage").zusammenfassung

    assert z["hat_warmwasser_achse"] is False


async def test_a9_gegenprobe_die_luft_wasser_wp_behaelt_alles(db):
    """⛔ **Die Gegenprobe, ohne die der Bau eine Löschung wäre.**

    Dieselbe Zeile an einer Luft-Wasser-Wärmepumpe: Menge, Achse, Arbeitszahl
    und Gas-Ersparnis bleiben unverändert. Ein Filter, der überall zuschlägt,
    nähme jeder Wärmepumpe ihr Warmwasser.
    """
    a = await _anlage(db, "A9b Luft-Wasser")
    await _geraet(
        db, a, "Wärmepumpe",
        {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz",
         "alter_energietraeger": "gas", "alter_preis_cent_kwh": 10.0},
        {"stromverbrauch_kwh": KLIMA_STROM_KWH,
         "warmwasser_kwh": WW_ALTWERT_KWH},
    )
    await db.commit()
    z = next(b for b in await _hub(db, a.id)
             if b.investition.bezeichnung == "Wärmepumpe").zusammenfassung

    assert z["gesamt_warmwasser_kwh"] == pytest.approx(WW_ALTWERT_KWH)
    assert z["gesamt_waerme_kwh"] == pytest.approx(WW_ALTWERT_KWH)
    assert z["hat_warmwasser_achse"] is True
    # `abs=0.005`: der Endpoint rundet die Arbeitszahl auf zwei Stellen —
    # eine relative Toleranz misst hier die Rundung, nicht die Rechnung.
    assert z["durchschnitt_cop"] == pytest.approx(
        WW_ALTWERT_KWH / KLIMA_STROM_KWH, abs=0.005
    )
    assert z["ersparnis_euro"] is not None


# ═══ A10 — 8ear (#404): die Achse, die es am Gerät gibt und in den Daten nie ═══
#
# **Die Anlage, die es wirklich gibt.** Zwei Geräte: eine Luft-Wasser-Wärmepumpe,
# die **nur heizt**, und daneben eine eigene Brauchwasser-Wärmepumpe fürs
# Warmwasser (#404, 03.09.2026). Sein Satz: *„Leider kann ich eedc nicht
# beibringen, dass die Luft/Wasser Wärmepumpe nur heizt und kein cop und kein
# Strom und kein heizwarme für Warmwasser hat."*
#
# ⭐ **Warum sein Wunsch — ein Schieber am Gerät — NICHT gebaut wurde.** SOLL
# §3.2a **R1**: *„was ein Gerät liefern kann, sagt der zugeordnete Zähler, nicht
# seine Bauart."* Ein Kennzeichen „macht kein Warmwasser" wäre eine zweite
# Aussage neben dem Zähler, und bei einer späteren Zuordnung müsste eedc
# entscheiden, welche gilt — im Zweifel gegen die Messung. Dieselbe Antwort gibt
# R1 der Sole-Wasser-WP mit Kühlung (MartyBr) und der Luft-Luft ohne Warmwasser
# (OB73-gif); die Zeilen stehen in derselben Tabelle des SOLL.
#
# ⛔ **Und warum es KEINE `wp_art` „Luft-Wasser, nur Heizen" gibt.** Eine
# Luft-Wasser-Wärmepumpe macht im Regelfall **beides** — Heizung und Warmwasser
# über denselben Kreis mit Umschaltventil auf den Speicher. 8ears Anlage ist die
# Ausnahme, nicht die Bauart (Einwand Gernot, 05.09.2026). Eine solche Art wäre
# genau die „Bauart-Schublade", die das SOLL in §3.2a verwirft: sie behauptete
# einen Gerätetyp, wo eine Anlagen-Konfiguration vorliegt.
#
# ⚠ **Was diese Proben NICHT decken.** Wer EINEN Wärmemengenzähler über die
# Gesamtwärme hat, trägt seine Zahl mangels Gesamtfeld unter `heizenergie_kwh`
# ein — dort steht dann Heizung **und** Warmwasser unter dem Namen „Heizwärme".
# Diese Lage ist von 8ears in den Daten nicht zu unterscheiden und bleibt hier
# ungelöst; sie ist ein eigener Befund, kein Anbau an diese Achse.

HEIZ_KWH_8EAR = 4200.0
STROM_KWH_8EAR = 1200.0


async def _baue_a10(db, ww_wert=None, mapping=None):
    a = await _anlage(db, "A10 8ear nur Heizen")
    if mapping is not None:
        a.sensor_mapping = mapping
    daten = {"stromverbrauch_kwh": STROM_KWH_8EAR,
             "heizenergie_kwh": HEIZ_KWH_8EAR}
    if ww_wert is not None:
        daten["warmwasser_kwh"] = ww_wert
    wp = await _geraet(
        db, a, "Wärmepumpe",
        {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz",
         "alter_energietraeger": "gas", "alter_preis_cent_kwh": 10.0},
        daten,
    )
    await db.commit()
    return a, wp


async def _z_a10(db, **kw):
    a, _wp = await _baue_a10(db, **kw)
    return next(b for b in await _hub(db, a.id)
                if b.investition.bezeichnung == "Wärmepumpe").zusammenfassung


async def test_a10_ohne_je_gemessenes_warmwasser_faellt_die_achse_weg(db):
    """8ears Fall: die Achse gibt es am Gerät, in seinen Daten nie.

    Vor diesem Bau hing `hat_warmwasser_achse` allein an der **Bauart** und
    stand deshalb an jeder Luft-Wasser-WP auf True — Balken, Spalte und Legende
    zeigten dauerhaft eine Null für eine Größe, die er nicht führt.
    """
    z = await _z_a10(db)

    assert z["hat_warmwasser_achse"] is False
    # ⛔ Die Heizseite bleibt vollständig — sonst wäre der Bau eine Löschung.
    assert z["gesamt_heizenergie_kwh"] == pytest.approx(HEIZ_KWH_8EAR)
    assert z["gesamt_waerme_kwh"] == pytest.approx(HEIZ_KWH_8EAR)
    assert z["durchschnitt_cop"] == pytest.approx(
        HEIZ_KWH_8EAR / STROM_KWH_8EAR, abs=0.005
    )


async def test_a10_eine_gepflegte_null_haelt_die_achse(db):
    """⛔ **Die Grenze des Total-Fall-Entscheids (29.08.), als Probe.**

    Unterdrückt wird nur, was **nie** gemessen wurde. Ein einziger gepflegter
    Monat hält die Achse — auch mit dem Wert **0**: Dann ist die Null eine
    Messung („diesen Monat kein Warmwasser") und keine Leerstelle, und sie
    auszublenden verbürge eine gute Angabe.

    ⚠ Genau hier scheitert der naheliegende Kurzschluss `if gesamt_warmwasser:`
    — er macht aus der gepflegten 0 eine Leerstelle.
    """
    z = await _z_a10(db, ww_wert=0.0)

    assert z["hat_warmwasser_achse"] is True
    assert z["gesamt_warmwasser_kwh"] == 0.0


async def test_a10_zugeordneter_zaehler_haelt_die_achse_ohne_jeden_wert(db):
    """R1 wörtlich: *wer einen Zähler zuordnet, sieht die Achse* — sofort.

    Die frisch eingerichtete Anlage: Sensor zugeordnet, noch kein Monat
    geschrieben. Ohne diesen Zweig verschwände die Achse genau in dem Moment, in
    dem der Anwender sie gerade eingerichtet hat, und käme erst Wochen später
    zurück.
    """
    z = await _z_a10(db, mapping={
        "investitionen": {"1": {"felder": {
            "warmwasser_kwh": {"strategie": "sensor",
                               "sensor_id": "sensor.wp_warmwasser"},
        }}},
    })

    assert z["hat_warmwasser_achse"] is True
