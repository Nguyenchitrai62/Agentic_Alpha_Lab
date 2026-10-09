"""audit_vrpstraddle blind replication: V2 weekly short straddle + G2 overlay f=0.25.
Built ONLY from research/tournament/oc_vrpstraddle/PLAN.md (frozen spec).
Does NOT read vrp.py/run_vrp.py/REPORT.md/results.json/trades_*.parquet/tmp.
"""
from __future__ import annotations
import json, pickle, math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
HERE = Path(__file__).parent

ANCH_S = ["2021-09-24","2022-09-24","2023-09-24","2024-09-24","2025-09-24"]
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH_S]
YEAR = pd.Timedelta(days=365)
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
STRAT = "R2B1D17BFG2"
COINS = ["BTC","ETH"]
GRID_STEP = {"BTC":1000.0,"ETH":50.0}

def norm_cdf(x):
    return 0.5*(1.0+math.erf(x/math.sqrt(2.0)))
v_norm_cdf = np.vectorize(lambda x: 0.5*(1.0+math.erf(x/math.sqrt(2.0))))

def bs_pair(S,K,s,T):
    """return (call,put) per unit, r=q=0. Handles edge -> intrinsic."""
    try:
        if not (np.isfinite(S) and np.isfinite(K)) or K<=0:
            return (np.nan,np.nan)
        if not np.isfinite(s) or s<=0 or not np.isfinite(T) or T<=0:
            c = max(S-K,0.0); p = max(K-S,0.0)
            return (c,p)
        import math as _m
        d1 = (_m.log(S/K)+0.5*s*s*T)/(s*_m.sqrt(T))
        d2 = d1 - s*_m.sqrt(T)
        N = lambda x: 0.5*(1.0+_m.erf(x/_m.sqrt(2.0)))
        c = S*N(d1)-K*N(d2)
        p = K*N(-d2)-S*N(-d1)
        return (max(c,0.0),max(p,0.0))
    except Exception:
        return (np.nan,np.nan)

def load_dvol():
    out={}
    for coin in COINS:
        ms_list=[]; c_list=[]
        for f in sorted((ROOT/"data/raw/deribit_dvol_20261005").glob(f"{coin}_*.json")):
            d=json.loads(f.read_text())
            for row in d["candles"]:
                ms=row[0]; c=row[4]
                ms_list.append(ms); c_list.append(c)
        ms_arr=np.array(ms_list,dtype=np.int64)
        c_arr=np.array(c_list,dtype=float)
        o=np.argsort(ms_arr); ms_arr=ms_arr[o]; c_arr=c_arr[o]
        # candle close = open ms + 3600s; known at close
        close_ns=(ms_arr+3600_000)*1_000_000
        # dedup: keep last
        out[coin]=(close_ns,c_arr)
    return out

def latest_dvol(dvol_close_ns,dvol_c,ts_ns):
    import numpy as np
    i=np.searchsorted(dvol_close_ns,ts_ns,side="right")-1
    if i<0: return np.nan
    return dvol_c[i]/100.0

def load_1m():
    data={}
    for coin,pat,files in [
        ("BTC","btc",["klines_1m_2019.parquet","klines_1m_2020.parquet","klines_1m_2021.parquet","klines_1m_2022.parquet","klines_1m_2023.parquet","klines_1m_2024.parquet","klines_1m_2025.parquet","klines_1m_2026.parquet"]),
        ("ETH","eth",None)]:
        if coin=="BTC":
            dfs=[]
            for fn in files:
                p=ROOT/f"data/raw/btc_intraday_20260924/{fn}"
                dfs.append(pd.read_parquet(p,columns=["open_time","close"]))
            df=pd.concat(dfs,ignore_index=True)
        else:
            dfs=[]
            import glob as _g
            for fn in ["ETHUSDT_1m_2019.parquet","ETHUSDT_1m_2020.parquet","ETHUSDT_1m_2021.parquet","ETHUSDT_1m_2022.parquet","ETHUSDT_1m_2023.parquet","ETHUSDT_1m_2024.parquet","ETHUSDT_1m_2025.parquet","ETHUSDT_1m_2026.parquet"]:
                p=ROOT/f"data/raw/majors_intraday_20260924/{fn}"
                if p.exists():
                    dfs.append(pd.read_parquet(p,columns=["open_time","close"]))
            df=pd.concat(dfs,ignore_index=True)
        df["open_time"]=pd.to_datetime(df["open_time"],utc=True)
        df=df.sort_values("open_time")
        tns=df["open_time"].values.astype("datetime64[ns]").astype(np.int64)
        cl=df["close"].to_numpy(dtype=float)
        # dedup exact dups keep last
        data[coin]=(tns,cl)
    return data

