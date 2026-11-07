"""Persistent opt-in experiments, immutable evidence and bounded engine budgets."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing,ExitStack
from datetime import datetime,timezone
import hashlib
import json
import math
import random
import shutil
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4
import chess
import chess.engine
import chess.pgn
from . import ranking
from .content import board_after,SCHOLAR,MATE_TWO

def now():return datetime.now(timezone.utc).isoformat()

def source_identity():
    root=Path(__file__).resolve().parents[3]
    identity=root/'build-info.json'
    if identity.is_file():return json.loads(identity.read_text(encoding='utf-8-sig'))
    git=shutil.which('git')
    if git:
        result=subprocess.run([git,'rev-parse','HEAD'],cwd=root,capture_output=True,text=True,timeout=5)
        if result.returncode==0:
            dirty=subprocess.run([git,'status','--porcelain'],cwd=root,capture_output=True,text=True,timeout=5)
            return {'commit':result.stdout.strip(),'dirty':bool(dirty.stdout.strip())}
    return {'commit':'UNCOMMITTED','dirty':True}

def checked_board(fen):
    try:board=chess.Board(fen)
    except (ValueError,TypeError):raise ValueError('INVALID_FEN') from None
    if not board.is_valid():raise ValueError('INVALID_CHESS_POSITION')
    return board

def score_json(score,turn):
    white=score.white();reported=score.pov(turn)
    return {'type':'mate' if white.is_mate() else 'cp','value':white.mate() if white.is_mate() else white.score(),
            'perspective':'white','reported_perspective':'side_to_move',
            'reported_value':reported.mate() if reported.is_mate() else reported.score()}

def score_order(score,turn):
    sign=1 if turn else -1
    value=score['value']*sign
    if score['type']=='mate':return (2,-value) if value>0 else (0,-value)
    return (1,value)

class Cancelled(Exception):pass

class EngineSession:
    def __init__(self,path,settings=None):self.path=str(path);self.engine=None;self.settings=settings or {}
    def __enter__(self):
        self.engine=chess.engine.SimpleEngine.popen_uci(self.path,timeout=5.)
        options={k:v for k,v in {'Threads':self.settings.get('threads',1),'Hash':self.settings.get('hash_mb',32),'Skill Level':20,'UCI_LimitStrength':False}.items() if k in self.engine.options}
        self.engine.configure(options)
        self.identity={'name':self.engine.id.get('name'),'author':self.engine.id.get('author'),'path':self.path,
                       'sha256':hashlib.sha256(Path(self.path).read_bytes()).hexdigest(),'configuration':options}
        return self
    def __exit__(self,*args):
        if self.engine:
            try:self.engine.quit()
            except Exception:self.engine.close()
    def analyze(self,board,nodes,multipv=1,root_moves=None):
        if 'Clear Hash' in self.engine.options:self.engine.configure({'Clear Hash':None})
        started=time.perf_counter()
        result=self.engine.analyse(board,chess.engine.Limit(nodes=nodes,time=2.),multipv=multipv,root_moves=root_moves)
        lines=[]
        for item in result:
            b=board.copy();ucis=[];sans=[]
            for move in item.get('pv',[]):
                if move not in b.legal_moves:raise ValueError('INVALID_ENGINE_PRINCIPAL_VARIATION')
                sans.append(b.san(move));ucis.append(move.uci());b.push(move)
            if not ucis or 'score' not in item:continue
            lines.append(dict(score=score_json(item['score'],board.turn),pv=ucis,san=sans,
                depth=item.get('depth'),nodes=item.get('nodes',0),nps=item.get('nps'),time=item.get('time')))
        if not lines:raise ValueError('ENGINE_RETURNED_NO_LEGAL_LINE')
        return {'lines':lines,'nodes':max(line['nodes'] for line in lines),
                'elapsed_seconds':time.perf_counter()-started,'requested_nodes':nodes}

def dataset(seed):
    families=[
      ('open-game',['e4 e5 Nf3 Nc6','e4 e5 Nf3 Nc6 Bb5 a6']),
      ('sicilian',['e4 c5 Nf3 d6','e4 c5 Nf3 d6 d4 cxd4']),
      ('french',['e4 e6 d4 d5','e4 e6 d4 d5 Nc3 Nf6']),
      ('queens-gambit',['d4 d5 c4 e6','d4 d5 c4 e6 Nc3 Nf6']),
      ('caro-kann',['e4 c6 d4 d5','e4 c6 d4 d5 Nc3 dxe4']),
      ('english',['c4 e5 Nc3 Nf6','c4 e5 Nc3 Nf6 g3 d5']),
      ('reti',['Nf3 d5 g3 c5','Nf3 d5 g3 c5 Bg2 Nc6']),
      ('composed-tactics',[SCHOLAR,MATE_TWO])]
    random.Random(seed).shuffle(families)
    rows=[];seen={}
    for index,(family,positions) in enumerate(families):
        split='TRAIN' if index<3 else 'VALIDATION' if index<5 else 'HELD_OUT'
        for text in positions:
            b=checked_board(text) if '/' in text else board_after(text)
            key=min(ranking.position_id(b),ranking.position_id(b.mirror()))
            if key in seen:
                if seen[key]!=split:raise ValueError('TRANSPOSITION_SPLIT_LEAKAGE')
                continue
            seen[key]=split
            rows.append(dict(fen=b.fen(),position_id=ranking.position_id(b),group=family,split=split))
    return rows

class Laboratory:
    def __init__(self,runtime_dir,engine_path):
        self.root=Path(runtime_dir);self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'research.sqlite3';self.engine_path=Path(engine_path) if engine_path else None
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='chess-lab')
        self.stop=threading.Event();self.guard=threading.Lock();self.deadlines={}
        with closing(self.connect()) as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS research_schema(version INTEGER PRIMARY KEY);
              INSERT OR IGNORE INTO research_schema VALUES(1);
              CREATE TABLE IF NOT EXISTS research_jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,
                payload TEXT NOT NULL,status TEXT NOT NULL,cancel INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL,
                updated TEXT NOT NULL,result TEXT,error TEXT,parent_id TEXT);
              CREATE TABLE IF NOT EXISTS research_evidence(id TEXT PRIMARY KEY,job_id TEXT,kind TEXT NOT NULL,
                created TEXT NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL);
              CREATE TRIGGER IF NOT EXISTS immutable_research_update BEFORE UPDATE ON research_evidence BEGIN SELECT RAISE(ABORT,'immutable research evidence'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_research_delete BEFORE DELETE ON research_evidence BEGIN SELECT RAISE(ABORT,'immutable research evidence'); END;
              CREATE TABLE IF NOT EXISTS content_revisions(seq INTEGER PRIMARY KEY AUTOINCREMENT,collection TEXT NOT NULL,
                id TEXT NOT NULL,owner TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL);
              CREATE TRIGGER IF NOT EXISTS immutable_content_update BEFORE UPDATE ON content_revisions BEGIN SELECT RAISE(ABORT,'immutable content revision'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_content_delete BEFORE DELETE ON content_revisions BEGIN SELECT RAISE(ABORT,'immutable content revision'); END;
              CREATE TABLE IF NOT EXISTS learning_events(id TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,
                item_id TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL);
              CREATE TRIGGER IF NOT EXISTS immutable_learning_update BEFORE UPDATE ON learning_events BEGIN SELECT RAISE(ABORT,'immutable learning event'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_learning_delete BEFORE DELETE ON learning_events BEGIN SELECT RAISE(ABORT,'immutable learning event'); END;
            ''')
            db.execute("UPDATE research_jobs SET status='INTERRUPTED',error='Restart interrupted pending work; explicit resume creates a new attempt.',updated=? WHERE status IN ('RUNNING','QUEUED')",(now(),))
            db.commit()
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA foreign_keys=ON')
        return db
    def journal(self,job_id,kind,payload):
        text=ranking.canonical(payload)
        with closing(self.connect()) as db:
            db.execute('INSERT INTO research_evidence VALUES(?,?,?,?,?,?)',(uuid4().hex,job_id,kind,now(),text,hashlib.sha256(text.encode()).hexdigest()));db.commit()
    def content(self,collection,defaults):
        merged={r['id']:dict(r) for r in defaults}
        with closing(self.connect()) as db:
            for row in db.execute('SELECT payload FROM content_revisions WHERE collection=? ORDER BY seq',(collection,)):
                item=json.loads(row['payload']);merged[item['id']]=item
        return list(merged.values())
    def revise(self,collection,owner,item):
        if collection not in ('lessons','puzzles','studies','settings'):raise ValueError('UNKNOWN_CONTENT_COLLECTION')
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not 1<=len(item['id'])<=100:raise ValueError('CONTENT_ID_REQUIRED')
        text=ranking.canonical(item)
        if len(text)>50000:raise ValueError('CONTENT_TOO_LARGE')
        if collection!='settings':
            if not item.get('title'):raise ValueError('TITLE_REQUIRED')
            board=checked_board(item.get('fen',chess.STARTING_FEN))
            for uci in item.get('solution',item.get('moves',[])):
                move=chess.Move.from_uci(uci)
                if move not in board.legal_moves:raise ValueError('INVALID_CONTENT_SOLUTION')
                board.push(move)
            if collection=='puzzles':
                item=dict(item,test='line',solutions=[item['solution'][0]] if item.get('solution') else [],unique_under_objective=False,
                          verification='LEGAL_LINE_ONLY_NOT_ENGINE_TACTICAL_PROOF',source='Owner-authored content')
                if not item['solutions']:raise ValueError('PUZZLE_SOLUTION_REQUIRED')
                text=ranking.canonical(item)
        with closing(self.connect()) as db:
            cursor=db.execute('INSERT INTO content_revisions(collection,id,owner,payload,created) VALUES(?,?,?,?,?)',(collection,item['id'],owner,text,now()));db.commit()
        return {'item':item,'revision':cursor.lastrowid,'status':'IMPLEMENTED'}
    def event(self,owner,kind,item,payload):
        with closing(self.connect()) as db:
            db.execute('INSERT INTO learning_events VALUES(?,?,?,?,?,?)',(uuid4().hex,owner,kind,item,ranking.canonical(payload),now()));db.commit()
    def progress(self,owner):
        with closing(self.connect()) as db:rows=[dict(r) for r in db.execute('SELECT * FROM learning_events WHERE owner=? ORDER BY created',(owner,))]
        lessons={r['item_id'] for r in rows if r['kind']=='lesson_complete'}
        attempts=[r for r in rows if r['kind']=='puzzle_attempt']
        solved={r['item_id'] for r in attempts if json.loads(r['payload']).get('correct')}
        failed=[r['item_id'] for r in attempts if not json.loads(r['payload']).get('correct')]
        recommendation='Retry '+failed[-1] if failed else 'Practice a beginner checkmate puzzle.'
        return dict(lessons_completed=len(lessons),lesson_ids=sorted(lessons),puzzles_attempted=len(attempts),puzzles_solved=len(solved),
                    solved_puzzle_ids=sorted(solved),study_sessions=len(rows),puzzle_success_rate=len([r for r in attempts if json.loads(r['payload']).get('correct')])/len(attempts) if attempts else None,
                    repeated_mistakes={key:failed.count(key) for key in set(failed)},recommendation=recommendation,
                    recommendation_evidence=[r['id'] for r in rows[-3:]],rating_status='NO_ELO_INFERENCE_FROM_LEARNING_PROGRESS')
    def jobs(self,owner,kind=None):
        with closing(self.connect()) as db:
            query='SELECT * FROM research_jobs WHERE owner=?';args=[owner]
            if kind:query+=' AND kind=?';args.append(kind)
            rows=db.execute(query+' ORDER BY created DESC LIMIT 100',args).fetchall()
        return [self.serialize(row) for row in rows]
    def settings(self):
        defaults={'id':'research-settings','default_nodes':20000,'max_nodes':200000,'max_tournament_plies':300,'threads':1,'hash_mb':32}
        return self.content('settings',[defaults])[-1]
    def serialize(self,row):
        result=dict(row);result['payload']=json.loads(result['payload']);result['result']=json.loads(result['result']) if result['result'] else None
        return result
    def get(self,job_id,owner):
        with closing(self.connect()) as db:row=db.execute('SELECT * FROM research_jobs WHERE id=? AND owner=?',(job_id,owner)).fetchone()
        if row is None:raise KeyError('JOB_NOT_FOUND')
        return self.serialize(row)
    def check(self,job_id):
        with closing(self.connect()) as db:row=db.execute('SELECT cancel FROM research_jobs WHERE id=?',(job_id,)).fetchone()
        if self.stop.is_set() or row is None or row['cancel']:raise Cancelled()
        if time.monotonic()>self.deadlines.get(job_id,float('inf')):raise TimeoutError('RESEARCH_JOB_WALL_DEADLINE_EXCEEDED')
    def submit(self,owner,kind,payload,parent_id=None):
        if kind not in ('experiment','tournament'):raise ValueError('UNKNOWN_RESEARCH_JOB')
        settings=self.settings()
        nodes=payload.get('nodes',settings['default_nodes'] if kind=='experiment' else 3000)
        if type(nodes) is not int or not 1000<=nodes<=settings['max_nodes']:raise ValueError('NODES_OUT_OF_RANGE')
        payload=dict(payload,nodes=nodes)
        if kind=='experiment':
            ref=payload.get('reference_nodes',nodes*2);seed=payload.get('seed',7331)
            if type(ref) is not int or not nodes<=ref<=500000 or type(seed) is not int or not 0<=seed<=2**31-1:raise ValueError('INVALID_EXPERIMENT_LIMITS')
            payload.update(reference_nodes=ref,seed=seed)
        else:
            cap=payload.get('max_plies',120)
            if type(cap) is not int or not 1<=cap<=settings['max_tournament_plies']:raise ValueError('INVALID_PLY_LIMIT')
            payload['max_plies']=cap
        if self.engine_path is None or not self.engine_path.is_file():raise ValueError('LOCAL_ENGINE_UNAVAILABLE')
        job=uuid4().hex
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            active=db.execute("SELECT count(*) FROM research_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]
            if active>=2:raise ValueError('RESEARCH_QUEUE_FULL')
            db.execute('INSERT INTO research_jobs(id,owner,kind,payload,status,created,updated,parent_id) VALUES(?,?,?,?,?,?,?,?)',(job,owner,kind,ranking.canonical(payload),'QUEUED',now(),now(),parent_id));db.commit()
        self.pool.submit(self.run,job,owner,kind,payload)
        return self.get(job,owner)
    def cancel(self,job,owner):
        self.get(job,owner)
        with closing(self.connect()) as db:
            db.execute("UPDATE research_jobs SET cancel=1,updated=? WHERE id=? AND owner=? AND status IN ('QUEUED','RUNNING')",(now(),job,owner));db.commit()
        return self.get(job,owner)
    def run(self,job,owner,kind,payload):
        self.deadlines[job]=time.monotonic()+120
        try:
            self.check(job)
            with closing(self.connect()) as db:db.execute("UPDATE research_jobs SET status='RUNNING',updated=? WHERE id=?",(now(),job));db.commit()
            result=self.experiment(job,payload) if kind=='experiment' else self.tournament(job,payload)
            self.check(job);status='SUCCEEDED';error=None
            self.journal(job,'completed_'+kind,result)
        except Cancelled:result=None;status='CANCELLED';error='Owner cancellation or orderly shutdown.'
        except Exception as exc:result=None;status='FAILED';error=f'{type(exc).__name__}: {exc}'[:1000]
        with closing(self.connect()) as db:
            db.execute('UPDATE research_jobs SET status=?,result=?,error=?,updated=? WHERE id=?',(status,ranking.canonical(result) if result else None,error,now(),job));db.commit()
    def latest_model(self):
        with closing(self.connect()) as db:row=db.execute("SELECT payload FROM research_evidence WHERE kind='frozen_model' ORDER BY created DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None
    def experiment(self,job,payload):
        started=time.perf_counter();positions=dataset(payload['seed']);train=[];validation=[];references=[]
        self.journal(job,'experiment_plan',{'positions':positions,'limits':payload,'source':source_identity(),'created':now()})
        with EngineSession(self.engine_path,self.settings()) as engine:
            def reference(row):
                self.check(job);b=checked_board(row['fen']);features=ranking.rank(b)
                decision={'position':row,'created':now(),'features':features}
                self.journal(job,'pre_search_decision_features',decision)
                result=engine.analyze(b,payload['reference_nodes'],multipv=b.legal_moves.count())
                ordered=sorted(result['lines'],key=lambda line:score_order(line['score'],b.turn),reverse=True)
                ref={'position':row,'result':result,'bestmove':ordered[0]['pv'][0],'label_available_at':now()}
                references.append(ref)
                bymove={line['pv'][0]:i for i,line in enumerate(ordered)}
                rows=[dict(features=r['features'],label=1-bymove.get(r['uci'],len(ordered))/max(1,len(ordered)-1),
                           split=row['split'],group=row['group'],position_id=row['position_id'],uci=r['uci']) for r in features]
                return b,features,ref,rows
            for row in positions:
                if row['split']=='TRAIN':train.extend(reference(row)[3])
                elif row['split']=='VALIDATION':validation.append(reference(row))
            candidates=[ranking.fit(train,regularization=value) for value in (.1,1.,10.)]
            def agreement(model):
                return sum(ranking.rank(b,model)[0]['uci']==ref['bestmove'] for b,_,ref,_ in validation)
            model=max(candidates,key=lambda m:(agreement(m),-m['regularization']))
            # This receipt is committed before any held-out expensive analysis.
            self.journal(job,'frozen_model',model)
            freeze=now();comparisons=[]
            for row in positions:
                if row['split']!='HELD_OUT':continue
                b=checked_board(row['fen']);rows=ranking.rank(b,model)
                planned={policy:ranking.allocate(rows,payload['nodes'],policy) for policy in ('uniform','heuristic','learned')}
                self.journal(job,'held_out_pre_search_ranking',{'position':row,'model_id':model['model_id'],
                    'ranked_moves':rows,'allocations':planned,'created':now()})
                _,_,ref,_=reference(row)
                scores={line['pv'][0]:line['score'] for line in ref['result']['lines']}
                for policy in ('conventional','uniform','heuristic','learned'):
                    self.check(job);arm_start=time.perf_counter();alloc=None
                    if policy=='conventional':
                        run=engine.analyze(b,payload['nodes']);chosen=run['lines'][0]['pv'][0];actual=run['nodes'];candidate_results=[]
                    else:
                        alloc=planned[policy];candidate_results=[]
                        for uci,nodes in alloc.items():
                            self.check(job);run=engine.analyze(b,nodes,root_moves=[chess.Move.from_uci(uci)])
                            candidate_results.append({'uci':uci,**run})
                        actual=sum(r['nodes'] for r in candidate_results)
                        selected=max(candidate_results,key=lambda r:score_order(r['lines'][0]['score'],b.turn))
                        chosen=selected['uci']
                    score=scores.get(chosen);best=scores[ref['bestmove']]
                    regret=max(0,(best['value']-score['value'])*(1 if b.turn else -1)) if score and best['type']==score['type']=='cp' else None
                    comparisons.append({'position_id':row['position_id'],'group':row['group'],'fen':b.fen(),'policy':policy,
                        'chosen_move':chosen,'reference_move':ref['bestmove'],'agreement':chosen==ref['bestmove'],
                        'requested_nodes':payload['nodes'],'actual_nodes':actual,'node_overshoot':max(0,actual-payload['nodes']),
                        'allocation':alloc,'elapsed_seconds':time.perf_counter()-arm_start,'reference_score':best,
                        'chosen_reference_score':score,'cp_regret':regret,'mate_score_comparison':best['type']=='mate' or bool(score and score['type']=='mate'),
                        'candidate_results':candidate_results})
            summary={}
            for policy in ('conventional','uniform','heuristic','learned'):
                rows=[r for r in comparisons if r['policy']==policy];cp=[r['cp_regret'] for r in rows if r['cp_regret'] is not None]
                summary[policy]={'positions':len(rows),'agreement':sum(r['agreement'] for r in rows)/len(rows),
                    'mean_cp_regret':sum(cp)/len(cp) if cp else None,'cp_regret_positions':len(cp),
                    'nodes':sum(r['actual_nodes'] for r in rows),'seconds':sum(r['elapsed_seconds'] for r in rows)}
            return {'schema_version':'chesselo5000.relevance-experiment/1','source':source_identity(),'seed':payload['seed'],
                'engine':engine.identity,'positions':positions,'train_rows':train,'validation_groups':sorted({r[2]['position']['group'] for r in validation}),
                'model':model,'model_frozen_at':freeze,'references':references,'comparisons':comparisons,'summary':summary,
                'elapsed_seconds':time.perf_counter()-started,'validation_selection':'Maximum validation best-move agreement; fixed regularization candidates .1,1,10.',
                'split_policy':'Opening-family groups, exact/mirrored transposition deduplication; all related study prefixes remain together.',
                'budget_policy':'Equal requested node totals per arm, all legal candidates receive positive resources. Each search also has a 2-second wall cap, with an outer UCI deadline. Actual UCI node-limit overshoot and per-candidate overhead are reported. Overall jobs have a 120-second deadline.',
                'conclusion':'EXPERIMENTAL_SMALL_SAMPLE: measured comparisons only. Actual-node differences, finite reference search, and small held-out groups preclude a superiority or Elo claim.',
                'negative_results_preserved':True}
    def tournament(self,job,payload):
        started=time.perf_counter();games=[];configs=[{'id':'stockfish-hash32','skill':20,'hash_mb':32},{'id':'stockfish-hash16','skill':20,'hash_mb':16}]
        starts=[SCHOLAR,MATE_TWO]
        with ExitStack() as stack:
            engines={cfg['id']:stack.enter_context(EngineSession(self.engine_path,{**self.settings(),'threads':1,'hash_mb':cfg['hash_mb']})) for cfg in configs}
            for start_index,fen in enumerate(starts):
                for reverse in (False,True):
                    self.check(job);white=configs[int(reverse)];black=configs[1-int(reverse)];b=checked_board(fen);game=chess.pgn.Game();game.setup(b)
                    for participant in engines.values():
                        if 'Clear Hash' in participant.engine.options:participant.engine.configure({'Clear Hash':None})
                    game.headers.update(Event='CHESS ELO 5000 paired tactical mini-tournament',White=white['id'],Black=black['id'],Date=datetime.now().strftime('%Y.%m.%d'))
                    cursor=game;nodes=0;trace=[];failure=None;failure_kind=None
                    for ply in range(payload['max_plies']):
                        self.check(job)
                        if b.outcome(claim_draw=False):break
                        player=white if b.turn else black
                        engine=engines[player['id']]
                        if 'Skill Level' in engine.engine.options:engine.engine.configure({'Skill Level':player['skill']})
                        try:
                            reply=engine.engine.play(b,chess.engine.Limit(nodes=payload['nodes'],time=2.),game=game,info=chess.engine.INFO_ALL)
                            if reply.move not in b.legal_moves:raise ValueError('ILLEGAL_ENGINE_MOVE')
                            trace.append({'ply':ply+1,'uci':reply.move.uci(),'nodes':reply.info.get('nodes',0),'depth':reply.info.get('depth'),'player':player['id']})
                            nodes+=reply.info.get('nodes',0);b.push(reply.move);cursor=cursor.add_variation(reply.move)
                        except Exception as exc:
                            failure=f'{type(exc).__name__}: {exc}'
                            failure_kind='ENGINE_CRASH' if isinstance(exc,chess.engine.EngineTerminatedError) else 'ENGINE_TIMEOUT' if isinstance(exc,TimeoutError) else 'ILLEGAL_MOVE' if 'ILLEGAL_ENGINE_MOVE' in str(exc) else 'ENGINE_PROTOCOL_FAILURE'
                            break
                    outcome=b.outcome(claim_draw=False);result=outcome.result() if outcome else '*';game.headers['Result']=result
                    games.append({'id':uuid4().hex,'starting_position':start_index,'color_reversed':reverse,'starting_fen':fen,'final_fen':b.fen(),
                        'white':white['id'],'black':black['id'],'result':result,'completed':bool(outcome),
                        'termination':outcome.termination.name if outcome else 'ENGINE_FAILURE' if failure else 'PLY_LIMIT',
                        'error':failure,'failure_kind':failure_kind,'nodes':nodes,'moves':trace,'pgn':str(game)})
                    self.journal(job,'tournament_game',games[-1])
            completed=[g for g in games if g['completed']];wins=draws=losses=0
            for g in completed:
                if g['result']=='1/2-1/2':draws+=1
                elif (g['result']=='1-0')==(g['white']==configs[0]['id']):wins+=1
                else:losses+=1
            count=len(completed);score=(wins+.5*draws)/count if count else None
            elo=None;interval=None
            if count:
                smoothed=(wins+.5*draws+.5)/(count+1);elo=400*math.log10(smoothed/(1-smoothed))
                z=1.96;center=(score+z*z/(2*count))/(1+z*z/count);radius=z*math.sqrt(score*(1-score)/count+z*z/(4*count*count))/(1+z*z/count)
                interval={'score_lower':max(0,center-radius),'score_upper':min(1,center+radius),'method':'Wilson score interval; draws treated as fractional scores (exploratory)'}
            return {'schema_version':'chesselo5000.tournament/1','source':source_identity(),'engine':engines[configs[0]['id']].identity,
                'participants':{key:value.identity for key,value in engines.items()},'configurations':configs,
                'budget':payload,'games':games,'games_completed':count,'wins':wins,'draws':draws,'losses':losses,
                'engine_crashes':sum(g['failure_kind']=='ENGINE_CRASH' for g in games),
                'engine_timeouts':sum(g['failure_kind']=='ENGINE_TIMEOUT' for g in games),
                'illegal_move_failures':sum(g['failure_kind']=='ILLEGAL_MOVE' for g in games),
                'protocol_failures':sum(g['failure_kind']=='ENGINE_PROTOCOL_FAILURE' for g in games),
                'unfinished':len(games)-count,'rating_estimate':elo,'uncertainty':interval,'rating_reference':'Hash32 relative to Hash16 = 0, both Skill20, this paired tactical sample only; half-point smoothing.',
                'rating_status':'EXPERIMENTAL_NOT_FIDE_OR_UNIVERSAL_ELO','elapsed_seconds':time.perf_counter()-started,
                'limitation':'Four paired composed tactical games, independent engine processes and cleared per-game hash tables. Deterministic full-skill configurations avoid unseedable reduced-skill randomness. Exact PGN replay is verified; no general engine-strength evidence.'}
    def shutdown(self):
        self.stop.set();self.pool.shutdown(wait=False,cancel_futures=True)
