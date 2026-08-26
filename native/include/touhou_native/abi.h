#pragma once

#include <stdint.h>

#if defined(__cplusplus)
#define TOUHOU_ABI_EXTERN extern "C"
#else
#define TOUHOU_ABI_EXTERN extern
#endif

#if defined(_WIN32)
#define TOUHOU_ABI TOUHOU_ABI_EXTERN __declspec(dllexport)
#else
#define TOUHOU_ABI \
    TOUHOU_ABI_EXTERN __attribute__((visibility("default")))
#endif

typedef struct TouhouAsyncOrderedInputIssueQueryV1 {
    uint32_t struct_size;
    uint32_t active_mask;
    uint32_t held_desired_mask;
    const uint32_t* queued_masks;
    int32_t queued_mask_count;
    int32_t completion_remaining;
    uint32_t selected_mask;
    const int32_t* post_dispatch_delay_support;
    int32_t post_dispatch_delay_count;
    const int32_t* dispatch_callback_count_support;
    int32_t dispatch_callback_count;
    uint32_t supported_mask;
    uint32_t forbidden_mask;
} TouhouAsyncOrderedInputIssueQueryV1;

typedef struct TouhouAsyncOrderedInputIssueBranchV1 {
    uint32_t selected_mask;
    uint8_t write_required;
    uint8_t reserved_u8[3];
    int32_t older_remaining;
    int32_t new_delay;
    int32_t dispatch_history_offset;
    int32_t dispatch_history_count;
    uint32_t successor_active_mask;
    uint32_t successor_held_desired_mask;
    int32_t successor_queue_offset;
    int32_t successor_queue_count;
    int32_t successor_completion_remaining;
} TouhouAsyncOrderedInputIssueBranchV1;

typedef struct TouhouAsyncOrderedInputIssueOutputV1 {
    uint32_t struct_size;
    TouhouAsyncOrderedInputIssueBranchV1* branches;
    int32_t branch_capacity;
    uint32_t* active_masks_consumed_during_dispatch;
    uint32_t* publications_during_dispatch;
    int32_t dispatch_history_capacity;
    uint32_t* successor_queued_masks;
    int32_t successor_queue_capacity;
    int32_t* branch_count;
    int32_t* dispatch_history_count;
    int32_t* successor_queue_count;
} TouhouAsyncOrderedInputIssueOutputV1;

TOUHOU_ABI int touhou_async_ordered_input_issue_v1(
    const TouhouAsyncOrderedInputIssueQueryV1* query,
    TouhouAsyncOrderedInputIssueOutputV1* output
);

TOUHOU_ABI int touhou_clearance_volume_v1(
    float x_start,
    float x_step,
    int column_count,
    float y_start,
    float y_step,
    int row_count,
    int frame_count,
    float player_radius,
    float clearance_cap,
    const float* aabb_x,
    const float* aabb_y,
    const float* aabb_velocity_x,
    const float* aabb_velocity_y,
    const float* aabb_half_width,
    const float* aabb_half_height,
    const float* aabb_base_uncertainty,
    const float* aabb_uncertainty_per_frame,
    int aabb_count,
    const float* segment_origin_x,
    const float* segment_origin_y,
    const float* segment_angle,
    const float* segment_tail,
    const float* segment_head,
    const float* segment_half_width,
    const float* segment_base_uncertainty,
    const float* segment_uncertainty_per_frame,
    int segment_count,
    float* output
);

TOUHOU_ABI int touhou_segment_trajectory_clearance_v1(
    float x_start,
    float x_step,
    int column_count,
    float y_start,
    float y_step,
    int row_count,
    int frame_count,
    float player_radius,
    const int32_t* frame_offsets,
    const float* segment_origin_x,
    const float* segment_origin_y,
    const float* segment_angle,
    const float* segment_tail,
    const float* segment_head,
    const float* segment_half_width,
    const float* segment_base_uncertainty,
    const float* segment_uncertainty_per_frame,
    int segment_sample_count,
    float* inout
);

TOUHOU_ABI int touhou_aabb_trajectory_clearance_v1(
    float x_start,
    float x_step,
    int column_count,
    float y_start,
    float y_step,
    int row_count,
    int frame_count,
    float player_radius,
    const int32_t* frame_offsets,
    const float* aabb_x,
    const float* aabb_y,
    const float* aabb_half_width,
    const float* aabb_half_height,
    const float* aabb_base_uncertainty,
    const float* aabb_uncertainty_per_frame,
    int aabb_sample_count,
    float* inout
);

