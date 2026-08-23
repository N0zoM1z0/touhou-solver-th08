#!/usr/bin/env python3
"""TH08 route-2 live controller implementation and compatibility surface.

The controller is a receding-horizon smoke agent, not the final global solver.
It reads game state and projectile pools, then uses physical ``SendInput``
events. Live action never writes target memory. Explicit default-off
diagnostic observers may install reversible trace-only runtime hooks; they
have no action authority. The controller aborts on identity, route, gameplay,
or foreground-window divergence.
"""

from __future__ import annotations

import argparse
import math
import struct
import time
from collections import deque
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path

import numpy as np

from th08_boss_phase import (
    BossPhaseSnapshot,
    capture_boss_phase_snapshot,
    serialize_boss_phase_snapshot,
)
from th08_corridor_runtime import (
    CorridorCommitment,
    CorridorSolution,
    LIVE_REFINEMENT_GRID_STEPS,
    LIVE_SURVIVAL_LABELS,
    SHADOW_REFINEMENT_GRID_STEPS,
    SHADOW_SURVIVAL_LABELS,
    corridor_policy_status as _corridor_policy_status,  # noqa: F401
    corridor_submit_due as _corridor_submit_due,
    corridor_target as _corridor_target,  # noqa: F401 - compatibility export
    corridor_viability_query as _corridor_viability_query,  # noqa: F401
    solve_corridor as _solve_corridor,
    stage_corridor_solution as _stage_corridor_solution,
)
from th08_corridor_adapter import TH08_CORRIDOR_CONFIG
from th08_ecl_runtime import (
    EclLookaheadResult,
    EclInstructionCache,
    EclVmSnapshot,
    TaggedVelocityToggle,
)
from th08_ecl_vm_state import float32_from_bits
from th08_ecl_tool.core import parse_ecl
from th08_enemy_collision import (
    enemy_contact_size_to_damage_half_extent,
    enemy_lethal_to_damage_half_extent,
)
from th08_future_hazard_projection import (
    OrdinaryFutureHazardProjection,
    condition_future_hazard_projection_on_player_paths,
)
from th08_ordinary_future_sources import (
    ORDINARY_FUTURE_SOURCE_SEMANTICS_VERSION,
)
from th08_laser_runtime import (
    Laser,
    PackedLaserFrame as _PackedLaserFrame,
    build_laser_collision_frames,  # noqa: F401 - compatibility export
    build_packed_laser_collision_frames as _build_packed_laser_collision_frames,
    pack_laser_frame as _pack_laser_frame,  # noqa: F401
    serialize_laser_trace,
)
from th08_live import (
    AutoConfirmPulse,  # noqa: F401 - compatibility export
    Bullet,
    BULLET_POOL_SIZE,  # noqa: F401 - compatibility export
    BULLET_STRIDE,  # noqa: F401 - compatibility export
    ENEMY_MAX_OBSERVED_WORLD_SPEED,
    EnemyBody,
    EnemyBodyModeMemory,
    EnemyPoolSnapshot,
    GameplaySceneGuard,  # noqa: F401 - compatibility export
    INPUT_CLOCK_SHADOW_ROLE,
    IssueController,
    Item,
    LiveServiceResources,
    LiveSession,
    PolicyCoordinator,
    PolicyQueryRequest,
    PackedBulletSnapshot,  # noqa: F401 - compatibility export
    SceneClockCoordinator,
    Sensor,
    SpellEnemyBodyGuard,
    TraceSink,
    auto_confirm_eligible as _auto_confirm_eligible,
    frozen_auto_confirm_eligible as _frozen_auto_confirm_eligible,
    input_clock_message_key as _input_clock_message_key,
    semantic_clock_observation as _semantic_clock_observation,
    serialize_bullet_trace,
    serialize_semantic_clock_event as _serialize_semantic_clock_event,
    serialize_semantic_clock_observation as _serialize_semantic_clock_observation,
)
from th08_live.runtime_ecl_identity import (
    RuntimeEclIdentityService,
    RuntimeEclPhysicalProvenance,
)
from th08_runtime.ordinary_future_source_capture import (
    OrdinaryFutureSourceCaptureResult,
    capture_and_project_ordinary_future_sources,
)
from th08_live.scale_schedule_authority import (
    FinalBScaleScheduleAuthority,
    NO_SCALE_WRITER_STAGE_ROUTE_INDICES,
    NoScaleWriterScheduleAuthority,
)
from th08_live.scale_source_trace import (
    FinalBScaleSourceTraceConfiguration,
    FinalBScaleSourceTraceService,
)
from th08_live.ecl_capture import capture_main_ecl
from th08_live.bullet_decode import (  # noqa: F401
    BULLET_ANGLE_OFFSET,
    BULLET_CALLBACK_AUX_STATE_OFFSET,
    BULLET_CALLBACK_PHASE_STATE_OFFSET,
    BULLET_GEOMETRY_OFFSET,
    BULLET_ORIGINAL_TRANSFORM_FLAGS_OFFSET,
    BULLET_POSITION_OFFSET,
    BULLET_SPEED_OFFSET,
    BULLET_STATE_OFFSET,
    BULLET_STOP_ANGLE_OPERAND_OFFSET,
    BULLET_STOP_DURATION_OFFSET,
    BULLET_STOP_REPEAT_COUNT_OFFSET,
    BULLET_STOP_REPEAT_LIMIT_OFFSET,
    BULLET_STOP_RESUME_SPEED_OFFSET,
    BULLET_STOP_TIMER_ELAPSED_OFFSET,
    BULLET_STOP_TIMER_FRACTION_OFFSET,
    BULLET_TRANSFORM_FLAGS_OFFSET,
    BULLET_TRANSFORM_PROGRAM_OFFSET,
    BULLET_TRANSFORM_QUEUE_CURSOR_OFFSET,
    BULLET_VELOCITY_OFFSET,
    NATIVE_PACKED_BULLET_MIN_COUNT,
    PLANNING_BULLET_VECTOR_THRESHOLD,
    attach_tagged_velocity_toggles,
    decode_bullets,
    decode_live_planning_bullets,
    decode_packed_bullets,
    decode_planning_bullets as _decode_planning_bullets,
    finite as _finite,
    native_bullet_half_extents as _native_bullet_half_extents,
    planning_bullet_active_slots as _planning_bullet_active_slots,
)
from th08_live.corridor_trace import build_corridor_trace_record
from th08_live.cli import LiveParserDefaults, build_live_parser
from th08_live.decision_control_trace import (
    DecisionControlTraceInput,
    build_decision_control_trace_fields,
)
from th08_live.decision_trace import (
    DecisionTimingTraceInput,
    build_decision_timing_trace_fields,
    build_optional_hazard_trace_fields,
)
from th08_live.hazard_decode import (  # noqa: F401
    ITEM_ACTIVE_OFFSET,
    ITEM_FULL_VALUE_OFFSET,
    ITEM_MOTION_STATE_OFFSET,
    ITEM_POOL_SIZE,
    ITEM_POSITION_OFFSET,
    ITEM_STRIDE,
    ITEM_TYPE_OFFSET,
    ITEM_VELOCITY_OFFSET,
    LASER_ACTIVE_FRAMES_OFFSET,
    LASER_ACTIVE_OFFSET,
    LASER_ANGLE_OFFSET,
    LASER_COLLISION_DISABLE_FRAME_OFFSET,
    LASER_COLLISION_ENABLE_FRAME_OFFSET,
    LASER_COLLISION_FLAG_OFFSET,
    LASER_CURRENT_WIDTH_OFFSET,
    LASER_FADE_FRAMES_OFFSET,
    LASER_FLAGS_OFFSET,
    LASER_HEAD_OFFSET,
    LASER_MAXIMUM_LENGTH_OFFSET,
    LASER_ORIGIN_OFFSET,
    LASER_PHASE_OFFSET,
    LASER_POOL_SIZE,
    LASER_SPEED_OFFSET,
    LASER_STRIDE,
    LASER_TAIL_OFFSET,
    LASER_TIMER_FRACTION_OFFSET,
    LASER_TIMER_OFFSET,
    LASER_WARMUP_FRAMES_OFFSET,
    LASER_WIDTH_OFFSET,
    decode_items,
    decode_lasers,
)
from th08_live.fresh_issue import (
    FreshEnemyIssueDependencies,
    recertify_fresh_enemy_prefix,
)
from th08_live.iteration import (
    CapturedIteration,
    FreshIssueResult,  # noqa: F401 - compatibility export
    PublishedGuidance,
    ServiceUpdate,
)
from th08_live.issue_overrides import (
    apply_deadline_hold,
    apply_post_hit_input_overrides,
)
from th08_live.issue_stage import (
    PhysicalIssueRequest,
    commit_physical_issue,
    observe_action_issue,
)
from th08_live.kill_before_saturation import (
    MINIMUM_PLAYER_POWER,
    choose_kill_before_saturation_preference,
    observe_kill_before_saturation_target,
)
from th08_live.local_certificates import (
    control_prefix_hazards as _control_prefix_hazards_impl,
    delayed_issue_action_certificates as _delayed_issue_action_certificates_impl,
    legacy_robust_action_certificates as _legacy_robust_action_certificates_impl,
    robust_action_certificates as _robust_action_certificates_impl,
)
from th08_live.local_hazards import (  # noqa: F401
    _aabb_clearance,
    _build_bullet_frames,
    _item_value,
    _native_hazards_for_positions,
    _numpy_hazards_for_positions,
    _project_item,
    _segment_clearance,
    _select_items,
)
from th08_live.ordinary_continuation_lease import (
    ContinuationCertifiedAabb,
    ContinuationGeometryCheck,
    ContinuationLeaseCheck,
    OrdinaryContinuationLease,
    check_continuation_enemy_geometry,
    check_continuation_enemy_snapshot,
    check_continuation_lease_capture,
    check_continuation_lease_issue,
)
from th08_live.local_objectives import (
    COLLECTION_HALF_WIDTH,
    ITEM_APPROACH_POTENTIAL_WEIGHT,  # noqa: F401 - compatibility export
    ITEM_OBJECTIVES_ENABLED,
    ITEM_SAFETY_CLEARANCE,
    ITEM_UTILITY_SATURATION,  # noqa: F401 - compatibility export
    ITEM_UTILITY_WEIGHT,  # noqa: F401 - compatibility export
    item_potential as _item_potential,  # noqa: F401
    node_key as _node_key,
    terminal_threat_degeneracy as _terminal_threat_degeneracy,
    terminal_threat_scores as _terminal_threat_scores_impl,
)
from touhou_control.hazard_coverage import (
    HazardCoverageAssessment,
    rebase_hazard_coverage,
)
from touhou_control.corridor import (
    aabb_sample_clearance_field,
    packed_annular_sector_clearance_field,
)
from touhou_control.prepublication import (
    CausalPrepublicationFilter,
    build_causal_prepublication_filter,
    unavailable_causal_prepublication_filter,
)
from touhou_control.viability import RobustViabilityPolicy
from th08_live.movement import (
    BOMB,
    DOWN,
    FOCUS,
    FOCUSED_CARDINAL_SPEED,  # noqa: F401 - compatibility export
    FOCUSED_DIAGONAL_SPEED,  # noqa: F401 - compatibility export
    LEFT,
    LOCAL_PIPELINE_STATE_ACTIONS as _LOCAL_PIPELINE_STATE_ACTIONS,  # noqa: F401
    PLANNER_ACTIONS as _PLANNER_ACTIONS,
    PLAYER_RADIUS,
    PLAYFIELD_BOTTOM,
    PLAYFIELD_LEFT,
    PLAYFIELD_RIGHT,
    PLAYFIELD_TOP,
    RIGHT,
    SHOT,
    UNFOCUSED_CARDINAL_SPEED,
    UNFOCUSED_DIAGONAL_SPEED,
    UP,
    action_name_from_mask as _action_name_from_mask,
    advance_planner_action as _advance_planner_action,
    boundary_control_reserve_deficit as _boundary_control_reserve_deficit,
    boundary_risk as _boundary_risk,
    boundary_risk_for_positions as _boundary_risk_for_positions,  # noqa: F401
    directions_opposed as _directions_opposed,
    local_pipeline_action_from_mask as _local_pipeline_action_from_mask,
    minimum_travel_frames as _minimum_travel_frames,
    project_player_for_read_lag as _project_player_for_read_lag,
)
from th08_live.sensing_trace import (
    SensingTraceInput,
    _time_scale_schedule_hard_authority,
    build_sensing_trace_fields,
)
from th08_time_scale import (
    SCALE_COVERAGE_COMPLETE,
    SCALE_COVERAGE_ROOT_ONLY,
    TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION,
    TH08_UNIT_TIME_SCALE_BITS,
    Th08TimeScaleSchedule,
)
from th08_live.enemy_sensor import (  # noqa: F401
    ENEMY_ACTIVE_FLAG,
    ENEMY_BODY_READ_OFFSET,
    ENEMY_BODY_READ_SIZE,
    ENEMY_CONTACT_BLOCKING_FLAGS,
    ENEMY_CONTACT_ENABLED_FLAG,
    ENEMY_CONTACT_SIZE_OFFSET,
    ENEMY_FLAGS_OFFSET,
    ENEMY_LOCAL_PREFIX_SIZE,
    ENEMY_MANAGER_TEMPLATE_BASE,
    ENEMY_POOL_BASE,
    ENEMY_POOL_SIZE,
    ENEMY_POSITION_OFFSET,
    ENEMY_STRIDE,
    ENEMY_VELOCITY_OFFSET,
    PLAYER_LETHAL_AABB_OFFSET,
    PLAYER_LETHAL_AABB_SIZE,
    _serialized_enemy_bodies,
    capture_enemy_pool_prefix_contiguous,
    capture_enemy_pool_snapshot,
    capture_enemy_pool_snapshot_contiguous,
    capture_enemy_pool_snapshot_sparse,
    capture_hit_contact_observation,
    decode_enemy_bodies,
    decode_enemy_body,
    decode_player_lethal_aabb,
    decode_spell_enemy_body_guard,
    enemy_body_contact_enabled,
    enemy_pointer_in_scanned_pool,
    enemy_pool_snapshot_changes,
    issue_enemy_snapshot_changes,
    merge_enemy_pool_prefix,
    merge_spell_enemy_body_guard,
    project_enemy_pool_snapshot,
    read_enemy_bodies_sparse,
    read_enemy_body_guard,
    read_spell_enemy_bodies,
    read_spell_enemy_body_guard,
)
from th08_live.enemy_mode_capture import capture_player_enemy_mode_prefix
from th08_live.planner_pass import (
    LocalCertificateTimingAccumulator as _LocalCertificateTimingAccumulator,
    PlannerModeTransition as _PlannerModeTransition,
    PlannerPassDependencies,
    _run_local_planner_pass as _run_local_planner_pass_impl,
)
from th08_live.pipeline_shadow import (
    build_pipeline_shadow_snapshot,
    corridor_hazard_version,
    unknown_future_coverage,
)
from th08_local_planner import (  # noqa: F401
    ActuatorPipeline,
    BaselineBeamContext,
    DamageDecisionFields,
    Decision,
    DecisionTelemetry,  # noqa: F401 - compatibility export
    EndpointRanker,
    GlobalGuidance,
    IssueAdapter,
    IssueRecertification,
    IssueRequest,
    IssueTransaction,
    IssuedDecision,
    LocalCertificateTiming,
    LocalPlannerRequest,
    LocalProposal,
    ObjectiveContext,
    PhysicalHazardSnapshot,
    PlannerAction,
    PlannerConfig,
    PlannerMode,
    PlannerPassPreparation,
    ProposalAssemblyContext,
    RobustActionCertificate,
    SearchNode,
    assemble_local_decision,
    prepare_planner_pass,
    run_baseline_beam,
)
from th08_runtime_agent import (
    ADDR_ENGINE_FLAGS,
    ADDR_ENEMY_MANAGER_FRAME,
    ADDR_PLAYER,
    ADDR_STAGE_ROUTE_INDEX,
    PLAYER_BOMB_ACTIVE_OFFSET,
    SUPPORTED_INPUT_MASK,
    TARGET_EXE,
    _require_foreground,
    capture_input_clock_shadow,
    capture_player_control_root,
    observe_state,
    send_scan_key,
    verify_target,
)
from th08_runtime.enemy_lifecycle_probe import (
    EnemyLifecycleBatch,
    EnemyLifecycleProbe,
    EnemyLifecycleProbeUnsafeStateError,
    PROBE_SCHEMA as ENEMY_LIFECYCLE_PROBE_SCHEMA,
)
from touhou_control import native_backend
from touhou_control.async_policy import (
    AsyncPolicyLead,
    delay_support_envelope,
)
from touhou_control.delay import AdaptiveControlDelay
from touhou_control.epochs import (
    ActionIssueAlignment,  # noqa: F401 - compatibility export
    FrameWindow,
    HazardEpochAlignment,
)
from touhou_control.input_clock import (
    SemanticClockEvent,
    SemanticClockObservation,
)
from touhou_control.local_pipeline_oracle import (
    LocalPipelineRoot,
    enumerate_delayed_issue_pipeline_branches,
    enumerate_local_pipeline_branches,
)
from touhou_control.phase_progress import (  # noqa: F401
    PhaseProgressObservation,
    PhaseProgressTracker,
    ProgressCandidate,
    select_progress_action,
)
ECL_CALLBACK_LOOKAHEAD_FRAMES = 256
ECL_BIRTH_LOOKAHEAD_FRAMES = 80
INPUT_CLOCK_SHADOW_WALL_CUT_SECONDS = 0.05

PLANNER_HORIZON = 10
PLANNER_THREAT_HORIZON = 32
PLANNER_BEAM_WIDTH = 24
PLANNER_ACTION_HOLD = 2
LIVE_ACTION_HOLD_DEFAULT = 3
LIVE_ACTION_HOLD_MAX = 6
# The previous input remains active while the current snapshot is read and
# planned. Live control estimates this prefix independently from action hold.
CONTROL_DELAY_FRAMES = 2
LIVE_CONTROL_DELAY_MIN = 1
LIVE_CONTROL_DELAY_MAX = 6
LIVE_CONTROL_DELAY_WINDOW = 120
LIVE_CONTROL_DELAY_GUARD_FRAMES = 600
# A native pool read normally spans zero or one manager update. A wider bound
# tolerates scheduler stalls but rejects known +1800 logical timer jumps that
# splice source state and hazard pools from different gameplay epochs.
MAX_SENSOR_EPOCH_EXTENT_FRAMES = 8
# A normal 60 Hz counter cannot advance this far during one local planning
# call. This catches logical +1800 jumps that occur after sensor capture but
# before input issue without mislabeling an ordinary 7..20-frame overrun as a
# new gameplay epoch.
MAX_ACTION_CONTIGUOUS_ADVANCE_FRAMES = 120
# Below this active-pool density, consolidated scalar unpacking is faster
# than allocating NumPy gather arrays. Retained synthetic sweeps place the
# crossover between 400 and 600 records on the current host.
# A rolling async policy can outlive several estimator updates. Cover the
# complete configured support instead of assuming only one-step drift.
ASYNC_POLICY_DELAY_PADDING = (
    LIVE_CONTROL_DELAY_MAX - LIVE_CONTROL_DELAY_MIN
)
ENEMY_SENSOR_INTERVAL_FRAMES = 4
# Keep the single worker work-conserving. There is never more than one queued
# solve, so native solve throughput remains the hard rate limit.
CORRIDOR_REPLAN_FRAMES = TH08_CORRIDOR_CONFIG.frames_per_layer
CORRIDOR_LOOKAHEAD_FRAMES = 16
CORRIDOR_MAX_AGE_FRAMES = (
    TH08_CORRIDOR_CONFIG.horizon_frames - 1
)
CORRIDOR_POLICY_LEAD_INITIAL_FRAMES = 80
CORRIDOR_POLICY_OVERLAP_FRAMES = 8
CORRIDOR_POLICY_MAXIMUM_LEAD_FRAMES = 180
ORDINARY_FUTURE_SOURCE_CAPTURE_INTERVAL_FRAMES = 8
ORDINARY_FUTURE_SOURCE_HORIZON_FRAMES = (
    CORRIDOR_POLICY_MAXIMUM_LEAD_FRAMES
    + TH08_CORRIDOR_CONFIG.horizon_frames
    + ORDINARY_FUTURE_SOURCE_CAPTURE_INTERVAL_FRAMES
)
CORRIDOR_POLICY_MINIMUM_LEAD_FRAMES = max(
    2 * TH08_CORRIDOR_CONFIG.frames_per_layer,
    LIVE_CONTROL_DELAY_MAX + LIVE_ACTION_HOLD_MAX,
)
ORDINARY_AUTHORITY_GRID_STEP = 4.0
ORDINARY_AUTHORITY_CELL_RADIUS = (
    math.sqrt(2.0) * ORDINARY_AUTHORITY_GRID_STEP / 2.0
)
ORDINARY_AUTHORITY_CORRIDOR_CONFIG = replace(
    TH08_CORRIDOR_CONFIG,
    grid_step=ORDINARY_AUTHORITY_GRID_STEP,
    required_clearance=ORDINARY_AUTHORITY_CELL_RADIUS,
)
# Leave physical CPU capacity for TH08, sensing, and issue-time control.  A
# 16-way background solve produced 12..16-frame action lag while an already
# published directional exact set was waiting to be issued.
ORDINARY_AUTHORITY_NATIVE_WORKERS = 8
ORDINARY_AUTHORITY_MIN_TERMINAL_LEAD = LIVE_ACTION_HOLD_MAX + 1
ORDINARY_TERMINAL_PROBE_ACTION_LIMIT = 3
ORDINARY_PREFIX_CERTIFICATE_ACTION_LIMIT = 3
ORDINARY_CAUSAL_ISSUE_DELAY_MIN = 0
ORDINARY_CAUSAL_ISSUE_DELAY_MAX = 79
ORDINARY_CAUSAL_ISSUE_BIN_FRAMES = 16
ORDINARY_CAUSAL_SCAN_INTERVAL_FRAMES = 60
ORDINARY_CAUSAL_COMPUTATION_GUARD_ENABLED = True
DIAGNOSTIC_ROOT_ONLY_SCALE_HORIZON = max(
    MAX_ACTION_CONTIGUOUS_ADVANCE_FRAMES,
    MAX_SENSOR_EPOCH_EXTENT_FRAMES
    + CORRIDOR_POLICY_MAXIMUM_LEAD_FRAMES
    + TH08_CORRIDOR_CONFIG.horizon_frames
    + 1,
)
# An ordinary enemy slot can clear its active/contact mode while its geometry
# continues and later re-enable inside the current robust-policy horizon.
# Retain the last observed mode envelope for exactly that modeled horizon.
ENEMY_DORMANT_MEMORY_FRAMES = TH08_CORRIDOR_CONFIG.horizon_frames
CORRIDOR_MIN_COMMIT_FRAMES = 32
CORRIDOR_INITIAL_SUBMIT_FRAME = -1_000_000
STAGE_TRANSITION_TIMEOUT_SECONDS = 90.0
TERMINAL_INACTIVE_GRACE_SECONDS = 5.0

# Route-2 stage resource indices. Stage 4B can feed Stage 5 but is not reached
# by Sakuya/Remilia; retaining it makes the scene guard valid for either branch.
ROUTE2_STAGE_SUCCESSORS = {
    0: 1,
    1: 2,
    2: 3,
    3: 5,
    4: 5,
    5: 7,
}
ORDINARY_PREEXHAUSTION_AUTHORITY = (
    "causal_ordinary_nonspell_prepublication_viability_v1"
)
ORDINARY_CAUSAL_HOLD_AUTHORITY = (
    "causal_ordinary_nonspell_constant_hold_remaining_horizon_v2"
)
ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY = (
    "causal_ordinary_nonspell_delayed_issue_horizon_v1"
)
ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY = (
    "causal_ordinary_nonspell_terminal_continuation_lease_v4"
)
CORRIDOR_ALLOWED_ACTION_AUTHORITY = "exact_corridor_viability_v1"
_NONRELAXABLE_ALLOWED_ACTION_AUTHORITIES = frozenset(
    {
        CORRIDOR_ALLOWED_ACTION_AUTHORITY,
        ORDINARY_PREEXHAUSTION_AUTHORITY,
        ORDINARY_CAUSAL_HOLD_AUTHORITY,
        ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY,
        ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY,
    }
)


def _allow_coarse_viability_relaxation(
    allowed_action_authority: str | None,
) -> bool:
    return (
        allowed_action_authority
        not in _NONRELAXABLE_ALLOWED_ACTION_AUTHORITIES
    )


_ORDINARY_PREEXHAUSTION_ACTIONS = tuple(
    action.name for action in _PLANNER_ACTIONS
)
_ORDINARY_PREEXHAUSTION_VELOCITIES = {
    action.name: (action.dx, action.dy)
    for action in _LOCAL_PIPELINE_STATE_ACTIONS
}


def _ordinary_prefix_candidate_actions(
    *,
    held_action: str,
    terminal_candidates: tuple[str, ...],
    recovery_actions: tuple[str, ...],
    limit: int = ORDINARY_PREFIX_CERTIFICATE_ACTION_LIMIT,
) -> tuple[PlannerAction, ...]:
    """Choose a bounded hard-authority subset without adding an action."""

    if limit <= 0:
        raise ValueError("ordinary prefix action limit must be positive")
    candidate_set = set(terminal_candidates)
    priority_names = (
        held_action,
        *recovery_actions[:3],
        "left_fast",
        "right_fast",
        "up_fast",
        "down_fast",
        *terminal_candidates,
    )
    selected_names: list[str] = []
    for name in priority_names:
        if name in candidate_set and name not in selected_names:
            selected_names.append(name)
        if len(selected_names) >= limit:
            break
    return tuple(
        action
        for name in selected_names
        for action in _PLANNER_ACTIONS
        if action.name == name
    )


def _ordinary_terminal_probe_actions(
    *,
    held_action: str,
    recovery_distances: tuple[tuple[str, float], ...],
    viable_repair_volumes: tuple[tuple[str, int], ...] = (),
    limit: int = ORDINARY_TERMINAL_PROBE_ACTION_LIMIT,
) -> tuple[PlannerAction, ...]:
    """Select a small exact predecessor subset before any policy queries.

    Current-kernel repair volume is candidate ordering only.  Every selected
    candidate still has to pass the independent prefix and terminal
    predecessor before it can acquire authority.
    """

    if limit <= 0:
        raise ValueError("ordinary terminal probe limit must be positive")
    recovery_names = tuple(
        name
        for name, _ in sorted(
            recovery_distances,
            key=lambda item: (item[1], item[0]),
        )
    )
    viable_names = tuple(
        name
        for name, _ in sorted(
            viable_repair_volumes,
            key=lambda item: (-item[1], item[0]),
        )
    )
    priority_names = (
        held_action,
        *viable_names,
        *recovery_names,
        "left_fast",
        "right_fast",
        "up_fast",
        "down_fast",
        *_ORDINARY_PREEXHAUSTION_ACTIONS,
    )
    selected_names: list[str] = []
    for name in priority_names:
        if (
            name in _ORDINARY_PREEXHAUSTION_VELOCITIES
            and name not in selected_names
        ):
            selected_names.append(name)
        if len(selected_names) >= limit:
            break
    return tuple(
        action
        for name in selected_names
        for action in _PLANNER_ACTIONS
        if action.name == name
    )


def _ordinary_delayed_computation_guard(
    *,
    continuation_lease_active: bool,
    held_action_safe: bool,
    held_action_reason: str,
) -> tuple[bool, str]:
    """Require an exact no-write witness before a synchronous long scan."""

    if continuation_lease_active:
        return True, "compatible_continuation_lease"
    if held_action_safe:
        return True, "exact_constant_hold_horizon"
    return False, f"blocked_without_exact_hold:{held_action_reason}"


def _prioritize_ordinary_delayed_actions(
    actions: tuple[PlannerAction, ...],
    *,
    planned_action: str,
    limit: int = ORDINARY_TERMINAL_PROBE_ACTION_LIMIT,
) -> tuple[PlannerAction, ...]:
    """Put the already-observed local proposal first for computation only.

    This ordering never grants authority or removes the exact held/no-write
    path from a candidate certificate.  It only decides which independent
    action-conditioned predecessor is computed first.
    """

    if limit <= 0:
        raise ValueError("ordinary delayed action limit must be positive")
    by_name = {action.name: action for action in _PLANNER_ACTIONS}
    ordered: list[PlannerAction] = []
    for candidate in (
        by_name.get(planned_action),
        *actions,
    ):
        if candidate is None or candidate in ordered:
            continue
        ordered.append(candidate)
        if len(ordered) >= limit:
            break
    return tuple(ordered)


def _finalize_ordinary_terminal_probe(
    terminal_probe: CausalPrepublicationFilter,
    *,
    prefix_safe_actions: tuple[str, ...],
) -> CausalPrepublicationFilter:
    """Attach the exact prefix slab without repeating terminal queries."""

    prefix_set = set(prefix_safe_actions)
    candidate_viable = tuple(
        action
        for action in terminal_probe.candidate_viable_actions
        if action in prefix_set
    )
    allowed_actions = (
        candidate_viable if terminal_probe.authority_eligible else None
    )
    if not terminal_probe.authority_eligible:
        reason = terminal_probe.reason
    elif not candidate_viable:
        reason = "prepublication_viable_predecessor_empty"
    elif len(candidate_viable) == len(terminal_probe.actions):
        reason = "all_selected_actions_reach_future_viable_set"
    else:
        reason = "prepublication_viable_actions_found"
    return replace(
        terminal_probe,
        applicable=bool(
            terminal_probe.authority_eligible and candidate_viable
        ),
        reason=reason,
        allowed_actions=allowed_actions,
        candidate_viable_actions=candidate_viable,
        prefix_safe_actions=prefix_safe_actions,
    )


def _corridor_scale_schedule_supported(
    schedule: Th08TimeScaleSchedule,
    *,
    horizon: int,
) -> bool:
    if (
        horizon <= 0
        or schedule.coverage != SCALE_COVERAGE_COMPLETE
        or schedule.complete_horizon < horizon
    ):
        return False
    return all(
        bits == TH08_UNIT_TIME_SCALE_BITS
        for bits in (
            *schedule.player_scale_bits[:horizon],
            *schedule.laser_scale_bits[:horizon],
        )
    )


def _corridor_submission_policy_allows(
    *,
    authority_only: bool,
    time_scale_hard_authority: bool,
) -> bool:
    return not authority_only or time_scale_hard_authority


def _diagnostic_constant_root_time_scale(
    schedule: Th08TimeScaleSchedule,
) -> Th08TimeScaleSchedule:
    """Build an explicit unknown-direction physical-observer proxy."""

    if schedule.coverage != SCALE_COVERAGE_ROOT_ONLY:
        raise ValueError(
            "diagnostic scale fallback requires root-only coverage"
        )
    return Th08TimeScaleSchedule.constant(
        schedule.root_scale_bits,
        horizon=DIAGNOSTIC_ROOT_ONLY_SCALE_HORIZON,
        provenance=(
            "diagnostic_constant_current_root_unknown_direction_no_authority"
        ),
        source_frame=schedule.source_frame,
    )


def _ordinary_lower_kernel(
    solution: CorridorSolution | None,
) -> RobustViabilityPolicy | None:
    if solution is None or solution.plan.viability_policy is None:
        return None
    policy = solution.plan.viability_policy
    if (
        len(policy.x_axis) < 2
        or not math.isclose(
            float(policy.x_axis[1] - policy.x_axis[0]),
            ORDINARY_AUTHORITY_GRID_STEP,
        )
        or not math.isclose(
            float(policy.config.required_clearance),
            ORDINARY_AUTHORITY_CELL_RADIUS,
        )
    ):
        return None
    return policy


def _ordinary_solution_hazard_authority(
    solution: CorridorSolution | None,
) -> bool:
    policy = _ordinary_lower_kernel(solution)
    if solution is None or policy is None:
        return False
    coverage = solution.future_hazard_coverage
    projection = solution.future_hazard_projection
    required_version = corridor_hazard_version(solution)
    return bool(
        isinstance(projection, OrdinaryFutureHazardProjection)
        and projection.version == required_version
        and coverage is not None
        and coverage.complete
        and coverage.root_frame <= solution.source_frame
        and coverage.horizon_frame
        >= solution.source_frame + policy.horizon_frames
        and coverage.slabs
        and all(
            slab.version == required_version
            for slab in coverage.slabs
        )
    )


def _ordinary_target_query_frame(
    *,
    policy: RobustViabilityPolicy,
    policy_age: int,
) -> int | None:
    frames_per_layer = policy.config.frames_per_layer
    target_layer = math.ceil(
        max(
            0,
            policy_age + ORDINARY_AUTHORITY_MIN_TERMINAL_LEAD,
        )
        / frames_per_layer
    )
    target_frame = target_layer * frames_per_layer
    if target_frame >= policy.horizon_frames:
        return None
    return target_frame


def _ordinary_authority_target(
    *,
    active_solution: CorridorSolution | None,
    pending_solution: CorridorSolution | None,
    current_frame: int,
) -> tuple[CorridorSolution | None, int]:
    """Choose the earliest exact terminal kernel still ahead of this root.

    A completed policy whose source epoch is still in the future is precisely
    the terminal object needed by the causal pre-publication predecessor.  It
    must not be hidden merely because it is not yet the active rolling policy.
    """

    candidates: list[tuple[int, int, CorridorSolution]] = []
    for order, solution in enumerate((active_solution, pending_solution)):
        policy = _ordinary_lower_kernel(solution)
        if (
            solution is None
            or policy is None
            or not _ordinary_solution_hazard_authority(solution)
        ):
            continue
        query_frame = _ordinary_target_query_frame(
            policy=policy,
            policy_age=current_frame - solution.source_frame,
        )
        if query_frame is None:
            continue
        publication_frame = solution.source_frame + query_frame
        if publication_frame <= current_frame:
            continue
        candidates.append(
            (publication_frame, order, solution)
        )
    if not candidates:
        return None, 0
    publication_frame, _order, solution = min(candidates)
    return solution, publication_frame - solution.source_frame


def _ordinary_submission_projection(
    result: OrdinaryFutureSourceCaptureResult | None,
    *,
    policy_source_frame: int,
    policy_horizon_frames: int,
) -> OrdinaryFutureHazardProjection | None:
    """Return only a complete source slab that covers the proposed kernel."""

    projection = result.closure.projection if result is not None else None
    if (
        projection is None
        or not projection.source_closure_complete
        or projection.root_frame > policy_source_frame
        or projection.horizon_frame
        < policy_source_frame + policy_horizon_frames
    ):
        return None
    return projection


