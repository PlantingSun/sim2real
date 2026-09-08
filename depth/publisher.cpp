#include "DepthFrame.h"
#include "processing.hpp"
#include <dds/dds.h>
#include <librealsense2/rs.hpp>
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <cstring>
#include <iostream>
#include <mutex>
#include <random>
#include <regex>
#include <thread>

using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;
static volatile std::sig_atomic_t running = 1;
static void stop(int) { running = 0; }
static uint64_t monotonic_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
}
static uint64_t unix_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
}
static uint64_t session_id() {
    std::random_device r;
    return (uint64_t(r()) << 32) ^ r() ^ unix_ns();
}
struct Options {
    std::string interface = "eth0", topic = "rt/depth/image64", serial, snapshot;
    int domain = 42, width = 0, height = 0;
    double duration = 0;
    bool synthetic = false, diagnose = false, spatial = true, temporal = false;
    int hole_filling = -1;
};
static Options parse(int argc, char** argv) {
    Options o;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto value = [&]() -> std::string {
            if (++i >= argc) throw std::runtime_error("Missing value for " + a);
            return argv[i];
        };
        if (a == "--interface") o.interface = value();
        else if (a == "--topic") o.topic = value();
        else if (a == "--domain") o.domain = std::stoi(value());
        else if (a == "--serial") o.serial = value();
        else if (a == "--snapshot") o.snapshot = value();
        else if (a == "--width") o.width = std::stoi(value());
        else if (a == "--height") o.height = std::stoi(value());
        else if (a == "--duration") o.duration = std::stod(value());
        else if (a == "--synthetic") o.synthetic = true;
        else if (a == "--diagnose") o.diagnose = true;
        else if (a == "--no-spatial") o.spatial = false;
        else if (a == "--temporal") o.temporal = true;
        else if (a == "--allow-partial-fov") {} // accepted for old launch files; no longer needed
        else if (a == "--hole-filling") o.hole_filling = std::stoi(value());
        else if (a == "--help") {
            std::cout << "go2w_depth [--interface eth0] [--domain 42] [--topic rt/depth/image64]\n"
                         "  [--serial SERIAL] [--width W --height H] [--duration SECONDS]\n"
                         "  [--no-spatial] [--temporal] [--hole-filling 0|1|2] [--diagnose | --synthetic]\n"
                         "  [--snapshot PATH.yml] (one raw/processed sample and calibration)\n"
                         "Depth-only Z16 60 FPS; auto profiles: 848x480, 640x480, 480x270.\n";
            std::exit(0);
        } else throw std::runtime_error("Unknown argument " + a);
    }
    if (!std::regex_match(o.interface, std::regex("[a-zA-Z0-9_.:-]+")) ||
        o.domain < 0 || o.domain > 230 || !std::isfinite(o.duration) || o.duration < 0 ||
        ((o.width == 0) != (o.height == 0)) || o.width < 0 || o.height < 0 || o.hole_filling < -1 || o.hole_filling > 2)
        throw std::runtime_error("Invalid interface/domain/duration/resolution");
    return o;
}
static dds_entity_t checked(dds_entity_t e) {
    if (e < 0) throw std::runtime_error(dds_strretcode(e));
    return e;
}
struct Publisher {
    dds_entity_t domain = 0, participant = 0, writer = 0;
    uint64_t published = 0;
    explicit Publisher(const Options& o) {
        std::string xml = "<CycloneDDS><Domain><General><Interfaces><NetworkInterface name=\"" +
            o.interface + "\"/></Interfaces><MaxMessageSize>1400B</MaxMessageSize>"
            "<FragmentSize>1280B</FragmentSize></General></Domain></CycloneDDS>";
        domain = checked(dds_create_domain(o.domain, xml.c_str()));
        participant = checked(dds_create_participant(o.domain, nullptr, nullptr));
        auto topic = checked(dds_create_topic(participant, &go2w_depth_DepthFrame_desc, o.topic.c_str(), nullptr, nullptr));
        auto q = dds_create_qos();
        dds_qset_reliability(q, DDS_RELIABILITY_BEST_EFFORT, 0);
        dds_qset_history(q, DDS_HISTORY_KEEP_LAST, 1);
        dds_qset_durability(q, DDS_DURABILITY_VOLATILE);
        writer = dds_create_writer(participant, topic, q, nullptr);
        dds_delete_qos(q);
        checked(writer);
    }
    ~Publisher() { if (participant > 0) dds_delete(participant); if (domain > 0) dds_delete(domain); }
    void write(go2w_depth_DepthFrame& m) {
        m.publish_monotonic_ns = monotonic_ns();
        m.publish_unix_ns = unix_ns();
        checked(dds_write(writer, &m));
        ++published;
    }
};
static rs2::device choose_device(rs2::context& context, const Options& o) {
    auto devices = context.query_devices();
    for (auto d : devices) {
        const std::string serial = d.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER);
        const std::string name = d.get_info(RS2_CAMERA_INFO_NAME);
        if ((!o.serial.empty() && serial == o.serial) ||
            (o.serial.empty() && name.find("D435I") != std::string::npos)) return d;
    }
    throw std::runtime_error("No matching D435i; check lsusb, USB3 cable/port and permissions");
}
static int diagnose() {
    rs2::context context;
    auto devices = context.query_devices();
    std::cout << "SDK devices=" << devices.size() << '\n';
    for (auto d : devices) {
        std::cout << d.get_info(RS2_CAMERA_INFO_NAME) << " serial=" << d.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER)
                  << " firmware=" << d.get_info(RS2_CAMERA_INFO_FIRMWARE_VERSION) << '\n';
        if (d.supports(RS2_CAMERA_INFO_USB_TYPE_DESCRIPTOR))
            std::cout << "USB=" << d.get_info(RS2_CAMERA_INFO_USB_TYPE_DESCRIPTOR) << '\n';
        for (auto s : d.query_sensors()) for (auto p : s.get_stream_profiles()) {
            auto v = p.as<rs2::video_stream_profile>();
            if (v && p.stream_type() == RS2_STREAM_DEPTH && p.format() == RS2_FORMAT_Z16) {
                const auto intr = v.get_intrinsics();
                cv::Mat mx, my;
                bool covered = true;
                try { go2w_depth_processing::make_maps(intr, mx, my); }
                catch (const std::runtime_error&) { covered = false; }
                std::cout << "depth Z16 " << v.width() << 'x' << v.height() << " fps=" << p.fps()
                          << " fx=" << intr.fx << " fy=" << intr.fy << " cx=" << intr.ppx << " cy=" << intr.ppy
                          << " covers_target=" << covered << '\n';
            }
        }
    }
    return devices.size() ? 0 : 2;
}
struct Latest {
    std::mutex mutex;
    std::condition_variable ready;
    rs2::depth_frame frame{nullptr};
    uint64_t received_ns = 0, overwritten = 0, captures = 0;
};
static void capture(Publisher& publisher, const Options& o, Clock::time_point end) {
    rs2::context context;
    auto device = choose_device(context, o);
    const std::string serial = device.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER);
    const std::string usb = device.supports(RS2_CAMERA_INFO_USB_TYPE_DESCRIPTOR) ?
        device.get_info(RS2_CAMERA_INFO_USB_TYPE_DESCRIPTOR) : "unknown";
    int width = 0, height = 0;
    const std::vector<std::pair<int,int>> candidates = o.width ?
        std::vector<std::pair<int,int>>{{o.width, o.height}} :
        std::vector<std::pair<int,int>>{{848,480}, {640,480}, {480,270}};
    for (const auto& size : candidates) {
        for (auto s : device.query_sensors()) for (auto p : s.get_stream_profiles()) {
            auto v = p.as<rs2::video_stream_profile>();
            if (v && p.stream_type() == RS2_STREAM_DEPTH && p.format() == RS2_FORMAT_Z16 &&
                p.fps() == 60 && v.width() == size.first && v.height() == size.second) {
                // Reject nominal 60 Hz modes that cannot cover the simulation FOV.
                cv::Mat mx, my;
                try { go2w_depth_processing::make_maps(v.get_intrinsics(), mx, my); }
                catch (const std::runtime_error&) { continue; }
                width = size.first; height = size.second;
            }
        }
        if (width) break;
    }
    if (!width) throw std::runtime_error("No Z16 60 FPS profile covering 58x58 degree target FOV");
    Latest latest;
    rs2::pipeline pipeline(context);
    rs2::config cfg;
    cfg.enable_device(serial);
    cfg.enable_stream(RS2_STREAM_DEPTH, width, height, RS2_FORMAT_Z16, 60);
    const auto profile = pipeline.start(cfg, [&](rs2::frame frame) {
        auto depth = frame.as<rs2::depth_frame>();
        if (auto set = frame.as<rs2::frameset>()) depth = set.get_depth_frame();
        if (!depth) return;
        const auto received = monotonic_ns();
        std::lock_guard<std::mutex> lock(latest.mutex);
        if (latest.frame) ++latest.overwritten;
        latest.frame = depth;
        latest.received_ns = received;
        ++latest.captures;
        latest.ready.notify_one();
    });
    // RAII ensures callbacks have stopped before their captured storage is destroyed.
    struct StopPipeline { rs2::pipeline& p; ~StopPipeline() { try { p.stop(); } catch (...) {} } } guard{pipeline};
    auto sensor = profile.get_device().first<rs2::depth_sensor>();
    if (sensor.supports(RS2_OPTION_FRAMES_QUEUE_SIZE)) sensor.set_option(RS2_OPTION_FRAMES_QUEUE_SIZE, 1);
    if (sensor.supports(RS2_OPTION_AUTO_EXPOSURE_PRIORITY)) sensor.set_option(RS2_OPTION_AUTO_EXPOSURE_PRIORITY, 0);
    const float scale = sensor.get_depth_scale();
    auto intr = profile.get_stream(RS2_STREAM_DEPTH).as<rs2::video_stream_profile>().get_intrinsics();
    cv::Mat mx, my;
    const float edge_clamped = go2w_depth_processing::make_maps(intr, mx, my);
    rs2::disparity_transform to_disparity(true), to_depth(false);
    rs2::spatial_filter spatial;
    spatial.set_option(RS2_OPTION_FILTER_MAGNITUDE, 2);
    spatial.set_option(RS2_OPTION_FILTER_SMOOTH_ALPHA, 0.5f);
    spatial.set_option(RS2_OPTION_FILTER_SMOOTH_DELTA, 20);
    spatial.set_option(RS2_OPTION_HOLES_FILL, 0);
    rs2::temporal_filter temporal;
    temporal.set_option(RS2_OPTION_HOLES_FILL, 0); // no persistent historical holes
    rs2::hole_filling_filter holes;
    if (o.hole_filling >= 0) holes.set_option(RS2_OPTION_HOLES_FILL, float(o.hole_filling));
    go2w_depth_DepthFrame message{};
    message.version = 1;
    message.session_id = session_id();
    std::cout << "CONNECTED serial=" << serial << " usb=" << usb << " profile=" << width << 'x' << height
              << "@60 scale=" << scale << " intrinsics=" << intr.fx << ',' << intr.fy << ','
              << intr.ppx << ',' << intr.ppy << " distortion=" << intr.model << " edge_clamped_fraction=" << edge_clamped
              << " spatial=" << o.spatial << " temporal=" << o.temporal << " hole_filling=" << o.hole_filling
              << " session=" << message.session_id << std::endl;
    auto last_log = Clock::now(), warmup_end = last_log + 1s;
    uint64_t count = 0, previous_frame = 0, previous_captures = 0;
    double processing_total_ms = 0, processing_max_ms = 0;
    std::vector<double> processing_samples;
    bool first_published = true;
    bool snapshot_saved = false;
    while (running && Clock::now() < end) {
        rs2::depth_frame raw(nullptr);
        uint64_t received;
        {
            std::unique_lock<std::mutex> lock(latest.mutex);
            if (!latest.ready.wait_for(lock, 2s, [&] { return bool(latest.frame); }))
                throw std::runtime_error("Camera frame timeout (2 seconds)");
            raw = latest.frame;
            latest.frame = rs2::depth_frame(nullptr);
            received = latest.received_ns;
        }
        if (Clock::now() < warmup_end) continue;
        if (first_published) {
            std::lock_guard<std::mutex> lock(latest.mutex);
            last_log = Clock::now(); previous_captures = latest.captures;
            first_published = false;
        }
        const uint64_t number = raw.get_frame_number();
        if (number == previous_frame) continue;
        previous_frame = number;
        rs2::frame filtered = raw;
        if (o.spatial || o.temporal) {
            filtered = to_disparity.process(raw);
            if (o.spatial) filtered = spatial.process(filtered);
            if (o.temporal) filtered = temporal.process(filtered);
            filtered = to_depth.process(filtered);
        }
        if (o.hole_filling >= 0) filtered = holes.process(filtered);
        cv::Mat source(height, width, CV_16U, const_cast<void*>(filtered.get_data()), filtered.as<rs2::video_frame>().get_stride_in_bytes());
        cv::Mat raw_source(height, width, CV_16U, const_cast<void*>(raw.get_data()), raw.get_stride_in_bytes());
        cv::Mat small, original, depth_m, original_m, valid;
        cv::remap(source, small, mx, my, cv::INTER_NEAREST);
        cv::remap(raw_source, original, mx, my, cv::INTER_NEAREST);
        small.convertTo(depth_m, CV_32F, scale);
        original.convertTo(original_m, CV_32F, scale);
        go2w_depth_processing::sanitize(depth_m, original_m, valid);
        if (!o.snapshot.empty() && !snapshot_saved) {
            cv::FileStorage file(o.snapshot, cv::FileStorage::WRITE);
            if (!file.isOpened()) throw std::runtime_error("Cannot open snapshot " + o.snapshot);
            cv::Mat raw_m, filtered_m;
            raw_source.convertTo(raw_m, CV_32F, scale);
            source.convertTo(filtered_m, CV_32F, scale);
            file << "serial" << serial << "frame_id" << std::to_string(number)
                 << "depth_scale" << scale << "source_fx" << intr.fx << "source_fy" << intr.fy
                 << "source_cx" << intr.ppx << "source_cy" << intr.ppy
                 << "edge_clamped_fraction" << edge_clamped << "target_fov_deg" << 58
                 << "raw_depth_m" << raw_m << "filtered_depth_m" << filtered_m
                 << "map_x" << mx << "map_y" << my << "depth64_m" << depth_m << "valid64" << valid;
            file.release();
            snapshot_saved = true;
            std::cout << "SNAPSHOT " << o.snapshot << " frame=" << number << std::endl;
        }
        std::memcpy(message.depth_m, depth_m.ptr<float>(), sizeof(message.depth_m));
        std::memcpy(message.valid, valid.ptr<uint8_t>(), sizeof(message.valid));
        message.frame_id = number;
        message.device_timestamp_ms = raw.get_timestamp();
        message.timestamp_domain = raw.get_frame_timestamp_domain();
        message.capture_monotonic_ns = received;
        publisher.write(message);
        const double ms = (message.publish_monotonic_ns - received) / 1e6;
        processing_total_ms += ms;
        processing_max_ms = std::max(processing_max_ms, ms);
        processing_samples.push_back(ms);
        ++count;
        const auto now = Clock::now();
        const double seconds = std::chrono::duration<double>(now - last_log).count();
        if (seconds >= 10) {
            std::lock_guard<std::mutex> lock(latest.mutex);
            std::sort(processing_samples.begin(), processing_samples.end());
            std::cout << "STATS publish_hz=" << count / seconds << " capture_hz=" << (latest.captures - previous_captures) / seconds
                      << " overwritten=" << latest.overwritten << " processing_mean_ms=" << processing_total_ms / count
                      << " processing_max_ms=" << processing_max_ms << " valid_ratio=" << cv::countNonZero(valid) / 4096.0
                      << " processing_p95_ms=" << processing_samples[size_t(0.95 * (processing_samples.size() - 1))]
                      << " processing_p99_ms=" << processing_samples[size_t(0.99 * (processing_samples.size() - 1))]
                      << (count / seconds < 50 ? " BELOW_TARGET" : "") << std::endl;
            previous_captures = latest.captures;
            count = 0; processing_total_ms = processing_max_ms = 0; last_log = now;
            processing_samples.clear();
        }
    }
}
int main(int argc, char** argv) {
    try {
        const auto o = parse(argc, argv);
        if (o.diagnose) return diagnose();
        std::signal(SIGINT, stop); std::signal(SIGTERM, stop);
        Publisher publisher(o);
        const auto start = Clock::now();
        const auto end = o.duration > 0 ? start + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(o.duration)) : Clock::time_point::max();
        if (o.synthetic) {
            go2w_depth_DepthFrame message{};
            message.version = 1; message.session_id = session_id(); message.timestamp_domain = -1;
            for (int i = 0; i < 4096; ++i) message.depth_m[i] = float(i) * 2 / 4095;
            std::fill(std::begin(message.valid), std::end(message.valid), 1);
            auto next = start;
            std::cout << "SYNTHETIC 60 Hz: test data, not camera measurements" << std::endl;
            while (running && Clock::now() < end) {
                ++message.frame_id;
                message.capture_monotonic_ns = monotonic_ns();
                message.device_timestamp_ms = message.frame_id * 1000.0 / 60;
                publisher.write(message);
                next += std::chrono::nanoseconds(16666667);
                if (next < Clock::now()) next = Clock::now();
                std::this_thread::sleep_until(next);
            }
            return 0;
        }
        while (running && Clock::now() < end) {
            try { capture(publisher, o, end); }
            catch (const std::exception& e) {
                std::cerr << "CAMERA_UNAVAILABLE: " << e.what() << "; retry in 2s" << std::endl;
                for (int i = 0; i < 20 && running && Clock::now() < end; ++i) std::this_thread::sleep_for(100ms);
            }
        }
        std::cout << "FINAL published=" << publisher.published << std::endl;
        if (!publisher.published) return 2;
    } catch (const std::exception& e) { std::cerr << "ERROR: " << e.what() << std::endl; return 1; }
}
