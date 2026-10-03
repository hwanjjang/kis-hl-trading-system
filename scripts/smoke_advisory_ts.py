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
            before=conn.execute("SELECT * FROM bars WHERE coin='xyz:KORU'").fetchone()
            for coin in COINS:
                info.raw[coin]=candles(start=1080000)
            info.raw['xyz:KORU'][0]['h']='50'
            conn.execute("CREATE TRIGGER late_write_failure BEFORE INSERT ON alerts WHEN NEW.coin='xyz:KORU' AND NEW.kind='breach' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
            late=monitor.tick(COINS,1635001)
            assert conn.execute("SELECT * FROM bars WHERE coin='xyz:KORU'").fetchone()==before
            assert late['diagnostics']['xyz:KORU']['reason']=='read_unavailable'
            assert late['diagnostics']['xyz:SP500']['reason']=='verified'
            assert not any('TS advisory:' in m or 'recovered' in m for m in late['messages'])
            conn.execute('DROP TRIGGER late_write_failure')
            assert sum('recovered' in m for m in monitor.tick(COINS,1637000)['messages'])==1
            assert operational.read_bytes()==original
            # Model a supervisor-produced CLOSED/zero snapshot outside the monitor.
            with sqlite3.connect(operational) as db:
                _, data=owner('xyz:KORU',COINS['xyz:KORU']);data['observed_size']='0'
                db.execute('UPDATE managed_positions SET state=?,snapshot=? WHERE id=?',
                           ('CLOSED',json.dumps(data),COINS['xyz:KORU']))
            del info.quantities['xyz:KORU']
            closed_fixture=operational.read_bytes()
            closed=monitor.tick(COINS,1639000)
            assert closed['diagnostics']['xyz:KORU']['reason']=='closed'
            assert not any('recovered' in m or 'degraded:' in m for m in closed['messages'])
            assert not monitor.tick(COINS,1640000)['messages']
            assert operational.read_bytes()==closed_fixture
            print(json.dumps(dict(scenario='boundary_gap_retry', degraded=first['diagnostics']['xyz:KORU'],
                                  recovery=recovery['messages'], late_write_rollback=True, closed_zero_owner='closed',
                                  operational_database_unchanged_by_monitor=True),sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
