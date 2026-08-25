from __future__ import annotations

import unittest

from th08_live import LiveServiceResources


class _FakeExecutor:
    def __init__(
        self,
        events: list[object],
        *,
        max_workers: int,
        thread_name_prefix: str,
    ) -> None:
        self.events = events
        self.name = thread_name_prefix
        events.append(("open", self.name, max_workers))

    def shutdown(self, *, wait: bool, cancel_futures: bool = False) -> None:
        self.events.append(("shutdown", self.name, wait, cancel_futures))


class _FakeFuture:
    def __init__(self, events: list[object], name: str) -> None:
        self.events = events
        self.name = name

    def cancel(self) -> bool:
        self.events.append(("cancel", self.name))
        return True


class LiveServiceResourcesTests(unittest.TestCase):
    def test_enabled_resources_have_one_owner_and_close_in_order(self) -> None:
        events: list[object] = []
        resources = LiveServiceResources(
            local_only=False,
            viability_audit_enabled=True,
            executor_factory=lambda **kwargs: _FakeExecutor(events, **kwargs),
        )
        corridor = _FakeFuture(events, "corridor")
        enemy = _FakeFuture(events, "enemy")
        future_source = _FakeFuture(events, "future_source")

        resources.close(
            corridor_future=corridor,
            enemy_future=enemy,
            future_source_future=future_source,
        )
        resources.close(
            corridor_future=corridor,
            enemy_future=enemy,
            future_source_future=future_source,
        )

        self.assertEqual(
            events,
            [
                ("open", "th08-corridor", 1),
                ("open", "th08-viability-audit", 1),
                ("open", "th08-enemy-sensor", 1),
                ("open", "th08-future-source", 1),
                ("cancel", "corridor"),
                ("shutdown", "th08-corridor", True, True),
                ("shutdown", "th08-viability-audit", True, False),
                ("cancel", "enemy"),
                ("shutdown", "th08-enemy-sensor", True, True),
                ("cancel", "future_source"),
                ("shutdown", "th08-future-source", True, True),
            ],
        )

    def test_local_only_still_owns_audit_and_enemy_executors(self) -> None:
        events: list[object] = []
        resources = LiveServiceResources(
            local_only=True,
            viability_audit_enabled=True,
            executor_factory=lambda **kwargs: _FakeExecutor(events, **kwargs),
        )

        self.assertIsNone(resources.corridor_executor)
        self.assertIsNotNone(resources.audit_executor)
        self.assertIsNotNone(resources.enemy_executor)
        self.assertIsNone(resources.future_source_executor)
        resources.close()

    def test_audit_executor_is_optional(self) -> None:
        events: list[object] = []
        resources = LiveServiceResources(
            local_only=True,
            viability_audit_enabled=False,
            executor_factory=lambda **kwargs: _FakeExecutor(events, **kwargs),
        )
        self.assertIsNone(resources.audit_executor)
        resources.close()

    def test_capture_only_future_source_worker_survives_local_only(self) -> None:
        events: list[object] = []
        resources = LiveServiceResources(
            local_only=True,
            viability_audit_enabled=False,
            future_source_enabled=True,
            executor_factory=lambda **kwargs: _FakeExecutor(events, **kwargs),
        )

        self.assertIsNone(resources.corridor_executor)
        self.assertIsNotNone(resources.future_source_executor)
        resources.close()
        self.assertIn(("open", "th08-future-source", 1), events)


if __name__ == "__main__":
    unittest.main()
