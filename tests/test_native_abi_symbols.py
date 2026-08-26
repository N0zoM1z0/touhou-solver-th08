from __future__ import annotations

import ctypes
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from touhou_control.native.library import load_library


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "native" / "abi_symbols_v1.txt"
ABI_HEADER = ROOT / "native" / "include" / "touhou_native" / "abi.h"


def _manifest_symbols() -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _binary_symbols(*, tool: str, library: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        [tool, "-g", "--defined-only", str(library)],
        check=True,
        capture_output=True,
        text=True,
    )
    symbols: list[str] = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        symbol = fields[-1]
        # i686 PE/COFF's object symbol table prefixes cdecl names with one
        # underscore even though the DLL export table exposes them undecorated.
        if symbol.startswith("_touhou_"):
            symbol = symbol[1:]
        if symbol.startswith("touhou_"):
            symbols.append(symbol)
    return tuple(sorted(symbols))


class NativeAbiSymbolTests(unittest.TestCase):
    def test_legacy_direct_v1_adapters_remain_callable(self) -> None:
        library = load_library()
        if library is None:
            self.skipTest("native library is unavailable")
        create = library.touhou_pipeline_survival_workspace_create_v1
        query = library.touhou_pipeline_survival_workspace_query_v1
        destroy = library.touhou_pipeline_survival_workspace_destroy_v1
        create.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_float,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        create.restype = ctypes.c_int
        query.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint16),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_uint16),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint64),
        ]
        query.restype = ctypes.c_int
        destroy.argtypes = [ctypes.c_void_p]
        destroy.restype = None

        clearance = (ctypes.c_float * 8)(*[1.0] * 8)
        velocity_x = (ctypes.c_double * 2)(0.0, 1.0)
        velocity_y = (ctypes.c_double * 2)(0.0, 0.0)
        delays = (ctypes.c_int * 1)(0)
        handle = ctypes.c_void_p()
        self.assertEqual(
            create(
                clearance,
                2,
                2,
                2,
                0.0,
                1.0,
                0.0,
                1.0,
                velocity_x,
                velocity_y,
                2,
                delays,
                1,
                1,
                0.0,
                1,
                ctypes.byref(handle),
            ),
            0,
        )
        self.assertTrue(handle.value)
        try:
            state_frames = ctypes.c_uint16()
            state_margin = ctypes.c_float()
            action_frames = (ctypes.c_uint16 * 2)()
            action_margins = (ctypes.c_float * 2)()
            best_mask = ctypes.c_uint32()
            stats = (ctypes.c_uint64 * 8)()
            self.assertEqual(
                query(
                    handle,
                    0,
                    0,
                    0,
                    0,
                    -1,
                    None,
                    0,
                    ctypes.byref(state_frames),
                    ctypes.byref(state_margin),
                    action_frames,
                    action_margins,
                    ctypes.byref(best_mask),
                    stats,
                ),
                0,
            )
            self.assertEqual(state_frames.value, 1)
            self.assertEqual(best_mask.value, 0x03)
        finally:
            destroy(handle)

    def test_legacy_belief_v6_query_v2_remains_callable(self) -> None:
        library = load_library()
        if library is None:
            self.skipTest("native library is unavailable")
        create = library.touhou_belief_pipeline_workspace_create_v6
        query = library.touhou_belief_pipeline_workspace_query_v2
        destroy = library.touhou_belief_pipeline_workspace_destroy_v1
        create.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_int,
            ctypes.c_float,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        create.restype = ctypes.c_int
        query.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint16),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_uint16),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint64),
        ]
        query.restype = ctypes.c_int
        destroy.argtypes = [ctypes.c_void_p]
        destroy.restype = None

        clearance = (ctypes.c_float * 8)(*[1.0] * 8)
        velocity_x = (ctypes.c_double * 2)(0.0, 1.0)
        velocity_y = (ctypes.c_double * 2)(0.0, 0.0)
        delays = (ctypes.c_int * 1)(0)
        cadence = (ctypes.c_int * 1)(1)
        handle = ctypes.c_void_p()
        self.assertEqual(
            create(
                clearance,
                2,
                2,
                2,
                0.0,
                1.0,
                0.0,
                1.0,
                velocity_x,
                velocity_y,
                2,
                0x03,
                0,
                0,
                0,
                0,
                delays,
                1,
                cadence,
                1,
                0.0,
                1,
                ctypes.byref(handle),
            ),
            0,
        )
        self.assertTrue(handle.value)
        try:
            state_frames = ctypes.c_uint16()
            state_margin = ctypes.c_float()
            action_frames = (ctypes.c_uint16 * 2)()
            action_margins = (ctypes.c_float * 2)()
            best_mask = ctypes.c_uint32()
            stats = (ctypes.c_uint64 * 8)()
            self.assertEqual(
                query(
                    handle,
                    0,
                    0,
                    0,
                    0,
                    -1,
                    None,
                    0,
                    -1,
                    0,
                    ctypes.byref(state_frames),
                    ctypes.byref(state_margin),
                    action_frames,
                    action_margins,
                    ctypes.byref(best_mask),
                    stats,
                ),
                0,
            )
            self.assertEqual(state_frames.value, 1)
            self.assertEqual(best_mask.value, 0x03)
        finally:
            destroy(handle)

    def test_authoritative_header_matches_export_manifest(self) -> None:
        header_symbols = tuple(
            sorted(
                re.findall(
                    r"\b(touhou_[a-zA-Z0-9_]+)\s*\(",
                    ABI_HEADER.read_text(encoding="utf-8"),
                )
            )
        )
        self.assertEqual(header_symbols, _manifest_symbols())

    def test_authoritative_header_is_self_contained_c_and_cpp(self) -> None:
        cases = (
            (shutil.which("cc"), "c11", "c"),
            (shutil.which("c++"), "c++17", "c++"),
        )
        checked = 0
        for compiler, standard, language in cases:
            if compiler is None:
                continue
            with self.subTest(language=language):
                subprocess.run(
                    [
                        compiler,
                        f"-std={standard}",
                        "-fsyntax-only",
                        "-I",
                        str(ROOT / "native"),
                        "-x",
                        language,
                        "-",
                    ],
                    input=(
                        '#include "include/touhou_native/abi.h"\n'
                        "int main(void) { return 0; }\n"
                    ),
                    check=True,
                    text=True,
                    capture_output=True,
                )
            checked += 1
        if checked == 0:
            self.skipTest("no C/C++ compiler is available")

    def test_linux_dynamic_exports_are_exactly_the_manifest(self) -> None:
        tool = shutil.which("nm")
        library = (
            ROOT
            / "native"
            / "build"
            / "linux-x86_64"
            / "libtouhou_viability.so"
        )
        if tool is None or not library.exists():
            self.skipTest("Linux native library or nm is unavailable")
        completed = subprocess.run(
            [tool, "-D", "-g", "--defined-only", str(library)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            tuple(sorted(line.split()[-1] for line in completed.stdout.splitlines())),
            _manifest_symbols(),
        )

    def test_built_libraries_match_checked_in_export_manifest(self) -> None:
        expected = _manifest_symbols()
        self.assertEqual(expected, tuple(sorted(set(expected))))
        self.assertEqual(len(expected), 46)
        targets = (
            (
                shutil.which("nm"),
                ROOT
                / "native"
                / "build"
                / "linux-x86_64"
                / "libtouhou_viability.so",
            ),
            (
                shutil.which("x86_64-w64-mingw32-nm"),
                ROOT
                / "native"
                / "build"
                / "windows-x86_64"
                / "touhou_viability.dll",
            ),
            (
                shutil.which("i686-w64-mingw32-nm"),
                ROOT
                / "native"
                / "build"
                / "windows-x86"
                / "touhou_viability.dll",
            ),
        )
        checked = 0
        for tool, library in targets:
            if tool is None or not library.exists():
                continue
            with self.subTest(library=library.name):
                self.assertEqual(
                    _binary_symbols(tool=tool, library=library),
                    expected,
                )
            checked += 1
        if checked == 0:
            self.skipTest("no native library/export tool pair is available")


if __name__ == "__main__":
    unittest.main()
