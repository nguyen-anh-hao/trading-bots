cmake_minimum_required(VERSION 3.16)
project(quant_mm LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(quant-mm
    src/main.cpp
    src/socket_client.cpp
    src/avellaneda_stoikov.cpp
    src/order_manager.cpp
)
target_include_directories(quant-mm PRIVATE src)

if(WIN32)
    target_link_libraries(quant-mm PRIVATE ws2_32)
endif()
