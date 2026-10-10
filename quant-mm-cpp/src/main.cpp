#include "avellaneda_stoikov.hpp"
#include "order_manager.hpp"
#include "socket_client.hpp"

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>

int main(int argc, char** argv) {
    std::string host = argc > 1 ? argv[1] : "localhost";
    uint16_t port = argc > 2 ? static_cast<uint16_t>(std::strtoul(argv[2], nullptr, 10)) : 8080;
    std::string symbol = argc > 3 ? argv[3] : "AAPL";
    std::string apiKey = argc > 4 ? argv[4] : "demo-key";

    mm::HttpClient client(host, port, apiKey);
    mm::OrderManager om;

    const double gamma = 0.01;
    const double sigma = 0.02;
    const double kappa = 1.5;
    const double horizon = 1.0;
    double inventory = 0.0;
    uint64_t buy_id = 0;
    uint64_t sell_id = 0;

    for (;;) {
        try {
            std::string ticker = client.get("/ticker?symbol=" + symbol);
            double last = mm::extract_number(ticker, "last_price");
            double best_bid = mm::extract_number(ticker, "best_bid");
            double best_ask = mm::extract_number(ticker, "best_ask");
            double mid = (best_bid > 0 && best_ask > 0) ? (best_bid + best_ask) / 2.0 : last;
            if (mid <= 0) {
                std::this_thread::sleep_for(std::chrono::seconds(1));
                continue;
            }

            mm::Quote q = mm::compute_quote(mid, inventory, gamma, sigma, kappa, horizon);

            // Cancel existing quotes before re-quoting.
            if (buy_id) {
                client.del("/orders?id=" + std::to_string(buy_id) + "&symbol=" + symbol);
                om.untrack(buy_id);
                buy_id = 0;
            }
            if (sell_id) {
                client.del("/orders?id=" + std::to_string(sell_id) + "&symbol=" + symbol);
                om.untrack(sell_id);
                sell_id = 0;
            }

            auto place = [&](const std::string& side, double price) -> uint64_t {
                std::string body = "{\"symbol\":\"" + symbol + "\",\"side\":\"" + side +
                                   "\",\"type\":\"LIMIT\",\"price\":\"" + std::to_string(price) +
                                   "\",\"quantity\":\"1\",\"time_in_force\":\"GTC\"}";
                std::string resp = client.post("/orders", body);
                uint64_t id = mm::extract_uint(resp, "order_id");
                if (id) om.track(id);
                return id;
            };

            buy_id = place("BUY", q.bid);
            sell_id = place("SELL", q.ask);
            std::cout << "[mm] " << symbol << " mid=" << mid
                      << " bid=" << q.bid << " ask=" << q.ask << std::endl;
        } catch (const std::exception& e) {
            std::cerr << "[mm] error: " << e.what() << std::endl;
        }
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    return 0;
}
