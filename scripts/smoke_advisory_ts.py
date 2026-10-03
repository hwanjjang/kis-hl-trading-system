"""Integrated offline SQLite/info-transport smoke; no credentials or real network."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kis_hl.advisory_ts import Monitor, load_owner, load_entry_ids
from tests.test_advisory_ts import COINS, ReadOnlyInfo, candles, owner


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        operational = root/'operational.sqlite'
        state = root/'alert.sqlite'
        with sqlite3.connect(operational) as db:
            db.execute('CREATE TABLE managed_positions (id TEXT PRIMARY KEY, state TEXT, snapshot TEXT)')
            db.execute('CREATE TABLE managed_attempts (position_id TEXT, kind TEXT, snapshot TEXT)')
            for coin, oid in COINS.items():
                st, data=owner(coin,oid)
                db.execute('INSERT INTO managed_positions VALUES(?,?,?)',(oid,st,json.dumps(data)))
        original=operational.read_bytes()
        info=ReadOnlyInfo()
        with sqlite3.connect(state) as conn:
            monitor=Monitor(conn,info,lambda oid:load_owner(operational,oid),lambda oid:load_entry_ids(operational,oid))
            conn.executemany('INSERT INTO bars VALUES(?,?,?,?,?)',[(c,1000,540000,'23.264','20.0876') for c in COINS])
            del info.raw['xyz:KORU'][4]
            first=monitor.tick(COINS,1095001)
            assert first['diagnostics']['xyz:KORU']['reason']=='coverage_gap'
            assert first['diagnostics']['xyz:SP500']['covered_through_ms']==1080000
            assert conn.execute("SELECT last_end,high,threshold FROM bars WHERE coin='xyz:KORU'").fetchone()==(540000,'23.264','20.0876')
            info.raw['xyz:KORU']=candles()
            recovery=monitor.tick(COINS,1097000)
            assert sum('recovered' in m for m in recovery['messages'])==1
            assert not monitor.tick(COINS,1099000)['messages']
            assert operational.read_bytes()==original
            print(json.dumps(dict(scenario='boundary_gap_retry', degraded=first['diagnostics']['xyz:KORU'],
                                  recovery=recovery['messages'], operational_database_unchanged=True),sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