def _ordinary_nonspell_preexhaustion_filter(
    *,
    enabled: bool,
    spell_active: bool,
    player_phase: int,
    root_scale_bits: int,
    root: LocalPipelineRoot | None,
    action_hold_frames: int,
    player_x: float,
    player_y: float,
    current_frame: int,
    future_solution: CorridorSolution | None,
    future_hazard_coverage: HazardCoverageAssessment | None,
    future_policy_query_frame: int = 0,
    future_policy_source_frame: int | None = None,
    prefix_certified_frames: int = 0,
    prefix_safe_actions: tuple[str, ...] | None = None,
    selected_actions: tuple[str, ...] = _ORDINARY_PREEXHAUSTION_ACTIONS,
) -> CausalPrepublicationFilter:
    """Build fail-closed authority into the next published ordinary kernel."""

    pickup_delay_frames = tuple(range(action_hold_frames + 1))
    if not enabled:
        return unavailable_causal_prepublication_filter(
            enabled=False,
            reason="disabled",
            pickup_delay_frames=pickup_delay_frames,
            coverage=future_hazard_coverage,
        )
    if spell_active:
        return unavailable_causal_prepublication_filter(
            enabled=True,
            reason="spell_active",
            pickup_delay_frames=pickup_delay_frames,
            coverage=future_hazard_coverage,
        )
    if player_phase in (1, 2):
        return unavailable_causal_prepublication_filter(
            enabled=True,
            reason="player_transition",
            pickup_delay_frames=pickup_delay_frames,
            coverage=future_hazard_coverage,
        )
    if root_scale_bits != TH08_UNIT_TIME_SCALE_BITS:
        return unavailable_causal_prepublication_filter(
            enabled=True,
            reason="nonunit_root_time_scale",
            pickup_delay_frames=pickup_delay_frames,
            coverage=future_hazard_coverage,
        )
    if future_solution is None:
        return unavailable_causal_prepublication_filter(
            enabled=True,
            reason="future_policy_unavailable",
            state_eligible=True,
            pickup_delay_frames=pickup_delay_frames,
            coverage=future_hazard_coverage,
        )
    return build_causal_prepublication_filter(
        enabled=True,
        root=root,
        selected_actions=selected_actions,
        action_velocities=_ORDINARY_PREEXHAUSTION_VELOCITIES,
        delay_frames=pickup_delay_frames,
        current_frame=current_frame,
        publication_frame=(
            future_solution.source_frame + future_policy_query_frame
        ),
        prefix_certified_frames=prefix_certified_frames,
        prefix_safe_actions=prefix_safe_actions,
        start_x=player_x,
        start_y=player_y,
        future_safety_policy=None,
        future_viability_policy=future_solution.plan.viability_policy,
        future_recovery_policy=future_solution.plan.viability_policy,
        hazard_coverage=future_hazard_coverage,
        required_hazard_version=corridor_hazard_version(future_solution),
        policy_query_frame=future_policy_query_frame,
        policy_source_frame=(
            future_solution.source_frame
            if future_policy_source_frame is None
            else future_policy_source_frame
        ),
    )


def _local_certificate_timing_record(
    timing: LocalCertificateTiming,
) -> dict[str, int | float]:
    segmented_ms = (
        timing.validation_ms
        + timing.hazard_projection_ms
        + timing.branch_setup_ms
        + timing.geometry_kernel_ms
        + timing.reduction_ms
    )
    return {
        "calls": timing.calls,
        "explicit_root_calls": timing.explicit_root_calls,
        "maximum_branch_count": timing.maximum_branch_count,
        "shared_laser_projection_ms": (
            timing.shared_laser_projection_ms
        ),
        "validation_ms": timing.validation_ms,
        "hazard_projection_ms": timing.hazard_projection_ms,
        "branch_setup_ms": timing.branch_setup_ms,
        "geometry_kernel_ms": timing.geometry_kernel_ms,
        "reduction_ms": timing.reduction_ms,
        "certificate_total_ms": timing.certificate_total_ms,
        "control_prefix_ms": timing.control_prefix_ms,
        "planning_bullet_projection_ms": (
            timing.planning_bullet_projection_ms
        ),
        "beam_search_ms": timing.beam_search_ms,
        "terminal_threat_ms": timing.terminal_threat_ms,
        "selection_finalize_ms": timing.selection_finalize_ms,
        "project_and_certify_ms": (
            timing.shared_laser_projection_ms
            + timing.certificate_total_ms
        ),
        "certificate_unattributed_ms": max(
            0.0,
            timing.certificate_total_ms - segmented_ms,
        ),
    }


def _robust_action_certificate_record(
    certificate: RobustActionCertificate,
) -> dict[str, object]:
    return {
        "action": certificate.action,
        "delay_frames": certificate.delay_frames,
        "worst_collisions": certificate.worst_collisions,
        "min_clearance": certificate.min_clearance,
        "cvar_risk": certificate.cvar_risk,
        "worst_delay": certificate.worst_delay,
        "write_required": certificate.write_required,
        "pipeline_branch_count": certificate.pipeline_branch_count,
        "worst_pending_remaining": (
            certificate.worst_pending_remaining
        ),
    }


def _issue_recertification_record(
    recertification: IssueRecertification | None,
) -> dict[str, object] | None:
    if recertification is None:
        return None
    global_allowed = recertification.global_allowed_actions
    selected_outside_global_without_relaxation = bool(
        global_allowed is not None
        and recertification.selected_action not in global_allowed
        and not recertification.global_constraint_relaxed
    )
    return {
        "planned_action": recertification.planned_action,
        "global_allowed_actions": global_allowed,
        "global_constraint_applicable": (
            recertification.global_constraint_applicable
        ),
        "fresh_safe_actions": recertification.fresh_safe_actions,
        "fresh_global_intersection": (
            recertification.fresh_global_intersection
        ),
        "selected_action": recertification.selected_action,
        "selection_reason": recertification.selection_reason,
        "preferred_action": recertification.preferred_action,
        "preference_reason": recertification.preference_reason,
        "preference_applied": recertification.preference_applied,
        "global_constraint_relaxed": (
            recertification.global_constraint_relaxed
        ),
        "allowed_action_authority": (
            recertification.allowed_action_authority
        ),
        "selected_outside_global_without_relaxation": (
            selected_outside_global_without_relaxation
        ),
        "planned_certificate": (
            _robust_action_certificate_record(
                recertification.planned_certificate
            )
            if recertification.planned_certificate is not None
            else None
        ),
        "selected_certificate": _robust_action_certificate_record(
            recertification.selected_certificate
        ),
    }


def commit_local_proposal_for_fresh_hazards(
    proposal: LocalProposal,
    *,
    player_x: float,
    player_y: float,
    previous_mask: int,
    delay_frames: tuple[int, ...],
    action_hold_frames: int,
    bullets: tuple[Bullet, ...],
    lasers: tuple[Laser, ...],
    enemy_bodies: tuple[EnemyBody, ...],
    snapshot_lag: int,
    pipeline_root: LocalPipelineRoot | None = None,
    allowed_first_actions: tuple[str, ...] | None = None,
    allowed_action_authority: str | None = None,
    viability_repair_volumes: tuple[tuple[str, int], ...] = (),
    viability_recovery_distances: tuple[tuple[str, float], ...] = (),
    viability_safety_actions: tuple[str, ...] = (),
    viability_survival_actions: tuple[str, ...] = (),
    preferred_action: str | None = None,
    preference_reason: str | None = None,
    time_scale_schedule: Th08TimeScaleSchedule | None = None,
) -> IssuedDecision:
    """Commit a proposal against fresh hazards and retained global authority."""

    if time_scale_schedule is None:
        time_scale_schedule = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=action_hold_frames + max(delay_frames),
            provenance="historical_issue_wrapper_unit_assumption",
        )
    return IssueTransaction(
        proposal,
        IssueRequest(
            player_x=player_x,
            player_y=player_y,
            previous_mask=previous_mask,
            delay_frames=delay_frames,
            action_hold_frames=action_hold_frames,
            bullets=bullets,
            lasers=lasers,
            enemy_bodies=enemy_bodies,
            snapshot_lag=snapshot_lag,
            time_scale_schedule=time_scale_schedule,
            pipeline_root=pipeline_root,
            allowed_first_actions=allowed_first_actions,
            allowed_action_authority=allowed_action_authority,
            viability_repair_volumes=viability_repair_volumes,
            viability_recovery_distances=(
                viability_recovery_distances
            ),
            viability_safety_actions=viability_safety_actions,
            viability_survival_actions=viability_survival_actions,
            preferred_action=preferred_action,
            preference_reason=preference_reason,
        ),
        IssueAdapter(
            actions=_PLANNER_ACTIONS,
            certificate_provider=_robust_action_certificates,
            timing_factory=_LocalCertificateTimingAccumulator,
            shot_mask=SHOT,
            focus_mask=FOCUS,
            bomb_mask=BOMB,
        ),
    ).commit()


def issue_transaction_for_fresh_hazards(
    decision: Decision,
    *,
    player_x: float,
    player_y: float,
    previous_mask: int,
    delay_frames: tuple[int, ...],
    action_hold_frames: int,
    bullets: tuple[Bullet, ...],
    lasers: tuple[Laser, ...],
    enemy_bodies: tuple[EnemyBody, ...],
    snapshot_lag: int,
    pipeline_root: LocalPipelineRoot | None = None,
    allowed_first_actions: tuple[str, ...] | None = None,
    allowed_action_authority: str | None = None,
    viability_repair_volumes: tuple[tuple[str, int], ...] = (),
    viability_recovery_distances: tuple[tuple[str, float], ...] = (),
    viability_safety_actions: tuple[str, ...] = (),
    viability_survival_actions: tuple[str, ...] = (),
    preferred_action: str | None = None,
    preference_reason: str | None = None,
    time_scale_schedule: Th08TimeScaleSchedule | None = None,
) -> IssuedDecision:
    """Compatibility adapter from a flat decision to a proposal."""

    return commit_local_proposal_for_fresh_hazards(
        LocalProposal.from_decision(decision),
        player_x=player_x,
        player_y=player_y,
        previous_mask=previous_mask,
        delay_frames=delay_frames,
        action_hold_frames=action_hold_frames,
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        pipeline_root=pipeline_root,
        allowed_first_actions=allowed_first_actions,
        allowed_action_authority=allowed_action_authority,
        viability_repair_volumes=viability_repair_volumes,
        viability_recovery_distances=viability_recovery_distances,
        viability_safety_actions=viability_safety_actions,
        viability_survival_actions=viability_survival_actions,
        preferred_action=preferred_action,
        preference_reason=preference_reason,
        time_scale_schedule=time_scale_schedule,
    )


def recertify_action_for_fresh_hazards(
    decision: Decision,
    *,
    player_x: float,
    player_y: float,
    previous_mask: int,
    delay_frames: tuple[int, ...],
    action_hold_frames: int,
    bullets: tuple[Bullet, ...],
    lasers: tuple[Laser, ...],
    enemy_bodies: tuple[EnemyBody, ...],
    snapshot_lag: int,
    pipeline_root: LocalPipelineRoot | None = None,
    allowed_first_actions: tuple[str, ...] | None = None,
    viability_repair_volumes: tuple[tuple[str, int], ...] = (),
    viability_recovery_distances: tuple[tuple[str, float], ...] = (),
    viability_safety_actions: tuple[str, ...] = (),
    viability_survival_actions: tuple[str, ...] = (),
    preferred_action: str | None = None,
    preference_reason: str | None = None,
    time_scale_schedule: Th08TimeScaleSchedule | None = None,
) -> Decision:
    """Compatibility wrapper for the explicit issue transaction."""

    return issue_transaction_for_fresh_hazards(
        decision,
        player_x=player_x,
        player_y=player_y,
        previous_mask=previous_mask,
        delay_frames=delay_frames,
        action_hold_frames=action_hold_frames,
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        pipeline_root=pipeline_root,
        allowed_first_actions=allowed_first_actions,
        viability_repair_volumes=viability_repair_volumes,
        viability_recovery_distances=viability_recovery_distances,
        viability_safety_actions=viability_safety_actions,
        viability_survival_actions=viability_survival_actions,
        preferred_action=preferred_action,
        preference_reason=preference_reason,
        time_scale_schedule=time_scale_schedule,
    ).decision


_LOCAL_HAZARD_BACKEND = "numpy"
_LOCAL_BEAM_REDUCER = "python"
_LOCAL_BULLET_DECODER = "python"


def _configure_local_hazard_backend(backend: str) -> None:
    global _LOCAL_HAZARD_BACKEND
    if backend not in {"numpy", "native"}:
        raise ValueError(f"unknown local hazard backend: {backend}")
    if (
        backend == "native"
        and native_backend._load_local_hazards_function() is None
    ):
        raise RuntimeError("native local hazard kernel is unavailable")
    _LOCAL_HAZARD_BACKEND = backend


def _configure_local_beam_reducer(backend: str) -> None:
    global _LOCAL_BEAM_REDUCER
    if backend not in {"python", "native"}:
        raise ValueError(f"unknown local beam reducer {backend!r}")
    if (
        backend == "native"
        and native_backend._load_local_beam_reduce_function() is None
    ):
        raise RuntimeError("native local beam reducer is unavailable")
    _LOCAL_BEAM_REDUCER = backend


def _configure_local_bullet_decoder(backend: str) -> None:
    global _LOCAL_BULLET_DECODER
    if backend not in {"python", "native"}:
        raise ValueError(f"unknown local bullet decoder {backend!r}")
    if (
        backend == "native"
        and native_backend._load_bullet_pool_decode_function() is None
    ):
        raise RuntimeError("native packed bullet decoder is unavailable")
    _LOCAL_BULLET_DECODER = backend


