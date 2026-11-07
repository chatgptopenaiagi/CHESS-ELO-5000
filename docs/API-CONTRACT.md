# Independent application contracts

All routes are versioned under `/api/v1`. JSON errors use `error` and `message`.
Only passive system status/engine availability and the sign-in POST are anonymous.
Saved data is owner-scoped. Writes require the local session's `X-CSRF-Token` or
the independently authenticated Joomla server bridge.

| Operation | Route |
|---|---|
| Sign in / current owner / sign out | POST/GET/DELETE `/session` |
| Create/list games | POST/GET `/games` |
| Read game / legal moves / PGN | GET `/games/{id}`, `/games/{id}/legal-moves`, `/games/{id}/pgn` |
| Validated move | POST `/games/{id}/moves` with `uci`, `expected_version`, `request_id` |
| Bounded engine turn | POST `/games/{id}/engine` with matching version/request identity |
| Resign/draw/study undo/clock tick | POST `/games/{id}/resign`, `/draw`, `/undo`, `/tick` |
| PGN import into independent study | POST `/studies/import` |
| Hypothetical variations | GET/POST `/games/{id}/variations` |
| Start/read/cancel analysis | POST `/analysis`, GET `/analysis/{id}`, POST `/analysis/{id}/cancel` |
| Rules and positional descriptions | GET `/positions?fen=...` |
| Lessons / completion | GET `/lessons`; POST `/lessons/{id}/complete` |
| Puzzles / attempts / hints | GET `/puzzles`; POST `/puzzles/{id}/attempts` |
| Opening/endgame studies / position lookup | GET `/learning/studies`, `/openings?fen=...` |
| Progress / evidence-backed coach | GET `/progress`; POST `/coach` |
| Decision-time move relevance | GET `/research/relevance?fen=...` |
| Strict-node reference search | POST `/research/search` |
| Research jobs | GET/POST `/research/experiments`, GET `/research/experiments/{id}`, POST `/{id}/cancel` or `/{id}/resume` |
| Paired mini-tournament | GET/POST `/tournaments`, GET `/tournaments/{id}`, POST `/{id}/cancel` |
| Deterministic tool dispatcher | POST `/dispatch` |
| Capability discovery | GET `/system/tools`, `/engines`; explicit POST `/engines/probe` executes the engine |
| Native admin content/settings/jobs | GET/POST `/admin/content/{lessons,puzzles,studies}`, `/admin/settings`; GET `/admin/jobs` |

Game state includes stable identity, initial/current FEN, UCI/SAN move records,
version, status/result/reason, authoritative legal moves and clocks. Claimable
threefold/fifty-move draws are distinct from automatic fivefold/seventy-five-move
termination. Ordinary history reads do not silently add moves or start engine work.

The game SQLite schema is versioned and reconstructs saved FEN from accepted
moves. Research has its own schema/version, immutable evidence/learning events
and append-only content revisions. Jobs have explicit state transitions; restart
does not automatically restart expensive research. A resumed experiment is a new
attempt linked to the retained earlier job.

Analysis identity includes exact FEN, executable hash, settings and limits. A
cached result preserves its original computation identity. Coach engine evidence
must be completed, owner-accessible and match the current FEN. Both cp and mate
scores preserve their type/perspective; every displayed concrete PV is legal.

Joomla's native proxy accepts only canonical loopback API paths, checks the Joomla
session/token and administrator permission, then signs the exact timestamp, nonce,
numeric owner, HTTP method, API path and SHA256 body. The HMAC key never reaches
the browser. See the source tests for expiry, replay, altered-body, CSRF and
cross-owner adversarial cases.
