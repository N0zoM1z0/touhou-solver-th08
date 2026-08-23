from __future__ import annotations

import ctypes
import os
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from touhou_control.native import arrays
from touhou_control.native import library


class NativeLibraryTests(unittest.TestCase):
    def test_contiguous_helper_preserves_numpy_copy_behavior(self) -> None:
        contiguous = np.arange(8, dtype=np.float32)
        self.assertIs(
            arrays.as_contiguous_array(contiguous, dtype=np.float32),
            contiguous,
        )

        noncontiguous = contiguous[::2]
        converted = arrays.as_contiguous_array(
            noncontiguous,
            dtype=np.float64,
        )
        expected = np.ascontiguousarray(noncontiguous, dtype=np.float64)
        np.testing.assert_array_equal(converted, expected)
        self.assertEqual(converted.dtype, expected.dtype)
        self.assertEqual(converted.flags.c_contiguous, expected.flags.c_contiguous)
        self.assertFalse(np.shares_memory(converted, noncontiguous))

        default_dtype = arrays.as_contiguous_array(noncontiguous)
        self.assertEqual(default_dtype.dtype, noncontiguous.dtype)
        self.assertTrue(default_dtype.flags.c_contiguous)

    def test_library_path_stays_inside_repository_native_build(self) -> None:
        expected_name = (
            "touhou_viability.dll"
            if os.name == "nt"
            else "libtouhou_viability.so"
        )
        self.assertEqual(library.library_path().name, expected_name)
        self.assertEqual(library.library_path().parents[2], library.ROOT / "native")

    def test_windows_library_directory_follows_python_pointer_width(self) -> None:
        self.assertEqual(
            library._windows_build_directory(4),
            "windows-x86",
        )
        self.assertEqual(
            library._windows_build_directory(8),
            "windows-x86_64",
        )
        with self.assertRaisesRegex(RuntimeError, "pointer size"):
            library._windows_build_directory(16)

    def test_disable_environment_skips_load_without_poisoning_retry(self) -> None:
        sentinel = object()
        with (
            mock.patch.object(library, "_LIBRARY", None),
            mock.patch.object(library, "_LOAD_ERROR", None),
            mock.patch.object(library.ctypes, "CDLL", return_value=sentinel) as load,
            mock.patch.dict(
                os.environ,
                {library.DISABLE_ENV: "1"},
                clear=False,
            ),
        ):
            self.assertIsNone(library.load_library())
            load.assert_not_called()
            del os.environ[library.DISABLE_ENV]
            self.assertIs(library.load_library(), sentinel)
            load.assert_called_once_with(str(library.library_path()))

    def test_load_error_is_cached(self) -> None:
        error = OSError("missing")
        with (
            mock.patch.object(library, "_LIBRARY", None),
            mock.patch.object(library, "_LOAD_ERROR", None),
            mock.patch.object(
                library.ctypes,
                "CDLL",
                side_effect=error,
            ) as load,
        ):
            self.assertIsNone(library.load_library())
            self.assertIsNone(library.load_library())
            self.assertIs(library._LOAD_ERROR, error)
            load.assert_called_once_with(str(library.library_path()))

    def test_optional_function_miss_is_retried_and_then_cached(self) -> None:
        fake_library = SimpleNamespace()

        def function() -> None:
            pass

        with (
            mock.patch.object(library, "load_library", return_value=fake_library),
            mock.patch.object(library, "_FUNCTION_CACHE", {}),
        ):
            self.assertIsNone(
                library.load_function(
                    "optional",
                    argtypes=[ctypes.c_int],
                    restype=ctypes.c_int,
                    optional=True,
                )
            )
            fake_library.optional = function
            self.assertIs(
                library.load_function(
                    "optional",
                    argtypes=[ctypes.c_int],
                    restype=ctypes.c_int,
                    optional=True,
                ),
                function,
            )
            del fake_library.optional
            self.assertIs(
                library.load_function(
                    "optional",
                    argtypes=[],
                    restype=None,
                    optional=True,
                ),
                function,
            )
        self.assertEqual(function.argtypes, [ctypes.c_int])
        self.assertIs(function.restype, ctypes.c_int)

    def test_optional_group_is_cached_only_after_every_symbol_exists(self) -> None:
        def first() -> None:
            pass

        def second() -> None:
            pass

        fake_library = SimpleNamespace(first=first)
        specifications = (
            ("first", [ctypes.c_int], ctypes.c_int),
            ("second", [], None),
        )
        with (
            mock.patch.object(library, "load_library", return_value=fake_library),
            mock.patch.object(library, "_FUNCTION_GROUP_CACHE", {}),
        ):
            self.assertIsNone(
                library.load_function_group(
                    "pair",
                    specifications,
                    optional=True,
                )
            )
            fake_library.second = second
            loaded = library.load_function_group(
                "pair",
                specifications,
                optional=True,
            )
            self.assertEqual(loaded, (first, second))
            del fake_library.first
            del fake_library.second
            self.assertIs(
                library.load_function_group(
                    "pair",
                    specifications,
                    optional=True,
                ),
                loaded,
            )

    def test_pipeline_status_conversion_preserves_exception_contract(self) -> None:
        cases = (
            (
                5,
                library.PipelineNativeCancelledError,
                "native pipeline workspace query was cancelled",
            ),
            (
                6,
                library.PipelineNativeDeadlineError,
                "native pipeline workspace query exceeded its deadline",
            ),
            (
                9,
                RuntimeError,
                "native pipeline workspace query returned 9",
            ),
        )
        for result, exception_type, message in cases:
            with self.subTest(result=result):
                with self.assertRaisesRegex(exception_type, f"^{message}$"):
                    library.raise_pipeline_result("query", result)


if __name__ == "__main__":
    unittest.main()
