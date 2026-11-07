"""Chess adaptation of GENESIS-6.1's whitelisted features and frozen ridge model.

The small pivoted solver is adapted from DRAGONHYDRA future_relevance/learning.py.
Sporting features, probability targets and mutable foreign runtimes are excluded.
Scores rank computational attention; they are neither probabilities nor ratings.
"""
from __future__ import annotations
import hashlib
import json
import math
import chess

FEATURES = ('intercept','check','capture','promotion','captured_value','mover_value',
            'center','development','attacked_destination','pawn_advance','king_ring',
            'legal_fraction','material_fraction','in_check')
VALUES = {chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9,chess.KING:0}

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)

def position_id(board):
    # Exact repetition position: legal EP/castling retained; clocks intentionally excluded.
    return hashlib.sha256(' '.join(board.fen(en_passant='legal').split()[:4]).encode()).hexdigest()

def features(board,move):
    if move not in board.legal_moves:
        raise ValueError('Feature extraction requires a legal move')
    piece=board.piece_at(move.from_square)
    victim=board.piece_at(move.to_square)
    captured=VALUES.get(victim.piece_type,0) if victim else int(board.is_en_passant(move))
    rank=chess.square_rank(move.to_square)
    forward=rank if board.turn else 7-rank
    king=board.king(not board.turn)
    result=dict(intercept=1.,check=float(board.gives_check(move)),capture=float(board.is_capture(move)),
        promotion=float(bool(move.promotion)),captured_value=captured/9,mover_value=VALUES[piece.piece_type]/9,
        center=(3.5-abs(chess.square_file(move.to_square)-3.5)+3.5-abs(rank-3.5))/7,
        development=float(piece.piece_type in (chess.KNIGHT,chess.BISHOP) and chess.square_rank(move.from_square)==(0 if board.turn else 7)),
        attacked_destination=float(board.is_attacked_by(not board.turn,move.to_square)),
        pawn_advance=forward/7 if piece.piece_type==chess.PAWN else 0.,
        king_ring=float(king is not None and chess.square_distance(move.to_square,king)<=2),
        legal_fraction=board.legal_moves.count()/100,
        material_fraction=sum(VALUES[p.piece_type]*(1 if p.color==board.turn else -1) for p in board.piece_map().values())/39,
        in_check=float(board.is_check()))
    return {key:float(result[key]) for key in FEATURES}

def heuristic(x):
    return 5*x['check']+4*x['promotion']+2*x['capture']+3*x['captured_value']+.4*x['center']+.6*x['development']-.5*x['attacked_destination']+.2*x['king_ring']

def solve(matrix,vector):
    size=len(vector)
    augmented=[list(row)+[value] for row,value in zip(matrix,vector)]
    for column in range(size):
        pivot=max(range(column,size),key=lambda row:abs(augmented[row][column]))
        if abs(augmented[pivot][column])<1e-12:
            raise ValueError('RIDGE_SINGULAR_SYSTEM')
        augmented[column],augmented[pivot]=augmented[pivot],augmented[column]
        divisor=augmented[column][column]
        augmented[column]=[value/divisor for value in augmented[column]]
        for row in range(size):
            if row!=column:
                multiplier=augmented[row][column]
                augmented[row]=[a-multiplier*b for a,b in zip(augmented[row],augmented[column])]
    result=[row[-1] for row in augmented]
    if not all(math.isfinite(v) for v in result):
        raise ValueError('NONFINITE_MODEL')
    return result

def fit(rows,regularization=1.):
    if not rows or not math.isfinite(regularization) or regularization<=0:
        raise ValueError('INVALID_TRAINING_DATA')
    for row in rows:
        if row['split']!='TRAIN' or set(row['features'])!=set(FEATURES):
            raise ValueError('TRAIN_ONLY_FEATURE_WHITELIST_REQUIRED')
        if not all(math.isfinite(v) and abs(v)<=100 for v in row['features'].values()) or not 0<=row['label']<=1:
            raise ValueError('NONFINITE_OR_OUT_OF_RANGE_TRAINING_ROW')
    size=len(FEATURES)
    gram=[[0.]*size for _ in range(size)]
    response=[0.]*size
    for row in rows:
        x=[row['features'][k] for k in FEATURES]
        for i in range(size):
            response[i]+=x[i]*row['label']
            for j in range(size):gram[i][j]+=x[i]*x[j]
    for i in range(size):gram[i][i]+=regularization
    model=dict(schema_version='chesselo5000.ridge/1',feature_names=list(FEATURES),coefficients=solve(gram,response),
               regularization=regularization,frozen=True,training_groups=sorted({r['group'] for r in rows}),
               training_rows_sha256=hashlib.sha256(canonical(rows).encode()).hexdigest(),target='reference_rank_percentile')
    model['model_id']=hashlib.sha256(canonical(model).encode()).hexdigest()
    return model

def predict(x,model):
    payload={k:v for k,v in model.items() if k!='model_id'}
    if model.get('frozen') is not True or model.get('model_id')!=hashlib.sha256(canonical(payload).encode()).hexdigest() or model.get('feature_names')!=list(FEATURES):
        raise ValueError('FROZEN_MODEL_IDENTITY_MISMATCH')
    value=math.fsum(a*x[k] for a,k in zip(model['coefficients'],FEATURES))
    if not math.isfinite(value):raise ValueError('NONFINITE_PREDICTION')
    return value

def rank(board,model=None):
    rows=[]
    for move in board.legal_moves:
        x=features(board,move)
        rows.append(dict(uci=move.uci(),san=board.san(move),features=x,heuristic_score=heuristic(x),
                         learned_score=predict(x,model) if model else None))
    return sorted(rows,key=lambda r:(-(r['learned_score'] if model else r['heuristic_score']),r['uci']))

def allocate(rows,budget,policy):
    if type(budget) is not int or budget<len(rows) or not rows:raise ValueError('BUDGET_TOO_SMALL')
    if policy=='uniform':weights=[1.]*len(rows)
    elif policy in ('heuristic','learned'):
        key='heuristic_score' if policy=='heuristic' else 'learned_score'
        if any(r[key] is None or not math.isfinite(r[key]) for r in rows):raise ValueError('MODEL_REQUIRED')
        order=sorted(range(len(rows)),key=lambda i:(-rows[i][key],rows[i]['uci']))
        weights=[0.]*len(rows)
        for place,i in enumerate(order):weights[i]=1.+len(rows)/(place+1)
    else:raise ValueError('UNKNOWN_ALLOCATION_POLICY')
    # Every legal root receives resources. No forced defense is silently discarded.
    floor=max(1,budget//(4*len(rows)))
    remaining=budget-floor*len(rows)
    raw=[remaining*w/sum(weights) for w in weights]
    amounts=[floor+int(v) for v in raw]
    for i in sorted(range(len(rows)),key=lambda i:raw[i]-int(raw[i]),reverse=True)[:budget-sum(amounts)]:amounts[i]+=1
    assert sum(amounts)==budget and min(amounts)>0
    return {row['uci']:amount for row,amount in zip(rows,amounts)}
