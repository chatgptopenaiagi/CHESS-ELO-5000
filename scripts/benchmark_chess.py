"""Actual legal-generation, persistence and optional bounded Stockfish workloads."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import sys
import time
import tracemalloc
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import chess
from chess_elo_5000.engines import EngineAdapter
from chess_elo_5000.research import ranking
from chess_elo_5000.research.laboratory import source_identity

def main():
    p=argparse.ArgumentParser();p.add_argument('--engine-positions',type=int,default=100);p.add_argument('--output',type=Path,default=Path('evidence/performance.json'));a=p.parse_args()
    root=Path(__file__).resolve().parents[1];r=random.Random(1641);board=chess.Board();positions=[]
    for i in range(10000):
        if board.outcome(claim_draw=False) or board.fullmove_number>100:board=chess.Board()
        positions.append(board.fen());board.push(r.choice(list(board.legal_moves)))
    workloads=[];tracemalloc.start()
    for count in (100,1000,10000):
        start=time.perf_counter();legal=sum(chess.Board(fen).legal_moves.count() for fen in positions[:count]);elapsed=time.perf_counter()-start
        workloads.append({'positions':count,'unique_fens':len(set(positions[:count])),'legal_moves':legal,'elapsed_seconds':elapsed,'positions_per_second':count/elapsed})
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    start=time.perf_counter()
    for fen in positions[:100]:ranking.rank(chess.Board(fen))
    ranking_seconds=time.perf_counter()-start
    dbpath=root/'runtime'/'benchmark.sqlite3';dbpath.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(dbpath)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS benchmark_positions(id TEXT PRIMARY KEY,fen TEXT NOT NULL)')
        start=time.perf_counter();db.executemany('INSERT OR REPLACE INTO benchmark_positions VALUES(?,?)',[(hashlib.sha256(f.encode()).hexdigest(),f) for f in positions]);db.commit();persist=time.perf_counter()-start
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    engine=EngineAdapter(root/'stockfish'/'stockfish'/'stockfish-windows-x86-64-universal.exe')
    runs=[]
    for fen in positions[:max(0,min(a.engine_positions,100))]:
        run=engine.analyze(chess.Board(fen),nodes=3000,movetime_ms=100,multipv=1)
        runs.append({'fen':fen,'nodes':run['nodes'],'elapsed_seconds':run['elapsed_seconds'],'bestmove':run.get('bestmove'),'depth':run['lines'][0]['depth'] if run.get('lines') else None})
    result={'schema_version':'chesselo5000.performance/1','source':source_identity(),'seed':1641,'legal_generation':workloads,
        'python_traced_peak_bytes':peak,'memory_scope':'Python traced heap only; excludes engine native memory. Engine configured hash is reported separately.',
        'ranking_100_positions_seconds':ranking_seconds,'ranking_mean_seconds':ranking_seconds/100,
        'sqlite_10000_upserts_seconds':persist,'engine':engine.identity(),'engine_runs':runs,
        'engine_nodes':sum(r['nodes'] for r in runs),'engine_total_seconds':sum(r['elapsed_seconds'] for r in runs),
        'interpretation':'Actual host measurements, no hardware-independent performance or strength claim. Repeated initial positions remain included and unique count is explicit.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('engine_runs','engine')},indent=2))
if __name__=='__main__':main()
