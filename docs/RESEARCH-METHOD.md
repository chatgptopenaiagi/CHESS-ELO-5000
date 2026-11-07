# Relevance research contract

The experimental quantity is computational attention, not a calibrated probability.
The feature vector is extracted from the current legal position before expensive
reference analysis. It contains only checks, captures, promotions, material/activity
geometry and available legal-move facts. Engine labels and future variations are
never features. Stockfish scores retain their reported side and cp/mate type.

Eight authored opening/composition families produce sixteen positions. A seeded
family split creates TRAIN, VALIDATION and HELD_OUT groups. Normalized and mirrored
transpositions are checked across partitions. Related prefixes stay within one
family. This is a small laboratory sample, not independent population calibration.

Training labels are reference move-rank percentiles. Three fixed ridge penalties
(.1, 1, 10) are selected by validation best-move agreement. The resulting model is
hashed and committed to immutable evidence before held-out reference searches.
Held-out rankings and complete node allocations are also recorded before their
reference analysis. The model remains frozen during held-out evaluation.

Four methods receive the same **requested** node budget: conventional root search,
uniform positive allocation to every candidate, transparent heuristic allocation,
and learned allocation. No legal defense is silently excluded. Each individual
search also has a two-second wall limit and UCI outer deadline; each job has a
120-second deadline. Stockfish may underspend on a solved terminal line or overshoot
node limits in internal batches. Actual nodes, timing and overshoot are recorded.
Multiple candidate searches also incur protocol/hash-reset overhead. Equal requested
budgets must not be represented as identical actual computation.

Reference analysis is finite Stockfish analysis with recorded limits, not perfect
game-theoretic truth. Centipawn regret is computed only when both reference scores
are cp values. Mate comparisons are separately flagged. No mate is converted into
an ordinary centipawn value. Report every arm and negative result; this experiment
does not establish superiority over Stockfish or any universal Elo rating.

The transparent reference search implements strict-node negamax, alpha-beta,
iterative deepening, history-sensitive transposition caching and bounded quiescence.
Its heuristic utility is labeled separately from Stockfish centipawns. MCTS and
principal-variation search are not implemented unnecessarily.

Tournaments are paired, color-reversed composed tactical mini-tournaments between
two independent Stockfish processes at full skill with 32MB/16MB hash settings.
Each game clears both transposition tables. Reduced-skill randomness is avoided
because Stockfish exposes no seed control for that setting. Complete terminal games, unfinished caps,
engine crashes, timeouts, illegal moves and protocol failures are recorded separately.
Relative smoothed Elo and exploratory Wilson score intervals apply only to this
defined sample; they are not FIDE ratings or evidence of a 5000 rating.

The first development run is retained as a pre-review experiment. A review found
that predictions were recorded after reference analysis (although the features did
not use reference labels). It is not accepted as final pre-search-ordering evidence.
The repaired run records the prospective ordering before reference work.
