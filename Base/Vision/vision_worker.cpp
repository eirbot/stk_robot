/**
 * ============================================================================
 * @file    vision_worker.cpp
 * @brief   Module de vision zénithale Eurobot 2026 - 100% C++17 natif
 *          Détection ArUco 4K @ 30fps, calculs géométriques, serveur MJPEG HTTP
 *          (port 8082) et télémétrie ZeroMQ (5555/5556).
 *          Accélération AVX2 / OpenMP / multi-threading natif.
 * @author  Eirbot - Eurobot 2026
 * ============================================================================
 */

#include <iostream>
#include <sstream>
#include <iomanip>
#include <vector>
#include <string>
#include <map>
#include <memory>
#include <thread>
#include <mutex>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <csignal>

// OpenCV
#include <opencv2/core.hpp>
#include <opencv2/core/version.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/calib3d.hpp>
#include <opencv2/videoio.hpp>

// Compatibilité multi-versions OpenCV :
// OpenCV >= 4.7 et OpenCV 5.0 placent ArUco dans objdetect/aruco_detector.hpp
// OpenCV < 4.7 (ex: Ubuntu 24.04 avec libopencv-contrib-dev 4.6) le place dans opencv2/aruco.hpp
#if CV_VERSION_MAJOR > 4 || (CV_VERSION_MAJOR == 4 && CV_VERSION_MINOR >= 7)
    #define OPENCV_ARUCO_MODERN 1
    #include <opencv2/objdetect/aruco_detector.hpp>
#else
    #define OPENCV_ARUCO_MODERN 0
    #include <opencv2/aruco.hpp>
#endif

// OpenMP
#include <omp.h>

// ZeroMQ
#include <zmq.h>

// Sockets POSIX pour le serveur HTTP MJPEG ultra-rapide sans dépendance
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>

// ==============================================================================
// --- CONSTANTES ET GEOMETRIE EUROBOT (en mm) ---
// ==============================================================================
constexpr double LARGEUR_TABLE_X   = 3000.0;
constexpr double HAUTEUR_TABLE_Y   = 2000.0;
constexpr double HAUTEUR_CAMERA    = 2500.0;
constexpr double CENTRE_CAM_X      = 1500.0;
constexpr double CENTRE_CAM_Y      = 1000.0;
constexpr double HAUTEUR_TAG_ROBOT = 300.0;
constexpr double DEPART_ABS_X      = 200.0;
constexpr double DEPART_ABS_Y      = 200.0;

constexpr int TAG_ID_ROBOT = 2;

// ==============================================================================
// --- WRAPPER UNIFIE ARUCO : COMPATIBLE OPENCV 4.x (< 4.7) ET OPENCV 5.x / 4.7+
// ==============================================================================
class ArucoDetectorWrapper {
public:
    ArucoDetectorWrapper(int dict_id = cv::aruco::DICT_4X4_50) {
#if OPENCV_ARUCO_MODERN
        dict_ = cv::aruco::getPredefinedDictionary(dict_id);
        params_.adaptiveThreshWinSizeMin = 3;
        params_.adaptiveThreshWinSizeMax = 41;
        params_.adaptiveThreshWinSizeStep = 4;
        params_.minMarkerPerimeterRate = 0.005;
        params_.maxMarkerPerimeterRate = 4.0;
        params_.polygonalApproxAccuracyRate = 0.05;
        params_.cornerRefinementMethod = cv::aruco::CORNER_REFINE_NONE;
        detector_ = std::make_unique<cv::aruco::ArucoDetector>(dict_, params_);
#else
        dict_ = cv::aruco::getPredefinedDictionary(dict_id);
        params_ = cv::aruco::DetectorParameters::create();
        params_->adaptiveThreshWinSizeMin = 3;
        params_->adaptiveThreshWinSizeMax = 41;
        params_->adaptiveThreshWinSizeStep = 4;
        params_->minMarkerPerimeterRate = 0.005;
        params_->maxMarkerPerimeterRate = 4.0;
        params_->polygonalApproxAccuracyRate = 0.05;
        params_->cornerRefinementMethod = cv::aruco::CORNER_REFINE_NONE;
#endif
    }

    void detectMarkers(const cv::Mat& image,
                       std::vector<std::vector<cv::Point2f>>& corners,
                       std::vector<int>& ids,
                       std::vector<std::vector<cv::Point2f>>& rejected) {
#if OPENCV_ARUCO_MODERN
        detector_->detectMarkers(image, corners, ids, rejected);
#else
        cv::aruco::detectMarkers(image, dict_, corners, ids, params_, rejected);
#endif
    }

    void generateMarker(int id, int sidePixels, cv::Mat& out_marker) {
#if OPENCV_ARUCO_MODERN
        dict_.generateImageMarker(id, sidePixels, out_marker);
#else
        cv::aruco::drawMarker(dict_, id, sidePixels, out_marker);
#endif
    }

private:
#if OPENCV_ARUCO_MODERN
    cv::aruco::Dictionary dict_;
    cv::aruco::DetectorParameters params_;
    std::unique_ptr<cv::aruco::ArucoDetector> detector_;
#else
    cv::Ptr<cv::aruco::Dictionary> dict_;
    cv::Ptr<cv::aruco::DetectorParameters> params_;
#endif
};

struct CameraPreset {
    int width;
    int height;
    int fps;
    std::string label;
};

const std::map<std::string, CameraPreset> CAMERA_PRESETS = {
    {"4K",    {3840, 2160, 30, "4K @ 30fps"}},
    {"1080P", {1920, 1080, 60, "1080p @ 60fps"}},
    {"2K",    {2560, 1440, 30, "2K @ 30fps"}}
};

// ==============================================================================
// --- ETAT GLOBAL ET BUFFER DE STREAMING MULTI-THREAD ---
// ==============================================================================
std::atomic<bool> g_running{true};
std::atomic<bool> g_do_calibration{false};

