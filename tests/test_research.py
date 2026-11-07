import json
import sqlite3
from contextlib import closing
import pytest
import chess
from chess_elo_5000 import create_app
from chess_elo_5000.research import content,ranking
from chess_elo_5000.research.search import search
from chess_elo_5000.research.laboratory import Laboratory,dataset

@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path,testing=True)
    c=app.test_client();r=c.post('/api/v1/session',json={'password':'test-owner'})
    c.environ_base['HTTP_X_CSRF_TOKEN']=r.json['csrf_token']
    yield c,app
    app.extensions['research_lab'].shutdown();app.extensions['chess_service'].close()

def test_every_authored_exercise_is_legal():
    assert len(content.lessons())>=23
    for item in content.lessons()+content.studies():
        board=chess.Board(item['fen']);assert board.is_valid()
        for uci in item['solution']:board.push_uci(uci)

def test_puzzles_objective_and_alternatives_exhaustively_verified():
    for puzzle in content.puzzles():
        b=chess.Board(puzzle['fen'])
        answers=[m.uci() for m in b.legal_moves if content.puzzle_objective(b,m,puzzle)]
        assert answers==puzzle['solutions']
        assert puzzle['unique_under_objective']==(len(answers)==1)
    mate=next(p for p in content.puzzles() if p['id']=='quiet-mate-two')
    assert mate['solutions']==['h4g3']
    assert not content.forced_mate(chess.Board(mate['fen']),1,chess.WHITE)

def test_frozen_ridge_model_rejects_tampering_and_leakage():
    b=chess.Board();rows=[dict(features=r['features'],label=i/19,split='TRAIN',group='a') for i,r in enumerate(ranking.rank(b))]
    model=ranking.fit(rows);assert len(ranking.rank(b,model))==20
    model['coefficients'][0]+=1
    with pytest.raises(ValueError,match='IDENTITY'):ranking.rank(b,model)
    rows[0]['split']='HELD_OUT'
    with pytest.raises(ValueError,match='TRAIN_ONLY'):ranking.fit(rows)

def test_nonfinite_learning_refused():
    row=dict(features=ranking.features(chess.Board(),chess.Move.from_uci('e2e4')),label=.5,split='TRAIN',group='x')
    row['features']['check']=float('nan')
    with pytest.raises(ValueError,match='NONFINITE'):ranking.fit([row])

def test_allocation_preserves_every_legal_defense_and_total():
    rows=ranking.rank(chess.Board())
    for policy in ('uniform','heuristic'):
        allocation=ranking.allocate(rows,20000,policy)
        assert len(allocation)==20 and min(allocation.values())>0 and sum(allocation.values())==20000
    with pytest.raises(ValueError):ranking.allocate(rows,10,'uniform')

def test_position_identity_ignores_clocks_retains_castling():
    b=chess.Board();changed=chess.Board(b.fen().replace('0 1','40 50'))
    assert ranking.position_id(b)==ranking.position_id(changed)
    changed.castling_rights=0
    assert ranking.position_id(b)!=ranking.position_id(changed)

def test_family_split_and_transpositions_do_not_cross():
    rows=dataset(7331);groups={};positions={}
    for row in rows:
        assert groups.setdefault(row['group'],row['split'])==row['split']
        b=chess.Board(row['fen']);key=min(ranking.position_id(b),ranking.position_id(b.mirror()))
        assert positions.setdefault(key,row['split'])==row['split']
    assert {r['split'] for r in rows}=={'TRAIN','VALIDATION','HELD_OUT'}

def test_strict_custom_search_budget_and_legal_pv():
    b=chess.Board()
    result=search(b,101)
    assert result['nodes']<=101 and result['move'] in [m.uci() for m in b.legal_moves]
    for uci in result['pv']:b.push_uci(uci)
    assert b.is_valid()

def test_exercise_completion_not_merely_a_click(client):
    c,_=client
    assert c.post('/api/v1/lessons/lesson-1/complete',json={'moves':[]}).status_code==400
    assert c.post('/api/v1/lessons/lesson-1/complete',json={'moves':['e2e4']}).status_code==200
    assert c.get('/api/v1/progress').json['lessons_completed']==1

