import pandas as pd
import numpy as np
import json
import random
from typing import List, Dict, Tuple

# Constants
ORDER_SIZE = 5000  
 

# 1
def preprocess_data(filepath: str):
    df = pd.read_csv(filepath)
    
    # Filter to keep only first message per publisher_id per ts_event
    df = df.sort_values(['ts_event', 'publisher_id']).drop_duplicates(subset=['ts_event', 'publisher_id'], keep='first')
    
    # Convert timestamps to datetime
    df['ts_event'] = pd.to_datetime(df['ts_event'])
    
    return df

# 2
def get_venue_snapshot(df, timestamp):
    snapshot = df[df['ts_event'] == timestamp] # bring snapshot, only consisted of timestamp we want ()
    
    venues = snapshot[['publisher_id', 'ask_px_00', 'ask_sz_00']]\
               .rename(columns={
                   'publisher_id': 'venue_id',
                   'ask_px_00': 'ask',
                   'ask_sz_00': 'ask_size'
               })\
               .assign(
                   fee=0.003,  # assuming fixed fee
                   rebate=0.002  # assuming fixed rebate
               )\
               .to_dict('records')
    return venues


# 3 psudocode  Returns best_split and best_cost
def allocate(order_size: int, venues: List[Dict],lambda_over: float, lambda_under: float, theta_queue: float) -> Tuple[List[int], float]:
    STEP = 100 
    splits = [[]]  
    
    for v in range(len(venues)):
        new_splits = []
        for alloc in splits:
            used = sum(alloc)
            max_v = min(order_size - used, venues[v]['ask_size'])
            for q in range(0, max_v + 1, STEP):
                new_splits.append(alloc + [q])
        splits = new_splits
    
    best_cost = float('inf')
    best_split = []
    
    for alloc in splits:
        if sum(alloc) != order_size:
            continue
        
        cost = compute_cost(alloc, venues, order_size, lambda_over, lambda_under, theta_queue)
        if cost < best_cost:
            best_cost = cost
            best_split = alloc
    
    return best_split, best_cost

# 4 psudocode  for allocate
def compute_cost(split: List[int], venues: List[Dict], order_size: int, lambda_o: float, lambda_u: float, theta: float) -> float:
   
    executed = 0
    cash_spent = 0
    
    for i in range(len(venues)):
        exe = min(split[i], venues[i]['ask_size'])
        executed += exe
        cash_spent += exe * (venues[i]['ask'] + venues[i]['fee'])
        maker_rebate = max(split[i] - exe, 0) * venues[i]['rebate']
        cash_spent -= maker_rebate
    
    underfill = max(order_size - executed, 0)
    overfill = max(executed - order_size, 0)
    risk_pen = theta * (underfill + overfill)
    cost_pen = lambda_u * underfill + lambda_o * overfill
    
    return cash_spent + risk_pen + cost_pen

# 5 Execute the order split across venues, return filled shares and cash spent
def execute_order(split: List[int], venues: List[Dict]) -> Tuple[int, float]:
    filled = 0
    cash_spent = 0.0
    
    for i in range(len(split)):
        if split[i] == 0:
            continue
            
        venue = venues[i]
        fill = min(split[i], venue['ask_size'])
        filled += fill
        cash_spent += fill * venue['ask']
    
    return filled, cash_spent




# Naive best ask strategy - take liquidity from cheapest venue
def best_ask_strategy(df: pd.DataFrame, order_size: int) -> Tuple[float, float]:
    remaining = order_size
    total_cost = 0.0
    
    for timestamp in sorted(df['ts_event'].unique()):
        if remaining <= 0:
            break
            
        snapshot = get_venue_snapshot(df, timestamp)
        if not snapshot:
            continue
            
        # Find venue with best (lowest) ask price
        best_venue = min(snapshot, key=lambda x: x['ask'])
        fill = min(remaining, best_venue['ask_size'])
        remaining -= fill
        total_cost += fill * best_venue['ask']
    
    avg_price = total_cost / order_size if order_size > 0 else 0
    return total_cost, avg_price

