#include "processing.hpp"
#include <iostream>
#include <limits>

void check(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
int main() {
    using namespace go2w_depth_processing;
    cv::Mat d(side, side, CV_32F, cv::Scalar(1));
    d.at<float>(0, 0) = 0;
    d.at<float>(0, 1) = -1;
    d.at<float>(0, 2) = std::numeric_limits<float>::quiet_NaN();
    d.at<float>(0, 3) = std::numeric_limits<float>::infinity();
    d.at<float>(0, 4) = 3;
    cv::Mat original = d.clone(), valid;
    sanitize(d, original, valid);
    for (int x = 0; x < 4; ++x) {
        check(d.at<float>(0, x) == 2, "Invalid depth must become far plane");
        check(valid.at<uint8_t>(0, x) == 0, "Invalid depth mask");
    }
    check(d.at<float>(0, 4) == 2 && valid.at<uint8_t>(0, 4) == 1, "Far valid depth clipping");
    check(d.at<float>(1, 1) == 1, "Meter scale preserved");
    original.at<float>(1, 1) = 0;
    sanitize(d, original, valid);
    check(valid.at<uint8_t>(1, 1) == 0, "Filter-filled pixels retain invalid source mask");
    rs2_intrinsics intr{};
    intr.width = intr.height = 640;
    intr.ppx = intr.ppy = 319.5f;
    intr.fx = intr.fy = 640 / (2 * std::tan(58 * float(CV_PI) / 360));
    intr.model = RS2_DISTORTION_NONE;
    cv::Mat mx, my;
    make_maps(intr, mx, my);
    check(std::abs(mx.at<float>(0, 0) - 4.5f) < 0.001f, "Target pixel center alignment");
    check(mx.at<float>(0, 63) > mx.at<float>(0, 0), "Horizontal orientation");
    check(my.at<float>(63, 0) > my.at<float>(0, 0), "Vertical orientation");
    intr.fx = intr.fy = 1000;
    bool rejected = false;
    try { make_maps(intr, mx, my); } catch (const std::runtime_error&) { rejected = true; }
    check(rejected, "Insufficient FOV must be rejected");
    intr.width = 480; intr.height = 270;
    intr.fx = intr.fy = 241.087f; intr.ppx = 240.835f; intr.ppy = 138.657f;
    const float corrected = make_maps(intr, mx, my);
    check(std::abs(corrected - 1.0f / 64) < 0.0001f, "USB2 camera corrects one bottom row");
    check(my.at<float>(63, 32) == 269 && my.at<float>(62, 32) < 269,
          "Bottom target row must sample the nearest real sensor row");
    cv::Mat source(270, 480, CV_16U, cv::Scalar(100));
    source.row(269).setTo(777);
    cv::Mat sampled;
    cv::remap(source, sampled, mx, my, cv::INTER_NEAREST);
    check(sampled.at<uint16_t>(63, 32) == 777,
          "Corrected bottom row must preserve the original edge measurement");
    check(sampled.at<uint16_t>(62, 32) == 100,
          "Edge correction must not change the preceding output row");
    std::cout << "depth processing checks passed\n";
}
