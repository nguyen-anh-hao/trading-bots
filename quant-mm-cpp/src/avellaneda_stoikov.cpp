#include "avellaneda_stoikov.hpp"

#include <cmath>

namespace mm {

Quote compute_quote(double mid, double inventory, double gamma, double sigma,
                   double kappa, double time_horizon) {
    // Reservation price: mid shifted away from the current inventory to
    // incentivize mean-reversion of the position.
    double reservation = mid - inventory * gamma * sigma * sigma * time_horizon;
    // Optimal spread (in absolute price units).
    double spread = gamma * sigma * sigma * time_horizon
                    + (2.0 / gamma) * std::log(1.0 + gamma / kappa);
    Quote q;
    q.reservation = reservation;
    q.spread = spread;
    q.bid = reservation - spread / 2.0;
    q.ask = reservation + spread / 2.0;
    return q;
}

} // namespace mm