void signal_handler(int signum) {
    (void)signum;
    std::cout << "\n[MAIN] Signal d'arrêt reçu, fermeture propre en cours...\n";
    g_running = false;
}

struct StreamFrameBuffer {
    mutable std::mutex mutex;
    std::vector<uchar> raw_jpeg;
    std::vector<uchar> annotated_jpeg;
    bool show_aruco = true;
    std::string current_preset = "4K";
    std::string preset_label = "4K @ 30fps";
    std::string pending_preset = "";
    double fps = 0.0;

    // Télémétrie
    bool connected = true;
    bool simulated = false;
    bool homography_ready = false;
    bool robot_detected = false;
    double robot_x = 0.0;
    double robot_y = 0.0;
    double robot_theta_deg = 0.0;
    double offset_x = 0.0;
    double offset_y = 0.0;
    std::vector<int> detected_ids;
    int width = 3840;
    int height = 2160;

    void update_frames(const std::vector<uchar>& raw,
                       const std::vector<uchar>& annot,
                       double current_fps,
                       bool sim, bool homo_ok, bool rob_ok,
                       double rx, double ry, double r_th_deg,
                       double ox, double oy,
                       const std::vector<int>& ids) {
        std::lock_guard<std::mutex> lock(mutex);
        raw_jpeg = raw;
        annotated_jpeg = annot;
        fps = current_fps;
        simulated = sim;
        homography_ready = homo_ok;
        robot_detected = rob_ok;
        robot_x = rx;
        robot_y = ry;
        robot_theta_deg = r_th_deg;
        offset_x = ox;
        offset_y = oy;
        detected_ids = ids;
    }

    std::vector<uchar> get_frame(int force_aruco) const {
        std::lock_guard<std::mutex> lock(mutex);
        bool use_annot = (force_aruco == 1) ? true :
                         (force_aruco == 0) ? false : show_aruco;
        if (use_annot) {
            return !annotated_jpeg.empty() ? annotated_jpeg : raw_jpeg;
        }
        return !raw_jpeg.empty() ? raw_jpeg : annotated_jpeg;
    }

    bool toggle_aruco(int state = -1) {
        std::lock_guard<std::mutex> lock(mutex);
        if (state == 1) show_aruco = true;
        else if (state == 0) show_aruco = false;
        else show_aruco = !show_aruco;
        return show_aruco;
    }

    std::string request_preset(const std::string& preset) {
        std::lock_guard<std::mutex> lock(mutex);
        std::string p = preset;
        for (auto& c : p) c = toupper(c);
        if (p.empty()) {
            p = (current_preset == "4K") ? "1080P" : "4K";
        }
        if (CAMERA_PRESETS.find(p) != CAMERA_PRESETS.end()) {
            pending_preset = p;
        }
        return !pending_preset.empty() ? pending_preset : current_preset;
    }

    std::string pop_pending_preset() {
        std::lock_guard<std::mutex> lock(mutex);
        std::string p = pending_preset;
        pending_preset.clear();
        return p;
    }

    void set_active_preset(const std::string& key, const std::string& label, int w, int h) {
        std::lock_guard<std::mutex> lock(mutex);
        current_preset = key;
        preset_label = label;
        width = w;
        height = h;
    }

    std::string get_status_json() const {
        std::lock_guard<std::mutex> lock(mutex);
        std::ostringstream ss;
        ss << std::fixed;
        ss << "{"
           << "\"connected\":" << (connected ? "true" : "false") << ","
           << "\"simulated\":" << (simulated ? "true" : "false") << ","
           << "\"homography_ready\":" << (homography_ready ? "true" : "false") << ","
           << "\"robot_detected\":" << (robot_detected ? "true" : "false") << ","
           << "\"robot_tag_id\":" << TAG_ID_ROBOT << ","
           << "\"robot_x\":" << std::setprecision(1) << robot_x << ","
           << "\"robot_y\":" << std::setprecision(1) << robot_y << ","
           << "\"robot_theta_deg\":" << std::setprecision(1) << robot_theta_deg << ","
           << "\"offset_x\":" << std::setprecision(1) << offset_x << ","
           << "\"offset_y\":" << std::setprecision(1) << offset_y << ","
           << "\"fps\":" << std::setprecision(1) << fps << ","
           << "\"show_aruco\":" << (show_aruco ? "true" : "false") << ","
           << "\"resolution\":\"" << current_preset << "\","
           << "\"resolution_label\":\"" << preset_label << "\","
           << "\"width\":" << width << ","
           << "\"height\":" << height << ","
           << "\"detected_ids\":[";
        for (size_t i = 0; i < detected_ids.size(); ++i) {
            ss << detected_ids[i] << (i + 1 < detected_ids.size() ? "," : "");
        }
        ss << "]}";
        return ss.str();
    }
};

static StreamFrameBuffer g_frame_buffer;

