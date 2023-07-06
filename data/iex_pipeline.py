import numpy as np
import pandas as pd 
import matplotlib.pyplot as plt
import gpytorch
import torch 
import seaborn as sns 

from sklearn.cluster import KMeans

import pandas as pd 
import numpy as np 
import os 
import sys 
import time 
import scipy.stats as stats
import datetime 
import requests 
from tqdm import tqdm




def get_data(loc_sym, start_date, end_date, ref_index=None): 

  col='close'
  get_year = lambda N: int(N.split('-')[0])
  get_month = lambda N: int(N.split('-')[1])
  get_day = lambda N: int(N.split('-')[2])
  parse_date = lambda D, T: datetime.datetime.combine(datetime.date(
                                get_year(D), 
                                get_month(D), 
                                get_day(D)), 
                              datetime.time(int(T.split(':')[0]), int(T.split(':')[1])))
  parser = lambda row: parse_date(row['date'], row['minute'])

  date_range = pd.date_range(start_date, end_date, freq='d')
  date_range = [ d for d in date_range if d.weekday() not in [5,6] ]
  date_strings = [ str(n).replace('-','').split(' ')[0] for n in date_range ]
  
  OHLC = pd.DataFrame()
  for date in tqdm(date_strings): 
   
    dateCol = 'fullTimestamp'

    try:
      ENDP = f"https://cloud.iexapis.com/stable/stock/{loc_sym}/chart/date/{date}?token=TODO" 
      ohlc_df = None
      ohlc = requests.get(ENDP).json()
      ohlc_df = pd.DataFrame.from_records(ohlc)
   
      ohlc_df.to_csv(f'data/iex/{loc_sym}_{date}.csv')
      ohlc_df[dateCol] = ohlc_df.apply(parser, axis=1)
      
      if col in ohlc_df \
                  and not ohlc_df[col].isnull().all():
            
        OHLC = OHLC.append(ohlc_df)
        print(OHLC['marketClose'])

    except Exception as e:
      print(e)
  
  OHLC.set_index(OHLC[dateCol], inplace=True)
  OHLC = OHLC[~OHLC.index.duplicated()]

  if ref_index is not None: 
    OHLC = OHLC.reindex(ref_index, method='ffill')

  OHLC[col] = OHLC[col] \
                .replace([np.inf, -np.inf, np.nan, 0.0], method='ffill')

  return OHLC

def get_barset(symbol, symbol_stdate, symbol_eddate, ref_index=None):

  cls = 'close' 
  ohlc_df = get_data(symbol, symbol_stdate, symbol_eddate, ref_index=ref_index)
  local_barset = pd.DataFrame()
  local_barset['Close'] = ohlc_df[cls] 
  local_barset['Volume'] = ohlc_df['marketVolume']
  local_barset['Timestamp'] = ohlc_df['fullTimestamp']
  
  return local_barset, local_barset.index
    
def get_logrets(symbol_base, start_date, end_date, assets=None):

  log_returns = pd.DataFrame()
  base_ohlc = pd.DataFrame()
  _, IDX = get_barset(symbol_base, start_date, end_date)

  for p in assets: 
    try:
      b, _ = get_barset(p, start_date, end_date, ref_index=IDX)
      closes = b['Close']

      base_serie = pd.Series(data=closes, name=p)
      log_serie = pd.Series(data=np.diff(closes), name=p)

      log_returns = pd.concat([log_returns, log_serie], axis=1, ignore_index=False)
      base_ohlc = pd.concat([base_ohlc, base_serie], axis=1, ignore_index=False)
    except \
      Exception as e: 
        print(e)

  return log_returns, base_ohlc



### PARAMS ### 

SYMBOL = 'IWM'
symbol_stdate = "2023-7-4"
symbol_eddate = "2023-7-6"  

def fetch_assets(assets, invalidate_cache=False): 

  log_returns = None
  log_returns, _ = get_logrets(SYMBOL, symbol_stdate, symbol_eddate, assets=assets)
  return log_returns


def generate_time_series(length, autocorr_decays):
    """
    Generate a time series with LRD using autocorr_decays array. 
    Parameters:
    - length: int, length of the time series
    - autocorr_decays: float array, decay factor controlling long-range dependence
    Returns:
    - time_series: numpy array, generated time series
    """
    time_series = np.zeros(length)
    for i in range(1, length):
        decay = autocorr_decays[i] if i < len(autocorr_decays) else 0.
        time_series[i] = decay * time_series[i-1] + np.random.normal(loc=0, scale=1)
    return time_series

