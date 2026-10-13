cmake_minimum_required(VERSION 3.16)
project(vision_worker CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ==============================================================================
# --- DETECTION DU COMPILATEUR ET DES INSTRUCTIONS VECTORIELLES AVX2 / FMA ---
# ==============================================================================
include(CheckCXXCompilerFlag)

# Optimisation agressive O3 + OpenMP
set(EXTRA_OPT_FLAGS -O3 -Wall -Wextra -funroll-loops -ftree-vectorize)

check_cxx_compiler_flag("-mavx2" COMPILER_SUPPORTS_AVX2)
if(COMPILER_SUPPORTS_AVX2)
    list(APPEND EXTRA_OPT_FLAGS -mavx2)
endif()

check_cxx_compiler_flag("-mfma" COMPILER_SUPPORTS_FMA)
if(COMPILER_SUPPORTS_FMA)
    list(APPEND EXTRA_OPT_FLAGS -mfma)
endif()

# ==============================================================================
# --- DEPENDANCES DU PROJET : OpenCV, OpenMP, ZeroMQ, Threads ---
# ==============================================================================
find_package(OpenMP REQUIRED)
find_package(Threads REQUIRED)

# Recherche modulaire d'OpenCV (compatible OpenCV 4.x et OpenCV 5.x, Ubuntu/Debian/Arch)
find_package(OpenCV QUIET COMPONENTS core imgproc objdetect imgcodecs videoio)

if(NOT OpenCV_FOUND)
    # Tentative dans les répertoires standards Ubuntu / Debian multiarch
    find_path(OpenCV_DIR OpenCVConfig.cmake
        PATHS
        /usr/lib/x86_64-linux-gnu/cmake/opencv4
        /usr/lib/aarch64-linux-gnu/cmake/opencv4
        /usr/share/opencv4
        /usr/lib/cmake/opencv4
        /usr/local/share/opencv4
    )
    if(OpenCV_DIR)
        find_package(OpenCV QUIET PATHS ${OpenCV_DIR})
    endif()
endif()

if(NOT OpenCV_FOUND)
    # Tentative via PkgConfig
    find_package(PkgConfig QUIET)
    if(PKG_CONFIG_FOUND)
        pkg_check_modules(OpenCV QUIET opencv4)
        if(NOT OpenCV_FOUND)
            pkg_check_modules(OpenCV QUIET opencv)
        endif()
    endif()
endif()

if(NOT OpenCV_FOUND)
    message(FATAL_ERROR
        "\n\n"
        "========================================================================\n"
        " [ERREUR] OpenCV developpement est introuvable sur cette machine !\n"
        " Pour l'installer sous Ubuntu / Debian (GCC 13+) :\n"
        "   sudo apt update && sudo apt install -y libopencv-dev libzmq3-dev libomp-dev\n"
        " Pour l'installer sous Arch Linux :\n"
        "   sudo pacman -S --needed opencv zeromq openmp\n"
        "========================================================================\n"
    )
endif()

# Détection de ZeroMQ via pkg-config ou recherche de bibliothèque standard
find_package(PkgConfig QUIET)
if(PKG_CONFIG_FOUND)
    pkg_check_modules(ZMQ QUIET libzmq)
endif()

if(NOT ZMQ_FOUND)
    find_path(ZMQ_INCLUDE_DIRS zmq.h PATHS /usr/include /usr/local/include)
    find_library(ZMQ_LIBRARIES NAMES zmq libzmq PATHS /usr/lib /usr/local/lib /usr/lib64)
endif()

if(NOT ZMQ_LIBRARIES)
    message(FATAL_ERROR "Bibliothèque ZeroMQ (libzmq) introuvable !")
endif()

# ==============================================================================
# --- CIBLE EXECUTABLE : vision_worker ---
# ==============================================================================
add_executable(vision_worker vision_worker.cpp)

target_compile_options(vision_worker PRIVATE
    ${EXTRA_OPT_FLAGS}
    ${OpenMP_CXX_FLAGS}
)

target_include_directories(vision_worker PRIVATE
    ${OpenCV_INCLUDE_DIRS}
    ${ZMQ_INCLUDE_DIRS}
)

# Composants OpenCV ciblés (évite VTK/viz et les dépendances inutiles)
set(CV_TARGET_LIBS opencv_core opencv_imgproc opencv_imgcodecs opencv_videoio)
foreach(lib opencv_objdetect opencv_aruco opencv_calib opencv_calib3d opencv_geometry)
    if(TARGET ${lib})
        list(APPEND CV_TARGET_LIBS ${lib})
    endif()
endforeach()

target_link_libraries(vision_worker PRIVATE
    ${CV_TARGET_LIBS}
    ${ZMQ_LIBRARIES}
    OpenMP::OpenMP_CXX
    Threads::Threads
)

# Placer l'exécutable compilé directement dans le dossier Vision/ pour un lancement immédiat
set_target_properties(vision_worker PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