def test_puzzle_wrong_illegal_correct_and_hint(client):
    c,_=client
    wrong=c.post('/api/v1/puzzles/scholar-mate/attempts',json={'moves':['h5h4']}).json
    assert wrong['correct'] is False
    illegal=c.post('/api/v1/puzzles/scholar-mate/attempts',json={'moves':['h5a1']}).json
    assert illegal['legal'] is False
    correct=c.post('/api/v1/puzzles/scholar-mate/attempts',json={'moves':['h5f7']}).json
    assert correct['correct'] is True
    c.post('/api/v1/puzzles/scholar-mate/attempts',json={'hint':True})
    progress=c.get('/api/v1/progress').json
    assert progress['puzzles_attempted']==3 and progress['puzzles_solved']==1

def test_coach_validates_every_move_and_labels_interpretation(client):
    c,_=client
    assert c.post('/api/v1/coach',json={'fen':chess.STARTING_FEN,'moves':['e2e5']}).status_code==400
    result=c.post('/api/v1/coach',json={'fen':chess.STARTING_FEN,'moves':['e2e4','e7e5']})
    assert result.status_code==200 and result.json['validated_line']==['e2e4','e7e5']
    assert {r['kind'] for r in result.json['facts']}=={'RULES_VERIFIED_FACT','HEURISTIC_INTERPRETATION'}
    assert result.json['provider']=='deterministic'

def test_content_versions_validate_and_preserve_history(client):
    c,app=client
    item={'id':'owner-exercise','title':'King study','fen':content.PROMOTION,'solution':['a7a8q']}
    assert c.post('/api/v1/admin/content/lessons',json=item).status_code==201
    item['title']='Revised king study'
    assert c.post('/api/v1/admin/content/lessons',json=item).status_code==201
    item['solution']=['a7a9q']
    assert c.post('/api/v1/admin/content/lessons',json=item).status_code==400
    lab=app.extensions['research_lab']
    with closing(lab.connect()) as db:
        assert db.execute('SELECT count(*) FROM content_revisions').fetchone()[0]==2
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE content_revisions SET owner='other'")

def test_immutable_research_evidence(client):
    _,app=client;lab=app.extensions['research_lab'];lab.journal(None,'test',{'observed':1})
    with closing(lab.connect()) as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM research_evidence')

def test_research_recovery_marks_interrupted_not_auto_restart(tmp_path):
    lab=Laboratory(tmp_path,tmp_path/'missing.exe')
    with closing(lab.connect()) as db:
        db.execute("INSERT INTO research_jobs(id,owner,kind,payload,status,created,updated) VALUES('old','owner','experiment','{}','RUNNING','a','a')");db.commit()
    lab.shutdown();restarted=Laboratory(tmp_path,tmp_path/'missing.exe')
    assert restarted.get('old','owner')['status']=='INTERRUPTED'
    with pytest.raises(KeyError):restarted.get('old','other')
    restarted.shutdown()

def test_read_only_status_and_missing_optional_tools(client):
    c,app=client;lab=app.extensions['research_lab']
    assert c.get('/api/v1/system/status').json['optional_ai']=='UNCONFIGURED'
    assert c.get('/api/v1/system/tools').json['tablebases']['status']=='UNCONFIGURED'
    c.get('/api/v1/research/relevance');c.get('/api/v1/research/experiments');c.get('/api/v1/tournaments')
    assert lab.jobs('local-owner')==[]

def test_research_budget_validation_before_execution(client):
    c,_=client
    assert c.post('/api/v1/research/experiments',json={'nodes':float('nan')}).status_code==400
    assert c.post('/api/v1/research/experiments',json={'nodes':99999999}).status_code==400
    assert c.post('/api/v1/tournaments',json={'max_plies':999999}).status_code==400

def test_missing_engine_does_not_prevent_chess_or_learning(tmp_path):
    lab=Laboratory(tmp_path,None)
    assert lab.progress('owner')['lessons_completed']==0
    with pytest.raises(ValueError,match='UNAVAILABLE'):lab.submit('owner','experiment',{'nodes':20000})
    lab.shutdown()
