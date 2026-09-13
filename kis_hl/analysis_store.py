"""Minimal reproducible market analysis; no strategy authority or order execution."""
from decimal import Decimal as D
from kis_hl.data_store import now_ms


def run_analysis(store, spec, *, as_of_ms=None):
    asof=now_ms() if as_of_ms is None else as_of_ms
    required={'instrument','provider','timeframe','adjustment','price_basis','variant','calendar'}
    if not required<=spec.keys():raise ValueError('Explicit complete market variant required')
    rows=[f for f in store.facts('bar',as_of_ms=asof) if all(f['payload'].get(k)==spec[k] for k in required) and f['payload']['complete'] and f['event_end_ms']<=asof]
    if not rows:raise ValueError('No completed eligible bars for this as-of variant')
    count=spec.get('window',20)
    if type(count) is not int or count<=0:raise ValueError('Positive analysis window required')
    rows=rows[-count:]
    if len(rows)<count:raise ValueError('Insufficient completed bars')
    close=[D(f['payload']['close']) for f in rows]
    result={'last_close':str(close[-1]),'mean_close':str(sum(close,D(0))/len(close)),'bar_count':len(rows),'calculation_version':'close-summary-v1','mode':'retrospective_research'}
    run=store.pin('analysis',spec,[r['id'] for r in rows],result,as_of_ms=asof)
    return {'analysis_id':run,**result}
