"""Authenticated chess learning, deterministic coaching and research endpoints."""
from __future__ import annotations
from functools import wraps
import importlib.metadata
import json
from pathlib import Path
import shutil
from flask import Blueprint,g,jsonify,request
import chess
from . import content,ranking
from .laboratory import Laboratory,checked_board
from .search import search

def register_research(app,service):
    lab=Laboratory(service.runtime_dir,service.engine.path)
    app.extensions['research_lab']=lab
    bp=Blueprint('chess_research',__name__,url_prefix='/api/v1')
    def safe(function):
        @wraps(function)
        def call(*args,**kwargs):
            try:return function(*args,**kwargs)
            except KeyError as exc:return jsonify(error='not_found',message=str(exc)),404
            except (ValueError,TypeError) as exc:return jsonify(error='invalid_input',message=str(exc)),400
        return call
    def body():
        value=request.get_json()
        if not isinstance(value,dict):raise ValueError('JSON_OBJECT_REQUIRED')
        return value
    def collection(name):
        defaults={'lessons':content.lessons,'puzzles':content.puzzles,'studies':content.studies}
        return lab.content(name,defaults[name]())
    def item(name,key):
        result=next((r for r in collection(name) if r['id']==key),None)
        if result is None:raise KeyError('CONTENT_NOT_FOUND')
        return result
    @bp.get('/lessons')
    @safe
    def lessons():return jsonify(lessons=collection('lessons'))
    @bp.get('/lessons/<key>')
    @safe
    def lesson(key):return jsonify(item('lessons',key))
    @bp.post('/lessons/<key>/complete')
    @safe
    def complete(key):
        lesson=item('lessons',key);moves=body().get('moves',[])
        board=checked_board(lesson['fen'])
        for uci in moves:board.push_uci(uci)
        if moves!=lesson['solution']:raise ValueError('PLAY_THE_DEMONSTRATED_EXERCISE_BEFORE_COMPLETING')
        lab.event(g.owner,'lesson_complete',key,{'moves':moves,'final_fen':board.fen()})
        return jsonify(status='completed',progress=lab.progress(g.owner))
    @bp.get('/puzzles')
    @safe
    def puzzles():return jsonify(puzzles=[{k:v for k,v in p.items() if k not in ('solutions','solution','test')} for p in collection('puzzles')])
    @bp.get('/puzzles/<key>')
    @safe
    def puzzle(key):return jsonify({k:v for k,v in item('puzzles',key).items() if k not in ('solutions','solution','test')})
    @bp.post('/puzzles/<key>/attempts')
    @safe
    def attempt(key):
        puzzle=item('puzzles',key);payload=body();moves=payload.get('moves',[])
        if payload.get('hint'):
            lab.event(g.owner,'puzzle_hint',key,{'shown':True})
            return jsonify(correct=False,legal=True,hint=puzzle.get('hint','Examine checks and forcing moves.'),message='Hint shown; no success recorded.')
        if not isinstance(moves,list) or not 1<=len(moves)<=30:raise ValueError('BOUNDED_MOVE_LIST_REQUIRED')
        b=checked_board(puzzle['fen']);first=chess.Move.from_uci(moves[0]);legal=True
        correct=content.puzzle_objective(b,first,puzzle)
        try:
            for uci in moves:b.push_uci(uci)
        except ValueError:legal=False;correct=False
        result={'correct':correct,'legal':legal,'message':'Verified objective achieved by the first move.' if correct else 'The submitted line does not meet the verified objective.',
                'verification':puzzle['verification'],'unique_under_objective':puzzle.get('unique_under_objective',False)}
        if correct:result['solution']=puzzle['solutions']
        lab.event(g.owner,'puzzle_attempt',key,{**result,'moves':moves})
        return jsonify(result)
    @bp.get('/learning/studies')
    @safe
    def studies():return jsonify(studies=collection('studies'))
    @bp.get('/openings')
    @safe
    def openings():
        rows=[r for r in collection('studies') if r.get('kind')=='opening'];fen=request.args.get('fen')
        if fen:
            position=ranking.position_id(checked_board(fen))
            rows=[r for r in rows if ranking.position_id(checked_board(r.get('final_fen',r['fen'])))==position]
        return jsonify(openings=rows,frequency_statistics='UNAVAILABLE')
    @bp.get('/progress')
    @safe
    def progress():return jsonify(lab.progress(g.owner))
    @bp.post('/coach')
    @safe
    def coach():
        payload=body();b=checked_board(payload.get('fen',chess.STARTING_FEN));original=b.copy()
        line=payload.get('moves',[])
        if not isinstance(line,list) or len(line)>60:raise ValueError('BOUNDED_LINE_REQUIRED')
        sans=[]
        for uci in line:
            m=chess.Move.from_uci(uci)
            if m not in b.legal_moves:raise ValueError('COACH_REFUSED_ILLEGAL_VARIATION')
            sans.append(b.san(m));b.push(m)
        rows=ranking.rank(original);material=sum(ranking.VALUES[p.piece_type]*(1 if p.color else -1) for p in original.piece_map().values())
        facts=[{'kind':'RULES_VERIFIED_FACT','text':f'{"White" if original.turn else "Black"} to move; {original.legal_moves.count()} legal moves; check={original.is_check()}.'},
               {'kind':'HEURISTIC_INTERPRETATION','text':f'Material balance is {material:+d} pawn units from White’s perspective using 1/3/3/5/9 weights. This omits positional compensation.'}]
        if original.outcome():facts.append({'kind':'RULES_VERIFIED_FACT','text':f'Terminal position: {original.outcome().termination.name}.'})
        if rows:facts.append({'kind':'HEURISTIC_INTERPRETATION','text':f'Investigate {rows[0]["san"]}: check/capture/promotion/activity features give it high computational priority. This is not a best-move proof.'})
        if line:facts.append({'kind':'RULES_VERIFIED_FACT','text':'The proposed line is legal: '+' '.join(sans)})
        analysis=None
        if payload.get('analysis_id'):
            analysis=service.get_analysis(g.owner,payload['analysis_id'])
            if analysis.get('fen')!=original.fen() or analysis.get('status')!='completed':raise ValueError('COACH_ANALYSIS_POSITION_OR_STATUS_MISMATCH')
        else:
            analysis=next((r for r in service.list_analysis(g.owner) if r.get('status')=='completed' and r.get('fen')==original.fen()),None)
        if analysis and analysis.get('result',{}).get('lines'):
            engine_line=analysis['result']['lines'][0];verify=original.copy();legal_sans=[]
            for uci in engine_line['pv']:
                move=chess.Move.from_uci(uci)
                if move not in verify.legal_moves:raise ValueError('COACH_REFUSED_INVALID_ENGINE_LINE')
                legal_sans.append(verify.san(move));verify.push(move)
            score=engine_line['score']
            facts.append({'kind':'ENGINE_EVALUATION','text':f'Completed local analysis reports {score["type"]} {score["value"]} from {score["perspective"]} perspective. Legal continuation: {" ".join(legal_sans[:8])}. This is bounded engine evidence, not a game-theoretic proof.'})
        packet={'schema_version':'chesselo5000.neural-packet/1','position_id':ranking.position_id(original),'fen':original.fen(),
                'side_to_move':'WHITE' if original.turn else 'BLACK','analysis_target':'EXPLAIN_CANDIDATE_MOVES','source_mode':'LOCAL_RESEARCH',
                'available_tools':['get_legal_moves','analyze_position','compare_candidate_moves'],'provider':'deterministic'}
        return jsonify(provider='deterministic',facts=facts,legal_moves=[m.uci() for m in original.legal_moves],validated_line=line,
                       recommendation=lab.progress(g.owner)['recommendation'],packet=packet,optional_llm='UNCONFIGURED',
                       analysis_id=analysis['id'] if analysis else None,engine_evidence=analysis.get('result') if analysis else None)
    @bp.get('/research/relevance')
    @safe
    def relevance():
        b=checked_board(request.args.get('fen',chess.STARTING_FEN));model=lab.latest_model()
        return jsonify(fen=b.fen(),rows=ranking.rank(b,model),policy_status='FROZEN_EXPERIMENTAL' if model else 'UNTRAINED_HEURISTIC_FALLBACK',
                       model_id=model['model_id'] if model else None,disclaimer='Experimental attention score; neither a probability nor a chess-strength rating.')
    @bp.post('/research/search')
    @safe
    def transparent_search():
        payload=body();b=checked_board(payload.get('fen',chess.STARTING_FEN));model=lab.latest_model() if payload.get('policy')=='learned' else None
        result=search(b,payload.get('nodes',10000),model)
        lab.journal(None,'transparent_search',{'fen':b.fen(),'result':result})
        return jsonify(result)
    @bp.route('/research/experiments',methods=['GET','POST'])
    @safe
    def experiments():
        return jsonify(experiments=lab.jobs(g.owner,'experiment')) if request.method=='GET' else (jsonify(lab.submit(g.owner,'experiment',body())),202)
    @bp.get('/research/experiments/<key>')
    @safe
    def experiment(key):return jsonify(lab.get(key,g.owner))
    @bp.post('/research/experiments/<key>/cancel')
    @safe
    def cancel_experiment(key):return jsonify(lab.cancel(key,g.owner))
    @bp.post('/research/experiments/<key>/resume')
    @safe
    def resume_experiment(key):
        previous=lab.get(key,g.owner)
        if previous['status'] not in ('CANCELLED','INTERRUPTED','FAILED','SUCCEEDED'):raise ValueError('JOB_STILL_ACTIVE')
        return jsonify(lab.submit(g.owner,previous['kind'],previous['payload'],parent_id=key)),202
    @bp.route('/tournaments',methods=['GET','POST'])
    @safe
    def tournaments():return jsonify(tournaments=lab.jobs(g.owner,'tournament')) if request.method=='GET' else (jsonify(lab.submit(g.owner,'tournament',body())),202)
    @bp.get('/tournaments/<key>')
    @safe
    def tournament(key):return jsonify(lab.get(key,g.owner))
    @bp.post('/tournaments/<key>/cancel')
    @safe
    def cancel_tournament(key):return jsonify(lab.cancel(key,g.owner))
    @bp.route('/admin/content/<name>',methods=['GET','POST'])
    @safe
    def admin_content(name):
        if name not in ('lessons','puzzles','studies'):raise ValueError('UNKNOWN_CONTENT_COLLECTION')
        return jsonify(items=collection(name)) if request.method=='GET' else (jsonify(lab.revise(name,g.owner,body())),201)
    @bp.route('/admin/settings',methods=['GET','POST'])
    @safe
    def admin_settings():
        defaults={'id':'research-settings','default_nodes':20000,'max_nodes':200000,'max_tournament_plies':300,'threads':1,'hash_mb':32}
        if request.method=='POST':
            payload=body();values={**defaults,**payload,'id':defaults['id']}
            ranges={'default_nodes':(1000,200000),'max_nodes':(1000,200000),'max_tournament_plies':(1,300),'threads':(1,6),'hash_mb':(16,512)}
            if set(payload)-set(defaults):raise ValueError('UNKNOWN_SETTING')
            for key,(low,high) in ranges.items():
                if type(values[key]) is not int or not low<=values[key]<=high:raise ValueError('INVALID_SETTING_'+key)
            if values['default_nodes']>values['max_nodes']:raise ValueError('DEFAULT_EXCEEDS_MAXIMUM')
            lab.revise('settings',g.owner,values)
        return jsonify(lab.content('settings',[defaults])[-1])
    @bp.get('/admin/jobs')
    @safe
    def admin_jobs():
        analysis=service.list_analysis(g.owner) if hasattr(service,'list_analysis') else []
        return jsonify(jobs=lab.jobs(g.owner),analysis=analysis)
    @bp.get('/system/tools')
    @safe
    def tools():
        root=Path(__file__).resolve().parents[3]
        paths=([Path(service.engine.path)] if service.engine.path else [])+[root/'engines'/'stockfish.exe']
        records=[];seen=set()
        for path in paths:
            if str(path).lower() in seen:continue
            seen.add(str(path).lower())
            records.append({'name':path.stem,'path':str(path),'availability':'DISCOVERED' if path.is_file() else 'UNCONFIGURED',
                'measured_functionality':'Consult actual engine-run receipts; discovery does not execute the engine.','supported_operations':['UCI'] if path.is_file() else []})
        records.extend({'name':name,'path':shutil.which(name),'availability':'DISCOVERED' if shutil.which(name) else 'UNCONFIGURED'} for name in ('stockfish','node','python'))
        return jsonify(tools=records,libraries={name:importlib.metadata.version(name) for name in ('chess','flask')},
                       opening_books={'paths':[str(p) for p in (root/'books').glob('*.bin')],'status':'DISCOVERED_ONLY'},
                       tablebases={'status':'UNCONFIGURED'},optional_ai={'status':'UNCONFIGURED'},gpu={'status':'NOT_REQUIRED_CPU_DEFAULT'})
    @bp.post('/dispatch')
    @safe
    def dispatch():
        payload=body();task=payload.get('task');b=checked_board(payload.get('fen',chess.STARTING_FEN))
        if task=='validate_move':
            move=chess.Move.from_uci(payload.get('uci',''))
            result={'legal':move in b.legal_moves,'fen':b.fen(),'uci':move.uci()};tool='python-chess/rules'
        elif task in ('analyze','exact_endgame'):
            result=service.request_analysis(g.owner,{'fen':b.fen(),'nodes':payload.get('nodes',20000),'movetime_ms':1000,'multipv':3});tool='local-UCI-engine'
            if task=='exact_endgame':result={**result,'tablebase':'UNCONFIGURED','fallback':'Bounded engine estimate; no exact tablebase claim.'}
        elif task=='explain':return coach()
        else:raise ValueError('UNSUPPORTED_DISPATCH_OBJECTIVE')
        receipt={'objective':task,'tool_identity':tool,'result':result,'status':'EXECUTED','position_id':ranking.position_id(b)}
        lab.journal(None,'tool_dispatch',receipt)
        return jsonify(receipt)
    app.register_blueprint(bp)
