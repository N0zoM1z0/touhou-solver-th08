from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import socket
import struct
import unittest

from th08_global_authority import GlobalActionAuthorityAssessment
from th08_corridor_runtime import solve_corridor
from th08_future_hazard_projection import complete_future_hazard_projection
from th08_linux.online_authority import (
    ONLINE_GLOBAL_ACTION_AUTHORITY,
    TH08_ONLINE_AUTHORITY_CONFIG,
    OnlineActionAuthority,
)
from th08_linux.online_bridge import OnlineSolverBridgeClient
from th08_linux.online_clock import (
    OnlineClockObservation,
    OnlineUnitCadenceAuthority,
)
from th08_linux.online_services import (
    LinuxOnlineFutureGlobalService,
    LinuxOnlineServiceConfig,
)
from th08_linux.online_protocol import (
    REQUEST_SIZE,
    OnlineInputRequest,
    decode_online_request,
    encode_online_response,
)
from th08_linux.planner import (
    LinuxOnlineHazardCapture,
    LinuxOneEpochPlanner,
    LinuxPlannerGuidance,
    LinuxPlannerSnapshot,
)
from th08_linux.protocol import (
    BOMB,
    FOCUS,
    LEFT,
    LIVES_PRESERVED,
    REPLAY_TARGET_STAMPED,
    RESPONSE_MAGIC,
    SHOOT,
)
from th08_local_planner.models import Decision
from th08_time_scale import TH08_UNIT_TIME_SCALE_BITS, Th08TimeScaleSchedule
from th08_live.scale_schedule_authority import FinalBScaleScheduleAuthority
from th08_corridor_adapter import TH08_CORRIDOR_CONFIG
from th08_live.models import Bullet
from th08_live.runtime_ecl_identity import RuntimeEclAcceptedVersion
from th08_runtime.game_state import (
    ADDR_FRSCREEN_IMPL_POINTER,
    ADDR_SCRIPTED_UPDATE_FREEZE,
)


def _request(source_epoch: int, *, published_us: int = 123_000) -> bytes:
    return struct.pack(
        "<IHHQQHHHHIIIIQ",
        0x51523854,
        2,
        REQUEST_SIZE,
        source_epoch,
        source_epoch + 1,
        SHOOT | FOCUS,
        SHOOT | FOCUS | LEFT,
        0x9630,
        0,
        REPLAY_TARGET_STAMPED | LIVES_PRESERVED,
        4,
        2,
        1,
        published_us,
    )


def _snapshot(*, frame: int = 100) -> LinuxPlannerSnapshot:
    return LinuxPlannerSnapshot(
        frame=frame,
        player_phase=0,
        player_x=192.0,
        player_y=400.0,
        time_scale_bits=TH08_UNIT_TIME_SCALE_BITS,
        power=64.0,
        bombs=3.0,
        bullets=(),
        lasers=(),
        enemy_bodies=(),
        items=(),
    )


def _clock_observation(
    *,
    source_epoch: int,
    manager_frame: int,
    context: tuple[int, int, int | None] = (1, 0, None),
    engine_flags: int = 0x04,
    dialogue_active: bool | None = False,
    scripted_update_freeze: bool | None = False,
) -> OnlineClockObservation:
    return OnlineClockObservation(
        source_input_epoch=source_epoch,
        captured_source_input_epoch=source_epoch,
        manager_frame=manager_frame,
        engine_flags=engine_flags,
        player_phase=0,
        bomb_active=False,
        dialogue_active=dialogue_active,
        scripted_update_freeze=scripted_update_freeze,
        context=context,
    )


