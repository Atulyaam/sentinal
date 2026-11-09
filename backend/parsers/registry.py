"""Parser registry for Project Sentinel."""

from typing import Dict, List, Optional, Type

from backend.parsers.auth_csv import AuthCsvParser
from backend.parsers.base import BaseParser
from backend.parsers.generic_jsonl import GenericJsonlParser
from backend.parsers.web_access_csv import WebAccessCsvParser


_PARSER_CLASSES: Dict[str, Type[BaseParser]] = {
    GenericJsonlParser.parser_id: GenericJsonlParser,
    AuthCsvParser.parser_id: AuthCsvParser,
    WebAccessCsvParser.parser_id: WebAccessCsvParser,
}


def get_parser(parser_id: str) -> Optional[BaseParser]:
    """Retrieve an instantiated parser instance by profile identifier."""
    parser_cls = _PARSER_CLASSES.get(parser_id.strip())
    if parser_cls is None:
        return None
    return parser_cls()


def list_available_parsers() -> List[Dict[str, str]]:
    """List metadata for all registered parser profiles."""
    parsers = []
    for parser_cls in _PARSER_CLASSES.values():
        instance = parser_cls()
        parsers.append(
            {
                "id": instance.parser_id,
                "name": instance.display_name,
                "version": instance.parser_version,
                "description": instance.description,
            }
        )
    return parsers

