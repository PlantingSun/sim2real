// C++ DDS/LowCmd process. Commands use stdin; states use a dedicated pipe.

#include <unitree/go2_idl/LowCmd_.hpp>
#include <unitree/go2_idl/LowState_.hpp>
#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/channel/channel_publisher.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>

#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>

namespace {

using LowCmd = unitree_go::msg::dds_::LowCmd_;
using LowState = unitree_go::msg::dds_::LowState_;
using Clock = std::chrono::steady_clock;

constexpr uint32_t kStateMagic = 0x53544154;    // "STAT"
constexpr uint32_t kCommandMagic = 0x434D4421;  // "CMD!"
constexpr uint16_t kVersion = 1;
constexpr uint16_t kArm = 1U << 1;
constexpr uint16_t kDamping = 1U << 2;
constexpr uint16_t kStop = 1U << 3;
constexpr uint16_t kStateArmed = 1U << 0;
constexpr uint16_t kStateEmergency = 1U << 1;
constexpr uint16_t kStateWatchdog = 1U << 2;
constexpr uint16_t kStateOtherLowCmd = 1U << 3;
constexpr uint16_t kStatePrearmLowCmd = 1U << 4;
constexpr float kPosStop = 2.146e9F;
constexpr float kVelStop = 16000.0F;
constexpr float kDampingKd = 8.0F;
constexpr float kWheelVelocityLimit = 30.0F;
constexpr auto kPeriod = std::chrono::microseconds(2000);
constexpr auto kTimeout = std::chrono::milliseconds(100);

#pragma pack(push, 1)
struct StatePacket {
    uint32_t magic;
    uint16_t version;
    uint16_t flags;
    uint64_t sequence;
    uint64_t received_ns;
    uint32_t tick;
    float values[63];  // q, dq, tau, quaternion, gyro, accel, rpy, power
};

struct CommandPacket {
    uint32_t magic;
    uint16_t version;
    uint16_t flags;
    uint64_t sequence;
    uint64_t sent_ns;
    float values[80];  // q, dq, kp, kd, tau
};

// Exact byte layout used by unitree_sdk2_python/utils/crc.py.
struct PackedMotorCmd {
    uint8_t mode;
    uint8_t padding[3];
    float q;
    float dq;
    float tau;
    float kp;
    float kd;
    uint32_t reserve[3];
};

struct PackedLowCmd {
    uint8_t head[2];
    uint8_t level_flag;
    uint8_t frame_reserve;
    uint32_t sn[2];
    uint32_t version[2];
    uint16_t bandwidth;
    uint8_t padding0[2];
    PackedMotorCmd motor_cmd[20];
    uint8_t bms_cmd[4];
    uint8_t wireless_remote[40];
    uint8_t led[12];
    uint8_t fan[2];
    uint8_t gpio;
    uint8_t padding1;
    uint32_t reserve;
    uint32_t crc;
};
#pragma pack(pop)

static_assert(sizeof(StatePacket) == 280, "StatePacket layout changed");
static_assert(sizeof(CommandPacket) == 344, "CommandPacket layout changed");
static_assert(sizeof(PackedLowCmd) == 812, "PackedLowCmd layout changed");

std::atomic<bool> g_signal_stop{false};

uint64_t monotonic_ns() {
    timespec now{};
    clock_gettime(CLOCK_MONOTONIC, &now);
    return static_cast<uint64_t>(now.tv_sec) * 1000000000ULL + now.tv_nsec;
}

void on_signal(int) {
    g_signal_stop.store(true);
}

uint32_t crc32_core(const uint8_t* bytes, size_t words) {
    constexpr uint32_t polynomial = 0x04C11DB7;
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < words; ++i) {
        uint32_t word = 0;
        std::memcpy(&word, bytes + i * 4, sizeof(word));
        for (uint32_t bit = 1U << 31; bit; bit >>= 1) {
            crc = (crc << 1) ^ ((crc & 0x80000000U) ? polynomial : 0U);
            if (word & bit) crc ^= polynomial;
        }
    }
    return crc;
}