def get_close(tns,cl,ts_ns):
    import numpy as np
    i=np.searchsorted(tns,ts_ns,side="left")
    if i<len(tns) and tns[i]==ts_ns:
        return float(cl[i])
    return np.nan

SEC_PER_YEAR = 365*86400

def fee_unit(S_trade, leg_price, rate):
    # per-unit option fee; rate 0.0003 entry/buyback, settlement uses 0.00015
    if not (np.isfinite(S_trade) and np.isfinite(leg_price)):
        return np.nan
    return min(rate*S_trade, 0.125*leg_price)

def simulate_coin(coin, entry, expiry, S_entry, K, sigma_sell, prem_c, prem_p,
                  tns, cl, dvol_ns, dvol_c):
    """Simulate one V2 short-straddle position with notional q=1 unit sizing agnostic.
    Returns dict with per-unit economics + event times. All prices/fees per unit.
    q scaling applied by caller.
    """
    T_entry = (expiry.value-entry.value)/1e9/SEC_PER_YEAR
    fee_c_entry = fee_unit(S_entry, prem_c, 0.0003)
    fee_p_entry = fee_unit(S_entry, prem_p, 0.0003)
    gross_unit = prem_c+prem_p
    opt_cash_unit = gross_unit-(fee_c_entry+fee_p_entry)
    # hourly check times: every hour boundary strictly after entry, strictly before expiry
    # entry e.g. 08:05 -> first 09:00
    cur = entry.floor("h")+pd.Timedelta(hours=1)
    # ensure strictly after entry
    while cur.value <= entry.value:
        cur += pd.Timedelta(hours=1)
    checks=[]
    t=cur
    while t.value < expiry.value:
        checks.append(t)
        t += pd.Timedelta(hours=1)
    result={"S_entry":S_entry,"K":K,"sigma_sell":sigma_sell,"prem_c":prem_c,"prem_p":prem_p,
            "fee_entry_unit":fee_c_entry+fee_p_entry,"gross_unit":gross_unit,
            "opt_cash_unit":opt_cash_unit,"T_entry":T_entry,"exit":None}
    for ch in checks:
        ch_ns=ch.value
        S_t=get_close(tns,cl,ch_ns)
        if not np.isfinite(S_t):
            continue
        sig_latest=latest_dvol(dvol_ns,dvol_c,ch_ns)
        if not np.isfinite(sig_latest):
            continue
        T_rem=(expiry.value-ch_ns)/1e9/SEC_PER_YEAR
        is_4h = (ch.hour%4==0 and ch.minute==0)
        # TP first at 4h closes
        mc,mp=bs_pair(S_t,K,sig_latest,T_rem)
        mark_unit=mc+mp
        if is_4h and np.isfinite(mark_unit) and np.isfinite(gross_unit) and gross_unit>0:
            if mark_unit<=0.3*gross_unit:
                fbc=fee_unit(S_t,mc,0.0003); fbp=fee_unit(S_t,mp,0.0003)
                realized=opt_cash_unit-mark_unit-(fbc+fbp)
                result["exit"]={"type":"TP","t":str(ch),"S":S_t,"sig":sig_latest,"T_rem":T_rem,
                                "mark_unit":mark_unit,"buy_unit":mark_unit,
                                "fee_exit_unit":float(fbc+fbp),"realized_unit":float(realized)}
                return result
        # SL at every hourly close
        pnl_mark=opt_cash_unit-mark_unit
        if np.isfinite(pnl_mark) and np.isfinite(gross_unit) and gross_unit>0:
            if pnl_mark<=-1.0*gross_unit:
                sig_buy=1.05*sig_latest
                bc,bp=bs_pair(S_t,K,sig_buy,T_rem)
                fbc=fee_unit(S_t,bc,0.0003); fbp=fee_unit(S_t,bp,0.0003)
                realized=opt_cash_unit-(bc+bp)-(fbc+fbp)
                result["exit"]={"type":"SL","t":str(ch),"S":S_t,"sig":sig_latest,"T_rem":T_rem,
                                "mark_unit":mark_unit,"buy_unit":float(bc+bp),
                                "fee_exit_unit":float(fbc+fbp),"realized_unit":float(realized)}
                return result
        result.setdefault("last_mark",{"t":str(ch),"S":S_t})  # keep last for debug
    # settle at expiry
    # S_settle = mean of 30 1m closes 07:30..07:59 expiry Friday
    exp_day = expiry.floor("D")
    closes=[]
    ok=True
    for m in range(30):
        ts = exp_day+pd.Timedelta(hours=7,minutes=30+m)
        px=get_close(tns,cl,ts.value)
        if not np.isfinite(px):
            ok=False; break
        closes.append(px)
    if not ok:
        result["exit"]={"type":"MISSING_SETTLE","realized_unit":np.nan}
        return result
    S_settle=float(np.mean(closes))
    call_int=max(S_settle-K,0.0); put_int=max(K-S_settle,0.0)
    sfee_c=fee_unit(S_settle,call_int,0.00015) if call_int>0 else 0.0
    sfee_p=fee_unit(S_settle,put_int,0.0+0.00015) if put_int>0 else 0.0
    realized=opt_cash_unit-(call_int+put_int)-(sfee_c+sfee_p)
    result["exit"]={"type":"EXPIRY","t":str(expiry),"S_settle":S_settle,
                    "intrinsic_unit":float(call_int+put_int),
                    "fee_exit_unit":float(sfee_c+sfee_p),"realized_unit":float(realized)}
    return result

