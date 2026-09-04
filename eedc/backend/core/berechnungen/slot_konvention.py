"""
Kanonische Stunden-Slot-Konvention für PV-Prognosequellen (Issue #144, #297).

**Backward-Konvention (#144):**
    Slot ``h`` = Energie im Intervall ``[h-1, h)``.
    Slot 0  = Energie ``[Vortag 23:00, Heute 00:00)``
    Slot 23 = Energie ``[Heute 22:00, Heute 23:00)``

Industriestandard (HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber).

Dieses Modul ist die **Single Source of Truth** dafür, wie die verschiedenen
Prognosequellen ihre Roh-Zeitmarker auf Backward-Slots abbilden. Die IST-Seite
hat **zwei** Pfade, die beide dasselbe Backward-Raster liefern müssen:
  - Snapshot-Diffs: ``services/snapshot/boundary_range.py``
    (``BoundaryRange.for_hourly_slots`` → Slot ``h = snap[h] − snap[h-1]``).
  - HA-LTS direkt: ``ha_statistics_service.get_hourly_kwh_deltas_for_day`` via
    ``lts_boundary_index`` (siehe unten).
Alle vier (OpenMeteo, Solcast, IST-Snapshot, IST-LTS) müssen ein und dasselbe
physische Intervall in denselben Slot legen — Symmetrie-Test
``tests/test_slot_konvention_quellen.py``.

✅ **Die FÜNFTE Bahn — der Leistungspfad — liegt seit 2026-09-04 backward**
(N-382, gemeldet als #405 von BMeyendriesch). Er speist
``TagesEnergieProfil.komponenten``: ``live_tagesverlauf_service`` beschriftet
jeden Punkt mit dem **Slot-BEGINN** (``{h_start.hour}:{h_start.minute}``, Raster
``h_start <= p < h_end``), ein Punkt „05:00" deckt also ``[05:00, 06:00)``.
``energie_profil/aggregator.py`` bucketet ihn deshalb in **Slot 6**.

⛔ **Bis dahin bucketete er nach dem rohen Stundenlabel.** Zeile ``h`` trug damit
im JSON ``[h, h+1)`` — während die Spalte ``pv_kw`` derselben Zeile aus dem
Zählerpfad kommt und ``[h-1, h)`` meint. **Eine Zeile, zwei verschiedene
Stunden.** Über 24 Slots hebt sich das auf (Tagessummen, Monat, ROI blieben
unauffällig), pro Stunde nicht: ``TagVerlaufChart`` subtrahierte quer über den
Versatz und zeichnete daraus ein Phantom-Band „PV (übrige)" bzw. — auf
steigender Kurve — einen Quellenstapel **über** der Erzeugung. An einer echten
Anlage mit genau EINEM PV-Erzeuger gemessen: 5,09 kWh Überhang an einem Tag,
in einer Stunde 130 %.

**Zwei Kanten gehören zur Umstellung:**

* **Slot 0** trägt ``[Vortag 23:00, 00:00)`` und kann deshalb nicht aus dem
  eigenen Tag kommen. ``get_tagesverlauf(mit_vortagsrand=True)`` macht dafür das
  bestehende Abruf-Fenster eine Stunde weiter auf — **kein zweiter Tagesabruf**,
  der Scheduler-Job ``energie_profil_heute`` läuft alle 15 Minuten. Die Punkte
  kommen **getrennt** unter ``"vortagsrand"`` zurück: ein Punkt trägt nur seine
  Uhrzeit, „23:00" von gestern und von heute wären in einer Liste nicht mehr
  unterscheidbar. Fehlt der Rand (erster Tag, HA-Historie zu kurz), wird die
  Zeile trotzdem geschrieben — nur ohne ``komponenten``, damit sie nicht auch
  ihre Zähler-, Wetter- und Preiswerte verliert.
* **Bucket 23** des Tages gehört in Slot 0 des **Folgetags** und fällt im
  eigenen Tag weg.

Gepinnt in ``tests/test_slot_konvention_leistungspfad.py`` (vier Proben: der
gemeinsame Slot, der Vortagsrand, die letzte Stunde, die Zeile 0 ohne Rand).

----------------------------------------------------------------------------
⚠️  DREI Bahnen derselben Zeile liegen WEITERHIN forward — N-387
----------------------------------------------------------------------------
Bei der Inventur zu N-382 (2026-09-04) über **alle** Größen der
``TagesEnergieProfil``-Zeile gemessen. Backward und damit richtig liegen: der
Zählerpfad (alle ``*_kw``-Spalten), ``wp_starts_anzahl`` /
``wp_betriebsstunden`` (``get_hourly_counter_sum_by_feld``), das Wetter
(OpenMeteo preceding-hour, s. unten) und — seit N-382 —
``komponenten`` und ``betriebsmodus_je_wp``. **Forward liegen noch:**

* ``soc_prozent`` / ``soc_je_speicher`` — ``ha_statistics_service
  .get_hourly_sensor_data`` nimmt ``datetime.fromtimestamp(start_ts).hour``,
  also den Perioden-BEGINN; der History-Fallback in
  ``energie_profil/_helpers.py`` bucketet ``h_start <= p < h_end``.
* ``strompreis_cent`` — ``get_hourly_mean_for_day`` (derselbe ``start_ts``)
  bzw. derselbe History-Fallback.
* ``boersenpreis_cent`` — ``strompreis_markt_service`` nimmt
  ``lokal.hour`` aus dem ``start_timestamp`` der aWATTar-Antwort.

**Wen das trifft, gemessen:** ``speicher_sizing_service`` und
``speicher_potential_service`` stellen den SoC neben die Backward-Spalten
derselben Zeile; ``speicher_wirtschaftlichkeit`` multipliziert die
**Netz-Ladung** einer Stunde (backward) mit dem **Preis** derselben Zeile
(forward) — der effektive Ladepreis eines Speichers rechnet damit auf einem
dynamischen Tarif mit dem Preis der Nachbarstunde.

⛔ **Sie sind bewusst NICHT mit N-382 gebaut worden.** Ein Paket, das fünf
Bahnen gleichzeitig verschiebt, hat keine saubere Abnahme, und jede der drei
trägt eine eigene Sachfrage: ein Preis ist keine Energiemenge, ein Ladestand ist
ein Zustand und keine Menge. ``betriebsmodus_je_wp`` musste dagegen **mit** —
``energie_profil/modus_split_monat.py`` paart ihn mit ``komponenten``
**derselben Zeile**, ein Alleingang des Leistungspfads hätte die Aufteilung
Heizen/Kühlen/Warmwasser neu falsch gemacht statt alt richtig zu lassen.

⚑ **Warum das hier steht und nicht nur im Fundregister:** Der Absatz darunter
zieht aus demselben Vorfall die Lehre *„jeden Parallelpfad pinnen"* — und genau
dieser Parallelpfad war beim Bau von ``c71b0f08`` nicht mitgenommen worden. Eine
Lehre, die den nächsten Fall nicht fängt, gehört an die Stelle, an der er
entsteht. **Deshalb stehen die drei offenen Bahnen hier namentlich:** N-382
wurde gefunden, weil jemand EINE Bahn nannte — nicht, weil jemand alle zählte.

⚠️ Historie: der LTS-Pfad labelte bis v3.3x FORWARD (Slot ``h = [h, h+1)``),
während alle anderen backward waren → IST erschien im Stundenvergleich
1 h zu früh (Rainer/Gernot, 2026-06-04). Der Symmetrie-Test deckte damals nur
den Snapshot-Pfad ab und blieb grün — Lehre: jeden Parallelpfad pinnen.

----------------------------------------------------------------------------
⚠️  OpenMeteo wird NICHT verschoben — und das ist KEIN Bug (Issue #297).
----------------------------------------------------------------------------
OpenMeteos stündliche Strahlungsvariablen (``global_tilted_irradiance``,
``shortwave_radiation``, …) sind in der Default-Form ein **Mittel der
vorangehenden Stunde**: der Wert am Zeitstempel ``T`` deckt das Intervall
``[T-1, T)`` ab (empirisch verifiziert 2026-06-04: bei Sonnenaufgang 04:46
ist der Wert@05:00 = 0 und erst der Wert@06:00 > 0; Trapez-Rekonstruktion
gegen die ``*_instant``-Variante bestätigt das). Damit IST der OpenMeteo-Wert
am Index ``h`` bereits der Backward-Slot ``h`` — ``openmeteo_preceding_hour_slot``
ist deshalb die **Identität**.

Ein naiver „+1-Shift" auf OpenMeteo (wie in #297 zunächst vermutet) würde die
Quelle eine Stunde zu spät einsortieren und genau den Versatz ERZEUGEN, den er
zu beheben vorgibt. Wer hier etwas verschiebt, verletzt den Symmetrie-Test.

Solcast dagegen liefert periodenbeginnende Buckets (HA-Sensor: ``period_start``)
bzw. periodenendende Marker (API: ``period_end``) und MUSS auf das Stunden-Ende
gerundet werden — siehe ``backward_slot_aus_period_start`` /
``backward_slot_aus_period_end``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


def openmeteo_preceding_hour_slot(stunde: int) -> int:
    """OpenMeteo preceding-hour-Wert@``stunde`` = Intervall ``[stunde-1, stunde)``.

    Das IST schon der Backward-Slot ``stunde`` → Identität, **kein Shift**.
    Existiert als benannte Funktion, damit der „kein Shift"-Vertrag im Code
    sichtbar und im Symmetrie-Test prüfbar ist (Issue #297).
    """
    return stunde


def lts_boundary_index(start_ts_dt: datetime, datum: date) -> int:
    """HA-LTS-Statistics-Row ``start_ts`` → Backward-Boundary-Index.

    HA legt bei ``start_ts=H`` den Counter-Stand am **Ende** der Periode ab,
    also ``Zähler(H+1):00`` (empirisch belegt 2026-06-04 gegen Live-HA:
    ``state@start_ts=H`` = Zählerstand um ``H+1``). Mit ``Zähler(k)`` := Counter
    um ``k:00`` ist ``Zähler(k) = sum @ start_ts=(k-1)``.

    Diese Funktion liefert für eine Statistics-Row den Boundary-Index ``k``
    (Stunden-Offset ab ``00:00`` des ``datum``), unter dem ihr Counter-Wert als
    ``Zähler(k)`` einzusortieren ist:

      ``start_ts = 22:00 Vortag`` → ``Zähler(23:00 Vortag)`` → ``k = -1``
      ``start_ts = 23:00 Vortag`` → ``Zähler(00:00 heute)``  → ``k =  0``
      ``start_ts = 05:00 heute``  → ``Zähler(06:00 heute)``  → ``k =  6``
      ``start_ts = 22:00 heute``  → ``Zähler(23:00 heute)``  → ``k = 23``

    Der Backward-Slot ``h`` (Energie ``[h-1, h)``) ist dann
    ``Zähler(h) − Zähler(h-1) = boundary[h] − boundary[h-1]`` — dasselbe
    Slot-Raster wie ``BoundaryRange.for_hourly_slots`` und die Prognosequellen
    (Symmetrie-Test ``tests/test_slot_konvention_quellen.py``).

    Wall-clock-Arithmetik (Tag-Offset × 24 + Stunde) statt Sekunden-Differenz —
    DST-robust an den Umstellungstagen.
    """
    boundary_dt = start_ts_dt + timedelta(hours=1)
    return (boundary_dt.date() - datum).days * 24 + boundary_dt.hour


def backward_slot_aus_period_start(period_start: datetime) -> tuple[date, int]:
    """Backward-Slot für ein **periodenbeginnendes** Bucket ``[period_start, …)``.

    Für Buckets von höchstens einer Stunde Länge (Solcast HA-Sensor: 30-Min)
    liegt das Intervall-Ende in der nächsten vollen Stunde → Slot =
    ``floor(period_start) + 1h``.

      ``period_start = N:00`` → Bucket ``[N:00, N:30)`` → Slot ``N+1``
      ``period_start = N:30`` → Bucket ``[N:30, N+1:00)`` → Slot ``N+1``

    Am Tagesübergang (``period_start = 23:xx``) wandert der Slot korrekt in
    Slot 0 des Folgetags — ``slot_date`` nimmt das mit.
    """
    marker = period_start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return marker.date(), marker.hour


def backward_slot_aus_period_end(period_end: datetime) -> tuple[date, int]:
    """Backward-Slot für einen **periodenendenden** Marker (Solcast API).

      ``period_end = N:00`` → Bucket ``[…, N:00)``   → Slot ``N``
      ``period_end = N:30`` → Bucket ``[…, N:30)``   → Slot ``N+1`` (aufgerundet)

    Ein Marker exakt auf der vollen Stunde markiert das Ende des Slots dieser
    Stunde; alles dazwischen rundet auf die nächste volle Stunde auf.
    """
    if period_end.minute == 0 and period_end.second == 0 and period_end.microsecond == 0:
        marker = period_end
    else:
        marker = period_end.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return marker.date(), marker.hour


def leistungspfad_slot(punkt_stunde: int) -> int | None:
    """Punkt-Label des Leistungspfads (Slot-BEGINN) → Backward-Slot.

    ``live_tagesverlauf_service`` beschriftet jeden Punkt mit dem **Beginn**
    seines Rasters (``h_start <= p < h_end``); ein Punkt „05:00" deckt also
    ``[05:00, 06:00)`` und gehört nach der Backward-Konvention in Slot **6**.

    ``None`` für ``23`` und höher: Bucket 23 des Tages ist ``[23:00, 24:00)``
    und damit Slot 0 des **Folgetags** — im eigenen Tag fällt er weg (er kommt
    dort über ``vortagsrand`` an).

    ⚑ **Warum das eine benannte Funktion ist:** Die Regel entstand mit N-382
    inline in ``energie_profil/aggregator.py``. Seit dem Archiv-Nachzug (N-388)
    hat sie einen **zweiten** Leser — dessen Vorflug muss die Stundenzahl einer
    Kurve vorher genauso zählen, wie der Aggregator sie nachher schreibt
    (``TagesZusammenfassung.stunden_verfuegbar``). Zwei Nachbauten derselben
    Bucket-Regel wären genau die Klasse, die N-382 überhaupt erst erzeugt hat.
    """
    if punkt_stunde >= 23:
        return None
    return punkt_stunde + 1
