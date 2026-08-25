#include "th08_source_oracle.h"

#include <math.h>
#include <stddef.h>
#include <stdint.h>

/* Binary32 constants emitted by the recovered source. */
static const float TH08_PI = 3.1415927410125732421875F;
static const float TH08_TWO_PI = 6.283185482025146484375F;

static float th08_normalize_angle(float a, float b) {
    int32_t i = 0;
    a += b;
    while (a > TH08_PI) {
        a -= TH08_TWO_PI;
        if (i++ > 16) {
            break;
        }
    }
    while (a < -TH08_PI) {
        a += TH08_TWO_PI;
        if (i++ > 16) {
            break;
        }
    }
    return a;
}

uint16_t th08_oracle_rng_next_u16(Th08OracleRng *rng) {
    uint16_t mixed;
    if (rng == NULL) {
        return 0;
    }
    mixed = (uint16_t)((rng->state ^ UINT16_C(0x9630)) -
                       UINT16_C(0x6553));
    rng->state = (uint16_t)((((uint32_t)mixed & UINT32_C(0xc000)) >> 14) +
                            (uint32_t)mixed * 4U);
    rng->calls += 1U;
    return rng->state;
}

uint32_t th08_oracle_rng_next_u32(Th08OracleRng *rng) {
    uint32_t high = (uint32_t)th08_oracle_rng_next_u16(rng);
    uint32_t low = (uint32_t)th08_oracle_rng_next_u16(rng);
    return (high << 16) | low;
}

float th08_oracle_rng_next_f32(Th08OracleRng *rng) {
    /* Global.cpp: both casts happen before the binary32 division. */
    return (float)th08_oracle_rng_next_u32(rng) / (float)UINT32_MAX;
}

static float th08_random_range(Th08OracleRng *rng, float span) {
    return th08_oracle_rng_next_f32(rng) * span;
}

int32_t th08_oracle_pattern_sample(
    const Th08OraclePattern *pattern,
    int32_t bullet_index,
    int32_t ring_index,
    Th08OracleRng *rng,
    Th08OraclePatternSample *sample) {
    float angle = 0.0F;
    float speed;
    if (pattern == NULL || sample == NULL || pattern->count1 <= 0 ||
        pattern->count2 <= 0 || pattern->mode < 0 || pattern->mode > 8 ||
        bullet_index < 0 || bullet_index >= pattern->count1 ||
        ring_index < 0 || ring_index >= pattern->count2 ||
        ((pattern->mode == 6 || pattern->mode == 7 || pattern->mode == 8) &&
         rng == NULL)) {
        return 1;
    }

    if (pattern->count2 > 1) {
        speed = pattern->speed1 -
                (pattern->speed1 - pattern->speed2) *
                    (float)ring_index / (float)pattern->count2;
    } else {
        speed = pattern->speed1;
    }

    switch (pattern->mode) {
    case 0:
    case 1:
        if ((pattern->count1 & 1) != 0) {
            angle += (float)((bullet_index + 1) / 2) * pattern->angle_step;
        } else {
            angle += (float)(bullet_index / 2) * pattern->angle_step +
                     pattern->angle_step * 0.5F;
        }
        if ((bullet_index & 1) != 0) {
            angle *= -1.0F;
        }
        if (pattern->mode == 0) {
            angle += pattern->angle_to_player;
        }
        angle += pattern->angle;
        break;
    case 2:
        angle += pattern->angle_to_player;
        /* fall through */
    case 3:
        angle += (float)bullet_index * TH08_TWO_PI /
                 (float)pattern->count1;
        angle += (float)ring_index * pattern->angle_step + pattern->angle;
        break;
    case 4:
        angle += pattern->angle_to_player;
        /* fall through */
    case 5:
        angle += TH08_PI / (float)pattern->count1;
        angle += (float)bullet_index * TH08_TWO_PI /
                 (float)pattern->count1;
        angle += pattern->angle;
        break;
    case 6:
        angle = th08_random_range(
                    rng, pattern->angle - pattern->angle_step) +
                pattern->angle_step;
        break;
    case 7:
        speed = th08_random_range(
                    rng, pattern->speed1 - pattern->speed2) +
                pattern->speed2;
        angle += (float)bullet_index * TH08_TWO_PI /
                 (float)pattern->count1;
        angle += (float)ring_index * pattern->angle_step + pattern->angle;
        break;
    case 8:
        angle = th08_random_range(
                    rng, pattern->angle - pattern->angle_step) +
                pattern->angle_step;
        speed = th08_random_range(
                    rng, pattern->speed1 - pattern->speed2) +
                pattern->speed2;
        break;
    default:
        return 1;
    }

    sample->speed = speed;
    sample->angle = th08_normalize_angle(angle, 0.0F);
    sample->velocity_x = cosf(angle) * speed * pattern->time_scale;
    sample->velocity_y = sinf(angle) * speed * pattern->time_scale;
    return 0;
}

