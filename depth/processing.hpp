#pragma once
#include <librealsense2/rsutil.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <cmath>
#include <stdexcept>

namespace go2w_depth_processing {
constexpr int side = 64;
constexpr float far_m = 2.0f;

// Match the square 58-degree pinhole camera used by Go2W WMP.
inline float make_maps(const rs2_intrinsics& intr, cv::Mat& mx, cv::Mat& my, bool allow_partial = false) {
    if (intr.model == RS2_DISTORTION_INVERSE_BROWN_CONRADY)
        throw std::runtime_error("Inverse Brown intrinsics cannot be projected; rectify the source first");
    mx.create(side, side, CV_32F);
    my.create(side, side, CV_32F);
    const float f = side / (2.0f * std::tan(58.0f * float(CV_PI) / 360.0f));
    int missing = 0;
    for (int y = 0; y < side; ++y) for (int x = 0; x < side; ++x) {
        float ray[3] = {(x - 31.5f) / f, (y - 31.5f) / f, 1.0f};
        float pixel[2];
        rs2_project_point_to_pixel(pixel, &intr, ray);
        if (!std::isfinite(pixel[0]) || !std::isfinite(pixel[1]) ||
            pixel[0] < 0 || pixel[0] > intr.width - 1 ||
            pixel[1] < 0 || pixel[1] > intr.height - 1) {
            ++missing;
            // Explicitly map out-of-FOV pixels to a zero border, even when nearest
            // sampling could round the coordinate back into the image.
            mx.at<float>(y, x) = -1;
            my.at<float>(y, x) = -1;
        } else {
            mx.at<float>(y, x) = pixel[0];
            my.at<float>(y, x) = pixel[1];
        }
    }
    const float fraction = float(missing) / (side * side);
    if (missing && (!allow_partial || fraction > 0.02f))
        throw std::runtime_error("Source does not cover 58x58 degree target FOV; missing_fraction=" +
                                 std::to_string(fraction) + "; optional --allow-partial-fov permits at most 2% invalid border");
    return fraction;
}

inline void sanitize(cv::Mat& depth, const cv::Mat& original, cv::Mat& valid) {
    if (depth.type() != CV_32F || original.type() != CV_32F ||
        depth.size() != cv::Size(side, side) || original.size() != depth.size())
        throw std::runtime_error("Expected two 64x64 float32 depth images");
    valid.create(side, side, CV_8U);
    for (int y = 0; y < side; ++y) for (int x = 0; x < side; ++x) {
        float& z = depth.at<float>(y, x);
        const float raw = original.at<float>(y, x);
        valid.at<uint8_t>(y, x) = std::isfinite(raw) && raw > 0 && std::isfinite(z) && z > 0;
        z = std::isfinite(z) && z > 0 ? std::min(z, far_m) : far_m;
    }
}
}
