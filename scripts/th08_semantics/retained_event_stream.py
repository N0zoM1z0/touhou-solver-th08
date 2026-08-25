"""Import coherent retained TH08 producer roots into the resolved stage IR.

This adapter deliberately remains narrower than the source executor.  It
replays a content-addressed root against its exact decoded ECL image and emits
one-shot ``BulletEmitter`` records only when every descriptor operand is a
point value and no reached callback or unresolved transform remains.  A source-
known sound flag and unconsumed callback tags are erased because they have no
geometry effect inside that proven prefix.  Unknown semantics reject the
complete stream; interval midpoints are never used.  The returned
``StageProgram`` covers only the proven causal prefix and does not claim enemy-
body, laser, arbitrary-ECL, or action authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from th08_bullet_template_contract import bullet_template_profile
from th08_ecl_tool.core import parse_ecl
from th08_future_birth_envelope import (
    FloatInterval,
    FutureDirectFire,
    FutureTaggedBulletCallback,
    KNOWN_DIRECT_FIRE_NONPROGRAM_FLAGS,
    KNOWN_TAGGED_CALLBACK_FLAGS,
)
from th08_ordinary_future_sources import (
    OrdinaryFutureSourceClosure,
    project_ordinary_future_sources,
)
from th08_runtime.future_source_retention import (
    read_retained_future_source_root,
)
from th08_semantics.stage import (
    BulletEmitter,
    StagePhase,
    StageProgram,
)


RETAINED_EVENT_STREAM_SCHEMA = "th08-retained-producer-event-stream-v1"
_SPAWN_LIFECYCLE_FLAG_MASK = 0x0E


class RetainedEventStreamError(ValueError):
    """A retained source fact cannot be represented exactly by the stage IR."""


@dataclass(frozen=True)
class RetainedEventStreamImport:
    schema: str
    root_path: Path
    root_sha256: str
    runtime_ecl_sha256: str
    root_frame: int
    requested_horizon_frames: int
    proven_horizon_frames: int
    producer_event_count: int
    emitter_count: int
    full_horizon_complete: bool
    causal_prefix_reason: str | None
    rejection_reason: str | None
    closure: OrdinaryFutureSourceClosure | None
    program: StageProgram | None

    @property
    def accepted_prefix(self) -> bool:
        return self.program is not None

    def compact_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "root_path": str(self.root_path),
            "root_sha256": self.root_sha256,
            "runtime_ecl_sha256": self.runtime_ecl_sha256,
            "root_frame": self.root_frame,
            "requested_horizon_frames": self.requested_horizon_frames,
            "proven_horizon_frames": self.proven_horizon_frames,
            "producer_event_count": self.producer_event_count,
            "emitter_count": self.emitter_count,
            "full_horizon_complete": self.full_horizon_complete,
            "causal_prefix_reason": self.causal_prefix_reason,
            "rejection_reason": self.rejection_reason,
            "accepted_prefix": self.accepted_prefix,
            "program_digest": (
                self.program.digest if self.program is not None else None
            ),
            "role": "offline_resolved_birth_prefix_no_action_authority",
        }


def _point(interval: FloatInterval, *, label: str) -> float:
    if interval.lower != interval.upper:
        raise RetainedEventStreamError(
            f"{label} is not point-valued: "
            f"[{interval.lower!r},{interval.upper!r}]"
        )
    return interval.lower


def _event_emitters(
    event: FutureDirectFire,
    *,
    ordinal: int,
) -> tuple[BulletEmitter, ...]:
    if event.tagged_callbacks:
        raise RetainedEventStreamError(
            "tagged bullet callbacks require separate stage-runtime lowering"
        )
    spawn_flags = event.original_flags & _SPAWN_LIFECYCLE_FLAG_MASK
    # Within a proven prefix, a high callback tag with no reached matching
    # callback is observationally inert.  Likewise 0x200 is sound-only in
    # BulletManager::FUN_00430e10.  Preserve fail-closed behavior for every
    # other flag instead of teaching the stage runtime imaginary semantics.
    remaining_flags = event.original_flags & ~(
        KNOWN_DIRECT_FIRE_NONPROGRAM_FLAGS | KNOWN_TAGGED_CALLBACK_FLAGS
    )
    if remaining_flags:
        raise RetainedEventStreamError(
            "direct-fire flags outside generic spawn lifecycle require "
            f"separate lowering: 0x{remaining_flags:x}"
        )
    if not event.transform_program_zero or any(event.transform_program):
        raise RetainedEventStreamError(
            "direct-fire transform program requires separate lowering"
        )
    origin_x = _point(event.origin_x, label="origin_x")
    origin_y = _point(event.origin_y, label="origin_y")
    speed1 = _point(event.speed1, label="speed1")
    speed2 = _point(event.speed2, label="speed2")
    angle1 = _point(event.angle1, label="angle1")
    angle2 = _point(event.angle2, label="angle2")
    aim_angle = _point(event.aim_angle, label="aim_angle")
    template = bullet_template_profile(event.bullet_type)
    return tuple(
        BulletEmitter(
            emitter_id=(
                f"retained:{ordinal}:{event.source}:activation={frame}"
            ),
            start_frame=frame,
            end_frame=frame,
            interval=1,
            origin_x=origin_x,
            origin_y=origin_y,
            origin_velocity_x=0.0,
            origin_velocity_y=0.0,
            origin_wave_x=0.0,
            origin_wave_y=0.0,
            origin_wave_step=0.0,
            mode=event.mode,
            count1=event.count1,
            count2=event.count2,
            speed1=speed1,
            speed2=speed2,
            angle=angle1,
            angle_step=angle2,
            angle_per_emission=0.0,
            tag_flags=0,
            half_width=event.half_width,
            half_height=event.half_height,
            cull_half_width=template.cull_half_width,
            cull_half_height=template.cull_half_height,
            resolved_aim_override=aim_angle,
            bullet_type=event.bullet_type,
            spawn_flags=spawn_flags,
        )
        for frame in event.activation_frames
    )


def resolved_direct_fire_stage_program(
    events: tuple[FutureDirectFire, ...],
    *,
    tagged_callbacks: tuple[FutureTaggedBulletCallback, ...] = (),
    horizon_frames: int,
    gameplay_rng_seed: int,
    root_sha256: str,
) -> StageProgram:
    """Lower a point-valued causal prefix without stage/spell dispatch."""

    if horizon_frames < 0:
        raise RetainedEventStreamError("event-stream horizon is negative")
    if len(root_sha256) != 64:
        raise RetainedEventStreamError("event-stream root digest is malformed")
    if tagged_callbacks:
        raise RetainedEventStreamError(
            "tagged bullet callbacks require current-pool stage-runtime "
            "composition"
        )
    emitters = tuple(
        emitter
        for ordinal, event in enumerate(events)
        for emitter in _event_emitters(event, ordinal=ordinal)
    )
    if any(emitter.end_frame > horizon_frames for emitter in emitters):
        raise RetainedEventStreamError(
            "direct-fire activation escapes the proven causal prefix"
        )
    return StageProgram(
        seed=int(root_sha256[:16], 16),
        profile=f"retained-producer-prefix:{root_sha256[:16]}",
        frame_count=horizon_frames + 1,
        gameplay_rng_seed=gameplay_rng_seed,
        phases=(
            StagePhase(
                name="retained-producer-prefix",
                start_frame=0,
                end_frame=horizon_frames,
                clear_at_start=False,
                emitters=emitters,
                callbacks=(),
                lasers=(),
            ),
        ),
    )


def _root_rejection_reason(record: dict[str, object]) -> str | None:
    capture = record.get("capture_clock")
    identity = record.get("root_identity")
    payload = record.get("root_payload")
    if not isinstance(capture, dict):
        return "retained capture clock is absent"
    if capture.get("stable") is not True:
        return "retained capture clock is not coherent"
    if not isinstance(identity, dict) or not isinstance(payload, dict):
        return "retained root identity or payload is absent"
    manager_frame = identity.get("manager_frame")
    if type(manager_frame) is not int:
        return "retained root manager frame is malformed"
    clock_fields = (
        "manager_frame_before",
        "manager_frame_after",
        "frscreen_update_serial_before",
        "frscreen_update_serial_after",
    )
    if any(type(capture.get(field)) is not int for field in clock_fields):
        return "retained capture clock field is malformed"
    if (
        capture["manager_frame_before"] != manager_frame
        or capture["manager_frame_after"] != manager_frame
        or capture["frscreen_update_serial_before"]
        != capture["frscreen_update_serial_after"]
    ):
        return "retained capture clock/root identity is incoherent"
    compact = payload.get("compact_state")
    if not isinstance(compact, dict):
        return "retained compact state is absent"
    for field in (
        "manager_frame",
        "route_id",
        "difficulty_index",
        "stage_route_index",
        "spell_id",
    ):
        if compact.get(field) != identity.get(field):
            return f"retained compact/root identity mismatch: {field}"
    if compact.get("player_phase") != 0:
        return (
            "retained planner root requires player phase 0, got "
            f"{compact.get('player_phase')!r}"
        )
    if compact.get("bomb_active") != 0:
        return "retained planner root requires bomb-inactive state"
    return None


def import_retained_future_event_stream(
    root_path: Path,
    ecl_path: Path,
    *,
    horizon_frames: int | None = None,
) -> RetainedEventStreamImport:
    """Integrity-check, source-replay, and lower one retained root prefix."""

    record = read_retained_future_source_root(root_path)
    identity = record["root_identity"]
    projection_at_capture = record["projection_at_capture"]
    assert isinstance(identity, dict)
    assert isinstance(projection_at_capture, dict)
    root_sha256 = root_path.name.split("-", 1)[1].split(".", 1)[0]
    runtime_ecl_sha256 = str(identity["runtime_ecl_canonical_sha256"])
    root_frame = int(identity["manager_frame"])
    requested_horizon = (
        int(projection_at_capture["requested_horizon_frames"])
        if horizon_frames is None
        else int(horizon_frames)
    )
    if requested_horizon < 0:
        raise RetainedEventStreamError("requested retained horizon is negative")

    root_rejection = _root_rejection_reason(record)
    if root_rejection is not None:
        return RetainedEventStreamImport(
            schema=RETAINED_EVENT_STREAM_SCHEMA,
            root_path=root_path,
            root_sha256=root_sha256,
            runtime_ecl_sha256=runtime_ecl_sha256,
            root_frame=root_frame,
            requested_horizon_frames=requested_horizon,
            proven_horizon_frames=0,
            producer_event_count=0,
            emitter_count=0,
            full_horizon_complete=False,
            causal_prefix_reason=None,
            rejection_reason=root_rejection,
            closure=None,
            program=None,
        )

    ecl = parse_ecl(ecl_path)
    if ecl.sha256 != runtime_ecl_sha256:
        raise RetainedEventStreamError(
            "decoded ECL does not match retained runtime identity: "
            f"expected={runtime_ecl_sha256},actual={ecl.sha256}"
        )
    payload = record["root_payload"]
    assert isinstance(payload, dict)
    closure = project_ordinary_future_sources(
        payload,
        ecl,
        horizon_frames=requested_horizon,
    )
    projection = closure.projection
    causal_prefix_reason = closure.causal_prefix_reason
    full_horizon_complete = bool(
        projection.source_closure_complete
        and projection.horizon_frames == requested_horizon
        and causal_prefix_reason is None
    )
    if not projection.source_closure_complete:
        return RetainedEventStreamImport(
            schema=RETAINED_EVENT_STREAM_SCHEMA,
            root_path=root_path,
            root_sha256=root_sha256,
            runtime_ecl_sha256=runtime_ecl_sha256,
            root_frame=root_frame,
            requested_horizon_frames=requested_horizon,
            # An UNKNOWN slab has a requested width, not a proven prefix.
            proven_horizon_frames=0,
            producer_event_count=0,
            emitter_count=0,
            full_horizon_complete=False,
            causal_prefix_reason=None,
            rejection_reason=projection.source_closure_reason,
            closure=closure,
            program=None,
        )
    compact = payload["compact_state"]
    assert isinstance(compact, dict)
    try:
        program = resolved_direct_fire_stage_program(
            closure.direct_fire_events,
            tagged_callbacks=closure.tagged_callbacks,
            horizon_frames=projection.horizon_frames,
            gameplay_rng_seed=int(compact["rng_state"]),
            root_sha256=root_sha256,
        )
    except RetainedEventStreamError as error:
        return RetainedEventStreamImport(
            schema=RETAINED_EVENT_STREAM_SCHEMA,
            root_path=root_path,
            root_sha256=root_sha256,
            runtime_ecl_sha256=runtime_ecl_sha256,
            root_frame=root_frame,
            requested_horizon_frames=requested_horizon,
            proven_horizon_frames=projection.horizon_frames,
            producer_event_count=len(closure.direct_fire_events),
            emitter_count=0,
            full_horizon_complete=False,
            causal_prefix_reason=causal_prefix_reason,
            rejection_reason=str(error),
            closure=closure,
            program=None,
        )
    emitter_count = sum(
        len(event.activation_frames)
        for event in closure.direct_fire_events
    )
    return RetainedEventStreamImport(
        schema=RETAINED_EVENT_STREAM_SCHEMA,
        root_path=root_path,
        root_sha256=root_sha256,
        runtime_ecl_sha256=runtime_ecl_sha256,
        root_frame=root_frame,
        requested_horizon_frames=requested_horizon,
        proven_horizon_frames=projection.horizon_frames,
        producer_event_count=len(closure.direct_fire_events),
        emitter_count=emitter_count,
        full_horizon_complete=full_horizon_complete,
        causal_prefix_reason=causal_prefix_reason,
        rejection_reason=None,
        closure=closure,
        program=program,
    )


__all__ = [
    "RETAINED_EVENT_STREAM_SCHEMA",
    "RetainedEventStreamError",
    "RetainedEventStreamImport",
    "import_retained_future_event_stream",
    "resolved_direct_fire_stage_program",
]
