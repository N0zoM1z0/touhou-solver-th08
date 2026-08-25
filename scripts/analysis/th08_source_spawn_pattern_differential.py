#!/usr/bin/env python3
"""Differential TH08 direct-fire pattern lowering against matching source.

The oracle below is an independent transcription of
``BulletManager::FUN_0042f5f0``.  It intentionally does not call the solver's
pattern helper.  The report combines a deterministic semantic sweep, the
source-owned Route-2 ECL atlas, and a full 1,536-slot lowering stress.  It is
an offline spawn-pattern gate, not proof of ECL execution or live policy
authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any

from th08_future_birth_envelope import (
    FloatInterval,
    FutureDirectFire,
    _pattern_speed_angle,
    lower_future_direct_fire_sectors,
)


SCHEMA = "th08-source-spawn-pattern-differential-v1"
SOURCE_FUNCTION = "BulletManager::FUN_0042f5f0"
SOURCE_PI_BITS = 0x40490FDB
SOURCE_TWO_PI_BITS = 0x40C90FDB
SEMANTIC_TOLERANCE = 2.0e-6
AUTOMATIC_AIM_MODES = frozenset((0, 2, 4))
DETERMINISTIC_MODES = tuple(range(6))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _float32_from_bits(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]


SOURCE_PI = _float32_from_bits(SOURCE_PI_BITS)
SOURCE_TWO_PI = _float32_from_bits(SOURCE_TWO_PI_BITS)


def _signed_i16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _word(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError(f"unsupported ECL argument word {value!r}")


def _wrapped_angle_error(left: float, right: float) -> float:
    return abs((left - right + math.pi) % (2.0 * math.pi) - math.pi)


def _source_speed(
    *,
    count2: int,
    ring_index: int,
    speed1: float,
    speed2: float,
) -> float:
    """Transcribe the source f32 speed statement with explicit stores."""

    if count2 <= 1:
        return _float32(speed1)
    difference = _float32(speed1 - speed2)
    scaled = _float32(difference * _float32(float(ring_index)))
    fraction = _float32(scaled / _float32(float(count2)))
    return _float32(speed1 - fraction)


def source_pattern_speed_angle(
    *,
    mode: int,
    count1: int,
    count2: int,
    bullet_index: int,
    ring_index: int,
    speed1: float,
    speed2: float,
    angle1: float,
    angle2: float,
    aim_angle: float,
) -> tuple[float, float]:
    """Independent deterministic-mode transcription of FUN_0042f5f0."""

    if mode not in DETERMINISTIC_MODES:
        raise ValueError("source oracle covers deterministic modes 0..5")
    if not 0 <= bullet_index < count1 or not 0 <= ring_index < count2:
        raise ValueError("pattern index is outside descriptor counts")
    speed = _source_speed(
        count2=count2,
        ring_index=ring_index,
        speed1=speed1,
        speed2=speed2,
    )
    angle = _float32(0.0)
    if mode in (0, 1):
        if count1 & 1:
            lateral = _float32(
                _float32(float((bullet_index + 1) // 2)) * angle2
            )
        else:
            whole = _float32(
                _float32(float(bullet_index // 2)) * angle2
            )
            half = _float32(angle2 * _float32(0.5))
            lateral = _float32(whole + half)
        if bullet_index & 1:
            lateral = _float32(-lateral)
        angle = _float32(angle + lateral)
        if mode == 0:
            angle = _float32(angle + aim_angle)
        angle = _float32(angle + angle1)
    elif mode in (2, 3):
        if mode == 2:
            angle = _float32(angle + aim_angle)
        radial = _float32(
            _float32(_float32(float(bullet_index)) * SOURCE_TWO_PI)
            / _float32(float(count1))
        )
        angle = _float32(angle + radial)
        ring = _float32(_float32(float(ring_index)) * angle2)
        angle = _float32(angle + _float32(ring + angle1))
    else:
        if mode == 4:
            angle = _float32(angle + aim_angle)
        half_step = _float32(SOURCE_PI / _float32(float(count1)))
        angle = _float32(angle + half_step)
        radial = _float32(
            _float32(_float32(float(bullet_index)) * SOURCE_TWO_PI)
            / _float32(float(count1))
        )
        angle = _float32(angle + radial)
        angle = _float32(angle + angle1)
    return speed, angle


def _solver_event(
    *,
    mode: int,
    count1: int,
    count2: int,
    speed1: float,
    speed2: float,
    angle1: float,
    angle2: float,
    aim_angle: float,
    original_flags: int,
) -> FutureDirectFire:
    # Pattern generation reads no transform/lifecycle bit.  Mask the atlas
    # flag to the non-program subset so this fixture does not pretend to carry
    # a transform program that belongs to runtime descriptor state.
    fixture_flags = original_flags & 0x0203
    return FutureDirectFire(
        source="source-spawn-pattern-differential",
        activation_frames=(1,),
        bullet_type=2,
        origin_x=FloatInterval.point(0.0),
        origin_y=FloatInterval.point(0.0),
        mode=mode,
        count1=count1,
        count2=count2,
        speed1=FloatInterval.point(speed1),
        speed2=FloatInterval.point(speed2),
        angle1=FloatInterval.point(angle1),
        angle2=FloatInterval.point(angle2),
        aim_angle=FloatInterval.point(aim_angle),
        half_width=2.0,
        half_height=2.0,
        original_flags=fixture_flags,
        transform_program_zero=True,
    )


def _legacy_angle(
    *,
    mode: int,
    count1: int,
    bullet_index: int,
    ring_index: int,
    angle1: float,
    angle2: float,
    aim_angle: float,
    original_flags: int,
) -> float:
    """Retain the pre-fix Python formula for regression accounting."""

    angle = angle1
    if mode in (0, 1):
        if original_flags & 1:
            lateral = ((bullet_index + 1) // 2) * angle2
        else:
            lateral = (bullet_index // 2 + 0.5) * angle2
        if bullet_index & 1:
            lateral *= -1.0
        angle += lateral
        if mode == 0:
            angle += aim_angle
    elif mode in (2, 3):
        angle += bullet_index * (2.0 * math.pi) / count1
        angle += ring_index * angle2
        if mode == 2:
            angle += aim_angle
    elif mode in (4, 5):
        angle += math.pi / count1
        angle += bullet_index * (2.0 * math.pi) / count1
        if mode == 4:
            angle += aim_angle
    return angle


def _compare_sample(
    *,
    mode: int,
    count1: int,
    count2: int,
    bullet_index: int,
    ring_index: int,
    speed1: float,
    speed2: float,
    angle1: float,
    angle2: float,
    aim_angle: float,
    original_flags: int,
) -> dict[str, float | bool]:
    source_speed, source_angle = source_pattern_speed_angle(
        mode=mode,
        count1=count1,
        count2=count2,
        bullet_index=bullet_index,
        ring_index=ring_index,
        speed1=speed1,
        speed2=speed2,
        angle1=angle1,
        angle2=angle2,
        aim_angle=aim_angle,
    )
    event = _solver_event(
        mode=mode,
        count1=count1,
        count2=count2,
        speed1=speed1,
        speed2=speed2,
        angle1=angle1,
        angle2=angle2,
        aim_angle=aim_angle,
        original_flags=original_flags,
    )
    solver_speed, solver_angle = _pattern_speed_angle(
        event,
        bullet_index=bullet_index,
        ring_index=ring_index,
    )
    speed_error = max(
        abs(solver_speed.lower - source_speed),
        abs(solver_speed.upper - source_speed),
    )
    angle_error = max(
        _wrapped_angle_error(solver_angle.lower, source_angle),
        _wrapped_angle_error(solver_angle.upper, source_angle),
    )
    legacy_angle_error = _wrapped_angle_error(
        _legacy_angle(
            mode=mode,
            count1=count1,
            bullet_index=bullet_index,
            ring_index=ring_index,
            angle1=angle1,
            angle2=angle2,
            aim_angle=aim_angle,
            original_flags=original_flags,
        ),
        source_angle,
    )
    return {
        "speed_error": speed_error,
        "angle_error": angle_error,
        "legacy_angle_error": legacy_angle_error,
        "fixed_mismatch": (
            speed_error > SEMANTIC_TOLERANCE
            or angle_error > SEMANTIC_TOLERANCE
        ),
        "legacy_mismatch": legacy_angle_error > SEMANTIC_TOLERANCE,
    }


def synthetic_differential() -> dict[str, object]:
    counts1 = tuple(range(1, 18))
    counts2 = (1, 2, 5, 8)
    flags = (0x000, 0x001, 0x202, 0x203)
    parameters = {
        "speed1": _float32(3.75),
        "speed2": _float32(0.35),
        "angle1": _float32(-0.7),
        "angle2": _float32(0.13),
        "aim_angle": _float32(1.2),
    }
    sample_count = 0
    legacy_mismatch_count = 0
    fixed_mismatch_count = 0
    maximum_speed_error = 0.0
    maximum_angle_error = 0.0
    maximum_legacy_angle_error = 0.0
    first_legacy_witness: dict[str, object] | None = None
    for mode in DETERMINISTIC_MODES:
        for count1 in counts1:
            for count2 in counts2:
                for original_flags in flags:
                    for ring_index in range(count2):
                        for bullet_index in range(count1):
                            result = _compare_sample(
                                mode=mode,
                                count1=count1,
                                count2=count2,
                                bullet_index=bullet_index,
                                ring_index=ring_index,
                                original_flags=original_flags,
                                **parameters,
                            )
                            sample_count += 1
                            fixed_mismatch_count += int(
                                bool(result["fixed_mismatch"])
                            )
                            legacy_mismatch_count += int(
                                bool(result["legacy_mismatch"])
                            )
                            maximum_speed_error = max(
                                maximum_speed_error,
                                float(result["speed_error"]),
                            )
                            maximum_angle_error = max(
                                maximum_angle_error,
                                float(result["angle_error"]),
                            )
                            maximum_legacy_angle_error = max(
                                maximum_legacy_angle_error,
                                float(result["legacy_angle_error"]),
                            )
                            if (
                                first_legacy_witness is None
                                and bool(result["legacy_mismatch"])
                            ):
                                first_legacy_witness = {
                                    "mode": mode,
                                    "count1": count1,
                                    "count2": count2,
                                    "bullet_index": bullet_index,
                                    "ring_index": ring_index,
                                    "original_flags": original_flags,
                                    "legacy_angle_error": result[
                                        "legacy_angle_error"
                                    ],
                                }
    return {
        "modes": list(DETERMINISTIC_MODES),
        "count1_range": [counts1[0], counts1[-1]],
        "count2_values": list(counts2),
        "original_flags": list(flags),
        "sample_count": sample_count,
        "legacy_mismatch_count": legacy_mismatch_count,
        "fixed_mismatch_count": fixed_mismatch_count,
        "semantic_tolerance": SEMANTIC_TOLERANCE,
        "maximum_fixed_speed_absolute_error": maximum_speed_error,
        "maximum_fixed_wrapped_angle_error": maximum_angle_error,
        "maximum_legacy_wrapped_angle_error": maximum_legacy_angle_error,
        "first_legacy_witness": first_legacy_witness,
    }


def _unique_direct_sites(stage: dict[str, Any]) -> list[dict[str, Any]]:
    sites: dict[str, dict[str, Any]] = {}
    for program in stage.get("source_programs", []):
        for site in program.get("direct_emission_sites", []):
            symbolic_id = str(site["symbolic_id"])
            sites.setdefault(symbolic_id, site)
    return [sites[key] for key in sorted(sites)]


def atlas_differential(atlas_path: Path) -> dict[str, object]:
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    stage_rows: list[dict[str, object]] = []
    route_fan_literal = 0
    route_fan_parity = 0
    route_fan_fully_literal = 0
    route_fan_fully_literal_parity = 0
    route_automatic_aim = 0
    sampled_sites = 0
    sampled_bullets = 0
    fixed_mismatch_count = 0
    maximum_speed_error = 0.0
    maximum_angle_error = 0.0
    maximum_witness: dict[str, object] | None = None
    representative_aim = _float32(0.8125)
    for stage in atlas["stages"]:
        sites = _unique_direct_sites(stage)
        fan_sites = [site for site in sites if int(site["opcode"]) in (0x60, 0x61)]
        literal_count_sites = [
            site for site in fan_sites if int(site["parameter_mask"]) & 0x04 == 0
        ]
        parity_sites = [
            site
            for site in literal_count_sites
            if (
                _signed_i16(_word(site["argument_words"][1])) & 1
            )
            != (_word(site["argument_words"][7]) & 1)
        ]
        fully_literal = [
            site for site in fan_sites if int(site["parameter_mask"]) == 0
        ]
        fully_literal_parity = [
            site
            for site in fully_literal
            if (
                _signed_i16(_word(site["argument_words"][1])) & 1
            )
            != (_word(site["argument_words"][7]) & 1)
        ]
        automatic_aim_sites = [
            site
            for site in sites
            if int(site["opcode"]) - 0x60 in AUTOMATIC_AIM_MODES
        ]
        stage_rows.append(
            {
                "key": stage["key"],
                "label": stage["label"],
                "fan_literal_count_sites": len(literal_count_sites),
                "fan_count_flag_parity_disagreement_sites": len(parity_sites),
                "fan_fully_literal_sites": len(fully_literal),
                "fan_fully_literal_parity_disagreement_sites": len(
                    fully_literal_parity
                ),
                "automatic_player_aim_sites": len(automatic_aim_sites),
            }
        )
        route_fan_literal += len(literal_count_sites)
        route_fan_parity += len(parity_sites)
        route_fan_fully_literal += len(fully_literal)
        route_fan_fully_literal_parity += len(fully_literal_parity)
        route_automatic_aim += len(automatic_aim_sites)

        for site in sites:
            mode = int(site["opcode"]) - 0x60
            if mode not in DETERMINISTIC_MODES:
                continue
            if int(site["parameter_mask"]) != 0:
                continue
            words = [_word(value) for value in site["argument_words"]]
            if len(words) != 8:
                raise ValueError(
                    f"direct-fire argument layout drifted at {site['symbolic_id']}"
                )
            count1 = _signed_i16(words[1])
            count2 = _signed_i16(words[2])
            if count1 <= 0 or count2 <= 0:
                continue
            allocation_count = count1 * count2
            if allocation_count > 0x600:
                raise ValueError(
                    f"literal source site exceeds native pool at {site['symbolic_id']}"
                )
            sampled_sites += 1
            parameters = {
                "speed1": _float32_from_bits(words[3]),
                "speed2": _float32_from_bits(words[4]),
                "angle1": _float32_from_bits(words[5]),
                "angle2": _float32_from_bits(words[6]),
                "aim_angle": representative_aim,
                "original_flags": words[7],
            }
            for ring_index in range(count2):
                for bullet_index in range(count1):
                    result = _compare_sample(
                        mode=mode,
                        count1=count1,
                        count2=count2,
                        bullet_index=bullet_index,
                        ring_index=ring_index,
                        **parameters,
                    )
                    sampled_bullets += 1
                    fixed_mismatch_count += int(bool(result["fixed_mismatch"]))
                    speed_error = float(result["speed_error"])
                    angle_error = float(result["angle_error"])
                    if max(speed_error, angle_error) > max(
                        maximum_speed_error, maximum_angle_error
                    ):
                        maximum_witness = {
                            "stage": stage["key"],
                            "symbolic_id": site["symbolic_id"],
                            "mode": mode,
                            "count1": count1,
                            "count2": count2,
                            "bullet_index": bullet_index,
                            "ring_index": ring_index,
                            "speed_error": speed_error,
                            "angle_error": angle_error,
                        }
                    maximum_speed_error = max(maximum_speed_error, speed_error)
                    maximum_angle_error = max(maximum_angle_error, angle_error)
    return {
        "path": str(atlas_path),
        "sha256": _sha256(atlas_path),
        "schema": atlas.get("schema"),
        "source_owned_site_deduplication": "symbolic_id",
        "stages": stage_rows,
        "route": {
            "fan_literal_count_sites": route_fan_literal,
            "fan_count_flag_parity_disagreement_sites": route_fan_parity,
            "fan_fully_literal_sites": route_fan_fully_literal,
            "fan_fully_literal_parity_disagreement_sites": (
                route_fan_fully_literal_parity
            ),
            "automatic_player_aim_sites": route_automatic_aim,
            "fully_literal_deterministic_sites_sampled": sampled_sites,
            "fully_literal_spawn_samples": sampled_bullets,
            "fixed_mismatch_count": fixed_mismatch_count,
            "maximum_fixed_speed_absolute_error": maximum_speed_error,
            "maximum_fixed_wrapped_angle_error": maximum_angle_error,
            "maximum_numeric_witness": maximum_witness,
            "representative_automatic_aim_angle": representative_aim,
        },
    }


def density_stress(*, horizon_frames: int) -> dict[str, object]:
    event = _solver_event(
        mode=0,
        count1=384,
        count2=4,
        speed1=_float32(4.0),
        speed2=_float32(0.5),
        angle1=_float32(-0.4),
        angle2=_float32(0.01),
        aim_angle=_float32(0.9),
        original_flags=0x001,
    )
    envelopes = lower_future_direct_fire_sectors(
        event,
        horizon_frames=horizon_frames,
    )
    pattern_indices = {envelope.pattern_index for envelope in envelopes}
    active_samples = 0
    finite = True
    for envelope in envelopes:
        trajectory = envelope.trajectory
        finite = finite and all(
            math.isfinite(value)
            for value in (
                trajectory.origin_x,
                trajectory.origin_y,
                trajectory.minimum_angle,
                trajectory.maximum_angle,
                trajectory.half_extent_radius,
                trajectory.origin_uncertainty,
            )
        )
        for frame in range(horizon_frames + 1):
            sample = trajectory.radial_sample(frame)
            if sample is None:
                continue
            active_samples += 1
            finite = finite and all(math.isfinite(value) for value in sample)
    return {
        "count1": event.count1,
        "count2": event.count2,
        "native_pool_capacity": 0x600,
        "requested_birth_count": event.count1 * event.count2,
        "lowered_envelope_count": len(envelopes),
        "unique_pattern_index_count": len(pattern_indices),
        "horizon_frames": horizon_frames,
        "active_radial_sample_count": active_samples,
        "all_values_finite": finite,
    }


def build_report(
    *,
    atlas_path: Path,
    stress_horizon_frames: int,
) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": SCHEMA,
        "source_authority": {
            "function": SOURCE_FUNCTION,
            "source_path": "../th08/src/BulletManager.cpp",
            "matching_ledger": "../th08/config/matches.csv",
            "source_pi_bits": f"0x{SOURCE_PI_BITS:08x}",
            "source_two_pi_bits": f"0x{SOURCE_TWO_PI_BITS:08x}",
            "fan_centering_operand": "descriptor.count1 & 1",
            "automatic_player_aim_modes": sorted(AUTOMATIC_AIM_MODES),
        },
        "synthetic_differential": synthetic_differential(),
        "route2_source_atlas": atlas_differential(atlas_path.resolve()),
        "pool_density_stress": density_stress(
            horizon_frames=stress_horizon_frames
        ),
        "authority": {
            "accepted_for": (
                "deterministic direct-fire modes 0..5, fan count parity, "
                "automatic mode-aim presence, source pi constants, decoded "
                "source-owned site inventory, and 1536-birth finite lowering"
            ),
            "not_accepted_for": (
                "runtime ECL reachability, rank adjustment, RNG modes 6..8, "
                "pool allocation order after saturation, transforms, ANM "
                "lifecycle, executable x87 excess precision, or live action "
                "authority"
            ),
        },
    }
    digest_payload = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    report["report_digest"] = hashlib.sha256(digest_payload).hexdigest()
    return report


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--atlas",
        type=Path,
        default=(
            repository_root
            / "artifacts/runtime_reports/"
            "th08_source_emission_program_atlas_20260731.json"
        ),
    )
    parser.add_argument("--stress-horizon-frames", type=int, default=80)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.stress_horizon_frames < 1:
        raise ValueError("stress horizon must be positive")
    report = build_report(
        atlas_path=args.atlas,
        stress_horizon_frames=args.stress_horizon_frames,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
