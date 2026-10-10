#include "socket_client.hpp"

#include <cctype>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <utility>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
using sock_t = SOCKET;
#define BAD_SOCKET INVALID_SOCKET
#else
#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
using sock_t = int;
#define BAD_SOCKET (-1)
#define closesocket close
#endif

namespace mm {

namespace {
void ensure_wsa() {
#ifdef _WIN32
    static bool init = [] {
        WSADATA d;
        WSAStartup(MAKEWORD(2, 2), &d);
        return true;
    }();
    (void)init;
#endif
}
} // namespace

HttpClient::HttpClient(std::string host, uint16_t port, std::string api_key)
    : host_(std::move(host)), port_(port), api_key_(std::move(api_key)) {}

std::string HttpClient::request(const std::string& method, const std::string& path,
                                const std::string& body) {
    ensure_wsa();

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    addrinfo* res = nullptr;
    std::string port_str = std::to_string(port_);
    if (getaddrinfo(host_.c_str(), port_str.c_str(), &hints, &res) != 0 || res == nullptr) {
        throw std::runtime_error("getaddrinfo failed for " + host_);
    }

    sock_t s = ::socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (s == BAD_SOCKET) {
        freeaddrinfo(res);
        throw std::runtime_error("socket() failed");
    }
    if (::connect(s, res->ai_addr, static_cast<int>(res->ai_addrlen)) != 0) {
        closesocket(s);
        freeaddrinfo(res);
        throw std::runtime_error("connect() failed to " + host_);
    }
    freeaddrinfo(res);

    std::string req = method + " " + path + " HTTP/1.1\r\n"
                      "Host: " + host_ + "\r\n"
                      "X-API-Key: " + api_key_ + "\r\n"
                      "Connection: close\r\n";
    if (!body.empty()) {
        req += "Content-Type: application/json\r\n"
               "Content-Length: " + std::to_string(body.size()) + "\r\n";
    }
    req += "\r\n" + body;

    size_t sent = 0;
    while (sent < req.size()) {
        int n = static_cast<int>(::send(s, req.data() + sent, static_cast<int>(req.size() - sent), 0));
        if (n <= 0) {
            closesocket(s);
            throw std::runtime_error("send() failed");
        }
        sent += static_cast<size_t>(n);
    }

    std::string resp;
    char buf[4096];
    int n = 0;
    while ((n = static_cast<int>(::recv(s, buf, sizeof(buf), 0))) > 0) {
        resp.append(buf, static_cast<size_t>(n));
    }
    closesocket(s);

    size_t pos = resp.find("\r\n\r\n");
    return pos == std::string::npos ? "" : resp.substr(pos + 4);
}

std::string HttpClient::get(const std::string& path) { return request("GET", path, ""); }
std::string HttpClient::post(const std::string& path, const std::string& body) { return request("POST", path, body); }
std::string HttpClient::del(const std::string& path) { return request("DELETE", path, ""); }

std::string extract_string(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\"";
    size_t p = json.find(needle);
    if (p == std::string::npos) return "";
    size_t colon = json.find(':', p + needle.size());
    if (colon == std::string::npos) return "";
    size_t q = colon + 1;
    while (q < json.size() && std::isspace(static_cast<unsigned char>(json[q]))) ++q;
    if (q < json.size() && json[q] == '"') {
        size_t end = json.find('"', q + 1);
        return end == std::string::npos ? "" : json.substr(q + 1, end - q - 1);
    }
    size_t end = q;
    while (end < json.size() && json[end] != ',' && json[end] != '}' && json[end] != ']') ++end;
    return json.substr(q, end - q);
}

double extract_number(const std::string& json, const std::string& key) {
    std::string v = extract_string(json, key);
    if (v.empty()) return 0.0;
    return std::strtod(v.c_str(), nullptr);
}

uint64_t extract_uint(const std::string& json, const std::string& key) {
    std::string v = extract_string(json, key);
    if (v.empty()) return 0;
    return std::strtoull(v.c_str(), nullptr, 10);
}

} // namespace mm
