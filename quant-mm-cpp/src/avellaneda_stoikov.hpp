#pragma once

namespace mm {

struct Quote {
    double bid = 0.0;
    double ask = 0.0;
    double reservation = 0.0;
    double spread = 0.0;
};

// Avellaneda-Stoikov market making: computes the reservation price and the
// optimal spread around the mid price given current inventory and the risk
// aversion gamma.
Quote compute_quote(double mid, double inventory, double gamma, double sigma,
                   double kappa, double time_horizon);

} // namespace mm