static const int32_t TH08_STATE2_TERMINAL_AGES[21] = {
    10, 10, 10, 10, 10, 10, 10, 30, 30, 30, 24,
    10, 10, 10, 30, 30, 10, 10, 30, 30, 30,
};

static const int32_t TH08_STATE3_TERMINAL_AGES[21] = {
    15, 15, 15, 15, 15, 15, 15, 30, 30, 30, 24,
    15, 15, 15, 30, 30, 15, 15, 30, 30, 30,
};

static const int32_t TH08_STATE4_TERMINAL_AGES[21] = {
    30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 24,
    30, 30, 30, 30, 30, 30, 30, 30, 30, 30,
};

int32_t th08_oracle_spawn_lifecycle_sample(
    int32_t bullet_type,
    uint32_t original_flags,
    int32_t age,
    float origin_x,
    float origin_y,
    float velocity_x,
    float velocity_y,
    Th08OracleSpawnLifecycleSample *sample) {
    const int32_t *terminal_ages = NULL;
    int32_t state = 1;
    int32_t terminal_age = 0;
    float divisor = 1.0F;
    float x = origin_x;
    float y = origin_y;
    int32_t update;

    if (sample == NULL || bullet_type < 0 || bullet_type >= 21 || age <= 0) {
        return 1;
    }
    if ((original_flags & UINT32_C(0x02)) != 0U) {
        state = 2;
        divisor = 2.0F;
        terminal_ages = TH08_STATE2_TERMINAL_AGES;
    } else if ((original_flags & UINT32_C(0x04)) != 0U) {
        state = 3;
        divisor = 2.5F;
        terminal_ages = TH08_STATE3_TERMINAL_AGES;
    } else if ((original_flags & UINT32_C(0x08)) != 0U) {
        state = 4;
        divisor = 3.0F;
        terminal_ages = TH08_STATE4_TERMINAL_AGES;
    }
    if (terminal_ages != NULL) {
        terminal_age = terminal_ages[bullet_type];
        x -= velocity_x * 4.0F;
        y -= velocity_y * 4.0F;
    }
    for (update = 1; update <= age; ++update) {
        if (state == 1) {
            x += velocity_x;
            y += velocity_y;
            continue;
        }
        x += velocity_x / divisor;
        y += velocity_y / divisor;
        if (update == terminal_age) {
            state = 1;
            x += velocity_x;
            y += velocity_y;
        }
    }
    sample->state = state;
    sample->lethal_active = state == 1;
    sample->terminal_age = terminal_age;
    sample->motion_divisor = divisor;
    sample->x = x;
    sample->y = y;
    return 0;
}

/*
 * EnemyTimeline.cpp::SpawnEnemy2, EclDependencies.cpp constructors, and
 * EclRunLow/High.inl cases 90..94.  The bootstrap state is an input because
 * SpawnEnemy2 executes arbitrary child ECL synchronously before cases 90..92
 * perform their linked-child mutations.
 */