uint32_t command_crc(const LowCmd& command) {
    PackedLowCmd packed{};
    packed.head[0] = command.head()[0];
    packed.head[1] = command.head()[1];
    packed.level_flag = command.level_flag();
    packed.frame_reserve = command.frame_reserve();
    std::copy(command.sn().begin(), command.sn().end(), packed.sn);
    std::copy(command.version().begin(), command.version().end(), packed.version);
    packed.bandwidth = command.bandwidth();
    for (size_t i = 0; i < 20; ++i) {
        const auto& source = command.motor_cmd()[i];
        auto& target = packed.motor_cmd[i];
        target.mode = source.mode();
        target.q = source.q();
        target.dq = source.dq();
        target.tau = source.tau();
        target.kp = source.kp();
        target.kd = source.kd();
        std::copy(source.reserve().begin(), source.reserve().end(), target.reserve);
    }
    packed.bms_cmd[0] = command.bms_cmd().off();
    std::copy(command.bms_cmd().reserve().begin(), command.bms_cmd().reserve().end(),
              packed.bms_cmd + 1);
    std::copy(command.wireless_remote().begin(), command.wireless_remote().end(),
              packed.wireless_remote);
    std::copy(command.led().begin(), command.led().end(), packed.led);
    std::copy(command.fan().begin(), command.fan().end(), packed.fan);
    packed.gpio = command.gpio();
    packed.reserve = command.reserve();
    return crc32_core(reinterpret_cast<const uint8_t*>(&packed), sizeof(packed) / 4 - 1);
}

void initialize_command(LowCmd& command) {
    command.head()[0] = 0xFE;
    command.head()[1] = 0xEF;
    command.level_flag() = 0xFF;
    for (auto& motor : command.motor_cmd()) {
        motor.mode() = 0x01;
        motor.q() = kPosStop;
        motor.dq() = kVelStop;
    }
}

class Bridge {
public:
    Bridge(std::string interface, int cpu, int state_fd, bool monitor_only)
        : interface_(std::move(interface)), cpu_(cpu), monitor_only_(monitor_only),
          state_fd_(state_fd), publisher_("rt/lowcmd"), subscriber_("rt/lowstate"),
          lowcmd_guard_("rt/lowcmd") {
        initialize_command(low_cmd_);
    }

    ~Bridge() {
        running_.store(false);
        if (command_thread_.joinable()) command_thread_.join();
        if (control_thread_.joinable()) control_thread_.join();
        lowcmd_guard_.CloseChannel();
        subscriber_.CloseChannel();
        publisher_.CloseChannel();
    }

    void initialize() {
        // A state packet is smaller than PIPE_BUF, so every write is atomic.
        fcntl(state_fd_, F_SETFL, fcntl(state_fd_, F_GETFL) | O_NONBLOCK);
        unitree::robot::ChannelFactory::Instance()->Init(0, interface_);
        publisher_.InitChannel();
        subscriber_.InitChannel([this](const void* data) { on_low_state(data); }, 1);
        lowcmd_guard_.InitChannel([this](const void* data) { on_low_cmd(data); }, 1);
        running_.store(true);
        std::cerr << "[CPP DDS] ready, interface=" << interface_ << std::endl;
        command_thread_ = std::thread(&Bridge::command_loop, this);
        control_thread_ = std::thread(&Bridge::control_loop, this);
    }

