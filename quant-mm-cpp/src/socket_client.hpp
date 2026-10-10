#pragma once

#include <cstdint>
#include <string>

namespace mm {

// Minimal blocking HTTP client used by the market-maker bot (Winsock on
// Windows, POSIX sockets elsewhere). It injects the X-API-Key auth header.
class HttpClient {
public:
    HttpClient(std::string host, uint16_t port, std::string api_key);

    std::string get(const std::string& path);
    std::string post(const std::string& path, const std::string& body);
    std::string del(const std::string& path);

private:
    std::string request(const std::string& method, const std::string& path,
                        const std::string& body);

    std::string host_;
    uint16_t port_;
    std::string api_key_;
};

// Tiny JSON helpers for the flat JSON payloads returned by the gateway.
std::string extract_string(const std::string& json, const std::string& key);
double extract_number(const std::string& json, const std::string& key);
uint64_t extract_uint(const std::string& json, const std::string& key);

} // namespace mm