TOUHOU_ABI int touhou_annular_sector_trajectory_clearance_v1(
    float x_start,
    float x_step,
    int column_count,
    float y_start,
    float y_step,
    int row_count,
    int frame_count,
    float player_radius,
    const int32_t* frame_offsets,
    const double* origin_x,
    const double* origin_y,
    const double* minimum_angle,
    const double* maximum_angle,
    const double* minimum_radius,
    const double* maximum_radius,
    const double* half_extent_radius,
    const double* origin_uncertainty,
    const double* base_uncertainty,
    const double* uncertainty_per_frame,
    int sample_count,
    float* inout
);

TOUHOU_ABI int touhou_annular_sector_frame_clearance_v1(
    const float* positions_x,
    const float* positions_y,
    int position_count,
    int frame,
    float player_radius,
    const double* origin_x,
    const double* origin_y,
    const double* minimum_angle,
    const double* maximum_angle,
    const double* minimum_radius,
    const double* maximum_radius,
    const double* half_extent_radius,
    const double* origin_uncertainty,
    const double* base_uncertainty,
    const double* uncertainty_per_frame,
    int sample_count,
    float* output
);

TOUHOU_ABI int touhou_piecewise_aabb_clearance_v1(
    float x_start,
    float x_step,
    int column_count,
    float y_start,
    float y_step,
    int row_count,
    int frame_count,
    float player_radius,
    const double* aabb_x,
    const double* aabb_y,
    const double* aabb_velocity_x,
    const double* aabb_velocity_y,
    const float* aabb_half_width,
    const float* aabb_half_height,
    const float* aabb_base_uncertainty,
    const float* aabb_uncertainty_per_frame,
    int aabb_count,
    const int32_t* event_offsets,
    const int32_t* event_frames,
    const double* event_velocity_x,
    const double* event_velocity_y,
    int event_count,
    float* inout
);

TOUHOU_ABI int touhou_local_hazards_v1(
    const float* positions_x,
    const float* positions_y,
    int position_count,
    int step,
    float player_radius,
    const float* bullet_x,
    const float* bullet_y,
    const float* bullet_half_width,
    const float* bullet_half_height,
    const uint8_t* bullet_transformed,
    int bullet_count,
    const float* laser_start_x,
    const float* laser_start_y,
    const float* laser_segment_x,
    const float* laser_segment_y,
    const float* laser_collision_radius,
    const float* laser_base_uncertainty,
    const float* laser_uncertainty_per_frame,
    int laser_count,
    const float* body_x,
    const float* body_y,
    const float* body_half_width,
    const float* body_half_height,
    int body_count,
    double* output_risk,
    int32_t* output_collisions,
    double* output_minimum
);

TOUHOU_ABI int touhou_decode_bullet_pool_v1(
    const uint8_t* blob,
    uint64_t blob_size,
    int record_count,
    int stride,
    int state_offset,
    int geometry_offset,
    int position_offset,
    int velocity_offset,
    int speed_offset,
    int angle_offset,
    int transform_flags_offset,
    int original_transform_flags_offset,
    int callback_phase_offset,
    int callback_aux_offset,
    float* output_x,
    float* output_y,
    float* output_velocity_x,
    float* output_velocity_y,
    float* output_half_width,
    float* output_half_height,
    uint32_t* output_transform_flags,
    int32_t* output_slots,
    float* output_speed,
    float* output_angle,
    int16_t* output_callback_phase,
    uint8_t* output_callback_aux,
    uint32_t* output_original_transform_flags,
    int output_capacity,
    int32_t* output_count
);

TOUHOU_ABI int touhou_local_beam_reduce_v2(
    const double* draft_x,
    const double* draft_y,
    const int32_t* first_action,
    const int32_t* last_direction,
    const uint8_t* last_focused,
    const uint32_t* collected_mask,
    const double* risk,
    const int32_t* collisions,
    const double* minimum_clearance,
    int draft_count,
    int step,
    int beam_width,
    double position_quantization,
    int target_enabled,
    double target_x,
    double target_y,
    int target_deadline,
    double item_safety_clearance,
    double playfield_left,
    double playfield_right,
    double playfield_top,
    double playfield_bottom,
    double reserve_distance,
    double diagonal_speed,
    double cardinal_speed,
    const int32_t* certificate_collisions,
    const double* certificate_minimum,
    const uint8_t* survival_preferred,
    const uint8_t* safety_preferred,
    const double* recovery_distance,
    int action_count,
    int preserve_first_action_strata,
    int32_t* output_indices,
    int32_t* output_count
);

