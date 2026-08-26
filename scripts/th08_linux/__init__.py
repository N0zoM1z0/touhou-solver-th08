"""Native Linux TH08 lockstep and local-process integration."""

from th08_linux.bridge import SolverBridgeClient
from th08_linux.fingerprint import (
    canonical_fingerprint_bytes,
    capture_runtime_semantic_spine,
    capture_semantic_spine,
    enrich_with_collision_control_projection,
    enrich_with_effect_lifecycle_summary,
)
from th08_linux.process import LinuxProcessReader
from th08_linux.protocol import InputRequest
from th08_linux.session import LinuxGameSession, LinuxRuntimeIdentity
from th08_linux.semantic_trace import (
    MANAGER_FRAME_TRANSITION_ADVANCED,
    MANAGER_FRAME_TRANSITION_SAME,
    classify_manager_frame_transition,
    compare_semantic_traces,
    partial_semantic_trace_path,
    read_semantic_trace,
    replay_stage_binding_mismatch,
    replay_stage_terminal_reason,
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
    capture_memory_witness,
    validate_request_memory_witness,
)

__all__ = (
    "InputRequest",
    "EASY_DIFFICULTY",
    "LinuxGameSession",
    "LockstepMemoryWitness",
    "LinuxProcessReader",
    "LinuxRuntimeIdentity",
    "MANAGER_FRAME_TRANSITION_ADVANCED",
    "MANAGER_FRAME_TRANSITION_SAME",
    "RouteTitleDriver",
    "ReplayTitleDriver",
    "SAKUYA_REMILIA_SHOT_TYPE",
    "SolverBridgeClient",
    "TitleSnapshot",
    "canonical_fingerprint_bytes",
    "capture_memory_witness",
    "capture_gameplay_bootstrap",
    "capture_runtime_semantic_spine",
    "capture_semantic_spine",
    "enrich_with_collision_control_projection",
    "enrich_with_effect_lifecycle_summary",
    "capture_title_snapshot",
    "classify_manager_frame_transition",
    "compare_semantic_traces",
    "partial_semantic_trace_path",
    "read_semantic_trace",
    "replay_stage_binding_mismatch",
    "replay_stage_terminal_reason",
    "validate_request_memory_witness",
    "write_semantic_trace",
)