def twap_strategy(df: pd.DataFrame, order_size: int, interval_seconds: int = 60) -> Tuple[float, float]:
    # 모든 고유 타임스탬프를 가져와 정렬
    timestamps = sorted(df['ts_event'].unique())
    if not timestamps:
        return 0.0, 0.0
    
    start_time = timestamps[0]
    end_time = timestamps[-1]
    total_duration = (end_time - start_time).total_seconds()
    
    # 총 간격 수 계산 (최소 1개 보장)
    num_intervals = max(int(total_duration / interval_seconds), 1)
    shares_per_interval = order_size / num_intervals
    
    remaining = order_size
    total_cost = 0.0
    current_interval = 1
    
    for i, timestamp in enumerate(timestamps):
        # 현재 간격의 종료 시간 계산
        interval_end = start_time + pd.Timedelta(seconds=current_interval * interval_seconds)
        
        # 현재 타임스탬프가 간격을 넘어섰으면 다음 간격으로 이동
        if timestamp >= interval_end:
            current_interval += 1
            if current_interval > num_intervals or remaining <= 0:
                break
        
        # 현재 간격의 남은 주문량 계산
        target_shares = min(shares_per_interval, remaining)
        
        # 스냅샷 가져오기
        snapshot = get_venue_snapshot(df, timestamp)
        if not snapshot:
            continue
        
        # 최선호 가격부터 주문 실행
        for venue in sorted(snapshot, key=lambda x: x['ask']):
            if target_shares <= 0:
                break
                
            fill = min(target_shares, venue['ask_size'])
            total_cost += fill * venue['ask']
            remaining -= fill
            target_shares -= fill
    
    # 마지막에 남은 주문 처리
    if remaining > 0 and timestamps:
        last_snapshot = get_venue_snapshot(df, timestamps[-1])
        if last_snapshot:
            for venue in sorted(last_snapshot, key=lambda x: x['ask']):
                if remaining <= 0:
                    break
                    
                fill = min(remaining, venue['ask_size'])
                total_cost += fill * venue['ask']
                remaining -= fill
    
    avg_price = total_cost / order_size if order_size > 0 else 0.0
    return total_cost, avg_price


def vwap_strategy(df: pd.DataFrame, order_size: int) -> Tuple[float, float]:
    remaining = order_size
    total_cost = 0.0
    total_volume = 0.0
    
    # Pre-calculate total available volume
    for timestamp in sorted(df['ts_event'].unique()):
        snapshot = get_venue_snapshot(df, timestamp)
        if not snapshot:
            continue
        total_volume += sum(v['ask_size'] for v in snapshot)
    
    if total_volume <= 0:
        return 0.0, 0.0
    
    for timestamp in sorted(df['ts_event'].unique()):
        if remaining <= 0:
            break
            
        snapshot = get_venue_snapshot(df, timestamp)
        if not snapshot:
            continue
            
        snapshot_volume = sum(v['ask_size'] for v in snapshot)
        weight = snapshot_volume / total_volume
        target_shares = min(order_size * weight, remaining)
        
        # Execute proportionally across venues
        for venue in sorted(snapshot, key=lambda x: x['ask']):
            if target_shares <= 0:
                break
                
            venue_weight = venue['ask_size'] / snapshot_volume
            venue_shares = min(target_shares * venue_weight, venue['ask_size'], remaining)
            remaining -= venue_shares
            total_cost += venue_shares * venue['ask']
    
    avg_price = total_cost / order_size if order_size > 0 else 0
    return total_cost, avg_price

def backtest(df: pd.DataFrame, lambda_over: float, lambda_under: float, theta_queue: float) -> Tuple[float, float]:
    remaining = ORDER_SIZE
    total_cost = 0.0
    
    for timestamp in sorted(df['ts_event'].unique()):
        if remaining <= 0:
            break
            
        venues = get_venue_snapshot(df, timestamp)
        if not venues:
            continue
            
        # Allocate remaining order
        split, _ = allocate(remaining, venues, lambda_over, lambda_under, theta_queue)
        
        # Execute the allocation
        filled, cost = execute_order(split, venues)
        remaining -= filled
        total_cost += cost
    
    avg_price = total_cost / ORDER_SIZE if ORDER_SIZE > 0 else 0
    return total_cost, avg_price



