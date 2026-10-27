#!/usr/bin/env python3
"""Causal index-price transforms for the remaining tractable price indicators.

These are research definitions, not provider-certified indicator definitions or
PIT-cleared predictive features. Four ambiguous/advanced indicators remain open.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'daily-index-validation-20261021'
TARGET = '2010-01-01'

def wma(s, n):
    weights = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def kama(s, n=10, fast=2, slow=30):
    er = (s - s.shift(n)).abs() / s.diff().abs().rolling(n).sum().replace(0, np.nan)
    sc = (er * (2/(fast+1)-2/(slow+1)) + 2/(slow+1))**2
    result = np.full(len(s), np.nan)
    for i in range(n, len(s)):
        result[i] = s.iloc[i] if np.isnan(result[i-1]) else result[i-1] + sc.iloc[i]*(s.iloc[i]-result[i-1])
    return pd.Series(result, index=s.index)

def supertrend(h, l, c, atr, multiple=3):
    mid = (h+l)/2; upper=mid+multiple*atr; lower=mid-multiple*atr
    fu=np.full(len(c),np.nan); fl=np.full(len(c),np.nan); trend=np.full(len(c),np.nan)
    for i in range(1,len(c)):
        if np.isnan(atr.iloc[i]): continue
        if np.isnan(fu[i-1]):
            fu[i]=upper.iloc[i];fl[i]=lower.iloc[i];trend[i]=fl[i];continue
        fu[i]=upper.iloc[i] if upper.iloc[i]<fu[i-1] or c.iloc[i-1]>fu[i-1] else fu[i-1]
        fl[i]=lower.iloc[i] if lower.iloc[i]>fl[i-1] or c.iloc[i-1]<fl[i-1] else fl[i-1]
        trend[i]=fl[i] if c.iloc[i]>fu[i-1] else (fu[i] if c.iloc[i]<fl[i-1] else (fl[i] if trend[i-1]==fl[i-1] else fu[i]))
    return pd.Series(trend,index=c.index)

def sar(h,l,step=.02,cap=.2):
    out=np.full(len(h),np.nan)
    if len(h)<3:return pd.Series(out,index=h.index)
    up=h.iloc[1]>=h.iloc[0];ep=h.iloc[1] if up else l.iloc[1]
    out[1]=l.iloc[0] if up else h.iloc[0];af=step
    for i in range(2,len(h)):
        value=out[i-1]+af*(ep-out[i-1])
        value=min(value,l.iloc[i-1],l.iloc[i-2]) if up else max(value,h.iloc[i-1],h.iloc[i-2])
        if (up and l.iloc[i]<value) or ((not up) and h.iloc[i]>value):
            up=not up;value=ep;ep=h.iloc[i] if up else l.iloc[i];af=step
        elif (up and h.iloc[i]>ep) or ((not up) and l.iloc[i]<ep):
            ep=h.iloc[i] if up else l.iloc[i];af=min(cap,af+step)
        out[i]=value
    return pd.Series(out,index=h.index)

def safe_div(a,b): return a/b.replace(0,np.nan)

def build(df):
    o,h,l,c=(df[k].astype(float) for k in ('open','high','low','close'))
    out=pd.DataFrame({'date':df.date})
    out['ema_20']=c.ewm(span=20,adjust=False,min_periods=20).mean()
    out['ema_50']=c.ewm(span=50,adjust=False,min_periods=50).mean()
    out['wma_20']=wma(c,20)
    out['kama_10_2_30']=kama(c)
    out['hma_20']=wma(2*wma(c,10)-wma(c,20),round(np.sqrt(20)))
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr10=tr.ewm(alpha=.1,adjust=False,min_periods=10).mean()
    out['supertrend_10_3']=supertrend(h,l,c,atr10)
    out['sar_002_02']=sar(h,l)
    ma=c.rolling(20).mean();out['ma20_slope_5']=ma.diff(5)/5;out['ma20_curvature_5']=out.ma20_slope_5.diff(5)/5
    delta=c.diff();gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean();loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100-100/(1+safe_div(gain,loss))
    low14=l.rolling(14).min();high14=h.rolling(14).max()
    out['stochastic_k_14']=100*safe_div(c-low14,high14-low14)
    out['stochastic_d_3']=out.stochastic_k_14.rolling(3).mean()
    out['stochrsi_14']=100*safe_div(rsi-rsi.rolling(14).min(),rsi.rolling(14).max()-rsi.rolling(14).min())
    typical=(h+l+c)/3;mean=typical.rolling(20).mean();mad=typical.rolling(20).apply(lambda x:np.mean(np.abs(x-np.mean(x))),raw=True)
    out['cci_20']=safe_div(typical-mean,.015*mad)
    up=h.diff();down=-l.diff();plus=up.where((up>down)&(up>0),0);minus=down.where((down>up)&(down>0),0)
    atr14=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    pdi=100*safe_div(plus.ewm(alpha=1/14,adjust=False,min_periods=14).mean(),atr14)
    mdi=100*safe_div(minus.ewm(alpha=1/14,adjust=False,min_periods=14).mean(),atr14)
    out['plus_di_14']=pdi;out['minus_di_14']=mdi
    dx=100*safe_div((pdi-mdi).abs(),pdi+mdi);out['adx_14']=dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    out['aroon_up_25']=h.rolling(25).apply(lambda x:100*(np.argmax(x)+1)/25,raw=True)
    out['aroon_down_25']=l.rolling(25).apply(lambda x:100*(np.argmin(x)+1)/25,raw=True)
    tri=c.ewm(span=15,adjust=False,min_periods=15).mean().ewm(span=15,adjust=False,min_periods=15).mean().ewm(span=15,adjust=False,min_periods=15).mean()
    out['trix_15']=tri.pct_change()*100
    d=c.diff();tsi_num=d.ewm(span=25,adjust=False,min_periods=25).mean().ewm(span=13,adjust=False,min_periods=13).mean()
    tsi_den=d.abs().ewm(span=25,adjust=False,min_periods=25).mean().ewm(span=13,adjust=False,min_periods=13).mean()
    out['tsi_25_13']=100*safe_div(tsi_num,tsi_den)
    macd=c.ewm(span=23,adjust=False,min_periods=23).mean()-c.ewm(span=50,adjust=False,min_periods=50).mean()
    k1=100*safe_div(macd-macd.rolling(10).min(),macd.rolling(10).max()-macd.rolling(10).min())
    smooth=k1.ewm(span=3,adjust=False,min_periods=3).mean()
    k2=100*safe_div(smooth-smooth.rolling(10).min(),smooth.rolling(10).max()-smooth.rolling(10).min())
    out['stc_23_50_10_3']=k2.ewm(span=3,adjust=False,min_periods=3).mean()
    rocs=[c.pct_change(n)*100 for n in (10,15,20,30)]
    out['kst_10_15_20_30']=sum(weight*roc.rolling(window).mean() for weight,roc,window in zip((1,2,3,4),rocs,(10,10,10,15)))
    out['kst_signal_9']=out.kst_10_15_20_30.rolling(9).mean()
    out['choppiness_14']=100*np.log10(safe_div(tr.rolling(14).sum(),h.rolling(14).max()-l.rolling(14).min()))/np.log10(14)
    med=(h+l)/2;normal=2*safe_div(med-med.rolling(10).min(),med.rolling(10).max()-med.rolling(10).min())-1
    smooth=np.full(len(c),np.nan);fish=np.full(len(c),np.nan)
    for i in range(1,len(c)):
        if np.isnan(normal.iloc[i]):continue
        prior=smooth[i-1] if not np.isnan(smooth[i-1]) else 0
        smooth[i]=np.clip(.33*normal.iloc[i]+.67*prior,-.999,.999)
        fish[i]=.5*np.log((1+smooth[i])/(1-smooth[i]))+(.5*fish[i-1] if not np.isnan(fish[i-1]) else 0)
    out['fisher_10']=fish
    out['keltner_mid_20']=out.ema_20;out['keltner_upper_20_2']=out.ema_20+2*atr10;out['keltner_lower_20_2']=out.ema_20-2*atr10
    bb_mid=c.rolling(20).mean();bb_sd=c.rolling(20).std()
    out['squeeze_20']=((bb_mid+2*bb_sd<out.keltner_upper_20_2)&(bb_mid-2*bb_sd>out.keltner_lower_20_2)).where(bb_sd.notna())
    overnight=np.log(o/c.shift());intraday=np.log(c/o)
    rs=np.log(h/c)*np.log(h/o)+np.log(l/c)*np.log(l/o)
    n=20;k=.34/(1.34+(n+1)/(n-1))
    variance=overnight.rolling(n).var()+k*intraday.rolling(n).var()+(1-k)*rs.rolling(n).mean()
    out['yang_zhang_20']=np.sqrt(variance.clip(lower=0))
    return out

COLS={2:['ema_20','ema_50'],3:['wma_20'],4:['kama_10_2_30'],5:['hma_20'],
      8:['supertrend_10_3'],9:['sar_002_02'],11:['ma20_slope_5','ma20_curvature_5'],
      15:['stochastic_k_14','stochastic_d_3','stochrsi_14'],16:['cci_20'],
      18:['plus_di_14','minus_di_14','adx_14'],19:['aroon_up_25','aroon_down_25'],
      20:['trix_15'],21:['tsi_25_13'],22:['stc_23_50_10_3'],
      24:['kst_10_15_20_30','kst_signal_9'],25:['choppiness_14'],27:['fisher_10'],
      30:['keltner_mid_20','keltner_upper_20_2','keltner_lower_20_2'],
      31:['squeeze_20'],35:['yang_zhang_20']}

def main():
    private=HERE/'private';private.mkdir(exist_ok=True)
    report=[]
    for market in ('kospi','kosdaq'):
        df=pd.read_csv(SOURCE/f'naver_{market}_daily.csv',parse_dates=['date'])
        out=build(df)
        out=out[out.date>=TARGET].reset_index(drop=True)
        path=private/f'{market}_derived_more.csv';out.to_csv(path,index=False)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        for i,cols in COLS.items():
            mask=out[cols].notna().all(axis=1)
            report.append({'indicator_id':i,'market':market.upper(),'columns':','.join(cols),
                           'row_count':len(out),'valid_count':int(mask.sum()),
                           'first_valid':str(out.loc[mask,'date'].min().date()) if mask.any() else '',
                           'last_valid':str(out.loc[mask,'date'].max().date()) if mask.any() else '',
                           'raw_sha256':digest,'derived_series_path':f'private:{path.name}',
                           'pit_status':'PIT_UNVERIFIED','definition_status':'RESEARCH_PARAMETERIZATION'})
    import csv
    with (HERE/'derived_addendum.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(report[0]),lineterminator='\n');w.writeheader();w.writerows(report)
    (HERE/'derived_addendum_manifest.json').write_text(json.dumps({'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'computed_indicator_ids':sorted(COLS),'remaining_price_indicator_ids':[6,7,14,23],
        'markets':['KOSPI','KOSDAQ'],'rows':len(report),'pit_status':'PIT_UNVERIFIED',
        'warning':'Research parameterization; provider reference formulas and release vintages not independently verified'},indent=2)+'\n')
    print('computed',len(COLS),'indicators in',len(report),'market rows')

if __name__=='__main__':main()
