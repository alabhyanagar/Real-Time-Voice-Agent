"""Small deterministic tools suitable for the first tool-calling milestone."""

from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool


@tool
def calculate(
    operation: Literal["add", "subtract", "multiply", "divide"],
    left: float,
    right: float,
) -> str:
    """Perform one basic arithmetic operation on two numbers."""
    if operation == "add":
        result = left + right
    elif operation == "subtract":
        result = left - right
    elif operation == "multiply":
        result = left * right
    elif operation == "divide":
        if right == 0:
            return "Error: division by zero is not allowed."
        result = left / right
    else:  # Literal validation prevents this for model-generated calls.
        return "Error: unsupported operation."
    return f"{result:g}"


@tool
def get_current_time(timezone_name: str = "UTC") -> str:
    """Return the current time in an IANA timezone such as Asia/Kolkata or UTC."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return f"Error: unknown timezone '{timezone_name}'. Use an IANA timezone name."
    return datetime.now(timezone.utc).astimezone(zone).isoformat(timespec="seconds")