// ==============================================================================
// --- SERVEUR HTTP MJPEG / API REST EMBARQUE (PORT 8082) ---
// ==============================================================================
void handle_http_client(int client_sock) {
    char req_buf[2048];
    ssize_t bytes_read = recv(client_sock, req_buf, sizeof(req_buf) - 1, 0);
    if (bytes_read <= 0) {
        close(client_sock);
        return;
    }
    req_buf[bytes_read] = '\0';

    std::string request(req_buf);
    std::string method, path;
    {
        std::istringstream iss(request);
        iss >> method >> path;
    }

    auto send_all = [](int sock, const std::string& str) -> bool {
        const char* p = str.data();
        size_t rem = str.size();
        while (rem > 0) {
            ssize_t n = send(sock, p, rem, MSG_NOSIGNAL);
            if (n <= 0) return false;
            p += n;
            rem -= n;
        }
        return true;
    };

    auto send_binary = [](int sock, const std::vector<uchar>& data) -> bool {
        const char* p = reinterpret_cast<const char*>(data.data());
        size_t rem = data.size();
        while (rem > 0) {
            ssize_t n = send(sock, p, rem, MSG_NOSIGNAL);
            if (n <= 0) return false;
            p += n;
            rem -= n;
        }
        return true;
    };

    if (method == "OPTIONS") {
        std::string resp =
            "HTTP/1.1 200 OK\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            "Access-Control-Allow-Headers: *\r\n"
            "Content-Length: 0\r\n"
            "Connection: close\r\n\r\n";
        send_all(client_sock, resp);
        close(client_sock);
        return;
    }

    std::string base_path = path;
    std::string query = "";
    size_t q_pos = path.find('?');
    if (q_pos != std::string::npos) {
        base_path = path.substr(0, q_pos);
        query = path.substr(q_pos + 1);
    }

    if (base_path == "/stream" || base_path == "/stream_aruco" || base_path == "/stream_raw") {
        int force_aruco = -1;
        if (base_path == "/stream_aruco") force_aruco = 1;
        else if (base_path == "/stream_raw") force_aruco = 0;
        else if (query.find("aruco=1") != std::string::npos || query.find("aruco=true") != std::string::npos) force_aruco = 1;
        else if (query.find("aruco=0") != std::string::npos || query.find("aruco=false") != std::string::npos) force_aruco = 0;

        std::string header =
            "HTTP/1.1 200 OK\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Cache-Control: no-cache, private, no-store, must-revalidate\r\n"
            "Pragma: no-cache\r\n"
            "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
            "Connection: close\r\n\r\n";

        if (!send_all(client_sock, header)) {
            close(client_sock);
            return;
        }

        auto last_stream = std::chrono::steady_clock::now();
        while (g_running) {
            auto now = std::chrono::steady_clock::now();
            std::chrono::duration<double> diff = now - last_stream;
            if (diff.count() < 0.033) { // Max 30 FPS pour préserver la bande passante
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
                continue;
            }

            std::vector<uchar> frame_data = g_frame_buffer.get_frame(force_aruco);
            if (!frame_data.empty()) {
                std::string part_header =
                    "--frame\r\n"
                    "Content-Type: image/jpeg\r\n"
                    "Content-Length: " + std::to_string(frame_data.size()) + "\r\n\r\n";

                if (!send_all(client_sock, part_header) ||
                    !send_binary(client_sock, frame_data) ||
                    !send_all(client_sock, "\r\n")) {
                    break; // Client déconnecté
                }
                last_stream = now;
            } else {
                std::this_thread::sleep_for(std::chrono::milliseconds(30));
            }
        }
        close(client_sock);
        return;
    }
    else if (base_path == "/api/status") {
        std::string json_body = g_frame_buffer.get_status_json();
        std::string resp =
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Content-Length: " + std::to_string(json_body.size()) + "\r\n"
            "Connection: close\r\n\r\n" + json_body;
        send_all(client_sock, resp);
    }
    else if (base_path == "/api/toggle_aruco") {
        int st = -1;
        if (query.find("state=1") != std::string::npos || query.find("state=true") != std::string::npos) st = 1;
        else if (query.find("state=0") != std::string::npos || query.find("state=false") != std::string::npos) st = 0;
        bool cur = g_frame_buffer.toggle_aruco(st);
        std::string json_body = "{\"status\":\"ok\",\"show_aruco\":" + std::string(cur ? "true" : "false") + "}";
        std::string resp =
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Content-Length: " + std::to_string(json_body.size()) + "\r\n"
            "Connection: close\r\n\r\n" + json_body;
        send_all(client_sock, resp);
    }
    else if (base_path == "/api/toggle_resolution" || base_path == "/api/toggle_mode" || base_path == "/api/set_resolution") {
        std::string mode = "";
        size_t m_pos = query.find("mode=");
        if (m_pos != std::string::npos) {
            mode = query.substr(m_pos + 5);
            size_t amp = mode.find('&');
            if (amp != std::string::npos) mode = mode.substr(0, amp);
        }
        std::string req_preset = g_frame_buffer.request_preset(mode);
        std::string json_body = "{\"status\":\"ok\",\"requested\":\"" + req_preset + "\"}";
        std::string resp =
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Content-Length: " + std::to_string(json_body.size()) + "\r\n"
            "Connection: close\r\n\r\n" + json_body;
        send_all(client_sock, resp);
    }
    else {
        std::string resp =
            "HTTP/1.1 404 Not Found\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Content-Length: 0\r\n"
            "Connection: close\r\n\r\n";
        send_all(client_sock, resp);
    }

    close(client_sock);
}

