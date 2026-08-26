"""Native Linux TH08 lockstep and local-process integration."""

from th08_linux.bridge import SolverBridgeClient
from th08_linux.fingerprint import (
    canonical_fingerprint_bytes,
    capture_semantic_spine,
)
from th08_linux.process import LinuxProcessReader
from th08_linux.protocol import InputRequest
from th08_linux.session import LinuxGameSession, LinuxRuntimeIdentity
from th08_linux.semantic_trace import (
    compare_semantic_traces,
    read_semantic_trace,
    write_semantic_trace,
)
from th08_linux.title import (
    EASY_DIFFICULTY,
    SAKUYA_REMILIA_SHOT_TYPE,
    ReplayTitleDriver,
    RouteTitleDriver,
    TitleSnapshot,
    capture_gameplay_bootstrap,
    capture_title_snapshot,
)
from th08_linux.witness import (
    LockstepMemoryWitness,
    validate_request_memory_witness,
)

__all__ = (
    "InputRequest",
    "EASY_DIFFICULTY",
    "LinuxGameSession",
    "LockstepMemoryWitness",
    "LinuxProcessReader",
    "LinuxRuntimeIdentity",
    "RouteTitleDriver",
    "ReplayTitleDriver",
    "SAKUYA_REMILIA_SHOT_TYPE",
    "SolverBridgeClient",
    "TitleSnapshot",
    "canonical_fingerprint_bytes",
    "capture_gameplay_bootstrap",
    "capture_semantic_spine",
    "capture_title_snapshot",
    "compare_semantic_traces",
    "read_semantic_trace",
    "validate_request_memory_witness",
    "write_semantic_trace",
)
