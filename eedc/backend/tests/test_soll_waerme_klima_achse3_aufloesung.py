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
    "P4/W-11": (
        "Ein Zähler mit Tages-Reset liefert im Tagespfad strukturell 0, und die "
        "0 wird als Aussage geschrieben statt als Lücke. `_tagesdetail_boundary_"
        "diff` bildet den Tageswert als Differenz zweier Randstände über "
        "[Tag 00:00, Folgetag 00:00) — bei täglichem Reset stehen an BEIDEN "
        "Rändern Werte am Reset. Der Feld-Hinweis verspricht den Tagessensor "
        "ausdrücklich (`field_definitions.py:179`)."
    ),
    "S3/W-9": (
        "Der Tagespfad trägt `wp_heizung_kwh` und `wp_warmwasser_kwh`, aber "
        "keine Wärme GESAMT — obwohl deren Summe sie wäre. Folge: JAZ, Wärme "
        "und Ersparnis bleiben im Tag „—\", während der Monat sie zeigt. "
        "Melder rapahl (T89667 #202)."
    ),
}

DATUM = date(2025, 6, 15)


async def _anlage_mit_tagesreset_zaehler(db, *, randwerte, feld):
    """Anlage + Klimaanlage mit EINEM Betriebsart-Zähler.

    `randwerte`: ``(wert_00_00, wert_folgetag_00_00)`` — genau die beiden Stände,
    aus denen `_tagesdetail_boundary_diff` den Tageswert bildet. Damit lässt sich
    die Bauform *Tages-Reset-Zähler* exakt nachstellen, ohne einen echten
    ``utility_meter`` zu brauchen.
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

    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": {
        feld: {"strategie": "sensor", "sensor_id": f"sensor.klima_{feld}_heute"},
    }}}}
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=DATUM,
        komponenten_kwh={f"waermepumpe_{inv.id}": 8.0},
    ))
    await db.commit()
    return anlage, inv


# ══ III-1a · OFFEN — Tagesreset, Stand NACH dem Reset gelesen ═══════════════

async def test_iii1a_tagesreset_stand_nach_reset(db):
    """**OFFEN (P4/W-11), Variante (a).**

    Der Zähler wird um Mitternacht auf 0 gesetzt; beide Randstände werden
    **nach** dem Reset gelesen. Am Tag selbst sind real 4,5 kWh geflossen.

    SOLL §3.1: *„Ein Zähler mit Tages-Reset wird erkannt und abgelehnt, statt
    still falsche Werte zu erzeugen."* Erwartung nach dem Bau: **kein Eintrag**
    für dieses Gerät (P4 — keine Aussage statt einer 0).

    Heute: ``5.0 − 5.0 = 0.0`` … hier ``0.0 − 0.0`` — der Wert **0,0 wird
    geschrieben**, obwohl die Funktion im eigenen Docstring „keine Aussage statt
    einer 0" für sich reklamiert. Übersprungen wird nur ``None``.
    """
    assert "P4/W-11" in REGELN_OFFEN
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(0.0, 0.0), feld="betriebsart_strom_kuehlen_kwh",
    )
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )

    assert werte == {str(inv.id): {"betriebsart_strom_kuehlen_kwh": 0.0}}


# ══ III-1b · OFFEN — Tagesreset, Stand VOR dem Reset gelesen ════════════════

async def test_iii1b_tagesreset_stand_vor_reset(db):
    """**OFFEN (P4/W-11), Variante (b).**

    Derselbe Zähler, andere Auslegung des Mitternachts-Snapshots: Der Stand um
    00:00 ist der **Tagesendwert** des Vortags (5,0), der Folgetag beginnt wieder
    bei ~0.

    Das Delta ist negativ, und die vorhandene Tagesreset-Heuristik greift:
    ``s1 < 0.5 and s0 > 0.5 ⇒ return max(0.0, s1)`` — also wieder **0**.

    ⭐ **Beide Auslegungen führen zu 0, und das ist der Kern des Befundes.** Die
    Heuristik ist für den **Stunden**-Slot über Mitternacht gebaut und dort
    richtig; am **Tagesrand** kann sie nichts retten, weil der ganze Tag zwischen
    zwei Resets liegt. Erwartung nach dem Bau: kein Eintrag (P4).
    """
    assert "P4/W-11" in REGELN_OFFEN
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(5.0, 0.0), feld="betriebsart_strom_kuehlen_kwh",
    )
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )

    assert werte == {str(inv.id): {"betriebsart_strom_kuehlen_kwh": 0.0}}


# ══ III-1c · ERFÜLLT — der kumulative Zähler bleibt unberührt ═══════════════

async def test_iii1c_kumulativer_zaehler_traegt_weiter(db):
    """**ERFÜLLT.** Ein normal hochzählender Zähler liefert seinen Tageswert.

    ⚠ **Diese Gegenprobe gehört zwingend dazu.** Sie hält fest, was die Lösung
    von III-1a/b **nicht** kaputt machen darf: Wer einen echten kumulativen
    Zähler hat, bekommt weiterhin seine Differenz. Eine Reset-Erkennung, die
    diesen Fall mitnimmt, wäre teurer als der Befund.
    """
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(100.0, 104.5), feld="betriebsart_strom_kuehlen_kwh",
    )
    werte = await get_betriebsart_strom_tageswerte(
        db, anlage, {str(inv.id): inv}, DATUM,
    )

    assert werte == {str(inv.id): {"betriebsart_strom_kuehlen_kwh": 4.5}}


# ══ III-1d · OFFEN — die 0 erreicht die Anzeige als Aufteilung ══════════════

async def test_iii1d_tagesreset_erzeugt_alles_nicht_aufgeteilt(db):
    """**OFFEN (P4/W-11).** Was der Anwender von der 0 aus III-1a sieht.

    Die Route stuft die Zeile als **gemessen** ein (ein Betriebsart-Zähler ist
    zugeordnet) und rechnet die Aufteilung: 8 kWh Bezug − 0 gemessen ⇒ **alles
    unter „nicht aufgeteilt"**.

    Erwartung nach dem Bau: Ohne verwertbaren Zähler ist die Zeile **nicht
    gemessen** — es gibt keine Aufteilung und keinen 100-%-Balken, sondern den
    Grund.

    ⭐ **Genau dieses Bild hat dietmar1968 am 25.08. gezeigt** (Tagesansicht:
    *Heizen 0 · Kühlen 0 · Nicht aufgeteilt 3 kWh · 100 %*). Er erklärte es mit
    *„die Anlage war heute nicht in Betrieb"* — der Pfad hätte bei vollem Betrieb
    dasselbe geliefert. **Ein Melder kann eine stille 0 nicht von einer echten
    unterscheiden; deshalb darf sie gar nicht erst entstehen.**
    """
    assert "P4/W-11" in REGELN_OFFEN
    from backend.api.routes.energie_profil.views import get_tag_detail

    anlage, inv = await _anlage_mit_tagesreset_zaehler(
        db, randwerte=(0.0, 0.0), feld="betriebsart_strom_kuehlen_kwh",
    )
    resp = await get_tag_detail(anlage.id, DATUM, db)

    assert resp.wp_modus_gemessen is True
    assert resp.wp_modus_strom_kuehlen_kwh == 0.0
    assert resp.wp_modus_nicht_aufgeteilt_kwh == 8.0


# ══ III-2 · OFFEN — S3: der Tag kennt seine eigene Wärme-Summe nicht ════════

def test_iii2_tag_hat_kein_feld_fuer_waerme_gesamt():
    """**OFFEN (S3/W-9).**

    Der Tagespfad liefert die **Summanden** ``wp_heizung_kwh`` und
    ``wp_warmwasser_kwh``, aber kein Feld für die Wärme **gesamt** — obwohl deren
    Summe genau das wäre. Die Monatssicht hat ``wp_waerme_kwh``.

    SOLL §3.3/S3: *„Eine Sicht, die weniger zeigt als die Nachbarsicht, sagt
    warum."* Erwartung nach dem Bau: entweder die Größe (sie ist ableitbar) oder
    der Grund — **nie ein „—" ohne Begründung**.

    **Melder rapahl (#202):** Monat *JAZ 4,07 · 110 kWh Wärme · +9 €*, am selben
    Tag im Tagesblock dreimal „—": *„Keine Wärmewertangaben und keine
    Verbrauchsbalken."* Die Zahlen sind beide richtig; unerklärt ist der
    Unterschied.

    ⚠ **Diese Probe prüft das Schema, nicht einen Wert** — der Befund ist ein
    fehlendes **Feld**, und ein Wert kann nicht fehlen, wo es kein Feld gibt.
    """
    assert "S3/W-9" in REGELN_OFFEN
    from backend.api.routes.energie_profil._shared import TagDetailResponse

    felder = set(TagDetailResponse.model_fields)

    assert "wp_heizung_kwh" in felder
    assert "wp_warmwasser_kwh" in felder
    assert "wp_waerme_kwh" not in felder


def test_iii2b_monat_hat_das_feld():
    """**ERFÜLLT.** Die Nachbarsicht trägt die Größe — der Beleg, dass III-2 eine
    Lücke ist und keine bewusste Abwesenheit.

    Ohne diese Gegenprobe wäre „der Tag hat das Feld nicht" nur eine Beobachtung.
    Erst dass **der Monat es hat**, macht daraus die S3-Frage: *Warum zeigt die
    eine Sicht weniger als die andere, ohne es zu sagen?*
    """
    from backend.api.routes.aktueller_monat import AktuellerMonatResponse

    assert "wp_waerme_kwh" in set(AktuellerMonatResponse.model_fields)
