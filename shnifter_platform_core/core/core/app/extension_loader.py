# Generated: 2025-07-04T09:50:40.230150
# Target: Shnifter Trader Platform with PySide6 and LLM integration
# Python Version: 3.13.2+

"""Extension Loader."""

from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from importlib_metadata import EntryPoint, EntryPoints, entry_points
from shnifter_core.app.model.abstract.singleton import SingletonMeta
from shnifter_core.app.model.extension import Extension

if TYPE_CHECKING:
    from shnifter_core.app.router import Router
    from shnifter_core.provider.abstract.provider import Provider


class ShnifterGroups(Enum):
    """Shnifter Extension Groups."""

    core = "shnifter_core_extension"
    provider = "shnifter_provider_extension"
    shnifterject = "shnifter_shnifterject_extension"

    @staticmethod
    def groups() -> List[str]:
        """Return the ShnifterGroups."""
        return [
            ShnifterGroups.core.value,
            ShnifterGroups.provider.value,
            ShnifterGroups.shnifterject.value,
        ]


class ExtensionLoader(metaclass=SingletonMeta):
    """Extension loader class."""

    def __init__(
        self,
    ) -> None:
        """Initialize the extension loader."""
        self._shnifterject_entry_points: EntryPoints = self._sorted_entry_points(
            group=ShnifterGroups.shnifterject.value
        )
        self._core_entry_points: EntryPoints = self._sorted_entry_points(
            group=ShnifterGroups.core.value
        )
        self._provider_entry_points: EntryPoints = self._sorted_entry_points(
            group=ShnifterGroups.provider.value
        )
        self._shnifterject_objects: Dict[str, Extension] = {}
        self._core_objects: Dict[str, Router] = {}
        self._provider_objects: Dict[str, Provider] = {}

    @property
    def shnifterject_entry_points(self) -> EntryPoints:
        """Return the shnifterject entry points."""
        return self._shnifterject_entry_points

    @property
    def core_entry_points(self) -> EntryPoints:
        """Return the core entry points."""
        return self._core_entry_points

    @property
    def provider_entry_points(self) -> EntryPoints:
        """Return the provider entry points."""
        return self._provider_entry_points

    @property
    def entry_points(self) -> List[EntryPoints]:
        """Return the entry points."""
        return [
            self._core_entry_points,
            self._provider_entry_points,
            self._shnifterject_entry_points,
        ]

    @staticmethod
    def _get_entry_point(
        entry_points_: EntryPoints, ext_name: str
    ) -> Optional[EntryPoint]:
        """Given an extension name and a list of entry points, return the corresponding entry point."""
        return next((ep for ep in entry_points_ if ep.name == ext_name), None)

    def get_shnifterject_entry_point(self, ext_name: str) -> Optional[EntryPoint]:
        """Given an extension name, return the corresponding entry point."""
        return self._get_entry_point(self._shnifterject_entry_points, ext_name)

    def get_core_entry_point(self, ext_name: str) -> Optional[EntryPoint]:
        """Given an extension name, return the corresponding entry point."""
        return self._get_entry_point(self._core_entry_points, ext_name)

    def get_provider_entry_point(self, ext_name: str) -> Optional[EntryPoint]:
        """Given an extension name, return the corresponding entry point."""
        return self._get_entry_point(self._provider_entry_points, ext_name)

    @property
    @lru_cache
    def shnifterject_objects(self) -> Dict[str, Extension]:
        """Return a dict of shnifterject extension objects."""
        self._shnifterject_objects = self._load_entry_points(
            self._shnifterject_entry_points, ShnifterGroups.shnifterject
        )
        return self._shnifterject_objects

    @property
    @lru_cache
    def core_objects(self) -> Dict[str, "Router"]:
        """Return a dict of core extension objects."""
        self._core_objects = self._load_entry_points(
            self._core_entry_points, ShnifterGroups.core
        )
        return self._core_objects

    @property
    @lru_cache
    def provider_objects(self) -> Dict[str, "Provider"]:
        """Return a dict of provider extension objects."""
        self._provider_objects = self._load_entry_points(
            self._provider_entry_points, ShnifterGroups.provider
        )
        return self._provider_objects

    @staticmethod
    def _sorted_entry_points(group: str) -> EntryPoints:
        """Return a sorted dictionary of entry points."""
        return sorted(entry_points(group=group))  # type: ignore

    def _load_entry_points(
        self, entry_points_: EntryPoints, group: ShnifterGroups
    ) -> Dict[str, Any]:
        """Return a dict of objects matching the entry points."""

        def load_shnifterject(eps: EntryPoints) -> Dict[str, Extension]:
            """
            Return a dictionary of shnifterject objects.

            Keys are entry point names and values are instances of the Extension class.
            """
            return {
                ep.name: entry
                for ep in eps
                if isinstance((entry := ep.load()), Extension)
            }

        def load_core(eps: EntryPoints) -> Dict[str, "Router"]:
            """Return a dictionary of core objects."""
            # pylint: disable=import-outside-toplevel
            from shnifter_core.app.router import Router

            return {
                ep.name: entry for ep in eps if isinstance((entry := ep.load()), Router)
            }

        def load_provider(eps: EntryPoints) -> Dict[str, "Provider"]:
            """
            Return a dictionary of provider objects.

            Keys are entry point names and values are instances of the Provider class.
            """
            # pylint: disable=import-outside-toplevel
            from shnifter_core.provider.abstract.provider import Provider

            entries: dict = {}
            for ep in eps:
                try:
                    if isinstance((entry := ep.load()), Provider):
                        entries[ep.name] = entry
                except ModuleNotFoundError:
                    continue
            return entries

        func = {
            ShnifterGroups.shnifterject: load_shnifterject,
            ShnifterGroups.core: load_core,
            ShnifterGroups.provider: load_provider,
        }
        return func[group](entry_points_)  # type: ignore
