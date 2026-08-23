"""Shared loading, symbol caching, and status handling for native bindings."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
DISABLE_ENV = "TOUHOU_DISABLE_NATIVE_PLANNER"

_LIBRARY: Any | None = None
_LOAD_ERROR: OSError | None = None
_FUNCTION_CACHE: dict[str, Any] = {}
_FUNCTION_GROUP_CACHE: dict[str, tuple[Any, ...]] = {}


def _windows_build_directory(pointer_size: int | None = None) -> str:
    """Select the native DLL architecture of the current Python process."""

    size = ctypes.sizeof(ctypes.c_void_p) if pointer_size is None else pointer_size
    if size == 4:
        return "windows-x86"
    if size == 8:
        return "windows-x86_64"
    raise RuntimeError(f"unsupported Windows pointer size: {size}")


def library_path() -> Path:
    """Return the platform-specific native planner library path."""

    if os.name == "nt":
        return (
            ROOT
            / "native"
            / "build"
            / _windows_build_directory()
            / "touhou_viability.dll"
        )
    return (
        ROOT
        / "native"
        / "build"
        / "linux-x86_64"
        / "libtouhou_viability.so"
    )


def load_library():
    """Load the optional native library while preserving legacy retry rules."""

    global _LIBRARY, _LOAD_ERROR
    if _LIBRARY is not None or _LOAD_ERROR is not None:
        return _LIBRARY
    if os.environ.get(DISABLE_ENV) == "1":
        return None
    try:
        _LIBRARY = ctypes.CDLL(str(library_path()))
    except OSError as error:
        _LOAD_ERROR = error
        return None
    return _LIBRARY


def available() -> bool:
    """Return whether the optional native planner library can be loaded."""

    return load_library() is not None


def cached_function(key: str):
    """Return one configured function previously stored under ``key``."""

    return _FUNCTION_CACHE.get(key)


def cache_function(key: str, function):
    """Store and return one successfully configured function."""

    _FUNCTION_CACHE[key] = function
    return function


def cached_function_group(key: str) -> tuple[Any, ...] | None:
    """Return one atomically configured function group."""

    return _FUNCTION_GROUP_CACHE.get(key)


def cache_function_group(
    key: str,
    functions: tuple[Any, ...],
) -> tuple[Any, ...]:
    """Store and return one complete configured function group."""

    _FUNCTION_GROUP_CACHE[key] = functions
    return functions


def load_function(
    symbol: str,
    *,
    argtypes: list[Any],
    restype: Any,
    optional: bool,
):
    """Load and cache one configured C function.

    Missing optional symbols are deliberately not cached. This retains the
    legacy behavior where a later library replacement can make them visible.
    """

    cached = _FUNCTION_CACHE.get(symbol)
    if cached is not None:
        return cached
    library = load_library()
    if library is None:
        return None
    try:
        function = getattr(library, symbol)
    except AttributeError:
        if optional:
            return None
        raise
    function.argtypes = argtypes
    function.restype = restype
    _FUNCTION_CACHE[symbol] = function
    return function


def load_function_group(
    key: str,
    specifications: Iterable[
        tuple[str, list[Any], Any]
    ],
    *,
    optional: bool,
) -> tuple[Any, ...] | None:
    """Load and atomically cache a configured group of C functions."""

    cached = _FUNCTION_GROUP_CACHE.get(key)
    if cached is not None:
        return cached
    library = load_library()
    if library is None:
        return None
    functions: list[Any] = []
    try:
        for symbol, argtypes, restype in specifications:
            function = getattr(library, symbol)
            function.argtypes = argtypes
            function.restype = restype
            functions.append(function)
    except AttributeError:
        if optional:
            return None
        raise
    loaded = tuple(functions)
    _FUNCTION_GROUP_CACHE[key] = loaded
    return loaded


class PipelineNativeCancelledError(RuntimeError):
    """A native workspace was invalidated while expanding."""


class PipelineNativeDeadlineError(RuntimeError):
    """A native workspace query exceeded its cooperative deadline."""


def raise_pipeline_result(operation: str, result: int) -> None:
    """Raise the historical exception for a nonzero pipeline status."""

    if result == 5:
        raise PipelineNativeCancelledError(
            f"native pipeline workspace {operation} was cancelled"
        )
    if result == 6:
        raise PipelineNativeDeadlineError(
            f"native pipeline workspace {operation} exceeded its deadline"
        )
    raise RuntimeError(
        f"native pipeline workspace {operation} returned {result}"
    )