int32_t th08_oracle_enemy_spawn_sample(
    const Th08OracleEnemySpawnInput *input,
    Th08OracleEnemySpawnSample *sample) {
    int32_t add_parent_world;
    int32_t linked_child;
    int32_t follow_parent_base;
    int32_t requires_clear_suppress_death_effects;
    float constructor_base_x;
    float constructor_base_y;
    float post_relative_x;
    float post_relative_y;
    uint32_t post_flags;

    if (input == NULL || sample == NULL) {
        return 1;
    }
    switch (input->opcode) {
    case 0x5a:
        add_parent_world = 0;
        linked_child = 1;
        follow_parent_base = 0;
        requires_clear_suppress_death_effects = 1;
        break;
    case 0x5b:
        add_parent_world = 1;
        linked_child = 1;
        follow_parent_base = 0;
        requires_clear_suppress_death_effects = 1;
        break;
    case 0x5c:
        add_parent_world = 0;
        linked_child = 1;
        follow_parent_base = 1;
        requires_clear_suppress_death_effects = 1;
        break;
    case 0x5d:
        add_parent_world = 0;
        linked_child = 0;
        follow_parent_base = 0;
        requires_clear_suppress_death_effects = 0;
        break;
    case 0x5e:
        add_parent_world = 1;
        linked_child = 0;
        follow_parent_base = 0;
        requires_clear_suppress_death_effects = 0;
        break;
    default:
        return 1;
    }

    constructor_base_x = input->operand_x;
    constructor_base_y = input->operand_y;
    if (add_parent_world) {
        constructor_base_x = constructor_base_x + input->parent_world_x;
        constructor_base_y = constructor_base_y + input->parent_world_y;
    }
    sample->constructor_admitted =
        input->pool_available && input->parent_hitpoints > 0;
    if (requires_clear_suppress_death_effects &&
        (input->parent_flags & (UINT32_C(1) << 10))) {
        sample->constructor_admitted = 0;
    }
    sample->spawned =
        sample->constructor_admitted && input->bootstrap_succeeded;
    sample->linked_child = sample->spawned && linked_child;
    sample->follow_parent_base =
        sample->spawned && linked_child && follow_parent_base;
    sample->constructor_base_x = constructor_base_x;
    sample->constructor_base_y = constructor_base_y;
    sample->constructor_world_x =
        constructor_base_x + input->template_relative_x;
    sample->constructor_world_y =
        constructor_base_y + input->template_relative_y;
    sample->constructor_flags = input->template_flags;

    sample->post_link_base_x = input->bootstrap_base_x;
    sample->post_link_base_y = input->bootstrap_base_y;
    post_relative_x = input->bootstrap_relative_x;
    post_relative_y = input->bootstrap_relative_y;
    sample->post_link_world_x = input->bootstrap_world_x;
    sample->post_link_world_y = input->bootstrap_world_y;
    post_flags = input->bootstrap_flags;
    if (sample->spawned && linked_child) {
        post_flags |= UINT32_C(1) << 8;
        post_flags &= ~(UINT32_C(1) << 2);
        if (input->player_is_youkais) {
            post_flags |= UINT32_C(1) << 11;
        } else {
            post_flags &= ~(UINT32_C(1) << 11);
        }
        if (follow_parent_base) {
            post_relative_x = input->parent_base_x;
            post_relative_y = input->parent_base_y;
            sample->post_link_world_x =
                post_relative_x + input->bootstrap_base_x;
            sample->post_link_world_y =
                post_relative_y + input->bootstrap_base_y;
            post_flags |= UINT32_C(1) << 9;
        }
    }
    sample->post_link_relative_x = post_relative_x;
    sample->post_link_relative_y = post_relative_y;
    sample->post_link_flags = post_flags;
    return 0;
}

int32_t th08_oracle_callback12(
    Th08OracleCallback12State *state,
    uint32_t bullet_tags,
    uint32_t selected_tags,
    float callback_angle,
    float callback_speed,
    float time_scale) {
    float angle;
    float speed;
    if (state == NULL || (bullet_tags & selected_tags) == 0U) {
        return 0;
    }
    if (state->phase_state == 1) {
        state->phase_state = 0;
        state->presentation_flags =
            (state->presentation_flags & UINT32_C(0xffffffcf)) |
            UINT32_C(0x10);
        state->animation_index += 16;
        state->collision_aux = 1;
        angle = callback_angle;
        speed = callback_speed * time_scale;
    } else {
        state->phase_state = 1;
        state->presentation_flags &= UINT32_C(0xffffffcf);
        state->animation_index -= 16;
        state->collision_aux = 0;
        angle = state->base_angle;
        speed = state->base_speed * time_scale;
    }
    state->velocity_x = cosf(angle) * speed;
    state->velocity_y = sinf(angle) * speed;
    return 1;
}

int32_t th08_oracle_callback14(
    Th08OracleCallback12State *state,
    uint32_t bullet_tags,
    uint32_t selected_tags,
    float callback_speed,
    float time_scale) {
    float speed;
    if (state == NULL || (bullet_tags & selected_tags) == 0U) {
        return 0;
    }
    if (state->phase_state == 1) {
        state->phase_state = 0;
        state->presentation_flags =
            (state->presentation_flags & UINT32_C(0xffffffcf)) |
            UINT32_C(0x10);
        state->animation_index += 16;
        state->collision_aux = 1;
        speed = callback_speed * time_scale;
        state->velocity_x = cosf(state->base_angle) * speed;
        state->velocity_y = sinf(state->base_angle) * speed;
    } else if (state->phase_state == 0) {
        state->phase_state = 2;
    } else {
        state->phase_state = 1;
        state->presentation_flags &= UINT32_C(0xffffffcf);
        state->animation_index -= 16;
        state->collision_aux = 0;
        speed = state->base_speed * time_scale;
        state->velocity_x = cosf(state->base_angle) * speed;
        state->velocity_y = sinf(state->base_angle) * speed;
    }
    return 1;
}