def optimize_parameters(
    df: pd.DataFrame,
    init_params: Tuple[float, float, float],
    lr: float = 1e-3,
    eps: float = 1e-2,
    max_iter: int = 20
) -> Tuple[float, float, float]:
    lam_o, lam_u, theta = init_params
    best_cost, _ = backtest(df, lam_o, lam_u, theta)
    for _ in range(max_iter):
        grads = []
        base = best_cost
        for i, val in enumerate((lam_o, lam_u, theta)):
            p = [lam_o, lam_u, theta]
            p[i] += eps
            cost_plus, _ = backtest(df, *p)
            grads.append((cost_plus - base) / eps)
        lam_o = max(lam_o - lr * grads[0], 0.0)
        lam_u = max(lam_u - lr * grads[1], 0.0)
        theta = max(theta - lr * grads[2], 0.0)
        cost, _ = backtest(df, lam_o, lam_u, theta)
        if cost < best_cost:
            best_cost = cost
    return lam_o, lam_u, theta

def parameter_search(df: pd.DataFrame) -> Dict:
    # random re-start setting
    bounds = {
        'lambda_over': (0.0, 0.1),
        'lambda_under': (0.0, 0.2),
        'theta_queue': (0.0, 0.01)
    }
    best = None
    best_cost = float('inf')
    for _ in range(5):  # 5 times re-start
        init_o = random.uniform(*bounds['lambda_over'])
        init_u = random.uniform(*bounds['lambda_under'])
        init_t = random.uniform(*bounds['theta_queue'])
        lam_o, lam_u, theta = optimize_parameters(
            df,
            init_params=(init_o, init_u, init_t)
        )
        total_cost, avg_price = backtest(df, lam_o, lam_u, theta)
        if total_cost < best_cost:
            best_cost = total_cost
            best = {
                'lambda_over': lam_o,
                'lambda_under': lam_u,
                'theta_queue': theta,
                'total_cost': total_cost,
                'avg_price': avg_price
            }
    return best









def calculate_bps_savings(cont_cost: float, baseline_cost: float, order_size: int) -> float:
    """Calculate basis points savings"""
    cont_price = cont_cost / order_size
    baseline_price = baseline_cost / order_size
    return (baseline_price - cont_price) / baseline_price * 10000

def main():
    # Load and preprocess data
    df = preprocess_data('l1_day.csv')
    
    # Parameter search
    best_params = parameter_search(df)
    
    # Run baseline strategies
    best_ask_cost, best_ask_price = best_ask_strategy(df, ORDER_SIZE)
    twap_cost, twap_price = twap_strategy(df, ORDER_SIZE)
    vwap_cost, vwap_price = vwap_strategy(df, ORDER_SIZE)
    
    # Calculate savings in basis points
    bps_vs_best_ask = calculate_bps_savings(
        best_params['total_cost'], best_ask_cost, ORDER_SIZE)
    bps_vs_twap = calculate_bps_savings(
        best_params['total_cost'], twap_cost, ORDER_SIZE)
    bps_vs_vwap = calculate_bps_savings(
        best_params['total_cost'], vwap_cost, ORDER_SIZE)
    
    # Prepare results
    results = {
        'best_parameters': {
            'lambda_over': best_params['lambda_over'],
            'lambda_under': best_params['lambda_under'],
            'theta_queue': best_params['theta_queue']
        },
        'cont_kukanov': {
            'total_cost': best_params['total_cost'],
            'avg_price': best_params['avg_price']
        },
        'best_ask': {
            'total_cost': best_ask_cost,
            'avg_price': best_ask_price
        },
        'twap': {
            'total_cost': twap_cost,
            'avg_price': twap_price
        },
        'vwap': {
            'total_cost': vwap_cost,
            'avg_price': vwap_price
        },
        'savings_bps': {
            'vs_best_ask': bps_vs_best_ask,
            'vs_twap': bps_vs_twap,
            'vs_vwap': bps_vs_vwap
        }
    }
    
    # Print results as JSON
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()