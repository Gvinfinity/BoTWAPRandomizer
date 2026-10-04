cmake_minimum_required(VERSION 3.16)
project(BotW_AP_Hook)

set(CMAKE_CXX_STANDARD 17)

# Define whether we are building for Windows (MinGW for Cemu on Wine/Windows) or Linux Native
if(WIN32)
    set(CMAKE_CXX_COMPILER "x86_64-w64-mingw32-g++")
    set(CMAKE_C_COMPILER "x86_64-w64-mingw32-gcc")
    add_compile_definitions(TARGET_WINDOWS)
else()
    add_compile_definitions(TARGET_LINUX)
endif()

# Include Submodules
include_directories(
    ${CMAKE_SOURCE_DIR}/../../external/uking/lib/
    ${CMAKE_SOURCE_DIR}/../../external/sead/include/
    ${CMAKE_SOURCE_DIR}/src/
)

# Core Hook Library
add_library(BotW_AP_Hook SHARED
    src/main.cpp
)

if(WIN32)
    set_target_properties(BotW_AP_Hook PROPERTIES PREFIX "" SUFFIX ".dll")
    target_link_options(BotW_AP_Hook PRIVATE "-static-libgcc" "-static-libstdc++")
else()
    set_target_properties(BotW_AP_Hook PROPERTIES PREFIX "lib" SUFFIX ".so")
endif()
