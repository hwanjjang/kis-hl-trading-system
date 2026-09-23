"""Offline harness handoff through CLI, SQLite and real supervisor/gateway."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from kis_hl.cli import main
from kis_hl.managed_execution import ExecutionStore, Supervisor
from kis_hl.managed_gateways import ManagedHyperliquidGateway
from kis_hl.journal_sync import Scope
from scripts.smoke_native_trailing import ReplayExchange, main as native_smoke
from tests.test_managed_execution import plan


class ManualExchange(ReplayExchange):
    def __init__(self, store, **kwargs):
        super().__init__(store, **kwargs)
        self.verification_db_path = store.path

    def _require_credentials(self):
        pass  # This exchange boundary is entirely in memory.

    def user_fills(self):
        return list(self.fills)

    def cancel_order(self, *, symbol, oid, dry_run):
        assert symbol == "BTC" and dry_run is False
        self.orders[oid]["status"] = "canceled"
        from types import SimpleNamespace
        return SimpleNamespace(status="submitted", response={"status":"ok"})


def handoff(root):
    store=ExecutionStore(root/"handoff.sqlite")
    ex=ManualExchange(store,reject_trailing=False)
    start=ex.now
    ex._accept("manual-entry",dict(side="B",sz="0",origSz="1",timestamp=start-100,
                                  reduceOnly=False,isTrigger=False,orderType="Limit"))
    ex.orders[100]["status"]="filled";ex.size="1"
    ex.fills=[dict(time=start-99,tid=1,oid=100,coin="BTC",side="B",sz="1",px="100000",startPosition="0")]
    ex._accept("manual-stop",dict(side="A",sz="1",reduceOnly=True,isTrigger=True,
                                 orderType="Stop Market",triggerPx="99996"))
    ex.sent=[]
    p=plan(harness="hermes");p.pop("trailing_provider",None)
    p.update(limit_price="100000",max_notional="100001",max_portfolio_notional="1000000",
             max_correlated_notional="500000",expires_ms=start+100000)
    source=root/"handoff.json";source.write_text(json.dumps(p))
    out=io.StringIO()
    with patch("kis_hl.cli.load_env_file"),patch("kis_hl.operations_cli.time.time",return_value=start/1000),patch("kis_hl.operations_cli.scope_client",return_value=(Scope("hyperliquid","testnet",ex.config.account_address),ex)),contextlib.redirect_stdout(out):
        code=main(["--db",str(store.path),"order","adopt","--input",str(source),
                   "--entry-order-id","100","--stop-order-id","101","--live"])
    assert code == 0,out.getvalue()
    row=json.loads(out.getvalue());assert row["state"]=="ADOPTING" and not ex.sent
    worker=Supervisor(store,ManagedHyperliquidGateway(ex,ex),live=True)
    def step(offset,restart=False):
        nonlocal worker
        ex.now=start+offset
        if restart: worker=Supervisor(ExecutionStore(store.path),ManagedHyperliquidGateway(ex,ex),live=True)
        with patch("kis_hl.managed_gateways.time.time",return_value=ex.now/1000):
            return worker.step(row["id"],ex.now)
    admitted=step(1)
    assert admitted["state"]=="PROTECTING",admitted
    assert admitted["plan"]["trailing_provider"]=="native"
    assert admitted["providers"]["local_trailing_backup"] is True
    assert admitted["fill_history_start_ms"]==start-100 and not ex.sent
    step(2);assert ex.sent==["trailing"]
    # The independent local quote crosses its floor while native is still waiting.
    book=ex.l2_book
    ex.l2_book=lambda symbol:book(symbol) | {"levels":[[{"px":"99995"}],[{"px":"99995.1"}]]}
    exiting=step(3)
    assert ex.sent==["trailing","exit"],exiting
    assert ex.orders[101]["status"]==ex.orders[102]["status"]=="open"
    # Exchange trail reduces part of the position while the local IOC resolves canceled.
    ex.orders[103]["status"]="canceled"
    ex.orders[102]["order"]["sz"]="0.6"
    ex.size="0.6"
    ex.fills.append(dict(time=start+4,tid=2,oid=102,coin="BTC",side="A",sz="0.4"))
    step(4,restart=True)
    assert ex.sent==["trailing","exit","exit"]
    assert ex.orders[104]["order"]["sz"]=="0.6"
    ex.orders[104]["status"]="filled";ex.size="0"
    ex.fills.append(dict(time=start+5,tid=3,oid=104,coin="BTC",side="A",sz="0.6"))
    assert step(5)["state"]=="CLEANUP"
    assert step(6,restart=True)["state"]=="CLOSED"
    assert ex.orders[101]["status"]==ex.orders[102]["status"]=="canceled"
    assert len([a for a in store.attempts(row["id"]) if a["kind"]=="entry"])==1
    assert all(a.get("imported") for a in store.attempts(row["id"])[:2])
    return True


def main_smoke():
    native_smoke()
    with tempfile.TemporaryDirectory() as directory:
        assert handoff(Path(directory))
    print(json.dumps({"status":"passed","manual_cli_handoff":True,"atomic_owned_id_import":True,
        "native_plus_local":True,"partial_native_local_exit_race":True,"restart_cleanup":True,
        "new_entry_orders":0,"network_requests":0,"live_exchange_verified":False}))


if __name__=="__main__": main_smoke()
