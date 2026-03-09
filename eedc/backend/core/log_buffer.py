"""
In-Memory Log Ring Buffer.

Custom logging.Handler der die letzten N Log-Einträge in einer deque speichert.
Thread-safe. Wird beim App-Start an den Root-Logger angehängt.
"""

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class LogEntry:
    """Einzelner Log-Eintrag im Buffer."""
    timestamp: str          # ISO 8601
    level: str              # DEBUG, INFO, WARNING, ERROR, CRITICAL
    logger_name: str        # z.B. "backend.api.routes.connector"
    message: str
    module: str             # Kurzname, z.B. "connector"


class RingBufferHandler(logging.Handler):
    """
    logging.Handler der Records in einer begrenzten deque speichert.

    Thread-safe via deque-Atomizität bei append + Lock für Snapshot-Reads.
    """

    def __init__(self, capacity: int = 500):
        super().__init__()
        self.capacity = capacity
        self._buffer: deque[LogEntry] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        try:
            entry = LogEntry(
                timestamp=datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat(),
                level=record.levelname,
                logger_name=record.name,
                message=self.format(record),
                module=record.module,
            )
            self._buffer.append(entry)
        except Exception:
            self.handleError(record)

    def get_entries(
        self,
        level: Optional[str] = None,
        module: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict]:
        """
        Gefilterte Einträge aus dem Buffer, neueste zuerst.

        Args:
            level: Minimum Log-Level Filter (z.B. "WARNING")
            module: Filter nach logger_name (enthält module)
            search: Case-insensitive Substring-Suche in message
            limit: Maximale Anzahl Einträge
        """
        level_num = getattr(logging, level.upper(), 0) if level else 0

        with self._lock:
            snapshot = list(self._buffer)

        # Neueste zuerst
        snapshot.reverse()

        results = []
        for entry in snapshot:
            if len(results) >= limit:
                break
            if level_num and getattr(logging, entry.level, 0) < level_num:
                continue
            if module and module.lower() not in entry.logger_name.lower():
                continue
            if search and search.lower() not in entry.message.lower():
                continue
            results.append(asdict(entry))

        return results

    def clear(self):
        """Alle Einträge löschen."""
        with self._lock:
            self._buffer.clear()


# Singleton-Instanz
_handler: Optional[RingBufferHandler] = None


def get_log_buffer() -> RingBufferHandler:
    """Singleton Ring Buffer Handler holen/erstellen."""
    global _handler
    if _handler is None:
        _handler = RingBufferHandler(capacity=500)
        _handler.setFormatter(logging.Formatter('%(message)s'))
    return _handler


def setup_log_buffer():
    """
    Ring Buffer Handler an den Root-Logger anhängen.
    Einmal beim App-Start aufrufen (in lifespan).
    """
    handler = get_log_buffer()
    root_logger = logging.getLogger()
    if handler not in root_logger.handlers:
        root_logger.addHandler(handler)
