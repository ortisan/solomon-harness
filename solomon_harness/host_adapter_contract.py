"""Typed port shared by the native Claude, AGY, and Codex adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Protocol, runtime_checkable

if TYPE_CHECKING:
    from solomon_harness.host_adapter_common import (
        HostCompileContext,
        HostInspectionContext,
    )


@dataclass(frozen=True)
class HostInspection:
    """Host-local discovery result returned to the neutral facade."""

    capability_states: Mapping[str, str]
    specialists: tuple[str, ...]
    workflows: tuple[str, ...]


@runtime_checkable
class NativeHostAdapter(Protocol):
    """Port implemented independently by each native host integration."""

    name: str

    def compile(self, context: HostCompileContext) -> None:
        """Render and merge only this host's discovery surfaces."""

    def inspect(self, context: HostInspectionContext) -> HostInspection:
        """Inspect this host without reading another host's surfaces."""