class LinuxOnlineProtocolTests(unittest.TestCase):
    def test_request_names_source_and_exact_next_target(self) -> None:
        request = decode_online_request(_request(41))
        self.assertEqual(request.source_epoch, 41)
        self.assertEqual(request.target_epoch, 42)
        self.assertEqual(request.epoch, 42)
        self.assertEqual(request.deadline_misses, 4)
        self.assertEqual(request.late_responses, 2)
        self.assertEqual(request.dropped_requests, 1)
        self.assertEqual(request.publication_age_ms(now_ns=124_000_000), 1.0)

    def test_response_cannot_target_a_later_or_bomb_epoch(self) -> None:
        payload = encode_online_response(
            source_epoch=7,
            target_epoch=8,
            input_mask=SHOOT | FOCUS | LEFT,
        )
        self.assertEqual(
            struct.unpack("<IHHQQHHI", payload),
            (RESPONSE_MAGIC, 2, 32, 7, 8, SHOOT | FOCUS | LEFT, 0, 0),
        )
        with self.assertRaisesRegex(ValueError, "exactly source epoch"):
            encode_online_response(
                source_epoch=7,
                target_epoch=9,
                input_mask=SHOOT,
            )
        with self.assertRaisesRegex(ValueError, "Bomb"):
            encode_online_response(
                source_epoch=7,
                target_epoch=8,
                input_mask=BOMB,
            )

    def test_client_drains_to_newest_publication_and_allows_gaps(self) -> None:
        game, solver = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(game.close)
        client = OnlineSolverBridgeClient(solver)
        self.addCleanup(client.close)
        game.send(_request(10))
        game.send(_request(12))

        newest = client.receive()
        self.assertEqual(newest.source_epoch, 12)
        self.assertEqual(client.drained_publications, 1)
        self.assertEqual(client.observed_epoch_gaps, 1)
        self.assertTrue(client.respond(SHOOT | FOCUS | LEFT))
        response = game.recv(32)
        self.assertEqual(struct.unpack_from("<QQ", response, 8), (12, 13))


class _EpochReader:
    def __init__(self, *epochs: int) -> None:
        self._epochs = list(epochs)

    def u32(self, address: int) -> int:
        if address == 0x1234:
            return self._epochs.pop(0)
        if address == ADDR_FRSCREEN_IMPL_POINTER:
            return 0
        raise AssertionError(f"unexpected u32 address {address:#x}")

    def u8(self, address: int) -> int:
        if address == ADDR_SCRIPTED_UPDATE_FREEZE:
            return 0
        raise AssertionError(f"unexpected u8 address {address:#x}")


class _OnlineCapture(LinuxOnlineHazardCapture):
    def __init__(self, reader: _EpochReader) -> None:
        self._reader = reader
        self._input_epoch_address = 0x1234

    def capture(self, _state: object) -> LinuxPlannerSnapshot:
        return _snapshot()