void run_http_server(int port = 8082) {
    int server_sock = socket(AF_INET, SOCK_STREAM, 0);
    if (server_sock < 0) {
        std::cerr << "[HTTP] Erreur création socket serveur.\n";
        return;
    }

    int opt = 1;
    setsockopt(server_sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);

    if (bind(server_sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        std::cerr << "[HTTP] Erreur bind sur le port " << port << ".\n";
        close(server_sock);
        return;
    }

    if (listen(server_sock, 32) < 0) {
        std::cerr << "[HTTP] Erreur listen.\n";
        close(server_sock);
        return;
    }

    std::cout << "[STREAM] Serveur vidéo HTTP C++ démarré sur http://0.0.0.0:" << port << "/stream\n";

    // Configuration socket non-bloquante pour sortie propre lors du SIGINT
    int flags = fcntl(server_sock, F_GETFL, 0);
    fcntl(server_sock, F_SETFL, flags | O_NONBLOCK);

    while (g_running) {
        sockaddr_in client_addr{};
        socklen_t client_len = sizeof(client_addr);
        int client_sock = accept(server_sock, (struct sockaddr*)&client_addr, &client_len);

        if (client_sock < 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
            continue;
        }

        // Active TCP_NODELAY pour latence minimale du stream
        int flag = 1;
        setsockopt(client_sock, IPPROTO_TCP, TCP_NODELAY, (char*)&flag, sizeof(int));

        std::thread(handle_http_client, client_sock).detach();
    }

    close(server_sock);
}

// ==============================================================================
// --- THREAD ZEROMQ SUB (PORT 5556 : ORDRES DU SERVEUR GO) ---
// ==============================================================================
void run_zmq_sub_worker(void* zmq_ctx) {
    void* sub_socket = zmq_socket(zmq_ctx, ZMQ_SUB);
    if (!sub_socket) return;

    if (zmq_connect(sub_socket, "tcp://localhost:5556") != 0) {
        std::cerr << "[ZMQ SUB] Échec connexion port 5556\n";
        zmq_close(sub_socket);
        return;
    }
    zmq_setsockopt(sub_socket, ZMQ_SUBSCRIBE, "", 0);

    // Timeout de 200ms pour permettre l'arrêt propre
    int timeout_ms = 200;
    zmq_setsockopt(sub_socket, ZMQ_RCVTIMEO, &timeout_ms, sizeof(timeout_ms));

    std::cout << "[ZMQ SUB] Connecté au port 5556, écoute des ordres...\n";

    char buffer[2048];
    while (g_running) {
        int bytes = zmq_recv(sub_socket, buffer, sizeof(buffer) - 1, 0);
        if (bytes > 0) {
            buffer[bytes] = '\0';
            std::string msg(buffer);
            if (msg.find("calibrate_vision") != std::string::npos) {
                std::cout << "[ZMQ SUB] 🎯 Ordre 'calibrate_vision' reçu ! Flag de calibration levé.\n";
                g_do_calibration = true;
            }
        }
    }

    zmq_close(sub_socket);
}

// ==============================================================================
// --- APPLICATION DU PRESET CAMERA (PHYSIQUE / SIMULATION) ---
// ==============================================================================
void apply_preset(cv::VideoCapture& cap, const std::string& key,
                  int& frame_w, int& frame_h, std::string& preset_label,
                  bool simuler, cv::Mat& K, cv::Mat& D, cv::Mat& map1, cv::Mat& map2,
                  cv::Mat& homography, bool& has_homography) {
    auto it = CAMERA_PRESETS.find(key);
    if (it == CAMERA_PRESETS.end()) it = CAMERA_PRESETS.find("4K");
    const auto& cfg = it->second;

    int old_w = frame_w;
    int old_h = frame_h;
    int new_w = cfg.width;
    int new_h = cfg.height;

    if (!simuler && cap.isOpened()) {
        cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
        cap.set(cv::CAP_PROP_FRAME_WIDTH, new_w);
        cap.set(cv::CAP_PROP_FRAME_HEIGHT, new_h);
        cap.set(cv::CAP_PROP_FPS, cfg.fps);
        cap.set(cv::CAP_PROP_BUFFERSIZE, 1);
        int actual_w = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_WIDTH));
        int actual_h = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_HEIGHT));
        std::cout << "[CAM] 🔄 Résolution basculée sur " << it->first
                  << " : " << actual_w << "x" << actual_h << " @ " << cfg.fps << "fps\n";
        new_w = actual_w;
        new_h = actual_h;
    } else {
        std::cout << "[CAM] 🔄 Résolution simulée basculée sur " << it->first
                  << " : " << new_w << "x" << new_h << "\n";
    }

    frame_w = new_w;
    frame_h = new_h;
    preset_label = cfg.label;

    double scale = static_cast<double>(frame_w) / 3840.0;
    double k_data[9] = {
        3000.0 * scale, 0.0,            frame_w / 2.0,
        0.0,            3000.0 * scale, frame_h / 2.0,
        0.0,            0.0,            1.0
    };
    K = cv::Mat(3, 3, CV_64F, k_data).clone();

    double d_data[5] = { -0.1, 0.05, 0.0, 0.0, -0.01 };
    D = cv::Mat(1, 5, CV_64F, d_data).clone();

    cv::initUndistortRectifyMap(K, D, cv::Mat(), K, cv::Size(frame_w, frame_h),
                                CV_16SC2, map1, map2);

    if (has_homography && old_w > 0 && old_h > 0 && (old_w != frame_w || old_h != frame_h)) {
        double sx = static_cast<double>(frame_w) / old_w;
        double sy = static_cast<double>(frame_h) / old_h;
        double s_data[9] = {
            1.0 / sx, 0.0,      0.0,
            0.0,      1.0 / sy, 0.0,
            0.0,      0.0,      1.0
        };
        cv::Mat S_inv(3, 3, CV_64F, s_data);
        homography = homography * S_inv;
    }

    g_frame_buffer.set_active_preset(it->first, cfg.label, frame_w, frame_h);
}

