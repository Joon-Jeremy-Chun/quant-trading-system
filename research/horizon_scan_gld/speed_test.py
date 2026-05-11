import sys, pandas as pd, time, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'research/horizon_scan_gld')
import run_horizon_scan as hs

prices   = hs.load_price(hs.DATA_CSV)
ohlcv_df = pd.read_csv(str(hs.DATA_CSV), parse_dates=['Date']).sort_values('Date').reset_index(drop=True)
sel_df   = hs.get_selection_df(prices, '2021-05-28')
X, cols  = hs.build_feature_matrix(sel_df, '2021-05-28', 10, ohlcv_df)
print('features:', X.shape)

t0 = time.perf_counter()
for h in [30, 60, 130, 250]:
    res = hs.run_one_horizon(prices, '2021-05-28', h, X, sel_df)
    model = res['best_model'] if res else None
    print(f'h={h}d  model={model}  elapsed={time.perf_counter()-t0:.1f}s')

total = time.perf_counter() - t0
print(f'4 horizons: {total:.1f}s')
print(f'예상 전체 (10 anchors x 100 horizons): {total/4*1000/60:.1f}분')
