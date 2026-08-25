"""Corridor policy artifacts, publication state, and runtime handles."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, replace

from ..query_survival import PipelineSurvivalWorkspace
from ..hazard_coverage import HazardCoverageAssessment
from ..pipeline_identity import VersionIdentity
from ..policy_authority import PolicyAuthorityVersion
from .model import CorridorPlan


@dataclass(frozen=True)
class CorridorPolicyArtifact:
    """Handle-free policy result plus value-only identity/timing metadata."""

    source_frame: int
    plan: CorridorPlan
    solve_ms: float
    snapshot_frame: int | None = None
    forecast_lead_frames: int = 0
    required_gate_lane: str | None = None
    constraint_honored: bool = False
    context_key: tuple[int, int, int | None] | None = None
    worker_ms: float | None = None
    background_priority_lowered: bool = False
    native_viability_worker_limit: int | None = None
    native_viability_worker_limit_applied: bool = False
    time_scale_identity: tuple[object, ...] | None = None
    future_hazard_version: VersionIdentity | None = None
    future_hazard_coverage: HazardCoverageAssessment | None = None
    current_pool_callback_join_version: VersionIdentity | None = None
    authority_version: PolicyAuthorityVersion | None = None


@dataclass(frozen=True)
class CorridorPublication:
    """Published diagnostics and post-publication shadow results."""

    audit_capsule: str | None = None
    audit_write_ms: float | None = None
    audit_error: str | None = None
    pipeline_survival_workspace_ms: float | None = None


@dataclass(frozen=True)
class CorridorRuntimeHandles:
    """Process-local objects that must never cross publication boundaries."""

    audit_future: Future[tuple[float, str | None]] | None = None
    pipeline_survival_workspace: PipelineSurvivalWorkspace | None = None
    future_hazard_projection: object | None = None
    current_pool_callback_join: object | None = None


@dataclass(frozen=True, init=False)
class CorridorSolution:
    """Compatibility view over separated artifact/publication/handle state."""

    artifact: CorridorPolicyArtifact
    publication: CorridorPublication
    handles: CorridorRuntimeHandles

    def __init__(
        self,
        source_frame: int | None = None,
        plan: CorridorPlan | None = None,
        solve_ms: float | None = None,
        snapshot_frame: int | None = None,
        forecast_lead_frames: int = 0,
        required_gate_lane: str | None = None,
        constraint_honored: bool = False,
        context_key: tuple[int, int, int | None] | None = None,
        audit_capsule: str | None = None,
        audit_write_ms: float | None = None,
        audit_error: str | None = None,
        worker_ms: float | None = None,
        audit_future: Future[tuple[float, str | None]] | None = None,
        pipeline_survival_workspace: (
            PipelineSurvivalWorkspace | None
        ) = None,
        future_hazard_projection: object | None = None,
        pipeline_survival_workspace_ms: float | None = None,
        background_priority_lowered: bool = False,
        native_viability_worker_limit: int | None = None,
        native_viability_worker_limit_applied: bool = False,
        time_scale_identity: tuple[object, ...] | None = None,
        future_hazard_version: VersionIdentity | None = None,
        future_hazard_coverage: HazardCoverageAssessment | None = None,
        current_pool_callback_join_version: VersionIdentity | None = None,
        current_pool_callback_join: object | None = None,
        authority_version: PolicyAuthorityVersion | None = None,
        *,
        artifact: CorridorPolicyArtifact | None = None,
        publication: CorridorPublication | None = None,
        handles: CorridorRuntimeHandles | None = None,
    ) -> None:
        if artifact is None:
            if source_frame is None or plan is None or solve_ms is None:
                raise TypeError(
                    "source_frame, plan, and solve_ms are required"
                )
            artifact = CorridorPolicyArtifact(
                source_frame=source_frame,
                plan=plan,
                solve_ms=solve_ms,
                snapshot_frame=snapshot_frame,
                forecast_lead_frames=forecast_lead_frames,
                required_gate_lane=required_gate_lane,
                constraint_honored=constraint_honored,
                context_key=context_key,
                worker_ms=worker_ms,
                background_priority_lowered=(
                    background_priority_lowered
                ),
                native_viability_worker_limit=(
                    native_viability_worker_limit
                ),
                native_viability_worker_limit_applied=(
                    native_viability_worker_limit_applied
                ),
                time_scale_identity=time_scale_identity,
                future_hazard_version=future_hazard_version,
                future_hazard_coverage=future_hazard_coverage,
                current_pool_callback_join_version=(
                    current_pool_callback_join_version
                ),
                authority_version=authority_version,
            )
            publication = CorridorPublication(
                audit_capsule=audit_capsule,
                audit_write_ms=audit_write_ms,
                audit_error=audit_error,
                pipeline_survival_workspace_ms=(
                    pipeline_survival_workspace_ms
                ),
            )
            handles = CorridorRuntimeHandles(
                audit_future=audit_future,
                pipeline_survival_workspace=(
                    pipeline_survival_workspace
                ),
                future_hazard_projection=future_hazard_projection,
                current_pool_callback_join=current_pool_callback_join,
            )
        else:
            if source_frame is not None or plan is not None or solve_ms is not None:
                raise TypeError(
                    "artifact cannot be combined with legacy core fields"
                )
            publication = publication or CorridorPublication()
            handles = handles or CorridorRuntimeHandles()
        object.__setattr__(self, "artifact", artifact)
        object.__setattr__(self, "publication", publication)
        object.__setattr__(self, "handles", handles)

    def with_publication(self, **changes: object) -> CorridorSolution:
        return CorridorSolution(
            artifact=self.artifact,
            publication=replace(self.publication, **changes),
            handles=self.handles,
        )

    def with_handles(self, **changes: object) -> CorridorSolution:
        return CorridorSolution(
            artifact=self.artifact,
            publication=self.publication,
            handles=replace(self.handles, **changes),
        )

    @property
    def source_frame(self) -> int:
        return self.artifact.source_frame

    @property
    def plan(self) -> CorridorPlan:
        return self.artifact.plan

    @property
    def solve_ms(self) -> float:
        return self.artifact.solve_ms

    @property
    def snapshot_frame(self) -> int | None:
        return self.artifact.snapshot_frame

    @property
    def time_scale_identity(self) -> tuple[object, ...] | None:
        return self.artifact.time_scale_identity

    @property
    def future_hazard_version(self) -> VersionIdentity | None:
        return self.artifact.future_hazard_version

    @property
    def future_hazard_coverage(self) -> HazardCoverageAssessment | None:
        return self.artifact.future_hazard_coverage

    @property
    def authority_version(self) -> PolicyAuthorityVersion | None:
        return self.artifact.authority_version

    @property
    def current_pool_callback_join_version(self) -> VersionIdentity | None:
        return self.artifact.current_pool_callback_join_version

    @property
    def future_hazard_projection(self) -> object | None:
        return self.handles.future_hazard_projection

    @property
    def current_pool_callback_join(self) -> object | None:
        return self.handles.current_pool_callback_join

    @property
    def forecast_lead_frames(self) -> int:
        return self.artifact.forecast_lead_frames

    @property
    def required_gate_lane(self) -> str | None:
        return self.artifact.required_gate_lane

    @property
    def constraint_honored(self) -> bool:
        return self.artifact.constraint_honored

    @property
    def context_key(self) -> tuple[int, int, int | None] | None:
        return self.artifact.context_key

    @property
    def audit_capsule(self) -> str | None:
        return self.publication.audit_capsule

    @property
    def audit_write_ms(self) -> float | None:
        return self.publication.audit_write_ms

    @property
    def audit_error(self) -> str | None:
        return self.publication.audit_error

    @property
    def worker_ms(self) -> float | None:
        return self.artifact.worker_ms

    @property
    def audit_future(
        self,
    ) -> Future[tuple[float, str | None]] | None:
        return self.handles.audit_future

    @property
    def pipeline_survival_workspace(
        self,
    ) -> PipelineSurvivalWorkspace | None:
        return self.handles.pipeline_survival_workspace

    @property
    def pipeline_survival_workspace_ms(self) -> float | None:
        return self.publication.pipeline_survival_workspace_ms

    @property
    def background_priority_lowered(self) -> bool:
        return self.artifact.background_priority_lowered

    @property
    def native_viability_worker_limit(self) -> int | None:
        return self.artifact.native_viability_worker_limit

    @property
    def native_viability_worker_limit_applied(self) -> bool:
        return self.artifact.native_viability_worker_limit_applied


__all__ = [
    "CorridorPolicyArtifact",
    "CorridorPublication",
    "CorridorRuntimeHandles",
    "CorridorSolution",
]
