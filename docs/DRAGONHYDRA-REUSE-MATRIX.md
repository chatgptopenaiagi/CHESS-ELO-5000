# Independent chess reconstruction

Inspected read-only: DRAGONHYDRA `a63068de10a111a7784bcf677101a66b693d0908`,
CORE NEXT `a4c0ecf1b7d0eaf35afdb7367ce8e464f285037e`, and GENESIS-6.1 source
`67c531462e90bc79c653b74066101dfa5a1e4125`. Their operational stores, services,
secrets, release histories and working changes are preserved.

| Foundation | Decision | Chess implementation and boundary |
|---|---|---|
| Mathematical kernel | REPLACED | python-chess generates legal moves; cp and mate values stay distinct. Football probability equations are excluded. |
| Cognitive reasoning | ADAPTED | Deterministic coach uses legal positions, labeled heuristics and matching completed engine evidence. |
| Relevance estimation | REIMPLEMENTED | Decision-time checks/captures/promotion/activity features rank legal candidates. |
| Future relevance | ADAPTED | GENESIS-6.1 feature whitelist, TRAIN-only ridge fitting, validation selection and frozen model receipts precede held-out searches. |
| Ridge solver | REUSED/ADAPTED | Small partial-pivot Gauss-Jordan implementation adapted from `future_relevance/learning.py`; source hash retained in evidence. |
| Tool discovery | ADAPTED | Bounded exact-path/local-library discovery distinguishes presence from measured engine execution. |
| Incremental computation | ADAPTED | Analysis cache includes full FEN, executable hash, limits and configuration; repeated matching results retain their identity. |
| Memory | ADAPTED | Immutable source-linked research evidence and learning events in the independent SQLite store. |
| Experimentation | ADAPTED | Grouped training/validation/held-out positions; four actual engine allocation methods; negative results retained. |
| Database persistence | REIMPLEMENTED | Independent game/research SQLite schemas and Joomla MariaDB database; no foreign operational database connections. |
| API contracts | ADAPTED | Versioned authenticated routes, explicit writes and passive status reads. |
| Authentication | ADAPTED | Local owner session/CSRF and Joomla server-side HMAC bridge with expiry, nonce and body binding. |
| Joomla integration | ADAPTED | Native chess component/template/package; supported installation; independent identity and permissions. |
| Job execution | ADAPTED | Bounded explicit analysis/research jobs, idempotency, cancellation and interrupted-state recovery. |
| Graphical interfaces | REIMPLEMENTED | Chess board and study/learning/research interfaces; no football interface relabeling. |
| Virtual time | REPLACED | Actual application clocks, node budgets and replay; no fictional elapsed-time claim. |
| Branching futures | ADAPTED | Legal hypothetical variations retain original parent game and deterministic position identity. |
| Performance evaluation | ADAPTED | Actual nodes/time, legal generation, cache correctness and fixed requested-budget comparisons. |
| Packaging | ADAPTED | Git-bound source, hashes, complete ZIPs and extracted startup acceptance. |
| Restart recovery | ADAPTED | Reconstruct board from accepted moves; persisted terminal result; pending research is marked interrupted without automatic computation. |
| Sporting providers/markets/odds | EXCLUDED | No feeds, bookmakers, football models, source credentials or provider schedules. |

This is an independent implementation with explicit, limited reuse of working
engineering patterns. No module imports another project's mutable source/runtime.
No general AI capability or learned search superiority is asserted.
