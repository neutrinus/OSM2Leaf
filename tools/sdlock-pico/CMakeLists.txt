# sdlock - SD CMD42 lock/unlock tool for the Raspberry Pi Pico (RP2040).
# Build: see docs/hardware/sd-blocker-pico.md (needs PICO_SDK_PATH).
cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(sdlock C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

add_executable(sdlock
    src/main.c
    src/sd_card.c
    src/sd_proto.c
)
target_compile_options(sdlock PRIVATE -Wall -Wextra)
target_link_libraries(sdlock pico_stdlib hardware_spi)

pico_enable_stdio_usb(sdlock 1)
pico_enable_stdio_uart(sdlock 0)
pico_add_extra_outputs(sdlock)
