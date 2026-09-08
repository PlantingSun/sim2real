#pragma once
#include <librealsense2/rsutil.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace go2w_depth_processing {
constexpr int side = 64;
constexpr float far_m = 2.0f;
constexpr float max_edge_correction_px = 2.0f;

// Match the square 58-degree pinhole camera used by Go2W WMP. A calibrated
// principal point need not be at the geometric image center, so an outer target
// ray can land just beyond the last source pixel even when the nominal source
// FOV covers 58 degrees. For an overshoot of at most two source pixels, sample
// the nearest real sensor edge. Larger mismatches still fail explicitly.
// The return value is the fraction of target pixels clamped to a sensor edge.
inline float make_maps(const rs2_intrinsics& intr, cv::Mat& mx, cv::Mat& my) {
    if (intr.model == RS2_DISTORTION_INVERSE_BROWN_CONRADY)
        throw std::runtime_error("Inverse Brown intrinsics cannot be projected; rectify the source first");
    mx.create(side, side, CV_32F);
    my.create(side, side, CV_32F);
    const float f = side / (2.0f * std::tan(58.0f * float(CV_PI) / 360.0f));
    int edge_corrected = 0;
    for (int y = 0; y < side; ++y) for (int x = 0; x < side; ++x) {
        float ray[3] = {(x - 31.5f) / f, (y - 31.5f) / f, 1.0f};
        float pixel[2];
        rs2_project_point_to_pixel(pixel, &intr, ray);
        if (!std::isfinite(pixel[0]) || !std::isfinite(pixel[1]))
            throw std::runtime_error("Non-finite projected depth coordinate");
        const float source_x = std::clamp(pixel[0], 0.0f, float(intr.width - 1));
        const float source_y = std::clamp(pixel[1], 0.0f, float(intr.height - 1));
        const float correction = std::max(std::abs(source_x - pixel[0]),
                                          std::abs(source_y - pixel[1]));
        if (correction > max_edge_correction_px)
            throw std::runtime_error("Source FOV is too small for the 58x58 degree target; edge_correction_px=" +
                                     std::to_string(correction));
        if (correction > 0) ++edge_corrected;
        mx.at<float>(y, x) = source_x;
        my.at<float>(y, x) = source_y;
    }
    return float(edge_corrected) / (side * side);
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
