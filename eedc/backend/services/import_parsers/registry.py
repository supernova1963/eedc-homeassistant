"""
Parser-Registry: Verwaltet alle verfügbaren Portal-Export-Parser.

Parser registrieren sich über den @register_parser Decorator.
"""

from typing import Optional

from .base import PortalExportParser, ParserInfo

_PARSERS: dict[str, type[PortalExportParser]] = {}


def register_parser(cls: type[PortalExportParser]) -> type[PortalExportParser]:
    """Decorator zum Registrieren eines Parsers."""
    instance = cls()
    parser_info = instance.info()
    _PARSERS[parser_info.id] = cls
    return cls


def list_parsers() -> list[ParserInfo]:
    """Alle verfügbaren Parser mit Metadaten."""
    return [cls().info() for cls in _PARSERS.values()]


def get_parser(parser_id: str) -> PortalExportParser:
    """Parser nach ID instanziieren."""
    if parser_id not in _PARSERS:
        raise ValueError(f"Unbekannter Parser: {parser_id}")
    return _PARSERS[parser_id]()


def auto_detect_parser(content: str, filename: str) -> Optional[PortalExportParser]:
    """Versucht automatisch den passenden Parser zu finden."""
    for cls in _PARSERS.values():
        parser = cls()
        if parser.can_parse(content, filename):
            return parser
    return None
