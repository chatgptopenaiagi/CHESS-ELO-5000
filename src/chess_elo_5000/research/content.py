"""Authored, playable lessons and composed exercises; no fabricated statistics."""
from __future__ import annotations
from functools import lru_cache
import chess

def board_after(sans):
    board=chess.Board()
    for san in sans.split():board.push_san(san)
    return board

SCHOLAR=board_after('e4 e5 Qh5 Nc6 Bc4 Nf6').fen()
PROMOTION='7k/P7/8/8/8/8/8/7K w - - 0 1'
FORK='r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1'
PIN='4k3/8/2n5/8/8/8/8/4KB2 w - - 0 1'
SKEWER='4q3/8/8/4k3/8/8/8/R6K w - - 0 1'
DISCOVERY='3q2k1/8/8/8/8/3B4/8/3R2K1 w - - 0 1'
BACKRANK='6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1'
MATE_TWO='8/8/6Q1/8/7K/8/8/7k w - - 0 1'

def forced_mate(board,plies,attacker):
    if board.is_checkmate():return board.turn!=attacker
    if plies<=0 or board.is_stalemate() or board.is_insufficient_material():return False
    moves=list(board.legal_moves)
    for move in moves:
        board.push(move)
        value=forced_mate(board,plies-1,attacker)
        board.pop()
        if board.turn==attacker and value:return True
        if board.turn!=attacker and not value:return False
    return bool(moves) and board.turn!=attacker

def puzzle_objective(board,move,item):
    kind=item['test']
    if move not in board.legal_moves:return False
    side=board.turn;piece=board.piece_at(move.from_square)
    board=board.copy();board.push(move)
    if kind=='mate1':return board.is_checkmate()
    if kind=='mate2':return forced_mate(board,2,side)
    if kind=='fork':return piece.piece_type==chess.KNIGHT and board.is_check() and any(board.piece_at(sq) and board.piece_at(sq).color!=side and board.piece_at(sq).piece_type==chess.ROOK for sq in board.attacks(move.to_square))
    if kind=='pin':return any(board.is_pinned(not side,sq) for sq in board.pieces(chess.KNIGHT,not side))
    if kind=='promotion':return bool(move.promotion==chess.QUEEN)
    return move.uci() in item['solutions']

@lru_cache(maxsize=1)
def puzzles():
    rows=[
      dict(id='scholar-mate',title='The undefended f7 square',category='MATE IN ONE',fen=SCHOLAR,test='mate1',objective='Find a move that immediately checkmates.',hint='The bishop on c4 protects the queen’s destination.',difficulty='Beginner',solutions=['h5f7']),
      dict(id='quiet-mate-two',title='A quiet king move',category='MATE IN TWO',fen=MATE_TWO,test='mate2',objective='Find the first move forcing mate within two White moves against every legal reply.',hint='The queen controls g1 until the king blocks that file.',difficulty='Intermediate',solutions=['h4g3']),
      dict(id='royal-fork',title='One knight, two targets',category='FORK',fen=FORK,test='fork',objective='Give check with a knight that also attacks the rook.',hint='A knight on c7 attacks a8 and e8.',difficulty='Beginner',solutions=['d5c7']),
      dict(id='absolute-pin',title='Line up the bishop',category='PIN',fen=PIN,test='pin',objective='Create an absolute pin of the black knight to its king.',hint='Find the diagonal b5–c6–d7–e8.',difficulty='Intermediate',solutions=['f1b5']),
      dict(id='rook-skewer',title='King in front, queen behind',category='SKEWER',fen=SKEWER,test='line',objective='Move the rook to the e-file, checking the king in front of its queen.',hint='The first rank is clear.',difficulty='Intermediate',solutions=['a1e1']),
      dict(id='discover-queen',title='Unmask the rook',category='DISCOVERED ATTACK',fen=DISCOVERY,test='line',objective='Give check with the bishop while opening the d-file rook attack on the queen.',hint='The bishop can reach h7.',difficulty='Intermediate',solutions=['d3h7']),
      dict(id='back-rank',title='No flight square',category='BACK-RANK MATE',fen=BACKRANK,test='mate1',objective='Checkmate on the eighth rank.',hint='The pawns block the king’s flight squares.',difficulty='Beginner',solutions=['a1a8']),
      dict(id='deflect-king',title='Deflect the king onto a mating line',category='DEFLECTION',fen=MATE_TWO,test='mate2',objective='Force the king away from h1 and mate within two White moves.',hint='Play Kg3, then answer the forced ...Kg1 along the first rank.',difficulty='Advanced',solutions=['h4g3']),
      dict(id='tactical-defense',title='Meet the queen’s check',category='TACTICAL DEFENSE',fen=board_after('e4 e5 Qh5 Nc6 Bc4 Qe7 Qxf7+').fen(),test='line',objective='Capture the checking queen with the king.',hint='The white bishop on c4 protects f7: the king cannot capture. Use the queen instead.',difficulty='Advanced',solutions=['e7f7']),
      dict(id='promote-queen',title='Choose the promotion',category='ENDGAME TECHNIQUE',fen=PROMOTION,test='promotion',objective='Promote the pawn to a queen, selecting the piece explicitly.',hint='The UCI move needs the q promotion suffix.',difficulty='Beginner',solutions=['a7a8q'])
    ]
    # Replace the defensive composition with a legal queen interposition exercise.
    rows[8].update(fen='4r1k1/8/8/8/8/8/3Q4/4K3 w - - 0 1',objective='Block the rook check by moving the queen to e2.',hint='A queen can interpose on e2.',solutions=['d2e2'])
    for item in rows:
        b=chess.Board(item['fen'])
        if not b.is_valid():raise ValueError('Invalid puzzle '+item['id'])
        accepted=[m.uci() for m in b.legal_moves if puzzle_objective(b,m,item)]
        if not accepted:raise ValueError('Puzzle has no verified answer '+item['id'])
        item['solutions']=accepted
        item['unique_under_objective']=len(accepted)==1
        item['side_to_move']='white' if b.turn else 'black'
        item['source']='Authored composition or explicit rules-generated opening line; no historical frequency claim.'
        item['verification']='RULES_VERIFIED' if item['test'] not in ('mate1','mate2') else 'EXHAUSTIVE_LEGAL_MATE_VERIFIED'
    return rows

