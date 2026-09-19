"""CLI entry points for canonical data, market collection and pinned analysis."""
from datetime import date
import json
from pathlib import Path
import time
from kis_hl.data_store import DataStore, now_ms


def register(sub):
    data=sub.add_parser('data',help='Manage canonical local evidence and analysis storage')
    ds=data.add_subparsers(dest='data_action',required=True)
    for action in ['status','migrate','retention']:
        p=ds.add_parser(action);p.set_defaults(handler=cmd_data)
        if action=='migrate':p.add_argument('--apply',action='store_true')
    p=ds.add_parser('import');p.add_argument('--manifest',required=True);p.add_argument('--apply',action='store_true');p.set_defaults(handler=cmd_data)
    for action in ['backup','restore']:
        p=ds.add_parser(action);p.add_argument('--target',required=True);p.set_defaults(handler=cmd_data)
        if action=='restore':p.add_argument('--source',required=True)
    p=ds.add_parser('reconcile');p.add_argument('--statement',required=True);p.add_argument('--sha256',required=True);p.add_argument('--apply',action='store_true');p.set_defaults(handler=cmd_data)
    p=ds.add_parser('journal');p.add_argument('--accounts',nargs='+',required=True);p.add_argument('--as-of-ms',type=int);p.set_defaults(handler=cmd_data)
    p=ds.add_parser('export');p.add_argument('--report-id',type=int,required=True);p.add_argument('--output',required=True);p.set_defaults(handler=cmd_data)
    p=ds.add_parser('configure');p.add_argument('--job-id',required=True);p.add_argument('--config',required=True);p.add_argument('--interval-seconds',type=int,default=10800);p.set_defaults(handler=cmd_data)
    p=ds.add_parser('sync');p.add_argument('--venue',choices=['kis','hyperliquid'],required=True);p.add_argument('--account');p.add_argument('--start-ms',type=int,required=True);p.add_argument('--end-ms',type=int);p.set_defaults(handler=cmd_data)
    market=sub.add_parser('market',help='Collect weekly/daily/minute bars and periodic snapshots')
    ms=market.add_subparsers(dest='market_action',required=True)
    p=ms.add_parser('backfill');p.add_argument('--instrument',required=True);p.add_argument('--timeframe',choices=['1w','1d','1m'],default='1w');p.add_argument('--years',type=int,default=10);p.add_argument('--start',type=date.fromisoformat);p.add_argument('--end',type=date.fromisoformat);p.set_defaults(handler=cmd_market)
    p=ms.add_parser('snapshot');p.add_argument('--instrument',required=True);p.add_argument('--kind',choices=['book','quote','funding'],default='book');p.set_defaults(handler=cmd_market)
    p=ms.add_parser('collect');p.add_argument('--once',action='store_true');p.add_argument('--poll-seconds',type=int,default=30);p.set_defaults(handler=cmd_market)
    analysis=sub.add_parser('analysis',help='Pin a reproducible market analysis')
    an=analysis.add_subparsers(dest='analysis_action',required=True)
    p=an.add_parser('run');p.add_argument('--spec',required=True);p.add_argument('--as-of-ms',type=int);p.set_defaults(handler=cmd_analysis)


def cmd_data(args):
    from kis_hl.data_import import import_manifest
    from kis_hl.data_maintenance import backup,restore,retention_preview
    from kis_hl.data_jobs import configure
    from kis_hl.journal_exports import journal,export_report
    if args.data_action=='restore':return restore(args.source,args.target)
    if args.data_action=='status' or (args.data_action=='migrate' and not args.apply):
        from kis_hl.data_migrations import inspect_schema
        schema=inspect_schema(args.db)
        if args.data_action=='migrate' or schema['schema_version']==0:return schema
        return DataStore(args.db,readonly=True).status()
    if args.data_action=='import' and not args.apply:
        return import_manifest(None,args.manifest,apply=False,existing_path=args.db)
    store=DataStore(args.db,readonly=args.data_action=='reconcile' and not args.apply)
    if args.data_action=='reconcile':
        from kis_hl.data_reconciliation import reconcile
        return reconcile(store,args.statement,args.sha256,apply=args.apply)
    if args.data_action in {'status','migrate'}:return store.status()
    if args.data_action=='retention':return retention_preview(store)
    if args.data_action=='import':return import_manifest(store,args.manifest,apply=True)
    if args.data_action=='backup':return backup(store,args.target)
    if args.data_action=='journal':return journal(store,args.accounts,as_of_ms=args.as_of_ms)
    if args.data_action=='export':return export_report(store,args.report_id,args.output)
    if args.data_action=='configure':return configure(store,args.job_id,json.loads(Path(args.config).read_text()),args.interval_seconds)
    if args.data_action=='sync':
        from kis_hl.data_account_sync import sync_account
        return sync_account(store,args.venue,args.account,start_ms=args.start_ms,end_ms=args.end_ms)


def client_for(key):
    from kis_hl.instruments import instrument
    from kis_hl.operations_cli import kis_client
    from kis_hl.hyperliquid.client import HyperliquidInfoClient
    from kis_hl.config import load_hyperliquid_config
    return kis_client() if instrument(key).venue=='kis' else HyperliquidInfoClient(load_hyperliquid_config())


def execute_job(store,config):
    from kis_hl.market_ingestion import backfill,snapshot
    if config['kind']=='account':
        from kis_hl.data_account_sync import sync_account
        start=config['start_ms']
        overlap=config.get('overlap_ms',86400000)
        if type(overlap) is not int or overlap<0:raise ValueError('Nonnegative account overlap required')
        if config.get('_last_success_ms') is not None and not config.get('history_audit',False):
            start=max(start,config['_last_success_ms']-overlap)
        return sync_account(store,config['venue'],config.get('account'),start_ms=start)
    key=config['instrument'];client=client_for(key)
    if config['kind']=='bar':
        # Refresh a short overlap; history backfill is an explicit separate operation.
        from datetime import timedelta
        if config['timeframe']=='1m':
            previous=config.get('_last_success_ms')
            start_ms=max(0,previous-300000) if previous is not None else now_ms()-1800000
            return backfill(store,key,'1m',client,start_ms=start_ms)
        return backfill(store,key,config['timeframe'],client,start=date.today()-timedelta(days=config.get('overlap_days',14)))
    return snapshot(store,key,client,kind=config['kind'])


def cmd_market(args):
    from kis_hl.market_ingestion import backfill,snapshot
    from kis_hl.data_jobs import run_due
    store=DataStore(args.db)
    if args.market_action=='backfill':return backfill(store,args.instrument,args.timeframe,client_for(args.instrument),years=args.years,start=args.start,end=args.end)
    if args.market_action=='snapshot':return snapshot(store,args.instrument,client_for(args.instrument),kind=args.kind)
    if args.poll_seconds<=0:raise ValueError('Positive poll interval required')
    while True:
        result=run_due(store,lambda config:execute_job(store,config))
        if args.once:return result
        time.sleep(min(args.poll_seconds,60))


def cmd_analysis(args):
    from kis_hl.analysis_store import run_analysis
    return run_analysis(DataStore(args.db),json.loads(Path(args.spec).read_text()),as_of_ms=args.as_of_ms)