def _hazards_for_positions(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    *,
    step: int,
    bullet_frame: tuple[np.ndarray, ...],
    lasers: tuple[Laser, ...] | _PackedLaserFrame,
    enemy_bodies: tuple[EnemyBody, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    implementation = (
        _native_hazards_for_positions
        if _LOCAL_HAZARD_BACKEND == "native"
        else _numpy_hazards_for_positions
    )
    return implementation(
        positions_x,
        positions_y,
        step=step,
        bullet_frame=bullet_frame,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
    )


def _hazards_for_positions_with_future_projection(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    *,
    step: int,
    bullet_frame: tuple[np.ndarray, ...],
    lasers: tuple[Laser, ...] | _PackedLaserFrame,
    enemy_bodies: tuple[EnemyBody, ...],
    future_hazard_projection: OrdinaryFutureHazardProjection,
    future_projection_offset: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Consume future births during a root-to-publication certificate.

    ``step`` is relative to the current observable root.  The retained
    projection may have been captured earlier for the asynchronously solved
    policy, so ``future_projection_offset`` aligns both physical clocks.
    """

    risk, collisions, minimum = _hazards_for_positions(
        positions_x,
        positions_y,
        step=step,
        bullet_frame=bullet_frame,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
    )
    projection_frame = future_projection_offset + step
    future_bodies = future_hazard_projection.aabb_samples(projection_frame)
    body_clearance = aabb_sample_clearance_field(
        positions_x,
        positions_y,
        future_bodies,
        frame=projection_frame,
        player_radius=PLAYER_RADIUS,
    )
    emission_clearance = packed_annular_sector_clearance_field(
        positions_x,
        positions_y,
        future_hazard_projection.packed_annular_sector_frames,
        frame=projection_frame,
        player_radius=PLAYER_RADIUS,
    )
    future_clearance = np.minimum(body_clearance, emission_clearance)
    collisions = collisions + (future_clearance <= 0.0).astype(
        np.int32,
        copy=False,
    )
    minimum = np.minimum(minimum, future_clearance)
    time_weight = 1.0 / (1.0 + 0.08 * (step - 1))
    danger = np.maximum(64.0 - future_clearance, 0.0)
    risk = risk + np.square(danger) * time_weight
    return risk, collisions, minimum


def _control_prefix_hazards(
    *,
    player_x: float,
    player_y: float,
    input_mask: int,
    bullets: tuple[Bullet, ...],
    lasers: tuple[Laser, ...],
    enemy_bodies: tuple[EnemyBody, ...],
    snapshot_lag: int,
    frames: int,
    player_scale_bits: tuple[int, ...],
    laser_scale_bits: tuple[int, ...],
    laser_frames: tuple[_PackedLaserFrame, ...] | None = None,
) -> tuple[float, int, float]:
    return _control_prefix_hazards_impl(
        hazards_for_positions=_hazards_for_positions,
        player_x=player_x,
        player_y=player_y,
        input_mask=input_mask,
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        frames=frames,
        player_scale_bits=player_scale_bits,
        laser_scale_bits=laser_scale_bits,
        laser_frames=laser_frames,
    )


def _legacy_robust_action_certificates(
    *,
    player_x: float,
    player_y: float,
    previous_mask: int,
    actions: tuple[PlannerAction, ...],
    delay_frames: tuple[int, ...],
    action_hold_frames: int,
    bullets: tuple[Bullet, ...],
    lasers: tuple[Laser, ...],
    enemy_bodies: tuple[EnemyBody, ...],
    snapshot_lag: int,
    player_scale_bits: tuple[int, ...],
    laser_scale_bits: tuple[int, ...],
    laser_frames: tuple[_PackedLaserFrame, ...] | None = None,
) -> dict[str, RobustActionCertificate]:
    return _legacy_robust_action_certificates_impl(
        hazards_for_positions=_hazards_for_positions,
        player_x=player_x,
        player_y=player_y,
        previous_mask=previous_mask,
        actions=actions,
        delay_frames=delay_frames,
        action_hold_frames=action_hold_frames,
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        player_scale_bits=player_scale_bits,
        laser_scale_bits=laser_scale_bits,
        laser_frames=laser_frames,
    )


def _robust_action_certificates(
    *,
    player_x: float,
    player_y: float,
    previous_mask: int,
    actions: tuple[PlannerAction, ...],
    delay_frames: tuple[int, ...],
    action_hold_frames: int,
    bullets: tuple[Bullet, ...],
    lasers: tuple[Laser, ...],
    enemy_bodies: tuple[EnemyBody, ...],
    snapshot_lag: int,
    player_scale_bits: tuple[int, ...],
    laser_scale_bits: tuple[int, ...],
    laser_frames: tuple[_PackedLaserFrame, ...] | None = None,
    pipeline_root: LocalPipelineRoot | None = None,
    future_hazard_projection: OrdinaryFutureHazardProjection | None = None,
    future_projection_offset: int = 0,
    timing_accumulator: _LocalCertificateTimingAccumulator | None = None,
) -> dict[str, RobustActionCertificate]:
    hazards_for_positions = _hazards_for_positions
    if future_hazard_projection is not None:
        if (
            not future_hazard_projection.source_closure_complete
            or not future_hazard_projection.coverage.complete
        ):
            raise ValueError(
                "future prefix certificate requires complete source coverage"
            )
        if future_projection_offset < 0:
            raise ValueError(
                "future prefix projection cannot start before its root"
            )
        required_horizon = (
            action_hold_frames + max(delay_frames, default=0)
        )
        if (
            future_projection_offset + required_horizon
            > future_hazard_projection.horizon_frames
        ):
            raise ValueError(
                "future prefix projection does not cover certificate horizon"
            )

        def hazards_for_positions(
            positions_x: np.ndarray,
            positions_y: np.ndarray,
            *,
            step: int,
            bullet_frame: tuple[np.ndarray, ...],
            lasers: tuple[Laser, ...] | _PackedLaserFrame,
            enemy_bodies: tuple[EnemyBody, ...],
        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            return _hazards_for_positions_with_future_projection(
                positions_x,
                positions_y,
                step=step,
                bullet_frame=bullet_frame,
                lasers=lasers,
                enemy_bodies=enemy_bodies,
                future_hazard_projection=future_hazard_projection,
                future_projection_offset=future_projection_offset,
            )

    return _robust_action_certificates_impl(
        hazards_for_positions=hazards_for_positions,
        player_x=player_x,
        player_y=player_y,
        previous_mask=previous_mask,
        actions=actions,
        delay_frames=delay_frames,
        action_hold_frames=action_hold_frames,
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        player_scale_bits=player_scale_bits,
        laser_scale_bits=laser_scale_bits,
        laser_frames=laser_frames,
        pipeline_root=pipeline_root,
        timing_accumulator=timing_accumulator,
    )


def _causal_pipeline_player_positions(
    *,
    root: LocalPipelineRoot,
    selected_action: str,
    delay_frames: tuple[int, ...],
    horizon_frames: int,
    player_x: float,
    player_y: float,
    player_scale_bits: tuple[int, ...],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Enumerate player positions seen by each future native emission.

    Index zero is the observed root. Later indices retain every hidden
    pending/pickup branch for the selected complete desired mask. The held
    action therefore remains the exact no-write branch.
    """

    if len(player_scale_bits) < horizon_frames:
        raise ValueError("causal player path lacks time-scale coverage")
    action_by_name = {
        action.name: action for action in _LOCAL_PIPELINE_STATE_ACTIONS
    }
    branches = enumerate_local_pipeline_branches(
        root=root,
        selected_action=selected_action,
        delay_frames=delay_frames,
        horizon_frames=horizon_frames,
    )
    positions_by_step: list[list[tuple[float, float]]] = [
        [(float(player_x), float(player_y)) for _ in branches]
    ]
    branch_positions = [
        (float(player_x), float(player_y)) for _ in branches
    ]
    for step in range(1, horizon_frames + 1):
        next_positions: list[tuple[float, float]] = []
        for branch_index, branch in enumerate(branches):
            action = action_by_name.get(branch.active_actions[step - 1])
            if action is None:
                raise ValueError("causal player path contains unknown action")
            x, y = branch_positions[branch_index]
            next_positions.append(
                _advance_planner_action(
                    x,
                    y,
                    action,
                    time_scale_bits=player_scale_bits[step - 1],
                )
            )
        positions_by_step.append(next_positions)
        branch_positions = next_positions
    return tuple(tuple(positions) for positions in positions_by_step)


def _delayed_causal_pipeline_player_positions(
    *,
    root: LocalPipelineRoot,
    selected_action: str,
    issue_delay_frames: tuple[int, ...],
    pickup_delay_frames: tuple[int, ...],
    horizon_frames: int,
    player_x: float,
    player_y: float,
    player_scale_bits: tuple[int, ...],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Pack exact emission-time paths through computation and pickup.

    The previous scalar implementation repeated the native-order movement
    interpreter once per hidden branch.  That made the computation delay we
    were trying to certify dominate the real issue age.  Planner action
    velocities and every intermediate store are binary32 here, matching the
    packed certificate kernel while retaining every delayed-issue branch.
    """

    if len(player_scale_bits) < horizon_frames:
        raise ValueError("delayed causal path lacks time-scale coverage")
    action_table = tuple(_LOCAL_PIPELINE_STATE_ACTIONS)
    action_index_by_name = {
        action.name: index for index, action in enumerate(action_table)
    }
    branches = enumerate_delayed_issue_pipeline_branches(
        root=root,
        selected_action=selected_action,
        issue_delay_frames=issue_delay_frames,
        pickup_delay_frames=pickup_delay_frames,
        horizon_frames=horizon_frames,
    )
    unknown_names = {
        name
        for branch in branches
        for name in branch.active_actions
        if name not in action_index_by_name
    }
    if unknown_names:
        raise ValueError(
            f"delayed causal path contains unknown actions: "
            f"{sorted(unknown_names)}"
        )
    packed_motion = np.asarray(
        [
            tuple(
                action_index_by_name[name]
                for name in branch.active_actions
            )
            for branch in branches
        ],
        dtype=np.int16,
    )
    packed_dx = np.asarray(
        [action.dx for action in action_table], dtype=np.float32
    )
    packed_dy = np.asarray(
        [action.dy for action in action_table], dtype=np.float32
    )
    positions_x = np.full(len(branches), player_x, dtype=np.float32)
    positions_y = np.full(len(branches), player_y, dtype=np.float32)
    positions_by_step: list[tuple[tuple[float, float], ...]] = [
        tuple(
            (float(x), float(y))
            for x, y in zip(positions_x, positions_y)
        )
    ]
    for step in range(1, horizon_frames + 1):
        motion_indices = packed_motion[:, step - 1]
        scale = np.float32(
            float32_from_bits(player_scale_bits[step - 1])
        )
        positions_x = np.clip(
            positions_x + packed_dx[motion_indices] * scale,
            PLAYFIELD_LEFT,
            PLAYFIELD_RIGHT,
        ).astype(np.float32, copy=False)
        positions_y = np.clip(
            positions_y + packed_dy[motion_indices] * scale,
            PLAYFIELD_TOP,
            PLAYFIELD_BOTTOM,
        ).astype(np.float32, copy=False)
        positions_by_step.append(
            tuple(
                (float(x), float(y))
                for x, y in zip(positions_x, positions_y)
            )
        )
    return tuple(positions_by_step)


def _delayed_issue_action_certificates(
    *,
    root: LocalPipelineRoot,
    actions: tuple[PlannerAction, ...],
    issue_delay_frames: tuple[int, ...],
    pickup_delay_frames: tuple[int, ...],
    horizon_frames: int,
    player_x: float,
    player_y: float,
    bullets: tuple[Bullet, ...],
    lasers: tuple[Laser, ...],
    enemy_bodies: tuple[EnemyBody, ...],
    snapshot_lag: int,
    player_scale_bits: tuple[int, ...],
    laser_scale_bits: tuple[int, ...],
    future_hazard_projection: OrdinaryFutureHazardProjection,
    source_frame: int,
) -> tuple[
    dict[int, dict[str, RobustActionCertificate]],
    dict[str, OrdinaryFutureHazardProjection],
]:
    """Build a hard action table conditioned on observable issue age."""

    if not future_hazard_projection.source_closure_complete:
        raise ValueError("delayed causal certificate lacks source closure")
    if not future_hazard_projection.coverage.complete:
        raise ValueError("delayed causal certificate lacks future coverage")
    certificates: dict[int, dict[str, RobustActionCertificate]] = {
        issue_delay: {} for issue_delay in issue_delay_frames
    }
    conditioned_projections: dict[
        str, OrdinaryFutureHazardProjection
    ] = {}
    general_issue_delay_bins = tuple(
        issue_delay_frames[start : start + ORDINARY_CAUSAL_ISSUE_BIN_FRAMES]
        for start in range(
            0,
            len(issue_delay_frames),
            ORDINARY_CAUSAL_ISSUE_BIN_FRAMES,
        )
    )
    bullet_frames = _build_bullet_frames(
        bullets,
        horizon=horizon_frames,
        snapshot_lag=-max(0, snapshot_lag),
    )
    laser_frames = _build_packed_laser_collision_frames(
        lasers,
        horizon=horizon_frames,
        time_scale_schedule_bits=laser_scale_bits[:horizon_frames],
    )
    for action in actions:
        held_no_write = action.name == root.held_desired_action
        issue_delay_bins = (
            ((issue_delay_frames[0],),)
            if held_no_write
            else general_issue_delay_bins
        )
        for issue_delay_bin in issue_delay_bins:
            player_positions = _delayed_causal_pipeline_player_positions(
                root=root,
                selected_action=action.name,
                issue_delay_frames=issue_delay_bin,
                pickup_delay_frames=pickup_delay_frames,
                horizon_frames=horizon_frames,
                player_x=player_x,
                player_y=player_y,
                player_scale_bits=player_scale_bits,
            )
            conditioned = condition_future_hazard_projection_on_player_paths(
                future_hazard_projection,
                source_frame=source_frame,
                horizon_frames=horizon_frames,
                player_positions_by_step=player_positions,
            )
            projection_key = (
                f"{action.name}@{issue_delay_bin[0]}-"
                f"{issue_delay_bin[-1]}"
            )
            conditioned_projections[projection_key] = conditioned

            def hazards_for_positions(
                positions_x: np.ndarray,
                positions_y: np.ndarray,
                *,
                step: int,
                bullet_frame: tuple[np.ndarray, ...],
                lasers: tuple[Laser, ...] | _PackedLaserFrame,
                enemy_bodies: tuple[EnemyBody, ...],
            ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
                return _hazards_for_positions_with_future_projection(
                    positions_x,
                    positions_y,
                    step=step,
                    bullet_frame=bullet_frame,
                    lasers=lasers,
                    enemy_bodies=enemy_bodies,
                    future_hazard_projection=conditioned,
                    future_projection_offset=0,
                )

            action_rows = _delayed_issue_action_certificates_impl(
                hazards_for_positions=hazards_for_positions,
                player_x=player_x,
                player_y=player_y,
                actions=(action,),
                issue_delay_frames=issue_delay_bin,
                pickup_delay_frames=pickup_delay_frames,
                horizon_frames=horizon_frames,
                bullets=bullets,
                lasers=lasers,
                enemy_bodies=enemy_bodies,
                snapshot_lag=snapshot_lag,
                player_scale_bits=player_scale_bits,
                laser_scale_bits=laser_scale_bits,
                pipeline_root=root,
                bullet_frames=bullet_frames,
                laser_frames=laser_frames,
            )
            if held_no_write:
                held_certificate = action_rows[issue_delay_bin[0]][
                    action.name
                ]
                for issue_delay in issue_delay_frames:
                    certificates[issue_delay][action.name] = held_certificate
            else:
                for issue_delay, row in action_rows.items():
                    certificates[issue_delay].update(row)
    return certificates, conditioned_projections


def _recertify_delayed_issue_rows_for_fresh_enemy_bodies(
    *,
    certificates_by_issue_delay: dict[
        int, dict[str, RobustActionCertificate]
    ],
    root: LocalPipelineRoot,
    actions: tuple[PlannerAction, ...],
    issue_delay_frames: tuple[int, ...],
    pickup_delay_frames: tuple[int, ...],
    horizon_frames: int,
    player_x: float,
    player_y: float,
    enemy_bodies: tuple[EnemyBody, ...],
    player_scale_bits: tuple[int, ...],
    laser_scale_bits: tuple[int, ...],
) -> dict[int, dict[str, RobustActionCertificate]]:
    """Intersect root certificates with one fresh issue-time body slab.

    Fresh bodies are aligned back to the same observable root by
    ``EnemyBodyModeMemory``.  Only steps after each branch's eventual issue
    age are evaluated: the earlier prefix has already physically happened by
    the time this refresh is observed.  The operation covers every issue-age
    row before the final issue-age read, so its own computation is included
    in the subsequently observed delay.
    """

    if not certificates_by_issue_delay:
        return {}
    body_rows = _delayed_issue_action_certificates_impl(
        hazards_for_positions=_hazards_for_positions,
        player_x=player_x,
        player_y=player_y,
        actions=actions,
        issue_delay_frames=issue_delay_frames,
        pickup_delay_frames=pickup_delay_frames,
        horizon_frames=horizon_frames,
        bullets=(),
        lasers=(),
        enemy_bodies=enemy_bodies,
        snapshot_lag=0,
        player_scale_bits=player_scale_bits,
        laser_scale_bits=laser_scale_bits,
        pipeline_root=root,
        evaluate_after_issue_only=True,
    )
    recertified: dict[int, dict[str, RobustActionCertificate]] = {}
    for issue_delay in issue_delay_frames:
        base_row = certificates_by_issue_delay.get(issue_delay, {})
        body_row = body_rows.get(issue_delay, {})
        merged_row: dict[str, RobustActionCertificate] = {}
        for action in actions:
            base = base_row.get(action.name)
            body = body_row.get(action.name)
            if base is None or body is None:
                continue
            merged_row[action.name] = replace(
                base,
                worst_collisions=max(
                    base.worst_collisions,
                    body.worst_collisions,
                ),
                min_clearance=min(
                    base.min_clearance,
                    body.min_clearance,
                ),
                cvar_risk=base.cvar_risk + body.cvar_risk,
            )
        recertified[issue_delay] = merged_row
    return recertified


def _select_delayed_issue_action(
    *,
    certificates_by_issue_delay: dict[
        int, dict[str, RobustActionCertificate]
    ],
    issue_age: int,
    planned_action: str,
    preferred_action: str | None,
) -> tuple[str | None, RobustActionCertificate | None, str]:
    """Choose only from the hard row for the now-observed issue age."""

    row = certificates_by_issue_delay.get(issue_age)
    if row is None:
        return None, None, "issue_age_outside_certified_support"
    safe = {
        action: certificate
        for action, certificate in row.items()
        if (
            certificate.worst_collisions == 0
            and certificate.min_clearance > 0.0
        )
    }
    if not safe:
        return None, None, "observed_issue_row_empty"
    for reason, action in (
        ("planned_action_safe_for_observed_issue_age", planned_action),
        (
            "preferred_action_safe_for_observed_issue_age",
            preferred_action,
        ),
    ):
        if action is not None and action in safe:
            return action, safe[action], reason
    action, certificate = min(
        safe.items(),
        key=lambda item: (
            -item[1].min_clearance,
            item[1].cvar_risk,
            item[0],
        ),
    )
    return action, certificate, "best_margin_for_observed_issue_age"


def _build_ordinary_continuation_lease(
    *,
    gameplay_epoch: int,
    stage_route_index: int,
    action: str,
    mask: int,
    root_frame: int,
    issue_frame: int,
    horizon_frames: int,
    projection: OrdinaryFutureHazardProjection,
    projection_source: str,
    pipeline_root: LocalPipelineRoot,
    pickup_delay_support: tuple[int, ...],
    player_x: float,
    player_y: float,
    player_scale_bits: tuple[int, ...],
    enemy_bodies: tuple[EnemyBody, ...],
    certificate: RobustActionCertificate,
    fresh_geometry_frame: int,
    fresh_geometry_changed: bool,
) -> OrdinaryContinuationLease:
    """Retain one exact delayed predecessor as a no-write continuation."""

    if (
        projection.source_semantics_version.split("+", 1)[0]
        != ORDINARY_FUTURE_SOURCE_SEMANTICS_VERSION
    ):
        raise ValueError(
            "continuation lease requires exact active-hostile source "
            "trajectory coverage"
        )

    issue_delay = issue_frame - root_frame
    branches = enumerate_delayed_issue_pipeline_branches(
        root=pipeline_root,
        selected_action=action,
        issue_delay_frames=(issue_delay,),
        pickup_delay_frames=pickup_delay_support,
        horizon_frames=horizon_frames,
    )
    positions_by_step = _delayed_causal_pipeline_player_positions(
        root=pipeline_root,
        selected_action=action,
        issue_delay_frames=(issue_delay,),
        pickup_delay_frames=pickup_delay_support,
        horizon_frames=horizon_frames,
        player_x=player_x,
        player_y=player_y,
        player_scale_bits=player_scale_bits,
    )
    projection_offset = root_frame - projection.root_frame
    if projection_offset < 0:
        raise ValueError("lease root predates future-hazard projection")
    if projection_offset + horizon_frames > projection.horizon_frames:
        raise ValueError("future-hazard projection does not cover lease")
    certified_enemy_boxes_by_step = tuple(
        tuple(
            ContinuationCertifiedAabb(
                x=body.x + body.vx * step,
                y=body.y + body.vy * step,
                half_width=(
                    body.half_width
                    + body.uncertainty
                    + min(12.0, 0.5 * step)
                ),
                half_height=(
                    body.half_height
                    + body.uncertainty
                    + min(12.0, 0.5 * step)
                ),
            )
            for body in enemy_bodies
            if enemy_body_contact_enabled(body)
        )
        + tuple(
            ContinuationCertifiedAabb(
                x=sample.x,
                y=sample.y,
                half_width=(
                    sample.half_width
                    + sample.base_uncertainty
                    + sample.uncertainty_per_frame
                    * (projection_offset + step)
                ),
                half_height=(
                    sample.half_height
                    + sample.base_uncertainty
                    + sample.uncertainty_per_frame
                    * (projection_offset + step)
                ),
            )
            for sample in projection.aabb_samples(
                projection_offset + step
            )
        )
        for step in range(horizon_frames + 1)
    )
    return OrdinaryContinuationLease(
        lease_id=(
            f"{gameplay_epoch}:{stage_route_index}:{root_frame}:"
            f"{issue_frame}:{action}:{projection.digest[:16]}"
        ),
        gameplay_epoch=gameplay_epoch,
        stage_route_index=stage_route_index,
        action=action,
        mask=mask,
        root_frame=root_frame,
        issue_frame=issue_frame,
        horizon_frames=horizon_frames,
        projection_digest=projection.digest,
        projection_source=projection_source,
        projection_version=projection.version,
        pipeline_root=pipeline_root,
        issue_delay=issue_delay,
        pickup_delay_support=pickup_delay_support,
        branches=branches,
        positions_by_step=positions_by_step,
        certified_enemy_boxes_by_step=certified_enemy_boxes_by_step,
        minimum_clearance=certificate.min_clearance,
        fresh_geometry_frame=fresh_geometry_frame,
        fresh_geometry_changed=fresh_geometry_changed,
    )


def _contiguous_integer_ranges(
    values: tuple[int, ...],
) -> tuple[tuple[int, int], ...]:
    if not values:
        return ()
    ordered = tuple(sorted(set(values)))
    ranges: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append((start, previous))
        start = previous = value
    ranges.append((start, previous))
    return tuple(ranges)


def _direct_root_certificate_shadow(
    *,
    root: LocalPipelineRoot,
    player_x: float,
    player_y: float,
    previous_mask: int,
    delay_frames: tuple[int, ...],
    action_hold_frames: int,
    bullets: tuple[Bullet, ...],
    lasers: tuple[Laser, ...],
    enemy_bodies: tuple[EnemyBody, ...],
    snapshot_lag: int,
    player_scale_bits: tuple[int, ...],
    laser_scale_bits: tuple[int, ...],
    authoritative_certificates: tuple[
        RobustActionCertificate, ...
    ] = (),
) -> dict[str, object]:
    """Late, counterfactual explicit-root certificate with no action authority."""

    timing_accumulator = _LocalCertificateTimingAccumulator()
    started_ns = time.perf_counter_ns()
    certificates = _robust_action_certificates(
        player_x=player_x,
        player_y=player_y,
        previous_mask=previous_mask,
        actions=_PLANNER_ACTIONS,
        delay_frames=delay_frames,
        action_hold_frames=action_hold_frames,
        bullets=bullets,
        lasers=lasers,
        enemy_bodies=enemy_bodies,
        snapshot_lag=snapshot_lag,
        player_scale_bits=player_scale_bits,
        laser_scale_bits=laser_scale_bits,
        pipeline_root=root,
        timing_accumulator=timing_accumulator,
    )
    wall_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
    authoritative_by_action = {
        certificate.action: certificate
        for certificate in authoritative_certificates
    }
    direct_safe_actions = tuple(
        action.name
        for action in _PLANNER_ACTIONS
        if (
            certificates[action.name].worst_collisions == 0
            and certificates[action.name].min_clearance >= 0.0
        )
    )
    authoritative_safe_actions = tuple(
        action.name
        for action in _PLANNER_ACTIONS
        if (
            action.name in authoritative_by_action
            and authoritative_by_action[action.name].worst_collisions == 0
            and authoritative_by_action[action.name].min_clearance >= 0.0
        )
    )
    return {
        "role": "post_issue_shadow_no_action_authority",
        "status": "complete",
        "computed_after_input": True,
        "wall_ms": wall_ms,
        "timing": _local_certificate_timing_record(
            timing_accumulator.snapshot()
        ),
        "direct_safe_actions": direct_safe_actions,
        "authoritative_safe_actions": authoritative_safe_actions,
        "safe_action_set_changed": (
            bool(authoritative_by_action)
            and direct_safe_actions != authoritative_safe_actions
        ),
        "certificates": tuple(
            _robust_action_certificate_record(certificates[action.name])
            for action in _PLANNER_ACTIONS
        ),
    }


def _estimate_live_action_hold(frame_deltas: tuple[int, ...]) -> int:
    operational = sorted(delta for delta in frame_deltas if 0 < delta < 120)
    if not operational:
        return LIVE_ACTION_HOLD_DEFAULT
    rank = max(0, math.ceil(0.9 * len(operational)) - 1)
    return max(
        PLANNER_ACTION_HOLD,
        min(LIVE_ACTION_HOLD_MAX, operational[rank]),
    )


def _terminal_threat_scores(
    nodes: list[SearchNode],
    *,
    start_step: int,
    end_step: int,
    control_delay_frames: int,
    bullet_frames: tuple[tuple[np.ndarray, ...], ...],
    laser_frames: tuple[tuple[Laser, ...], ...],
    enemy_bodies: tuple[EnemyBody, ...],
) -> dict[SearchNode, tuple[int, float]]:
    return _terminal_threat_scores_impl(
        nodes,
        hazards_for_positions=_hazards_for_positions,
        start_step=start_step,
        end_step=end_step,
        control_delay_frames=control_delay_frames,
        bullet_frames=bullet_frames,
        laser_frames=laser_frames,
        enemy_bodies=enemy_bodies,
    )


def _prepare_local_planner_pass(
    request: LocalPlannerRequest,
    *,
    timing_accumulator: _LocalCertificateTimingAccumulator,
) -> PlannerPassPreparation:
    return prepare_planner_pass(
        request,
        planner_action_names=frozenset(
            action.name for action in _PLANNER_ACTIONS
        ),
        terminal_threat_degeneracy=_terminal_threat_degeneracy,
        item_objectives_enabled=ITEM_OBJECTIVES_ENABLED,
        select_items=_select_items,
        focus_mask=FOCUS,
        unfocused_cardinal_speed=UNFOCUSED_CARDINAL_SPEED,
        build_laser_timeline=_build_packed_laser_collision_frames,
        actions=_PLANNER_ACTIONS,
        certificate_provider=_robust_action_certificates,
        timing_accumulator=timing_accumulator,
    )


def _planner_pass_dependencies() -> PlannerPassDependencies:
    """Bind the current controller backends and patch seams for one pass."""

    return PlannerPassDependencies(
        planner_actions=_PLANNER_ACTIONS,
        local_beam_reducer=_LOCAL_BEAM_REDUCER,
        bomb_mask=BOMB,
        focus_mask=FOCUS,
        shot_mask=SHOT,
        collection_half_width=COLLECTION_HALF_WIDTH,
        item_safety_clearance=ITEM_SAFETY_CLEARANCE,
        player_radius=PLAYER_RADIUS,
        playfield_left=PLAYFIELD_LEFT,
        playfield_right=PLAYFIELD_RIGHT,
        playfield_top=PLAYFIELD_TOP,
        playfield_bottom=PLAYFIELD_BOTTOM,
        unfocused_cardinal_speed=UNFOCUSED_CARDINAL_SPEED,
        unfocused_diagonal_speed=UNFOCUSED_DIAGONAL_SPEED,
        boundary_control_reserve_deficit=(
            _boundary_control_reserve_deficit
        ),
        boundary_risk=_boundary_risk,
        build_bullet_frames=_build_bullet_frames,
        control_prefix_hazards=_control_prefix_hazards,
        directions_opposed=_directions_opposed,
        hazards_for_positions=_hazards_for_positions,
        minimum_travel_frames=_minimum_travel_frames,
        node_key=_node_key,
        project_item=_project_item,
        advance_planner_action=_advance_planner_action,
        project_player_for_read_lag=_project_player_for_read_lag,
        robust_action_certificates=_robust_action_certificates,
        terminal_threat_scores=_terminal_threat_scores,
        assemble_local_decision=assemble_local_decision,
        run_baseline_beam=run_baseline_beam,
        select_progress_action=select_progress_action,
    )


def _run_local_planner_pass(
    request: LocalPlannerRequest,
    preparation: PlannerPassPreparation,
    *,
    _certificate_timing_accumulator: (
        _LocalCertificateTimingAccumulator
    ),
) -> Decision | _PlannerModeTransition:
    """Preserve the historical controller patch seam for one planner pass."""

    return _run_local_planner_pass_impl(
        request,
        preparation,
        dependencies=_planner_pass_dependencies(),
        _certificate_timing_accumulator=(
            _certificate_timing_accumulator
        ),
    )


def _contradiction_key(candidate: Decision) -> tuple[object, ...]:
    return (
        candidate.robust_collisions,
        max(-candidate.robust_min_clearance, 0.0),
        -candidate.robust_min_clearance,
        candidate.terminal_threat_collisions,
        max(-candidate.terminal_threat_min_clearance, 0.0),
        max(-candidate.min_clearance, 0.0),
        candidate.score,
    )


def _choose_action_decision_request(
    request: LocalPlannerRequest,
) -> Decision:
    """Execute planner passes and return the compatibility decision."""

    timing = _LocalCertificateTimingAccumulator()
    preparation = _prepare_local_planner_pass(
        request,
        timing_accumulator=timing,
    )
    result = _run_local_planner_pass(
        request,
        preparation,
        _certificate_timing_accumulator=timing,
    )
    if isinstance(result, _PlannerModeTransition):
        retry_preparation = _prepare_local_planner_pass(
            result.next_request,
            timing_accumulator=timing,
        )
        retry = _run_local_planner_pass(
            result.next_request,
            retry_preparation,
            _certificate_timing_accumulator=timing,
        )
        if isinstance(retry, _PlannerModeTransition):
            raise AssertionError("relaxed planner mode cannot transition again")
        if _contradiction_key(retry) < _contradiction_key(
            result.current_decision
        ):
            decision = replace(
                retry,
                viability_safe_action_count=(
                    result.original_allowed_action_count
                ),
                viability_constraint_relaxed=True,
            )
        else:
            decision = result.current_decision
        return replace(
            decision,
            local_certificate_timing=timing.snapshot(),
        )
    return result


def choose_local_proposal_request(
    request: LocalPlannerRequest,
) -> LocalProposal:
    """Build a proposal that has not yet crossed the issue boundary."""

    return LocalProposal.from_decision(
        _choose_action_decision_request(request)
    )


def _local_planner_request_from_capture(
    *,
    capture: CapturedIteration,
    pipeline_root: LocalPipelineRoot | None,
    action_hold_frames: int,
    corridor_target: tuple[float, float, int] | None,
    policy_guidance: object,
    allowed_action_authority: str | None,
    horizon: int,
    threat_horizon: int,
    beam_width: int,
    losing_control_reserve: bool,
    preserve_previous_direction_inertia: bool,
    damage_target_x: float | None = None,
    damage_target_half_width: float = 0.0,
    damageable: bool = False,
) -> LocalPlannerRequest:
    """Assemble one immutable local request from the captured version."""

    return LocalPlannerRequest(
        physical=PhysicalHazardSnapshot(
            player_x=capture.player_x,
            player_y=capture.player_y,
            bullets=capture.bullets,
            lasers=capture.lasers,
            time_scale_schedule=capture.time_scale_schedule,
            enemy_bodies=capture.enemy_bodies,
            items=capture.items,
            snapshot_lag=capture.player_to_hazard_lag,
        ),
        actuator=ActuatorPipeline(
            previous_direction=capture.previous_direction,
            can_bomb=capture.can_bomb,
            previous_focus=bool(capture.held_desired_mask & FOCUS),
            control_delay_frames=capture.control_delay_frames,
            control_delay_candidates=capture.delay_estimate.support,
            action_hold_frames=action_hold_frames,
            local_pipeline_root=pipeline_root,
        ),
        guidance=GlobalGuidance(
            target_x=(
                corridor_target[0] if corridor_target is not None else None
            ),
            target_y=(
                corridor_target[1] if corridor_target is not None else None
            ),
            target_deadline=(
                corridor_target[2] if corridor_target is not None else None
            ),
            allowed_first_actions=policy_guidance.allowed_first_actions,
            allowed_action_authority=allowed_action_authority,
            allow_coarse_viability_relaxation=(
                _allow_coarse_viability_relaxation(
                    allowed_action_authority
                )
            ),
            viability_repair_volumes=policy_guidance.repair_volumes,
            viability_recovery_distances=policy_guidance.recovery_distances,
            viability_safety_actions=policy_guidance.safety_actions,
            viability_safety_state_value=policy_guidance.safety_state_value,
            viability_survival_actions=policy_guidance.survival_actions,
            viability_survival_frames=policy_guidance.survival_frames,
            viability_survival_bottleneck_margin=(
                policy_guidance.survival_bottleneck_margin
            ),
            viability_position_error=policy_guidance.position_error,
        ),
        config=PlannerConfig(
            horizon=horizon,
            threat_horizon=threat_horizon,
            beam_width=beam_width,
            losing_control_reserve=losing_control_reserve,
            preserve_previous_direction_inertia=(
                preserve_previous_direction_inertia
            ),
        ),
        objective=ObjectiveContext(
            power=capture.power,
            bombs=capture.bombs,
            damage_target_x=damage_target_x,
            damage_target_half_width=damage_target_half_width,
            damageable=damageable,
        ),
    )


def choose_action_request(request: LocalPlannerRequest) -> Decision:
    """Compatibility view of a grouped local proposal."""

    return choose_local_proposal_request(request).decision


def choose_action(
    *,
    player_x: float,
    player_y: float,
    bullets: tuple[Bullet, ...],
    lasers: tuple[Laser, ...],
    previous_direction: int,
    can_bomb: bool,
    enemy_bodies: tuple[EnemyBody, ...] = (),
    items: tuple[Item, ...] = (),
    power: float = 0.0,
    bombs: float = 0.0,
    previous_focus: bool = True,
    local_pipeline_root: LocalPipelineRoot | None = None,
    snapshot_lag: int = 0,
    control_delay_frames: int = CONTROL_DELAY_FRAMES,
    control_delay_candidates: tuple[int, ...] | None = None,
    action_hold_frames: int = PLANNER_ACTION_HOLD,
    horizon: int = PLANNER_HORIZON,
    threat_horizon: int | None = None,
    beam_width: int = PLANNER_BEAM_WIDTH,
    target_x: float | None = None,
    target_y: float | None = None,
    target_deadline: int | None = None,
    allowed_first_actions: tuple[str, ...] | None = None,
    viability_repair_volumes: tuple[tuple[str, int], ...] = (),
    viability_recovery_distances: tuple[tuple[str, float], ...] = (),
    viability_safety_actions: tuple[str, ...] = (),
    viability_safety_state_value: float | None = None,
    viability_survival_actions: tuple[str, ...] = (),
    viability_survival_frames: int | None = None,
    viability_survival_bottleneck_margin: float | None = None,
    viability_position_error: float = 0.0,
    damage_target_x: float | None = None,
    damage_target_half_width: float = 0.0,
    damageable: bool = False,
    recovery_control_reserve: bool = True,
    losing_control_reserve: bool = False,
    preloss_continuation_preference: bool = False,
    preserve_previous_direction_inertia: bool = True,
    beam_dedup_mode: str = "quantized",
    relax_stale_viability_contradiction: bool = False,
    enforce_fresh_viability_intersection: bool = True,
    time_scale_schedule: Th08TimeScaleSchedule | None = None,
) -> Decision:
    """Compatibility wrapper for callers not yet migrated to grouped input.

    Omitting ``time_scale_schedule`` preserves historical unit-scale fixtures
    only for this request's finite horizon. Live grouped callers must carry
    observed phase-specific coverage instead.
    """

    if time_scale_schedule is None:
        maximum_delay = max(
            control_delay_candidates or (control_delay_frames,)
        )
        required_scale_horizon = max(
            control_delay_frames + (threat_horizon or horizon),
            maximum_delay + action_hold_frames,
        )
        time_scale_schedule = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=required_scale_horizon,
            provenance="historical_flat_wrapper_unit_assumption",
        )

    return choose_action_request(
        LocalPlannerRequest(
            physical=PhysicalHazardSnapshot(
                player_x=player_x,
                player_y=player_y,
                bullets=bullets,
                lasers=lasers,
                time_scale_schedule=time_scale_schedule,
                enemy_bodies=enemy_bodies,
                items=items,
                snapshot_lag=snapshot_lag,
            ),
            actuator=ActuatorPipeline(
                previous_direction=previous_direction,
                can_bomb=can_bomb,
                previous_focus=previous_focus,
                local_pipeline_root=local_pipeline_root,
                control_delay_frames=control_delay_frames,
                control_delay_candidates=control_delay_candidates,
                action_hold_frames=action_hold_frames,
            ),
            guidance=GlobalGuidance(
                target_x=target_x,
                target_y=target_y,
                target_deadline=target_deadline,
                allowed_first_actions=allowed_first_actions,
                viability_repair_volumes=viability_repair_volumes,
                viability_recovery_distances=(
                    viability_recovery_distances
                ),
                viability_safety_actions=viability_safety_actions,
                viability_safety_state_value=(
                    viability_safety_state_value
                ),
                viability_survival_actions=viability_survival_actions,
                viability_survival_frames=viability_survival_frames,
                viability_survival_bottleneck_margin=(
                    viability_survival_bottleneck_margin
                ),
                viability_position_error=viability_position_error,
            ),
            config=PlannerConfig(
                horizon=horizon,
                threat_horizon=threat_horizon,
                beam_width=beam_width,
                recovery_control_reserve=recovery_control_reserve,
                losing_control_reserve=losing_control_reserve,
                preloss_continuation_preference=(
                    preloss_continuation_preference
                ),
                preserve_previous_direction_inertia=(
                    preserve_previous_direction_inertia
                ),
                beam_dedup_mode=beam_dedup_mode,
                relax_stale_viability_contradiction=(
                    relax_stale_viability_contradiction
                ),
                enforce_fresh_viability_intersection=(
                    enforce_fresh_viability_intersection
                ),
            ),
            objective=ObjectiveContext(
                power=power,
                bombs=bombs,
                damage_target_x=damage_target_x,
                damage_target_half_width=damage_target_half_width,
                damageable=damageable,
            ),
        )
    )


def _enemy_sensor_submit_due(
    *,
    current_frame: int,
    last_submit_frame: int,
    pending: bool,
    interval_frames: int = ENEMY_SENSOR_INTERVAL_FRAMES,
) -> bool:
    if interval_frames <= 0:
        raise ValueError("enemy sensor interval must be positive")
    return (
        not pending
        and current_frame - last_submit_frame >= interval_frames
    )


def _write_run_summary(
    trace_sink: TraceSink,
    *,
    last_frame: int | None,
    counter_gaps: int,
    hit_count: int,
    termination_reason: str,
) -> None:
    trace_sink.summary(
        last_frame=last_frame,
        counter_gaps=counter_gaps,
        hit_count=hit_count,
        termination_reason=termination_reason,
    )


def _terminate_unsafe_instrumented_target(
    *,
    api: object,
    verified_image_path: Path,
    trace_sink: TraceSink,
    phase: str,
) -> None:
    """Fail closed when a runtime hook cannot prove exact rollback."""

    from th08_automation.practice_windows import (
        configure_supervisor_api,
        terminate_exact_target,
    )

    configure_supervisor_api(api)
    terminated = terminate_exact_target(api, verified_image_path)
    trace_sink.emit(
        {
            "kind": "enemy_lifecycle_probe_unsafe_target_termination",
            "schema": ENEMY_LIFECYCLE_PROBE_SCHEMA,
            "phase": phase,
            "terminated": terminated,
            "verified_image_path": str(verified_image_path),
            "action_authority": False,
        },
        flush=True,
    )
    if not terminated:
        raise RuntimeError(
            "unsafe lifecycle instrumentation target was not available for "
            "verified termination"
        )


def _prepare_live_run(args: argparse.Namespace) -> None:
    if not args.armed:
        raise RuntimeError("live control requires the explicit --armed flag")
    if min(
        args.corridor_every,
        args.corridor_lookahead,
        args.corridor_max_age,
    ) <= 0:
        raise ValueError("corridor timing arguments must be positive")
    if args.wait_timeout <= 0.0:
        raise ValueError("wait timeout must be positive")
    if args.stop_after_hits < 0 or args.post_hit_frames < 0:
        raise ValueError("hit stopping arguments cannot be negative")
    if (
        args.safety_value_horizon < 0
        or args.safety_value_horizon > TH08_CORRIDOR_CONFIG.horizon_frames
        or (
            args.safety_value_horizon
            % TH08_CORRIDOR_CONFIG.frames_per_layer
        )
    ):
        raise ValueError(
            "safety-value horizon must be zero or complete corridor layers "
            "within the global horizon"
        )
    if not (
        LIVE_CONTROL_DELAY_MIN
        <= args.control_delay_frames
        <= LIVE_CONTROL_DELAY_MAX
    ):
        raise ValueError(
            "initial control delay must be within the live estimator bounds"
        )
    if args.auto_confirm_every < 0 or args.auto_confirm_idle_frames < 0:
        raise ValueError("auto-confirm timing arguments cannot be negative")
    if args.input_clock_shadow_sample_ms <= 0.0:
        raise ValueError("input-clock shadow sample cadence must be positive")
    if args.local_pipeline_root_shadow_every < 0:
        raise ValueError(
            "local pipeline root shadow cadence cannot be negative"
        )
    runtime_ecl_static_image = getattr(
        args,
        "runtime_ecl_static_image",
        None,
    )
    runtime_ecl_static_sha256 = getattr(
        args,
        "runtime_ecl_static_sha256",
        None,
    )
    if (runtime_ecl_static_image is None) != (
        runtime_ecl_static_sha256 is None
    ):
        raise ValueError(
            "runtime ECL identity requires both a static image and SHA-256"
        )
    if (
        runtime_ecl_static_image is not None
        and args.expected_stage is None
    ):
        raise ValueError(
            "runtime ECL identity requires an explicit expected stage"
        )
    enable_finalb_scale_source_authority = bool(
        getattr(args, "enable_finalb_scale_source_authority", False)
    )
    if enable_finalb_scale_source_authority and (
        args.difficulty != 3 or args.expected_stage not in {0, 7}
    ):
        raise ValueError(
            "Final-B scale-source authority requires Lunatic full route or "
            "stage 7"
        )
    if enable_finalb_scale_source_authority and not args.no_bomb:
        raise ValueError(
            "Final-B scale-source authority requires explicit hard no-Bomb"
        )
    if (
        getattr(args, "kill_before_saturation", False)
        and not args.no_bomb
    ):
        raise ValueError(
            "kill-before-saturation requires explicit hard no-Bomb"
        )
    if (
        getattr(args, "ordinary_preexhaustion_authority", False)
        and not args.no_bomb
    ):
        raise ValueError(
            "ordinary pre-exhaustion authority requires explicit hard no-Bomb"
        )
    if enable_finalb_scale_source_authority and (
        runtime_ecl_static_image is None
        or runtime_ecl_static_sha256 is None
    ):
        raise ValueError(
            "Final-B scale-source authority requires exact runtime ECL identity"
        )
    _configure_local_hazard_backend(args.local_hazard_backend)
    _configure_local_beam_reducer(args.local_beam_reducer)
    _configure_local_bullet_decoder(args.bullet_decode_backend)
    if (
        args.stage_transition_timeout <= 0.0
        or args.terminal_inactive_grace <= 0.0
    ):
        raise ValueError("scene transition timing arguments must be positive")


def run(args: argparse.Namespace) -> int:
    _prepare_live_run(args)
    with LiveSession(
        output_path=args.output,
        requested_pid=args.pid,
        target_exe=TARGET_EXE,
    ) as session:
        return _run_live_session(args, session)


def _run_live_session(
    args: argparse.Namespace,
    session: LiveSession,
) -> int:
    api = session.api
    pid = session.pid
    reader = session.reader
    output = session.output
    trace_sink = TraceSink(output)
    previous_mask = 0
    previous_direction = 0
    previous_counter: int | None = None
    previous_phase: int | None = None
    previous_bombs: float | None = None
    previous_power: float | None = None
    previous_action_phase: int | None = None
    last_bomb_counter = -10000
    gaps = 0
    iterations = 0
    diagnostic_scale_fallback_key: tuple[object, ...] | None = None
    hit_count = 0
    stop_after_frame: int | None = None
    gameplay_armed = False
    termination_reason = "duration"
    corridor_future: Future[CorridorSolution] | None = None
    ordinary_future_source_future: (
        Future[OrdinaryFutureSourceCaptureResult] | None
    ) = None
    ordinary_future_source_result: (
        OrdinaryFutureSourceCaptureResult | None
    ) = None
    ordinary_future_source_last_submit = CORRIDOR_INITIAL_SUBMIT_FRAME
    ordinary_causal_delayed_last_scan: (
        tuple[tuple[int, int], int] | None
    ) = None
    ordinary_continuation_lease: OrdinaryContinuationLease | None = None
    enemy_future: Future[EnemyPoolSnapshot] | None = None
    enemy_snapshot: EnemyPoolSnapshot | None = None
    enemy_last_submit = CORRIDOR_INITIAL_SUBMIT_FRAME
    corridor_solution: CorridorSolution | None = None
    corridor_pending_solution: CorridorSolution | None = None
    corridor_last_submit = CORRIDOR_INITIAL_SUBMIT_FRAME
    corridor_commitment = CorridorCommitment()
    corridor_context: tuple[int, int, int | None] | None = None
    enemy_body_memory = EnemyBodyModeMemory(
        maximum_age_frames=ENEMY_DORMANT_MEMORY_FRAMES
    )
    enemy_background_memory = EnemyBodyModeMemory(
        maximum_age_frames=ENEMY_DORMANT_MEMORY_FRAMES
    )
    spell_enemy_body_memory = EnemyBodyModeMemory(
        maximum_age_frames=ENEMY_DORMANT_MEMORY_FRAMES
    )
    enemy_body_memories = (
        enemy_body_memory,
        enemy_background_memory,
        spell_enemy_body_memory,
    )
    boss_phase_tracker = PhaseProgressTracker()
    gameplay_epoch = 0
    stage_successors = dict(ROUTE2_STAGE_SUCCESSORS)
    if args.terminal_stage is not None:
        stage_successors.pop(args.terminal_stage, None)
    scene_clock = SceneClockCoordinator.create(
        auto_confirm_interval_frames=args.auto_confirm_every,
        auto_confirm_idle_frames=args.auto_confirm_idle_frames,
        stage_successors=stage_successors,
        transition_timeout_seconds=args.stage_transition_timeout,
        terminal_grace_seconds=args.terminal_inactive_grace,
        input_clock_shadow=args.input_clock_boundary_shadow,
    )
    auto_confirm = scene_clock.auto_confirm
    scene_guard = scene_clock.scene_guard
    input_clock_tracker = scene_clock.input_clock_tracker
    last_frame_progress = time.perf_counter()
    last_frozen_confirm = float("-inf")
    input_clock_repeat_frame: int | None = None
    input_clock_repeat_polls = 0
    input_clock_wall_cut_frame: int | None = None
    input_clock_last_sample_ns = 0
    input_clock_last_message_key: tuple[object, ...] | None = None
    input_clock_delay_support: tuple[int, ...] = (
        args.control_delay_frames,
    )
    decision_frame_deltas: deque[int] = deque(maxlen=120)
    delay_estimator = AdaptiveControlDelay(
        supported_mask=SUPPORTED_INPUT_MASK,
        minimum=LIVE_CONTROL_DELAY_MIN,
        maximum=LIVE_CONTROL_DELAY_MAX,
        window=LIVE_CONTROL_DELAY_WINDOW,
        guard_frames=LIVE_CONTROL_DELAY_GUARD_FRAMES,
    )
    corridor_policy_lead = AsyncPolicyLead(
        initial_frames=CORRIDOR_POLICY_LEAD_INITIAL_FRAMES,
        overlap_frames=CORRIDOR_POLICY_OVERLAP_FRAMES,
        minimum_frames=CORRIDOR_POLICY_MINIMUM_LEAD_FRAMES,
        maximum_frames=CORRIDOR_POLICY_MAXIMUM_LEAD_FRAMES,
    )
    ecl_instruction_cache = EclInstructionCache()
    trace_enemy_mode_transitions = bool(
        getattr(args, "trace_enemy_mode_transitions", False)
    )
    trace_enemy_lifecycle_events = bool(
        getattr(args, "trace_enemy_lifecycle_events", False)
    )
    kill_before_saturation = bool(
        getattr(args, "kill_before_saturation", False)
    )
    ordinary_preexhaustion_authority = bool(
        getattr(args, "ordinary_preexhaustion_authority", False)
    )
    ordinary_safety_value_horizon = (
        0
        if ordinary_preexhaustion_authority
        else args.safety_value_horizon
    )

    enemy_lifecycle_probe: EnemyLifecycleProbe | None = None
    enemy_lifecycle_probe_last_serial: int | None = None
    enemy_lifecycle_probe_installation: dict[str, object] = {
        "schema": ENEMY_LIFECYCLE_PROBE_SCHEMA,
        "role": "trace_only_no_action_authority",
        "status": "disabled",
        "action_authority": False,
    }
    verified_image_path: Path | None = None
    diagnostic_continue_root_only_scale = bool(
        getattr(
            args,
            "diagnostic_continue_root_only_scale",
            False,
        )
    )
    runtime_ecl_identity_service: RuntimeEclIdentityService | None = None
    finalb_scale_schedule_authority: (
        FinalBScaleScheduleAuthority | None
    ) = None
    no_scale_writer_schedule_authority: (
        NoScaleWriterScheduleAuthority | None
    ) = None
    runtime_ecl_static_image = getattr(
        args,
        "runtime_ecl_static_image",
        None,
    )
    runtime_ecl_static_path: Path | None = None
    ordinary_future_ecl = None
    if runtime_ecl_static_image is not None:
        runtime_ecl_static_path = runtime_ecl_static_image
        if not runtime_ecl_static_path.is_absolute():
            runtime_ecl_static_path = (
                Path(__file__).resolve().parents[2]
                / runtime_ecl_static_path
            )
        runtime_ecl_identity_service = RuntimeEclIdentityService(
            static_image=runtime_ecl_static_path.read_bytes(),
            static_label=runtime_ecl_static_image.as_posix(),
            expected_static_sha256=args.runtime_ecl_static_sha256,
            expected_route_id=2,
            expected_difficulty_index=args.difficulty,
            expected_stage_route_index=args.expected_stage,
        )
        runtime_ecl = parse_ecl(runtime_ecl_static_path)
        if ordinary_preexhaustion_authority:
            ordinary_future_ecl = runtime_ecl
        if args.expected_stage in NO_SCALE_WRITER_STAGE_ROUTE_INDICES:
            no_scale_writer_schedule_authority = (
                NoScaleWriterScheduleAuthority(
                    runtime_ecl,
                    expected_static_sha256=args.runtime_ecl_static_sha256,
                    expected_route_id=2,
                    expected_difficulty_index=args.difficulty,
                    expected_stage_route_index=args.expected_stage,
                    horizon_frames=DIAGNOSTIC_ROOT_ONLY_SCALE_HORIZON,
                )
            )
            if not no_scale_writer_schedule_authority.static_eligible:
                no_scale_writer_schedule_authority = None
        if getattr(args, "enable_finalb_scale_source_authority", False):
            finalb_scale_schedule_authority = (
                FinalBScaleScheduleAuthority(
                    FinalBScaleSourceTraceService(
                        FinalBScaleSourceTraceConfiguration(
                            static_path=runtime_ecl_static_path,
                            expected_static_sha256=(
                                args.runtime_ecl_static_sha256
                            ),
                            expected_route_id=2,
                            expected_difficulty_index=args.difficulty,
                            expected_stage_route_index=args.expected_stage,
                        )
                    )
                )
            )
    previous_iteration_ms: float | None = None
    previous_trace_ms: float | None = None
    service_resources = LiveServiceResources(
        local_only=args.local_only,
        viability_audit_enabled=args.viability_audit_dir is not None,
    )
    corridor_executor = service_resources.corridor_executor
    audit_executor = service_resources.audit_executor
    enemy_executor = service_resources.enemy_executor
    future_source_executor = service_resources.future_source_executor
    issue_controller = IssueController(
        api=api,
        pid=pid,
        supported_mask=SUPPORTED_INPUT_MASK,
        forbidden_mask=BOMB if args.no_bomb else 0,
    )
    policy_coordinator = PolicyCoordinator()

    def input_clock_policy_snapshot() -> dict[str, object]:
        return {
            "published_solution_present": corridor_solution is not None,
            "pending_solution_present": corridor_pending_solution is not None,
            "solve_future_pending": (
                corridor_future is not None and not corridor_future.done()
            ),
        }

    def record_input_clock_sample(
        *,
        sample: dict[str, object],
        observation: SemanticClockObservation,
        events: tuple[SemanticClockEvent, ...],
        frame: int,
        stage_route_index: int,
        frozen_seconds: float,
        repeat_poll_count: int,
        triggers: tuple[str, ...],
    ) -> None:
        record = {
            "kind": "input_clock_shadow_observation",
            "role": INPUT_CLOCK_SHADOW_ROLE,
            "frame": frame,
            "stage_route_index": stage_route_index,
            "gameplay_epoch": gameplay_epoch,
            "frozen_seconds": frozen_seconds,
            "repeat_poll_count": repeat_poll_count,
            "triggers": triggers,
            "held_desired_mask": previous_mask,
            "delay_support": input_clock_delay_support,
            "active_episode_id": (
                input_clock_tracker.active_episode_id
                if input_clock_tracker is not None
                else None
            ),
            "policy_retirement_hypothesis": input_clock_policy_snapshot(),
            "observation": _serialize_semantic_clock_observation(
                observation
            ),
            "sample": sample,
        }
        records = [record]
        for event in events:
            event_record = _serialize_semantic_clock_event(event)
            event_record.update(
                {
                    "stage_route_index": stage_route_index,
                    "gameplay_epoch": gameplay_epoch,
                    "held_desired_mask": previous_mask,
                    "delay_support": input_clock_delay_support,
                    "policy_retirement_hypothesis": (
                        input_clock_policy_snapshot()
                    ),
                    "sample": sample,
                }
            )
            records.append(event_record)
        trace_sink.emit_many(records, flush=True)

    try:
        identity = verify_target(reader)
        verified_image_path = Path(str(identity["image_path"]))
        trace_sink.emit({"kind": "identity", **identity})
        if trace_enemy_lifecycle_events:
            try:
                enemy_lifecycle_probe = EnemyLifecycleProbe.install(
                    api,
                    pid,
                )
                enemy_lifecycle_probe_installation = (
                    enemy_lifecycle_probe.installation_record()
                )
            except EnemyLifecycleProbeUnsafeStateError as error:
                trace_sink.emit(
                    {
                        "kind": "enemy_lifecycle_probe_activation_error",
                        "schema": ENEMY_LIFECYCLE_PROBE_SCHEMA,
                        "unsafe_target_state": True,
                        "error": f"{type(error).__name__}: {error}",
                        "action_authority": False,
                    },
                    flush=True,
                )
                if verified_image_path is None:
                    raise RuntimeError(
                        "unsafe lifecycle activation has no verified target "
                        "identity"
                    ) from error
                _terminate_unsafe_instrumented_target(
                    api=api,
                    verified_image_path=verified_image_path,
                    trace_sink=trace_sink,
                    phase="activation",
                )
                raise
            except Exception as error:
                enemy_lifecycle_probe_installation = {
                    "schema": ENEMY_LIFECYCLE_PROBE_SCHEMA,
                    "role": "trace_only_no_action_authority",
                    "status": "unavailable",
                    "error": f"{type(error).__name__}: {error}",
                    "action_authority": False,
                }
        trace_sink.emit(
            {
                    "kind": "controller_config",
                    "bomb_policy": (
                        "disabled"
                        if args.no_bomb
                        else (
                            "normal_and_deathbomb"
                            if args.normal_bomb
                            else "deathbomb_only"
                        )
                    ),
                    "item_policy": (
                        "survival_only_passive_collection"
                        if not ITEM_OBJECTIVES_ENABLED
                        else "certified_viable_tiebreaker"
                    ),
                    "item_sensor_enabled": (
                        ITEM_OBJECTIVES_ENABLED or bool(args.trace_items)
                    ),
                    "item_sensor_role": (
                        "control_objective"
                        if ITEM_OBJECTIVES_ENABLED
                        else (
                            "explicit_trace_only"
                            if args.trace_items
                            else "disabled_no_control_consumer"
                        )
                    ),
                    "boss_phase_sensor": (
                        "native_registry_health_timer_and_damage_gate"
                    ),
                    "damage_objective": (
                        "shadow_lexicographic_inside_fresh_safe_set"
                    ),
                    "ordinary_preexhaustion_authority": {
                        "enabled": ordinary_preexhaustion_authority,
                        "scope": "ordinary_nonspell_only",
                        "authority": ORDINARY_PREEXHAUSTION_AUTHORITY,
                        "empty_kernel_causal_hold_authority": (
                            ORDINARY_CAUSAL_HOLD_AUTHORITY
                        ),
                        "delayed_issue_authority": (
                            ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                        ),
                        "terminal_continuation_lease_authority": (
                            ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY
                        ),
                        "hard_inputs": (
                            "observed_active_held_pending_pipeline_root_"
                            "pickup_delay_support_completed_future_policy_"
                            "exact_hazard_version"
                        ),
                        "hostile_birth_uncertainty": (
                            "future_hazard_coverage_required_or_no_"
                            "action_authority"
                        ),
                        "future_time_scale_support": "exact_unit_only",
                        "predecessor": (
                            "set_valued_hazard_space_all_pickup_branches_"
                            "to_next_publication_epoch"
                        ),
                        "empty_kernel_fallback": (
                            "rolling_exact_held_no_write_renewal_then_"
                            "new_direction_only_through_a_new_delayed_"
                            "predecessor"
                        ),
                        "recovery_role": (
                            "directional_set_distance_diagnostic_only"
                        ),
                        "fresh_collision_certificate_is_final_gate": True,
                        "shadow_future_promoted": False,
                    },
                    "kill_before_saturation": {
                        "enabled": kill_before_saturation,
                        "role": (
                            "observed_enemy_objective_preference_inside_"
                            "causal_and_fresh_issue_safe_set"
                            if kill_before_saturation
                            else "disabled"
                        ),
                        "complete_action": (
                            "observed_target_alignment_then_same_direction_"
                            "unfocused"
                        ),
                        "fallback": (
                            "preserve_survival_baseline_on_missing_or_"
                            "losing_global_query_or_fresh_rejection"
                        ),
                        "global_shadow_is_hard_authority": False,
                        "upcoming_spawn_forecast": {
                            "enabled": False,
                            "reason": (
                                "withheld_after_noncausal_timeline_lifecycle_"
                                "counterexample"
                            ),
                        },
                        "hard_no_bomb_required": True,
                    },
                    "enemy_body_sensor": (
                        "synchronous_latent_contact_prefix_plus_"
                        "async_enabled_tail_with_observed_world_motion"
                    ),
                    "enemy_body_synchronous_prefix_slots": (
                        ENEMY_LOCAL_PREFIX_SIZE
                    ),
                    "enemy_body_dormant_memory_frames": (
                        ENEMY_DORMANT_MEMORY_FRAMES
                    ),
                    "enemy_body_max_observed_world_speed": (
                        ENEMY_MAX_OBSERVED_WORLD_SPEED
                    ),
                    "control_delay_policy": (
                        "adaptive_end_to_end_distribution_robust_mpc"
                    ),
                    "control_delay_default": args.control_delay_frames,
                    "control_delay_min": LIVE_CONTROL_DELAY_MIN,
                    "control_delay_max": LIVE_CONTROL_DELAY_MAX,
                    "control_delay_window": LIVE_CONTROL_DELAY_WINDOW,
                    "control_delay_guard_frames": (
                        LIVE_CONTROL_DELAY_GUARD_FRAMES
                    ),
                    "enemy_lifecycle_probe": (
                        enemy_lifecycle_probe_installation
                    ),
                    "maximum_sensor_epoch_extent_frames": (
                        MAX_SENSOR_EPOCH_EXTENT_FRAMES
                    ),
                    "maximum_action_contiguous_advance_frames": (
                        MAX_ACTION_CONTIGUOUS_ADVANCE_FRAMES
                    ),
                    "input_clock_boundary_shadow": (
                        args.input_clock_boundary_shadow
                    ),
                    "input_clock_shadow_role": (
                        INPUT_CLOCK_SHADOW_ROLE
                        if args.input_clock_boundary_shadow
                        else "disabled"
                    ),
                    "input_clock_shadow_sample_ms": (
                        args.input_clock_shadow_sample_ms
                    ),
                    "input_clock_shadow_predicate": (
                        "frscreen_msg_state_ge_0_or_eq_minus_2"
                        if args.input_clock_boundary_shadow
                        else "disabled"
                    ),
                    "finalb_scale_source_authority": bool(
                        getattr(
                            args,
                            "enable_finalb_scale_source_authority",
                            False,
                        )
                    ),
                    "finalb_scale_pretarget_transport": (
                        "experimental_unit_unknown_direction"
                        if getattr(
                            args,
                            "enable_finalb_scale_source_authority",
                            False,
                        )
                        else "disabled"
                    ),
                    "no_scale_writer_schedule_authority": (
                        no_scale_writer_schedule_authority is not None
                    ),
                    "no_scale_writer_static_audit": (
                        no_scale_writer_schedule_authority.static_audit
                        .compact_record()
                        if no_scale_writer_schedule_authority is not None
                        else None
                    ),
                    "diagnostic_continue_root_only_scale": (
                        diagnostic_continue_root_only_scale
                    ),
                    "diagnostic_root_only_scale_semantics": (
                        "constant_current_root_unknown_direction_no_authority"
                        if diagnostic_continue_root_only_scale
                        else "disabled"
                    ),
                    "runtime_ecl_static_sha256": getattr(
                        args,
                        "runtime_ecl_static_sha256",
                        None,
                    ),
                    "local_hazard_backend": args.local_hazard_backend,
                    "local_hazard_backend_authority": (
                        "parity_gated_native_default_exact_implementation"
                        if args.local_hazard_backend == "native"
                        else "explicit_python_reference_rollback"
                    ),
                    "local_beam_reducer": args.local_beam_reducer,
                    "local_beam_reducer_authority": (
                        "parity_gated_native_quantized_reduction"
                        if args.local_beam_reducer == "native"
                        else "explicit_python_reference_rollback"
                    ),
                    "bullet_decode_backend": (
                        args.bullet_decode_backend
                    ),
                    "bullet_decode_backend_authority": (
                        "python_diagnostic_transform_override"
                        if args.trace_transform_runtime
                        else (
                            "parity_gated_native_packed_with_sparse_python_crossover"
                            if args.bullet_decode_backend == "native"
                            else "explicit_python_object_reference_rollback"
                        )
                    ),
                    "pool_read_buffers": (
                        "persistent_ctypes_destination_unsigned_byte_view"
                    ),
                    "global_planner": (
                        "finite_horizon_robust_backward_viability"
                        if not args.local_only
                        else "disabled"
                    ),
                    "corridor_submission_policy": (
                        "hard_time_scale_authority_only"
                        if args.authority_only_corridor
                        else "diagnostic_and_authoritative"
                    ),
                    "corridor_background_low_priority": False,
                    "viability_grid_step": (
                        TH08_CORRIDOR_CONFIG.grid_step
                    ),
                    "viability_required_clearance": (
                        TH08_CORRIDOR_CONFIG.required_clearance
                    ),
                    "viability_continuous_position_authority": (
                        "boolean_lower_cell_radius_inflated"
                    ),
                    "ordinary_viability_authority": {
                        "enabled": ordinary_preexhaustion_authority,
                        "scope": "ordinary_nonspell_only",
                        "future_kernel": (
                            "4px_boolean_lower_cell_radius_inflated"
                            if ordinary_preexhaustion_authority
                            else "disabled"
                        ),
                        "terminal_adapter": (
                            "active_policy_next_layer_causal_held_no_write"
                            if ordinary_preexhaustion_authority
                            else "disabled"
                        ),
                        "minimum_terminal_lead_frames": (
                            ORDINARY_AUTHORITY_MIN_TERMINAL_LEAD
                        ),
                        "future_source_coverage": (
                            "exact_version_required_fail_closed"
                        ),
                    },
                    "viability_refinement_grid_steps": (
                        LIVE_REFINEMENT_GRID_STEPS
                    ),
                    "viability_shadow_refinement_grid_steps": (
                        SHADOW_REFINEMENT_GRID_STEPS
                    ),
                    "viability_refinement_trigger": (
                        "shadow_only_after_stage4a_latency_rejection"
                    ),
                    "viability_survival_labels": (
                        {
                            "live": LIVE_SURVIVAL_LABELS,
                            "shadow": SHADOW_SURVIVAL_LABELS,
                            "reason": (
                                "shadow_isolated_after_serialized_delivery_"
                                "rejection"
                            ),
                        }
                    ),
                    "viability_frames_per_layer": (
                        TH08_CORRIDOR_CONFIG.frames_per_layer
                    ),
                    "viability_horizon_frames": (
                        TH08_CORRIDOR_CONFIG.horizon_frames
                    ),
                    "corridor_native_viability_workers": (
                        args.corridor_native_workers
                    ),
                    "ordinary_authority_native_viability_workers": (
                        ORDINARY_AUTHORITY_NATIVE_WORKERS
                    ),
                    "ordinary_authority_background_low_priority": True,
                    "local_planner_horizon_frames": args.horizon,
                    "local_terminal_threat_horizon_frames": (
                        args.threat_horizon
                    ),
                    "viability_max_query_age_frames": (
                        args.corridor_max_age
                    ),
                    "async_policy_epoch": "forecasted_solve_completion",
                    "async_policy_context": (
                        "gameplay_epoch_stage_spell"
                    ),
                    "async_policy_initial_lead_frames": (
                        corridor_policy_lead.frames
                    ),
                    "async_policy_overlap_frames": (
                        corridor_policy_lead.overlap_frames
                    ),
                    "async_policy_minimum_lead_frames": (
                        corridor_policy_lead.minimum_frames
                    ),
                    "async_policy_delay_support_padding": (
                        ASYNC_POLICY_DELAY_PADDING
                    ),
                    "async_policy_submit_interval_frames": (
                        args.corridor_every
                    ),
                    "safety_value_horizon_frames": (
                        ordinary_safety_value_horizon
                    ),
                    "safety_value_role": (
                        "empty_kernel_soft_preference"
                        if ordinary_safety_value_horizon
                        else "disabled"
                    ),
                    "safety_value_action_values_retained": (
                        False
                    ),
                    "native_planner_backend": native_backend.available(),
                    "viability_quantifiers": (
                        "exists_action_forall_delay"
                    ),
                    "viability_audit_capsules": (
                        str(args.viability_audit_dir)
                        if args.viability_audit_dir is not None
                        else None
                    ),
            },
            flush=True,
        )
        if trace_enemy_lifecycle_events and enemy_lifecycle_probe is None:
            raise RuntimeError(
                "requested enemy lifecycle instrumentation is unavailable"
            )
        state = observe_state(reader)
        if args.wait_gameplay:
            trace_sink.emit(
                {
                    "kind": "wait_ready",
                    "frame": state["enemy_manager_frame"],
                },
                flush=True,
            )
            wait_deadline = time.perf_counter() + args.wait_timeout
            while True:
                if state["gameplay_active"]:
                    gameplay_armed = True
                    if (
                        state["route_id"] != 2
                        or state["difficulty_index"] != args.difficulty
                    ):
                        raise RuntimeError(
                            "manual selection mismatch after confirm: "
                            f"difficulty={state['difficulty_index']} "
                            f"route={state['route_id']}"
                        )
                    if (
                        args.expected_stage is not None
                        and state["stage_route_index"] != args.expected_stage
                    ):
                        raise RuntimeError(
                            "practice stage mismatch after confirm: "
                            f"expected={args.expected_stage} "
                            f"got={state['stage_route_index']}"
                        )
                    if not state["input_raw"]:
                        break
                if args.stop_file is not None and args.stop_file.exists():
                    termination_reason = "external_stop"
                    return 0
                if time.perf_counter() >= wait_deadline:
                    raise RuntimeError(
                        "timed out waiting for idle route-2 gameplay"
                    )
                _require_foreground(api, pid)
                time.sleep(0.005)
                state = observe_state(reader)
        if not state["gameplay_active"] or state["route_id"] != 2:
            raise RuntimeError("agent requires active route-2 gameplay")
        if state["difficulty_index"] != args.difficulty:
            raise RuntimeError(
                "difficulty mismatch: "
                f"expected {args.difficulty}, got {state['difficulty_index']}"
            )
        if (
            args.expected_stage is not None
            and state["stage_route_index"] != args.expected_stage
        ):
            raise RuntimeError(
                "stage mismatch: "
                f"expected {args.expected_stage}, "
                f"got {state['stage_route_index']}"
            )
        if state["input_raw"]:
            raise RuntimeError("physical gameplay input is already active")
        _require_foreground(api, pid)
        gameplay_armed = True
        if enemy_lifecycle_probe is not None:
            enemy_lifecycle_baseline = enemy_lifecycle_probe.read_since(None)
            enemy_lifecycle_probe_last_serial = (
                enemy_lifecycle_baseline.observed_serial
            )
            trace_sink.emit(
                {
                    "kind": "enemy_lifecycle_probe_baseline",
                    **enemy_lifecycle_baseline.compact_record(),
                },
                flush=True,
            )
            if enemy_lifecycle_probe_last_serial is None:
                raise RuntimeError(
                    "enemy lifecycle probe could not establish its baseline"
                )
        scene_guard.observe(
            gameplay_active=True,
            current_stage=int(state["stage_route_index"]),
            now=time.perf_counter(),
        )
        enemy_future = enemy_executor.submit(
            capture_enemy_pool_snapshot,
            reader,
        )
        enemy_last_submit = int(state["enemy_manager_frame"])
        item_sensor_enabled = ITEM_OBJECTIVES_ENABLED or bool(
            args.trace_items
        )
        sensor = Sensor(reader, capture_items=item_sensor_enabled)
        deadline = time.perf_counter() + args.duration
        while time.perf_counter() < deadline:
            if args.stop_file is not None and args.stop_file.exists():
                termination_reason = "external_stop"
                break
            counter = reader.u32(ADDR_ENEMY_MANAGER_FRAME)
            now = time.perf_counter()
            engine_flags = reader.u32(ADDR_ENGINE_FLAGS)
            stage_route_index = reader.u32(ADDR_STAGE_ROUTE_INDEX)
            scene_decision = scene_guard.observe(
                gameplay_active=bool(engine_flags & 0x04),
                current_stage=stage_route_index,
                now=now,
            )
            if not engine_flags & 0x04:
                if (
                    input_clock_tracker is not None
                    and input_clock_tracker.active_episode_id is not None
                ):
                    input_clock_sample = capture_input_clock_shadow(reader)
                    input_clock_observation = _semantic_clock_observation(
                        input_clock_sample,
                        fallback_frame=counter,
                        context=(gameplay_epoch, stage_route_index),
                    )
                    input_clock_event = input_clock_tracker.censor(
                        input_clock_observation,
                        reason=f"scene_inactive:{scene_decision.status}",
                    )
                    record_input_clock_sample(
                        sample=input_clock_sample,
                        observation=input_clock_observation,
                        events=(
                            (input_clock_event,)
                            if input_clock_event is not None
                            else ()
                        ),
                        frame=counter,
                        stage_route_index=stage_route_index,
                        frozen_seconds=max(0.0, now - last_frame_progress),
                        repeat_poll_count=input_clock_repeat_polls,
                        triggers=("scene_inactive",),
                    )
                if scene_decision.entered:
                    issue_controller.dispatch(
                        previous_mask,
                        0,
                        require_foreground=True,
                    )
                    previous_mask = 0
                    previous_direction = 0
                    corridor_solution = None
                    corridor_pending_solution = None
                    for memory in enemy_body_memories:
                        memory.clear()
                    if corridor_future is not None and corridor_future.cancel():
                        corridor_future = None
                    ordinary_continuation_lease = None
                    ordinary_future_source_result = None
                    if ordinary_future_source_future is not None:
                        ordinary_future_source_future.cancel()
                        ordinary_future_source_future = None
                    trace_sink.emit(
                        {
                                "kind": "scene_inactive",
                                "frame": counter,
                                "engine_flags": engine_flags,
                                "stage_route_index": stage_route_index,
                                "transition_from_stage": (
                                    scene_decision.transition_from_stage
                                ),
                                "expected_stage": scene_decision.expected_stage,
                                "status": scene_decision.status,
                        },
                        flush=True,
                    )
                if scene_decision.status in (
                    "stage_transition_timeout",
                    "route_complete",
                ):
                    termination_reason = scene_decision.status
                    break
                assert scene_guard.inactive_since is not None
                if auto_confirm.frozen_pulse_due(
                    now=now,
                    last_progress=scene_guard.inactive_since,
                    last_pulse=last_frozen_confirm,
                    eligible=scene_decision.expected_stage is not None,
                ):
                    _require_foreground(api, pid)
                    send_scan_key(api, scan_code=0x2C, pressed=False)
                    time.sleep(0.04)
                    send_scan_key(api, scan_code=0x2C, pressed=True)
                    previous_mask = SHOT
                    auto_confirm.mark_full_pulse(frame=counter)
                    last_frozen_confirm = time.perf_counter()
                    trace_sink.emit(
                        {
                                "kind": "auto_confirm_transition_pulse",
                                "frame": counter,
                                "stage_route_index": stage_route_index,
                                "transition_from_stage": (
                                    scene_decision.transition_from_stage
                                ),
                                "expected_stage": scene_decision.expected_stage,
                                "inactive_seconds": (
                                    scene_decision.inactive_seconds
                                ),
                        },
                        flush=True,
                    )
                time.sleep(args.poll_ms / 1000.0)
                continue
            if scene_decision.status == "resumed":
                gameplay_epoch += 1
                if finalb_scale_schedule_authority is not None:
                    finalb_scale_schedule_authority.reset()
                if no_scale_writer_schedule_authority is not None:
                    no_scale_writer_schedule_authority.reset()
                boss_phase_tracker.reset()
                trace_sink.emit(
                    {
                            "kind": "scene_resumed",
                            "frame": counter,
                            "engine_flags": engine_flags,
                            "stage_route_index": stage_route_index,
                            "transition_from_stage": (
                                scene_decision.transition_from_stage
                            ),
                            "expected_stage": scene_decision.expected_stage,
                            "inactive_seconds": scene_decision.inactive_seconds,
                            "expected_stage_matched": (
                                scene_decision.expected_stage is None
                                or scene_decision.expected_stage
                                == stage_route_index
                            ),
                            "gameplay_epoch": gameplay_epoch,
                    },
                    flush=True,
                )
                previous_counter = None
                previous_phase = None
                previous_action_phase = None
                decision_frame_deltas.clear()
                delay_estimator.reset()
                previous_iteration_ms = None
                previous_trace_ms = None
                corridor_solution = None
                corridor_pending_solution = None
                corridor_last_submit = CORRIDOR_INITIAL_SUBMIT_FRAME
                corridor_context = None
                corridor_commitment = CorridorCommitment()
                for memory in enemy_body_memories:
                    memory.clear()
                ecl_instruction_cache.clear()
                if corridor_future is not None and corridor_future.cancel():
                    corridor_future = None
                ordinary_continuation_lease = None
                ordinary_future_source_result = None
                if ordinary_future_source_future is not None:
                    ordinary_future_source_future.cancel()
                    ordinary_future_source_future = None
                auto_confirm.eligible_since = None
                auto_confirm.released = False
                last_frame_progress = now
            if counter == previous_counter:
                input_clock_sample: dict[str, object] | None = None
                if input_clock_tracker is not None:
                    if input_clock_repeat_frame != counter:
                        input_clock_repeat_frame = counter
                        input_clock_repeat_polls = 0
                        input_clock_wall_cut_frame = None
                    input_clock_repeat_polls += 1
                    sample_now_ns = time.perf_counter_ns()
                    sample_due = (
                        input_clock_repeat_polls == 1
                        or (
                            sample_now_ns - input_clock_last_sample_ns
                            >= int(
                                args.input_clock_shadow_sample_ms
                                * 1_000_000.0
                            )
                        )
                    )
                    if sample_due:
                        input_clock_sample = capture_input_clock_shadow(reader)
                        input_clock_last_sample_ns = int(
                            input_clock_sample.get(
                                "monotonic_end_ns",
                                sample_now_ns,
                            )
                        )
                        input_clock_observation = (
                            _semantic_clock_observation(
                                input_clock_sample,
                                fallback_frame=counter,
                                context=(gameplay_epoch, stage_route_index),
                            )
                        )
                        input_clock_events = input_clock_tracker.observe(
                            input_clock_observation
                        )
                        triggers: list[str] = []
                        if input_clock_repeat_polls == 1:
                            triggers.append("first_repeat")
                        input_clock_message_key = (
                            _input_clock_message_key(input_clock_sample)
                        )
                        if (
                            input_clock_message_key
                            != input_clock_last_message_key
                        ):
                            triggers.append("message_state_changed")
                            input_clock_last_message_key = (
                                input_clock_message_key
                            )
                        frozen_seconds = max(
                            0.0,
                            now - last_frame_progress,
                        )
                        if (
                            frozen_seconds
                            >= INPUT_CLOCK_SHADOW_WALL_CUT_SECONDS
                            and input_clock_wall_cut_frame != counter
                        ):
                            triggers.append("wall_50ms_audit_cut")
                            input_clock_wall_cut_frame = counter
                        if input_clock_events:
                            triggers.append("semantic_episode_boundary")
                        if triggers:
                            record_input_clock_sample(
                                sample=input_clock_sample,
                                observation=input_clock_observation,
                                events=input_clock_events,
                                frame=counter,
                                stage_route_index=stage_route_index,
                                frozen_seconds=frozen_seconds,
                                repeat_poll_count=(
                                    input_clock_repeat_polls
                                ),
                                triggers=tuple(triggers),
                            )
                bomb_active = reader.u32(
                    ADDR_PLAYER + PLAYER_BOMB_ACTIVE_OFFSET
                )
                if auto_confirm.frozen_pulse_due(
                    now=now,
                    last_progress=last_frame_progress,
                    last_pulse=last_frozen_confirm,
                    eligible=_frozen_auto_confirm_eligible(
                        bomb_active=bool(bomb_active),
                    ),
                ):
                    input_clock_held_desired_mask = previous_mask
                    _require_foreground(api, pid)
                    send_scan_key(api, scan_code=0x2C, pressed=False)
                    time.sleep(0.04)
                    send_scan_key(api, scan_code=0x2C, pressed=True)
                    input_clock_episode_id = (
                        input_clock_tracker.mark_pulse()
                        if input_clock_tracker is not None
                        else None
                    )
                    if input_clock_tracker is not None:
                        input_clock_sample = capture_input_clock_shadow(reader)
                        input_clock_last_sample_ns = int(
                            input_clock_sample.get(
                                "monotonic_end_ns",
                                time.perf_counter_ns(),
                            )
                        )
                        input_clock_observation = (
                            _semantic_clock_observation(
                                input_clock_sample,
                                fallback_frame=counter,
                                context=(gameplay_epoch, stage_route_index),
                            )
                        )
                        input_clock_events = input_clock_tracker.observe(
                            input_clock_observation
                        )
                        record_input_clock_sample(
                            sample=input_clock_sample,
                            observation=input_clock_observation,
                            events=input_clock_events,
                            frame=counter,
                            stage_route_index=stage_route_index,
                            frozen_seconds=max(
                                0.0,
                                time.perf_counter()
                                - last_frame_progress,
                            ),
                            repeat_poll_count=input_clock_repeat_polls,
                            triggers=("wall_pulse_after",),
                        )
                    previous_mask |= SHOT
                    auto_confirm.mark_full_pulse(frame=counter)
                    last_frozen_confirm = time.perf_counter()
                    trace_sink.emit(
                        {
                                "kind": "auto_confirm_wall_pulse",
                                "frame": counter,
                                "stage_route_index": state[
                                    "stage_route_index"
                                ],
                                "player_phase": state["player"]["phase"],
                                "spell": state["spell"],
                                "input_clock_shadow_role": (
                                    INPUT_CLOCK_SHADOW_ROLE
                                    if input_clock_tracker is not None
                                    else None
                                ),
                                "held_desired_mask": (
                                    input_clock_held_desired_mask
                                ),
                                "held_desired_mask_after_pulse": (
                                    previous_mask
                                ),
                                "input_clock_shadow_episode_id": (
                                    input_clock_episode_id
                                ),
                                "input_clock_shadow": input_clock_sample,
                        },
                        flush=True,
                    )
                time.sleep(args.poll_ms / 1000.0)
                continue
            last_frame_progress = time.perf_counter()
            input_clock_repeat_frame = None
            input_clock_repeat_polls = 0
            input_clock_wall_cut_frame = None
            iteration_started = time.perf_counter()
            observe_started = iteration_started
            state = observe_state(reader)
            observe_ms = (time.perf_counter() - observe_started) * 1000.0
            if not state["gameplay_active"]:
                time.sleep(args.poll_ms / 1000.0)
                continue
            enemy_lifecycle_batch: EnemyLifecycleBatch | None = None
            if state["route_id"] != 2:
                termination_reason = "gameplay_ended"
                break
            if (
                input_clock_tracker is not None
                and input_clock_tracker.active_episode_id is not None
            ):
                input_clock_sample = capture_input_clock_shadow(reader)
                input_clock_last_sample_ns = int(
                    input_clock_sample.get(
                        "monotonic_end_ns",
                        time.perf_counter_ns(),
                    )
                )
                input_clock_observation = _semantic_clock_observation(
                    input_clock_sample,
                    fallback_frame=counter,
                    context=(gameplay_epoch, stage_route_index),
                )
                input_clock_events = input_clock_tracker.observe(
                    input_clock_observation
                )
                input_clock_message_key = _input_clock_message_key(
                    input_clock_sample
                )
                triggers = ["manager_progress"]
                if (
                    input_clock_message_key
                    != input_clock_last_message_key
                ):
                    triggers.append("message_state_changed")
                    input_clock_last_message_key = input_clock_message_key
                if input_clock_events:
                    triggers.append("semantic_episode_boundary")
                record_input_clock_sample(
                    sample=input_clock_sample,
                    observation=input_clock_observation,
                    events=input_clock_events,
                    frame=counter,
                    stage_route_index=stage_route_index,
                    frozen_seconds=0.0,
                    repeat_poll_count=0,
                    triggers=tuple(triggers),
                )
            delay_estimator.observe(
                frame=int(state["enemy_manager_frame"]),
                input_mask=int(state["input_current"]),
            )
            if previous_counter is not None and counter != previous_counter + 1:
                gaps += 1
            spell_state = state["spell"]
            corridor_context = (
                gameplay_epoch,
                int(state["stage_route_index"]),
                (
                    int(spell_state["spell_id"])
                    if spell_state["active"]
                    else None
                ),
            )
            corridor_context_changed = corridor_commitment.set_context(
                corridor_context
            )
            for memory in enemy_body_memories:
                memory.set_context(corridor_context)
            if corridor_context_changed:
                boss_phase_tracker.reset()
                corridor_solution = None
                corridor_pending_solution = None
                if (
                    corridor_future is not None
                    and corridor_future.cancel()
                ):
                    corridor_future = None
                ordinary_continuation_lease = None
                ordinary_future_source_result = None
                if ordinary_future_source_future is not None:
                    ordinary_future_source_future.cancel()
                    ordinary_future_source_future = None
            iterations += 1
            if iterations % 30 == 0:
                _require_foreground(api, pid)
            read_started = time.perf_counter()
            enemy_background_started = read_started
            if enemy_future is not None and enemy_future.done():
                enemy_snapshot = enemy_future.result()
                enemy_future = None
            if (
                _enemy_sensor_submit_due(
                    current_frame=counter,
                    last_submit_frame=enemy_last_submit,
                    pending=enemy_future is not None,
                )
            ):
                enemy_future = enemy_executor.submit(
                    capture_enemy_pool_snapshot,
                    reader,
                )
                enemy_last_submit = counter
            if enemy_snapshot is None:
                enemy_bodies = ()
                background_dormant_enemy_body_pointers = frozenset()
            else:
                (
                    enemy_bodies,
                    background_dormant_enemy_body_pointers,
                ) = enemy_background_memory.merge_snapshot(
                    enemy_snapshot,
                    frame=int(state["enemy_manager_frame"]),
                )
            enemy_pool_read_ms = (
                enemy_snapshot.read_ms
                if enemy_snapshot is not None
                else None
            )
            enemy_body_snapshot_frame = (
                enemy_snapshot.frame_after
                if enemy_snapshot is not None
                else None
            )
            enemy_background_ms = (
                time.perf_counter() - enemy_background_started
            ) * 1000.0
            enemy_prefix_capture_started = time.perf_counter()
            enemy_mode_prefix_capture = None
            if trace_enemy_mode_transitions:
                enemy_mode_prefix_capture = (
                    capture_player_enemy_mode_prefix(
                        reader,
                        include_main_ecl_vms=False,
                        include_combat_progress=kill_before_saturation,
                    )
                )
                enemy_prefix_snapshot = (
                    enemy_mode_prefix_capture.enemy_snapshot
                )
            else:
                enemy_prefix_snapshot = (
                    capture_enemy_pool_prefix_contiguous(
                        reader,
                        include_main_ecl_vms=False,
                        include_combat_progress=kill_before_saturation,
                    )
                )
            enemy_prefix_capture_ms = (
                time.perf_counter() - enemy_prefix_capture_started
            ) * 1000.0
            enemy_prefix_merge_started = time.perf_counter()
            (
                enemy_prefix_bodies,
                prefix_dormant_enemy_body_pointers,
            ) = enemy_body_memory.merge_snapshot(
                enemy_prefix_snapshot,
                frame=int(state["enemy_manager_frame"]),
            )
            prefix_end = (
                ENEMY_POOL_BASE + ENEMY_LOCAL_PREFIX_SIZE * ENEMY_STRIDE
            )
            dormant_enemy_body_pointers = frozenset(
                set(prefix_dormant_enemy_body_pointers)
                | {
                    pointer
                    for pointer in background_dormant_enemy_body_pointers
                    if pointer >= prefix_end
                }
            )
            enemy_bodies = merge_enemy_pool_prefix(
                enemy_bodies,
                enemy_prefix_bodies,
            )
            enemy_prefix_merge_ms = (
                time.perf_counter() - enemy_prefix_merge_started
            ) * 1000.0
            raw_pools = sensor.capture_raw_pools()
            bullet_blob = raw_pools.bullet_blob
            laser_blob = raw_pools.laser_blob
            item_blob = raw_pools.item_blob
            bullet_frame_before = raw_pools.bullet_frame_before
            bullet_frame_after = raw_pools.bullet_frame_after
            bullet_pool_read_ms = raw_pools.bullet_pool_read_ms
            laser_pool_read_ms = raw_pools.laser_pool_read_ms
            item_pool_read_ms = raw_pools.item_pool_read_ms
            ecl_vm_snapshot: EclVmSnapshot | None = None
            ecl_lookahead: EclLookaheadResult | None = None
            tagged_velocity_toggles: tuple[TaggedVelocityToggle, ...] = ()
            ecl_lookahead_error: str | None = None
            ecl_frame_before: int | None = None
            ecl_frame_after: int | None = None
            spell_enemy_body_guard: SpellEnemyBodyGuard | None = None
            spell_enemy_body_guard_error: str | None = None
            boss_guard_frame_before: int | None = None
            boss_guard_frame_after: int | None = None
            boss_phase_snapshot: BossPhaseSnapshot | None = None
            boss_phase_error: str | None = None
            boss_phase_progress: PhaseProgressObservation | None = None
            spell_enemy_pointer = int(spell_state.get("enemy_pointer", 0))
            boss_phase_read_started = time.perf_counter()
            try:
                boss_phase_snapshot = capture_boss_phase_snapshot(
                    reader,
                    preferred_pointer=(
                        spell_enemy_pointer
                        if spell_state.get("active")
                        else 0
                    ),
                )
            except (OSError, RuntimeError, ValueError, struct.error) as error:
                boss_phase_error = f"{type(error).__name__}: {error}"
            boss_phase_read_ms = (
                time.perf_counter() - boss_phase_read_started
            ) * 1000.0
            boss_enemy_pointer = (
                boss_phase_snapshot.pointer
                if boss_phase_snapshot is not None
                else (
                    spell_enemy_pointer
                    if spell_state.get("active")
                    else 0
                )
            )
            spell_enemy_guard_read_ms = 0.0
            if boss_enemy_pointer:
                spell_enemy_guard_read_started = time.perf_counter()
                boss_guard_frame_before = reader.u32(
                    ADDR_ENEMY_MANAGER_FRAME
                )
                try:
                    spell_enemy_body_guard = read_enemy_body_guard(
                        reader,
                        pointer=boss_enemy_pointer,
                    )
                except (OSError, RuntimeError, ValueError, struct.error) as error:
                    spell_enemy_body_guard_error = (
                        f"{type(error).__name__}: {error}"
                    )
                boss_guard_frame_after = reader.u32(
                    ADDR_ENEMY_MANAGER_FRAME
                )
                spell_enemy_guard_read_ms = (
                    time.perf_counter() - spell_enemy_guard_read_started
                ) * 1000.0
            ecl_lookahead_read_ms = 0.0
            if spell_state.get("active") and spell_enemy_pointer:
                ecl_capture = capture_main_ecl(
                    reader,
                    enemy_pointer=spell_enemy_pointer,
                    instruction_cache=ecl_instruction_cache,
                    horizon_frames=ECL_CALLBACK_LOOKAHEAD_FRAMES,
                    active_difficulty_mask=(
                        1 << int(state["difficulty_index"])
                    ),
                )
                ecl_vm_snapshot = ecl_capture.snapshot
                ecl_lookahead = ecl_capture.lookahead
                tagged_velocity_toggles = (
                    ecl_capture.tagged_velocity_toggles
                )
                ecl_lookahead_error = ecl_capture.error
                ecl_frame_before = ecl_capture.frame_before
                ecl_frame_after = ecl_capture.frame_after
                ecl_lookahead_read_ms = ecl_capture.elapsed_ms
            hazard_read_bookkeeping_started = time.perf_counter()
            if (
                spell_enemy_body_guard is not None
                and boss_guard_frame_before is not None
                and boss_guard_frame_after is not None
            ):
                tracked_spell_bodies, _dormant = (
                    spell_enemy_body_memory.merge_snapshot(
                        EnemyPoolSnapshot(
                            boss_guard_frame_before,
                            boss_guard_frame_after,
                            (spell_enemy_body_guard.body,),
                            0.0,
                        ),
                        frame=int(state["enemy_manager_frame"]),
                    )
                )
                if tracked_spell_bodies:
                    spell_enemy_body_guard = replace(
                        spell_enemy_body_guard,
                        body=tracked_spell_bodies[0],
                    )
            boss_phase_progress = boss_phase_tracker.observe(
                (
                    boss_phase_snapshot.as_progress_state(
                        context=corridor_context,
                        continuity_context=(
                            gameplay_epoch,
                            int(state["stage_route_index"]),
                        ),
                        bomb_active=bool(
                            state["player"]["bomb_active"]
                        ),
                        player_transition_state=int(
                            state["player"]["phase"]
                        ),
                        spell_active=bool(state["spell"]["active"]),
                        active_spell_owner=bool(
                            state["spell"]["active"]
                            and int(state["spell"]["enemy_pointer"])
                            == boss_phase_snapshot.pointer
                        ),
                    )
                    if boss_phase_snapshot is not None
                    else None
                )
            )
            enemy_bodies = merge_spell_enemy_body_guard(
                enemy_bodies,
                spell_enemy_body_guard,
            )
            exact_contact_enemy_bodies = tuple(
                body
                for body in enemy_bodies
                if enemy_body_contact_enabled(body)
            )
            player_control_root = capture_player_control_root(reader)
            counter_after_read = player_control_root.frame_after
            hazard_read_bookkeeping_ms = (
                time.perf_counter() - hazard_read_bookkeeping_started
            ) * 1000.0
            read_ms = (time.perf_counter() - read_started) * 1000.0
            if not player_control_root.stable:
                gaps += 1
                trace_sink.emit(
                    {
                        "kind": "player_control_root_unstable",
                        "source_frame": state["enemy_manager_frame"],
                        "frame_before": (
                            player_control_root.frame_before
                        ),
                        "frame_after": player_control_root.frame_after,
                        "scale_bits": player_control_root.scale_bits,
                        "position_before": [
                            player_control_root.x_before,
                            player_control_root.y_before,
                        ],
                        "position_after": [
                            player_control_root.x_after,
                            player_control_root.y_after,
                        ],
                        "input_current_before": (
                            player_control_root.input_current_before
                        ),
                        "input_current_after": (
                            player_control_root.input_current_after
                        ),
                        "attempts": player_control_root.attempts,
                        "semantics_version": (
                            TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION
                        ),
                    },
                    flush=True,
                )
                continue
            if (
                enemy_prefix_snapshot.frame_after
                < enemy_prefix_snapshot.frame_before
                or counter_after_read < enemy_prefix_snapshot.frame_after
                or bullet_frame_after < bullet_frame_before
                or counter_after_read < bullet_frame_after
                or (
                    ecl_frame_before is not None
                    and ecl_frame_after is not None
                    and ecl_frame_after < ecl_frame_before
                )
                or (
                    boss_guard_frame_before is not None
                    and boss_guard_frame_after is not None
                    and boss_guard_frame_after < boss_guard_frame_before
                )
            ):
                gaps += 1
                continue
            snapshot_lag = max(0, counter_after_read - int(state["enemy_manager_frame"]))
            hazard_frame_before = min(
                enemy_prefix_snapshot.frame_before,
                bullet_frame_before,
                (
                    boss_guard_frame_before
                    if boss_guard_frame_before is not None
                    else bullet_frame_before
                ),
            )
            hazard_frame_after = max(
                enemy_prefix_snapshot.frame_after,
                bullet_frame_after,
                (
                    boss_guard_frame_after
                    if boss_guard_frame_after is not None
                    else bullet_frame_after
                ),
            )
            hazard_alignment = HazardEpochAlignment(
                source_frame=int(state["enemy_manager_frame"]),
                hazard_window=FrameWindow(
                    hazard_frame_before,
                    hazard_frame_after,
                ),
                current_frame=counter_after_read,
                event_window=(
                    FrameWindow(ecl_frame_before, ecl_frame_after)
                    if (
                        ecl_frame_before is not None
                        and ecl_frame_after is not None
                    )
                    else None
                ),
            )
            if not hazard_alignment.fits_epoch(
                maximum_extent=MAX_SENSOR_EPOCH_EXTENT_FRAMES
            ):
                gaps += 1
                gameplay_epoch += 1
                if finalb_scale_schedule_authority is not None:
                    finalb_scale_schedule_authority.reset()
                if no_scale_writer_schedule_authority is not None:
                    no_scale_writer_schedule_authority.reset()
                safe_mask = previous_mask & SHOT
                issue_controller.dispatch(
                    previous_mask,
                    safe_mask,
                    require_foreground=True,
                )
                previous_mask = safe_mask
                previous_direction = 0
                decision_frame_deltas.clear()
                delay_estimator.reset()
                corridor_solution = None
                corridor_pending_solution = None
                corridor_context = None
                corridor_commitment = CorridorCommitment()
                for memory in enemy_body_memories:
                    memory.clear()
                boss_phase_tracker.reset()
                ecl_instruction_cache.clear()
                if corridor_future is not None:
                    corridor_future.cancel()
                ordinary_continuation_lease = None
                ordinary_future_source_result = None
                if ordinary_future_source_future is not None:
                    ordinary_future_source_future.cancel()
                    ordinary_future_source_future = None
                trace_sink.emit(
                    {
                            "kind": "sensor_epoch_discontinuity",
                            "frame": counter_after_read,
                            "source_frame": state["enemy_manager_frame"],
                            "gameplay_epoch": gameplay_epoch,
                            "maximum_extent": (
                                MAX_SENSOR_EPOCH_EXTENT_FRAMES
                            ),
                            "observed_extent": (
                                hazard_alignment.total_frame_extent
                            ),
                            "hazard_window": [
                                bullet_frame_before,
                                bullet_frame_after,
                            ],
                            "event_window": (
                                [ecl_frame_before, ecl_frame_after]
                                if (
                                    ecl_frame_before is not None
                                    and ecl_frame_after is not None
                                )
                                else None
                            ),
                            "spell": state["spell"],
                            "released_to_mask": safe_mask,
                    },
                    flush=True,
                )
                continue
            player_to_hazard_lag = (
                hazard_alignment.source_to_hazard_lag
            )
            hazard_snapshot_age = hazard_alignment.hazard_age
            bullet_capture_span = hazard_alignment.hazard_window.span
            ecl_event_frame_offset: int | None = None
            ecl_event_frame_uncertainty: int | None = None
            if ecl_vm_snapshot is not None:
                ecl_event_frame_offset = (
                    hazard_alignment.event_frame_offset
                )
                ecl_event_frame_uncertainty = (
                    hazard_alignment.event_frame_uncertainty
                )
            decode_started = time.perf_counter()
            bullet_decode_started = decode_started
            bullets = (
                decode_bullets(
                    bullet_blob,
                    retain_transform_runtime=True,
                )
                if args.trace_transform_runtime
                else decode_live_planning_bullets(
                    bullet_blob,
                    backend=args.bullet_decode_backend,
                )
            )
            bullet_decode_ms = (
                time.perf_counter() - bullet_decode_started
            ) * 1000.0
            bullet_event_attach_started = time.perf_counter()
            if ecl_vm_snapshot is not None and tagged_velocity_toggles:
                bullets = attach_tagged_velocity_toggles(
                    bullets,
                    vm_snapshot=ecl_vm_snapshot,
                    toggles=tagged_velocity_toggles,
                    frame_offset=ecl_event_frame_offset or 0,
                    event_frame_uncertainty=(
                        ecl_event_frame_uncertainty or 0
                    ),
                )
            bullet_event_attach_ms = (
                time.perf_counter() - bullet_event_attach_started
            ) * 1000.0
            laser_decode_started = time.perf_counter()
            lasers = decode_lasers(laser_blob)
            laser_decode_ms = (
                time.perf_counter() - laser_decode_started
            ) * 1000.0
            item_decode_started = time.perf_counter()
            items = decode_items(item_blob)
            item_decode_ms = (
                time.perf_counter() - item_decode_started
            ) * 1000.0
            decode_ms = (time.perf_counter() - decode_started) * 1000.0
            player = state["player"]
            control_root_player = {
                **player,
                "x": player_control_root.x,
                "y": player_control_root.y,
            }
            control_root_input_state = {
                **state,
                "input_raw": player_control_root.input_raw,
                "input_current": player_control_root.input_current,
                "input_previous": player_control_root.input_previous,
            }
            resources = state["resources"]
            if resources is None:
                termination_reason = "resources_unavailable"
                break
            kill_before_saturation_observation = (
                observe_kill_before_saturation_target(
                    enabled=kill_before_saturation,
                    inventory=(
                        enemy_prefix_snapshot.combat_progress_inventory
                    ),
                    enemy_bodies=enemy_prefix_bodies,
                    player_x=float(player["x"]),
                    player_y=float(player["y"]),
                    power=float(resources["power"]),
                    spell_active=bool(spell_state["active"]),
                    excluded_enemy_pointer=boss_enemy_pointer,
                )
            )
            upcoming_spawn_observation = None
            upcoming_spawn_skip_reason: str | None = None
            if not kill_before_saturation:
                upcoming_spawn_skip_reason = "disabled"
            elif bool(spell_state["active"]):
                upcoming_spawn_skip_reason = "spell_active"
            elif (
                float(resources["power"]) < MINIMUM_PLAYER_POWER
            ):
                upcoming_spawn_skip_reason = "power_below_native_root"
            elif kill_before_saturation_observation.target is not None:
                upcoming_spawn_skip_reason = (
                    "current_enemy_target_has_priority"
                )
            else:
                upcoming_spawn_skip_reason = (
                    "withheld_after_noncausal_timeline_lifecycle_"
                    "counterexample"
                )
            can_bomb = (
                not args.no_bomb
                and args.normal_bomb
                and player["phase"] == 0
                and not player["bomb_active"]
                and resources["bombs"] > 0
                and counter_after_read - last_bomb_counter > 30
            )
            source_time_scale_bits = int(state["time_scale_bits"])
            scale_authority_resolution = None
            if finalb_scale_schedule_authority is not None:
                scale_authority_resolution = (
                    finalb_scale_schedule_authority.resolve(
                        reader,
                        decision_frame=counter_after_read,
                        source_frame=counter_after_read,
                        gameplay_epoch=gameplay_epoch,
                        route_id=int(state["route_id"]),
                        difficulty_index=int(
                            state["difficulty_index"]
                        ),
                        stage_route_index=int(
                            state["stage_route_index"]
                        ),
                        spell_id=(
                            int(spell_state["spell_id"])
                            if spell_state["active"]
                            else None
                        ),
                        observed_root_scale_bits=(
                            player_control_root.scale_bits
                        ),
                        observed_player_bomb_active=int(
                            bool(player["bomb_active"])
                        ),
                        player_phase=int(player["phase"]),
                        player_predeath_counter=int(
                            player["predeath_counter"]
                        ),
                        hit_started=(
                            int(player["phase"]) == 2
                            and previous_action_phase != 2
                        ),
                    )
                )
            elif (
                no_scale_writer_schedule_authority is not None
                and runtime_ecl_identity_service is not None
                and runtime_ecl_identity_service.accepted_version is not None
            ):
                scale_authority_resolution = (
                    no_scale_writer_schedule_authority.resolve(
                        reader,
                        runtime_version=(
                            runtime_ecl_identity_service.accepted_version
                        ),
                        source_frame=counter_after_read,
                        gameplay_epoch=gameplay_epoch,
                        route_id=int(state["route_id"]),
                        difficulty_index=int(state["difficulty_index"]),
                        stage_route_index=int(state["stage_route_index"]),
                        observed_root_scale_bits=(
                            player_control_root.scale_bits
                        ),
                        observed_player_bomb_active=int(
                            bool(player["bomb_active"])
                        ),
                    )
                )
            if scale_authority_resolution is not None:
                if scale_authority_resolution.trace_record is not None:
                    trace_sink.emit(
                        scale_authority_resolution.trace_record,
                        flush=True,
                    )
                trace_sink.emit(
                    scale_authority_resolution.compact_record()
                )
                time_scale_schedule = (
                    scale_authority_resolution.schedule
                )
            else:
                time_scale_schedule = (
                    Th08TimeScaleSchedule.root_observation(
                        player_control_root.scale_bits,
                        source_frame=counter_after_read,
                        provenance="live_stable_player_control_root",
                    )
                )
            projected_player_x = player_control_root.x
            projected_player_y = player_control_root.y
            player_projection_authority = "exact_current_control_root"
            delay_estimate = delay_estimator.estimate(
                frame=counter_after_read,
                default=args.control_delay_frames,
            )
            input_clock_delay_support = tuple(delay_estimate.support)
            control_delay_frames = delay_estimate.nominal
            if control_delay_frames <= 1:
                control_origin_x, control_origin_y = (
                    _project_player_for_read_lag(
                        projected_player_x,
                        projected_player_y,
                        previous_mask,
                        control_delay_frames,
                        player_scale_bits=(
                            time_scale_schedule.require_player_horizon(
                                control_delay_frames
                            )
                        ),
                    )
                )
            else:
                control_origin_x = projected_player_x
                control_origin_y = projected_player_y
            held_desired_mask = previous_mask & SUPPORTED_INPUT_MASK
            captured_iteration = CapturedIteration(
                gameplay_epoch=gameplay_epoch,
                stage_route_index=int(state["stage_route_index"]),
                spell_id=(
                    int(spell_state["spell_id"])
                    if spell_state["active"]
                    else None
                ),
                context_key=corridor_context,
                source_frame=int(state["enemy_manager_frame"]),
                snapshot_frame=counter_after_read,
                source_time_scale_bits=source_time_scale_bits,
                time_scale_schedule=time_scale_schedule,
                player_projection_authority=(
                    player_projection_authority
                ),
                player_x=player_control_root.x,
                player_y=player_control_root.y,
                projected_player_x=projected_player_x,
                projected_player_y=projected_player_y,
                native_active_mask=player_control_root.input_current,
                held_desired_mask=held_desired_mask,
                previous_direction=previous_direction,
                can_bomb=can_bomb,
                power=float(resources["power"]),
                bombs=float(resources["bombs"]),
                bullets=bullets,
                lasers=lasers,
                enemy_bodies=enemy_bodies,
                items=items,
                hazard_alignment=hazard_alignment,
                snapshot_lag=snapshot_lag,
                player_to_hazard_lag=player_to_hazard_lag,
                hazard_snapshot_age=hazard_snapshot_age,
                delay_estimate=delay_estimate,
                control_delay_frames=control_delay_frames,
                context_changed=corridor_context_changed,
            )
            if (
                captured_iteration.time_scale_schedule.coverage
                != SCALE_COVERAGE_COMPLETE
            ):
                if scale_authority_resolution is not None:
                    trace_sink.emit(
                        {
                            "kind": "scale_schedule_authority_wait",
                            "frame": captured_iteration.snapshot_frame,
                            "source_frame": captured_iteration.source_frame,
                            "gameplay_epoch": gameplay_epoch,
                            "stage_route_index": (
                                captured_iteration.stage_route_index
                            ),
                            "spell_id": captured_iteration.spell_id,
                            "root_scale_bits": (
                                captured_iteration.time_scale_schedule
                                .root_scale_bits
                            ),
                            "native_active_mask": (
                                captured_iteration.native_active_mask
                            ),
                            "changes_input": False,
                            "status": (
                                "waiting_without_write_after_scale_"
                                f"authority_{scale_authority_resolution.status}"
                            ),
                            "reason": scale_authority_resolution.reason,
                        },
                        flush=True,
                    )
                    time.sleep(args.poll_ms / 1000.0)
                    continue
                unknown_record = {
                    "kind": "time_scale_authority_unknown",
                    "frame": captured_iteration.snapshot_frame,
                    "source_frame": captured_iteration.source_frame,
                    "gameplay_epoch": gameplay_epoch,
                    "stage_route_index": (
                        captured_iteration.stage_route_index
                    ),
                    "spell_id": captured_iteration.spell_id,
                    "semantics_version": (
                        TH08_PLAYER_LASER_SCALE_SEMANTICS_VERSION
                    ),
                    "coverage": (
                        captured_iteration.time_scale_schedule.coverage
                    ),
                    "root_scale_bits": (
                        captured_iteration.time_scale_schedule.root_scale_bits
                    ),
                    "player_scale_bits": list(
                        captured_iteration.time_scale_schedule.player_scale_bits
                    ),
                    "laser_scale_bits": list(
                        captured_iteration.time_scale_schedule.laser_scale_bits
                    ),
                    "player_projection_authority": (
                        captured_iteration.player_projection_authority
                    ),
                    "hard_authority": False,
                    "scale_authority_status": "disabled",
                    "scale_authority_reason": None,
                }
                if diagnostic_continue_root_only_scale:
                    diagnostic_schedule = (
                        _diagnostic_constant_root_time_scale(
                            captured_iteration.time_scale_schedule
                        )
                    )
                    fallback_key = (
                        gameplay_epoch,
                        captured_iteration.stage_route_index,
                        captured_iteration.spell_id,
                        diagnostic_schedule.root_scale_bits,
                    )
                    if fallback_key != diagnostic_scale_fallback_key:
                        trace_sink.emit(
                            {
                                **unknown_record,
                                "fallback": (
                                    "diagnostic_constant_current_root_"
                                    "unknown_direction"
                                ),
                                "diagnostic_schedule_horizon": (
                                    diagnostic_schedule.complete_horizon
                                ),
                                "diagnostic_schedule_provenance": (
                                    diagnostic_schedule.provenance
                                ),
                            },
                            flush=True,
                        )
                        diagnostic_scale_fallback_key = fallback_key
                    time_scale_schedule = diagnostic_schedule
                    captured_iteration = replace(
                        captured_iteration,
                        time_scale_schedule=diagnostic_schedule,
                    )
                else:
                    trace_sink.emit(
                        {
                            **unknown_record,
                            "fallback": "terminate_and_release_keys",
                        },
                        flush=True,
                    )
                    termination_reason = "time_scale_authority_unknown"
                    break
            if (
                ordinary_future_source_future is not None
                and ordinary_future_source_future.done()
            ):
                try:
                    ordinary_future_source_result = (
                        ordinary_future_source_future.result()
                    )
                    closure = ordinary_future_source_result.closure
                    trace_sink.emit(
                        {
                            "kind": "ordinary_future_source_projection",
                            "frame": counter_after_read,
                            "root_frame": (
                                closure.projection.root_frame
                            ),
                            "horizon_frame": (
                                closure.projection.horizon_frame
                            ),
                            "requested_horizon_frames": (
                                ORDINARY_FUTURE_SOURCE_HORIZON_FRAMES
                            ),
                            "causal_prefix_truncated": bool(
                                closure.projection.source_closure_complete
                                and closure.projection.horizon_frames
                                < ORDINARY_FUTURE_SOURCE_HORIZON_FRAMES
                            ),
                            "causal_prefix_reason": (
                                closure.causal_prefix_reason
                            ),
                            "stable_capture": (
                                ordinary_future_source_result.snapshot.stable
                            ),
                            "capture_read_ms": (
                                ordinary_future_source_result.snapshot.read_ms
                            ),
                            "capture_attempts": (
                                ordinary_future_source_result.snapshot.attempts
                            ),
                            "capture_frscreen_update_serial": (
                                ordinary_future_source_result.snapshot
                                .update_serial_after
                            ),
                            "source_closure_complete": (
                                closure.projection.source_closure_complete
                            ),
                            "source_closure_reason": (
                                closure.projection.source_closure_reason
                            ),
                            "source_count": closure.source_count,
                            "auxiliary_count": closure.auxiliary_count,
                            "timeline_spawn_count": (
                                closure.timeline_spawn_count
                            ),
                            "health_transition_proven_count": (
                                closure.health_transition_proven_count
                            ),
                            "health_transition_minimum_margin": (
                                closure.health_transition_minimum_margin
                            ),
                            "direct_fire_event_count": len(
                                closure.direct_fire_events
                            ),
                            "future_aabb_trajectory_count": len(
                                closure.projection.aabb_trajectories
                            ),
                            "future_sector_trajectory_count": len(
                                closure.projection.trajectories
                            ),
                            "digest": closure.projection.digest,
                            "changes_input": False,
                        }
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as error:
                    ordinary_future_source_result = None
                    trace_sink.emit(
                        {
                            "kind": "ordinary_future_source_projection",
                            "frame": counter_after_read,
                            "source_closure_complete": False,
                            "source_closure_reason": str(error),
                            "changes_input": False,
                        }
                    )
                ordinary_future_source_future = None
            ordinary_future_source_due = (
                ordinary_preexhaustion_authority
                and not bool(spell_state["active"])
                and int(player["phase"]) not in (1, 2)
                and ordinary_future_ecl is not None
                and future_source_executor is not None
                and ordinary_future_source_future is None
                and (
                    runtime_ecl_identity_service is not None
                    and runtime_ecl_identity_service.accepted_version
                    is not None
                )
                and (
                    counter_after_read
                    - ordinary_future_source_last_submit
                    >= ORDINARY_FUTURE_SOURCE_CAPTURE_INTERVAL_FRAMES
                )
            )
            if ordinary_future_source_due:
                ordinary_future_source_future = (
                    future_source_executor.submit(
                        capture_and_project_ordinary_future_sources,
                        reader,
                        ordinary_future_ecl,
                        horizon_frames=(
                            ORDINARY_FUTURE_SOURCE_HORIZON_FRAMES
                        ),
                    )
                )
                ordinary_future_source_last_submit = counter_after_read
            pending_command_estimate = delay_estimator.pending_estimate(
                frame=counter_after_read,
            )
            corridor_started = time.perf_counter()
            corridor_updated = False
            corridor_completed = False
            corridor_submitted = False
            if corridor_pending_solution is not None:
                pending_candidate = corridor_pending_solution
                (
                    corridor_solution,
                    corridor_pending_solution,
                ) = _stage_corridor_solution(
                    corridor_solution,
                    corridor_pending_solution,
                    current_frame=counter_after_read,
                    context_key=corridor_context,
                )
                if corridor_solution is pending_candidate:
                    corridor_commitment.accept(
                        corridor_solution,
                        current_frame=counter_after_read,
                    )
                    corridor_updated = True
            if corridor_future is not None and corridor_future.done():
                completed_solution = corridor_future.result()
                corridor_future = None
                corridor_completed = True
                corridor_policy_lead.observe(
                    completed_solution.worker_ms
                    if completed_solution.worker_ms is not None
                    else completed_solution.solve_ms
                )
                (
                    corridor_solution,
                    corridor_pending_solution,
                ) = _stage_corridor_solution(
                    corridor_solution,
                    completed_solution,
                    current_frame=counter_after_read,
                    context_key=corridor_context,
                )
                if (
                    corridor_pending_solution is None
                    and corridor_solution is completed_solution
                ):
                    corridor_commitment.accept(
                        completed_solution,
                        current_frame=counter_after_read,
                    )
                    corridor_updated = True
            corridor_required_scale_horizon = (
                max(0, hazard_snapshot_age)
                + max(0, corridor_policy_lead.frames)
                + TH08_CORRIDOR_CONFIG.horizon_frames
                + 1
            )
            corridor_scale_schedule_supported = (
                _corridor_scale_schedule_supported(
                    captured_iteration.time_scale_schedule,
                    horizon=corridor_required_scale_horizon,
                )
            )
            corridor_time_scale_hard_authority = (
                _time_scale_schedule_hard_authority(
                    captured_iteration.time_scale_schedule
                )
            )
            corridor_submission_due = _corridor_submit_due(
                current_frame=counter_after_read,
                last_submit_frame=corridor_last_submit,
                interval_frames=args.corridor_every,
            )
            forecast_lead_frames = corridor_policy_lead.frames
            policy_source_frame = counter_after_read + forecast_lead_frames
            policy_hazard_horizon_frame = (
                policy_source_frame + TH08_CORRIDOR_CONFIG.horizon_frames
            )
            ordinary_submission = bool(
                ordinary_preexhaustion_authority
                and not bool(spell_state["active"])
            )
            ordinary_future_projection: (
                OrdinaryFutureHazardProjection | None
            ) = None
            if ordinary_submission:
                ordinary_future_projection = (
                    _ordinary_submission_projection(
                        ordinary_future_source_result,
                        policy_source_frame=policy_source_frame,
                        policy_horizon_frames=(
                            TH08_CORRIDOR_CONFIG.horizon_frames
                        ),
                    )
                )
            if (
                corridor_executor is not None
                and corridor_future is None
                and corridor_pending_solution is None
                and (
                    captured_iteration.player_projection_authority
                    != "unknown_incomplete_source_schedule"
                )
                and corridor_scale_schedule_supported
                and corridor_submission_due
                and _corridor_submission_policy_allows(
                    authority_only=args.authority_only_corridor,
                    time_scale_hard_authority=(
                        corridor_time_scale_hard_authority
                    ),
                )
                and (
                    not ordinary_submission
                    or ordinary_future_projection is not None
                )
            ):
                policy_delay_support = delay_support_envelope(
                    delay_estimate.support,
                    minimum=LIVE_CONTROL_DELAY_MIN,
                    maximum=LIVE_CONTROL_DELAY_MAX,
                    padding=ASYNC_POLICY_DELAY_PADDING,
                )
                if (
                    ordinary_preexhaustion_authority
                    and 0 not in policy_delay_support
                ):
                    # A command already pending at the future publication
                    # epoch can have zero residual pickup delay.  Treating
                    # the held mask as a fresh write over (0..max) is a
                    # conservative superset of that exact no-write branch.
                    policy_delay_support = (0, *policy_delay_support)
                forecast_player_x, forecast_player_y = (
                    _project_player_for_read_lag(
                        captured_iteration.projected_player_x,
                        captured_iteration.projected_player_y,
                        previous_mask,
                        forecast_lead_frames,
                        player_scale_bits=(
                            captured_iteration.time_scale_schedule
                            .require_player_horizon(
                                forecast_lead_frames
                            )
                        ),
                    )
                )
                corridor_future = corridor_executor.submit(
                    _solve_corridor,
                    source_frame=policy_source_frame,
                    snapshot_frame=counter_after_read,
                    forecast_lead_frames=forecast_lead_frames,
                    player_x=forecast_player_x,
                    player_y=forecast_player_y,
                    bullets=bullets,
                    lasers=lasers,
                    enemy_bodies=(
                        exact_contact_enemy_bodies
                        if ordinary_submission
                        else enemy_bodies
                    ),
                    future_hazard_projection=(
                        ordinary_future_projection
                    ),
                    snapshot_lag=hazard_snapshot_age,
                    control_delay_candidates=policy_delay_support,
                    observed_control_delay_candidates=(
                        delay_estimate.support
                    ),
                    nominal_control_delay=control_delay_frames,
                    active_action=_action_name_from_mask(previous_mask),
                    safety_value_horizon_frames=(
                        ordinary_safety_value_horizon
                    ),
                    retain_safety_action_values=(
                        False
                    ),
                    required_gate_lane=(
                        corridor_commitment.active_lane(counter_after_read)
                    ),
                    context_key=corridor_context,
                    audit_capsule_dir=args.viability_audit_dir,
                    audit_executor=audit_executor,
                    background_low_priority=(
                        ordinary_preexhaustion_authority
                        and not bool(spell_state["active"])
                    ),
                    native_viability_worker_limit=(
                        ORDINARY_AUTHORITY_NATIVE_WORKERS
                        if (
                            ordinary_preexhaustion_authority
                            and not bool(spell_state["active"])
                        )
                        else args.corridor_native_workers
                    ),
                    time_scale_schedule=(
                        captured_iteration.time_scale_schedule
                    ),
                    corridor_config=(
                        ORDINARY_AUTHORITY_CORRIDOR_CONFIG
                        if (
                            ordinary_preexhaustion_authority
                            and not bool(spell_state["active"])
                        )
                        else TH08_CORRIDOR_CONFIG
                    ),
                )
                corridor_last_submit = counter_after_read
                corridor_submitted = True
            observed_input_action = _action_name_from_mask(
                captured_iteration.native_active_mask
            )
            policy_query_request = PolicyQueryRequest(
                solution=corridor_solution,
                target_frame=(
                    captured_iteration.source_frame
                    + captured_iteration.control_delay_frames
                ),
                query_frame=captured_iteration.snapshot_frame,
                player_x=captured_iteration.projected_player_x,
                player_y=captured_iteration.projected_player_y,
                active_action=_action_name_from_mask(
                    captured_iteration.held_desired_mask
                ),
                observed_action=observed_input_action,
                lookahead_frames=args.corridor_lookahead,
                max_age_frames=args.corridor_max_age,
                current_delay_frames=(
                    captured_iteration.delay_estimate.support
                ),
            )
            primary_policy_query = policy_coordinator.query_primary(
                policy_query_request
            )
            corridor_target = primary_policy_query.target
            viability_query = primary_policy_query.viability_query
            pipeline_shadow_snapshot = build_pipeline_shadow_snapshot(
                supported_mask=SUPPORTED_INPUT_MASK,
                native_active_mask=captured_iteration.native_active_mask,
                held_desired_mask=captured_iteration.held_desired_mask,
                pending_estimate=pending_command_estimate,
                action_from_mask=_local_pipeline_action_from_mask,
                gameplay_epoch=captured_iteration.gameplay_epoch,
                stage_route_index=(
                    captured_iteration.stage_route_index
                ),
                spell_id=captured_iteration.spell_id,
                manager_frame=captured_iteration.source_frame,
                query_frame=captured_iteration.snapshot_frame,
                target_frame=policy_query_request.target_frame,
                player_x=captured_iteration.projected_player_x,
                player_y=captured_iteration.projected_player_y,
                hazard_horizon_frames=PLANNER_THREAT_HORIZON,
                corridor_solution=corridor_solution,
            )
            observed_local_pipeline_root = (
                pipeline_shadow_snapshot.local_root
            )
            local_pipeline_root_record = pipeline_shadow_snapshot.record
            policy_queries = policy_coordinator.complete_query(
                policy_query_request,
                primary_policy_query,
            )
            safety_value_query = policy_queries.safety_value_query
            policy_guidance = policy_queries.guidance
            corridor_action_authority = corridor_time_scale_hard_authority
            if (
                corridor_action_authority
                and ordinary_preexhaustion_authority
                and not bool(spell_state["active"])
            ):
                corridor_action_authority = (
                    _ordinary_solution_hazard_authority(
                        corridor_solution
                    )
                )
            if corridor_action_authority:
                actionable_corridor_target = corridor_target
                actionable_policy_guidance = policy_guidance
            else:
                actionable_corridor_target = None
                actionable_policy_guidance = replace(
                    policy_guidance,
                    support_covers_current=False,
                    allowed_first_actions=None,
                    repair_volumes=(),
                    recovery_distances=(),
                    safety_actions=(),
                    safety_state_value=None,
                    survival_actions=(),
                    survival_frames=None,
                    survival_bottleneck_margin=None,
                    position_error=0.0,
                )
            corridor_overhead_ms = (
                time.perf_counter() - corridor_started
            ) * 1000.0
            service_update = ServiceUpdate(
                context_key=captured_iteration.context_key,
                query_frame=captured_iteration.snapshot_frame,
                active_solution=corridor_solution,
                pending_solution=corridor_pending_solution,
                corridor_updated=corridor_updated,
                elapsed_ms=corridor_overhead_ms,
            )
            published_guidance = PublishedGuidance(
                capture=captured_iteration,
                service_update=service_update,
                request=policy_query_request,
                primary_query=primary_policy_query,
                completed_query=policy_queries,
                pipeline_shadow=pipeline_shadow_snapshot,
            )
            action_hold_frames = _estimate_live_action_hold(
                tuple(decision_frame_deltas)
            )
            ordinary_future_hazard_coverage = None
            ordinary_prefix_certified_frames = 0
            ordinary_prefix_safe_actions: tuple[str, ...] | None = None
            ordinary_prefix_evaluated_actions: tuple[str, ...] = ()
            ordinary_terminal_candidate_actions: tuple[str, ...] = ()
            ordinary_terminal_probe_actions: tuple[str, ...] = ()
            ordinary_terminal_probe_result: (
                CausalPrepublicationFilter | None
            ) = None
            ordinary_prefix_certificate_ms = 0.0
            ordinary_terminal_probe_ms = 0.0
            published_future_projection = None
            delayed_projection_source = "unavailable"
            future_projection_offset = -1
            ordinary_authority_solution: CorridorSolution | None = None
            ordinary_future_policy_query_frame = 0
            (
                ordinary_authority_solution,
                ordinary_future_policy_query_frame,
            ) = _ordinary_authority_target(
                active_solution=corridor_solution,
                pending_solution=corridor_pending_solution,
                current_frame=captured_iteration.snapshot_frame,
            )
            future_viability_policy = _ordinary_lower_kernel(
                ordinary_authority_solution
            )
            if ordinary_authority_solution is not None:
                ordinary_required_hazard_horizon = (
                    ordinary_authority_solution.source_frame
                    + future_viability_policy.horizon_frames
                )
                published_future_coverage = (
                    ordinary_authority_solution.future_hazard_coverage
                )
                if (
                    published_future_coverage is not None
                    and published_future_coverage.root_frame
                    <= captured_iteration.snapshot_frame
                    and published_future_coverage.horizon_frame
                    >= ordinary_required_hazard_horizon
                ):
                    ordinary_future_hazard_coverage = (
                        rebase_hazard_coverage(
                            published_future_coverage,
                            root_frame=(
                                captured_iteration.snapshot_frame
                            ),
                            horizon_frame=(
                                ordinary_required_hazard_horizon
                            ),
                        )
                    )
                else:
                    ordinary_future_hazard_coverage = unknown_future_coverage(
                        root_frame=captured_iteration.snapshot_frame,
                        horizon_frames=(
                            ordinary_required_hazard_horizon
                            - captured_iteration.snapshot_frame
                        ),
                        hazard_version=corridor_hazard_version(
                            ordinary_authority_solution
                        ),
                    )
                ordinary_publication_lead = (
                    ordinary_authority_solution.source_frame
                    + ordinary_future_policy_query_frame
                    - captured_iteration.snapshot_frame
                )
                if (
                    ordinary_preexhaustion_authority
                    and not spell_state["active"]
                    and int(player["phase"]) not in (1, 2)
                    and (
                        player_control_root.scale_bits
                        == TH08_UNIT_TIME_SCALE_BITS
                    )
                    and observed_local_pipeline_root is not None
                    and ordinary_publication_lead > 0
                ):
                    ordinary_prefix_delay_frames = tuple(
                        range(LIVE_ACTION_HOLD_MAX + 1)
                    )
                    ordinary_prefix_hold_frames = max(
                        1,
                        ordinary_publication_lead
                        - max(ordinary_prefix_delay_frames),
                    )
                    candidate_prefix_certified_frames = (
                        ordinary_prefix_hold_frames
                        + max(ordinary_prefix_delay_frames)
                    )
                    published_future_projection = (
                        ordinary_authority_solution.future_hazard_projection
                    )
                    future_projection_offset = (
                        captured_iteration.snapshot_frame
                        - published_future_projection.root_frame
                        if isinstance(
                            published_future_projection,
                            OrdinaryFutureHazardProjection,
                        )
                        else -1
                    )
                    prefix_projection_usable = bool(
                        isinstance(
                            published_future_projection,
                            OrdinaryFutureHazardProjection,
                        )
                        and published_future_projection.version
                        == corridor_hazard_version(
                            ordinary_authority_solution
                        )
                        and published_future_projection.coverage.complete
                        and future_projection_offset >= 0
                        and (
                            future_projection_offset
                            + candidate_prefix_certified_frames
                            <= published_future_projection.horizon_frames
                        )
                    )
                    if prefix_projection_usable:
                        delayed_projection_source = "global_solution"
                        ordinary_prefix_certified_frames = (
                            candidate_prefix_certified_frames
                        )
                        # First query only terminal Boolean membership. This
                        # pass has no prefix authority and is never published;
                        # it selects a small conservative subset for the
                        # expensive per-frame hazard certificate below.
                        held_action_name = (
                            observed_local_pipeline_root
                            .held_desired_action
                        )
                        terminal_probe_planner_actions = (
                            _ordinary_terminal_probe_actions(
                                held_action=held_action_name,
                                recovery_distances=(
                                    policy_guidance.recovery_distances
                                ),
                                viable_repair_volumes=(
                                    policy_guidance.repair_volumes
                                ),
                            )
                        )
                        ordinary_terminal_probe_actions = tuple(
                            action.name
                            for action in terminal_probe_planner_actions
                        )
                        terminal_probe_started = time.perf_counter()
                        terminal_probe = (
                            _ordinary_nonspell_preexhaustion_filter(
                                enabled=True,
                                spell_active=False,
                                player_phase=int(player["phase"]),
                                root_scale_bits=(
                                    player_control_root.scale_bits
                                ),
                                root=observed_local_pipeline_root,
                                action_hold_frames=LIVE_ACTION_HOLD_MAX,
                                player_x=player_control_root.x,
                                player_y=player_control_root.y,
                                current_frame=(
                                    captured_iteration.snapshot_frame
                                ),
                                future_solution=(
                                    ordinary_authority_solution
                                ),
                                future_hazard_coverage=(
                                    ordinary_future_hazard_coverage
                                ),
                                future_policy_query_frame=(
                                    ordinary_future_policy_query_frame
                                ),
                                future_policy_source_frame=(
                                    ordinary_authority_solution.source_frame
                                ),
                                prefix_certified_frames=(
                                    candidate_prefix_certified_frames
                                ),
                                prefix_safe_actions=(
                                    ordinary_terminal_probe_actions
                                ),
                                selected_actions=(
                                    ordinary_terminal_probe_actions
                                ),
                            )
                        )
                        ordinary_terminal_probe_result = terminal_probe
                        ordinary_terminal_probe_ms = (
                            time.perf_counter() - terminal_probe_started
                        ) * 1000.0
                        ordinary_terminal_candidate_actions = (
                            terminal_probe.candidate_viable_actions
                        )
                        ordinary_prefix_actions = (
                            _ordinary_prefix_candidate_actions(
                                held_action=held_action_name,
                                terminal_candidates=(
                                    terminal_probe
                                    .candidate_viable_actions
                                ),
                                recovery_actions=(
                                    terminal_probe.recovery_actions
                                ),
                            )
                        )
                        ordinary_prefix_evaluated_actions = tuple(
                            action.name for action in ordinary_prefix_actions
                        )
                        if not ordinary_prefix_actions:
                            ordinary_prefix_safe_actions = ()
                        else:
                            ordinary_prefix_started = time.perf_counter()
                            ordinary_prefix_certificates = (
                                _robust_action_certificates(
                                    player_x=player_control_root.x,
                                    player_y=player_control_root.y,
                                    previous_mask=held_desired_mask,
                                    actions=ordinary_prefix_actions,
                                    delay_frames=(
                                        ordinary_prefix_delay_frames
                                    ),
                                    action_hold_frames=(
                                        ordinary_prefix_hold_frames
                                    ),
                                    bullets=bullets,
                                    lasers=lasers,
                                    enemy_bodies=exact_contact_enemy_bodies,
                                    snapshot_lag=player_to_hazard_lag,
                                    player_scale_bits=(
                                        captured_iteration
                                        .time_scale_schedule
                                        .require_player_horizon(
                                            candidate_prefix_certified_frames
                                        )
                                    ),
                                    laser_scale_bits=(
                                        captured_iteration
                                        .time_scale_schedule
                                        .require_laser_horizon(
                                            candidate_prefix_certified_frames
                                        )
                                    ),
                                    pipeline_root=(
                                        observed_local_pipeline_root
                                    ),
                                    future_hazard_projection=(
                                        published_future_projection
                                    ),
                                    future_projection_offset=(
                                        future_projection_offset
                                    ),
                                )
                            )
                            ordinary_prefix_certificate_ms = (
                                time.perf_counter()
                                - ordinary_prefix_started
                            ) * 1000.0
                            ordinary_prefix_safe_actions = tuple(
                                action.name
                                for action in ordinary_prefix_actions
                                if (
                                    ordinary_prefix_certificates[
                                        action.name
                                    ].worst_collisions
                                    == 0
                                    and ordinary_prefix_certificates[
                                        action.name
                                    ].min_clearance
                                    > 0.0
                                )
                            )
            if (
                published_future_projection is None
                and ordinary_future_source_result is not None
            ):
                candidate_projection = (
                    ordinary_future_source_result.closure.projection
                )
                candidate_offset = (
                    captured_iteration.snapshot_frame
                    - candidate_projection.root_frame
                )
                if (
                    candidate_projection.source_closure_complete
                    and candidate_projection.coverage.complete
                    and candidate_offset >= 0
                    and (
                        candidate_offset
                        + TH08_CORRIDOR_CONFIG.horizon_frames
                        <= candidate_projection.horizon_frames
                    )
                ):
                    published_future_projection = candidate_projection
                    future_projection_offset = candidate_offset
                    delayed_projection_source = (
                        "latest_complete_future_source_capture"
                    )
            if ordinary_terminal_probe_result is not None:
                ordinary_preexhaustion = (
                    _finalize_ordinary_terminal_probe(
                        ordinary_terminal_probe_result,
                        prefix_safe_actions=(
                            ordinary_prefix_safe_actions or ()
                        ),
                    )
                )
            else:
                ordinary_preexhaustion = (
                    _ordinary_nonspell_preexhaustion_filter(
                    enabled=ordinary_preexhaustion_authority,
                    spell_active=bool(spell_state["active"]),
                    player_phase=int(player["phase"]),
                    root_scale_bits=player_control_root.scale_bits,
                    root=observed_local_pipeline_root,
                    action_hold_frames=LIVE_ACTION_HOLD_MAX,
                    player_x=player_control_root.x,
                    player_y=player_control_root.y,
                    current_frame=captured_iteration.snapshot_frame,
                    future_solution=ordinary_authority_solution,
                    future_hazard_coverage=(
                        ordinary_future_hazard_coverage
                    ),
                    future_policy_query_frame=(
                        ordinary_future_policy_query_frame
                    ),
                    future_policy_source_frame=(
                        ordinary_authority_solution.source_frame
                        if ordinary_authority_solution is not None
                        else None
                    ),
                    prefix_certified_frames=(
                        ordinary_prefix_certified_frames
                    ),
                    prefix_safe_actions=(
                        ordinary_prefix_safe_actions
                    ),
                    # No complete prefix slab means no terminal query can
                    # acquire authority; avoid spending the physical lease on
                    # a diagnostic all-action scan.
                    selected_actions=(),
                    )
                )
            ordinary_continuation_lease_present_at_capture = bool(
                ordinary_continuation_lease is not None
            )
            ordinary_continuation_lease_capture_record = (
                ordinary_continuation_lease.record()
                if ordinary_continuation_lease is not None
                else None
            )
            ordinary_continuation_lease_revoked_reason: str | None = None
            ordinary_continuation_capture_check = ContinuationLeaseCheck(
                valid=False,
                reason="no_active_lease",
                age_frames=0,
                remaining_frames=0,
            )
            ordinary_continuation_capture_geometry_check = (
                ContinuationGeometryCheck(
                    valid=False,
                    reason="no_active_lease",
                    checked_frame_count=0,
                    checked_body_count=len(enemy_bodies),
                )
            )
            if ordinary_continuation_lease is not None:
                ordinary_continuation_capture_check = (
                    check_continuation_lease_capture(
                        ordinary_continuation_lease,
                        gameplay_epoch=gameplay_epoch,
                        stage_route_index=int(state["stage_route_index"]),
                        spell_active=bool(spell_state["active"]),
                        player_phase=int(player["phase"]),
                        unit_time_scale=bool(
                            player_control_root.scale_bits
                            == TH08_UNIT_TIME_SCALE_BITS
                        ),
                        current_frame=captured_iteration.snapshot_frame,
                        player_x=player_control_root.x,
                        player_y=player_control_root.y,
                        pipeline_root=observed_local_pipeline_root,
                        minimum_remaining_frames=(
                            ORDINARY_AUTHORITY_MIN_TERMINAL_LEAD
                        ),
                    )
                )
                if ordinary_continuation_capture_check.valid:
                    ordinary_continuation_capture_geometry_check = (
                        check_continuation_enemy_geometry(
                            ordinary_continuation_lease,
                            body_root_frame=(
                                captured_iteration.snapshot_frame
                            ),
                            valid_from_frame=(
                                captured_iteration.snapshot_frame
                            ),
                            enemy_bodies=exact_contact_enemy_bodies,
                        )
                    )
                if not ordinary_continuation_capture_check.valid:
                    ordinary_continuation_lease_revoked_reason = (
                        ordinary_continuation_capture_check.reason
                    )
                    ordinary_continuation_lease = None
                elif not ordinary_continuation_capture_geometry_check.valid:
                    ordinary_continuation_lease_revoked_reason = (
                        "fresh_geometry_not_contained_at_capture:"
                        f"{ordinary_continuation_capture_geometry_check.reason}"
                    )
                    ordinary_continuation_lease = None
            ordinary_continuation_lease_active = bool(
                ordinary_continuation_lease is not None
                and ordinary_continuation_capture_check.valid
                and ordinary_continuation_capture_geometry_check.valid
            )
            ordinary_continuation_renewal_due = bool(
                ordinary_continuation_lease_active
            )
            # The held-only v2 certificate is the computation guard for the
            # contingent delayed-issue table below.  The scan is itself a
            # no-write control interval and may not start without this proof
            # or a compatible older continuation lease.
            ordinary_causal_hold_reason = "not_needed"
            ordinary_causal_hold_action: str | None = None
            ordinary_causal_hold_safe = False
            ordinary_causal_hold_min_clearance: float | None = None
            ordinary_causal_hold_collisions: int | None = None
            ordinary_causal_hold_branch_count = 0
            ordinary_causal_hold_event_count = 0
            ordinary_causal_hold_projection_digest: str | None = None
            ordinary_causal_hold_horizon = 0
            ordinary_causal_hold_ms = 0.0
            ordinary_causal_delayed_reason = "not_needed"
            ordinary_causal_delayed_actions: tuple[str, ...] = ()
            ordinary_causal_delayed_evaluated_actions: tuple[str, ...] = ()
            ordinary_causal_delayed_incremental_observations: tuple[
                tuple[str, int, bool], ...
            ] = ()
            ordinary_causal_delayed_ranking_action: str | None = None
            ordinary_causal_delayed_ranking_ms = 0.0
            ordinary_causal_delayed_ranking_proposal: (
                LocalProposal | None
            ) = None
            ordinary_causal_delayed_ranking_proposal_reused = False
            ordinary_causal_delayed_safe_union: tuple[str, ...] = ()
            ordinary_causal_delayed_issue_support: tuple[int, ...] = ()
            ordinary_causal_delayed_pickup_support: tuple[int, ...] = ()
            ordinary_causal_delayed_certificates: dict[
                int, dict[str, RobustActionCertificate]
            ] = {}
            ordinary_causal_delayed_projection_records: tuple[
                tuple[str, str, int], ...
            ] = ()
            ordinary_causal_delayed_horizon = 0
            ordinary_causal_delayed_ms = 0.0
            ordinary_causal_delayed_fresh_enemy_ms = 0.0
            ordinary_causal_delayed_fresh_enemy_reason = "not_needed"
            ordinary_causal_delayed_post_fresh_safe_union: tuple[
                str, ...
            ] = ()
            ordinary_causal_delayed_trigger_reason = (
                ordinary_preexhaustion.reason
            )
            ordinary_causal_delayed_scan_key = (
                gameplay_epoch,
                int(state["stage_route_index"]),
            )
            ordinary_causal_delayed_scan_due = bool(
                ordinary_continuation_renewal_due
                or ordinary_continuation_lease_revoked_reason is not None
                or ordinary_causal_delayed_last_scan is None
                or ordinary_causal_delayed_last_scan[0]
                != ordinary_causal_delayed_scan_key
                or (
                    captured_iteration.snapshot_frame
                    - ordinary_causal_delayed_last_scan[1]
                    >= ORDINARY_CAUSAL_SCAN_INTERVAL_FRAMES
                )
            )
            if (
                observed_local_pipeline_root is not None
                and observed_local_pipeline_root.pending_action is not None
                and not ordinary_continuation_lease_active
            ):
                ordinary_causal_delayed_reason = (
                    "older_pending_must_resolve_before_delayed_direction_scan"
                )
            if (
                ORDINARY_CAUSAL_COMPUTATION_GUARD_ENABLED
                and ordinary_preexhaustion_authority
                and ordinary_preexhaustion.authority_eligible
                and ordinary_preexhaustion.reason
                == "prepublication_viable_predecessor_empty"
                and observed_local_pipeline_root is not None
                and observed_local_pipeline_root.pending_action is None
            ):
                ordinary_causal_hold_reason = "prerequisite_unavailable"
                held_action_name = (
                    observed_local_pipeline_root.held_desired_action
                )
                held_action = next(
                    (
                        action
                        for action in _PLANNER_ACTIONS
                        if action.name == held_action_name
                    ),
                    None,
                )
                causal_horizon = (
                    min(
                        TH08_CORRIDOR_CONFIG.horizon_frames,
                        (
                            published_future_projection.horizon_frames
                            - future_projection_offset
                        ),
                    )
                    if isinstance(
                        published_future_projection,
                        OrdinaryFutureHazardProjection,
                    )
                    and future_projection_offset >= 0
                    else 0
                )
                causal_delay_frames = tuple(
                    range(LIVE_ACTION_HOLD_MAX + 1)
                )
                causal_hold_frames = (
                    causal_horizon - max(causal_delay_frames)
                )
                causal_projection_usable = bool(
                    held_action is not None
                    and isinstance(
                        published_future_projection,
                        OrdinaryFutureHazardProjection,
                    )
                    and future_projection_offset >= 0
                    and causal_hold_frames > 0
                    and future_projection_offset + causal_horizon
                    <= published_future_projection.horizon_frames
                )
                if causal_projection_usable:
                    ordinary_causal_hold_horizon = causal_horizon
                    causal_hold_started = time.perf_counter()
                    try:
                        causal_player_scale_bits = (
                            captured_iteration.time_scale_schedule
                            .require_player_horizon(causal_horizon)
                        )
                        causal_player_positions = (
                            _causal_pipeline_player_positions(
                                root=observed_local_pipeline_root,
                                selected_action=held_action_name,
                                delay_frames=causal_delay_frames,
                                horizon_frames=causal_horizon,
                                player_x=player_control_root.x,
                                player_y=player_control_root.y,
                                player_scale_bits=(
                                    causal_player_scale_bits
                                ),
                            )
                        )
                        causal_projection = (
                            condition_future_hazard_projection_on_player_paths(
                                published_future_projection,
                                source_frame=(
                                    captured_iteration.snapshot_frame
                                ),
                                horizon_frames=causal_horizon,
                                player_positions_by_step=(
                                    causal_player_positions
                                ),
                            )
                        )
                        causal_certificate = _robust_action_certificates(
                            player_x=player_control_root.x,
                            player_y=player_control_root.y,
                            previous_mask=held_desired_mask,
                            actions=(held_action,),
                            delay_frames=causal_delay_frames,
                            action_hold_frames=causal_hold_frames,
                            bullets=bullets,
                            lasers=lasers,
                            enemy_bodies=exact_contact_enemy_bodies,
                            snapshot_lag=player_to_hazard_lag,
                            player_scale_bits=causal_player_scale_bits,
                            laser_scale_bits=(
                                captured_iteration.time_scale_schedule
                                .require_laser_horizon(causal_horizon)
                            ),
                            pipeline_root=observed_local_pipeline_root,
                            future_hazard_projection=causal_projection,
                            future_projection_offset=0,
                        )[held_action_name]
                        ordinary_causal_hold_action = held_action_name
                        ordinary_causal_hold_min_clearance = (
                            causal_certificate.min_clearance
                        )
                        ordinary_causal_hold_collisions = (
                            causal_certificate.worst_collisions
                        )
                        ordinary_causal_hold_branch_count = (
                            causal_certificate.pipeline_branch_count
                        )
                        ordinary_causal_hold_event_count = len(
                            causal_projection.direct_fire_events
                        )
                        ordinary_causal_hold_projection_digest = (
                            causal_projection.digest
                        )
                        ordinary_causal_hold_safe = bool(
                            causal_certificate.worst_collisions == 0
                            and causal_certificate.min_clearance > 0.0
                        )
                        ordinary_causal_hold_reason = (
                            "constant_hold_remaining_horizon_safe"
                            if ordinary_causal_hold_safe
                            else "constant_hold_remaining_horizon_unsafe"
                        )
                    except (KeyError, TypeError, ValueError) as error:
                        ordinary_causal_hold_reason = (
                            "causal_conditioning_failed:"
                            f"{type(error).__name__}:{error}"
                        )
                    ordinary_causal_hold_ms = (
                        time.perf_counter() - causal_hold_started
                    ) * 1000.0
            (
                ordinary_causal_delayed_computation_guard_passed,
                ordinary_causal_delayed_computation_guard_reason,
            ) = _ordinary_delayed_computation_guard(
                continuation_lease_active=(
                    ordinary_continuation_lease_active
                ),
                held_action_safe=ordinary_causal_hold_safe,
                held_action_reason=ordinary_causal_hold_reason,
            )
            if (
                ordinary_preexhaustion_authority
                and ordinary_preexhaustion.reason
                in {
                    "prepublication_viable_predecessor_empty",
                    "future_policy_unavailable",
                }
                and observed_local_pipeline_root is not None
                and observed_local_pipeline_root.pending_action is None
                and ordinary_causal_delayed_scan_due
                and not ordinary_causal_delayed_computation_guard_passed
            ):
                ordinary_causal_delayed_reason = (
                    "computation_guard_"
                    f"{ordinary_causal_delayed_computation_guard_reason}"
                )
            if (
                ordinary_preexhaustion_authority
                and not bool(spell_state["active"])
                and int(player["phase"]) not in (1, 2)
                and (
                    player_control_root.scale_bits
                    == TH08_UNIT_TIME_SCALE_BITS
                )
                and ordinary_preexhaustion.reason
                in {
                    "prepublication_viable_predecessor_empty",
                    "future_policy_unavailable",
                }
                and observed_local_pipeline_root is not None
                and (
                    (
                        ordinary_continuation_lease_active
                        and ordinary_continuation_renewal_due
                    )
                    or (
                        not ordinary_continuation_lease_active
                        and observed_local_pipeline_root.pending_action is None
                    )
                )
                and ordinary_causal_delayed_scan_due
                and ordinary_causal_delayed_computation_guard_passed
            ):
                ordinary_causal_delayed_last_scan = (
                    ordinary_causal_delayed_scan_key,
                    captured_iteration.snapshot_frame,
                )
                ordinary_causal_delayed_reason = "prerequisite_unavailable"
                if ordinary_continuation_lease_active:
                    assert ordinary_continuation_lease is not None
                    ordinary_causal_delayed_trigger_reason = (
                        "terminal_continuation_renewal_due"
                    )
                    ordinary_causal_delayed_ranking_action = (
                        ordinary_continuation_lease.action
                    )
                    causal_actions = _ordinary_terminal_probe_actions(
                        held_action=ordinary_continuation_lease.action,
                        recovery_distances=(
                            policy_guidance.recovery_distances
                        ),
                        viable_repair_volumes=(
                            policy_guidance.repair_volumes
                        ),
                    )
                else:
                    ranking_started = time.perf_counter()
                    ranking_authority = (
                        CORRIDOR_ALLOWED_ACTION_AUTHORITY
                        if (
                            corridor_action_authority
                            and actionable_policy_guidance
                            .allowed_first_actions
                            is not None
                        )
                        else None
                    )
                    ranking_proposal = choose_local_proposal_request(
                        _local_planner_request_from_capture(
                            capture=published_guidance.capture,
                            pipeline_root=observed_local_pipeline_root,
                            action_hold_frames=action_hold_frames,
                            corridor_target=actionable_corridor_target,
                            policy_guidance=actionable_policy_guidance,
                            allowed_action_authority=ranking_authority,
                            horizon=args.horizon,
                            threat_horizon=args.threat_horizon,
                            beam_width=args.beam_width,
                            losing_control_reserve=(
                                args.losing_control_reserve
                            ),
                            preserve_previous_direction_inertia=(
                                not corridor_context_changed
                            ),
                        )
                    )
                    ordinary_causal_delayed_ranking_action = (
                        ranking_proposal.decision.action
                    )
                    ordinary_causal_delayed_ranking_proposal = (
                        ranking_proposal
                    )
                    ordinary_causal_delayed_ranking_ms = (
                        time.perf_counter() - ranking_started
                    ) * 1000.0
                    causal_actions = _ordinary_terminal_probe_actions(
                        held_action=(
                            observed_local_pipeline_root
                            .held_desired_action
                        ),
                        recovery_distances=(
                            policy_guidance.recovery_distances
                        ),
                        viable_repair_volumes=(
                            policy_guidance.repair_volumes
                        ),
                    )
                    causal_actions = _prioritize_ordinary_delayed_actions(
                        causal_actions,
                        planned_action=(
                            ordinary_causal_delayed_ranking_action
                        ),
                    )
                causal_horizon = (
                    min(
                        TH08_CORRIDOR_CONFIG.horizon_frames,
                        (
                            published_future_projection.horizon_frames
                            - future_projection_offset
                        ),
                    )
                    if isinstance(
                        published_future_projection,
                        OrdinaryFutureHazardProjection,
                    )
                    and future_projection_offset >= 0
                    else 0
                )
                causal_pickup_delay_frames = tuple(
                    range(LIVE_ACTION_HOLD_MAX + 1)
                )
                causal_issue_delay_frames = tuple(
                    range(
                        ORDINARY_CAUSAL_ISSUE_DELAY_MIN,
                        min(
                            ORDINARY_CAUSAL_ISSUE_DELAY_MAX,
                            causal_horizon
                            - max(causal_pickup_delay_frames)
                            - 1,
                        )
                        + 1
                    )
                ) if (
                    causal_horizon
                    - max(causal_pickup_delay_frames)
                    - 1
                    >= ORDINARY_CAUSAL_ISSUE_DELAY_MIN
                ) else ()
                causal_projection_usable = bool(
                    causal_actions
                    and isinstance(
                        published_future_projection,
                        OrdinaryFutureHazardProjection,
                    )
                    and future_projection_offset >= 0
                    and causal_issue_delay_frames
                    and future_projection_offset + causal_horizon
                    <= published_future_projection.horizon_frames
                )
                if causal_projection_usable:
                    ordinary_causal_delayed_actions = tuple(
                        action.name for action in causal_actions
                    )
                    ordinary_causal_delayed_issue_support = (
                        causal_issue_delay_frames
                    )
                    ordinary_causal_delayed_pickup_support = (
                        causal_pickup_delay_frames
                    )
                    ordinary_causal_delayed_horizon = causal_horizon
                    causal_delayed_started = time.perf_counter()
                    try:
                        causal_player_scale_bits = (
                            captured_iteration.time_scale_schedule
                            .require_player_horizon(causal_horizon)
                        )
                        causal_laser_scale_bits = (
                            captured_iteration.time_scale_schedule
                            .require_laser_horizon(causal_horizon)
                        )
                        causal_projections: dict[
                            str, OrdinaryFutureHazardProjection
                        ] = {}
                        incremental_observations: list[
                            tuple[str, int, bool]
                        ] = []
                        evaluated_action_names: list[str] = []
                        # Candidate actions are independent exact
                        # predecessors.  Stop once one is safe at the
                        # non-authoritative intermediate age instead of
                        # spending the remaining physical lease computing
                        # actions that cannot enlarge that certificate.  The
                        # later fresh read and exact issue-age row remain the
                        # only authority.
                        for causal_action in causal_actions:
                            action_rows, action_projections = (
                                _delayed_issue_action_certificates(
                                    root=observed_local_pipeline_root,
                                    actions=(causal_action,),
                                    issue_delay_frames=(
                                        causal_issue_delay_frames
                                    ),
                                    pickup_delay_frames=(
                                        causal_pickup_delay_frames
                                    ),
                                    horizon_frames=causal_horizon,
                                    player_x=player_control_root.x,
                                    player_y=player_control_root.y,
                                    bullets=bullets,
                                    lasers=lasers,
                                    enemy_bodies=exact_contact_enemy_bodies,
                                    snapshot_lag=player_to_hazard_lag,
                                    player_scale_bits=(
                                        causal_player_scale_bits
                                    ),
                                    laser_scale_bits=(
                                        causal_laser_scale_bits
                                    ),
                                    future_hazard_projection=(
                                        published_future_projection
                                    ),
                                    source_frame=(
                                        captured_iteration.snapshot_frame
                                    ),
                                )
                            )
                            for issue_delay, row in action_rows.items():
                                ordinary_causal_delayed_certificates.setdefault(
                                    issue_delay, {}
                                ).update(row)
                            causal_projections.update(action_projections)
                            evaluated_action_names.append(
                                causal_action.name
                            )
                            intermediate_issue_age = max(
                                0,
                                reader.u32(ADDR_ENEMY_MANAGER_FRAME)
                                - captured_iteration.snapshot_frame,
                            )
                            intermediate_certificate = (
                                action_rows.get(
                                    intermediate_issue_age, {}
                                ).get(causal_action.name)
                            )
                            intermediate_safe = bool(
                                intermediate_certificate is not None
                                and intermediate_certificate
                                .worst_collisions == 0
                                and intermediate_certificate.min_clearance
                                > 0.0
                            )
                            incremental_observations.append(
                                (
                                    causal_action.name,
                                    intermediate_issue_age,
                                    intermediate_safe,
                                )
                            )
                            if intermediate_safe:
                                break
                        ordinary_causal_delayed_evaluated_actions = tuple(
                            evaluated_action_names
                        )
                        ordinary_causal_delayed_incremental_observations = (
                            tuple(incremental_observations)
                        )
                        ordinary_causal_delayed_safe_union = tuple(
                            action.name
                            for action in causal_actions
                            if action.name in evaluated_action_names
                            if any(
                                action.name in row
                                and row[action.name].worst_collisions == 0
                                and row[action.name].min_clearance > 0.0
                                for row in (
                                    ordinary_causal_delayed_certificates
                                    .values()
                                )
                            )
                        )
                        ordinary_causal_delayed_projection_records = tuple(
                            (
                                key,
                                projection.digest,
                                len(projection.direct_fire_events),
                            )
                            for key, projection in sorted(
                                causal_projections.items()
                            )
                        )
                        ordinary_causal_delayed_reason = (
                            "contingent_issue_table_has_safe_action"
                            if ordinary_causal_delayed_safe_union
                            else "contingent_issue_table_empty"
                        )
                    except (KeyError, TypeError, ValueError) as error:
                        ordinary_causal_delayed_reason = (
                            "delayed_causal_conditioning_failed:"
                            f"{type(error).__name__}:{error}"
                        )
                    ordinary_causal_delayed_ms = (
                        time.perf_counter() - causal_delayed_started
                    ) * 1000.0
            allowed_action_authority = (
                CORRIDOR_ALLOWED_ACTION_AUTHORITY
                if (
                    corridor_action_authority
                    and actionable_policy_guidance.allowed_first_actions
                    is not None
                )
                else None
            )
            if (
                allowed_action_authority is None
                and ordinary_preexhaustion.applicable
                and ordinary_preexhaustion.allowed_actions is not None
            ):
                actionable_policy_guidance = replace(
                    actionable_policy_guidance,
                    support_covers_current=True,
                    allowed_first_actions=(
                        ordinary_preexhaustion.allowed_actions
                    ),
                    repair_volumes=(),
                    recovery_distances=(),
                    safety_actions=(),
                    safety_state_value=None,
                    survival_actions=(),
                    survival_frames=None,
                    survival_bottleneck_margin=None,
                    position_error=0.0,
                )
                allowed_action_authority = (
                    ORDINARY_PREEXHAUSTION_AUTHORITY
                )
            if (
                allowed_action_authority is None
                and ordinary_causal_delayed_safe_union
            ):
                actionable_policy_guidance = replace(
                    actionable_policy_guidance,
                    support_covers_current=True,
                    allowed_first_actions=(
                        ordinary_causal_delayed_safe_union
                    ),
                    repair_volumes=(),
                    recovery_distances=(),
                    safety_actions=(),
                    safety_state_value=None,
                    survival_actions=(),
                    survival_frames=None,
                    survival_bottleneck_margin=None,
                    position_error=0.0,
                )
                allowed_action_authority = (
                    ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                )
            if (
                allowed_action_authority is None
                and ordinary_continuation_lease_active
                and ordinary_continuation_lease is not None
            ):
                actionable_policy_guidance = replace(
                    actionable_policy_guidance,
                    support_covers_current=True,
                    allowed_first_actions=(
                        ordinary_continuation_lease.action,
                    ),
                    repair_volumes=(),
                    recovery_distances=(),
                    safety_actions=(),
                    safety_state_value=None,
                    survival_actions=(),
                    survival_frames=None,
                    survival_bottleneck_margin=None,
                    position_error=0.0,
                )
                allowed_action_authority = (
                    ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY
                )
            if (
                allowed_action_authority is None
                and ordinary_causal_hold_safe
                and ordinary_causal_hold_action is not None
            ):
                actionable_policy_guidance = replace(
                    actionable_policy_guidance,
                    support_covers_current=True,
                    allowed_first_actions=(ordinary_causal_hold_action,),
                    repair_volumes=(),
                    recovery_distances=(),
                    safety_actions=(),
                    safety_state_value=None,
                    survival_actions=(),
                    survival_frames=None,
                    survival_bottleneck_margin=None,
                    position_error=0.0,
                )
                allowed_action_authority = ORDINARY_CAUSAL_HOLD_AUTHORITY
            early_kill_allowed_actions = (
                actionable_policy_guidance.allowed_first_actions
            )
            damage_target_x: float | None = None
            damage_target_half_width = 0.0
            damageable = False
            if (
                boss_phase_snapshot is not None
                and boss_phase_progress is not None
                and spell_enemy_body_guard is not None
                and spell_enemy_body_guard.body.pointer
                == boss_phase_snapshot.pointer
            ):
                boss_body = spell_enemy_body_guard.body
                damage_target_x = (
                    boss_body.x
                    + boss_body.vx
                    * (player_to_hazard_lag + args.horizon)
                )
                # Damage uses the raw contact AABB at 0x00451670; lethal
                # body contact separately divides that size by 1.5f.
                if spell_enemy_body_guard.raw_contact_width is not None:
                    damage_target_half_width = (
                        enemy_contact_size_to_damage_half_extent(
                            spell_enemy_body_guard.raw_contact_width
                        )
                    )
                else:
                    damage_target_half_width = (
                        enemy_lethal_to_damage_half_extent(
                            spell_enemy_body_guard.body.half_width
                        )
                    )
                damageable = boss_phase_progress.state.damageable
            plan_started = time.perf_counter()
            local_proposal = (
                ordinary_causal_delayed_ranking_proposal
                if ordinary_causal_delayed_ranking_proposal is not None
                else choose_local_proposal_request(
                    LocalPlannerRequest(
                    physical=PhysicalHazardSnapshot(
                        player_x=(
                            published_guidance.capture.player_x
                        ),
                        player_y=(
                            published_guidance.capture.player_y
                        ),
                        bullets=published_guidance.capture.bullets,
                        lasers=published_guidance.capture.lasers,
                        time_scale_schedule=(
                            published_guidance.capture.time_scale_schedule
                        ),
                        enemy_bodies=(
                            published_guidance.capture.enemy_bodies
                        ),
                        items=published_guidance.capture.items,
                        snapshot_lag=(
                            published_guidance.capture.player_to_hazard_lag
                        ),
                    ),
                    actuator=ActuatorPipeline(
                        previous_direction=(
                            published_guidance.capture.previous_direction
                        ),
                        can_bomb=published_guidance.capture.can_bomb,
                        previous_focus=bool(
                            published_guidance.capture.held_desired_mask
                            & FOCUS
                        ),
                        control_delay_frames=(
                            published_guidance.capture.control_delay_frames
                        ),
                        control_delay_candidates=(
                            published_guidance.capture.delay_estimate.support
                        ),
                        action_hold_frames=action_hold_frames,
                        local_pipeline_root=observed_local_pipeline_root,
                    ),
                    guidance=GlobalGuidance(
                        target_x=(
                            actionable_corridor_target[0]
                            if actionable_corridor_target is not None
                            else None
                        ),
                        target_y=(
                            actionable_corridor_target[1]
                            if actionable_corridor_target is not None
                            else None
                        ),
                        target_deadline=(
                            actionable_corridor_target[2]
                            if actionable_corridor_target is not None
                            else None
                        ),
                        allowed_first_actions=(
                            actionable_policy_guidance.allowed_first_actions
                        ),
                        allowed_action_authority=(
                            allowed_action_authority
                        ),
                        allow_coarse_viability_relaxation=(
                            _allow_coarse_viability_relaxation(
                                allowed_action_authority
                            )
                        ),
                        viability_repair_volumes=(
                            actionable_policy_guidance.repair_volumes
                        ),
                        viability_recovery_distances=(
                            actionable_policy_guidance.recovery_distances
                        ),
                        viability_safety_actions=(
                            actionable_policy_guidance.safety_actions
                        ),
                        viability_safety_state_value=(
                            actionable_policy_guidance.safety_state_value
                        ),
                        viability_survival_actions=(
                            actionable_policy_guidance.survival_actions
                        ),
                        viability_survival_frames=(
                            actionable_policy_guidance.survival_frames
                        ),
                        viability_survival_bottleneck_margin=(
                            actionable_policy_guidance
                            .survival_bottleneck_margin
                        ),
                        viability_position_error=(
                            actionable_policy_guidance.position_error
                        ),
                    ),
                    config=PlannerConfig(
                        horizon=args.horizon,
                        threat_horizon=args.threat_horizon,
                        beam_width=args.beam_width,
                        losing_control_reserve=(
                            args.losing_control_reserve
                        ),
                        preserve_previous_direction_inertia=(
                            not corridor_context_changed
                        ),
                    ),
                    objective=ObjectiveContext(
                        power=published_guidance.capture.power,
                        bombs=published_guidance.capture.bombs,
                        damage_target_x=damage_target_x,
                        damage_target_half_width=(
                            damage_target_half_width
                        ),
                        damageable=damageable,
                    ),
                    )
                )
            )
            ordinary_causal_delayed_ranking_proposal_reused = bool(
                ordinary_causal_delayed_ranking_proposal is not None
            )
            decision = local_proposal.decision
            if kill_before_saturation_observation.target is not None:
                kill_before_saturation_preference = (
                    choose_kill_before_saturation_preference(
                        decision.action,
                        target=(
                            kill_before_saturation_observation.target
                        ),
                        player_x=(
                            published_guidance.capture.projected_player_x
                        ),
                        action_hold_frames=action_hold_frames,
                        target_forecast_frames=(
                            max(
                                published_guidance.capture
                                .delay_estimate.support,
                                default=(
                                    published_guidance.capture
                                    .control_delay_frames
                                ),
                            )
                            + action_hold_frames
                        ),
                        allowed_first_actions=(
                            early_kill_allowed_actions
                        ),
                        actions=_PLANNER_ACTIONS,
                    )
                )
                kill_before_saturation_preference_source = (
                    "observed_enemy"
                )
            else:
                kill_before_saturation_preference = None
                kill_before_saturation_preference_source = None
            kill_before_saturation_preferred_action = (
                kill_before_saturation_preference.action
                if kill_before_saturation_preference is not None
                else None
            )
            plan_ms = (time.perf_counter() - plan_started) * 1000.0
            pre_issue_action = decision.action
            pre_issue_mask = decision.mask
            issue_path_started = time.perf_counter()
            alignment_frame = int(state["enemy_manager_frame"])
            fresh_enemy_issue = recertify_fresh_enemy_prefix(
                proposal=local_proposal,
                reader=reader,
                memory=enemy_body_memory,
                alignment_frame=alignment_frame,
                planned_prefix_snapshot=enemy_prefix_snapshot,
                planned_prefix_bodies=enemy_prefix_bodies,
                enemy_bodies=enemy_bodies,
                commit=lambda proposal, fresh_enemy_bodies: (
                    commit_local_proposal_for_fresh_hazards(
                        proposal,
                        player_x=player_control_root.x,
                        player_y=player_control_root.y,
                        previous_mask=previous_mask,
                        delay_frames=delay_estimate.support,
                        action_hold_frames=action_hold_frames,
                        bullets=bullets,
                        lasers=lasers,
                        enemy_bodies=fresh_enemy_bodies,
                        snapshot_lag=player_to_hazard_lag,
                        pipeline_root=observed_local_pipeline_root,
                        allowed_first_actions=(
                            actionable_policy_guidance.allowed_first_actions
                        ),
                        allowed_action_authority=(
                            allowed_action_authority
                        ),
                        viability_repair_volumes=(
                            actionable_policy_guidance.repair_volumes
                        ),
                        viability_recovery_distances=(
                            actionable_policy_guidance.recovery_distances
                        ),
                        viability_safety_actions=(
                            actionable_policy_guidance.safety_actions
                        ),
                        viability_survival_actions=(
                            actionable_policy_guidance.survival_actions
                        ),
                        preferred_action=(
                            kill_before_saturation_preferred_action
                        ),
                        preference_reason=(
                            (
                                "kill_before_saturation_"
                                f"{kill_before_saturation_preference.reason}"
                            )
                            if (
                                kill_before_saturation_preferred_action
                                is not None
                                and kill_before_saturation_preference
                                is not None
                            )
                            else None
                        ),
                        time_scale_schedule=(
                            captured_iteration.time_scale_schedule
                        ),
                    )
                ),
                read_started=issue_path_started,
                dependencies=FreshEnemyIssueDependencies(
                    capture_prefix=capture_enemy_pool_prefix_contiguous,
                    detect_changes=issue_enemy_snapshot_changes,
                    merge_prefix=merge_enemy_pool_prefix,
                    monotonic=time.perf_counter,
                ),
            )
            issue_enemy_prefix_snapshot = fresh_enemy_issue.prefix_snapshot
            issue_enemy_prefix_bodies = fresh_enemy_issue.prefix_bodies
            issue_dormant_enemy_body_pointers = (
                fresh_enemy_issue.dormant_pointers
            )
            issue_enemy_changes = fresh_enemy_issue.changes
            issue_enemy_read_ms = fresh_enemy_issue.read_ms
            issue_enemy_recertificate_ms = (
                fresh_enemy_issue.recertification_ms
            )
            issue_enemy_bodies_for_shadow = (
                fresh_enemy_issue.enemy_bodies_for_shadow
            )
            issue_exact_contact_enemy_bodies = tuple(
                body
                for body in issue_enemy_bodies_for_shadow
                if enemy_body_contact_enabled(body)
            )
            decision = fresh_enemy_issue.decision
            plan_ms += issue_enemy_recertificate_ms
            post_issue_guard_action = decision.action
            post_issue_guard_mask = decision.mask
            if (
                allowed_action_authority
                == ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                and issue_enemy_changes
            ):
                unusable_fresh_enemy_snapshot = any(
                    change in {"unstable_capture", "frame_reversed"}
                    for change in issue_enemy_changes
                )
                if unusable_fresh_enemy_snapshot:
                    ordinary_causal_delayed_certificates = {
                        issue_delay: {}
                        for issue_delay in (
                            ordinary_causal_delayed_issue_support
                        )
                    }
                    ordinary_causal_delayed_fresh_enemy_reason = (
                        "fresh_enemy_snapshot_unstable_fail_closed"
                    )
                else:
                    fresh_body_started = time.perf_counter()
                    try:
                        delayed_action_names = set(
                            ordinary_causal_delayed_evaluated_actions
                        )
                        delayed_action_objects = tuple(
                            action
                            for action in _PLANNER_ACTIONS
                            if action.name in delayed_action_names
                        )
                        ordinary_causal_delayed_certificates = (
                            _recertify_delayed_issue_rows_for_fresh_enemy_bodies(
                                certificates_by_issue_delay=(
                                    ordinary_causal_delayed_certificates
                                ),
                                root=observed_local_pipeline_root,
                                actions=delayed_action_objects,
                                issue_delay_frames=(
                                    ordinary_causal_delayed_issue_support
                                ),
                                pickup_delay_frames=(
                                    ordinary_causal_delayed_pickup_support
                                ),
                                horizon_frames=(
                                    ordinary_causal_delayed_horizon
                                ),
                                player_x=player_control_root.x,
                                player_y=player_control_root.y,
                                enemy_bodies=issue_exact_contact_enemy_bodies,
                                player_scale_bits=(
                                    captured_iteration.time_scale_schedule
                                    .require_player_horizon(
                                        ordinary_causal_delayed_horizon
                                    )
                                ),
                                laser_scale_bits=(
                                    captured_iteration.time_scale_schedule
                                    .require_laser_horizon(
                                        ordinary_causal_delayed_horizon
                                    )
                                ),
                            )
                        )
                        ordinary_causal_delayed_fresh_enemy_reason = (
                            "fresh_enemy_body_slab_recertified"
                        )
                    except (KeyError, TypeError, ValueError) as error:
                        ordinary_causal_delayed_certificates = {
                            issue_delay: {}
                            for issue_delay in (
                                ordinary_causal_delayed_issue_support
                            )
                        }
                        ordinary_causal_delayed_fresh_enemy_reason = (
                            "fresh_enemy_body_recertification_failed:"
                            f"{type(error).__name__}:{error}"
                        )
                    ordinary_causal_delayed_fresh_enemy_ms = (
                        time.perf_counter() - fresh_body_started
                    ) * 1000.0
                    plan_ms += ordinary_causal_delayed_fresh_enemy_ms
            ordinary_causal_delayed_post_fresh_safe_union = tuple(
                action
                for action in ordinary_causal_delayed_evaluated_actions
                if any(
                    action in row
                    and row[action].worst_collisions == 0
                    and row[action].min_clearance > 0.0
                    for row in ordinary_causal_delayed_certificates.values()
                )
            )
            action_issue_observation = observe_action_issue(
                reader,
                source_frame=int(state["enemy_manager_frame"]),
                capture_frame=counter_after_read,
                delay_support=delay_estimate.support,
            )
            phase_now = action_issue_observation.player_phase
            predeath_now = action_issue_observation.predeath_counter
            ordinary_issue_spell_active = (
                action_issue_observation.spell_active
            )
            ordinary_issue_stage_route_index = (
                action_issue_observation.stage_route_index
            )
            ordinary_issue_context_eligible = bool(
                not ordinary_issue_spell_active
                and ordinary_issue_stage_route_index
                == int(state["stage_route_index"])
            )
            ordinary_issue_phase_eligible = bool(
                phase_now not in (1, 2)
                and ordinary_issue_context_eligible
            )
            counter_at_action = action_issue_observation.issue_frame
            action_alignment = action_issue_observation.alignment
            if action_alignment.crosses_contiguous_epoch(
                maximum_post_capture_advance=(
                    MAX_ACTION_CONTIGUOUS_ADVANCE_FRAMES
                )
            ):
                gaps += 1
                gameplay_epoch += 1
                if finalb_scale_schedule_authority is not None:
                    finalb_scale_schedule_authority.reset()
                if no_scale_writer_schedule_authority is not None:
                    no_scale_writer_schedule_authority.reset()
                safe_mask = previous_mask & SHOT
                issue_controller.dispatch(
                    previous_mask,
                    safe_mask,
                    require_foreground=True,
                )
                previous_mask = safe_mask
                previous_direction = 0
                decision_frame_deltas.clear()
                delay_estimator.reset()
                corridor_solution = None
                corridor_pending_solution = None
                corridor_context = None
                corridor_commitment = CorridorCommitment()
                for memory in enemy_body_memories:
                    memory.clear()
                boss_phase_tracker.reset()
                ecl_instruction_cache.clear()
                if corridor_future is not None:
                    corridor_future.cancel()
                ordinary_continuation_lease = None
                ordinary_future_source_result = None
                if ordinary_future_source_future is not None:
                    ordinary_future_source_future.cancel()
                    ordinary_future_source_future = None
                trace_sink.emit(
                    {
                            "kind": "action_epoch_discontinuity",
                            "frame": counter_at_action,
                            "source_frame": state["enemy_manager_frame"],
                            "capture_frame": counter_after_read,
                            "gameplay_epoch": gameplay_epoch,
                            "action_lag": action_alignment.action_lag,
                            "post_capture_advance": (
                                action_alignment.post_capture_advance
                            ),
                            "maximum_contiguous_advance": (
                                MAX_ACTION_CONTIGUOUS_ADVANCE_FRAMES
                            ),
                            "control_delay_candidates": (
                                delay_estimate.support
                            ),
                            "planned_action": decision.action,
                            "planned_mask": decision.mask,
                            "spell": state["spell"],
                            "released_to_mask": safe_mask,
                    },
                    flush=True,
                )
                continue
            planned_action = decision.action
            planned_mask = decision.mask
            action_deadline_missed = action_alignment.deadline_missed
            ordinary_issue_age = (
                counter_at_action - captured_iteration.snapshot_frame
            )
            ordinary_causal_delayed_effective_at_issue = False
            ordinary_causal_delayed_issue_reason = "authority_not_selected"
            ordinary_causal_delayed_issue_safe_actions: tuple[str, ...] = ()
            ordinary_causal_delayed_issue_action: str | None = None
            ordinary_causal_delayed_issue_certificate: (
                RobustActionCertificate | None
            ) = None
            if (
                allowed_action_authority
                == ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
            ):
                if not ordinary_issue_phase_eligible:
                    ordinary_causal_delayed_issue_reason = (
                        "player_phase_ineligible_at_issue"
                    )
                elif ordinary_causal_delayed_fresh_enemy_reason.startswith(
                    (
                        "fresh_enemy_snapshot_unstable_fail_closed",
                        "fresh_enemy_body_recertification_failed:",
                    )
                ):
                    ordinary_causal_delayed_issue_reason = (
                        ordinary_causal_delayed_fresh_enemy_reason
                    )
                else:
                    (
                        ordinary_causal_delayed_issue_action,
                        ordinary_causal_delayed_issue_certificate,
                        ordinary_causal_delayed_issue_reason,
                    ) = _select_delayed_issue_action(
                        certificates_by_issue_delay=(
                            ordinary_causal_delayed_certificates
                        ),
                        issue_age=ordinary_issue_age,
                        planned_action=planned_action,
                        preferred_action=(
                            kill_before_saturation_preferred_action
                        ),
                    )
                    issue_row = ordinary_causal_delayed_certificates.get(
                        ordinary_issue_age,
                        {},
                    )
                    ordinary_causal_delayed_issue_safe_actions = tuple(
                        action.name
                        for action in _PLANNER_ACTIONS
                        if (
                            action.name in issue_row
                            and issue_row[action.name].worst_collisions == 0
                            and issue_row[action.name].min_clearance > 0.0
                        )
                    )
                    if (
                        ordinary_causal_delayed_issue_action is not None
                        and ordinary_causal_delayed_issue_certificate
                        is not None
                    ):
                        selected_action = next(
                            action
                            for action in _PLANNER_ACTIONS
                            if action.name
                            == ordinary_causal_delayed_issue_action
                        )
                        selected_mask = (
                            SHOT
                            | (
                                FOCUS if selected_action.focused else 0
                            )
                            | selected_action.direction
                        )
                        if selected_mask & BOMB:
                            raise AssertionError(
                                "delayed causal authority emitted Bomb"
                            )
                        transaction = decision.issue_recertification
                        if transaction is None:
                            transaction = IssueRecertification(
                                planned_action=planned_action,
                                global_allowed_actions=(
                                    ordinary_causal_delayed_issue_safe_actions
                                ),
                                global_constraint_applicable=True,
                                fresh_safe_actions=(
                                    ordinary_causal_delayed_issue_safe_actions
                                ),
                                fresh_global_intersection=(
                                    ordinary_causal_delayed_issue_safe_actions
                                ),
                                selected_action=selected_action.name,
                                selection_reason=(
                                    ordinary_causal_delayed_issue_reason
                                ),
                                global_constraint_relaxed=False,
                                planned_certificate=issue_row.get(
                                    planned_action
                                ),
                                selected_certificate=(
                                    ordinary_causal_delayed_issue_certificate
                                ),
                                preferred_action=(
                                    kill_before_saturation_preferred_action
                                ),
                                preference_reason=(
                                    "kill_before_saturation_inside_"
                                    "delayed_causal_viable_set"
                                    if (
                                        kill_before_saturation_preferred_action
                                        is not None
                                    )
                                    else None
                                ),
                                preference_applied=bool(
                                    selected_action.name
                                    == kill_before_saturation_preferred_action
                                ),
                                allowed_action_authority=(
                                    ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                                ),
                            )
                        else:
                            transaction = replace(
                                transaction,
                                global_allowed_actions=(
                                    ordinary_causal_delayed_issue_safe_actions
                                ),
                                global_constraint_applicable=True,
                                fresh_safe_actions=(
                                    ordinary_causal_delayed_issue_safe_actions
                                ),
                                fresh_global_intersection=(
                                    ordinary_causal_delayed_issue_safe_actions
                                ),
                                selected_action=selected_action.name,
                                selection_reason=(
                                    ordinary_causal_delayed_issue_reason
                                ),
                                global_constraint_relaxed=False,
                                planned_certificate=issue_row.get(
                                    planned_action
                                ),
                                selected_certificate=(
                                    ordinary_causal_delayed_issue_certificate
                                ),
                                allowed_action_authority=(
                                    ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                                ),
                            )
                        decision = replace(
                            decision,
                            mask=selected_mask,
                            action=selected_action.name,
                            bomb=False,
                            planned_focus=selected_action.focused,
                            robust_delay_frames=(
                                ordinary_causal_delayed_issue_certificate
                                .delay_frames
                            ),
                            robust_override=bool(
                                decision.robust_override
                                or selected_action.name != planned_action
                            ),
                            robust_collisions=0,
                            robust_min_clearance=(
                                ordinary_causal_delayed_issue_certificate
                                .min_clearance
                            ),
                            robust_cvar_risk=(
                                ordinary_causal_delayed_issue_certificate
                                .cvar_risk
                            ),
                            robust_worst_delay=(
                                ordinary_causal_delayed_issue_certificate
                                .worst_delay
                            ),
                            viability_constrained=True,
                            viability_safe_action_count=len(
                                ordinary_causal_delayed_issue_safe_actions
                            ),
                            viability_constraint_relaxed=False,
                            issue_recertification=transaction,
                        )
                        ordinary_causal_delayed_effective_at_issue = True
            ordinary_continuation_issue_check = ContinuationLeaseCheck(
                valid=False,
                reason="lease_authority_not_selected",
                age_frames=ordinary_issue_age,
                remaining_frames=0,
            )
            ordinary_continuation_issue_geometry_check = (
                ContinuationGeometryCheck(
                    valid=False,
                    reason="lease_authority_not_selected",
                    checked_frame_count=0,
                    checked_body_count=len(
                        issue_enemy_bodies_for_shadow
                    ),
                )
            )
            ordinary_continuation_lease_effective_at_issue = False
            lease_fresh_safe = False
            ordinary_continuation_primary_fallback = False
            ordinary_continuation_held_mask_applied = False
            if (
                ordinary_continuation_lease_active
                and ordinary_continuation_lease is not None
                and (
                    allowed_action_authority
                    == ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY
                    or (
                        allowed_action_authority
                        == ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                        and not ordinary_causal_delayed_effective_at_issue
                    )
                )
            ):
                ordinary_continuation_primary_fallback = bool(
                    allowed_action_authority
                    == ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                )
                # Consume the held complete mask as no-write.  A later
                # auto-confirm SHOT pulse is movement-equivalent and is
                # conditioned at the next capture like any pending command.
                decision = replace(
                    decision,
                    mask=previous_mask,
                    action=ordinary_continuation_lease.action,
                    bomb=False,
                    planned_focus=bool(previous_mask & FOCUS),
                )
                ordinary_continuation_held_mask_applied = True
                allowed_action_authority = (
                    ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY
                )
            if (
                allowed_action_authority
                == ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY
                and ordinary_continuation_lease is not None
            ):
                ordinary_continuation_issue_check = (
                    check_continuation_lease_issue(
                        ordinary_continuation_lease,
                        gameplay_epoch=gameplay_epoch,
                        stage_route_index=ordinary_issue_stage_route_index,
                        spell_active=ordinary_issue_spell_active,
                        player_phase=phase_now,
                        issue_frame=counter_at_action,
                        selected_action=decision.action,
                        selected_mask=decision.mask,
                        minimum_remaining_frames=(
                            ORDINARY_AUTHORITY_MIN_TERMINAL_LEAD
                        ),
                    )
                )
                if ordinary_continuation_issue_check.valid:
                    ordinary_continuation_issue_geometry_check = (
                        check_continuation_enemy_snapshot(
                            ordinary_continuation_lease,
                            snapshot=issue_enemy_prefix_snapshot,
                        )
                    )
                lease_transaction = decision.issue_recertification
                lease_fresh_safe = bool(
                    lease_transaction is not None
                    and not lease_transaction.global_constraint_relaxed
                    and lease_transaction.selected_action
                    in lease_transaction.fresh_global_intersection
                    and lease_transaction.selected_certificate
                    .worst_collisions
                    == 0
                    and lease_transaction.selected_certificate
                    .min_clearance
                    >= 0.0
                )
                if (
                    ordinary_continuation_issue_check.valid
                    and not ordinary_continuation_issue_geometry_check.valid
                ):
                    ordinary_continuation_issue_check = (
                        ContinuationLeaseCheck(
                            valid=False,
                            reason=(
                                "fresh_geometry_not_contained_at_issue:"
                                f"{ordinary_continuation_issue_geometry_check.reason}"
                            ),
                            age_frames=(
                                ordinary_continuation_issue_check.age_frames
                            ),
                            remaining_frames=(
                                ordinary_continuation_issue_check
                                .remaining_frames
                            ),
                            matched_branch_count=(
                                ordinary_continuation_issue_check
                                .matched_branch_count
                            ),
                        )
                    )
                ordinary_continuation_lease_effective_at_issue = (
                    ordinary_continuation_issue_check.valid
                )
            decision = apply_deadline_hold(
                decision,
                deadline_missed=bool(
                    (
                        allowed_action_authority
                        == ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                        and not ordinary_causal_delayed_effective_at_issue
                    )
                    or (
                        allowed_action_authority
                        == ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY
                        and not ordinary_continuation_lease_effective_at_issue
                    )
                    or (
                        action_deadline_missed
                        and not ordinary_causal_delayed_effective_at_issue
                    )
                ),
                previous_mask=previous_mask,
                focus_bit=FOCUS,
                action_name_from_mask=_action_name_from_mask,
            )
            ordinary_issued_action = _action_name_from_mask(decision.mask)
            ordinary_preexhaustion_effective_at_issue = bool(
                allowed_action_authority
                == ORDINARY_PREEXHAUSTION_AUTHORITY
                and ordinary_issue_phase_eligible
                and ordinary_issue_age <= ordinary_prefix_certified_frames
                and ordinary_preexhaustion.allowed_actions is not None
                and ordinary_issued_action
                in ordinary_preexhaustion.allowed_actions
            )
            ordinary_causal_hold_effective_at_issue = bool(
                allowed_action_authority == ORDINARY_CAUSAL_HOLD_AUTHORITY
                and ordinary_issue_phase_eligible
                and ordinary_issue_age <= ordinary_causal_hold_horizon
                and decision.mask == held_desired_mask
            )
            hit_started = phase_now == 2 and previous_action_phase != 2
            hit_contact_observation = None
            if hit_started:
                hit_count += 1
                delay_estimator.register_hit(counter_at_action)
                hit_contact_observation = capture_hit_contact_observation(
                    reader,
                    state["spell"],
                )
                if (
                    args.stop_after_hits
                    and hit_count >= args.stop_after_hits
                    and stop_after_frame is None
                ):
                    stop_after_frame = counter_at_action + args.post_hit_frames
            issue_overrides = apply_post_hit_input_overrides(
                decision,
                no_bomb=args.no_bomb,
                phase_now=phase_now,
                predeath_now=predeath_now,
                bomb_stock=float(resources["bombs"]),
                counter_at_action=counter_at_action,
                last_bomb_counter=last_bomb_counter,
                bomb_bit=BOMB,
                auto_confirm_eligible=_auto_confirm_eligible(
                    player_phase=phase_now,
                    bomb_active=bool(player["bomb_active"]),
                    active_bullets=len(bullets),
                    active_lasers=len(lasers),
                ),
                auto_confirm_apply=auto_confirm.apply,
            )
            decision = issue_overrides.decision
            kill_before_saturation_transaction = (
                decision.issue_recertification
            )
            kill_before_saturation_record = {
                "enabled": kill_before_saturation,
                "observation_reason": (
                    kill_before_saturation_observation.reason
                ),
                "observation_frame": (
                    enemy_prefix_snapshot.frame_after
                ),
                "target": (
                    kill_before_saturation_observation.target.record()
                    if (
                        kill_before_saturation_observation.target
                        is not None
                    )
                    else None
                ),
                "upcoming_spawn": (
                    upcoming_spawn_observation.record()
                    if upcoming_spawn_observation is not None
                    else {
                        "target": None,
                        "reason": upcoming_spawn_skip_reason,
                    }
                ),
                "planned_action": pre_issue_action,
                "preferred_action": (
                    kill_before_saturation_preferred_action
                ),
                "preference": (
                    kill_before_saturation_preference.record()
                    if kill_before_saturation_preference is not None
                    else None
                ),
                "preference_source": (
                    kill_before_saturation_preference_source
                ),
                "preference_applied": bool(
                    kill_before_saturation_transaction is not None
                    and kill_before_saturation_transaction.preference_applied
                ),
                "transaction_selected_action": (
                    kill_before_saturation_transaction.selected_action
                    if kill_before_saturation_transaction is not None
                    else None
                ),
                "issued_action": decision.action,
                "deadline_missed": action_deadline_missed,
                "global_role": (
                    "observed_enemy_objective_preference"
                    if kill_before_saturation
                    else "disabled"
                ),
                "global_action_authority": False,
                "fresh_local_action_authority": False,
                "planned_allowed_action_authority": (
                    allowed_action_authority
                ),
                "issued_allowed_action_authority": (
                    allowed_action_authority
                    if (
                        not action_deadline_missed
                        or ordinary_causal_delayed_effective_at_issue
                    )
                    else None
                ),
            }
            can_deathbomb = issue_overrides.can_deathbomb
            auto_confirm_event = issue_overrides.auto_confirm_event
            last_bomb_counter = issue_overrides.last_bomb_counter
            # Read only after every pre-issue early exit. Commit the observed
            # serial after the decision row is flushed so an exception cannot
            # consume ring evidence without retaining it.
            if enemy_lifecycle_probe is not None:
                enemy_lifecycle_batch = enemy_lifecycle_probe.read_since(
                    enemy_lifecycle_probe_last_serial
                )
            physical_issue = commit_physical_issue(
                PhysicalIssueRequest(
                    capture=captured_iteration,
                    proposal=local_proposal,
                    decision=decision,
                    alignment=action_alignment,
                    previous_mask=previous_mask,
                    direction_mask=UP | DOWN | LEFT | RIGHT,
                    pre_issue_action=pre_issue_action,
                    pre_issue_mask=pre_issue_mask,
                    post_guard_action=post_issue_guard_action,
                    post_guard_mask=post_issue_guard_mask,
                    planned_action=planned_action,
                    planned_mask=planned_mask,
                    fresh_enemy_changed=bool(issue_enemy_changes),
                    recertification_ms=issue_enemy_recertificate_ms,
                    issue_path_started=issue_path_started,
                    iteration_started=iteration_started,
                ),
                issue_controller=issue_controller,
                delay_recorder=delay_estimator,
                publication_serial_sampler=None,
                clock=time.perf_counter,
            )
            fresh_issue_result = physical_issue.issue
            input_dispatch = fresh_issue_result.dispatch
            if (
                ordinary_continuation_lease_effective_at_issue
                and input_dispatch.transitions
            ):
                raise AssertionError(
                    "continuation lease must consume held input as no-write"
                )
            input_ms = input_dispatch.input_ms
            issue_path_ms = fresh_issue_result.issue_path_ms
            observe_to_issue_ms = fresh_issue_result.observe_to_issue_ms
            previous_mask = physical_issue.previous_mask
            previous_direction = physical_issue.previous_direction
            ordinary_continuation_lease_created = False
            ordinary_continuation_lease_renewed = False
            ordinary_continuation_post_issue_reason = "no_lease_change"
            lease_before_post_issue = ordinary_continuation_lease
            if ordinary_causal_delayed_effective_at_issue:
                if (
                    ordinary_causal_delayed_issue_action is not None
                    and ordinary_causal_delayed_issue_certificate is not None
                    and decision.action
                    == ordinary_causal_delayed_issue_action
                    and decision.mask == previous_mask
                    and ordinary_issue_phase_eligible
                    and not hit_started
                    and isinstance(
                        published_future_projection,
                        OrdinaryFutureHazardProjection,
                    )
                    and observed_local_pipeline_root is not None
                ):
                    try:
                        ordinary_continuation_lease = (
                            _build_ordinary_continuation_lease(
                                gameplay_epoch=gameplay_epoch,
                                stage_route_index=int(
                                    state["stage_route_index"]
                                ),
                                action=(
                                    ordinary_causal_delayed_issue_action
                                ),
                                mask=decision.mask,
                                root_frame=(
                                    captured_iteration.snapshot_frame
                                ),
                                issue_frame=counter_at_action,
                                horizon_frames=(
                                    ordinary_causal_delayed_horizon
                                ),
                                projection=published_future_projection,
                                projection_source=(
                                    delayed_projection_source
                                ),
                                pipeline_root=(
                                    observed_local_pipeline_root
                                ),
                                pickup_delay_support=(
                                    ordinary_causal_delayed_pickup_support
                                ),
                                player_x=player_control_root.x,
                                player_y=player_control_root.y,
                                player_scale_bits=(
                                    captured_iteration.time_scale_schedule
                                    .require_player_horizon(
                                        ordinary_causal_delayed_horizon
                                    )
                                ),
                                enemy_bodies=issue_exact_contact_enemy_bodies,
                                certificate=(
                                    ordinary_causal_delayed_issue_certificate
                                ),
                                fresh_geometry_frame=int(
                                    issue_enemy_prefix_snapshot.frame_after
                                ),
                                fresh_geometry_changed=bool(
                                    issue_enemy_changes
                                ),
                            )
                        )
                        ordinary_continuation_lease_created = bool(
                            lease_before_post_issue is None
                        )
                        ordinary_continuation_lease_renewed = bool(
                            lease_before_post_issue is not None
                        )
                        ordinary_continuation_post_issue_reason = (
                            "exact_delayed_predecessor_renewed_lease"
                            if ordinary_continuation_lease_renewed
                            else "exact_delayed_predecessor_created_lease"
                        )
                    except (KeyError, TypeError, ValueError) as error:
                        ordinary_continuation_lease = None
                        ordinary_continuation_lease_revoked_reason = (
                            "lease_construction_failed:"
                            f"{type(error).__name__}:{error}"
                        )
                        ordinary_continuation_post_issue_reason = (
                            ordinary_continuation_lease_revoked_reason
                        )
                else:
                    ordinary_continuation_lease = None
                    ordinary_continuation_lease_revoked_reason = (
                        "delayed_authority_changed_before_physical_commit"
                    )
                    ordinary_continuation_post_issue_reason = (
                        ordinary_continuation_lease_revoked_reason
                    )
            elif lease_before_post_issue is not None:
                retained_issue_check = check_continuation_lease_issue(
                    lease_before_post_issue,
                    gameplay_epoch=gameplay_epoch,
                    stage_route_index=ordinary_issue_stage_route_index,
                    spell_active=ordinary_issue_spell_active,
                    player_phase=phase_now,
                    issue_frame=counter_at_action,
                    selected_action=decision.action,
                    selected_mask=decision.mask,
                    minimum_remaining_frames=(
                        ORDINARY_AUTHORITY_MIN_TERMINAL_LEAD
                    ),
                )
                retained_geometry_check = ContinuationGeometryCheck(
                    valid=False,
                    reason="retained_issue_contract_invalid",
                    checked_frame_count=0,
                    checked_body_count=len(
                        issue_enemy_bodies_for_shadow
                    ),
                )
                if retained_issue_check.valid:
                    retained_geometry_check = (
                        check_continuation_enemy_snapshot(
                            lease_before_post_issue,
                            snapshot=issue_enemy_prefix_snapshot,
                        )
                    )
                    ordinary_continuation_issue_geometry_check = (
                        retained_geometry_check
                    )
                retain_old_lease = bool(
                    retained_issue_check.valid
                    and retained_geometry_check.valid
                    and (
                        ordinary_continuation_lease_effective_at_issue
                        or allowed_action_authority
                        == ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                    )
                )
                if retain_old_lease:
                    ordinary_continuation_lease = lease_before_post_issue
                    ordinary_continuation_post_issue_reason = (
                        "old_exact_lease_retained_without_write"
                    )
                else:
                    ordinary_continuation_lease = None
                    ordinary_continuation_lease_revoked_reason = (
                        ordinary_continuation_issue_check.reason
                        if (
                            allowed_action_authority
                            == ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY
                        )
                        else retained_issue_check.reason
                    )
                    if (
                        retained_issue_check.valid
                        and not retained_geometry_check.valid
                    ):
                        ordinary_continuation_lease_revoked_reason = (
                            "fresh_geometry_not_contained_at_issue:"
                            f"{retained_geometry_check.reason}"
                        )
                    ordinary_continuation_post_issue_reason = (
                        ordinary_continuation_lease_revoked_reason
                    )
                    ordinary_causal_delayed_last_scan = None
            if runtime_ecl_identity_service is not None:
                runtime_ecl_identity_service.observe_if_due(
                    reader,
                    trace_sink,
                    provenance=RuntimeEclPhysicalProvenance(
                        pid=pid,
                        executable_sha256=str(identity["sha256"]),
                        route_id=int(state["route_id"]),
                        difficulty_index=int(
                            state["difficulty_index"]
                        ),
                        stage_route_index=int(
                            state["stage_route_index"]
                        ),
                        gameplay_epoch=gameplay_epoch,
                        decision_frame=counter_at_action,
                        snapshot_frame=int(
                            state["enemy_manager_frame"]
                        ),
                        gameplay_active=bool(
                            state["gameplay_active"]
                        ),
                    ),
                )
            local_pipeline_certificate_shadow: (
                dict[str, object] | None
            ) = None
            if (
                args.local_pipeline_root_shadow_every > 0
                and iterations % args.local_pipeline_root_shadow_every == 0
            ):
                if observed_local_pipeline_root is None:
                    local_pipeline_certificate_shadow = {
                        "role": "post_issue_shadow_no_action_authority",
                        "status": "estimator_inconsistent",
                        "computed_after_input": True,
                        "wall_ms": 0.0,
                    }
                else:
                    local_pipeline_certificate_shadow = (
                        _direct_root_certificate_shadow(
                            root=observed_local_pipeline_root,
                            player_x=player_control_root.x,
                            player_y=player_control_root.y,
                            previous_mask=held_desired_mask,
                            delay_frames=delay_estimate.support,
                            action_hold_frames=action_hold_frames,
                            bullets=bullets,
                            lasers=lasers,
                            enemy_bodies=issue_enemy_bodies_for_shadow,
                            snapshot_lag=player_to_hazard_lag,
                            player_scale_bits=(
                                captured_iteration.time_scale_schedule
                                .require_player_horizon(
                                    action_hold_frames
                                    + max(delay_estimate.support)
                                )
                            ),
                            laser_scale_bits=(
                                captured_iteration.time_scale_schedule
                                .require_laser_horizon(
                                    action_hold_frames
                                    + max(delay_estimate.support)
                                )
                            ),
                            authoritative_certificates=(
                                decision.issue_action_certificates
                            ),
                        )
                    )
                    local_pipeline_certificate_shadow.update(
                        {
                            "source_frame": int(
                                state["enemy_manager_frame"]
                            ),
                            "capture_frame": counter_after_read,
                            "issue_frame": counter_at_action,
                            "post_capture_advance": (
                                action_alignment.post_capture_advance
                            ),
                            "fresh_enemy_prefix_changed": bool(
                                issue_enemy_changes
                            ),
                        }
                    )
            current_phase = int(player["phase"])
            current_bombs = resources["bombs"]
            current_power = resources["power"]
            trace_ms = 0.0
            if (
                trace_enemy_mode_transitions
                or trace_enemy_lifecycle_events
                or iterations % args.log_every == 0
                or decision.bomb
                or current_phase != previous_phase
                or current_bombs != previous_bombs
                or current_power != previous_power
                or corridor_updated
                or hit_started
                or auto_confirm_event is not None
                or action_deadline_missed
                or local_pipeline_certificate_shadow is not None
                or ordinary_continuation_lease_effective_at_issue
                or ordinary_continuation_lease_created
                or ordinary_continuation_lease_renewed
                or ordinary_continuation_lease_revoked_reason is not None
            ):
                record = {
                    "kind": "decision",
                    "frame": counter_at_action,
                    "gameplay_epoch": gameplay_epoch,
                    "snapshot_frame": state["enemy_manager_frame"],
                    "snapshot_lag": snapshot_lag,
                    "action_lag": counter_at_action - int(state["enemy_manager_frame"]),
                }
                if enemy_mode_prefix_capture is not None:
                    record["player_enemy_mode_capture"] = (
                        enemy_mode_prefix_capture.compact_record()
                    )
                sensing_trace_fields = build_sensing_trace_fields(
                    SensingTraceInput(
                        resources=resources,
                        stage_route_index=state["stage_route_index"],
                        spell=state["spell"],
                        boss_phase_snapshot=boss_phase_snapshot,
                        boss_phase_error=boss_phase_error,
                        boss_phase_progress=boss_phase_progress,
                        ecl_vm_snapshot=ecl_vm_snapshot,
                        ecl_lookahead=ecl_lookahead,
                        tagged_velocity_toggles=(
                            tagged_velocity_toggles
                        ),
                        bullets=bullets,
                        ecl_event_frame_offset=ecl_event_frame_offset,
                        ecl_event_frame_uncertainty=(
                            ecl_event_frame_uncertainty
                        ),
                        ecl_lookahead_error=ecl_lookahead_error,
                        lasers=lasers,
                        items=items,
                        enemy_bodies=enemy_bodies,
                        dormant_enemy_body_pointers=(
                            dormant_enemy_body_pointers
                        ),
                        bullet_frame_before=bullet_frame_before,
                        bullet_frame_after=bullet_frame_after,
                        enemy_prefix_snapshot=enemy_prefix_snapshot,
                        enemy_prefix_bodies=enemy_prefix_bodies,
                        bullet_capture_span=bullet_capture_span,
                        hazard_snapshot_age=hazard_snapshot_age,
                        player_to_hazard_lag=player_to_hazard_lag,
                        ecl_frame_before=ecl_frame_before,
                        ecl_frame_after=ecl_frame_after,
                        boss_guard_frame_before=boss_guard_frame_before,
                        boss_guard_frame_after=boss_guard_frame_after,
                        enemy_body_snapshot_frame=(
                            enemy_body_snapshot_frame
                        ),
                        query_frame=counter_after_read,
                        issue_enemy_prefix_snapshot=(
                            issue_enemy_prefix_snapshot
                        ),
                        issue_enemy_prefix_bodies=(
                            issue_enemy_prefix_bodies
                        ),
                        issue_dormant_enemy_body_pointers=(
                            issue_dormant_enemy_body_pointers
                        ),
                        issue_enemy_changes=issue_enemy_changes,
                        issue_enemy_read_ms=issue_enemy_read_ms,
                        issue_enemy_recertificate_ms=(
                            issue_enemy_recertificate_ms
                        ),
                        issue=fresh_issue_result,
                        spell_enemy_body_guard=spell_enemy_body_guard,
                        spell_enemy_body_guard_error=(
                            spell_enemy_body_guard_error
                        ),
                    ),
                    serialize_boss_phase_snapshot=(
                        serialize_boss_phase_snapshot
                    ),
                    serialize_enemy_bodies=_serialized_enemy_bodies,
                    enemy_body_contact_enabled=(
                        enemy_body_contact_enabled
                    ),
                    enemy_pointer_in_scanned_pool=(
                        enemy_pointer_in_scanned_pool
                    ),
                    issue_recertification_record=(
                        _issue_recertification_record
                    ),
                )
                record.update(sensing_trace_fields)
                ordinary_preexhaustion_record = (
                    ordinary_preexhaustion.record()
                )
                ordinary_preexhaustion_record.update(
                    {
                        "terminal_policy_state": (
                            "pending"
                            if (
                                ordinary_authority_solution is not None
                                and ordinary_authority_solution
                                is corridor_pending_solution
                            )
                            else (
                                "active"
                                if ordinary_authority_solution is not None
                                else None
                            )
                        ),
                        "selected_as_allowed_action_authority": (
                            allowed_action_authority
                            == ORDINARY_PREEXHAUSTION_AUTHORITY
                        ),
                        "effective_at_issue": bool(
                            ordinary_preexhaustion_effective_at_issue
                        ),
                        "deadline_missed": action_deadline_missed,
                        "issue_phase_eligible": (
                            ordinary_issue_phase_eligible
                        ),
                        "terminal_candidate_actions": (
                            ordinary_terminal_candidate_actions
                        ),
                        "terminal_probe_actions": (
                            ordinary_terminal_probe_actions
                        ),
                        "terminal_probe_action_limit": (
                            ORDINARY_TERMINAL_PROBE_ACTION_LIMIT
                        ),
                        "prefix_evaluated_actions": (
                            ordinary_prefix_evaluated_actions
                        ),
                        "prefix_action_limit": (
                            ORDINARY_PREFIX_CERTIFICATE_ACTION_LIMIT
                        ),
                    }
                )
                record["ordinary_preexhaustion"] = (
                    ordinary_preexhaustion_record
                )
                record["ordinary_causal_hold"] = {
                    "schema": (
                        "th08-ordinary-causal-hold-remaining-horizon-v2"
                    ),
                    "authority": ORDINARY_CAUSAL_HOLD_AUTHORITY,
                    "reason": ordinary_causal_hold_reason,
                    "action": ordinary_causal_hold_action,
                    "safe": ordinary_causal_hold_safe,
                    "min_clearance": ordinary_causal_hold_min_clearance,
                    "worst_collisions": ordinary_causal_hold_collisions,
                    "pipeline_branch_count": (
                        ordinary_causal_hold_branch_count
                    ),
                    "conditioned_event_count": (
                        ordinary_causal_hold_event_count
                    ),
                    "conditioned_projection_digest": (
                        ordinary_causal_hold_projection_digest
                    ),
                    "certified_horizon_frames": (
                        ordinary_causal_hold_horizon
                    ),
                    "issue_age_frames": ordinary_issue_age,
                    "elapsed_ms": ordinary_causal_hold_ms,
                    "selected_as_allowed_action_authority": (
                        allowed_action_authority
                        == ORDINARY_CAUSAL_HOLD_AUTHORITY
                    ),
                    "effective_at_issue": bool(
                        ordinary_causal_hold_effective_at_issue
                    ),
                    "births_at_or_before_root": (
                        "covered_by_complete_native_bullet_pool"
                    ),
                    "future_observation_merge": (
                        "only_selected_action_hidden_pickup_paths"
                    ),
                }
                record["ordinary_causal_delayed_issue"] = {
                    "schema": (
                        "th08-ordinary-causal-delayed-issue-table-v1"
                    ),
                    "authority": (
                        ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                    ),
                    "reason": ordinary_causal_delayed_reason,
                    "trigger_reason": (
                        ordinary_causal_delayed_trigger_reason
                    ),
                    "scan_due": ordinary_causal_delayed_scan_due,
                    "scan_interval_frames": (
                        ORDINARY_CAUSAL_SCAN_INTERVAL_FRAMES
                    ),
                    "computation_guard": {
                        "passed": (
                            ordinary_causal_delayed_computation_guard_passed
                        ),
                        "reason": (
                            ordinary_causal_delayed_computation_guard_reason
                        ),
                        "lease_active": (
                            ordinary_continuation_lease_active
                        ),
                        "held_action_safe": ordinary_causal_hold_safe,
                        "held_certified_horizon_frames": (
                            ordinary_causal_hold_horizon
                        ),
                        "configured_issue_delay_cap": (
                            ORDINARY_CAUSAL_ISSUE_DELAY_MAX
                        ),
                        "semantics": (
                            "long_scan_is_a_no_write_control_interval"
                        ),
                    },
                    "future_projection_source": delayed_projection_source,
                    "candidate_actions": ordinary_causal_delayed_actions,
                    "local_ranking_action": (
                        ordinary_causal_delayed_ranking_action
                    ),
                    "local_ranking_ms": ordinary_causal_delayed_ranking_ms,
                    "local_ranking_proposal_reused": (
                        ordinary_causal_delayed_ranking_proposal_reused
                    ),
                    "local_ranking_role": (
                        "computation_order_only_no_action_authority"
                    ),
                    "evaluated_actions": (
                        ordinary_causal_delayed_evaluated_actions
                    ),
                    "incremental_stop_observations": tuple(
                        {
                            "action": action,
                            "issue_age_after_action_certificate": issue_age,
                            "safe_at_intermediate_age": safe,
                        }
                        for action, issue_age, safe in (
                            ordinary_causal_delayed_incremental_observations
                        )
                    ),
                    "incremental_stop_observation_role": (
                        "scheduling_only_final_fresh_exact_issue_row_"
                        "remains_authority"
                    ),
                    "safe_action_union": (
                        ordinary_causal_delayed_safe_union
                    ),
                    "issue_delay_support": (
                        ordinary_causal_delayed_issue_support
                    ),
                    "issue_delay_support_policy": (
                        "complete_actionable_horizon_fail_closed_after_"
                        "terminal_issue_age"
                    ),
                    "pickup_delay_support": (
                        ordinary_causal_delayed_pickup_support
                    ),
                    "issue_delay_conditioning_bin_frames": (
                        ORDINARY_CAUSAL_ISSUE_BIN_FRAMES
                    ),
                    "safe_issue_age_ranges": {
                        action: _contiguous_integer_ranges(
                            tuple(
                                issue_delay
                                for issue_delay, row in (
                                    ordinary_causal_delayed_certificates
                                    .items()
                                )
                                if (
                                    action in row
                                    and row[action].worst_collisions == 0
                                    and row[action].min_clearance > 0.0
                                )
                            )
                        )
                        for action in ordinary_causal_delayed_actions
                    },
                    "post_fresh_safe_action_union": (
                        ordinary_causal_delayed_post_fresh_safe_union
                    ),
                    "fresh_enemy_recertification_reason": (
                        ordinary_causal_delayed_fresh_enemy_reason
                    ),
                    "fresh_enemy_recertification_ms": (
                        ordinary_causal_delayed_fresh_enemy_ms
                    ),
                    "conditioned_projections": tuple(
                        {
                            "action_issue_bin": key,
                            "digest": digest,
                            "direct_fire_event_count": event_count,
                        }
                        for key, digest, event_count in (
                            ordinary_causal_delayed_projection_records
                        )
                    ),
                    "certified_horizon_frames": (
                        ordinary_causal_delayed_horizon
                    ),
                    "terminal_continuation": (
                        "constant_selected_action_through_complete_"
                        "future_slab_without_saturated_global_kernel"
                    ),
                    "elapsed_ms": ordinary_causal_delayed_ms,
                    "selected_as_allowed_action_authority": (
                        allowed_action_authority
                        == ORDINARY_CAUSAL_DELAYED_ISSUE_AUTHORITY
                    ),
                    "actual_issue_age_frames": ordinary_issue_age,
                    "actual_issue_safe_actions": (
                        ordinary_causal_delayed_issue_safe_actions
                    ),
                    "actual_issue_selected_action": (
                        ordinary_causal_delayed_issue_action
                    ),
                    "actual_issue_selection_reason": (
                        ordinary_causal_delayed_issue_reason
                    ),
                    "actual_issue_certificate": (
                        _robust_action_certificate_record(
                            ordinary_causal_delayed_issue_certificate
                        )
                        if (
                            ordinary_causal_delayed_issue_certificate
                            is not None
                        )
                        else None
                    ),
                    "fresh_enemy_changed": bool(issue_enemy_changes),
                    "player_phase_eligible": (
                        ordinary_issue_phase_eligible
                    ),
                    "issue_spell_active": ordinary_issue_spell_active,
                    "issue_stage_route_index": (
                        ordinary_issue_stage_route_index
                    ),
                    "issue_context_eligible": (
                        ordinary_issue_context_eligible
                    ),
                    "nominal_deadline_missed": action_deadline_missed,
                    "effective_at_issue": bool(
                        ordinary_causal_delayed_effective_at_issue
                    ),
                    "deadline_bypassed_by_explicit_delay_certificate": bool(
                        ordinary_causal_delayed_effective_at_issue
                        and action_deadline_missed
                    ),
                    "computation_delay_observation": (
                        "issue_frame_minus_snapshot_frame"
                    ),
                    "no_write_semantics": (
                        "held_complete_mask_preserves_old_pending"
                    ),
                    "future_observation_merge": (
                        "hidden_old_pending_and_pickup_merged_per_"
                        "observable_issue_age_bin_before_action_selection"
                    ),
                }
                record["ordinary_terminal_continuation_lease"] = {
                    "schema": (
                        "th08-ordinary-terminal-continuation-lease-v4"
                    ),
                    "authority": (
                        ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY
                    ),
                    "present_at_capture": (
                        ordinary_continuation_lease_present_at_capture
                    ),
                    "capture_lease": (
                        ordinary_continuation_lease_capture_record
                    ),
                    "capture_check": (
                        ordinary_continuation_capture_check.record()
                    ),
                    "capture_geometry_check": (
                        ordinary_continuation_capture_geometry_check.record()
                    ),
                    "renewal_due": ordinary_continuation_renewal_due,
                    "renewal_policy": (
                        "every_compatible_fallback_root_old_exact_lease_"
                        "bridges_computation"
                    ),
                    "selected_as_allowed_action_authority": (
                        allowed_action_authority
                        == ORDINARY_CAUSAL_CONTINUATION_LEASE_AUTHORITY
                    ),
                    "issue_check": ordinary_continuation_issue_check.record(),
                    "issue_geometry_check": (
                        ordinary_continuation_issue_geometry_check.record()
                    ),
                    "effective_at_issue": (
                        ordinary_continuation_lease_effective_at_issue
                    ),
                    "primary_authority_fallback": (
                        ordinary_continuation_primary_fallback
                    ),
                    "held_complete_mask_applied": (
                        ordinary_continuation_held_mask_applied
                    ),
                    "fresh_local_recertification_diagnostic_safe": (
                        lease_fresh_safe
                    ),
                    "physical_no_write": not bool(
                        input_dispatch.transitions
                    ),
                    "physical_movement_write": any(
                        transition.bit != SHOT
                        for transition in input_dispatch.transitions
                    ),
                    "shot_only_physical_write": bool(
                        input_dispatch.transitions
                    ) and all(
                        transition.bit == SHOT
                        for transition in input_dispatch.transitions
                    ),
                    "created": ordinary_continuation_lease_created,
                    "renewed": ordinary_continuation_lease_renewed,
                    "revoked_reason": (
                        ordinary_continuation_lease_revoked_reason
                    ),
                    "post_issue_reason": (
                        ordinary_continuation_post_issue_reason
                    ),
                    "active_after_issue": (
                        ordinary_continuation_lease.record()
                        if ordinary_continuation_lease is not None
                        else None
                    ),
                    "direction_change_rule": (
                        "new_direction_or_focus_requires_new_exact_"
                        "predecessor_shot_only_pulse_is_movement_equivalent"
                    ),
                    "fresh_geometry_rule": (
                        "fresh_contact_enabled_observation_seam_must_be_"
                        "contained_by_old_exact_active_or_future_source_"
                        "trajectories"
                    ),
                }
                record["corridor_delivery"] = {
                    "executor_enabled": corridor_executor is not None,
                    "worker_pending": corridor_future is not None,
                    "pending_publication": (
                        corridor_pending_solution is not None
                    ),
                    "active_publication": corridor_solution is not None,
                    "completed_this_decision": corridor_completed,
                    "submitted_this_decision": corridor_submitted,
                    "submission_due": corridor_submission_due,
                    "submission_authority_required": bool(
                        args.authority_only_corridor
                    ),
                    "submission_authority_available": (
                        corridor_time_scale_hard_authority
                    ),
                    "authority_blocked_submission": bool(
                        args.authority_only_corridor
                        and corridor_submission_due
                        and not corridor_time_scale_hard_authority
                    ),
                    "ordinary_source_ready_for_submission": (
                        ordinary_future_projection is not None
                        if ordinary_submission
                        else None
                    ),
                    "ordinary_source_blocked_submission": bool(
                        ordinary_submission
                        and corridor_submission_due
                        and ordinary_future_projection is None
                    ),
                    "required_scale_horizon": (
                        corridor_required_scale_horizon
                    ),
                    "available_scale_horizon": (
                        captured_iteration.time_scale_schedule
                        .complete_horizon
                    ),
                    "scale_schedule_supported": (
                        corridor_scale_schedule_supported
                    ),
                    "player_projection_authority": (
                        captured_iteration.player_projection_authority
                    ),
                    "action_authority": corridor_action_authority,
                    "allowed_action_authority": (
                        allowed_action_authority
                    ),
                }
                control_trace_fields = build_decision_control_trace_fields(
                    DecisionControlTraceInput(
                        issue=fresh_issue_result,
                        delay_estimate=delay_estimate,
                        control_delay_frames=control_delay_frames,
                        action_hold_frames=action_hold_frames,
                        input_state=control_root_input_state,
                        local_pipeline_root_record=(
                            local_pipeline_root_record
                        ),
                        local_pipeline_certificate_shadow=(
                            local_pipeline_certificate_shadow
                        ),
                        corridor_target=actionable_corridor_target,
                        damage_target_x=damage_target_x,
                        damage_target_half_width=(
                            damage_target_half_width
                        ),
                        damageable=damageable,
                        active_item_count=(
                            len(items) if item_sensor_enabled else None
                        ),
                        item_objectives_enabled=ITEM_OBJECTIVES_ENABLED,
                        corridor_context_changed=(
                            corridor_context_changed
                        ),
                        policy_guidance=actionable_policy_guidance,
                        player=control_root_player,
                        projected_player_x=projected_player_x,
                        projected_player_y=projected_player_y,
                        control_origin_x=control_origin_x,
                        control_origin_y=control_origin_y,
                        phase_at_action=phase_now,
                        predeath_at_action=predeath_now,
                        local_horizon=args.horizon,
                        serialized_enemy_bodies=(
                            _serialized_enemy_bodies(enemy_bodies)
                        ),
                        hit_started=hit_started,
                        hit_count=hit_count,
                        auto_confirm_event=auto_confirm_event,
                        kill_before_saturation=(
                            kill_before_saturation_record
                        ),
                    ),
                    local_certificate_timing_record=(
                        _local_certificate_timing_record
                    ),
                )
                record.update(control_trace_fields)
                if trace_enemy_lifecycle_events:
                    record["enemy_lifecycle_probe"] = {
                        "role": "trace_only_no_action_authority",
                        "installation_status": (
                            enemy_lifecycle_probe_installation["status"]
                        ),
                        "capture": (
                            enemy_lifecycle_batch.compact_record()
                            if enemy_lifecycle_batch is not None
                            else None
                        ),
                        "action_authority": False,
                    }
                timing_trace_fields = build_decision_timing_trace_fields(
                    DecisionTimingTraceInput(
                        observe_ms=observe_ms,
                        read_ms=read_ms,
                        enemy_background_ms=enemy_background_ms,
                        enemy_prefix_capture_ms=(
                            enemy_prefix_capture_ms
                        ),
                        enemy_prefix_merge_ms=enemy_prefix_merge_ms,
                        bullet_pool_read_ms=bullet_pool_read_ms,
                        laser_pool_read_ms=laser_pool_read_ms,
                        item_pool_read_ms=item_pool_read_ms,
                        boss_phase_read_ms=boss_phase_read_ms,
                        spell_enemy_guard_read_ms=(
                            spell_enemy_guard_read_ms
                        ),
                        ecl_lookahead_read_ms=ecl_lookahead_read_ms,
                        hazard_read_bookkeeping_ms=(
                            hazard_read_bookkeeping_ms
                        ),
                        enemy_pool_read_ms=enemy_pool_read_ms,
                        enemy_prefix_read_ms=(
                            enemy_prefix_snapshot.read_ms
                        ),
                        issue_enemy_read_ms=issue_enemy_read_ms,
                        decode_ms=decode_ms,
                        bullet_decode_ms=bullet_decode_ms,
                        bullet_event_attach_ms=bullet_event_attach_ms,
                        laser_decode_ms=laser_decode_ms,
                        item_decode_ms=item_decode_ms,
                        corridor_overhead_ms=corridor_overhead_ms,
                        plan_ms=plan_ms,
                        issue_enemy_recertificate_ms=(
                            issue_enemy_recertificate_ms
                        ),
                        issue_path_ms=issue_path_ms,
                        observe_to_issue_ms=observe_to_issue_ms,
                        decision=decision,
                        local_pipeline_certificate_shadow=(
                            local_pipeline_certificate_shadow
                        ),
                        input_ms=input_ms,
                        before_trace_ms=(
                            time.perf_counter() - iteration_started
                        )
                        * 1000.0,
                        previous_trace_ms=previous_trace_ms,
                        previous_iteration_ms=previous_iteration_ms,
                    )
                )
                timing_trace_fields["timing_ms"][
                    "ordinary_preexhaustion_prefix"
                ] = ordinary_prefix_certificate_ms
                timing_trace_fields["timing_ms"][
                    "ordinary_preexhaustion_terminal_probe"
                ] = ordinary_terminal_probe_ms
                timing_trace_fields["timing_ms"][
                    "ordinary_causal_hold_remaining_horizon"
                ] = ordinary_causal_hold_ms
                timing_trace_fields["timing_ms"][
                    "ordinary_causal_delayed_issue_table"
                ] = ordinary_causal_delayed_ms
                record.update(timing_trace_fields)
                if hit_contact_observation is not None:
                    record["hit_contact_observation"] = (
                        hit_contact_observation
                    )
                corridor_record = build_corridor_trace_record(
                    active_solution=corridor_solution,
                    pending_solution=corridor_pending_solution,
                    issue_frame=counter_at_action,
                    query_frame=counter_after_read,
                    max_age_frames=args.corridor_max_age,
                    viability_query=viability_query,
                    safety_value_query=safety_value_query,
                    policy_lead=corridor_policy_lead,
                    commitment=corridor_commitment,
                    context_key=corridor_context,
                    observed_input_action=observed_input_action,
                    decision=decision,
                    delay_support=delay_estimate.support,
                    guidance=policy_guidance,
                    action_authority=corridor_action_authority,
                    pending_command_estimate=(
                        pending_command_estimate
                    ),
                    target=corridor_target,
                    control_origin_x=control_origin_x,
                    control_origin_y=control_origin_y,
                    action_name_from_mask=_action_name_from_mask,
                    minimum_travel_frames=_minimum_travel_frames,
                )
                if corridor_record is not None:
                    record["corridor"] = corridor_record
                optional_hazard_fields = (
                    build_optional_hazard_trace_fields(
                        trace_radius=args.trace_radius,
                        trace_transform_runtime=(
                            args.trace_transform_runtime
                        ),
                        bullets=bullets,
                        lasers=lasers,
                        items=items,
                        projected_player_x=projected_player_x,
                        projected_player_y=projected_player_y,
                        serialize_bullet_trace=serialize_bullet_trace,
                        serialize_laser_trace=serialize_laser_trace,
                    )
                )
                record.update(optional_hazard_fields)
                trace_ms = trace_sink.emit(
                    record,
                    flush=True,
                    measure=True,
                )
            if (
                enemy_lifecycle_batch is not None
                and enemy_lifecycle_batch.observed_serial is not None
            ):
                enemy_lifecycle_probe_last_serial = (
                    enemy_lifecycle_batch.observed_serial
                )
            if previous_counter is not None:
                decision_delta = counter_at_action - previous_counter
                if 0 < decision_delta < 120:
                    decision_frame_deltas.append(decision_delta)
            action_lag = counter_at_action - int(state["enemy_manager_frame"])
            delay_estimator.record_computation_lag(action_lag)
            previous_trace_ms = trace_ms
            previous_iteration_ms = (
                time.perf_counter() - iteration_started
            ) * 1000.0
            previous_phase = current_phase
            previous_bombs = current_bombs
            previous_power = current_power
            previous_action_phase = phase_now
            previous_counter = counter_at_action
            if (
                stop_after_frame is not None
                and counter_at_action >= stop_after_frame
            ):
                termination_reason = "hit_limit"
                break
        if (
            input_clock_tracker is not None
            and input_clock_tracker.active_episode_id is not None
        ):
            input_clock_sample = capture_input_clock_shadow(reader)
            input_clock_frame = int(
                input_clock_sample.get(
                    "manager_frame_after",
                    previous_counter
                    if previous_counter is not None
                    else state["enemy_manager_frame"],
                )
            )
            input_clock_stage = int(state["stage_route_index"])
            input_clock_observation = _semantic_clock_observation(
                input_clock_sample,
                fallback_frame=input_clock_frame,
                context=(gameplay_epoch, input_clock_stage),
            )
            input_clock_event = input_clock_tracker.censor(
                input_clock_observation,
                reason=f"run_ended:{termination_reason}",
            )
            record_input_clock_sample(
                sample=input_clock_sample,
                observation=input_clock_observation,
                events=(
                    (input_clock_event,)
                    if input_clock_event is not None
                    else ()
                ),
                frame=input_clock_frame,
                stage_route_index=input_clock_stage,
                frozen_seconds=max(
                    0.0,
                    time.perf_counter() - last_frame_progress,
                ),
                repeat_poll_count=input_clock_repeat_polls,
                triggers=("run_ended",),
            )
        _write_run_summary(
            trace_sink,
            last_frame=previous_counter,
            counter_gaps=gaps,
            hit_count=hit_count,
            termination_reason=termination_reason,
        )
        return 0
    except OSError as exc:
        termination_reason = "process_unreadable"
        trace_sink.runtime_error(exc, last_frame=previous_counter)
        _write_run_summary(
            trace_sink,
            last_frame=previous_counter,
            counter_gaps=gaps,
            hit_count=hit_count,
            termination_reason=termination_reason,
        )
        return 0
    except Exception as exc:
        termination_reason = "agent_error"
        trace_sink.runtime_error(exc, last_frame=previous_counter)
        _write_run_summary(
            trace_sink,
            last_frame=previous_counter,
            counter_gaps=gaps,
            hit_count=hit_count,
            termination_reason=termination_reason,
        )
        raise
    finally:
        try:
            session.release_keys()
        finally:
            try:
                if enemy_lifecycle_probe is not None:
                    try:
                        final_batch = enemy_lifecycle_probe.read_since(
                            enemy_lifecycle_probe_last_serial
                        )
                        if final_batch.observed_serial is not None:
                            enemy_lifecycle_probe_last_serial = (
                                final_batch.observed_serial
                            )
                        trace_sink.emit(
                            {
                                "kind": "enemy_lifecycle_probe_final",
                                "phase": "after_key_release",
                                **final_batch.compact_record(),
                            },
                            flush=True,
                        )
                    except Exception as error:
                        trace_sink.emit(
                            {
                                "kind": "enemy_lifecycle_probe_final",
                                "schema": ENEMY_LIFECYCLE_PROBE_SCHEMA,
                                "phase": "after_key_release",
                                "role": (
                                    "trace_only_no_action_authority"
                                ),
                                "status": "read_error",
                                "error": (
                                    f"{type(error).__name__}: {error}"
                                ),
                                "action_authority": False,
                            },
                            flush=True,
                        )
                    try:
                        enemy_lifecycle_probe.close()
                    except EnemyLifecycleProbeUnsafeStateError as error:
                        trace_sink.emit(
                            {
                                "kind": (
                                    "enemy_lifecycle_probe_cleanup_error"
                                ),
                                "schema": ENEMY_LIFECYCLE_PROBE_SCHEMA,
                                "unsafe_target_state": True,
                                "error": (
                                    f"{type(error).__name__}: {error}"
                                ),
                                "action_authority": False,
                            },
                            flush=True,
                        )
                        if verified_image_path is None:
                            raise RuntimeError(
                                "unsafe lifecycle cleanup has no verified "
                                "target identity"
                            ) from error
                        _terminate_unsafe_instrumented_target(
                            api=api,
                            verified_image_path=verified_image_path,
                            trace_sink=trace_sink,
                            phase="cleanup",
                        )
                        raise
                    except Exception as error:
                        trace_sink.emit(
                            {
                                "kind": (
                                    "enemy_lifecycle_probe_cleanup_error"
                                ),
                                "schema": ENEMY_LIFECYCLE_PROBE_SCHEMA,
                                "error": (
                                    f"{type(error).__name__}: {error}"
                                ),
                                "action_authority": False,
                            },
                            flush=True,
                        )
                should_pause = False
                try:
                    should_pause = bool(
                        args.pause_on_exit
                        and gameplay_armed
                        and api.foreground_pid() == pid
                        and reader.u32(0x0164D0B4) & 0x04
                    )
                except OSError:
                    pass
                if should_pause:
                    send_scan_key(api, scan_code=0x01, pressed=True)
                    try:
                        time.sleep(0.06)
                    finally:
                        send_scan_key(api, scan_code=0x01, pressed=False)
                service_resources.close(
                    corridor_future=corridor_future,
                    enemy_future=enemy_future,
                    future_source_future=(
                        ordinary_future_source_future
                    ),
                )
            finally:
                session.close()


def build_parser() -> argparse.ArgumentParser:
    defaults = LiveParserDefaults(
        planner_horizon=PLANNER_HORIZON,
        planner_threat_horizon=PLANNER_THREAT_HORIZON,
        planner_beam_width=PLANNER_BEAM_WIDTH,
        control_delay_frames=CONTROL_DELAY_FRAMES,
        corridor_replan_frames=CORRIDOR_REPLAN_FRAMES,
        corridor_lookahead_frames=CORRIDOR_LOOKAHEAD_FRAMES,
        corridor_max_age_frames=CORRIDOR_MAX_AGE_FRAMES,
        stage_transition_timeout_seconds=STAGE_TRANSITION_TIMEOUT_SECONDS,
        terminal_inactive_grace_seconds=TERMINAL_INACTIVE_GRACE_SECONDS,
    )
    return build_live_parser(defaults, description=__doc__)


if __name__ == "__main__":
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except Exception as exc:
        print(f"error: {exc}")
        raise SystemExit(1)