@lru_cache(maxsize=1)
def lessons():
    start=chess.STARTING_FEN
    opening=board_after('e4 e5').fen()
    rook='7k/8/8/8/8/5K2/8/R7 w - - 0 1'
    pawn='8/4k3/8/4K3/4P3/8/8/8 w - - 0 1'
    specs=[
      ('BEGINNER','Board orientation','White’s right-hand corner is h1. Start by moving the e-pawn two squares.',start,['e2e4']),
      ('BEGINNER','Piece movement','A knight jumps in an L shape. Develop the g1 knight to f3.',start,['g1f3']),
      ('BEGINNER','Legal moves','A rook cannot jump over its own pawn. Advance the a-pawn to clear its file.',start,['a2a4']),
      ('BEGINNER','Check and checkmate','Check requires a legal response. Here the protected queen can deliver mate on f7.',SCHOLAR,['h5f7']),
      ('BEGINNER','Basic tactics','A checking knight fork attacks two valuable targets. Try Nc7+.',FORK,['d5c7']),
      ('BEGINNER','Elementary endgames','A pawn reaching the last rank must choose a new piece. Promote to a queen.',PROMOTION,['a7a8q']),
      ('INTERMEDIATE','Opening principles','Develop while influencing the center. Nf3 attacks e5; it is an example, not a unique best-move claim.',opening,['g1f3']),
      ('INTERMEDIATE','Development','Bring a minor piece into play before repeatedly moving the same piece.',start,['b1c3']),
      ('INTERMEDIATE','King safety','Castling requires clear squares, retained rights and no attacked transit square.',board_after('e4 e5 Nf3 Nc6 Bc4 Nf6').fen(),['e1g1']),
      ('INTERMEDIATE','Pawn structure','A central pawn move changes controlled squares and available files. Examine d4.',opening,['d2d4']),
      ('INTERMEDIATE','Tactical combinations','Open one line while creating a forcing threat on another.',DISCOVERY,['d3h7']),
      ('INTERMEDIATE','Piece coordination','The bishop c4 protects the queen on f7. The mating move works because both pieces cooperate.',SCHOLAR,['h5f7']),
      ('ADVANCED','Positional planning','Place the rook on an open file. This is a playable planning example; check engine alternatives.',rook,['a1e1']),
      ('ADVANCED','Calculation','List legal defenses before assuming a threat works. A quiet king move can force mate here.',MATE_TWO,['h4g3']),
      ('ADVANCED','Candidate moves','Start with checks and captures, then include quiet candidates. Here examine the knight fork.',FORK,['d5c7']),
      ('ADVANCED','Strategic imbalances','A rook’s open-file access differs from material advantage. Improve its activity without claiming an exact win.',rook,['a1a7']),
      ('ADVANCED','Endgame technique','Improve the king before pushing a pawn. Opposition is geometric, not a guarantee without calculation.',pawn,['e5d5']),
      ('ADVANCED','Defensive resources','Interposing a piece is one way to answer a line check. Play Qe2.',puzzles()[8]['fen'],['d2e2']),
      ('EXPERT RESEARCH','Search algorithms','Negamax and alpha-beta examine legal continuations. First create a candidate position, then compare bounded searches.',opening,['g1f3']),
      ('EXPERT RESEARCH','Evaluation functions','An evaluation is a model-dependent estimate. A forced mate is represented separately from centipawns.',SCHOLAR,['h5f7']),
      ('EXPERT RESEARCH','Engine comparisons','Compare identical starting positions with reversed engine colors and recorded budgets.',start,['d2d4']),
      ('EXPERT RESEARCH','Relevance-driven search','Rank checks, captures and positional changes before expensive search. A high score is not a probability.',FORK,['d5c7']),
      ('EXPERT RESEARCH','Controlled experiments','Freeze the policy before held-out analysis. Keep transpositions in one split and report failures.',opening,['b1c3'])
    ]
    rows=[]
    for i,(level,title,body,fen,line) in enumerate(specs):
        b=chess.Board(fen)
        for uci in line:
            m=chess.Move.from_uci(uci)
            if m not in b.legal_moves:raise ValueError('Invalid lesson '+title)
            b.push(m)
        rows.append(dict(id='lesson-'+str(i+1),level=level,title=title,body=body,fen=fen,solution=line,
                         objective='Play the demonstrated move in the study board.',unique_best_move_claim=False))
    return rows