int32_t th08_oracle_aabb_overlap(
    float player_x,
    float player_y,
    float player_half_width,
    float player_half_height,
    float hazard_x,
    float hazard_y,
    float hazard_half_width,
    float hazard_half_height) {
    return player_x - player_half_width <= hazard_x + hazard_half_width &&
           player_x + player_half_width >= hazard_x - hazard_half_width &&
           player_y - player_half_height <= hazard_y + hazard_half_height &&
           player_y + player_half_height >= hazard_y - hazard_half_height;
}

static void th08_polar(
    float angle,
    float magnitude,
    float *velocity_x,
    float *velocity_y) {
    *velocity_x = cosf(angle) * magnitude;
    *velocity_y = sinf(angle) * magnitude;
}

static int32_t th08_transform_inside(
    const Th08OracleTransformState *state) {
    return !(state->x + state->half_width < 0.0F ||
             state->x - state->half_width > 384.0F ||
             state->y + state->half_height < 0.0F ||
             state->y - state->half_height > 448.0F);
}

int32_t th08_oracle_transform_step(
    uint32_t kind,
    Th08OracleTransformState *state,
    float player_x,
    float player_y,
    float time_scale) {
    float magnitude;
    if (state == NULL || state->active == 0) {
        return 0;
    }
    switch (kind) {
    case UINT32_C(0x1):
        if (state->timer <= 16) {
            magnitude =
                5.0F - ((float)state->timer * 5.0F) / 16.0F;
            th08_polar(
                state->base_angle,
                (magnitude + state->base_speed) * time_scale,
                &state->velocity_x,
                &state->velocity_y);
        } else {
            state->active = 0;
        }
        state->timer += 1;
        break;
    case UINT32_C(0x10):
        if (state->timer >= state->duration) {
            state->active = 0;
        } else {
            state->velocity_x += state->acceleration_x * time_scale;
            state->velocity_y += state->acceleration_y * time_scale;
            if (fabsf(state->velocity_x) > 0.0001F ||
                fabsf(state->velocity_y) > 0.0001F) {
                state->base_angle = atan2f(
                    state->velocity_y,
                    state->velocity_x);
            }
        }
        state->timer += 1;
        break;
    case UINT32_C(0x20):
        if (state->timer >= state->duration) {
            state->active = 0;
        } else {
            state->base_angle = th08_normalize_angle(
                state->base_angle,
                time_scale * state->parameter_1);
            state->base_speed += time_scale * state->parameter_0;
            th08_polar(
                state->base_angle,
                time_scale * state->base_speed,
                &state->velocity_x,
                &state->velocity_y);
        }
        state->timer += 1;
        break;
    case UINT32_C(0x40):
    case UINT32_C(0x80):
    case UINT32_C(0x100):
        if (state->timer >= state->duration) {
            state->repeat_count += 1;
            if (state->repeat_count >= state->repeat_limit) {
                state->active = 0;
            }
            if (kind == UINT32_C(0x40)) {
                state->base_angle += state->parameter_0;
            } else if (kind == UINT32_C(0x80)) {
                state->base_angle = th08_normalize_angle(
                    atan2f(player_y - state->y, player_x - state->x),
                    state->parameter_0);
            } else {
                state->base_angle = state->parameter_0;
            }
            state->base_speed = state->restored_speed;
            magnitude = state->base_speed;
            state->timer = 0;
        } else {
            magnitude = state->base_speed -
                        ((float)state->timer * state->base_speed) /
                            state->duration;
        }
        th08_polar(
            state->base_angle,
            magnitude * time_scale,
            &state->velocity_x,
            &state->velocity_y);
        state->timer += 1;
        break;
    case UINT32_C(0x400):
    case UINT32_C(0x800):
        if (!th08_transform_inside(state)) {
            if (state->x < 0.0F || state->x >= 384.0F) {
                state->base_angle = th08_normalize_angle(
                    -state->base_angle - TH08_PI,
                    0.0F);
            }
            if (state->y < 0.0F ||
                (state->y >= 448.0F && kind == UINT32_C(0x400))) {
                state->base_angle = -state->base_angle;
            }
            state->base_speed = state->restored_speed;
            th08_polar(
                state->base_angle,
                state->base_speed * time_scale,
                &state->velocity_x,
                &state->velocity_y);
            state->repeat_count += 1;
            if (state->repeat_count >= state->repeat_limit) {
                state->active = 0;
            }
        }
        break;
    default:
        return 2;
    }
    return 0;
}