    int run() {
        while (!g_signal_stop.load() && !stop_requested_.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        emergency_.store(true);
        if (armed_.load() && !monitor_only_) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        running_.store(false);
        if (command_thread_.joinable()) command_thread_.join();
        if (control_thread_.joinable()) control_thread_.join();
        print_statistics();
        return 0;
    }

private:
    void command_loop() {
        pollfd input{STDIN_FILENO, POLLIN | POLLHUP, 0};
        while (running_.load()) {
            const int ready = poll(&input, 1, 100);
            if (ready < 0) continue;
            if (input.revents & POLLHUP) {
                on_command_pipe_closed();
                return;
            }
            if (!(input.revents & POLLIN)) continue;

            CommandPacket packet{};
            const ssize_t count = read(STDIN_FILENO, &packet, sizeof(packet));
            if (count == 0) {
                on_command_pipe_closed();
                return;
            }
            if (count != static_cast<ssize_t>(sizeof(packet)) ||
                packet.magic != kCommandMagic || packet.version != kVersion) {
                continue;
            }
            if (packet.flags & kDamping) emergency_.store(true);
            if (packet.flags & kStop) stop_requested_.store(true);
            if (!(packet.flags & kDamping) && command_is_finite(packet)) {
                std::lock_guard<std::mutex> lock(command_mutex_);
                command_ = packet;
                command_time_ = Clock::now();
                has_command_ = true;
                if (packet.flags & kArm) {
                    armed_.store(true);
                }
            }
        }
    }

    static bool command_is_finite(const CommandPacket& packet) {
        for (float value : packet.values) {
            if (!std::isfinite(value)) return false;
        }
        return true;
    }

    void on_command_pipe_closed() {
        emergency_.store(true);
        if (armed_.load()) {
            watchdog_.store(true);
            watchdog_time_ns_.store(monotonic_ns());
        } else {
            stop_requested_.store(true);
        }
    }

    void on_low_cmd(const void* data) {
        const auto& command = *static_cast<const LowCmd*>(data);
        if (!own_write_started_.load()) {
            prearm_lowcmd_ns_.store(monotonic_ns());
            return;
        }
        if (monotonic_ns() - own_write_start_ns_.load() < 20000000ULL) return;

        bool own_crc = false;
        {
            std::lock_guard<std::mutex> lock(crc_mutex_);
            own_crc = std::find(recent_crc_.begin(), recent_crc_.end(), command.crc())
                      != recent_crc_.end();
        }
        if (!own_crc && !other_lowcmd_.exchange(true)) {
            std::cerr << "[CPP DDS] concurrent rt/lowcmd publisher detected" << std::endl;
            emergency_.store(true);
            watchdog_.store(true);
            watchdog_time_ns_.store(monotonic_ns());
        }
    }

    void on_low_state(const void* data) {
        const auto& state = *static_cast<const LowState*>(data);
        StatePacket packet{};
        packet.magic = kStateMagic;
        packet.version = kVersion;
        packet.sequence = ++state_sequence_;
        packet.received_ns = monotonic_ns();
        packet.tick = state.tick();
        size_t index = 0;
        for (size_t i = 0; i < 16; ++i) packet.values[index++] = state.motor_state()[i].q();
        for (size_t i = 0; i < 16; ++i) packet.values[index++] = state.motor_state()[i].dq();
        for (size_t i = 0; i < 16; ++i) packet.values[index++] = state.motor_state()[i].tau_est();
        for (float value : state.imu_state().quaternion()) packet.values[index++] = value;
        for (float value : state.imu_state().gyroscope()) packet.values[index++] = value;
        for (float value : state.imu_state().accelerometer()) packet.values[index++] = value;
        for (float value : state.imu_state().rpy()) packet.values[index++] = value;
        packet.values[index++] = state.power_v();
        packet.values[index] = state.power_a();
        if (armed_.load()) packet.flags |= kStateArmed;
        if (emergency_.load()) packet.flags |= kStateEmergency;
        if (watchdog_.load()) packet.flags |= kStateWatchdog;
        if (other_lowcmd_.load()) packet.flags |= kStateOtherLowCmd;
        const uint64_t prearm_ns = prearm_lowcmd_ns_.load();
        if (!own_write_started_.load() && prearm_ns != 0 &&
            monotonic_ns() - prearm_ns < 500000000ULL) {
            packet.flags |= kStatePrearmLowCmd;
        }

        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            latest_state_ = packet;
            state_time_ = Clock::now();
            has_state_ = true;
        }
        if (write(state_fd_, &packet, sizeof(packet)) != sizeof(packet)) ++state_drops_;
    }

    void control_loop() {
        pin_control_thread();
        auto next = Clock::now();
        while (running_.load()) {
            const auto start = Clock::now();
            if (armed_.load() && !monitor_only_) {
                record_interval(start);
            } else {
                last_loop_time_ = Clock::time_point{};
            }
            write_low_command(start);
            next += kPeriod;
            if (Clock::now() > next) {
                ++late_cycles_;
                next = Clock::now() + kPeriod;  // Never replay an expired cycle.
            }
            std::this_thread::sleep_until(next);
        }
    }

    void pin_control_thread() const {
        if (cpu_ < 0) return;
        cpu_set_t cpus;
        CPU_ZERO(&cpus);
        CPU_SET(cpu_, &cpus);
        const int result = pthread_setaffinity_np(pthread_self(), sizeof(cpus), &cpus);
        if (result != 0) {
            std::cerr << "[CPP DDS] CPU affinity failed: " << std::strerror(result) << std::endl;
        } else {
            std::cerr << "[CPP DDS] LowCmd thread pinned to CPU " << cpu_ << std::endl;
        }
    }

