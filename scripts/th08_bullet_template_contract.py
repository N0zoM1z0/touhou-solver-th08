"""Source- and asset-authoritative TH08 bullet-template contract.

The native manager initializes exactly 21 template rows from
``g_BulletSpriteScripts``.  Geometry is selected from each normal ANM script's
time-zero sprite and the generic size/script classes in
``BulletManager::AddedCallback``.  Lifecycle completion ages are the first
reachable ANM delete times of the corresponding template scripts.

This module is deliberately data-driven by bullet type.  It contains no
stage, route, or spell dispatch.  The pinned values can be regenerated and
checked against the exact shipped ``etama.anm`` bytes with
``verify_decoded_etama``.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass


BULLET_TEMPLATE_CONTRACT_SCHEMA = "th08-bullet-template-contract-v1"
SOURCE_AUTHORITY_COMMIT = "57ee34f45eb36a0eb1ad47bea8165274da8ee34f"
SOURCE_SPAWN_ADDRESS = 0x0042F5F0
SOURCE_TEMPLATE_INITIALIZER_ADDRESS = 0x00433070
ETAMA_DECODED_SHA256 = (
    "c3d19370bcbbc2f9b320f437ab5493834c9a6cd2b7bb9f866a4ed4df1d59f3de"
)
ETAMA_DECODED_SIZE = 613_780
BULLET_TEMPLATE_COUNT = 21
BULLET_MANAGER_BASE = 0x00F54E90
BULLET_TEMPLATE_STRIDE = 0x0D44
BULLET_TEMPLATE_GEOMETRY_SCHEMA = "th08-bullet-template-geometry-v1"


class BulletTemplateContractError(ValueError):
    """The decoded asset or an observed template prefix violates the contract."""


@dataclass(frozen=True)
class BulletTemplateProfile:
    """One generic manager template selected by a direct-fire bullet type."""

    bullet_type: int
    normal_script: int
    state2_script: int
    state3_script: int
    state4_script: int
    despawn_script: int
    half_width: float
    half_height: float
    state2_terminal_age: int
    state3_terminal_age: int
    state4_terminal_age: int
    despawn_terminal_age: int

    def to_payload(self) -> dict[str, object]:
        return {
            "bullet_type": self.bullet_type,
            "scripts": {
                "normal": self.normal_script,
                "state2": self.state2_script,
                "state3": self.state3_script,
                "state4": self.state4_script,
                "despawn": self.despawn_script,
            },
            "half_width": self.half_width,
            "half_height": self.half_height,
            "terminal_ages": {
                "state2": self.state2_terminal_age,
                "state3": self.state3_terminal_age,
                "state4": self.state4_terminal_age,
                "despawn": self.despawn_terminal_age,
            },
        }


# BulletManager.cpp:g_BulletSpriteScripts[21] at the pinned source commit.
_SOURCE_SCRIPT_ROWS = (
    (0, 18, 19, 20, 15),
    (1, 21, 22, 23, 16),
    (2, 21, 22, 23, 16),
    (3, 21, 22, 23, 16),
    (4, 21, 22, 23, 16),
    (5, 21, 22, 23, 16),
    (6, 21, 22, 23, 16),
    (7, 24, 24, 24, 17),
    (8, 24, 24, 24, 17),
    (9, 24, 24, 24, 17),
    (25, 27, 27, 27, 26),
    (106, 21, 22, 23, 16),
    (107, 21, 22, 23, 16),
    (108, 21, 22, 23, 16),
    (109, 24, 24, 24, 17),
    (110, 24, 24, 24, 17),
    (111, 21, 22, 23, 16),
    (112, 21, 22, 23, 16),
    (113, 24, 24, 24, 17),
    (114, 24, 24, 24, 17),
    (115, 24, 24, 24, 17),
)

# Pinned results of the AddedCallback collision-size rules applied to the
# time-zero normal sprites in the exact decoded etama.anm.  Values are live
# AABB half-extents, not sprite dimensions.
_NORMAL_SCRIPT_HALF_EXTENT = {
    0: 2.0,
    1: 3.0,
    2: 2.0,
    3: 3.0,
    4: 2.0,
    5: 2.0,
    6: 2.0,
    7: 5.0,
    8: 2.5,
    9: 4.0,
    25: 12.0,
    106: 2.0,
    107: 2.0,
    108: 2.0,
    109: 4.0,
    110: 4.0,
    111: 2.0,
    112: 2.0,
    113: 2.5,
    114: 2.5,
    115: 2.5,
}

# First reachable AnmOpcode_Delete time in the exact lifecycle scripts.
_LIFECYCLE_TERMINAL_AGE = {
    15: 12,
    16: 12,
    17: 12,
    18: 10,
    19: 15,
    20: 30,
    21: 10,
    22: 15,
    23: 30,
    24: 30,
    26: 16,
    27: 24,
}

# Source switch classes inside AddedCallback.  These are ANM script classes,
# not card-specific policy.
_SMALL_SPRITE_FOUR_PIXEL_SCRIPTS = frozenset(
    (2, 4, 5, 6, 106, 107, 108, 111, 112)
)
_MEDIUM_SPRITE_FIVE_PIXEL_SCRIPTS = frozenset((8, 113, 114, 115))
_MEDIUM_SPRITE_EIGHT_PIXEL_SCRIPTS = frozenset((9, 109, 110))


def _profile_from_pins(
    bullet_type: int,
    scripts: tuple[int, int, int, int, int],
) -> BulletTemplateProfile:
    normal, state2, state3, state4, despawn = scripts
    half_extent = _NORMAL_SCRIPT_HALF_EXTENT[normal]
    return BulletTemplateProfile(
        bullet_type=bullet_type,
        normal_script=normal,
        state2_script=state2,
        state3_script=state3,
        state4_script=state4,
        despawn_script=despawn,
        half_width=half_extent,
        half_height=half_extent,
        state2_terminal_age=_LIFECYCLE_TERMINAL_AGE[state2],
        state3_terminal_age=_LIFECYCLE_TERMINAL_AGE[state3],
        state4_terminal_age=_LIFECYCLE_TERMINAL_AGE[state4],
        despawn_terminal_age=_LIFECYCLE_TERMINAL_AGE[despawn],
    )


BULLET_TEMPLATE_PROFILES = tuple(
    _profile_from_pins(bullet_type, scripts)
    for bullet_type, scripts in enumerate(_SOURCE_SCRIPT_ROWS)
)
_PROFILE_BY_TYPE = {
    profile.bullet_type: profile for profile in BULLET_TEMPLATE_PROFILES
}


def bullet_template_profile(bullet_type: int) -> BulletTemplateProfile:
    """Return the source-initialized template row or fail outside 0..20."""

    try:
        return _PROFILE_BY_TYPE[int(bullet_type)]
    except (KeyError, TypeError, ValueError) as error:
        raise BulletTemplateContractError(
            f"bullet type {bullet_type!r} is outside the initialized template table"
        ) from error


def _checked_slice(data: bytes, offset: int, size: int, *, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise BulletTemplateContractError(f"{label} escapes decoded etama.anm")


def _parse_anm_tables(
    data: bytes,
) -> tuple[tuple[tuple[float, float], ...], tuple[int, ...]]:
    """Return global sprite dimensions and script offsets in native load order."""

    sprites: list[tuple[float, float]] = []
    script_offsets: list[int] = []
    entry_base = 0
    entry_count = 0
    while True:
        _checked_slice(data, entry_base, 0x40, label="ANM entry header")
        num_sprites, num_scripts = struct.unpack_from("<ii", data, entry_base)
        version = struct.unpack_from("<I", data, entry_base + 0x28)[0]
        next_offset = struct.unpack_from("<I", data, entry_base + 0x38)[0]
        if version != 3:
            raise BulletTemplateContractError(
                f"ANM entry {entry_count} has unsupported version {version}"
            )
        if not 0 <= num_sprites <= 4096 or not 0 <= num_scripts <= 4096:
            raise BulletTemplateContractError("ANM sprite/script count is invalid")
        table = entry_base + 0x40
        table_size = num_sprites * 4 + num_scripts * 8
        _checked_slice(data, table, table_size, label="ANM offset table")
        for index in range(num_sprites):
            relative = struct.unpack_from("<I", data, table + index * 4)[0]
            sprite_offset = entry_base + relative
            _checked_slice(data, sprite_offset, 20, label="ANM sprite")
            _sprite_id, _x, _y, width, height = struct.unpack_from(
                "<Iffff", data, sprite_offset
            )
            if (
                not math.isfinite(width)
                or not math.isfinite(height)
                or width <= 0.0
                or height <= 0.0
            ):
                raise BulletTemplateContractError(
                    "ANM sprite has non-positive or nonfinite dimensions"
                )
            sprites.append((width, height))
        script_table = table + num_sprites * 4
        for index in range(num_scripts):
            _script_id, relative = struct.unpack_from(
                "<II", data, script_table + index * 8
            )
            offset = entry_base + relative
            _checked_slice(data, offset, 8, label="ANM script")
            script_offsets.append(offset)
        entry_count += 1
        if next_offset == 0:
            break
        if next_offset < 0x40:
            raise BulletTemplateContractError("ANM next-entry offset is invalid")
        entry_base += next_offset
        if entry_count > 256:
            raise BulletTemplateContractError("ANM entry chain does not terminate")
    return tuple(sprites), tuple(script_offsets)


def _script_first_sprite(data: bytes, offset: int) -> int:
    for _instruction_index in range(4096):
        _checked_slice(data, offset, 8, label="ANM instruction")
        opcode, size, time, variable_mask = struct.unpack_from(
            "<hHhH", data, offset
        )
        if opcode == 3 and time == 0:
            if size < 12 or variable_mask & 0x01:
                raise BulletTemplateContractError(
                    "normal ANM sprite operand is not an immediate integer"
                )
            return struct.unpack_from("<i", data, offset + 8)[0]
        if opcode in (-1, 1, 2) or time > 0:
            break
        if size < 8:
            raise BulletTemplateContractError("ANM instruction size is invalid")
        offset += size
    raise BulletTemplateContractError(
        "normal ANM script has no reachable time-zero sprite"
    )


def _script_terminal_age(data: bytes, offset: int) -> int:
    for _instruction_index in range(4096):
        _checked_slice(data, offset, 8, label="ANM lifecycle instruction")
        opcode, size, time, _variable_mask = struct.unpack_from(
            "<hHhH", data, offset
        )
        if opcode == 1:
            if time < 0:
                raise BulletTemplateContractError(
                    "ANM lifecycle delete time is negative"
                )
            return time
        if opcode in (-1, 2):
            raise BulletTemplateContractError(
                "ANM lifecycle terminates without a delete instruction"
            )
        if opcode in (4, 5):
            raise BulletTemplateContractError(
                "ANM lifecycle control flow requires separate lowering"
            )
        if size < 8:
            raise BulletTemplateContractError("ANM instruction size is invalid")
        offset += size
    raise BulletTemplateContractError("ANM lifecycle script does not terminate")


def _source_collision_half_extent(normal_script: int, height: float) -> float:
    """Apply the exact generic size/script classes in AddedCallback."""

    if height <= 8.0:
        full_extent = 4.0
    elif height <= 16.0:
        full_extent = (
            4.0
            if normal_script in _SMALL_SPRITE_FOUR_PIXEL_SCRIPTS
            else 6.0
        )
    elif height <= 32.0:
        if normal_script in _MEDIUM_SPRITE_FIVE_PIXEL_SCRIPTS:
            full_extent = 5.0
        elif normal_script in _MEDIUM_SPRITE_EIGHT_PIXEL_SCRIPTS:
            full_extent = 8.0
        else:
            full_extent = 10.0
    else:
        full_extent = 24.0
    return full_extent * 0.5


def derive_decoded_etama_profiles(data: bytes) -> tuple[BulletTemplateProfile, ...]:
    """Derive all 21 profiles from exact decoded ANM bytes and source tables."""

    digest = hashlib.sha256(data).hexdigest()
    if len(data) != ETAMA_DECODED_SIZE or digest != ETAMA_DECODED_SHA256:
        raise BulletTemplateContractError(
            "decoded etama.anm identity mismatch: "
            f"expected={ETAMA_DECODED_SHA256}/{ETAMA_DECODED_SIZE},"
            f"actual={digest}/{len(data)}"
        )
    sprites, script_offsets = _parse_anm_tables(data)
    required_scripts = {
        script for row in _SOURCE_SCRIPT_ROWS for script in row
    }
    if max(required_scripts) >= len(script_offsets):
        raise BulletTemplateContractError(
            "decoded etama.anm lacks a source-selected script"
        )
    terminal_ages = {
        script: _script_terminal_age(data, script_offsets[script])
        for script in required_scripts
        if script not in _NORMAL_SCRIPT_HALF_EXTENT
    }
    profiles: list[BulletTemplateProfile] = []
    for bullet_type, scripts in enumerate(_SOURCE_SCRIPT_ROWS):
        normal, state2, state3, state4, despawn = scripts
        sprite_index = _script_first_sprite(data, script_offsets[normal])
        if not 0 <= sprite_index < len(sprites):
            raise BulletTemplateContractError(
                f"normal script {normal} selects an absent sprite"
            )
        _sprite_width, sprite_height = sprites[sprite_index]
        half_extent = _source_collision_half_extent(normal, sprite_height)
        profiles.append(
            BulletTemplateProfile(
                bullet_type=bullet_type,
                normal_script=normal,
                state2_script=state2,
                state3_script=state3,
                state4_script=state4,
                despawn_script=despawn,
                half_width=half_extent,
                half_height=half_extent,
                state2_terminal_age=terminal_ages[state2],
                state3_terminal_age=terminal_ages[state3],
                state4_terminal_age=terminal_ages[state4],
                despawn_terminal_age=terminal_ages[despawn],
            )
        )
    return tuple(profiles)


def verify_decoded_etama(data: bytes) -> tuple[BulletTemplateProfile, ...]:
    """Fail if regenerated profiles differ from the pinned runtime contract."""

    derived = derive_decoded_etama_profiles(data)
    if derived != BULLET_TEMPLATE_PROFILES:
        raise BulletTemplateContractError(
            "decoded etama.anm profiles disagree with the pinned contract"
        )
    return derived


def pinned_contract_payload() -> dict[str, object]:
    """Return a compact canonical-JSON-ready evidence record."""

    return {
        "schema": BULLET_TEMPLATE_CONTRACT_SCHEMA,
        "source_authority": {
            "commit": SOURCE_AUTHORITY_COMMIT,
            "spawn_address": SOURCE_SPAWN_ADDRESS,
            "template_initializer_address": SOURCE_TEMPLATE_INITIALIZER_ADDRESS,
            "template_count": BULLET_TEMPLATE_COUNT,
        },
        "asset_authority": {
            "name": "etama.anm",
            "decoded_sha256": ETAMA_DECODED_SHA256,
            "decoded_size": ETAMA_DECODED_SIZE,
        },
        "profiles": [profile.to_payload() for profile in BULLET_TEMPLATE_PROFILES],
        "role": "offline_source_asset_contract_no_action_authority",
    }


def fallback_geometry_from_observed_prefix(
    geometry: object,
    bullet_type: int,
) -> tuple[float, float] | None:
    """Supplement an old 16-row capture only after exact overlap validation.

    Physical values remain primary.  This fallback is intentionally unavailable
    for sparse synthetic records, duplicate rows, altered metadata, or any
    observed overlap that disagrees with the source+asset contract.
    """

    if not isinstance(geometry, dict):
        return None
    if (
        geometry.get("schema") != BULLET_TEMPLATE_GEOMETRY_SCHEMA
        or geometry.get("manager_base") != BULLET_MANAGER_BASE
        or geometry.get("template_stride") != BULLET_TEMPLATE_STRIDE
    ):
        return None
    rows = geometry.get("rows")
    if not isinstance(rows, list):
        return None
    by_type: dict[int, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("type")) is not int:
            return None
        row_type = int(row["type"])
        if row_type in by_type:
            return None
        by_type[row_type] = row
    if set(range(16)) - set(by_type):
        return None
    for observed_type, row in by_type.items():
        if observed_type not in _PROFILE_BY_TYPE:
            return None
        profile = _PROFILE_BY_TYPE[observed_type]
        expected = {
            "width": profile.half_width * 2.0,
            "height": profile.half_height * 2.0,
            "half_width": profile.half_width,
            "half_height": profile.half_height,
            "collision_z": 0.0,
        }
        try:
            if any(float(row[field]) != value for field, value in expected.items()):
                return None
        except (KeyError, TypeError, ValueError):
            return None
    try:
        profile = bullet_template_profile(bullet_type)
    except BulletTemplateContractError:
        return None
    return profile.half_width, profile.half_height


__all__ = [
    "BULLET_MANAGER_BASE",
    "BULLET_TEMPLATE_CONTRACT_SCHEMA",
    "BULLET_TEMPLATE_COUNT",
    "BULLET_TEMPLATE_GEOMETRY_SCHEMA",
    "BULLET_TEMPLATE_PROFILES",
    "BULLET_TEMPLATE_STRIDE",
    "BulletTemplateContractError",
    "BulletTemplateProfile",
    "ETAMA_DECODED_SHA256",
    "ETAMA_DECODED_SIZE",
    "SOURCE_AUTHORITY_COMMIT",
    "bullet_template_profile",
    "derive_decoded_etama_profiles",
    "fallback_geometry_from_observed_prefix",
    "pinned_contract_payload",
    "verify_decoded_etama",
]
