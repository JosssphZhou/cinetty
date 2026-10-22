"""Pick the driver for a loaded scene.

``driver: rounds`` (the default) is the round-based scene engine (``scene.Scene``).
``driver: events`` plays a board from timed events; ``board:`` names which one.
"""
from __future__ import annotations


def build(spec):
    if spec.get("driver") == "events":
        kind = spec.get("board", "circuit")
        if kind == "workflow":
            from .workflow import WorkflowBoard
            return WorkflowBoard(spec)
        if kind == "phone":
            from .phone import PhoneBoard
            return PhoneBoard(spec)
        from .board import Board
        return Board(spec)
    from .scene import Scene
    return Scene(spec)