// ==============================================================================
// --- MAIN PIPELINE DE VISION C++ HAUTE PERFORMANCE ---
// ==============================================================================
int main(int argc, char** argv) {
    (void)argc; (void)argv;
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    signal(SIGPIPE, SIG_IGN); // Empêche l'arrêt du programme lors de déconnexion client HTTP

    // Activation de toutes les optimisations CPU et threads OpenCV
    cv::setUseOptimized(true);
    cv::setNumThreads(std::max(4u, std::thread::hardware_concurrency()));

    std::cout << "=========================================================\n";
    std::cout << "   EIRBOT VISION 4K - MODULE NATIF C++17 ULTRA-OPTIMISE   \n";
    std::cout << "   OpenCV " << CV_VERSION << " | OpenMP " << _OPENMP << " | AVX2 & FMA\n";
    std::cout << "=========================================================\n";

    // Initialisation du contexte ZeroMQ
    void* zmq_ctx = zmq_ctx_new();

    // Socket PUSH pour publier la télémétrie vers le serveur Go (Port 5555)
    void* push_socket = zmq_socket(zmq_ctx, ZMQ_PUSH);
    zmq_connect(push_socket, "tcp://localhost:5555");
    std::cout << "[ZMQ PUSH] Canal télémétrie connecté sur port 5555.\n";

    // Démarrage des threads en tâche de fond (ZMQ SUB et HTTP MJPEG)
    std::thread th_zmq_sub(run_zmq_sub_worker, zmq_ctx);
    std::thread th_http(run_http_server, 8082);

    // Initialisation de la caméra USB V4L2
    cv::VideoCapture cap(0, cv::CAP_V4L2);
    if (!cap.isOpened()) {
        cap.open(0);
    }

    bool simuler_flux = false;
    int frame_w = 3840;
    int frame_h = 2160;
    std::string current_preset_key = "4K";
    std::string current_preset_label = "4K @ 30fps";

    if (!cap.isOpened()) {
        std::cout << "[CAM] ⚠️  Impossible d'ouvrir la caméra physique (/dev/video0). Passage en SIMULATION.\n";
        simuler_flux = true;
    } else {
        cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
        cap.set(cv::CAP_PROP_FRAME_WIDTH, 3840);
        cap.set(cv::CAP_PROP_FRAME_HEIGHT, 2160);
        cap.set(cv::CAP_PROP_FPS, 30);
        cap.set(cv::CAP_PROP_BUFFERSIZE, 1);
        frame_w = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_WIDTH));
        frame_h = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_HEIGHT));
        std::cout << "[CAM] ✅ Caméra physique USB connectée (" << frame_w << "x" << frame_h
                  << " @ " << static_cast<int>(cap.get(cv::CAP_PROP_FPS)) << "fps).\n";
    }

    // Coordonnées physiques des tags vinyle Eurobot (en mm)
    const std::map<int, cv::Point2f> tags_vinyle = {
        {10, {1000.0f, 1500.0f}}, // Haut-Gauche
        {11, {2000.0f, 1500.0f}}, // Haut-Droite
        {12, {2000.0f, 500.0f}},  // Bas-Droite
        {13, {1000.0f, 500.0f}}   // Bas-Gauche
    };

    // Matrices intrinsèques et tables de remap
    cv::Mat K, D, map1, map2, homography;
    bool has_homography = false;
    apply_preset(cap, current_preset_key, frame_w, frame_h, current_preset_label,
                 simuler_flux, K, D, map1, map2, homography, has_homography);

    // Initialisation du détecteur ArUco unifié (compatible OpenCV 4.x et OpenCV 5.x)
    ArucoDetectorWrapper aruco(cv::aruco::DICT_4X4_50);

    // Buffers réutilisés (zéro allocation à chaque frame)
    cv::Mat frame_raw, frame_undistorted, frame_annotated;
    cv::Mat down_raw, down_annot;
    std::vector<uchar> buf_raw_jpeg, buf_annot_jpeg;
    buf_raw_jpeg.reserve(512 * 1024);
    buf_annot_jpeg.reserve(512 * 1024);

    double offset_x = 0.0;
    double offset_y = 0.0;
    double fps_calc = 30.0;
    double t_simu = 0.0;

    std::cout << "[MAIN] Pipeline de vision zénithale C++ opérationnel.\n";

    while (g_running) {
        auto t_start = std::chrono::steady_clock::now();

        // 1. Vérification d'une demande de bascule de résolution
        std::string pending = g_frame_buffer.pop_pending_preset();
        if (!pending.empty()) {
            current_preset_key = pending;
            apply_preset(cap, current_preset_key, frame_w, frame_h, current_preset_label,
                         simuler_flux, K, D, map1, map2, homography, has_homography);
        }

        // 2. Acquisition de la frame (physique ou synthétique)
        if (simuler_flux) {
            frame_raw = cv::Mat::zeros(frame_h, frame_w, CV_8UC3);
            double scale_sim = static_cast<double>(frame_w) / 3840.0;

            const std::map<int, cv::Point> pts_sim = {
                {10, {static_cast<int>(1200 * scale_sim), static_cast<int>(480 * scale_sim)}},
                {11, {static_cast<int>(2640 * scale_sim), static_cast<int>(480 * scale_sim)}},
                {12, {static_cast<int>(2640 * scale_sim), static_cast<int>(1680 * scale_sim)}},
                {13, {static_cast<int>(1200 * scale_sim), static_cast<int>(1680 * scale_sim)}}
            };

            for (const auto& kv : pts_sim) {
                cv::Mat marker_img;
                aruco.generateMarker(kv.first, static_cast<int>(100 * scale_sim), marker_img);
                cv::Mat marker_bgr;
                cv::cvtColor(marker_img, marker_bgr, cv::COLOR_GRAY2BGR);
                int sz = marker_bgr.rows;
                int x = kv.second.x - sz / 2;
                int y = kv.second.y - sz / 2;
                if (x >= 0 && y >= 0 && x + sz < frame_w && y + sz < frame_h) {
                    marker_bgr.copyTo(frame_raw(cv::Rect(x, y, sz, sz)));
                }
            }

            // Déplacement circulaire simulé du robot
            double sim_x_phys = 200.0 + 80.0 * std::sin(t_simu);
            double sim_y_phys = 200.0 + 50.0 * std::cos(t_simu);
            double sim_theta = -t_simu;
            t_simu += 0.05;

            int x_img = static_cast<int>((sim_x_phys - 1000.0) * 1.44 * scale_sim + 1200.0 * scale_sim);
            int y_img = static_cast<int>((1500.0 - sim_y_phys) * 1.2 * scale_sim + 480.0 * scale_sim);

            cv::Mat rob_marker;
            aruco.generateMarker(TAG_ID_ROBOT, static_cast<int>(80 * scale_sim), rob_marker);
            cv::Mat M_rot = cv::getRotationMatrix2D(cv::Point2f(40 * scale_sim, 40 * scale_sim),
                                                   sim_theta * 180.0 / M_PI, 1.0);
            cv::Mat rob_rot;
            cv::warpAffine(rob_marker, rob_rot, M_rot, cv::Size(rob_marker.cols, rob_marker.rows),
                           cv::INTER_LINEAR, cv::BORDER_CONSTANT, cv::Scalar(0));
            cv::Mat rob_bgr;
            cv::cvtColor(rob_rot, rob_bgr, cv::COLOR_GRAY2BGR);

            int r_sz = rob_bgr.rows;
            int rx_top = x_img - r_sz / 2;
            int ry_top = y_img - r_sz / 2;
            if (rx_top >= 0 && ry_top >= 0 && rx_top + r_sz < frame_w && ry_top + r_sz < frame_h) {
                rob_bgr.copyTo(frame_raw(cv::Rect(rx_top, ry_top, r_sz, r_sz)));
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(30));
        } else {
            if (!cap.read(frame_raw) || frame_raw.empty()) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }
        }

        // 3. Correction de distorsion optique par tables pré-calculées (AVX2)
        cv::remap(frame_raw, frame_undistorted, map1, map2, cv::INTER_LINEAR);

        // 4. Détection ArUco
        std::vector<std::vector<cv::Point2f>> corners, rejected;
        std::vector<int> ids;
        aruco.detectMarkers(frame_undistorted, corners, ids, rejected);

        frame_undistorted.copyTo(frame_annotated);

        double scale_ui = std::max(1.0, static_cast<double>(frame_w) / 1920.0);
        bool robot_trouve = false;
        double x_final = 0.0;
        double y_final = 0.0;
        double theta_rad = 0.0;
        std::vector<int> detected_id_list;

        if (!ids.empty()) {
            detected_id_list = ids;

            // Dessin des contours de tags
            for (size_t i = 0; i < corners.size(); ++i) {
                const auto& c = corners[i];
                std::vector<cv::Point> pts = {
                    cv::Point(static_cast<int>(c[0].x), static_cast<int>(c[0].y)),
                    cv::Point(static_cast<int>(c[1].x), static_cast<int>(c[1].y)),
                    cv::Point(static_cast<int>(c[2].x), static_cast<int>(c[2].y)),
                    cv::Point(static_cast<int>(c[3].x), static_cast<int>(c[3].y))
                };
                cv::polylines(frame_annotated, pts, true, cv::Scalar(0, 255, 0),
                              std::max(2, static_cast<int>(3 * scale_ui)));

                int tag_id = ids[i];
                cv::Point corner_pt(pts[0].x, std::max(static_cast<int>(25 * scale_ui),
                                                       pts[0].y - static_cast<int>(10 * scale_ui)));
                cv::putText(frame_annotated, "#" + std::to_string(tag_id), corner_pt,
                            cv::FONT_HERSHEY_SIMPLEX, 0.75 * scale_ui,
                            cv::Scalar(0, 255, 128), std::max(2, static_cast<int>(2 * scale_ui)));
            }

            // Calcul de l'homographie de la table si les 4 tags sont visibles
            std::map<int, cv::Point2f> detectes;
            for (size_t i = 0; i < ids.size(); ++i) {
                int id = ids[i];
                if (tags_vinyle.find(id) != tags_vinyle.end()) {
                    const auto& coin = corners[i];
                    cv::Point2f centre = (coin[0] + coin[1] + coin[2] + coin[3]) * 0.25f;
                    detectes[id] = centre;
                }
            }

            if (detectes.size() == 4) {
                std::vector<cv::Point2f> pts_img;
                std::vector<cv::Point2f> pts_phys;
                for (const auto& kv : tags_vinyle) {
                    pts_img.push_back(detectes[kv.first]);
                    pts_phys.push_back(kv.second);
                }
                cv::Mat H = cv::findHomography(pts_img, pts_phys);
                if (!H.empty()) {
                    homography = H;
                    has_homography = true;
                }
            }

            // Annotation des tags vinyles
            for (size_t i = 0; i < ids.size(); ++i) {
                int tag_id = ids[i];
                if (tags_vinyle.find(tag_id) != tags_vinyle.end()) {
                    const auto& coin = corners[i];
                    cv::Point2f centre = (coin[0] + coin[1] + coin[2] + coin[3]) * 0.25f;
                    cv::Point c_pt(static_cast<int>(centre.x), static_cast<int>(centre.y));
                    int r_c = static_cast<int>(12 * scale_ui);
                    cv::circle(frame_annotated, c_pt, r_c, cv::Scalar(255, 255, 0), -1);
                    cv::circle(frame_annotated, c_pt, r_c + static_cast<int>(4 * scale_ui),
                               cv::Scalar(0, 180, 255), std::max(1, static_cast<int>(2 * scale_ui)));
                    cv::putText(frame_annotated, "TABLE #" + std::to_string(tag_id),
                                cv::Point(c_pt.x + static_cast<int>(18 * scale_ui), c_pt.y - static_cast<int>(10 * scale_ui)),
                                cv::FONT_HERSHEY_SIMPLEX, 0.85 * scale_ui, cv::Scalar(255, 255, 0),
                                std::max(2, static_cast<int>(2.5 * scale_ui)));
                }
            }

            // Calcul de la position du robot (Tag TAG_ID_ROBOT)
            int robot_idx = -1;
            for (size_t i = 0; i < ids.size(); ++i) {
                if (ids[i] == TAG_ID_ROBOT) {
                    robot_idx = static_cast<int>(i);
                    break;
                }
            }

            if (robot_idx != -1) {
                robot_trouve = true;
                const auto& coins_robot = corners[robot_idx];
                cv::Point2f centre_image = (coins_robot[0] + coins_robot[1] + coins_robot[2] + coins_robot[3]) * 0.25f;
                cv::Point2f devant_image = (coins_robot[0] + coins_robot[1]) * 0.5f;

                double theta_deg = 0.0;

                if (has_homography) {
                    std::vector<cv::Point2f> pts_proj = { centre_image, devant_image };
                    std::vector<cv::Point2f> pts_monde_brut;
                    cv::perspectiveTransform(pts_proj, pts_monde_brut, homography);

                    double x_brut = pts_monde_brut[0].x;
                    double y_brut = pts_monde_brut[0].y;
                    double x_devant_brut = pts_monde_brut[1].x;
                    double y_devant_brut = pts_monde_brut[1].y;

                    // Correction de parallaxe de Thalès
                    double ratio = 1.0 - (HAUTEUR_TAG_ROBOT / HAUTEUR_CAMERA);
                    double x_parallaxe = CENTRE_CAM_X + (x_brut - CENTRE_CAM_X) * ratio;
                    double y_parallaxe = CENTRE_CAM_Y + (y_brut - CENTRE_CAM_Y) * ratio;
                    double x_devant_parallaxe = CENTRE_CAM_X + (x_devant_brut - CENTRE_CAM_X) * ratio;
                    double y_devant_parallaxe = CENTRE_CAM_Y + (y_devant_brut - CENTRE_CAM_Y) * ratio;

                    double dx = x_devant_parallaxe - x_parallaxe;
                    double dy = y_devant_parallaxe - y_parallaxe;
                    theta_rad = std::atan2(dy, dx);
                    theta_deg = theta_rad * 180.0 / M_PI;

                    if (g_do_calibration.load()) {
                        offset_x = DEPART_ABS_X - x_parallaxe;
                        offset_y = DEPART_ABS_Y - y_parallaxe;
                        g_do_calibration = false;
                        std::cout << "[VISION WORKER] 🎯 Calibration réussie ! Offsets : DX = "
                                  << offset_x << " mm, DY = " << offset_y << " mm\n";
                    }

                    x_final = x_parallaxe + offset_x;
                    y_final = y_parallaxe + offset_y;
                } else {
                    // Mode sans homographie vinyle préalable :
                    // Calcul de l'angle direct dans l'image et position métrique estimée
                    double dx = devant_image.x - centre_image.x;
                    double dy = devant_image.y - centre_image.y;
                    theta_rad = std::atan2(-dy, dx);
                    theta_deg = theta_rad * 180.0 / M_PI;

                    x_final = (centre_image.x / static_cast<double>(frame_w)) * LARGEUR_TABLE_X;
                    y_final = (1.0 - (centre_image.y / static_cast<double>(frame_h))) * HAUTEUR_TABLE_Y;
                }

                // Envoi ZeroMQ PUSH vers le serveur Go (type dédié vision_update avec theta en degrés)
                char zmq_msg[256];
                snprintf(zmq_msg, sizeof(zmq_msg),
                         "{\"type\":\"vision_update\",\"data\":{\"x\":%.2f,\"y\":%.2f,\"theta\":%.2f,\"detected\":true}}",
                         x_final, y_final, theta_deg);
                zmq_send(push_socket, zmq_msg, strlen(zmq_msg), ZMQ_DONTWAIT);

                // Tracé overlay du robot
                cv::Point pt_centre(static_cast<int>(centre_image.x), static_cast<int>(centre_image.y));
                cv::Point pt_devant(static_cast<int>(devant_image.x), static_cast<int>(devant_image.y));

                double v_dx = pt_devant.x - pt_centre.x;
                double v_dy = pt_devant.y - pt_centre.y;
                double v_len = std::hypot(v_dx, v_dy);
                cv::Point pt_arrow = pt_devant;
                if (v_len > 0.0) {
                    double tgt_len = 110.0 * scale_ui;
                    pt_arrow = cv::Point(static_cast<int>(pt_centre.x + (v_dx / v_len) * tgt_len),
                                         static_cast<int>(pt_centre.y + (v_dy / v_len) * tgt_len));
                }

                cv::circle(frame_annotated, pt_centre, static_cast<int>(15 * scale_ui), cv::Scalar(0, 255, 255), -1);
                cv::arrowedLine(frame_annotated, pt_centre, pt_arrow, cv::Scalar(0, 255, 255),
                                std::max(3, static_cast<int>(6 * scale_ui)), 8, 0, 0.25);

                std::ostringstream ss_rob;
                ss_rob << std::fixed << std::setprecision(0);
                if (has_homography) {
                    ss_rob << "ROBOT #" << TAG_ID_ROBOT << " : X=" << x_final << " Y=" << y_final
                           << " O=" << std::setprecision(1) << theta_deg << "deg";
                } else {
                    ss_rob << "ROBOT #" << TAG_ID_ROBOT << " [SANS TABLE] : X=" << x_final << " Y=" << y_final
                           << " O=" << std::setprecision(1) << theta_deg << "deg";
                }
                std::string label_robot = ss_rob.str();

                int baseline = 0;
                cv::Size t_sz = cv::getTextSize(label_robot, cv::FONT_HERSHEY_SIMPLEX,
                                                0.85 * scale_ui, std::max(2, static_cast<int>(2.5 * scale_ui)), &baseline);
                cv::Point lbl_pos(pt_centre.x - static_cast<int>(120 * scale_ui),
                                  pt_centre.y - static_cast<int>(35 * scale_ui));
                cv::Rect bg_rect(lbl_pos.x - 8, lbl_pos.y - t_sz.height - 8, t_sz.width + 16, t_sz.height + 16);
                bg_rect = bg_rect & cv::Rect(0, 0, frame_w, frame_h);
                if (bg_rect.width > 0 && bg_rect.height > 0) {
                    cv::rectangle(frame_annotated, bg_rect, cv::Scalar(12, 16, 20), -1);
                    cv::rectangle(frame_annotated, bg_rect, cv::Scalar(0, 255, 255), std::max(1, static_cast<int>(1.5 * scale_ui)));
                    cv::putText(frame_annotated, label_robot, lbl_pos, cv::FONT_HERSHEY_SIMPLEX,
                                0.85 * scale_ui, cv::Scalar(0, 255, 255), std::max(2, static_cast<int>(2.5 * scale_ui)));
                }
            }
        }

        // Calcul FPS glissant
        auto t_end = std::chrono::steady_clock::now();
        std::chrono::duration<double> dt = t_end - t_start;
        if (dt.count() > 0.0) {
            fps_calc = 0.9 * fps_calc + 0.1 * (1.0 / dt.count());
        }

        // 5. Bandeau HUD synthétique (optimisation ROI alpha blend)
        int hud_x = static_cast<int>(20 * scale_ui);
        int hud_y = static_cast<int>(20 * scale_ui);
        int hud_w = static_cast<int>(760 * scale_ui);
        int hud_h = static_cast<int>(165 * scale_ui);
        cv::Rect hud_rect(hud_x, hud_y, hud_w, hud_h);
        hud_rect = hud_rect & cv::Rect(0, 0, frame_w, frame_h);
        if (hud_rect.width > 0 && hud_rect.height > 0) {
            cv::Mat roi = frame_annotated(hud_rect);
            cv::Mat dark_bg(roi.size(), CV_8UC3, cv::Scalar(12, 16, 20));
            cv::addWeighted(dark_bg, 0.82, roi, 0.18, 0.0, roi);
            cv::rectangle(frame_annotated, hud_rect, cv::Scalar(0, 210, 255), std::max(2, static_cast<int>(2.5 * scale_ui)));

            double f_scale_main = 0.90 * scale_ui;
            double f_scale_sub  = 0.72 * scale_ui;
            int th_main = std::max(2, static_cast<int>(2.5 * scale_ui));
            int th_sub  = std::max(2, static_cast<int>(2.0 * scale_ui));

            std::ostringstream ss_hud_fps;
            ss_hud_fps << std::fixed << std::setprecision(1)
                       << "CAM USB - " << fps_calc << " FPS [" << current_preset_key << " " << frame_w << "x" << frame_h << "]";
            cv::putText(frame_annotated, ss_hud_fps.str(),
                        cv::Point(hud_x + static_cast<int>(20 * scale_ui), hud_y + static_cast<int>(45 * scale_ui)),
                        cv::FONT_HERSHEY_SIMPLEX, f_scale_main, cv::Scalar(0, 210, 255), th_main);

            std::string homo_txt = has_homography ?
                "HOMOGRAPHIE: 4/4 TAGS OK (CALIBRE)" :
                "ATTENTE VINYLES (" + std::to_string(detected_id_list.size()) + "/4 tags vus)";
            cv::Scalar homo_col = has_homography ? cv::Scalar(0, 255, 128) : cv::Scalar(0, 165, 255);
            cv::putText(frame_annotated, homo_txt,
                        cv::Point(hud_x + static_cast<int>(20 * scale_ui), hud_y + static_cast<int>(92 * scale_ui)),
                        cv::FONT_HERSHEY_SIMPLEX, f_scale_sub, homo_col, th_sub);

            std::ostringstream ss_hud_rob;
            ss_hud_rob << std::fixed << std::setprecision(0);
            if (robot_trouve) {
                if (has_homography) {
                    ss_hud_rob << "ROBOT: DETECTE (X=" << x_final << " Y=" << y_final << ")";
                } else {
                    ss_hud_rob << "ROBOT: VU [SANS TABLE] (X=" << x_final << " Y=" << y_final << ")";
                }
            } else {
                ss_hud_rob << "ROBOT: NON DETECTE (Tag #" << TAG_ID_ROBOT << ")";
            }
            cv::Scalar rob_col = robot_trouve ? cv::Scalar(0, 255, 128) : cv::Scalar(0, 165, 255);
            cv::putText(frame_annotated, ss_hud_rob.str(),
                        cv::Point(hud_x + static_cast<int>(20 * scale_ui), hud_y + static_cast<int>(138 * scale_ui)),
                        cv::FONT_HERSHEY_SIMPLEX, f_scale_sub, rob_col, th_sub);
        }

        // 6. Encodage JPEG OpenMP multi-thread et downscaling vers Full HD (1920 max)
        std::vector<int> encode_params = { cv::IMWRITE_JPEG_QUALITY, 80 };
        bool downscale = (frame_w > 1920);
        cv::Size target_sz(1920, static_cast<int>(frame_h * (1920.0 / frame_w)));

        #pragma omp parallel sections
        {
            #pragma omp section
            {
                if (downscale) {
                    cv::resize(frame_undistorted, down_raw, target_sz, 0, 0, cv::INTER_LINEAR);
                    cv::imencode(".jpg", down_raw, buf_raw_jpeg, encode_params);
                } else {
                    cv::imencode(".jpg", frame_undistorted, buf_raw_jpeg, encode_params);
                }
            }
            #pragma omp section
            {
                if (downscale) {
                    cv::resize(frame_annotated, down_annot, target_sz, 0, 0, cv::INTER_LINEAR);
                    cv::imencode(".jpg", down_annot, buf_annot_jpeg, encode_params);
                } else {
                    cv::imencode(".jpg", frame_annotated, buf_annot_jpeg, encode_params);
                }
            }
        }

        // 7. Mise à jour du buffer de streaming partagé
        g_frame_buffer.update_frames(buf_raw_jpeg, buf_annot_jpeg, fps_calc,
                                     simuler_flux, has_homography, robot_trouve,
                                     x_final, y_final, theta_rad * 180.0 / M_PI,
                                     offset_x, offset_y, detected_id_list);
    }

    std::cout << "[MAIN] Nettoyage des ressources...\n";
    if (cap.isOpened()) cap.release();
    zmq_close(push_socket);
    zmq_ctx_term(zmq_ctx);

    if (th_zmq_sub.joinable()) th_zmq_sub.join();
    if (th_http.joinable()) th_http.join();

    std::cout << "[MAIN] Vision worker terminé avec succès.\n";
    return 0;
}