TOUHOU_ABI int touhou_local_beam_reduce_v1(
    const double* draft_x,
    const double* draft_y,
    const int32_t* first_action,
    const int32_t* last_direction,
    const uint8_t* last_focused,
    const uint32_t* collected_mask,
    const double* risk,
    const int32_t* collisions,
    const double* minimum_clearance,
    int draft_count,
    int step,
    int beam_width,
    double position_quantization,
    int target_enabled,
    double target_x,
    double target_y,
    int target_deadline,
    double item_safety_clearance,
    double playfield_left,
    double playfield_right,
    double playfield_top,
    double playfield_bottom,
    double reserve_distance,
    double diagonal_speed,
    double cardinal_speed,
    const int32_t* certificate_collisions,
    const double* certificate_minimum,
    const uint8_t* survival_preferred,
    const uint8_t* safety_preferred,
    const double* recovery_distance,
    int action_count,
    int32_t* output_indices,
    int32_t* output_count
);

TOUHOU_ABI int touhou_pipeline_survival_workspace_create_v2(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    const int* decision_frame_support,
    int decision_frame_count,
    int continuation_decision_frames,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_pipeline_survival_workspace_create_v1(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    int decision_frames,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_pipeline_survival_workspace_query_v1(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    uint16_t* output_state_frames,
    float* output_state_margin,
    uint16_t* output_action_frames,
    float* output_action_margins,
    uint32_t* output_best_action_mask,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_pipeline_survival_workspace_contains_root_v1(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int* output_present
);

TOUHOU_ABI int touhou_pipeline_survival_workspace_query_v2(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int timeout_ms,
    uint16_t* output_state_frames,
    float* output_state_margin,
    uint16_t* output_action_frames,
    float* output_action_margins,
    uint32_t* output_best_action_mask,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_pipeline_survival_workspace_prewarm_continuation_v1(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int timeout_ms,
    uint16_t* output_frames,
    float* output_margin,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_pipeline_survival_workspace_merge_continuation_v1(
    void* destination_workspace,
    void* source_workspace,
    uint64_t* output_added_states
);

TOUHOU_ABI int touhou_pipeline_survival_workspace_cancel_v1(
    void* workspace
);

TOUHOU_ABI void touhou_pipeline_survival_workspace_destroy_v1(
    void* workspace
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_create_v7(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    uint64_t base_action_mask,
    uint64_t budgeted_action_mask,
    int continuation_budget,
    int remaining_delay_bucket_size,
    int continuation_policy_mode,
    const int* delay_frames,
    int delay_count,
    const int* cadence_frames,
    int cadence_count,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_create_v8(
    const float* clearance,
    const float* terminal_state_margins,
    const float* terminal_action_margins,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    uint64_t base_action_mask,
    uint64_t budgeted_action_mask,
    int continuation_budget,
    int remaining_delay_bucket_size,
    int continuation_policy_mode,
    const int* delay_frames,
    int delay_count,
    const int* cadence_frames,
    int cadence_count,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_create_v6(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    uint32_t base_action_mask,
    uint32_t budgeted_action_mask,
    int continuation_budget,
    int remaining_delay_bucket_size,
    int continuation_policy_mode,
    const int* delay_frames,
    int delay_count,
    const int* cadence_frames,
    int cadence_count,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_create_v5(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    uint32_t base_action_mask,
    uint32_t budgeted_action_mask,
    int continuation_budget,
    int reveal_remaining_delay,
    int continuation_policy_mode,
    const int* delay_frames,
    int delay_count,
    const int* cadence_frames,
    int cadence_count,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_create_v4(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    uint32_t base_action_mask,
    uint32_t budgeted_action_mask,
    int continuation_budget,
    int reveal_remaining_delay,
    const int* delay_frames,
    int delay_count,
    const int* cadence_frames,
    int cadence_count,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_create_v3(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    uint32_t base_action_mask,
    uint32_t budgeted_action_mask,
    int continuation_budget,
    const int* delay_frames,
    int delay_count,
    const int* cadence_frames,
    int cadence_count,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_create_v2(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    uint32_t continuation_action_mask,
    const int* delay_frames,
    int delay_count,
    const int* cadence_frames,
    int cadence_count,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_create_v1(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    const int* cadence_frames,
    int cadence_count,
    float required_clearance,
    int clamp_to_bounds,
    void** output_workspace
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_query_v3(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int continuation_action_budget,
    int timeout_ms,
    uint16_t* output_state_frames,
    float* output_state_margin,
    uint16_t* output_action_frames,
    float* output_action_margins,
    uint64_t* output_best_action_mask,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_query_v2(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int continuation_action_budget,
    int timeout_ms,
    uint16_t* output_state_frames,
    float* output_state_margin,
    uint16_t* output_action_frames,
    float* output_action_margins,
    uint32_t* output_best_action_mask,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_query_v1(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int timeout_ms,
    uint16_t* output_state_frames,
    float* output_state_margin,
    uint16_t* output_action_frames,
    float* output_action_margins,
    uint32_t* output_best_action_mask,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_certify_upper_v3(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int continuation_action_budget,
    uint16_t lower_frames,
    float lower_margin,
    int timeout_ms,
    uint64_t* output_unresolved_action_mask,
    int* output_deadline_expired,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_certify_exact_v1(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int continuation_action_budget,
    uint16_t target_frames,
    float target_margin,
    int timeout_ms,
    uint64_t* output_winning_action_mask,
    uint64_t* output_unresolved_action_mask,
    int* output_deadline_expired,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_certify_upper_v2(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int continuation_action_budget,
    uint16_t lower_frames,
    float lower_margin,
    int timeout_ms,
    uint32_t* output_unresolved_action_mask,
    int* output_deadline_expired,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_certify_upper_v1(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int continuation_action_budget,
    uint16_t lower_frames,
    float lower_margin,
    int timeout_ms,
    uint32_t* output_unresolved_action_mask,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_recommend_action_column_v1(
    void* workspace,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    int target_root_action,
    int max_depth,
    int timeout_ms,
    int* output_recommended_action,
    int* output_witness_frame,
    int* output_witness_row,
    int* output_witness_column,
    int* output_witness_active,
    int* output_witness_pending,
    uint64_t* output_witness_remaining_mask,
    uint16_t* output_current_frames,
    float* output_current_margin,
    uint16_t* output_recommended_frames,
    float* output_recommended_margin,
    int* output_depth,
    uint64_t* output_stats
);

TOUHOU_ABI int touhou_belief_pipeline_workspace_cancel_v1(
    void* workspace
);

TOUHOU_ABI void touhou_belief_pipeline_workspace_destroy_v1(
    void* workspace
);

TOUHOU_ABI int touhou_query_local_survival_v1(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    int decision_frames,
    float required_clearance,
    int clamp_to_bounds,
    int start_frame,
    int start_row,
    int start_column,
    int observed_action,
    int pending_action,
    const int* pending_remaining_frames,
    int pending_remaining_count,
    uint16_t* output_state_frames,
    float* output_state_margin,
    uint16_t* output_action_frames,
    float* output_action_margins,
    uint32_t* output_best_action_mask,
    uint64_t* output_evaluated_state_count
);

TOUHOU_ABI int touhou_set_current_thread_viability_worker_limit_v1(
    int worker_limit
);

TOUHOU_ABI int touhou_robust_viability_v1(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    int frames_per_layer,
    float required_clearance,
    int clamp_to_bounds,
    uint8_t* viable,
    uint32_t* safe_action_masks
);

TOUHOU_ABI int touhou_robust_viability_terminal_v1(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    int frames_per_layer,
    float required_clearance,
    int clamp_to_bounds,
    const uint8_t* terminal_viable,
    uint8_t* viable,
    uint32_t* safe_action_masks
);

TOUHOU_ABI int touhou_robust_safety_value_v1(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    int frames_per_layer,
    int clamp_to_bounds,
    float* state_values,
    float* action_values
);

TOUHOU_ABI int touhou_robust_safety_policy_v1(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    int frames_per_layer,
    int clamp_to_bounds,
    float* state_values,
    uint32_t* best_action_masks
);

TOUHOU_ABI int touhou_robust_survival_viability_v1(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    int frames_per_layer,
    float required_clearance,
    int clamp_to_bounds,
    uint16_t* state_survival_frames,
    float* state_bottleneck_margins,
    uint32_t* best_action_masks,
    uint8_t* viable,
    uint32_t* safe_action_masks
);

TOUHOU_ABI int touhou_losing_survival_labels_v1(
    const float* clearance,
    int frame_count,
    int row_count,
    int column_count,
    double x_start,
    double x_step,
    double y_start,
    double y_step,
    const double* velocity_x,
    const double* velocity_y,
    int action_count,
    const int* delay_frames,
    int delay_count,
    int frames_per_layer,
    float required_clearance,
    int clamp_to_bounds,
    int requested_worker_count,
    const uint8_t* viable,
    const uint32_t* safe_action_masks,
    uint16_t* state_survival_frames,
    float* state_bottleneck_margins,
    uint32_t* best_action_masks
);