class LinuxOnlineAuthorityTests(unittest.TestCase):
    @staticmethod
    def _wire_request(source: int = 7) -> OnlineInputRequest:
        return decode_online_request(_request(source))

    def test_capture_rejects_an_input_epoch_crossing(self) -> None:
        capture = _OnlineCapture(_EpochReader(7, 8))
        with self.assertRaisesRegex(RuntimeError, "crossed its input epoch"):
            capture.capture_transaction(
                self._wire_request(),
                observe=lambda: {"gameplay_active": True},
            )

    def test_capture_attaches_input_epoch_and_native_freeze_gates(self) -> None:
        capture = _OnlineCapture(_EpochReader(7, 7))
        _state, snapshot = capture.capture_transaction(
            self._wire_request(),
            observe=lambda: {"gameplay_active": True},
        )

        self.assertEqual(snapshot.source_input_epoch, 7)
        self.assertFalse(snapshot.dialogue_active)
        self.assertFalse(snapshot.scripted_update_freeze)

    def test_hard_authority_uses_one_physical_frame_layers(self) -> None:
        self.assertEqual(TH08_ONLINE_AUTHORITY_CONFIG.frames_per_layer, 1)
        self.assertEqual(
            LinuxOnlineServiceConfig().corridor_config.frames_per_layer,
            1,
        )
        with self.assertRaisesRegex(ValueError, "one physical frame"):
            OnlineActionAuthority(corridor_config=TH08_CORRIDOR_CONFIG)

    def test_manager_policy_clock_requires_and_revokes_unit_cadence(self) -> None:
        clock = OnlineUnitCadenceAuthority()
        first = clock.observe(
            _clock_observation(source_epoch=100, manager_frame=40)
        )
        certified = clock.observe(
            _clock_observation(source_epoch=103, manager_frame=43)
        )
        mismatched = clock.observe(
            _clock_observation(source_epoch=105, manager_frame=44)
        )
        recovered = clock.observe(
            _clock_observation(source_epoch=106, manager_frame=45)
        )

        self.assertFalse(first.allowed)
        self.assertEqual(first.reason, "unit-cadence-needs-successor")
        self.assertTrue(certified.allowed)
        self.assertEqual((certified.input_delta, certified.manager_delta), (3, 3))
        self.assertFalse(mismatched.allowed)
        self.assertEqual(mismatched.reason, "input-manager-cadence-mismatch")
        self.assertGreater(mismatched.generation, certified.generation)
        self.assertTrue(recovered.allowed)

    def test_manager_policy_clock_fails_closed_on_native_freeze_gates(self) -> None:
        cases = (
            ({"dialogue_active": True}, "dialogue-active"),
            (
                {"scripted_update_freeze": True},
                "scripted-update-freeze-active",
            ),
            ({"engine_flags": 0x404}, "manager-update-skipped"),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason):
                clock = OnlineUnitCadenceAuthority()
                observation = _clock_observation(
                    source_epoch=100,
                    manager_frame=40,
                    **changes,
                )
                assessment = clock.observe(observation)
                self.assertFalse(assessment.allowed)
                self.assertEqual(assessment.reason, reason)

    def test_rolling_publication_cannot_starve_the_earliest_pending_epoch(
        self,
    ) -> None:
        authority = OnlineActionAuthority()
        context = (1, 0, None)
        earliest = SimpleNamespace(context_key=context, source_frame=180)
        newer = SimpleNamespace(context_key=context, source_frame=188)

        self.assertTrue(
            authority.publish(
                earliest,  # type: ignore[arg-type]
                solution_source_input_epoch=180,
                current_frame=100,
                current_input_epoch=100,
                context=context,
            )
        )
        self.assertFalse(
            authority.publish(
                newer,  # type: ignore[arg-type]
                solution_source_input_epoch=188,
                current_frame=108,
                current_input_epoch=108,
                context=context,
            )
        )
        self.assertIs(authority.pending_solution, earliest)

        authority.advance(
            current_frame=180,
            current_input_epoch=180,
            context=context,
        )
        self.assertIs(authority.active_solution, earliest)
        self.assertIsNone(authority.pending_solution)

    def test_policy_is_revoked_when_input_and_manager_clocks_diverge(self) -> None:
        authority = OnlineActionAuthority()
        context = (1, 0, None)
        solution = SimpleNamespace(context_key=context, source_frame=100)
        self.assertTrue(
            authority.publish(
                solution,  # type: ignore[arg-type]
                solution_source_input_epoch=100,
                current_frame=100,
                current_input_epoch=100,
                context=context,
            )
        )

        self.assertFalse(
            authority.advance(
                current_frame=101,
                current_input_epoch=102,
                context=context,
            )
        )
        self.assertIsNone(authority.active_solution)

    def test_planner_forwards_global_and_future_into_action_choice(self) -> None:
        captured: dict[str, object] = {}

        def chooser(**kwargs: object) -> Decision:
            captured.update(kwargs)
            return Decision(
                SHOOT | FOCUS | LEFT,
                "left",
                1.0,
                1.0,
                0.0,
                False,
            )

        schedule = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=32,
            provenance="test-exact-scale",
            source_frame=100,
        )
        future = object()
        guidance = LinuxPlannerGuidance(
            allowed_first_actions=("left",),
            allowed_action_authority=ONLINE_GLOBAL_ACTION_AUTHORITY,
            future_hazard_projection=future,  # type: ignore[arg-type]
            future_projection_offset=3,
            time_scale_schedule=schedule,
            authority_version="version-a",
        )
        plan = LinuxOneEpochPlanner(chooser=chooser).choose(
            _snapshot(),
            previous_mask=SHOOT | FOCUS,
            guidance=guidance,
        )
        self.assertEqual(captured["allowed_first_actions"], ("left",))
        self.assertEqual(
            captured["allowed_action_authority"],
            ONLINE_GLOBAL_ACTION_AUTHORITY,
        )
        self.assertIs(captured["future_hazard_projection"], future)
        self.assertEqual(captured["future_projection_offset"], 3)
        self.assertEqual(plan.reason, "local+global+future-online-plan")

    def test_named_online_authority_cannot_relax_to_a_local_action(self) -> None:
        root = _snapshot()
        snapshot = LinuxPlannerSnapshot(
            frame=root.frame,
            player_phase=root.player_phase,
            player_x=root.player_x,
            player_y=432.0,
            time_scale_bits=root.time_scale_bits,
            power=root.power,
            bombs=root.bombs,
            bullets=(Bullet(160.0, 432.0, 4.0, 0.0, 2.0, 2.0),),
            lasers=(),
            enemy_bodies=(),
            items=(),
        )
        guidance = LinuxPlannerGuidance(
            allowed_first_actions=("stay",),
            allowed_action_authority=ONLINE_GLOBAL_ACTION_AUTHORITY,
            time_scale_schedule=Th08TimeScaleSchedule.constant(
                TH08_UNIT_TIME_SCALE_BITS,
                horizon=64,
                provenance="test-exact-scale",
                source_frame=100,
            ),
        )

        plan = LinuxOneEpochPlanner().choose(
            snapshot,
            previous_mask=SHOOT | FOCUS,
            guidance=guidance,
        )

        self.assertEqual(plan.action, "stay")
        self.assertIsNotNone(plan.decision)
        self.assertTrue(plan.decision.viability_constrained)  # type: ignore[union-attr]
        self.assertFalse(
            plan.decision.viability_constraint_relaxed  # type: ignore[union-attr]
        )

    def test_exact_global_query_becomes_live_allowed_action_authority(self) -> None:
        policy_guidance = SimpleNamespace(
            support_covers_current=True,
            allowed_first_actions=("left", "up_left"),
            repair_volumes=(("left", 5),),
            recovery_distances=(("left", 0.0),),
            safety_actions=(),
            safety_state_value=None,
            survival_actions=(),
            survival_frames=None,
            survival_bottleneck_margin=None,
            position_error=0.5,
        )
        query_result = SimpleNamespace(
            guidance=policy_guidance,
            primary=SimpleNamespace(target=(160.0, 320.0, 12)),
        )
        coordinator = SimpleNamespace(query=lambda _request: query_result)
        version = SimpleNamespace(digest="policy-version")

        def assess(*_args: object, **_kwargs: object) -> object:
            return GlobalActionAuthorityAssessment(True, (), version)  # type: ignore[arg-type]

        authority = OnlineActionAuthority(
            policy_coordinator=coordinator,  # type: ignore[arg-type]
            assess=assess,  # type: ignore[arg-type]
        )
        context = (3, 0, None)
        solution = SimpleNamespace(
            context_key=context,
            source_frame=100,
            future_hazard_projection=None,
        )
        self.assertTrue(
            authority.publish(
                solution,  # type: ignore[arg-type]
                solution_source_input_epoch=100,
                current_frame=100,
                current_input_epoch=100,
                context=context,
            )
        )
        schedule = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=256,
            provenance="test-exact-scale",
            source_frame=100,
        )
        result = authority.guidance_for(
            _snapshot(),
            current_input_epoch=100,
            current_input=SHOOT | FOCUS,
            context=context,
            runtime_ecl_version=None,
            time_scale_schedule=schedule,
        )
        self.assertTrue(result.global_constraint_applied)
        self.assertEqual(
            result.guidance.allowed_first_actions,
            ("left", "up_left"),
        )
        self.assertEqual(
            result.guidance.allowed_action_authority,
            ONLINE_GLOBAL_ACTION_AUTHORITY,
        )
        self.assertEqual(authority.constrained_action_count, 1)

    def test_real_one_frame_policy_join_constrains_online_action(self) -> None:
        context = (1, 0, None)
        runtime = RuntimeEclAcceptedVersion(
            runtime_base=0x2100000,
            image_length=4096,
            relocated_sha256="1" * 64,
            normalized_sha256="2" * 64,
            static_sha256="3" * 64,
            route_id=2,
            difficulty_index=0,
            stage_route_index=0,
            gameplay_epoch=1,
            decision_frame=90,
            snapshot_frame=90,
        )
        projection = complete_future_hazard_projection(
            root_frame=90,
            horizon_frames=100,
            events=(),
            source_semantics_version="test-online-real-policy-v1",
        )
        schedule = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=256,
            provenance="test-online-real-policy-scale",
            source_frame=90,
        )
        solution = solve_corridor(
            source_frame=100,
            snapshot_frame=90,
            forecast_lead_frames=10,
            player_x=192.0,
            player_y=400.0,
            bullets=(),
            lasers=(),
            enemy_bodies=(),
            future_hazard_projection=projection,
            runtime_ecl_version=runtime,
            snapshot_lag=0,
            control_delay_candidates=(0,),
            observed_control_delay_candidates=(0,),
            nominal_control_delay=0,
            active_action="stay",
            context_key=context,
            time_scale_schedule=schedule,
            corridor_config=TH08_ONLINE_AUTHORITY_CONFIG,
        )
        policy = solution.plan.viability_policy
        self.assertIsNotNone(policy)
        self.assertEqual(policy.config.frames_per_layer, 1)  # type: ignore[union-attr]
        authority = OnlineActionAuthority()
        self.assertTrue(
            authority.publish(
                solution,
                solution_source_input_epoch=100,
                current_frame=100,
                current_input_epoch=100,
                context=context,
            )
        )

        result = authority.guidance_for(
            _snapshot(),
            current_input_epoch=100,
            current_input=SHOOT | FOCUS,
            context=context,
            runtime_ecl_version=runtime,
            time_scale_schedule=schedule,
        )

        self.assertTrue(result.global_constraint_applied, result.reasons)
        self.assertTrue(result.guidance.allowed_first_actions)
        self.assertEqual(
            result.guidance.allowed_action_authority,
            ONLINE_GLOBAL_ACTION_AUTHORITY,
        )

    def test_local_future_projection_requires_the_full_local_horizon(self) -> None:
        policy_guidance = SimpleNamespace(
            support_covers_current=True,
            allowed_first_actions=("left",),
            repair_volumes=(),
            recovery_distances=(),
            safety_actions=(),
            safety_state_value=None,
            survival_actions=(),
            survival_frames=None,
            survival_bottleneck_margin=None,
            position_error=0.0,
        )
        coordinator = SimpleNamespace(
            query=lambda _request: SimpleNamespace(
                guidance=policy_guidance,
                primary=SimpleNamespace(target=None),
            )
        )

        def assess(*_args: object, **_kwargs: object) -> object:
            return GlobalActionAuthorityAssessment(
                True,
                (),
                SimpleNamespace(digest="policy-version"),  # type: ignore[arg-type]
            )

        projection = complete_future_hazard_projection(
            root_frame=100,
            horizon_frames=40,
            events=(),
            source_semantics_version="test-online-local-horizon-v1",
        )
        context = (3, 0, None)
        solution = SimpleNamespace(
            context_key=context,
            source_frame=100,
            future_hazard_projection=projection,
        )
        authority = OnlineActionAuthority(
            policy_coordinator=coordinator,  # type: ignore[arg-type]
            assess=assess,  # type: ignore[arg-type]
            local_future_horizon_frames=32,
        )
        authority.publish(
            solution,  # type: ignore[arg-type]
            solution_source_input_epoch=100,
            current_frame=100,
            current_input_epoch=100,
            context=context,
        )
        schedule = Th08TimeScaleSchedule.constant(
            TH08_UNIT_TIME_SCALE_BITS,
            horizon=256,
            provenance="test-exact-scale",
            source_frame=109,
        )
        result = authority.guidance_for(
            _snapshot(frame=109),
            current_input_epoch=109,
            current_input=SHOOT | FOCUS,
            context=context,
            runtime_ecl_version=None,
            time_scale_schedule=schedule,
        )

        self.assertTrue(result.global_constraint_applied)
        self.assertFalse(result.future_projection_applied_locally)
        self.assertIsNone(result.guidance.future_hazard_projection)

    def test_final_b_uses_the_existing_exact_scale_source_authority(self) -> None:
        decoded = Path(__file__).resolve().parents[1] / "artifacts" / "decoded"
        service = LinuxOnlineFutureGlobalService(
            reader=SimpleNamespace(),
            input_epoch_address=0x1234,
            decoded_ecl_directory=decoded,
            route_id=2,
            difficulty_index=0,
            config=LinuxOnlineServiceConfig(native_viability_workers=1),
        )
        self.addCleanup(service.close)

        binding = service._load_stage(7)

        self.assertIsNotNone(binding)
        self.assertIsInstance(
            binding.scale_authority,  # type: ignore[union-attr]
            FinalBScaleScheduleAuthority,
        )


if __name__ == "__main__":
    unittest.main()
