#pragma once

#include <cstdint>
#include <unordered_set>

namespace mm {

// Tracks the market-maker's currently open orders.
class OrderManager {
public:
    void track(uint64_t id) { open_.insert(id); }
    void untrack(uint64_t id) { open_.erase(id); }
    bool is_open(uint64_t id) const { return open_.count(id) > 0; }
    const std::unordered_set<uint64_t>& open() const { return open_; }

private:
    std::unordered_set<uint64_t> open_;
};

} // namespace mm
