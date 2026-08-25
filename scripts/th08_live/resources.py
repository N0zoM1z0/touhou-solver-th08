"""Single-owner lifecycle for live executors and background services."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Iterable

class LiveServiceResources:
    """Own every executor and closeable background service for a live run."""

    def __init__(
        self,
        *,
        local_only: bool,
        viability_audit_enabled: bool,
        future_source_enabled: bool | None = None,
        executor_factory: Callable[..., Any] = ThreadPoolExecutor,
    ) -> None:
        self.corridor_executor: Any | None = None
        self.audit_executor: Any | None = None
        self.enemy_executor: Any | None = None
        self.future_source_executor: Any | None = None
        self._closed = False
        try:
            if not local_only:
                self.corridor_executor = executor_factory(
                    max_workers=1,
                    thread_name_prefix="th08-corridor",
                )
            if viability_audit_enabled:
                self.audit_executor = executor_factory(
                    max_workers=1,
                    thread_name_prefix="th08-viability-audit",
                )
            self.enemy_executor = executor_factory(
                max_workers=1,
                thread_name_prefix="th08-enemy-sensor",
            )
            if (
                not local_only
                if future_source_enabled is None
                else future_source_enabled
            ):
                self.future_source_executor = executor_factory(
                    max_workers=1,
                    thread_name_prefix="th08-future-source",
                )
        except BaseException:
            self.close()
            raise

    def close(
        self,
        *,
        corridor_future: Future[Any] | None = None,
        enemy_future: Future[Any] | None = None,
        future_source_future: Future[Any] | None = None,
    ) -> None:
        """Cancel pending work and idempotently close owners in live order."""

        if self._closed:
            return
        self._closed = True
        cleanup_errors: list[BaseException] = []

        def attempt(operation: Callable[[], object]) -> None:
            try:
                operation()
            except BaseException as error:
                cleanup_errors.append(error)

        if corridor_future is not None:
            attempt(corridor_future.cancel)
        if self.corridor_executor is not None:
            attempt(
                lambda: self.corridor_executor.shutdown(
                    wait=True,
                    cancel_futures=True,
                )
            )
        if self.audit_executor is not None:
            attempt(lambda: self.audit_executor.shutdown(wait=True))
        if enemy_future is not None:
            attempt(enemy_future.cancel)
        if self.enemy_executor is not None:
            attempt(
                lambda: self.enemy_executor.shutdown(
                    wait=True,
                    cancel_futures=True,
                )
            )
        if future_source_future is not None:
            attempt(future_source_future.cancel)
        if self.future_source_executor is not None:
            attempt(
                lambda: self.future_source_executor.shutdown(
                    wait=True,
                    cancel_futures=True,
                )
            )
        if cleanup_errors:
            raise cleanup_errors[0]


__all__: Iterable[str] = ["LiveServiceResources"]
