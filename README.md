# 📈 Optimal Order Placement Backtest

This project implements and extends the static order allocation model from **Cont & Kukanov (2013)** to simulate and evaluate optimal order placement strategies in fragmented limit order markets. Using historical L1 order book data, the simulator computes execution costs and compares optimized allocation against baseline strategies such as **TWAP**, **VWAP**, and **Best Ask**.

> “We calibrate the parameters λ_over, λ_under, and θ_queue based on empirical backtesting to minimize total execution cost.”  
> — *Cont & Kukanov (2013)*

---

## 🧠 Model Summary

Cont & Kukanov formulate a convex optimization problem to split a parent order (`S`) into market and limit orders across multiple venues. Each venue has:
- Initial queue size `Q_k`, outflow uncertainty `ξ_k`
- Fee `f_k`, Rebate `r_k`
- Execution uncertainty modeled via risk penalties (θ), underfill (λ_u), and overfill (λ_o)

The goal is to **minimize total expected cost**, factoring in partial fills and market impact.

---

## 🔧 Code Structure

The project follows a clear pipeline for simulating and comparing execution strategies:

### 🔹 1. Preprocessing
- **`preprocess_data(filepath)`**  
  → Loads and cleans raw L1 data; drops duplicates per timestamp and venue.

- **`get_venue_snapshot(df, timestamp)`**  
  → Extracts venue-level snapshot (price, size, fee/rebate) at a given timestamp.

### 🔹 2. Optimal Allocation (based on pseudocode from the paper)
- **`allocate(order_size, venues, λ_over, λ_under, θ_queue)`**  
  → Brute-force grid search of all feasible order splits across venues.  
  🔸 Implements **static allocation logic** using step size to enumerate splits.

- **`compute_cost(split, venues, order_size, λ_o, λ_u, θ)`**  
  → Calculates execution cost:  
     - Market order cost  
     - Rebate from limit orders  
     - Penalties for underfill/overfill and queue risk  
  🔸 Implements equation from the paper, using queue-adjusted fills.

- **`execute_order(split, venues)`**  
  → Simulates real fill outcomes: partial fills at best ask, cash cost calculated.

### 🔹 3. Baseline Strategies
- **`best_ask_strategy(df, order_size)`**  
  → Naively fills orders from the cheapest venue until completion.

- **`twap_strategy(df, order_size, interval_seconds=60)`**  
  → Time-weighted execution: evenly splits order over time intervals.

- **`vwap_strategy(df, order_size)`**  
  → Volume-weighted execution: assigns order size based on venue volume share.

### 🔹 4. Optimization & Backtest
- **`backtest(df, λ_over, λ_under, θ_queue)`**  
  → Runs a full simulation over the dataset for given parameter values.

- **`optimize_parameters(df, init_params)`**  
  → Uses finite-difference gradient descent to tune parameters.

- **`parameter_search(df)`**  
  → Repeats optimization with random restarts to avoid local minima.

- **`calculate_bps_savings(cont_cost, baseline_cost, order_size)`**  
  → Computes cost savings in basis points (bps) vs baseline strategies.

- **`main()`**  
  → End-to-end pipeline: loads data, finds best parameters, evaluates baselines, compares results.

---

## 🔍 Pseudocode References

The following functions implement the pseudocode from the paper's static order placement model:

| Function | Paper Reference | Description |
|----------|------------------|-------------|
| `allocate` | Section 3, Eqn (2) | Brute-force optimizer for discrete order allocation |
| `compute_cost` | Section 3, Eqn (4) | Cost function accounting for fees, rebates, and penalties |

---

## 📊 Evaluation Summary

The simulation outputs:
- **Optimal parameters**: λ_over, λ_under, θ_queue
- **Execution cost and average price** of optimal vs baseline
- **Savings in basis points (bps)**

Currnet output:
```json
{
  "best_parameters": {
    "lambda_over": 0.052485551207673814,
    "lambda_under": 0.11143111457488658,
    "theta_queue": 0.003227328859860633
  },
  "cont_kukanov": {
    "total_cost": 1113700.0,
    "avg_price": 222.74
  },
  "best_ask": {
    "total_cost": 1114102.2800000003,
    "avg_price": 222.82045600000006
  },
  "twap": {
    "total_cost": 1114102.2800000003,
    "avg_price": 222.82045600000006
  },
  "vwap": {
    "total_cost": 1115319.1590477177,
    "avg_price": 223.06383180954353
  },
  "savings_bps": {
    "vs_best_ask": 3.610799539879539,
    "vs_twap": 3.610799539879539,
    "vs_vwap": 14.517450315298746
  }
}