    void write_low_command(Clock::time_point now) {
        if (!armed_.load() || monitor_only_) return;
        CommandPacket command{};
        bool invalid = false;
        {
            std::lock_guard<std::mutex> lock(command_mutex_);
            command = command_;
            invalid = !has_command_ || now - command_time_ > kTimeout;
        }
        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            invalid = invalid || !has_state_ || now - state_time_ > kTimeout;
            for (size_t i = 12; !invalid && i < 16; ++i) {
                invalid = std::abs(latest_state_.values[16 + i]) > kWheelVelocityLimit;
            }
        }
        if (invalid) {
            watchdog_.store(true);
            emergency_.store(true);
            uint64_t expected = 0;
            watchdog_time_ns_.compare_exchange_strong(expected, monotonic_ns());
        }
        const uint64_t watchdog_ns = watchdog_time_ns_.load();
        if (watchdog_ns && monotonic_ns() - watchdog_ns > 500000000ULL) {
            stop_requested_.store(true);
        }

        if (emergency_.load()) fill_damping(); else fill_command(command);
        const auto crc_start = Clock::now();
        low_cmd_.crc() = command_crc(low_cmd_);
        const double crc_ms = std::chrono::duration<double, std::milli>(
            Clock::now() - crc_start).count();
        crc_sum_ms_ += crc_ms;
        crc_max_ms_ = std::max(crc_max_ms_, crc_ms);
        {
            std::lock_guard<std::mutex> lock(crc_mutex_);
            recent_crc_[crc_index_++ % recent_crc_.size()] = low_cmd_.crc();
        }
        const auto write_start = Clock::now();
        if (!own_write_started_.exchange(true)) own_write_start_ns_.store(monotonic_ns());
        if (!publisher_.Write(low_cmd_)) ++write_failures_;
        const double write_ms = std::chrono::duration<double, std::milli>(
            Clock::now() - write_start).count();
        ++write_count_;
        write_sum_ms_ += write_ms;
        write_max_ms_ = std::max(write_max_ms_, write_ms);
    }

    void fill_command(const CommandPacket& packet) {
        for (size_t i = 0; i < 16; ++i) {
            auto& motor = low_cmd_.motor_cmd()[i];
            motor.mode() = 0x01;
            motor.q() = packet.values[i];
            motor.dq() = packet.values[16 + i];
            motor.kp() = packet.values[32 + i];
            motor.kd() = packet.values[48 + i];
            motor.tau() = packet.values[64 + i];
        }
    }

    void fill_damping() {
        for (auto& motor : low_cmd_.motor_cmd()) {
            motor.mode() = 0x01;
            motor.q() = kPosStop;
            motor.dq() = 0.0F;
            motor.kp() = 0.0F;
            motor.kd() = kDampingKd;
            motor.tau() = 0.0F;
        }
    }

    void record_interval(Clock::time_point now) {
        if (last_loop_time_ != Clock::time_point{}) {
            const double ms = std::chrono::duration<double, std::milli>(now - last_loop_time_).count();
            ++interval_count_;
            interval_sum_ms_ += ms;
            interval_max_ms_ = std::max(interval_max_ms_, ms);
            if (ms > 3.0) ++over_3ms_;
            if (ms > 5.0) ++over_5ms_;
            if (ms > 10.0) ++over_10ms_;
            if (ms < 1.0) ++under_1ms_;
        }
        last_loop_time_ = now;
    }

    void print_statistics() const {
        const double interval_mean = interval_count_ ? interval_sum_ms_ / interval_count_ : 0.0;
        const double write_mean = write_count_ ? write_sum_ms_ / write_count_ : 0.0;
        const double crc_mean = write_count_ ? crc_sum_ms_ / write_count_ : 0.0;
        std::cerr << "[CPP DDS RATE] writes=" << write_count_
                  << " interval_mean_ms=" << interval_mean
                  << " interval_max_ms=" << interval_max_ms_
                  << " over_3/5/10ms=" << over_3ms_ << "/" << over_5ms_ << "/" << over_10ms_
                  << " under_1ms=" << under_1ms_ << " late=" << late_cycles_ << std::endl;
        std::cerr << "[CPP DDS WRITE] mean_ms=" << write_mean
                  << " max_ms=" << write_max_ms_ << " failures=" << write_failures_
                  << " crc_mean/max_ms=" << crc_mean << "/" << crc_max_ms_
                  << " state_drops=" << state_drops_.load()
                  << " other_lowcmd=" << other_lowcmd_.load()
                  << " prearm_lowcmd_seen=" << (prearm_lowcmd_ns_.load() != 0) << std::endl;
    }

    std::string interface_;
    int cpu_;
    bool monitor_only_;
    int state_fd_;
    unitree::robot::ChannelPublisher<LowCmd> publisher_;
    unitree::robot::ChannelSubscriber<LowState> subscriber_;
    unitree::robot::ChannelSubscriber<LowCmd> lowcmd_guard_;
    LowCmd low_cmd_;
    StatePacket latest_state_{};
    CommandPacket command_{};
    std::mutex state_mutex_;
    std::mutex command_mutex_;
    std::mutex crc_mutex_;
    Clock::time_point state_time_{};
    Clock::time_point command_time_{};
    Clock::time_point last_loop_time_{};
    bool has_state_ = false;
    bool has_command_ = false;
    std::atomic<bool> running_{false};
    std::atomic<bool> armed_{false};
    std::atomic<bool> emergency_{false};
    std::atomic<bool> watchdog_{false};
    std::atomic<bool> stop_requested_{false};
    std::atomic<bool> other_lowcmd_{false};
    std::atomic<bool> own_write_started_{false};
    std::atomic<uint64_t> own_write_start_ns_{0};
    std::atomic<uint64_t> prearm_lowcmd_ns_{0};
    std::atomic<uint64_t> state_sequence_{0};
    std::atomic<uint64_t> state_drops_{0};
    std::array<uint32_t, 16> recent_crc_{};
    size_t crc_index_ = 0;
    std::thread command_thread_;
    std::thread control_thread_;
    std::atomic<uint64_t> watchdog_time_ns_{0};
    uint64_t write_count_ = 0;
    uint64_t write_failures_ = 0;
    uint64_t interval_count_ = 0;
    uint64_t over_3ms_ = 0;
    uint64_t over_5ms_ = 0;
    uint64_t over_10ms_ = 0;
    uint64_t under_1ms_ = 0;
    uint64_t late_cycles_ = 0;
    double interval_sum_ms_ = 0.0;
    double interval_max_ms_ = 0.0;
    double write_sum_ms_ = 0.0;
    double write_max_ms_ = 0.0;
    double crc_sum_ms_ = 0.0;
    double crc_max_ms_ = 0.0;
};

}  // namespace

