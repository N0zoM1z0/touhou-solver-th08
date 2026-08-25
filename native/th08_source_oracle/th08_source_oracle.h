#ifndef TH08_SOURCE_ORACLE_H
#define TH08_SOURCE_ORACLE_H

#include <stdint.h>

#if defined(_WIN32)
#define TH08_ORACLE_API __declspec(dllexport)
#else
#define TH08_ORACLE_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Small, dependency-free source oracle for offline differential testing.
 *
 * This is intentionally not linked to the solver's native planner.  The
 * implementation is an isolated transcription of the recovered TH08 source
 * functions named in README.md so Python and optimized solver code cannot
 * silently share the same implementation error.
 */

typedef struct Th08OracleRng {
    uint16_t state;
    uint16_t reserved;
    uint32_t calls;
} Th08OracleRng;

typedef struct Th08OraclePattern {
    int32_t mode;
    int32_t count1;
    int32_t count2;
    float speed1;
    float speed2;
    float angle;
    float angle_step;
    float angle_to_player;
    float time_scale;
} Th08OraclePattern;

typedef struct Th08OraclePatternSample {
    float speed;
    float angle;
    float velocity_x;
    float velocity_y;
} Th08OraclePatternSample;

typedef struct Th08OracleSpawnLifecycleSample {
    int32_t state;
    int32_t lethal_active;
    int32_t terminal_age;
    float motion_divisor;
    float x;
    float y;
} Th08OracleSpawnLifecycleSample;

typedef struct Th08OracleEnemySpawnInput {
    int32_t opcode;
    float operand_x;
    float operand_y;
    float parent_base_x;
    float parent_base_y;
    float parent_world_x;
    float parent_world_y;
    float template_relative_x;
    float template_relative_y;
    uint32_t template_flags;
    uint32_t parent_flags;
    int32_t parent_hitpoints;
    int32_t player_is_youkais;
    int32_t pool_available;
    int32_t bootstrap_succeeded;
    float bootstrap_base_x;
    float bootstrap_base_y;
    float bootstrap_relative_x;
    float bootstrap_relative_y;
    float bootstrap_world_x;
    float bootstrap_world_y;
    uint32_t bootstrap_flags;
} Th08OracleEnemySpawnInput;

typedef struct Th08OracleEnemySpawnSample {
    int32_t constructor_admitted;
    int32_t spawned;
    int32_t linked_child;
    int32_t follow_parent_base;
    float constructor_base_x;
    float constructor_base_y;
    float constructor_world_x;
    float constructor_world_y;
    uint32_t constructor_flags;
    float post_link_base_x;
    float post_link_base_y;
    float post_link_relative_x;
    float post_link_relative_y;
    float post_link_world_x;
    float post_link_world_y;
    uint32_t post_link_flags;
} Th08OracleEnemySpawnSample;

typedef struct Th08OracleCallback12State {
    int16_t phase_state;
    uint8_t collision_aux;
    uint8_t reserved;
    uint32_t presentation_flags;
    int32_t animation_index;
    float base_speed;
    float base_angle;
    float velocity_x;
    float velocity_y;
} Th08OracleCallback12State;

typedef struct Th08OracleTransformState {
    float x;
    float y;
    float half_width;
    float half_height;
    float velocity_x;
    float velocity_y;
    float base_speed;
    float base_angle;
    float parameter_0;
    float parameter_1;
    float restored_speed;
    float acceleration_x;
    float acceleration_y;
    int32_t timer;
    int32_t duration;
    int32_t repeat_limit;
    int32_t repeat_count;
    int32_t active;
} Th08OracleTransformState;

TH08_ORACLE_API uint16_t th08_oracle_rng_next_u16(Th08OracleRng *rng);
TH08_ORACLE_API uint32_t th08_oracle_rng_next_u32(Th08OracleRng *rng);
TH08_ORACLE_API float th08_oracle_rng_next_f32(Th08OracleRng *rng);

TH08_ORACLE_API int32_t th08_oracle_pattern_sample(
    const Th08OraclePattern *pattern,
    int32_t bullet_index,
    int32_t ring_index,
    Th08OracleRng *rng,
    Th08OraclePatternSample *sample);

TH08_ORACLE_API int32_t th08_oracle_spawn_lifecycle_sample(
    int32_t bullet_type,
    uint32_t original_flags,
    int32_t age,
    float origin_x,
    float origin_y,
    float velocity_x,
    float velocity_y,
    Th08OracleSpawnLifecycleSample *sample);

TH08_ORACLE_API int32_t th08_oracle_enemy_spawn_sample(
    const Th08OracleEnemySpawnInput *input,
    Th08OracleEnemySpawnSample *sample);

TH08_ORACLE_API int32_t th08_oracle_callback12(
    Th08OracleCallback12State *state,
    uint32_t bullet_tags,
    uint32_t selected_tags,
    float callback_angle,
    float callback_speed,
    float time_scale);

TH08_ORACLE_API int32_t th08_oracle_callback14(
    Th08OracleCallback12State *state,
    uint32_t bullet_tags,
    uint32_t selected_tags,
    float callback_speed,
    float time_scale);

TH08_ORACLE_API int32_t th08_oracle_aabb_overlap(
    float player_x,
    float player_y,
    float player_half_width,
    float player_half_height,
    float hazard_x,
    float hazard_y,
    float hazard_half_width,
    float hazard_half_height);

TH08_ORACLE_API int32_t th08_oracle_transform_step(
    uint32_t kind,
    Th08OracleTransformState *state,
    float player_x,
    float player_y,
    float time_scale);

#ifdef __cplusplus
}
#endif

#endif
