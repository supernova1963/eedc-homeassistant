"""SOLL Wärme/Klima — **Achse III: Auflösung.** Was kann eine Sicht sagen, was nicht?

Maschinelle Fassung von `soll-waerme-klima.md` §3.1 (Auflösung je Herkunft) und
§3.3/**S3** (*„Eine Sicht, die weniger zeigt als die Nachbarsicht, sagt warum"*).

Proben-Sorten wie in `test_soll_waerme_klima_achse1_erfassung.py`: **ERFÜLLT**
assertiert die SOLL-Erwartung hart, **OFFEN** hält den heutigen Zustand fest und
schlägt fehl, sobald gebaut wird. Kein ``xfail``.

⭐ **Warum III-1 hier mit Fixtures steht und nicht als Rückfrage bei einem Melder:**
dietmar1968 hat Sensoren zugeordnet, deren Namen auf einen Tages-Reset deuten
(``…energie_heizen_heute_kwh_riemann_sql``). Ob **seine** Sensoren zurücksetzen,
entscheidet aber nicht, ob eedc die Bauform beherrschen muss: Ein
``utility_meter`` mit ``daily``-Zyklus ist ein Standard-Baustein von Home
Assistant und existiert unabhängig davon, wer ihn gerade benutzt. **Die Fixture
ist der stärkere Beleg als die Rückfrage** — sie stellt die Bauform selbst her.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)

#: SOLL-Regeln, die noch **nicht** gebaut sind (siehe Achse I für das Muster).
REGELN_OFFEN: dict[str, str] = {
    # Leer — beide Regeln dieser Achse sind gebaut (26.08.2026).
}

DATUM = date(2025, 6, 15)


async def _anlage_mit_tagesreset_zaehler(db, *, randwerte, feld, zwischenstaende=()):
    """Anlage + Klimaanlage mit EINEM Betriebsart-Zähler.

    `randwerte`: ``(wert_00_00, wert_folgetag_00_00)`` — die beiden Stände, aus
    denen der Tageswert als Differenz gebildet wird.

    `zwischenstaende`: ``[(stunde, wert), …]`` — die stündlichen Snapshots
    **innerhalb** des Tages, wie sie der :05-Scheduler schreibt.

    ⭐ **Die Zwischenstände sind nicht Beiwerk, sie sind der Gegenstand.** Ein
    Tagesreset-Zähler ist an seinen zwei Randständen **nicht** von einem ruhenden
    Gerät unterscheidbar — beide zeigen dieselbe Differenz. Unterscheidbar wird
    er allein an der **Monotonie**: ein kumulativer Zähler kann nicht fallen. Die
    erste Fassung dieser Fixture schrieb nur die Ränder und stellte damit gar
    keinen Tagesreset-Zähler nach, sondern ein ruhendes Gerät.
    """
    anlage = Anlage(anlagenname="III", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Splitklima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter={"wp_art": "luft_luft"},
    )
    db.add(inv)
    await db.flush()

    t0 = datetime.combine(DATUM, datetime.min.time())
    key = f"inv:{inv.id}:{feld}"
    s0, s1 = randwerte
    db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key, zeitpunkt=t0,
                          wert_kwh=s0, quelle="ha_statistics"))
    db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                          zeitpunkt=t0 + timedelta(days=1), wert_kwh=s1,
                          quelle="ha_statistics"))
    for stunde, wert in zwischenstaende:
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                              zeitpunkt=t0 + timedelta(hours=stunde),
                              wert_kwh=wert, quelle="ha_statistics"))

    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": {
        feld: {"strategie": "sensor", "sensor_id": f"sensor.klima_{feld}_heute"},
    }}}}
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=DATUM,
        komponenten_kwh={f"waermepumpe_{inv.id}": 8.0},
    ))
    await db.commit()
    return anlage, inv


# ══ III-1a · ERFÜLLT — Tagesreset, Stand NACH dem Reset gelesen ════════════

async def test_iii1a_tagesreset_stand_nach_reset(db):
    """**ERFÜLLT (P4/W-11, Variante (a) — gebaut 2026-08-26).**

    Der Zähler wird um Mitternacht auf 0 gesetzt; beide Randstände werden
    **nach** dem Reset gelesen. Am Tag selbst sind real 4,5 kWh geflossen — an
    den Zwischenständen ablesbar, an den Rändern nicht.

    SOLL §3.1: *„Ein Zähler mit Tages-Reset wird erkannt und abgelehnt, statt
    still falsche Werte zu erzeugen."* ⇒ **kein Eintrag** für dieses Gerät
    (P4 — keine Aussage statt einer 0).

    Vorher: ``0.0 − 0.0 = 0.0``, und die **0 wurde geschrieben**, obwohl die
    Funktion im eigenen Docstring „keine Aussage statt einer 0" für sich
    reklamierte. Übersprungen wurde nur ``None``.
    """
    assert "P4/W-11" not in REGELN_OFFEN
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(0.0, 0.0), feld="betriebsart_strom_kuehlen_kwh",
        zwischenstaende=[(6, 1.5), (12, 3.0), (18, 4.5)],
    )
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )

    assert werte == {}


# ══ III-1b · ERFÜLLT — Tagesreset, Stand VOR dem Reset gelesen ═════════════

async def test_iii1b_tagesreset_stand_vor_reset(db):
    """**ERFÜLLT (P4/W-11, Variante (b) — gebaut 2026-08-26).**

    Derselbe Zähler, andere Auslegung des Mitternachts-Snapshots: Der Stand um
    00:00 ist der **Tagesendwert** des Vortags (5,0), der Folgetag beginnt wieder
    bei ~0.

    Vorher griff die Tagesreset-Heuristik ``s1 < 0.5 and s0 > 0.5 ⇒
    return max(0.0, s1)`` — also **0**, geschrieben als Aussage.

    ⭐ **Die Heuristik ist für den Stunden-Slot über Mitternacht gebaut und dort
    richtig** (`get_hourly_kwh_by_category`, unverändert). Am **Tagesrand** kann
    sie nichts retten, weil das ganze Fenster zwischen zwei Resets liegt.
    Gleiche Formel, verschiedenes Fenster, verschiedene Wahrheit.
    """
    assert "P4/W-11" not in REGELN_OFFEN
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(5.0, 0.0), feld="betriebsart_strom_kuehlen_kwh",
        zwischenstaende=[(6, 1.2), (18, 3.8)],
    )
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )

    assert werte == {}


# ══ III-1b2 · ERFÜLLT — Tagesreset, BEIDE Ränder vor dem Reset ═════════════

async def test_iii1b2_tagesreset_beide_raender_vor_dem_reset(db):
    """**ERFÜLLT (P4/W-11, Variante (c) — der Fall, den die Ränder verstecken).**

    Beide Mitternachts-Snapshots treffen den **Tagesendwert** vor dem Reset:
    00:00 = 5,0 (gestriger Tagesstand), Folgetag 00:00 = 7,0 (heutiger). Die
    Randdifferenz ist **+2,0** — positiv, plausibel, und **die Differenz zweier
    Tagessummen statt einer Tagesmenge**.

    ⭐ **Diese Variante stand in keiner Fassung des Befundes.** Sie ist beim Bau
    der Fixture aufgefallen und hat die Erkennung geändert: Ein Entwurf, der nur
    ``max > Endstand`` prüfte, hätte sie durchgelassen — hier liegt kein
    Zwischenstand über 7,0. Sichtbar ist der Reset allein an der **unteren**
    Schranke: direkt nach 00:00 fällt der Zähler auf 0,4 und damit unter s0.
    *Eine Monotonie-Prüfung, die nur ein Ende prüft, prüft keine Monotonie.*
    """
    assert "P4/W-11" not in REGELN_OFFEN
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(5.0, 7.0), feld="betriebsart_strom_kuehlen_kwh",
        zwischenstaende=[(1, 0.4), (12, 3.5), (23, 6.8)],
    )
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )

    assert werte == {}


# ══ III-1c · ERFÜLLT — der kumulative Zähler bleibt unberührt ═══════════════

async def test_iii1c_kumulativer_zaehler_traegt_weiter(db):
    """**ERFÜLLT.** Ein normal hochzählender Zähler liefert seinen Tageswert.

    ⚠ **Diese Gegenprobe gehört zwingend dazu.** Sie hält fest, was die Lösung
    von III-1a/b **nicht** kaputt machen darf: Wer einen echten kumulativen
    Zähler hat, bekommt weiterhin seine Differenz. Eine Reset-Erkennung, die
    diesen Fall mitnimmt, wäre teurer als der Befund.

    Die Zwischenstände sind hier **monoton** — genau die Eigenschaft, an der die
    Erkennung den Unterschied festmacht.
    """
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(100.0, 104.5), feld="betriebsart_strom_kuehlen_kwh",
        zwischenstaende=[(6, 101.2), (12, 102.8), (18, 103.9)],
    )
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )

    assert werte == {str(inv.id): {"betriebsart_strom_kuehlen_kwh": 4.5}}


# ══ III-1c2 · ERFÜLLT — eine gemessene 0 bleibt eine Messung ═══════════════

async def test_iii1c2_ruhendes_geraet_behaelt_seine_null(db):
    """**ERFÜLLT.** Ein Gerät, das an diesem Tag nicht lief, meldet **0,0** — und
    das ist eine Aussage, keine Lücke.

    ⚠ **Die schärfste Gegenprobe des ganzen Pakets.** Der bequeme Weg zu III-1a
    wäre gewesen, jede 0 zu verwerfen („keine Aussage statt einer 0"). Das wäre
    falsch: Eine 0 aus zwei gelesenen Rändern **ist** gemessen. Verworfen wird
    nicht der Wert, sondern der **Zähler**, dessen Reihe die Monotonie verletzt.

    Genau hier verläuft die Grenze zu dietmars Bild vom 25.08. (*Heizen 0 ·
    Kühlen 0 · Nicht aufgeteilt 3 kWh*): Seine eigene Erklärung — *„die Anlage
    war heute nicht in Betrieb"* — beschreibt diesen Fall, und dann ist die
    Anzeige **richtig**.
    """
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(100.0, 100.0), feld="betriebsart_strom_kuehlen_kwh",
        zwischenstaende=[(6, 100.0), (12, 100.0), (18, 100.0)],
    )
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )

    assert werte == {str(inv.id): {"betriebsart_strom_kuehlen_kwh": 0.0}}


# ══ III-1d · OFFEN — die 0 erreicht die Anzeige als Aufteilung ══════════════

async def test_iii1d_tagesreset_erzeugt_keine_aufteilung(db):
    """**ERFÜLLT (P4/W-11 — gebaut 2026-08-26).** Was der Anwender jetzt sieht.

    Vorher stufte die Route die Zeile als **gemessen** ein (ein Betriebsart-
    Zähler war zugeordnet und lieferte 0,0) und rechnete die Aufteilung:
    8 kWh Bezug − 0 gemessen ⇒ **alles unter „nicht aufgeteilt", 100 %**.

    Jetzt: Ohne verwertbaren Zähler ist die Zeile **nicht gemessen** — es gibt
    weder Aufteilung noch 100-%-Balken. Der Block erscheint gar nicht erst,
    statt eine Aufteilung zu behaupten, die es nicht gibt.

    ⚠ **Die Abgrenzung zu III-1c2 ist der eigentliche Gegenstand:** Dort meldet
    ein ruhendes Gerät seine echte 0 und die Zeile **bleibt** gemessen. Der
    Unterschied ist nie der Wert, sondern die Monotonie der Zählerreihe.
    """
    assert "P4/W-11" not in REGELN_OFFEN
    from backend.api.routes.energie_profil.views import get_tag_detail

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(0.0, 0.0), feld="betriebsart_strom_kuehlen_kwh",
        zwischenstaende=[(6, 1.5), (12, 3.0), (18, 4.5)],
    )
    resp = await get_tag_detail(anlage.id, DATUM, db)

    assert resp.wp_modus_gemessen is None
    assert resp.wp_modus_strom_kuehlen_kwh is None
    assert resp.wp_modus_nicht_aufgeteilt_kwh is None


# ══ III-2 · OFFEN — S3: der Tag kennt seine eigene Wärme-Summe nicht ════════

def test_iii2_tag_liefert_waerme_gesamt_und_arbeitszahl():
    """**ERFÜLLT (S3/W-9 — gebaut 2026-08-26).**

    Der Tagespfad liefert jetzt die Wärme **gesamt** und die Arbeitszahl fertig,
    beide aus dem Layer (`waermepumpe_kennzahl`). Vorher gab es hier nur die
    beiden Summanden, und der Client bildete Summe **und** Quotient selbst.

    ⛔ **Der Befund war zur Hälfte falsch, und das gehört hierher.** Er lautete:
    *„Im Tag bleiben JAZ, Wärme und Ersparnis ‚—', obwohl Heizung und Warmwasser
    einzeln vorliegen und ihre Summe die Wärme wäre."* Gemessen am 26.08.:
    `v4/TagKomponenten.tsx` **hat** diese Summe gebildet, seit der ersten Fassung
    der Datei (`6cea9f1e`) — liegen die Summanden vor, entsteht die Wärme und
    daraus die Tages-JAZ. Und das „—" trug bereits einen Grund im
    Voraussetzungs-Hinweis (`KpiStrip.tsx:30`, Entscheid Gernot 24.06.).

    ⭐ **Was wirklich fehlte, ist deshalb kein Datenverlust, sondern eine zweite
    Definitionsstelle:** derselbe Kanon im Layer *und* im Client — und der
    Client-Zweig kannte die Belastbarkeits-Sperre nicht (ADR-001/S1, gleiche
    Klasse wie W-3). *Ein Befund, der die Aufrufkette nicht aufgelöst hat,
    beschreibt das Symptom des Melders, nicht die Ursache.*

    **Warum rapahl trotzdem dreimal „—" sah:** Ihm fehlt der **kumulative**
    Wärmemengenzähler; sein Monatswert stammt aus dem Monatsabschluss, den der
    Tag nicht haben kann. Das ist die Auflösungsfrage aus SOLL §3.1 — richtig
    gerechnet und begründet.
    """
    assert "S3/W-9" not in REGELN_OFFEN
    from backend.api.routes.energie_profil._shared import TagDetailResponse

    felder = set(TagDetailResponse.model_fields)

    assert "wp_heizung_kwh" in felder
    assert "wp_warmwasser_kwh" in felder
    assert "wp_waerme_kwh" in felder
    # Die Zahl UND ihre Begründung — ein „—" ohne Grund ist die häufigste
    # Beschwerde dieser Fläche (S3).
    assert "wp_jaz" in felder
    assert "wp_jaz_grund" in felder


def test_iii2b_monat_hat_das_feld():
    """**ERFÜLLT.** Die Nachbarsicht trägt die Größe — der Beleg, dass III-2 eine
    Lücke ist und keine bewusste Abwesenheit.

    Ohne diese Gegenprobe wäre „der Tag hat das Feld nicht" nur eine Beobachtung.
    Erst dass **der Monat es hat**, macht daraus die S3-Frage: *Warum zeigt die
    eine Sicht weniger als die andere, ohne es zu sagen?*
    """
    from backend.api.routes.aktueller_monat import AktuellerMonatResponse

    assert "wp_waerme_kwh" in set(AktuellerMonatResponse.model_fields)


# ═══ III-W18 — der Grund für einen fehlenden Tageswert ══════════════════════
#
# SOLL §3.3/**S3**: *„Eine Sicht, die weniger zeigt als die Nachbarsicht, sagt
# warum."* Der Tag zeigte bei dietmar1968 weniger als der Monat — und sagte
# einen Grund, den es bei ihm nicht gab (T89667 #210, W-18).

def test_w18_kurz_und_langform_beschreiben_dieselben_zustaende():
    """⛔ **Zwei Listen für dieselbe Sache müssen deckungsgleich sein.**

    Es gibt sie zweimal, weil derselbe Zustand an zwei verschiedenen Orten
    steht: als Absatz unter der Wärme-Kachel und als kurze Beschriftung neben
    der gesperrten Arbeitszahl. Ein Zustand nur in einer der beiden Listen wäre
    ein Fall, den die eine Fläche benennen kann und die andere nicht — und er
    fiele erst dem Anwender auf.

    ⭐ Dieselbe Bauform, die W-14 erzeugt hat: eine Größe, die an einer von drei
    Stellen nicht nachgezogen wurde.
    """
    from backend.core.tageswert_grund import (
        GRUND_RANG, TAGESWERT_GRUND_KURZ, TAGESWERT_GRUND_TEXT,
    )

    assert set(TAGESWERT_GRUND_KURZ) == set(TAGESWERT_GRUND_TEXT)
    assert set(GRUND_RANG) == set(TAGESWERT_GRUND_TEXT), (
        "ein Zustand ohne Rang verliert jeden Vergleich (`GRUND_RANG.get(..., -1)`)")
    assert all(TAGESWERT_GRUND_KURZ.values()), "eine leere Kurzform ist keine Auskunft"
    assert all(TAGESWERT_GRUND_TEXT.values())


def test_w18_nur_die_fehlende_zuordnung_traegt_eine_handlungsanweisung():
    """**Der Grund sagt, was IST — die Handlung hängt am Feld** (Regel 1 des Moduls).

    ⛔ Genau diese Trennung war der Fehler: Der alte Client-Satz hängte
    *„Sensor zuordnen"* an **jedes** „—", auch an das eines Anwenders, der
    zugeordnet hatte. Eine Handlungsanweisung an den beiden anderen Zuständen
    wäre derselbe Fehler in neuer Form.
    """
    from backend.core.tageswert_grund import (
        GRUND_KEINE_ZAEHLERSTAENDE, GRUND_NICHT_ZUGEORDNET,
        GRUND_ZAEHLER_RUECKSPRUNG, HANDLUNG_JE_FELD, tageswert_grund_text,
    )

    mit_handlung = tageswert_grund_text(GRUND_NICHT_ZUGEORDNET, "wp_heizung_kwh")
    assert mit_handlung and "zuordnen" in mit_handlung

    for grund in (GRUND_KEINE_ZAEHLERSTAENDE, GRUND_ZAEHLER_RUECKSPRUNG):
        text = tageswert_grund_text(grund, "wp_heizung_kwh")
        assert text and "zuordnen" not in text, (
            f"{grund} fordert eine Zuordnung, die es schon gibt")

    # Jedes Feld, das über eine Randdifferenz erhoben wird, braucht seinen
    # Handlungssatz — sonst steht dort nur „Kein Zähler zugeordnet" ohne Weg.
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh  # noqa: F401
    for feld in ("wp_heizung_kwh", "wp_warmwasser_kwh", "speicher_ladung_netz_kwh",
                 "emob_ladung_pv_kwh", "emob_ladung_netz_kwh"):
        assert feld in HANDLUNG_JE_FELD


def test_w18_ein_unbekannter_zustand_liefert_keinen_bezeichner():
    """Ein durchgereichtes ``"zaehler_ruecksprung"`` wäre schlechter als nichts."""
    from backend.core.tageswert_grund import tageswert_grund_kurz, tageswert_grund_text

    assert tageswert_grund_text("gibt_es_nicht") is None
    assert tageswert_grund_kurz("gibt_es_nicht") is None
    assert tageswert_grund_text(None) is None
    assert tageswert_grund_kurz(None) is None


def test_w18_arbeitszahl_behaelt_ihren_wortlaut_ohne_besseren_grund():
    """⚠ **Der Default ist bitgleich zu vorher.**

    Die Sperre bekommt einen optionalen Grund — kein Aufrufer, der ihn nicht
    übergibt, darf sein Verhalten ändern. Sonst wäre W-18 ein stiller Umbau an
    acht anderen Flächen.
    """
    from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl

    ohne = arbeitszahl(0.0, 100.0)
    assert ohne.wert is None
    assert ohne.grund == "kein Wärmemengenzähler zugeordnet"

    mit = arbeitszahl(0.0, 100.0, waerme_fehlt_grund="für diesen Tag keine Zählerstände")
    assert mit.wert is None
    assert mit.grund == "für diesen Tag keine Zählerstände"

    # Der bessere Grund gilt NUR für den fehlende-Wärme-Fall — er darf keine
    # andere Sperre überschreiben.
    kein_strom = arbeitszahl(500.0, 0.0, waerme_fehlt_grund="für diesen Tag keine Zählerstände")
    assert kein_strom.grund == "kein Stromverbrauch erfasst"


# ═══ III-DOK — das Handbuch zitiert die Gründe, also muss es sie kennen ═════

def test_handbuch_waerme_klima_zitiert_die_gruende_woertlich():
    """⛔ **Ein Handbuch ist auch nur eine Behauptung über den Code.**

    `docs/HANDBUCH_WAERME_KLIMA.md` §4 führt die Sperr-Gründe **wörtlich** auf,
    damit ein Anwender den Satz, den er in der App liest, im Handbuch
    wiederfindet. Ändert jemand einen Wortlaut im Code, lügt das Handbuch —
    still, und ausgerechnet an der Stelle, an der jemand nachschlägt, weil er
    nicht weiterweiß.

    ⭐ Dieselbe Klasse wie der falsche Tooltip, der W-18 ausgelöst hat: eine
    Auskunft, die einmal richtig war und es nicht geblieben ist.

    ⚠ **Der Test prüft nur, was das Handbuch als Zitat AUSGIBT** — er verlangt
    nicht, dass jeder neue Grund sofort dort steht. Ein Grund ohne Handbuch-Zeile
    ist eine Lücke; ein Handbuch-Zitat ohne Grund im Code ist eine Falschaussage,
    und nur die ist hier gefangen.
    """
    from pathlib import Path

    from backend.core.berechnungen.waermepumpe_kennzahl import (
        GRUND_FREMDSTROM, GRUND_FREMDWAERME, GRUND_GERAETE_OHNE_WAERME,
        GRUND_KEINE_KAELTEMENGE, GRUND_STROM_NICHT_JE_FUNKTION, GRUND_ZEITRAUM,
    )
    from backend.core.tageswert_grund import TAGESWERT_GRUND_TEXT

    doc = Path(__file__).resolve().parents[3] / "docs" / "HANDBUCH_WAERME_KLIMA.md"
    if not doc.exists():  # eedc-Standalone-Spiegel trägt `docs/` nicht mit
        import pytest
        pytest.skip("docs/ liegt nur im Source-of-Truth-Repo")
    text = doc.read_text(encoding="utf-8")

    erwartet = [
        GRUND_GERAETE_OHNE_WAERME, GRUND_FREMDSTROM, GRUND_FREMDWAERME,
        GRUND_ZEITRAUM, GRUND_STROM_NICHT_JE_FUNKTION, GRUND_KEINE_KAELTEMENGE,
        "kein Stromverbrauch erfasst",
        "nur Kühlbetrieb in diesem Zeitraum",
        "Wärme ist gerechnet, nicht gemessen",
        "kein Wärmemengenzähler zugeordnet",
        *TAGESWERT_GRUND_TEXT.values(),
    ]
    fehlend = [g for g in erwartet if g not in text]
    assert not fehlend, (
        "Das Handbuch zitiert diese Gründe nicht mehr wörtlich — im Code steht "
        f"jetzt etwas anderes: {fehlend}"
    )
