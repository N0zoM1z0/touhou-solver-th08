#include <algorithm>
#include <atomic>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <functional>
#include <limits>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <vector>

#include "src/internal/abi_impl.hpp"
#include "include/touhou_native/local_hazard_stop.hpp"

using touhou_native::local_hazard_stop_status;

namespace {

bool source_aabb_overlap(
    float player_x,
    float player_y,
    float player_half_extent,
    float hazard_x,
    float hazard_y,
    float hazard_half_width,
    float hazard_half_height
) {
    // Player::FUN_0044a230 compares inclusive bounds after each Float3
    // component has been stored as binary32.  The center-distance shortcut
    // is not equivalent at touching edges.
    const float player_left = player_x - player_half_extent;
    const float player_top = player_y - player_half_extent;
    const float player_right = player_x + player_half_extent;
    const float player_bottom = player_y + player_half_extent;
    const float hazard_left = hazard_x - hazard_half_width;
    const float hazard_top = hazard_y - hazard_half_height;
    const float hazard_right = hazard_x + hazard_half_width;
    const float hazard_bottom = hazard_y + hazard_half_height;
    return !(
        player_left > hazard_right
        || player_top > hazard_bottom
        || player_right < hazard_left
        || player_bottom < hazard_top
    );
}

float align_clearance_sign(float clearance, bool overlap) {
    if (overlap) {
        return std::min(clearance, 0.0F);
    }
    return std::max(
        clearance,
        std::nextafter(0.0F, std::numeric_limits<float>::infinity())
    );
}

}  // namespace

