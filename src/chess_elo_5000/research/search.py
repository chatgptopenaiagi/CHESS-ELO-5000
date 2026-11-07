"""Transparent strict-node negamax/alpha-beta laboratory, separate from Stockfish."""
from __future__ import annotations
import time
import chess
from .ranking import rank,VALUES,position_id

class BudgetExhausted(Exception):pass

def search(board,budget=10000,model=None,cancel=None):
    if type(budget) is not int or not 1<=budget<=1000000:raise ValueError('Invalid node budget')
    nodes=0; table={}; started=time.perf_counter()
    def tick():
        nonlocal nodes
        if nodes>=budget or (cancel and cancel()):raise BudgetExhausted()
        nodes+=1
    def evaluate(b):
        return sum(VALUES[p.piece_type]*100*(1 if p.color==b.turn else -1) for p in b.piece_map().values())
    def terminal(b,ply):
        if b.is_checkmate():return -100000+ply
        if b.outcome(claim_draw=False):return 0
        return None
    def quiet(b,alpha,beta,ply,qdepth):
        tick()
        end=terminal(b,ply)
        if end is not None:return end,[]
        stand=evaluate(b)
        if qdepth<=0:return stand,[]
        if not b.is_check():
            if stand>=beta:return stand,[]
            alpha=max(alpha,stand)
        moves=[r['uci'] for r in rank(b,model) if b.is_check() or b.is_capture(chess.Move.from_uci(r['uci'])) or chess.Move.from_uci(r['uci']).promotion]
        best=[]
        for uci in moves:
            m=chess.Move.from_uci(uci);b.push(m)
            try:score,line=quiet(b,-beta,-alpha,ply+1,qdepth-1);score=-score
            finally:b.pop()
            if score>alpha:alpha,best=score,[uci]+line
            if alpha>=beta:break
        return alpha,best
    def negamax(b,depth,alpha,beta,ply):
        tick()
        end=terminal(b,ply)
        if end is not None:return end,[]
        if depth==0:return quiet(b,alpha,beta,ply,3)
        # Draw repetition and mate distance are history/ply dependent.
        key=(position_id(b),b.halfmove_clock,depth,ply,tuple(b.move_stack))
        cached=table.get(key)
        if cached:return cached
        original=alpha; best=[];cut=False
        for row in rank(b,model):
            uci=row['uci'];b.push_uci(uci)
            try:score,line=negamax(b,depth-1,-beta,-alpha,ply+1);score=-score
            finally:b.pop()
            if score>alpha:alpha,best=score,[uci]+line
            if alpha>=beta:cut=True;break
        if not cut and alpha>original:table[key]=(alpha,best)
        return alpha,best
    legal=list(board.legal_moves)
    if not legal or board.outcome(claim_draw=False):return dict(move=None,pv=[],nodes=0,depth=0,terminal=True,elapsed_seconds=0)
    best=legal[0].uci();pv=[best];completed=0;value=None
    for depth in range(1,65):
        try:
            score,line=negamax(board.copy(stack=True),depth,-1000000,1000000,0)
            if line:best,pv=line[0],line
            completed,value=depth,score
        except BudgetExhausted:break
    return dict(move=best,pv=pv,nodes=nodes,depth=completed,elapsed_seconds=time.perf_counter()-started,
                value=value,value_type='heuristic_search_utility_not_engine_centipawns',budget=budget,
                algorithms=['negamax','alpha-beta','iterative-deepening','exact-transposition-cache','bounded-quiescence'],
                status='EXPERIMENTAL',budget_exhausted=nodes==budget)
