"""Routing rules for the initial tool-free graph."""
from typing import Literal

GraphRoute = Literal["load_context", "call_model", "stream_response", "finalize_turn", "end"]


def next_after_context(_: dict) -> GraphRoute:
    return "call_model"


def next_after_model(_: dict) -> GraphRoute:
    return "stream_response"


def next_after_stream(_: dict) -> GraphRoute:
    return "finalize_turn"