int main(int argc, char** argv) {
    std::string interface = "eth0";
    int cpu = 1;
    int state_fd = STDOUT_FILENO;
    bool monitor_only = false;
    bool crc_test = false;
    for (int i = 1; i < argc; ++i) {
        const std::string option = argv[i];
        if (option == "--interface" && i + 1 < argc) interface = argv[++i];
        else if (option == "--cpu" && i + 1 < argc) cpu = std::stoi(argv[++i]);
        else if (option == "--state-fd" && i + 1 < argc) state_fd = std::stoi(argv[++i]);
        else if (option == "--monitor-only") monitor_only = true;
        else if (option == "--crc-test") crc_test = true;
        else {
            std::cerr << "Unknown argument: " << option << std::endl;
            return 2;
        }
    }
    if (crc_test) {
        LowCmd command;
        initialize_command(command);
        for (size_t i = 0; i < command.motor_cmd().size(); ++i) {
            command.motor_cmd()[i].q() = static_cast<float>(i);
            command.motor_cmd()[i].dq() = -static_cast<float>(i);
            command.motor_cmd()[i].tau() = 0.25F * static_cast<float>(i);
            command.motor_cmd()[i].kp() = 10.0F + static_cast<float>(i);
            command.motor_cmd()[i].kd() = 0.5F + 0.03125F * static_cast<float>(i);
        }
        std::cout << command_crc(command) << std::endl;
        return 0;
    }
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    signal(SIGPIPE, SIG_IGN);  // Keep the damping path alive if Python exits first.
    Bridge bridge(interface, cpu, state_fd, monitor_only);
    bridge.initialize();
    return bridge.run();
}
