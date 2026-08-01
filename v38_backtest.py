import csv, math, os, sys, json
sys.path.insert(0, os.getcwd())
from src import opportunity_score as osc
from src import opportunity_inbox as oib

rows = list(csv.DictReader(open("/mnt/user-data/uploads/22etsy-agent/keyword_data.csv", encoding="utf-8-sig")))
K = 100  # logistic steepness (midpoint 2.5%)

def logistic_conv(cr, k=K):
    return 100.0/(1.0+math.exp(-k*(cr-0.025)))

def market_v38(d, k=K):
    demand = osc._demand_from(d)
    velocity = osc._first(d, "momentum_score", "velocity")
    cr = osc._first(d, "avg_conversion_rate", "conversion_rate", "conversion")
    conv = None if cr is None else logistic_conv(cr, k)
    parts = [(demand,.40),(velocity,.35),(conv,.25)]
    avail = [(x,w) for x,w in parts if x is not None]
    if not avail: return None
    return round(sum(x*w for x,w in avail)/sum(w for _,w in avail),1)

def comp_v38(d, intended=False):
    listings = osc._num(d.get("listing_count"))
    if listings is None: return None
    ci = max(10.0, min(95.0, -40.0+41.0*math.log10(max(listings,1.0))))
    base = 100.0-ci
    sellers = osc._num(d.get("seller_count")) or 0.0
    term = 10.0*(sellers/max(1.0,listings)) if intended else 10.0*(1.0-(sellers/max(1.0,listings)))
    return round(max(0.0, min(100.0, base+term)),1)

def verdict_from(overall, ip, core_missing, dg):
    if ip=="high": return "SKIP"
    if overall is None or core_missing: return "WATCH"
    if (not dg) and overall>=50: return "WATCH"
    if overall>=80: return "GO"
    if overall>=65: return "CONDITIONAL"
    if overall>=50: return "WATCH"
    return "SKIP"

def overall_with(subs, w):
    avail=[(subs[k],w[k]) for k in subs if subs[k] is not None]
    return round(sum(v*wt for v,wt in avail)/sum(wt for _,wt in avail),1) if avail else None

from collections import Counter
cur_dist=Counter(); v38_dist=Counter(); intended_dist=Counter()
flips=[]; flips_intended=[]; recs=[]
for row in rows:
    d,*_ = oib._to_scorer(row)
    kw=d.get("tag") or ""
    s=osc.score(d, keyword=kw)
    subs=s["sub_scores"]; w=s["weights_used"]; ip=s["ip_risk"]; dg=s["demand_grounded"]
    core_missing = subs["market_potential"] is None or subs["competition_health"] is None
    cur_v=s["verdict"]; cur_o=s["overall_score"]
    # v38 as written
    M2=market_v38(d); C2=comp_v38(d, intended=False)
    subs2=dict(subs, market_potential=M2, competition_health=C2)
    o2=overall_with(subs2,w); v2=verdict_from(o2,ip,core_missing,dg)
    # v38 with the "intended" (favor multi-seller) competition term
    C3=comp_v38(d, intended=True)
    subs3=dict(subs, market_potential=M2, competition_health=C3)
    o3=overall_with(subs3,w); v3=verdict_from(o3,ip,core_missing,dg)
    cur_dist[cur_v]+=1; v38_dist[v2]+=1; intended_dist[v3]+=1
    rec=dict(kw=kw, listings=osc._num(d.get("listing_count")), sellers=osc._num(d.get("seller_count")),
             cr=osc._first(d,"avg_conversion_rate","conversion_rate"),
             curM=subs["market_potential"], curC=subs["competition_health"], curO=cur_o, curV=cur_v,
             v38M=M2, v38C=C2, v38O=o2, v38V=v2, intV=v3)
    recs.append(rec)
    if v2!=cur_v: flips.append(rec)
    if v3!=cur_v: flips_intended.append(rec)

def pct(c,n): return f"{100*c/n:.1f}%"
n=len(rows)
print(f"N = {n}\n")
order=["GO","CONDITIONAL","WATCH","SKIP"]
print(f"{'verdict':<12}{'CURRENT':>10}{'v38(as-written)':>18}{'v38(intended)':>16}")
for v in order:
    print(f"{v:<12}{cur_dist[v]:>6} {pct(cur_dist[v],n):>7}   {v38_dist[v]:>6} {pct(v38_dist[v],n):>7}   {intended_dist[v]:>6} {pct(intended_dist[v],n):>7}")
print(f"\nverdict CHANGED (as-written): {len(flips)}/{n} = {pct(len(flips),n)}")
print(f"verdict CHANGED (intended)  : {len(flips_intended)}/{n} = {pct(len(flips_intended),n)}")

# direction of flips (as-written)
def rank(v): return order.index(v)
up=sum(1 for r in flips if rank(r['v38V'])<rank(r['curV']))
down=sum(1 for r in flips if rank(r['v38V'])>rank(r['curV']))
print(f"  of those: {up} upgraded (toward GO), {down} downgraded")

# conversion delta stats (isolate MATH-01): current conv vs logistic
print("\n-- conversion sub-score examples (MATH-01) --")
for cr in [0.005,0.01,0.02,0.025,0.03,0.05,0.08,0.12]:
    curc = cr*1600 if cr<=0.05 else 80+20*(1-math.exp(-25*(cr-0.05)))
    print(f"  cr={cr*100:4.1f}%  current={curc:5.1f}   v38-logistic(k={K})={logistic_conv(cr):5.1f}")

# seller term examples (MATH-02)
print("\n-- competition seller-term examples (MATH-02, as-written) --")
for r in sorted(recs, key=lambda x:-(x['v38C']-x['curC']))[:5]:
    print(f"  {r['kw'][:28]:<28} listings={r['listings']:.0f} sellers={r['sellers']:.0f}  curC={r['curC']}  v38C={r['v38C']}  (+{r['v38C']-r['curC']:.1f})")

# example flips (as-written)
print("\n-- example verdict flips (as-written) --")
for r in flips[:12]:
    print(f"  {r['kw'][:26]:<26} {r['curV']:>11} -> {r['v38V']:<11} | O {r['curO']}->{r['v38O']}  M {r['curM']}->{r['v38M']} C {r['curC']}->{r['v38C']}")

json.dump({"n":n,"current":dict(cur_dist),"v38":dict(v38_dist),"intended":dict(intended_dist),
           "flips":len(flips),"flips_intended":len(flips_intended),"up":up,"down":down,
           "recs":recs}, open("backtest_result.json","w"))
print("\nsaved backtest_result.json")
