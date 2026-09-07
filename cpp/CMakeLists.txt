cmake_minimum_required(VERSION 3.10)
project(sim2real_dds_bridge LANGUAGES CXX)

add_executable(go2w_dds_bridge go2w_dds_bridge.cpp)
target_compile_features(go2w_dds_bridge PRIVATE cxx_std_17)
target_compile_options(go2w_dds_bridge PRIVATE -O2 -Wall -Wextra -Wpedantic)
target_include_directories(go2w_dds_bridge PRIVATE
    /usr/local/include
    /usr/local/include/ddscxx
    /usr/local/include/iceoryx/v2.0.2
)
target_link_directories(go2w_dds_bridge PRIVATE /usr/local/lib)
target_link_libraries(go2w_dds_bridge PRIVATE
    unitree_go2_sdk
    unitree_go2_idl_cpp
    ddscxx
    ddsc
    pthread
)

