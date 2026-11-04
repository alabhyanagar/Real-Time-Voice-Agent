"""Protocol version constants and compatibility helpers."""
from typing import Final

PROTOCOL_VERSION: Final[str] = "1.0"
SUPPORTED_PROTOCOL_MAJOR: Final[int] = 1

def is_supported_version(version: str) -> bool:
    try:
        return int(version.split(".", 1)[0]) == SUPPORTED_PROTOCOL_MAJOR
    except (AttributeError, ValueError, IndexError):
        return False
