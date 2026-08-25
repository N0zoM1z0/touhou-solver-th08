#!/usr/bin/env python3
"""Compile a Stage-5 Lunatic spell-producer topology contract.

This is a static topology oracle, not a future-hazard projection.  It pins the
route and stage-scoped Spell Practice ECL images, finds literal spell roots,
closes over literal same-source/child program edges, and compares the two
packages after normalizing subroutine numbers and phase-exit targets.  Runtime
VM state is still required to decide which eligible sites are reached from a
particular observation.  Ordinary Practice Start uses the route image and is
not the meaning of ``*sp.ecl``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from th08_ecl import EclFile, SubInstruction, parse_ecl
from th08_ecl_birth import (
    ECL_OP_DISABLE_DEFERRED_FIRE,
    ECL_OP_EMIT_CURRENT_PATTERN,
    ECL_OP_ENABLE_DEFERRED_FIRE,
    ECL_OP_FIRST_CHILD_SOURCE,
    ECL_OP_FIRST_DIRECT_FIRE,
    ECL_OP_LAST_CHILD_SOURCE,
    ECL_OP_LAST_DIRECT_FIRE,
    ECL_OP_SET_FIRE_DELAY,
    ECL_OP_SET_FIRE_DELAY_RANDOM_PHASE,
)
from th08_ecl_callback_model import CALLBACK_SPECS
from th08_ecl_opcodes import opcode_spec
from th08_stage_ecl_catalog import (
    ROUTE_STAGE_ECL_IDENTITIES,
    STAGE_SPELL_PRACTICE_ECL_IDENTITIES,
)


SCHEMA = "th08-stage5-spell-producer-contract-v2"
DIFFICULTY_INDEX = 3
DIFFICULTY_MASK = 0x08
ROUTE_ID = 2
SPELL_START_OPCODE = 0x7A
EXPECTED_ROUTE_SPELL_IDS = (103, 107, 111, 115, 118)
OBSERVED_ROUTE2_SAKUYA_REMILIA_SPELL_IDS = (103, 107, 111, 115)

_DIRECT_FIRE_OPCODES = frozenset(
    range(ECL_OP_FIRST_DIRECT_FIRE, ECL_OP_LAST_DIRECT_FIRE + 1)
)
_PERIODIC_CONTROL_OPCODES = frozenset(
    {
        ECL_OP_SET_FIRE_DELAY,
        ECL_OP_SET_FIRE_DELAY_RANDOM_PHASE,
        ECL_OP_ENABLE_DEFERRED_FIRE,
        ECL_OP_DISABLE_DEFERRED_FIRE,
        ECL_OP_EMIT_CURRENT_PATTERN,
    }
)
_TRANSFORM_OPCODE = 0x6F
_CALLBACK_OPCODES = frozenset({0x88, 0x89})

# opcode -> (target argument index, edge kind, dependency edge)
_TARGET_OPERANDS = {
    0x34: (0, "call", True),
    0x58: (1, "call_with_enemy", True),
    **{
        opcode: (0, "child_spawn", True)
        for opcode in range(
            ECL_OP_FIRST_CHILD_SOURCE,
            ECL_OP_LAST_CHILD_SOURCE + 1,
        )
    },
    0x7E: (0, "interrupt_slot", True),
    0x82: (0, "enemy_end", False),
    0x85: (2, "health_phase", False),
    0x86: (1, "timeout_phase", False),
    0x87: (1, "aux_vm", True),
}
_SAME_SOURCE_EDGE_KINDS = frozenset(
    {"call", "interrupt_slot", "aux_vm"}
)
_CROSS_SOURCE_EDGE_KINDS = frozenset(
    {"call_with_enemy", "child_spawn"}
)


class SpellProducerContractError(ValueError):
    """Raised when a pinned static producer claim cannot be made exactly."""


def _signed(value: int) -> int:
    return value if value < 0x80000000 else value - 0x100000000


def _eligible(instruction: SubInstruction) -> bool:
    return bool(instruction.difficulty_mask & DIFFICULTY_MASK)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _target(
    instruction: SubInstruction,
) -> tuple[str, int | None, bool] | None:
    specification = _TARGET_OPERANDS.get(instruction.opcode)
    if specification is None:
        return None
    argument_index, edge_kind, dependency = specification
    if argument_index >= len(instruction.arguments):
        raise SpellProducerContractError(
            f"opcode {instruction.opcode:#x} at {instruction.offset:#x} "
            "omits its subroutine target"
        )
    if instruction.parameter_mask & (1 << argument_index):
        return edge_kind, None, dependency
    return edge_kind, _signed(instruction.arguments[argument_index]), dependency


def _subroutine_edges(
    ecl: EclFile,
    subroutine: int,
) -> tuple[tuple[SubInstruction, str, int | None, bool], ...]:
    rows = []
    for instruction in ecl.subroutines[subroutine].instructions:
        if not _eligible(instruction):
            continue
        target = _target(instruction)
        if target is not None:
            edge_kind, target_subroutine, dependency = target
            rows.append(
                (instruction, edge_kind, target_subroutine, dependency)
            )
    return tuple(rows)


def _dependency_closure(
    ecl: EclFile,
    root_subroutine: int,
    *,
    accepted_edge_kinds: frozenset[str] | None = None,
) -> tuple[int, ...]:
    pending = [root_subroutine]
    visited: set[int] = set()
    while pending:
        subroutine = pending.pop()
        if subroutine in visited:
            continue
        if not 0 <= subroutine < len(ecl.subroutines):
            raise SpellProducerContractError(
                f"producer edge targets invalid subroutine {subroutine}"
            )
        visited.add(subroutine)
        for _, edge_kind, target, dependency in _subroutine_edges(
            ecl,
            subroutine,
        ):
            if (
                not dependency
                or target is None
                or target < 0
                or (
                    accepted_edge_kinds is not None
                    and edge_kind not in accepted_edge_kinds
                )
            ):
                continue
            pending.append(target)
    return tuple(sorted(visited))


def _spell_roots(ecl: EclFile) -> dict[int, tuple[int, SubInstruction]]:
    roots: dict[int, tuple[int, SubInstruction]] = {}
    for subroutine in ecl.subroutines:
        for instruction in subroutine.instructions:
            if instruction.opcode != SPELL_START_OPCODE or not _eligible(
                instruction
            ):
                continue
            if not instruction.arguments or instruction.parameter_mask & 0x01:
                raise SpellProducerContractError(
                    f"dynamic/missing spell ID at {instruction.offset:#x}"
                )
            spell_id = (instruction.arguments[0] >> 16) & 0xFFFF
            if spell_id in roots:
                raise SpellProducerContractError(
                    f"duplicate Lunatic spell ID {spell_id}"
                )
            roots[spell_id] = (subroutine.index, instruction)
    return roots


def _semantic_subroutine_digest(
    ecl: EclFile,
    subroutine: int,
    *,
    memo: dict[int, str],
    visiting: set[int],
) -> str:
    cached = memo.get(subroutine)
    if cached is not None:
        return cached
    if subroutine in visiting:
        raise SpellProducerContractError(
            f"recursive subroutine dependency at subroutine {subroutine}"
        )
    visiting.add(subroutine)
    parsed = ecl.subroutines[subroutine]
    rows: list[dict[str, object]] = []
    for instruction in parsed.instructions:
        if not _eligible(instruction):
            continue
        arguments: list[object] = list(instruction.arguments)
        # The remainder of opcode 0x7A is encoded display text.  It cannot
        # affect producer execution and is intentionally outside this digest.
        if instruction.opcode == SPELL_START_OPCODE:
            arguments = arguments[:2]
        target = _target(instruction)
        if target is not None:
            argument_index = _TARGET_OPERANDS[instruction.opcode][0]
            edge_kind, target_subroutine, dependency = target
            if target_subroutine is None:
                normalized_target: object = {
                    "edge": edge_kind,
                    "target": "dynamic",
                }
            elif target_subroutine < 0:
                normalized_target = {
                    "edge": edge_kind,
                    "target": "clear",
                }
            elif dependency:
                if target_subroutine >= len(ecl.subroutines):
                    raise SpellProducerContractError(
                        f"producer edge targets invalid subroutine "
                        f"{target_subroutine}"
                    )
                normalized_target = {
                    "edge": edge_kind,
                    "target_digest": _semantic_subroutine_digest(
                        ecl,
                        target_subroutine,
                        memo=memo,
                        visiting=visiting,
                    ),
                }
            else:
                normalized_target = {
                    "edge": edge_kind,
                    "target": "phase_exit",
                }
            arguments[argument_index] = normalized_target
        rows.append(
            {
                "relative_offset": instruction.offset - parsed.start,
                "time": instruction.time,
                "opcode": instruction.opcode,
                "size": instruction.size,
                "byte_08": instruction.byte_08,
                "difficulty_mask": instruction.difficulty_mask,
                "parameter_mask": instruction.parameter_mask,
                "arguments": arguments,
            }
        )
    visiting.remove(subroutine)
    digest = _canonical_sha256(rows)
    memo[subroutine] = digest
    return digest


def _site(
    ecl: EclFile,
    subroutine: int,
    instruction: SubInstruction,
) -> dict[str, object]:
    parsed = ecl.subroutines[subroutine]
    return {
        "subroutine": subroutine,
        "offset": instruction.offset,
        "relative_offset": instruction.offset - parsed.start,
        "local_vm_time": instruction.time,
        "opcode": instruction.opcode,
        "opcode_hex": f"0x{instruction.opcode:02x}",
        "opcode_name": opcode_spec(instruction.opcode).name,
        "parameter_mask": instruction.parameter_mask,
    }


def _callback_site(
    ecl: EclFile,
    subroutine: int,
    instruction: SubInstruction,
) -> dict[str, object]:
    site = _site(ecl, subroutine, instruction)
    if not instruction.arguments or instruction.parameter_mask & 0x01:
        callback_index = None
    else:
        callback_index = _signed(instruction.arguments[0])
    site.update(
        {
            "action": "invoke" if instruction.opcode == 0x88 else "install",
            "callback_index": callback_index,
            "callback_name": (
                CALLBACK_SPECS[callback_index].name
                if callback_index is not None
                and 0 <= callback_index < len(CALLBACK_SPECS)
                else None
            ),
        }
    )
    return site


def _literal_timeout(
    root_subroutine: int,
    instructions: Iterable[SubInstruction],
) -> tuple[int, int]:
    sites = [instruction for instruction in instructions if instruction.opcode == 0x86]
    if len(sites) != 1:
        raise SpellProducerContractError(
            f"spell root {root_subroutine} has {len(sites)} timeout sites"
        )
    instruction = sites[0]
    if (
        len(instruction.arguments) < 2
        or instruction.parameter_mask & 0x03
    ):
        raise SpellProducerContractError(
            f"spell root {root_subroutine} has a dynamic timeout"
        )
    return _signed(instruction.arguments[0]), _signed(instruction.arguments[1])


def _program_report(
    ecl: EclFile,
    *,
    spell_id: int,
    root_subroutine: int,
    spell_start: SubInstruction,
) -> dict[str, object]:
    same_source = _dependency_closure(
        ecl,
        root_subroutine,
        accepted_edge_kinds=_SAME_SOURCE_EDGE_KINDS,
    )
    dependency_subroutines = _dependency_closure(ecl, root_subroutine)
    same_source_set = set(same_source)
    dependency_rows = [
        (subroutine, instruction)
        for subroutine in dependency_subroutines
        for instruction in ecl.subroutines[subroutine].instructions
        if _eligible(instruction)
    ]
    root_instructions = tuple(
        instruction
        for instruction in ecl.subroutines[root_subroutine].instructions
        if _eligible(instruction)
    )
    timeout_frames, timeout_successor = _literal_timeout(
        root_subroutine,
        root_instructions,
    )
    child_source_roots: set[int] = set()
    dynamic_edges: list[dict[str, object]] = []
    for subroutine in same_source:
        for instruction, edge_kind, target, dependency in _subroutine_edges(
            ecl,
            subroutine,
        ):
            if target is None:
                dynamic_edges.append(
                    {
                        **_site(ecl, subroutine, instruction),
                        "edge_kind": edge_kind,
                    }
                )
            elif (
                dependency
                and edge_kind in _CROSS_SOURCE_EDGE_KINDS
                and target >= 0
            ):
                child_source_roots.add(target)

    direct_fire_sites = [
        _site(ecl, subroutine, instruction)
        for subroutine, instruction in dependency_rows
        if instruction.opcode in _DIRECT_FIRE_OPCODES
    ]
    transform_sites = [
        _site(ecl, subroutine, instruction)
        for subroutine, instruction in dependency_rows
        if instruction.opcode == _TRANSFORM_OPCODE
    ]
    child_sites = [
        _site(ecl, subroutine, instruction)
        for subroutine, instruction in dependency_rows
        if ECL_OP_FIRST_CHILD_SOURCE
        <= instruction.opcode
        <= ECL_OP_LAST_CHILD_SOURCE
    ]
    callback_sites = [
        _callback_site(ecl, subroutine, instruction)
        for subroutine, instruction in dependency_rows
        if instruction.opcode in _CALLBACK_OPCODES
    ]
    periodic_sites = [
        _site(ecl, subroutine, instruction)
        for subroutine, instruction in dependency_rows
        if instruction.opcode in _PERIODIC_CONTROL_OPCODES
    ]
    callback_counts = Counter(
        (
            str(site["action"]),
            site["callback_index"],
        )
        for site in callback_sites
    )
    memo: dict[int, str] = {}
    semantic_digest = _semantic_subroutine_digest(
        ecl,
        root_subroutine,
        memo=memo,
        visiting=set(),
    )
    requirements = []
    if direct_fire_sites:
        requirements.append("direct_fire")
    if transform_sites:
        requirements.append("bullet_transform")
    if child_sites:
        requirements.append("child_source")
    for action, callback_index in sorted(
        callback_counts,
        key=lambda item: (item[0], -999 if item[1] is None else int(item[1])),
    ):
        requirements.append(f"callback_{action}_{callback_index}")
    if periodic_sites:
        requirements.append("periodic_emitter")

    return {
        "spell_id": spell_id,
        "root_subroutine": root_subroutine,
        "spell_start_offset": spell_start.offset,
        "spell_start_local_vm_time": spell_start.time,
        "enemy_face": spell_start.arguments[0] & 0xFFFF,
        "timeout_frames": timeout_frames,
        "timeout_successor_subroutine": timeout_successor,
        "same_source_subroutines": list(same_source),
        "dependency_subroutines": list(dependency_subroutines),
        "child_source_roots": sorted(child_source_roots),
        "direct_fire_sites": direct_fire_sites,
        "transform_sites": transform_sites,
        "child_spawn_sites": child_sites,
        "callback_sites": callback_sites,
        "periodic_control_sites": periodic_sites,
        "dynamic_subroutine_edges": dynamic_edges,
        "site_counts": {
            "direct_fire": len(direct_fire_sites),
            "transform": len(transform_sites),
            "child_spawn": len(child_sites),
            "callback": len(callback_sites),
            "periodic_control": len(periodic_sites),
        },
        "semantic_program_sha256": semantic_digest,
        "required_lowering_families": requirements,
        "lexical_scope_only": True,
        "root_is_in_same_source_component": root_subroutine in same_source_set,
    }


def _image_report(path: Path, *, expected_sha256: str) -> dict[str, object]:
    ecl = parse_ecl(path)
    if ecl.sha256 != expected_sha256:
        raise SpellProducerContractError(
            f"{path.name} SHA-256 differs from its mode catalog"
        )
    roots = _spell_roots(ecl)
    return {
        "filename": path.name,
        "sha256": ecl.sha256,
        "spell_ids": sorted(roots),
        "programs": {
            str(spell_id): _program_report(
                ecl,
                spell_id=spell_id,
                root_subroutine=root,
                spell_start=spell_start,
            )
            for spell_id, (root, spell_start) in sorted(roots.items())
        },
    }


def build_report(decoded_dir: Path) -> dict[str, object]:
    route_identity = ROUTE_STAGE_ECL_IDENTITIES["5"]
    spell_practice_identity = STAGE_SPELL_PRACTICE_ECL_IDENTITIES["5"]
    route = _image_report(
        decoded_dir / route_identity.filename,
        expected_sha256=route_identity.sha256,
    )
    spell_practice = _image_report(
        decoded_dir / spell_practice_identity.filename,
        expected_sha256=spell_practice_identity.sha256,
    )
    route_programs = route["programs"]
    spell_practice_programs = spell_practice["programs"]
    assert isinstance(route_programs, dict)
    assert isinstance(spell_practice_programs, dict)
    shared_spell_ids = sorted(
        set(map(int, route_programs)) & set(map(int, spell_practice_programs))
    )
    equivalence = {}
    for spell_id in shared_spell_ids:
        route_program = route_programs[str(spell_id)]
        spell_practice_program = spell_practice_programs[str(spell_id)]
        assert isinstance(route_program, dict)
        assert isinstance(spell_practice_program, dict)
        route_digest = route_program["semantic_program_sha256"]
        spell_practice_digest = spell_practice_program[
            "semantic_program_sha256"
        ]
        equivalence[str(spell_id)] = {
            "route_semantic_program_sha256": route_digest,
            "spell_practice_semantic_program_sha256": spell_practice_digest,
            "equivalent": route_digest == spell_practice_digest,
        }
    route_spell_ids = tuple(int(value) for value in route["spell_ids"])
    passed = (
        route_spell_ids == EXPECTED_ROUTE_SPELL_IDS
        and set(route_spell_ids).issubset(shared_spell_ids)
        and all(bool(row["equivalent"]) for row in equivalence.values())
        and all(
            not program["dynamic_subroutine_edges"]
            for program in route_programs.values()
            if isinstance(program, dict)
        )
    )
    return {
        "schema": SCHEMA,
        "passed": passed,
        "scope": {
            "route_id": ROUTE_ID,
            "difficulty_index": DIFFICULTY_INDEX,
            "difficulty_mask": DIFFICULTY_MASK,
            "observed_route2_sakuya_remilia_spell_ids": list(
                OBSERVED_ROUTE2_SAKUYA_REMILIA_SPELL_IDS
            ),
            "claim": (
                "static literal producer topology and normalized route/"
                "Spell-Practice program equivalence; no reached-prefix or action "
                "authority"
            ),
        },
        "native_authority": {
            "loader": (
                "th08/src/EnemyManager.cpp: isSpellPractice bit14 selects "
                "the stage *sp.ecl table below card 205; Practice Start "
                "keeps bit14 clear and loads the route stage ECL"
            ),
            "spell_layout": (
                "th08/src/EclDependencies.cpp: opcode 0x7A stores enemyFace "
                "u16 at +0x0C and spellCardNumber u16 at +0x0E"
            ),
            "callback_dispatch": (
                "th08/src/EclRunHigh.inl and th08/src/EclExIns.cpp"
            ),
        },
        "route": route,
        "spell_practice": spell_practice,
        "shared_spell_ids": shared_spell_ids,
        "route_spell_practice_equivalence": equivalence,
        "limitations": [
            "Static eligible lexical closure can include a branch not reached from a retained VM root.",
            "RNG state, player-aim dependence, phase timing, and live locals require a runtime-root replay.",
            "A matching semantic digest proves copied ECL program equivalence, not solver lowering completeness.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoded-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = build_report(arguments.decoded_dir)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if arguments.output is None:
        print(serialized)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