def mark_unit_at(coin_sim, S_t, sig_latest, T_rem):
    K=coin_sim["K"]
    return sum(bs_pair(S_t,K,sig_latest,T_rem))


def fridays():
    # Fridays on/after 2021-09-24 00:00 UTC; friday_index 0 = 2021-09-24
    start=pd.Timestamp("2021-09-24",tz="UTC")
    # find Fridays up to 2026-09-23
    end=pd.Timestamp("2026-09-23",tz="UTC")
    days=pd.date_range(start.normalize(),end.normalize(),freq="D")
    fris=[d for d in days if d.weekday()==4]
    return [pd.Timestamp(d.date(),tz="UTC") for d in fris]


def main():
    import importlib.util
    spec=importlib.util.spec_from_file_location("v388_a",RD/"v388/v388_bot_stop_distance.py")
    v388=importlib.util.module_from_spec(spec); spec.loader.exec_module(v388)
    g1=v388.Y1+pd.Timedelta(hours=12)
    grid=pd.date_range(GRID0,g1,freq="1h")
    gn=grid.values.astype("datetime64[ns]").astype(np.int64)
    # ---- G2 baseline reproduction ----
    runs=pickle.loads(V421.read_bytes())
    Es=[];Ms=[]
    for s in range(4):
        e1,m1=v388.hourly(runs[s][STRAT],GRID0,g1)
        assert (e1.index==grid).all()
        Es.append(e1.to_numpy(float)); Ms.append(m1.to_numpy(float))
    Es=np.stack(Es); Ms=np.stack(Ms)
    Etot=Es.mean(axis=0); Mtot=Ms.mean(axis=0)
    # per-year reset metric (same as reset_metric.year_reset)
    years_R=[];years_DD=[]
    for y,a0 in enumerate(ANCH):
        a1=a0+YEAR
        seg=(grid>a0)&(grid<=a1)
        idx=np.where(np.asarray(seg))[0]
        le=gn<=a0.value
        b=np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
        E4=[Es[s][idx]/b[s] for s in range(4)]
        M4=[Ms[s][idx]/b[s] for s in range(4)]
        es=np.mean(E4,axis=0); ms=np.mean(M4,axis=0)
        R=round(100*float(es[-1]**(1/12)-1),3)
        pk=np.maximum.accumulate(es)
        DD=round(100*float(np.max(1-ms/pk)),2)
        years_R.append(R);years_DD.append(DD)
    R5=round(float(np.prod([1+r/100 for r in years_R])**(1/5)-1)*100,3)
    DDmax=max(years_DD)
    segf=np.asarray(grid>pd.Timestamp("2021-09-24",tz="UTC"))
    esf,msf=Etot[segf],Mtot[segf]
    dd_m=round(100*float(np.max(1-msf/np.maximum.accumulate(esf))),2)
    dd_c=round(100*float(np.max(1-esf/np.maximum.accumulate(esf))),2)
    full=max(dd_m,dd_c)
    exp=json.loads(V421_RES.read_text())["rows"][STRAT]
    print("G2 reproduced:",years_R,years_DD,R5,DDmax,(dd_m,dd_c,full))
    print("G2 expected:",exp)
    assert years_R==[r for r,_ in exp["years"]],(years_R,exp)
    assert years_DD==[d for _,d in exp["years"]],(years_DD,exp)
    assert R5==exp["R"] and DDmax==exp["DD"],((R5,DDmax),exp)
    assert full==exp["full_path_dd"],(full,exp)
    print("f=0 validation OK")
    g2={"years_R":years_R,"years_DD":years_DD,"R":R5,"DD":DDmax,
        "full_marked":dd_m,"full_close":dd_c,"full":full}
    # ---- load market data ----
    print("loading dvol...",flush=True)
    dvol=load_dvol()
    print("loading 1m (heavy)...",flush=True)
    m1m=load_1m()
    # ---- enumerate cycles ----
    fris=fridays()
    cycles=[]  # (entry, expiry)
    for f in fris:
        entry=f+pd.Timedelta(hours=8,minutes=5)
        expiry=entry+pd.Timedelta(days=7)-pd.Timedelta(minutes=5)
        cycles.append((entry,expiry))
    # pre-simulate each Friday x coin with unit economics (entry/pricing independent of sizing)
    print(f"{len(cycles)} fridays",flush=True)
    sims={}  # (fri_idx,coin) -> dict or None(skip)
    skips=0
    for fi,(entry,expiry) in enumerate(cycles):
        for coin in COINS:
            tns,cl=m1m[coin]
            S_entry=get_close(tns,cl,(entry-pd.Timedelta(minutes=1)).value)
            if not np.isfinite(S_entry):
                sims[(fi,coin)]=None; continue
            grid_step=GRID_STEP[coin]
            K=float(round(S_entry/grid_step)*grid_step)
            if not np.isfinite(K) or K<=0:
                sims[(fi,coin)]=None; continue
            dvol_ns,dvol_c=dvol[coin]
            sig_l=latest_dvol(dvol_ns,dvol_c,entry.value)
            if not np.isfinite(sig_l):
                sims[(fi,coin)]=None; continue
            sigma_sell=0.97*sig_l
            T_entry=(expiry.value-entry.value)/1e9/SEC_PER_YEAR
            pc,pp=bs_pair(S_entry,K,sigma_sell,T_entry)
            if not (np.isfinite(pc) and np.isfinite(pp)):
                sims[(fi,coin)]=None; continue
            r=simulate_coin(coin,entry,expiry,S_entry,K,sigma_sell,pc,pp,tns,cl,dvol_ns,dvol_c)
            r.update({"entry":str(entry),"expiry":str(expiry),"fi":fi,"coin":coin})
            # realized vol for IV-RV gap: 1m log rets entry->expiry
            try:
                i0=int(np.searchsorted(tns,entry.value,side="right"))
                i1=int(np.searchsorted(tns,expiry.value,side="right"))
                seg=cl[max(i0-1,0):i1]
                seg=seg[np.isfinite(seg)]
                if len(seg)>100:
                    lr=np.log(seg[1:]/seg[:-1])
                    rv=float(np.std(lr)*np.sqrt(SEC_PER_YEAR/60.0))
                else:
                    rv=float("nan")
            except Exception:
                rv=float("nan")
            r["rv"]=rv; r["iv_rv_gap"]=float(sigma_sell-rv) if np.isfinite(rv) else float("nan")
            sims[(fi,coin)]=r
    # ---- standalone per dev year (anchors 0..3), E=1.0 reset, q=0.5*E/S ----
    dev_years=[]
    for y in range(4):
        a0=ANCH[y]; a1=a0+YEAR
        E=1.0
        trades=[]; nTP=nSL=nEXP=0; gaps=[]
        # hourly mark series for DD
        seg=(grid>a0)&(grid<=a1)
        gseg=grid[np.asarray(seg)]
        marks=np.full(len(gseg),np.nan)
        # iterate cycles in time order within year filter
        for fi,(entry,expiry) in enumerate(cycles):
            if not (entry>=a0 and entry<a1 and expiry<=a0+YEAR):
                continue
            # both coins share E_entry
            E_entry=E
            coin_rs=[]
            valid=False
            for coin in COINS:
                r=sims.get((fi,coin))
                if r is None: continue
                if r["exit"] is None or not np.isfinite(r["exit"].get("realized_unit",np.nan)):
                    continue
                valid=True
                S_entry=r["S_entry"]
                q=0.5*E_entry/S_entry
                pnl=q*r["exit"]["realized_unit"]
                coin_rs.append((coin,q,pnl,r))
            if not valid:
                continue
            # count exits per coin trade
            for coin,q,pnl,r in coin_rs:
                et=r["exit"]["type"]
                if et=="TP": nTP+=1
                elif et=="SL": nSL+=1
                elif et=="EXPIRY": nEXP+=1
                if np.isfinite(r.get("iv_rv_gap",np.nan)): gaps.append(r["iv_rv_gap"])
                trades.append({"fi":fi,"coin":coin,"entry":r["entry"],"exit":et,
                               "q":q,"pnl":pnl,"S_entry":r["S_entry"],"K":r["K"]})
            E=E_entry+sum(pnl for _,_,pnl,_ in coin_rs if np.isfinite(pnl))
        R=round(100*float(E**(1/12)-1),3)
        # hourly marks: walk grid, track open cycle
        # build list of taken cycles with E_entry info (recompute E_entry path)
        E2=1.0
        taken=[]
        for fi,(entry,expiry) in enumerate(cycles):
            if not (entry>=a0 and entry<a1 and expiry<=a0+YEAR):
                continue
            # need same validity as above
            okcs=[c for c in COINS if sims.get((fi,c)) is not None and sims[(fi,c)]["exit"] is not None and np.isfinite(sims[(fi,c)]["exit"].get("realized_unit",np.nan))]
            if not okcs: continue
            taken.append((fi,entry,expiry,E2,okcs))
            # advance E2
            add=0.0
            for c in okcs:
                r=sims[(fi,c)]; q=0.5*E2/r["S_entry"]
                add+=q*r["exit"]["realized_unit"]
            E2+=add
        Earr=np.zeros(len(gseg)); Earr[:]=np.nan
        # for each grid point, find: last closed E + open mark
        # determine for each taken cycle its entry grid pos (first grid > entry) and exit grid pos
        for gi,gt in enumerate(gseg):
            # find open taken cycle containing gt (entry < gt <= exit-settle?)
            # equity = E_entry + sum mark pnl of open coins at gt (if gt after entry-book and before exit)
            # else = E after last closed cycle with exit <= gt
            cur_E=1.0
            val=1.0; found=False
            for (fi,entry,expiry,E_entry,okcs) in taken:
                # exit time: for TP/SL use exit t; for expiry use expiry
                # need per-coin exit times (same week may differ per coin!)
                # compute per-coin state at gt
                if gt.value<=entry.value:
                    val=cur_E; found=True; break
                # check if all coins exited by gt
                all_done=True; open_pnl=0.0; any_open=False
                for c in okcs:
                    r=sims[(fi,c)]
                    ex=r["exit"]; q=0.5*E_entry/r["S_entry"]
                    et=ex["type"]
                    if et in ("TP","SL"):
                        ext=pd.Timestamp(ex["t"],tz="UTC")
                    else:
                        ext=expiry
                    if gt.value<=(entry.value):
                        all_done=False; any_open=False; break
                    if gt.value>=ext.value if hasattr(ext,"value") else True:
                        continue  # this coin done (its pnl in cur_E at end? handle below)
                    else:
                        all_done=False
                        # open: mark at gt
                        tns,cl=m1m[c]
                        S_t=get_close(tns,cl,gt.value)
                        dvol_ns,dvol_c=dvol[c]
                        sig=latest_dvol(dvol_ns,dvol_c,gt.value)
                        if np.isfinite(S_t) and np.isfinite(sig):
                            T_rem=(expiry.value-gt.value)/1e9/SEC_PER_YEAR
                            mk=mark_unit_at(r,S_t,sig,max(T_rem,0.0))
                            open_pnl+=q*(r["opt_cash_unit"]-mk)
                            any_open=True
                        else:
                            open_pnl+=0.0; any_open=True
                if any_open:
                    val=E_entry+open_pnl
                    # NOTE: if one coin done early and other open, cur_E accounting:
                    # E_entry + realized(done coins) + open mark(open coins). Our open_pnl above only
                    # includes open coins; add realized of done coins:
                    for c in okcs:
                        r=sims[(fi,c)]; q=0.5*E_entry/r["S_entry"]
                        ex=r["exit"]
                        if ex["type"] in ("TP","SL"):
                            ext=pd.Timestamp(ex["t"],tz="UTC")
                        else:
                            ext=expiry
                        if gt.value>=ext.value:
                            open_pnl+=q*ex["realized_unit"]
                    val=E_entry+open_pnl
                    found=True; break
                if all_done:
                    # advance cur_E past this cycle
                    add=sum(0.5*E_entry/sims[(fi,c)]["S_entry"]*sims[(fi,c)]["exit"]["realized_unit"] for c in okcs)
                    cur_E=E_entry+add
                    continue
            else:
                val=cur_E
            Earr[gi]=val
        # fill pre-first NaN with 1.0 (shouldn't happen)
        Earr=pd.Series(Earr,index=gseg).ffill().fillna(1.0).to_numpy()
        pk=np.maximum.accumulate(Earr)
        DD=round(100*float(np.max(1-Earr/pk)),2)
        # worst week: min 168-step return
        if len(Earr)>168:
            wret=Earr[168:]/Earr[:-168]-1
            worst_w=round(100*float(np.min(wret)),2)
        else:
            worst_w=0.0
        dev_years.append({"anchor":ANCH_S[y],"E_end":round(float(E),6),"R":R,"DD":DD,
                          "trades":len(trades),"TP":nTP,"SL":nSL,"EXPIRY":nEXP,
                          "worst_week_pct":worst_w,
                          "mean_iv_rv_gap":round(float(np.nanmean(gaps)),4) if gaps else None})
    R4=round(float(np.prod([1+d["R"]/100 for d in dev_years])**(1/4)-1)*100,3)
    W4=min(d["R"] for d in dev_years)
    out={"meta":{"note":"blind replication from PLAN.md only; hourly price = 1m close of that minute; DVOL close<=t; fee per unit*q; entry booked at first hourly grid>entry for overlay; standalone marks hourly","g2":g2},
         "standalone_V2_dev4":dev_years,
         "standalone_V2_dev4_mean":R4,"standalone_V2_dev4_worst":W4,
         "standalone_V2_dev4_maxDD":max(d["DD"] for d in dev_years)}
    # ---- overlay f=0.25: per-year reset + 5y full path ----
    F=0.25
    ov_years=[]
    for y in range(5):
        a0=ANCH[y]; a1=a0+YEAR
        seg=(grid>a0)&(grid<=a1)
        idx=np.where(np.asarray(seg))[0]
        le=gn<=a0.value
        b=np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
        E4=[Es[s][idx]/b[s] for s in range(4)]
        M4=[Ms[s][idx]/b[s] for s in range(4)]
        es=np.mean(E4,axis=0); ms=np.mean(M4,axis=0)
        es_prev=np.concatenate([[1.0],es[:-1]])
        g=es/es_prev; hh=ms/es_prev
        # taken cycles this year with entry grid positions
        taken=[]
        for fi,(entry,expiry) in enumerate(cycles):
            if not (entry>=a0 and entry<a1 and expiry<=a0+YEAR):
                continue
            okcs=[c for c in COINS if sims.get((fi,c)) is not None and sims[(fi,c)]["exit"] is not None and np.isfinite(sims[(fi,c)]["exit"].get("realized_unit",np.nan))]
            if not okcs: continue
            taken.append((fi,entry,expiry,okcs))
        # map entry to grid pos: first grid idx > entry
        # sleeve U(t): cumulative sleeve leg value; dU=U-Uprev
        # For each taken cycle, notional Nk_c = F*A_prev_at_entry where A_prev is combo A at grid just before entry
        # We iterate hourly and open notionals as we go.
        A_prev=1.0; U_prev=0.0
        A_arr=np.empty(len(idx)); M_arr=np.empty(len(idx))
        # precompute per-cycle entry pos
        epos={}
        for (fi,entry,expiry,okcs) in taken:
            pos=int(np.searchsorted(gn[idx],entry.value,side="right"))
            epos[fi]=pos
        openN={}  # (fi,coin)->N
        # helper: sleeve U at grid i
        for i in range(len(idx)):
            gt_ns=gn[idx[i]]
            # open new cycles whose entry pos == i (use A_prev before update)
            for (fi,entry,expiry,okcs) in taken:
                if epos[fi]==i:
                    for c in okcs:
                        r=sims[(fi,c)]
                        openN[(fi,c)]=F*A_prev
            # compute U_i = sum over openN of N * ret_c(gt)
            # ret_c = per-1-sleeve-equity return: q1*opt_cash_unit - q1*mark_or_realized where q1=0.5/S_entry
            U_i=0.0
            for (fi,c),N in list(openN.items()):
                r=sims[(fi,c)]
                ex=r["exit"]
                if ex["type"] in ("TP","SL"):
                    ext=pd.Timestamp(ex["t"],tz="UTC").value
                else:
                    # expiry settle books at expiry grid (08:00)
                    ext=r["expiry"] and pd.Timestamp(r["expiry"],tz="UTC").value
                q1=0.5/r["S_entry"]
                if gt_ns>=ext:
                    U_i+=N*q1*ex["realized_unit"]
                elif gt_ns>(pd.Timestamp(r["entry"],tz="UTC").value):
                    tns,cl=m1m[c]
                    S_t=get_close(tns,cl,gt_ns)
                    dvol_ns,dvol_c=dvol[c]
                    sig=latest_dvol(dvol_ns,dvol_c,gt_ns)
                    exp_ts=pd.Timestamp(r["expiry"],tz="UTC").value
                    T_rem=(exp_ts-gt_ns)/1e9/SEC_PER_YEAR
                    if np.isfinite(S_t) and np.isfinite(sig):
                        mk=mark_unit_at(r,S_t,sig,max(T_rem,0.0))
                        U_i+=N*q1*(r["opt_cash_unit"]-mk)
                    else:
                        U_i+=N*q1*(r["opt_cash_unit"]-r["gross_unit"])  # fallback conservative
                else:
                    pass
            dU=U_i-U_prev
            A_i=A_prev*g[i]+dU
            M_i=A_prev*hh[i]+dU
            A_arr[i]=A_i; M_arr[i]=M_i
            A_prev,U_prev=A_i,U_i
        pk=np.maximum.accumulate(A_arr)
        R=round(100*float(A_arr[-1]**(1/12)-1),3)
        DD=round(100*float(np.max(1-M_arr/pk)),2)
        ov_years.append({"anchor":ANCH_S[y],"R":R,"DD":DD,"end":round(float(A_arr[-1]),6)})
    R5ov=round(float(np.prod([1+yy["R"]/100 for yy in ov_years])**(1/5)-1)*100,3)
    W5ov=min(yy["R"] for yy in ov_years)
    # continuous full-path for overlay (grid from GRID0)
    Etot_c=Etot.copy(); Mtot_c=Mtot.copy()
    n=len(grid)
    A_c=np.empty(n); M_c=np.empty(n)
    A_c[0],M_c[0]=float(Etot[0]),float(Mtot[0])
    A_prev=float(Etot[0]); U_prev=0.0
    # all taken across full span (entries with expiry<=? for full path use same boundary skip per year? use per-year filter union)
    full_taken=[]
    for y in range(5):
        a0=ANCH[y]
        for fi,(entry,expiry) in enumerate(cycles):
            if entry>=a0 and entry<a0+YEAR and expiry<=a0+YEAR:
                okcs=[c for c in COINS if sims.get((fi,c)) is not None and sims[(fi,c)]["exit"] is not None and np.isfinite(sims[(fi,c)]["exit"].get("realized_unit",np.nan))]
                if okcs: full_taken.append((fi,entry,expiry,okcs))
    epos_full={}
    for (fi,entry,expiry,okcs) in full_taken:
        epos_full[fi]=int(np.searchsorted(gn,entry.value,side="right"))
    openN={}
    U_prev=0.0; A_prev=float(Etot[0])
    # U rebase at grid start = 0
    for i in range(1,n):
        gt_ns=gn[i]
        for (fi,entry,expiry,okcs) in full_taken:
            if epos_full[fi]==i:
                for c in okcs:
                    openN[(fi,c)]=F*A_prev
        U_i=0.0
        for (fi,c),N in list(openN.items()):
            r=sims[(fi,c)]
            ex=r["exit"]
            if ex["type"] in ("TP","SL"):
                ext=pd.Timestamp(ex["t"],tz="UTC").value
            else:
                ext=pd.Timestamp(r["expiry"],tz="UTC").value
            q1=0.5/r["S_entry"]
            if gt_ns>=ext:
                U_i+=N*q1*ex["realized_unit"]
            elif gt_ns>pd.Timestamp(r["entry"],tz="UTC").value:
                tns,cl=m1m[c]
                S_t=get_close(tns,cl,gt_ns)
                dvol_ns,dvol_c=dvol[c]
                sig=latest_dvol(dvol_ns,dvol_c,gt_ns)
                exp_ts=pd.Timestamp(r["expiry"],tz="UTC").value
                T_rem=(exp_ts-gt_ns)/1e9/SEC_PER_YEAR
                if np.isfinite(S_t) and np.isfinite(sig):
                    mk=mark_unit_at(r,S_t,sig,max(T_rem,0.0))
                    U_i+=N*q1*(r["opt_cash_unit"]-mk)
        dU=U_i-U_prev
        g=Etot[i]/Etot[i-1]; hh=Mtot[i]/Etot[i-1]
        A_c[i]=A_prev*g+dU; M_c[i]=A_prev*hh+dU
        A_prev,U_prev=A_c[i],U_i
    segf=np.asarray(grid>pd.Timestamp("2021-09-24",tz="UTC"))
    esf,msf=A_c[segf],M_c[segf]
    dd_m=round(100*float(np.max(1-msf/np.maximum.accumulate(esf))),2)
    dd_c=round(100*float(np.max(1-esf/np.maximum.accumulate(esf))),2)
    out["overlay_f025_per_year"]=ov_years
    out["overlay_f025_5y_R"]=R5ov
    out["overlay_f025_5y_W"]=W5ov
    out["overlay_f025_5y_maxDD"]=max(yy["DD"] for yy in ov_years)
    out["overlay_f025_full_marked"]=dd_m
    out["overlay_f025_full_close"]=dd_c
    out["overlay_f025_full"]=max(dd_m,dd_c)
    (HERE/"replication.json").write_text(json.dumps(out,indent=1))
    print(json.dumps({k:(v if not isinstance(v,list) else v) for k,v in out.items() if k!="meta"},indent=1))

if __name__=="__main__":
    main()

