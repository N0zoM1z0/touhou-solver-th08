"""Small fail-closed ELF symbol helpers for the pinned Linux runtime."""

from __future__ import annotations

from pathlib import Path
import subprocess


def resolve_defined_symbol(executable: Path | str, symbol: str) -> int:
    """Return the unique address of one defined symbol from ``nm -P``."""

    if not symbol:
        raise ValueError("ELF symbol name cannot be empty")
    path = Path(executable).resolve(strict=True)
    completed = subprocess.run(
        ["nm", "-P", "--defined-only", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    matches = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] == symbol:
            matches.append(int(fields[2], 16))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one defined ELF symbol {symbol}, found {len(matches)}"
        )
    return matches[0]


__all__ = ("resolve_defined_symbol",)