int touhou_native_impl_local_hazards_v1(
    const float* positions_x,
    const float* positions_y,
    int position_count,
    int step,
    float player_radius,
    const float* bullet_x,
    const float* bullet_y,
    const float* bullet_half_width,
    const float* bullet_half_height,
    const std::uint8_t* bullet_transformed,
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
    std::int32_t* output_collisions,
    double* output_minimum
) {
    if (
        positions_x == nullptr
        || positions_y == nullptr
        || output_risk == nullptr
        || output_collisions == nullptr
        || output_minimum == nullptr
        || position_count <= 0
        || step <= 0
        || !std::isfinite(player_radius)
        || player_radius < 0.0F
        || bullet_count < 0
        || laser_count < 0
        || body_count < 0
    ) {
        return -1;
    }
    if (
        (
            bullet_count > 0
            && (
                bullet_x == nullptr
                || bullet_y == nullptr
                || bullet_half_width == nullptr
                || bullet_half_height == nullptr
                || bullet_transformed == nullptr
            )
        )
        || (
            laser_count > 0
            && (
                laser_start_x == nullptr
                || laser_start_y == nullptr
                || laser_segment_x == nullptr
                || laser_segment_y == nullptr
                || laser_collision_radius == nullptr
                || laser_base_uncertainty == nullptr
                || laser_uncertainty_per_frame == nullptr
            )
        )
        || (
            body_count > 0
            && (
                body_x == nullptr
                || body_y == nullptr
                || body_half_width == nullptr
                || body_half_height == nullptr
            )
        )
    ) {
        return -2;
    }

    float position_min_x = positions_x[0];
    float position_max_x = positions_x[0];
    float position_min_y = positions_y[0];
    float position_max_y = positions_y[0];
    for (int position = 0; position < position_count; ++position) {
        if ((position & 63) == 0) {
            const int stop = local_hazard_stop_status();
            if (stop != 0) {
                return stop;
            }
        }
        if (
            !std::isfinite(positions_x[position])
            || !std::isfinite(positions_y[position])
        ) {
            return -3;
        }
        position_min_x = std::min(
            position_min_x,
            positions_x[position]
        );
        position_max_x = std::max(
            position_max_x,
            positions_x[position]
        );
        position_min_y = std::min(
            position_min_y,
            positions_y[position]
        );
        position_max_y = std::max(
            position_max_y,
            positions_y[position]
        );
        output_risk[position] = 0.0;
        output_collisions[position] = 0;
        output_minimum[position] = std::numeric_limits<double>::infinity();
    }
    const double time_weight = 1.0 / (
        1.0 + 0.08 * static_cast<double>(step - 1)
    );

    const float bullet_margin = 84.0F;
    const float base_bullet_uncertainty = (
        0.2F * std::sqrt(static_cast<float>(step))
    );
    const float transformed_uncertainty = std::min(
        10.0F,
        3.0F + 0.35F * static_cast<float>(step)
    );
    std::vector<float> bullet_risk_sum(
        static_cast<std::size_t>(position_count),
        0.0F
    );
    for (int bullet = 0; bullet < bullet_count; ++bullet) {
        if ((bullet & 63) == 0) {
            const int stop = local_hazard_stop_status();
            if (stop != 0) {
                return stop;
            }
        }
        if (
            bullet_x[bullet] < position_min_x - bullet_margin
            || bullet_x[bullet] > position_max_x + bullet_margin
            || bullet_y[bullet] < position_min_y - bullet_margin
            || bullet_y[bullet] > position_max_y + bullet_margin
        ) {
            continue;
        }
        const float uncertainty = (
            base_bullet_uncertainty
            + (
                bullet_transformed[bullet] != 0
                ? transformed_uncertainty
                : 0.0F
            )
        );
        for (int position = 0; position < position_count; ++position) {
            if (
                bullet_x[bullet]
                    < positions_x[position] - bullet_margin
                || bullet_x[bullet]
                    > positions_x[position] + bullet_margin
                || bullet_y[bullet]
                    < positions_y[position] - bullet_margin
                || bullet_y[bullet]
                    > positions_y[position] + bullet_margin
            ) {
                continue;
            }
            const float dx = (
                std::fabs(positions_x[position] - bullet_x[bullet])
                - (player_radius + bullet_half_width[bullet])
            );
            const float dy = (
                std::fabs(positions_y[position] - bullet_y[bullet])
                - (player_radius + bullet_half_height[bullet])
            );
            const bool overlap = source_aabb_overlap(
                positions_x[position],
                positions_y[position],
                player_radius,
                bullet_x[bullet],
                bullet_y[bullet],
                bullet_half_width[bullet],
                bullet_half_height[bullet]
            );
            const bool center_overlap = dx <= 0.0F && dy <= 0.0F;
            const float metric_clearance = center_overlap
                ? std::max(dx, dy)
                : std::hypot(
                    std::max(dx, 0.0F),
                    std::max(dy, 0.0F)
                );
            const float clearance = align_clearance_sign(
                metric_clearance,
                overlap
            );
            if (overlap) {
                ++output_collisions[position];
            }
            const float robust_clearance = clearance - uncertainty;
            output_minimum[position] = std::min(
                output_minimum[position],
                static_cast<double>(robust_clearance)
            );
            const float danger = std::max(
                44.0F - robust_clearance,
                0.0F
            );
            bullet_risk_sum[position] += danger * danger;
        }
    }
    for (int position = 0; position < position_count; ++position) {
        output_risk[position] += (
            static_cast<double>(bullet_risk_sum[position])
            * time_weight
        );
    }

    const float laser_margin = 56.0F;
    std::vector<float> laser_risk_sum(
        static_cast<std::size_t>(position_count),
        0.0F
    );
    for (int laser = 0; laser < laser_count; ++laser) {
        if ((laser & 63) == 0) {
            const int stop = local_hazard_stop_status();
            if (stop != 0) {
                return stop;
            }
        }
        const float uncertainty = (
            laser_base_uncertainty[laser]
            + std::min(
                6.0F,
                laser_uncertainty_per_frame[laser]
                    * static_cast<float>(step)
            )
        );
        const float occupied_radius = (
            laser_collision_radius[laser] + uncertainty
        );
        const float end_x = (
            laser_start_x[laser] + laser_segment_x[laser]
        );
        const float end_y = (
            laser_start_y[laser] + laser_segment_y[laser]
        );
        const float min_x = std::min(laser_start_x[laser], end_x);
        const float max_x = std::max(laser_start_x[laser], end_x);
        const float min_y = std::min(laser_start_y[laser], end_y);
        const float max_y = std::max(laser_start_y[laser], end_y);
        if (
            max_x + occupied_radius
                < position_min_x - laser_margin
            || min_x - occupied_radius
                > position_max_x + laser_margin
            || max_y + occupied_radius
                < position_min_y - laser_margin
            || min_y - occupied_radius
                > position_max_y + laser_margin
        ) {
            continue;
        }
        const float length_squared = (
            laser_segment_x[laser] * laser_segment_x[laser]
            + laser_segment_y[laser] * laser_segment_y[laser]
        );
        for (int position = 0; position < position_count; ++position) {
            if (
                max_x + occupied_radius
                    < positions_x[position] - laser_margin
                || min_x - occupied_radius
                    > positions_x[position] + laser_margin
                || max_y + occupied_radius
                    < positions_y[position] - laser_margin
                || min_y - occupied_radius
                    > positions_y[position] + laser_margin
            ) {
                continue;
            }
            float projection = 0.0F;
            if (length_squared > 1e-9F) {
                projection = (
                    (
                        positions_x[position] - laser_start_x[laser]
                    ) * laser_segment_x[laser]
                    + (
                        positions_y[position] - laser_start_y[laser]
                    ) * laser_segment_y[laser]
                ) / length_squared;
            }
            projection = std::min(
                1.0F,
                std::max(0.0F, projection)
            );
            const float distance = std::hypot(
                positions_x[position]
                    - (
                        laser_start_x[laser]
                        + projection * laser_segment_x[laser]
                    ),
                positions_y[position]
                    - (
                        laser_start_y[laser]
                        + projection * laser_segment_y[laser]
                    )
            );
            const float clearance = (
                distance - laser_collision_radius[laser]
            );
            if (clearance <= 0.0F) {
                ++output_collisions[position];
            }
            const float robust_clearance = clearance - uncertainty;
            output_minimum[position] = std::min(
                output_minimum[position],
                static_cast<double>(robust_clearance)
            );
            const float danger = std::max(
                56.0F - robust_clearance,
                0.0F
            );
            laser_risk_sum[position] += danger * danger;
        }
    }
    for (int position = 0; position < position_count; ++position) {
        output_risk[position] += (
            2.0
            * static_cast<double>(laser_risk_sum[position])
            * time_weight
        );
    }

    const float body_step_uncertainty = std::min(
        12.0F,
        0.5F * static_cast<float>(step)
    );
    std::vector<float> body_risk_sum(
        static_cast<std::size_t>(position_count),
        0.0F
    );
    for (int body = 0; body < body_count; ++body) {
        if ((body & 63) == 0) {
            const int stop = local_hazard_stop_status();
            if (stop != 0) {
                return stop;
            }
        }
        for (int position = 0; position < position_count; ++position) {
            const float dx = (
                std::fabs(positions_x[position] - body_x[body])
                - (player_radius + body_half_width[body])
            );
            const float dy = (
                std::fabs(positions_y[position] - body_y[body])
                - (player_radius + body_half_height[body])
            );
            const bool overlap = source_aabb_overlap(
                positions_x[position],
                positions_y[position],
                player_radius,
                body_x[body],
                body_y[body],
                body_half_width[body],
                body_half_height[body]
            );
            const bool center_overlap = dx <= 0.0F && dy <= 0.0F;
            const float metric_clearance = center_overlap
                ? std::max(dx, dy)
                : std::hypot(
                    std::max(dx, 0.0F),
                    std::max(dy, 0.0F)
                );
            const float clearance = align_clearance_sign(
                metric_clearance,
                overlap
            );
            if (overlap) {
                ++output_collisions[position];
            }
            const float robust_clearance = (
                clearance - body_step_uncertainty
            );
            output_minimum[position] = std::min(
                output_minimum[position],
                static_cast<double>(robust_clearance)
            );
            const float danger = std::max(
                64.0F - robust_clearance,
                0.0F
            );
            body_risk_sum[position] += danger * danger;
        }
    }
    for (int position = 0; position < position_count; ++position) {
        output_risk[position] += (
            2.0
            * static_cast<double>(body_risk_sum[position])
            * time_weight
        );
    }
    return local_hazard_stop_status();
}
