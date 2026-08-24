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
