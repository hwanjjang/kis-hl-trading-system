# Review 5308021468 correction: independent verification

Verdict: **PASS**. No unresolved Must Fix findings in the three requested correction
areas. This receipt covers the local candidate identified below, not a remote PR
head, CI result, merge authorization, or live exchange behavior.

Verifier: delegated OpenAI child context `/root/verify_issue27`, independent from the
implementation author. This is local independent correction verification, not a
cross-provider PR review. Main owns SDLC accounting and any authorized publication.
Date: 2026-09-24, approximately 17:55–17:58 UTC.
Base HEAD: `b6cad43dd636b0c77bff627af7ea042fa4e9c620`.
Reviewed input: `reports/sdlc/issue-27/review-5308021468.md`, current source/test diff,
capital/add/exit owner docs and the Hyperliquid error-reference update.

The verifier changed only this report and an isolated `/tmp` probe. No production
source, tests, shared receipts, account data, signed venue requests, GitHub posts,
commits or pushes were changed by this verifier.

## Assessed corrections

| Area | Verdict | Evidence and preserved boundaries |
| --- | --- | --- |
| Native non-fill termination with another full overlay | PASS | Canceled/rejected/expired older trails retain PROTECTED with active verified coverage 1.5. Independent probes reverse persisted attempt traversal after SQLite reopen: no exit, cancellation, new native trail or watermark reset. Smaller, inactive, unverified or canceled replacement trails fail to establish full coverage and still request a full residual exit. Coverage is the maximum individually verified full-size trail, never a sum of small orders. |
| Protective fills and uncertain native submissions | PASS | Actual old-trail fill still exits residual .5. A .2 protective fill followed by old-trail cancellation still exits residual 1.3 despite valid full overlay. A single canceled trail exits 1.0. An UNKNOWN native submission remains INTERVENTION even with another valid overlay and is not resent. |
| Transient pre-submission reads | PASS | Only typed TransientInfoError remains QUEUED before a durable add send. HTTP 408/429/500/502/503/504 and URL/timeout/connection errors are classified by transport tests; permanent HTTP, identity and schema failures remain outside this retry class. Recovery/reopen sends once; expiry rejects without another preflight. An independent grant-revocation-after-transient probe performs only one read and zero add sends. Authority is checked before each preflight and again after successful reads. |
| Signed unknown outcomes | PASS | Independent probe throws TransientInfoError from signed `submit`, then reopens SQLite and advances three ticks. One add attempt remains UNKNOWN and is never retransmitted; the read retry classification does not create a second signed lifecycle. |
| Unsupported capital components | PASS | Nonzero/malformed/negative escrow totals, borrowed/supplied values, and contradictory or malformed portfolioMarginEnabled evidence reject. Zero-valued supported optional shapes preserve capital 10000 and one-unit risk 100 from total balance 1000; unsupported fields are not added as a guessed valuation. |

## Executed commands and outcomes

Commands ran serially after the author released the shared fixture account lock.

```bash
/tmp/hl-trailing-venv/bin/python -m unittest tests.test_conditional_add tests.test_managed_execution tests.test_managed_gateways tests.test_strategy_signals tests.test_strategy_tools tests.test_native_trailing tests.test_manual_adoption tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk -q
PYTHONPATH=. /tmp/hl-trailing-venv/bin/python /tmp/issue27-reviewfix-independent-probe.py
/tmp/hl-trailing-venv/bin/python -m unittest tests.test_hyperliquid_client -q
/tmp/hl-trailing-venv/bin/python scripts/smoke_conditional_add.py
git diff --check
```

1. Full changed-scope run: **192 tests passed in 26.875s**, exit 0.
2. Independent probe: **15 cases passed**, exit 0, socket creation forbidden. Source
   is reproduced in the appendix so the `/tmp` location is not its only record.
3. The author then closed retryable HTTP error responses before raising. The final
   client candidate was reread and its **34 tests passed in 0.673s**, exit 0.
   Other tested source files were unchanged, so prior lifecycle evidence remains
   applicable. The client digest below includes `exc.close()`.
4. CLI/SQLite smoke: passed, exit 0, network forbidden. Each CLI invocation reopens
   temporary SQLite. Total balance 1000, operating capital 10000, one add attempt,
   add fill .5, remaining exposure 1.5, fixed-SL coverage 1.5, native-TS coverage 1.5,
   final state PROTECTED. The smoke is additional integrated evidence, not a unit
   test relabeled as smoke.
