"""Descriptive historical comparisons, never an order or entry filter."""
import math
import statistics

VERSION = 'historical-analogs-v1'


def analyze(rows, lookback=24, horizon=24, count=10, minimum=8, cost_bps=40):
    if lookback < 2 or horizon < 1 or minimum < 1 or count < minimum:
        raise ValueError('Invalid study parameters')
    prices = [float(r[4]) for r in rows]
    volumes = [float(r[5]) for r in rows]
    if any(not math.isfinite(p) or p <= 0 for p in prices):
        raise ValueError('Invalid price')
    if any(not math.isfinite(v) or v < 0 for v in volumes):
        raise ValueError('Invalid volume')
    if any(int(b[0])-int(a[0]) != 3600000 for a,b in zip(rows, rows[1:])):
        raise ValueError('Only contiguous hourly candles supported')
    query_end = len(rows)-1
    query_start = query_end-lookback+1
    report = {'version':VERSION,'mode':'PAPER_ONLY','lookback_bars':lookback,
              'horizon_bars':horizon,'requested_cases':count,'minimum_cases':minimum,
              'cost_bps':cost_bps,'status':'INSUFFICIENT_DATA','cases':[],
              'calibrated_probability':False,'used_for_entries':False,
              'note':'Historical close-to-close outcomes, not executable fills or future odds'}
    if query_start < 0:
        return report
    def features(end):
        start = end-lookback+1
        close_path = [math.log(p/prices[start]) for p in prices[start:end+1]]
        avg_volume = statistics.mean(volumes[start:end+1])
        volume_path = [v/avg_volume if avg_volume else 0 for v in volumes[start:end+1]]
        return close_path, volume_path
    current = features(query_end)
    candidates = []
    # Outcomes must finish BEFORE the current comparison window even starts.
    for end in range(lookback-1, query_start-horizon):
        path, volume = features(end)
        distance = math.sqrt(statistics.mean((a-b)**2 for a,b in zip(path,current[0])))
        distance += 0.005 * statistics.mean(abs(a-b) for a,b in zip(volume,current[1]))
        if distance <= 0.05:
            candidates.append((distance,end))
    selected = []
    for distance,end in sorted(candidates):
        # Disjoint outcome windows; feature windows may still overlap.
        if any(abs(end-previous) < horizon for previous in selected):
            continue
        selected.append(end)
        net = prices[end+horizon]/prices[end]-1-cost_bps/10000
        report['cases'].append({'input_end_ms':int(rows[end][6])+1,
                                'outcome_end_ms':int(rows[end+horizon][6])+1,
                                'distance':distance,'net_return':net})
        if len(selected) == count:
            break
    report['sample_count'] = len(selected)
    report['query_cutoff_ms'] = int(rows[-1][6])+1
    if len(selected) >= minimum:
        returns = [r['net_return'] for r in report['cases']]
        report.update(status='DESCRIPTIVE_ONLY', historical_positive_fraction=sum(r>0 for r in returns)/len(returns),
                      mean_net_return=statistics.mean(returns), median_net_return=statistics.median(returns),
                      worst_net_return=min(returns), best_net_return=max(returns))
    return report