def calculate_auto_correlation(time_series):
    """
    Calculate auto-correlation of a time series.
    Parameters:
    - time_series: numpy array, input time series
    Returns:
    - auto_corr: numpy array, auto-correlation values
    """
    length = len(time_series)
    auto_corr = np.correlate(time_series, time_series, mode='full')
    auto_corr = auto_corr[length-1:]
    auto_corr /= auto_corr[0]  
    return auto_corr

def plot_auto_correlation(auto_corr):
    """
    Plot the auto-correlation values.
    Parameters:
    - auto_corr: numpy array, auto-correlation values
    """
    plt.plot(auto_corr)
    plt.xlabel('Lag')
    plt.ylabel('Auto-correlation')
    plt.title('Auto-correlation of Time Series')
    plt.grid(True)
    plt.show()


assetlist = [ 'TLT', 'SPY' ]
num_components = 4
assets = fetch_assets(assetlist, invalidate_cache=True)

# Apply z-score in a rolling way that does not create lookahead bias 
windowed_zscore = lambda serie: stats.zscore(serie).values[-1] 

# Clean data
m6_subset1 = assets.replace([np.inf, -np.inf], np.nan).dropna().reset_index().drop(columns='index')
local_time_series1 = m6_subset1['TLT'].rolling(60).apply(windowed_zscore).dropna().values
#    .rolling(100).mean().dropna().values
local_time_series2 = m6_subset1['SPY'].rolling(60).apply(windowed_zscore).dropna().values
#    .rolling(100).mean().dropna().values
    
# Calculate auto-correlation
#auto_corr = calculate_auto_correlation(local_time_series)

# Plot auto-correlation 
#plot_auto_correlation(auto_corr[1:])
  
# Evaluate kernel self similarity matrix (aka 'affinity matrix') as it grows with data 
kernel = gpytorch.kernels.RBFKernel(lengthscale=10)
eigenvalues1, eigenvectors1 = np.linalg.eig( 
  (kernel(torch.tensor(local_time_series1)).evaluate()).detach().numpy() )
eigenvalues2, eigenvectors2 = np.linalg.eig(
  (kernel(torch.tensor(local_time_series2)).evaluate()).detach().numpy()  )
       
# Cluster eigenvectors (
  # TODO 
  #   Spectral clustering + 
  #   Random Fourier Features + 
  #   Wavelet research
  # )
sns.distplot([float(x) for x in eigenvectors1[:, 0]])
sns.distplot([float(x) for x in eigenvectors2[:, 0]])
plt.show()

featuredf = pd.DataFrame()
featuredf['x0']=[float(x) for x in eigenvectors1[:, 0]]
featuredf['x1']=[float(x) for x in eigenvectors2[:, 0]]

kmeans_n=2
kmeans_lbl = KMeans(n_clusters=kmeans_n).fit(featuredf).labels_
fig,ax=plt.subplots()

sns.lineplot(data=np.cumsum(local_time_series1), ax=ax, label=assetlist[0])
sns.lineplot(data=np.cumsum(local_time_series2), ax=ax, label=assetlist[1])
state_counts = np.zeros(kmeans_n)
for M1 in kmeans_lbl:
    state_counts[M1] += 1 
    
for M2 in range(len(kmeans_lbl)): 
    if kmeans_lbl[M2] == np.argmin(state_counts):
        ax.axvline(M2, color='black', alpha=0.15)
plt.title('RBFKernel Eigenvector Clustering')
plt.legend()
plt.grid(True)
plt.show()

# Plot the evaluation results
fig, ax = plt.subplots()
im = ax.imshow(
  (kernel(torch.tensor(local_time_series2)).evaluate()).detach().numpy(), cmap='viridis', origin='lower')

# Add colorbar
cbar = ax.figure.colorbar(im, ax=ax)
cbar.ax.set_ylabel('similarity measure', rotation=-90, va="bottom")

# Set labels
ax.set_xlabel('time')
ax.set_ylabel('time')
ax.set_title('Affinity Matrix')

# Show the plot
plt.grid(False)
plt.show()
