"""Test-Doppel für die Snapshot-Aggregatoren.

Beide Aggregator-Testdateien (`test_snapshot_aggregator_regression.py`,
`test_aggregator_symmetrie.py`) prüfen die **Feld-Auswahl** — welche Sensoren
einer Investition in `komponenten_kwh` einfließen —, nicht den Datenbankzugriff.
Sie stubben deshalb `get_snapshot` und reichten bis 2026-08-26 ein blankes
``MagicMock()`` als Session durch.

Mit der Tagesreset-Erkennung (SOLL §3.1, Befund W-11) fragt der Tagespfad die
Zählerreihe **selbst** ab — und ein ``MagicMock`` ist nicht awaitable. Das
Doppel hier antwortet auf genau diese eine Frage, und zwar mit der ehrlichen
Auskunft *„keine Zwischenstände vorhanden"*.

⚠ **Warum kein `AsyncMock` an Ort und Stelle:** Ein Mock, der auf jede Frage
etwas zurückgibt, hätte die Erkennung stumm mitgetestet — sie hätte immer
„monoton" gemeldet, egal was der Code fragt. Das Doppel steht deshalb an einer
Stelle und sagt im Namen, was es kann.
"""

from __future__ import annotations


class _LeeresErgebnis:
    @staticmethod
    def first():
        """MIN/MAX über eine leere Menge — SQL liefert `(None, None)`.

        ⚠ **Nicht `()`.** Ein ``MagicMock`` liefert hier ein leeres Tupel und
        ließ das Entpacken mit ``ValueError`` auflaufen — dieselbe Stelle, an der
        `test_hourly_kategorie_symmetrie.py` hängen blieb. Ein Doppel muss die
        **Form** der echten Antwort treffen, nicht nur ihre Leere.
        """
        return (None, None)

    @staticmethod
    def all():
        """Für die `mqtt_energy_snapshots`-Abfrage des Snapshot-Readers."""
        return []

    @staticmethod
    def scalar_one_or_none():
        return None


class DbOhneZwischenstaende:
    """Session-Doppel: kennt **keine** Snapshots zwischen den Tagesrändern.

    Damit meldet `reader.zaehler_faellt_im_fenster` ``False`` (nicht
    feststellbar) und der Tagespfad verhält sich wie vor der Erkennung — genau
    die Voraussetzung, unter der die Feld-Auswahl geprüft werden soll.
    """

    async def execute(self, *_args, **_kwargs):
        return _LeeresErgebnis()