5. `git diff --check`: passed, exit 0.

The independent probes supplement repository regressions with reversed attempt
ordering after reopen, combined cancellation and real fill evidence, transient
failure followed by grant revocation, and the transient exception type raised from
the signed-send boundary. No new mandatory findings were identified.

## Limits

All gateway/API responses were stubs or mocked transport errors. This report makes
no claim about real occurrence of extra capital fields under unified account mode,
their correct monetary valuation, live cancellation/activation timing, exchange
acceptance of overlapping native trails, or production restart behavior. Unknown
components fail closed; no unsupported amount is inferred. No live authority was
activated, no live accounts were read, and no orders were placed. Tests cannot
establish cross-provider PR-review eligibility or remote merge readiness.

## Candidate SHA-256 identities

```text
465c481ba05412d1429519fcae4cf426aa3ef5d728f782a1dbb99d09f5cf33dc  kis_hl/account_capital.py
14833a4a6a09100d3f3b6578fc802b868d94f91ccd74878665ffea48e2ab2170  kis_hl/conditional_add.py
15203945adfabba91da059069be37cad340be0a16bef954811efd1996d1c61ec  kis_hl/managed_execution.py
0ecb3e02374f5c672896050f7f5d15c2a9e2ce9acbd4017bccd4de08969fa9ff  kis_hl/hyperliquid/client.py
966dadf31088239d8b52d8976966e93da73ac4ba8d71fae45fc5c8795a7a04f2  tests/test_conditional_add.py
1aa76b58a0fda91d519a18c0fc44fe1c2caa1dcf62d938cc9e858e2896cf368a  tests/test_hyperliquid_client.py
ac2ee7c894a5fb1f66c3b3a987b684169f86b8bfe41e68d1bc1bb7d673103de6  docs/trading-operations.md
7510dc9393d865627536397ba6e927c8e881c373d5b3c1b67511a383f7e6b17f  docs/strategy-tools.md
4bd3841aaef44dcfeec57d54a42ec135840933ab94508c04fec0d125d7ab4907  docs/strategy_execution_design.md
baeef62a9ca7c3cf238377007a88b356df9843dcf4bd88d4404559c9033df223  .agents/skills/hyperliquid-api/references/limits-and-errors.md
451c5705bf0dfdbcd2b8c8bfa5014d61ac545b5b90de9e76668d755b7971fd6f  scripts/smoke_conditional_add.py
878ba3c5f9362b7602a916f9eedcdf7f9e4dc908770097ded98114e8c6cb2f59  /tmp/issue27-reviewfix-independent-probe.py
```

## Independent probe source

Recreate the exact `/tmp` path from this source and run the command above. It uses
repository fixtures with fresh temporary databases and forbids network sockets.

