"""Conservative economic representation selection for mixed-grain funding."""
from decimal import Decimal as D


def effective_funding(facts):
    funding=[f for f in facts if f['payload'].get('kind')=='funding']
    blocked=set();issues=[]
    for day in funding:
        p=day['payload']
        if p['grain']!='DAY':continue
        overlapping=[f for f in funding if f['id']!=day['id'] and f['scope']==day['scope'] and f['instrument']==day['instrument']
            and f['payload']['currency']==p['currency'] and f['event_start_ms']<day['event_end_ms'] and f['event_end_ms']>day['event_start_ms']]
        if not overlapping:continue
        points=[f for f in overlapping if f['payload']['grain']=='POINT']
        # Only all expected distinct samples with a matching sum establish equivalence.
        if len(points)==len(overlapping)==p.get('samples') and len({f['event_start_ms'] for f in points})==len(points) and sum((D(f['payload']['amount']) for f in points),D(0))==D(p['amount']):
            blocked.add(day['id'])
        else:
            ids={day['id'],*(f['id'] for f in overlapping)}
            blocked.update(ids)
            issues.append({'kind':'funding_representation_conflict','scope':day['scope'],'instrument':day['instrument'],'currency':p['currency'],'fact_ids':sorted(ids)})
    return [f for f in funding if f['id'] not in blocked],issues