@lru_cache(maxsize=1)
def studies():
    openings=[('Ruy Lopez','C60','e4 e5 Nf3 Nc6 Bb5','Develop, contest the center and examine the pressure on c6.'),
      ('Sicilian Defense','B20','e4 c5','Asymmetric central control; develop before seeking an attack.'),
      ('French Defense','C00','e4 e6 d4 d5','Study the central pawn chain and the c8 bishop’s development.'),
      ("Queen’s Gambit",'D06','d4 d5 c4','Challenge d5 while maintaining central development.'),
      ('English Opening','A10','c4','Control d5 and compare possible transpositions.')]
    rows=[]
    for i,(title,eco,sans,plans) in enumerate(openings):
        b=chess.Board();moves=[]
        for san in sans.split():m=b.parse_san(san);moves.append(m.uci());b.push(m)
        rows.append(dict(id='opening-'+str(i+1),kind='opening',title=title,eco=eco,fen=chess.STARTING_FEN,
                         final_fen=b.fen(),moves=moves,plans=plans,objective='Replay the study line.',solution=moves,
                         statistics='UNAVAILABLE',source='Named canonical opening prefix; no frequency statistics.'))
    endgames=[('King and pawn','8/4k3/8/4K3/4P3/8/8/8 w - - 0 1',['e5d5'],'Investigate king activity and the pawn’s promotion path.'),
      ('Rook endgames','7k/8/8/8/8/5K2/8/R7 w - - 0 1',['a1a7'],'Cut off the opposing king, then verify the continuation.'),
      ('Queen endgames',MATE_TWO,['h4g3','h1g1','g6b1'],'A quiet king move creates a forced mating net.'),
      ('Minor piece endgames',FORK,['d5c7'],'Use the knight’s fork geometry.'),
      ('Pawn promotion',PROMOTION,['a7a8q'],'Promotion requires explicit piece selection.'),
      ('Opposition','8/4k3/8/4K3/4P3/8/8/8 w - - 0 1',['e5d5'],'Compare king opposition after each legal reply. This example does not assert a forced win.'),
      ('Zugzwang investigation','8/8/4k3/4p3/4K3/8/8/8 w - - 0 1',['e4d3'],'Compare the position with opposite side to move using engine analysis; no exact zugzwang result is claimed.'),
      ('Basic mating techniques',BACKRANK,['a1a8'],'Use the opponent’s blocked flight squares.')]
    for i,(title,fen,moves,plans) in enumerate(endgames):
        b=chess.Board(fen)
        if not b.is_valid():raise ValueError('Invalid endgame '+title)
        for uci in moves:b.push_uci(uci)
        rows.append(dict(id='endgame-'+str(i+1),kind='endgame',title=title,fen=fen,moves=moves,solution=moves,
                         plans=plans,objective='Play the demonstrated continuation and compare alternatives.',
                         tablebase_status='UNCONFIGURED',evaluation_kind='RULES_VERIFIED_LINE_NOT_TABLEBASE_VALUE'))
    return rows
