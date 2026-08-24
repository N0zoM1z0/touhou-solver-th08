"""Planner proposal, certificate, issue, and telemetry value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LocalCertificateTiming:
    calls: int = 0
    explicit_root_calls: int = 0
    maximum_branch_count: int = 0
    shared_laser_projection_ms: float = 0.0
    validation_ms: float = 0.0
    hazard_projection_ms: float = 0.0
    branch_setup_ms: float = 0.0
    geometry_kernel_ms: float = 0.0
    reduction_ms: float = 0.0
    certificate_total_ms: float = 0.0
    control_prefix_ms: float = 0.0
    planning_bullet_projection_ms: float = 0.0
    beam_search_ms: float = 0.0
    terminal_threat_ms: float = 0.0
    selection_finalize_ms: float = 0.0


@dataclass(frozen=True)
class RobustActionCertificate:
    action: str
    delay_frames: tuple[int, ...]
    worst_collisions: int
    min_clearance: float
    cvar_risk: float
    worst_delay: int | None
    write_required: bool = True
    pipeline_branch_count: int = 0
    worst_pending_remaining: int | None = None


@dataclass(frozen=True)
class PlannerAction:
    name: str
    direction: int
    dx: float
    dy: float
    focused: bool


@dataclass(frozen=True)
class SearchNode:
    x: float
    y: float
    first_action: PlannerAction
    last_action: PlannerAction
    risk: float
    collisions: int
    min_clearance: float
    immediate_clearance: float
    collected_mask: int
    item_utility: float


@dataclass(frozen=True)
class ActionCertificateSet:
    certificates: tuple[RobustActionCertificate, ...] = ()

    def get(self, action: str) -> RobustActionCertificate | None:
        return next(
            (
                certificate
                for certificate in self.certificates
                if certificate.action == action
            ),
            None,
        )

    @property
    def safe_actions(self) -> tuple[str, ...]:
        return tuple(
            certificate.action
            for certificate in self.certificates
            if (
                certificate.worst_collisions == 0
                and certificate.min_clearance >= 0.0
            )
        )


@dataclass(frozen=True)
class IssueRecertification:
    """Auditable fresh/global action transaction at input issue."""

    planned_action: str
    global_allowed_actions: tuple[str, ...] | None
    global_constraint_applicable: bool
    fresh_safe_actions: tuple[str, ...]
    fresh_global_intersection: tuple[str, ...]
    selected_action: str
    selection_reason: str
    global_constraint_relaxed: bool
    planned_certificate: RobustActionCertificate | None
    selected_certificate: RobustActionCertificate
    preferred_action: str | None = None
    preference_reason: str | None = None
    preference_applied: bool = False
    allowed_action_authority: str | None = None
    fresh_action_set_complete: bool = True
    certificate_mode: str = "full"


@dataclass(frozen=True)
class Decision:
    """Flat compatibility view retained while consumers migrate."""

    mask: int
    action: str
    min_clearance: float
    immediate_clearance: float
    score: float
    bomb: bool
    item_utility: float = 0.0
    planned_focus: bool = True
    predicted_collections: tuple[int, ...] = ()
    pipeline_clearance: float = 9999.0
    robust_delay_frames: tuple[int, ...] = ()
    robust_override: bool = False
    robust_collisions: int = 0
    robust_min_clearance: float = 9999.0
    robust_cvar_risk: float = 0.0
    robust_worst_delay: int | None = None
    viability_constrained: bool = False
    viability_safe_action_count: int = 0
    viability_repair_volume: int = 0
    viability_constraint_relaxed: bool = False
    terminal_threat_horizon: int = 0
    terminal_threat_collisions: int = 0
    terminal_threat_min_clearance: float = 9999.0
    viability_recovery_distance: float | None = None
    viability_control_reserve_deficit: float = 0.0
    viability_safety_value_preferred: bool = False
    viability_safety_state_value: float | None = None
    viability_fresh_prefix_filtered: bool = False
    viability_fresh_prefix_relaxed: bool = False
    viability_survival_preferred: bool = False
    viability_survival_frames: int | None = None
    viability_survival_bottleneck_margin: float | None = None
    damage_objective_available: bool = False
    damage_baseline_action: str | None = None
    damage_shadow_action: str | None = None
    damage_current_alignment_cost: float | None = None
    damage_shadow_alignment_cost: float | None = None
    damage_eligible_action_count: int = 0
    damage_reason: str = "disabled"
    issue_action_certificates: tuple[RobustActionCertificate, ...] = ()
    local_certificate_timing: LocalCertificateTiming = (
        LocalCertificateTiming()
    )
    issue_certificate_timing: LocalCertificateTiming = (
        LocalCertificateTiming()
    )
    viability_control_reserve_valid: bool = True
    issue_recertification: IssueRecertification | None = None
    preloss_continuation_preference_active: bool = False
    planned_route_gate_deficit: float = 0.0
    preloss_historical_action: str | None = None
    preloss_historical_route_gate_deficit: float = 0.0
    local_collisions: int = 0


@dataclass(frozen=True)
class DecisionTelemetry:
    """Canonical hard fields and timing, independent of issue ownership."""

    planner_action: str
    planner_mask: int
    bomb: bool
    hard_vector: tuple[int | float | None, ...]
    local_certificate_timing: LocalCertificateTiming
    issue_certificate_timing: LocalCertificateTiming
    issue_recertification: IssueRecertification | None

    @classmethod
    def from_decision(cls, decision: Any) -> DecisionTelemetry:
        return cls(
            planner_action=decision.action,
            planner_mask=decision.mask,
            bomb=decision.bomb,
            hard_vector=(
                decision.robust_collisions,
                decision.robust_min_clearance,
                decision.terminal_threat_collisions,
                decision.terminal_threat_min_clearance,
                decision.local_collisions,
                decision.min_clearance,
                decision.immediate_clearance,
                decision.viability_control_reserve_valid,
            ),
            local_certificate_timing=decision.local_certificate_timing,
            issue_certificate_timing=decision.issue_certificate_timing,
            issue_recertification=decision.issue_recertification,
        )


@dataclass(frozen=True)
class LocalProposal:
    """Planner output before fresh issue-time sensing and certification."""

    decision: Any
    action_certificates: ActionCertificateSet
    telemetry: DecisionTelemetry

    @classmethod
    def from_decision(cls, decision: Any) -> LocalProposal:
        return cls(
            decision=decision,
            action_certificates=ActionCertificateSet(
                decision.issue_action_certificates
            ),
            telemetry=DecisionTelemetry.from_decision(decision),
        )


@dataclass(frozen=True)
class IssuedDecision:
    """Decision after the fresh/global issue transaction has committed."""

    decision: Any
    action_certificates: ActionCertificateSet
    telemetry: DecisionTelemetry
    transaction: IssueRecertification

    @classmethod
    def from_decision(cls, decision: Any) -> IssuedDecision:
        transaction = decision.issue_recertification
        if transaction is None:
            raise ValueError("issued decision requires transaction telemetry")
        return cls(
            decision=decision,
            action_certificates=ActionCertificateSet(
                decision.issue_action_certificates
            ),
            telemetry=DecisionTelemetry.from_decision(decision),
            transaction=transaction,
        )