```python
import json
import socket
from decimal import Decimal
from unittest.mock import patch
from tests.test_conditional_add import ConditionalAddTests, NOW, sizing
from kis_hl.hyperliquid.client import TransientInfoError
from kis_hl.managed_execution import ExecutionStore, Supervisor
from kis_hl.strategy_tools import size_position

results=[]
def fresh():
    c=ConditionalAddTests(); c.setUp(); return c

def exits(c):
    return [a['quantity'] for a in c.g.sent if a['kind']=='exit']

with patch.object(socket,'socket',side_effect=AssertionError('Network forbidden')):
    for status in ('canceled','rejected','expired'):
        c=fresh()
        try:
            c.test_native_overlay_preserves_old_watermark_and_covers_combined_size()
            trails=[a for a in c.g.sent if a['kind']=='trailing']
            c.g.orders[trails[0]['id']]['status']=status
            store=ExecutionStore(c.store.path)
            original=store.attempts
            store.attempts=lambda position_id: list(reversed(original(position_id)))
            worker=Supervisor(store,c.g,live=True)
            with patch.object(c.g,'cancel',wraps=c.g.cancel) as cancel:
                row=worker.step(c.row['id'],NOW+20)
                assert row['state']=='PROTECTED' and not row['exit_requested_ms']
                assert Decimal(row['trailing_covered_size'])==Decimal('1.5')
                assert not exits(c) and cancel.call_count==0
            assert len([a for a in c.g.sent if a['kind']=='trailing'])==2
            results.append(dict(case='reversed-order-old-'+status,state=row['state'],native_coverage=row['trailing_covered_size'],exit_count=0))
        finally:c.doCleanups()
    for status,remaining,fill in (('filled','0.5','1'),('canceled','1.3','0.2')):
        c=fresh()
        try:
            c.test_native_overlay_preserves_old_watermark_and_covers_combined_size()
            old=next(a for a in c.g.sent if a['kind']=='trailing')
            c.g.orders[old['id']]['status']=status
            c.g.size=remaining; c.g.protective_filled=fill
            row=c.worker.step(c.row['id'],NOW+20)
            assert exits(c)==[remaining]
            results.append(dict(case='protective-fill-with-'+status,exit_quantities=exits(c)))
        finally:c.doCleanups()
    c=fresh()
    try:
        c.native_fixture()
        old=next(a for a in c.g.sent if a['kind']=='trailing')
        c.g.orders[old['id']]['status']='canceled'
        c.worker.step(c.row['id'],NOW+20)
        assert exits(c)==['1']
        results.append(dict(case='single-trail-canceled',exit_quantities=exits(c)))
    finally:c.doCleanups()
    c=fresh()
    try:
        c.test_native_overlay_preserves_old_watermark_and_covers_combined_size()
        old=next(a for a in c.store.attempts(c.row['id']) if a['kind']=='trailing')
        c.store.update_attempt(old,order_id=None,status='UNKNOWN')
        row=c.worker.step(c.row['id'],NOW+20)
        assert row['state']=='INTERVENTION' and row['native_trailing_intervention']
        assert not exits(c) and len([a for a in c.g.sent if a['kind']=='trailing'])==2
        results.append(dict(case='unknown-native-with-full-overlay',state=row['state'],resent=False))
    finally:c.doCleanups()
    c=fresh()
    try:
        grant=dict(id='grant',scope='scope',strategy='fixture',strategy_version='1',instruments=['hl:ETH'],max_notional='100',max_intents=1,live=True,actions=['add'],signal_ids=['add-once'],position_ids=[c.row['id']],expires_ms=NOW+50000)
        c.signals.grant(grant,now_ms=NOW)
        c.signals.execute('add-once','scope',c.plan,grant_id='grant',live=True,now_ms=NOW+5)
        calls=[]
        def fail(*args,**kwargs):
            calls.append(1); raise TransientInfoError('Temporary read unavailable')
        c.g.preflight=fail
        c.worker.step(c.row['id'],NOW+10)
        assert c.store.tranches(c.row['id'])[0]['status']=='QUEUED'
        c.signals.revoke('grant')
        c.worker.step(c.row['id'],NOW+11)
        assert len(calls)==1 and c.store.tranches(c.row['id'])[0]['status']=='REJECTED'
        assert not any(a['kind']=='add' for a in c.g.sent)
        results.append(dict(case='transient-then-revoked',preflight_calls=len(calls),status='REJECTED',add_count=0))
    finally:c.doCleanups()
    c=fresh()
    try:
        c.authorize(); original=c.g.submit
        def unknown(row,attempt):
            if attempt['kind']=='add':
                c.g.sent.append(dict(attempt)); raise TransientInfoError('Failure after signed transmission')
            return original(row,attempt)
        c.g.submit=unknown
        c.worker.step(c.row['id'],NOW+10)
        store=ExecutionStore(c.path); worker=Supervisor(store,c.g,live=True)
        for tick in (11,12,13):worker.step(c.row['id'],NOW+tick)
        assert len([a for a in c.g.sent if a['kind']=='add'])==1
        assert store.tranches(c.row['id'])[0]['status']=='UNKNOWN'
        results.append(dict(case='signed-transient-class-is-still-unknown',add_count=1,status='UNKNOWN'))
    finally:c.doCleanups()
    for name,change in [('escrow-nonzero',lambda s:s.update(evmEscrows=[dict(coin='USDC',token=0,total='1')])),('escrow-negative',lambda s:s.update(evmEscrows=[dict(coin='USDC',token=0,total='-1')])),('escrow-malformed',lambda s:s.update(evmEscrows={})),('borrowed-nonzero',lambda s:s['balances'][0].update(borrowed='1')),('supplied-malformed',lambda s:s['balances'][0].update(supplied=None)),('contradictory-mode',lambda s:s.update(portfolioMarginEnabled=True))]:
        req=sizing();change(req['capital_evidence']['spot'])
        try:size_position(req,now_ms=NOW)
        except ValueError:results.append(dict(case=name,status='REJECTED'))
        else:raise AssertionError(name+' accepted')
print(json.dumps(dict(result='passed',network='forbidden',cases=results),indent=2))
```
