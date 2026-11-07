# CHESS ELO 5000 — Engineering and verification report

Completed 2026-11-07T02:59:37+00:00.

Version: **0.1.0-development**. Accepted source: **d273edc67897f3a7540bbe7105edce5a10b5ee15**. Source tree: `966efc8ef726f0877861b9e7b001676d83923108`.

## Repository and workspace

Independent public repository: https://github.com/chatgptopenaiagi/CHESS-ELO-5000

Source: `C:\xampp\CHESS-ELO-5000`. Operational state: `runtime\chess.sqlite3`, `runtime\research.sqlite3`, and the private `runtime\joomla` deployment. No module imports another project's mutable source or runtime. The release tag identifies the accepted application commit; a later report-only commit does not change that frozen identity.

## Launch and credentials

Run `pwsh -NoProfile -File .\Start-CHESS-ELO-5000.ps1`. The primary website is **http://127.0.0.1:18952/**; administrator: **http://127.0.0.1:18952/administrator/**. Standalone client/API: **http://127.0.0.1:18961/**.

The owner launcher was executed with its normal browser-opening behavior. It reused this product's verified processes. The extracted launcher was separately exercised with `-NoBrowser`, correctly using that copy's own API 18971/site 18972. Generated Joomla credentials are in `runtime/private/joomla-access.json`; standalone credentials are in `runtime/private/config.json`. Credentials, databases, browser sessions and SQL backups are excluded from public source/packages.

## Chess rules and gameplay — VERIFIED

The server is authoritative: python-chess 1.11.2 validates moves, castling, en passant, promotions, checkmate/stalemate, insufficient material and repetition/move-count draws. Claimable threefold/fifty-move draws remain distinct from automatic fivefold/seventy-five-move termination. Application rules cover clocks, forfeits, resignation, agreement and study-only undo.

Accepted moves are transactional and persisted with version/request identities. Identical duplicate submissions are idempotent; conflicting submissions, concurrent version conflicts and stale engine responses cannot add extra moves. Actual terminal games, engine replies and exact board reconstruction after a real backend process restart passed acceptance. Human White/Black, click/drag/touch/keyboard board controls, highlights, rotation, capture display, history/replay and promotion selection are implemented and exercised by regression/browser tests.

## Chess engine and Windows GUI — VERIFIED

Original engine: `C:\xampp\CHESS-ELO-5000\stockfish\stockfish\stockfish-windows-x86-64-universal.exe`, **Stockfish 19**. SHA256: `45BC8E4969147DB9C2EB533810637994619BFF0EACC81CCFD9854394901BCBD0`. It was neither replaced nor reinstalled.

Default analysis: **Threads = 6, Hash = 512 MB, MultiPV = 3, Skill Level = 20, UCI_LimitStrength = false**. Options are discovered through actual UCI communication. Bounded depth/time/node limits, legal PV validation, cancellation, engine-crash/timeout handling and configuration-bound cache identities are implemented.

Direct `uci`, `isready`, `position startpos`, `go depth 20` test passed: **`bestmove e2e4 ponder e7e5`**, three depth 20 lines, 3,959,852 reported nodes, 1.182s engine time, 1.952s protocol test elapsed, exit0. Scores preserve centipawn/mate representation and perspective.

The earlier En Croissant 0.15.1 integration remains available at `C:\Users\LOVE\AppData\Local\en-croissant\en-croissant.exe` through `Start-Stockfish-GUI.ps1`. Actual local-engine registration, live evaluations, human e4/engine e5 and sample-PGN mate analysis were observed. See `CHESS-GUI-INTEGRATION-REPORT.md` and its GUI/UCI evidence.

## Joomla and authentication — VERIFIED

Independent physical website: `C:\xampp\htdocs\chess-elo-5000`, **Joomla 6.2.0**. Reused XAMPP PHP 8.5.12, Apache 2.4.65 and MariaDB 10.11.16. Dedicated loopback MariaDB 18953 owns `chess_elo_5000_db`; dedicated Apache 18952 uses this product's own configuration. Existing XAMPP services/sites were not reconfigured.

The native `com_chesselo5000` component and chess template provide frontend play/study/research and administrator content revisions, engine availability, settings and job views. The native Joomla package was installed through both supported CLI and the real administrator upload interface. Its deterministic SHA256 is `BE3B5F9EFA61455C1E3768F8DDF6990EFE1503CFF5BAD94BBD5D61A2EE7F25B3`.

Joomla sessions/CSRF/permissions gate a server-side HMAC bridge with timestamp, nonce, user, method, path and body binding. Guest writes, invalid signatures, replay and path-encoding ACL bypasses are rejected. Standalone owner sessions use HttpOnly cookies and CSRF. Passive status reads do not create analysis jobs.

## Analysis, archiving and memory — VERIFIED

PGN/FEN/SAN/UCI, strict imports, preserved PGN comments/variations, exports, saved archives and deterministic replay are working. Hypothetical branches retain ancestry and do not rewrite historical moves. The coach distinguishes rules facts, actual matching engine evidence and heuristic interpretation; concrete continuations are legally validated.

Analysis cache identity includes full FEN, executable SHA256, limits and configuration. A cached lower-budget result is not relabeled as deeper analysis. Independent SQLite stores preserve games, moves, jobs, evaluations, branches, experiments, content revisions and learning events. Interrupted work remains explicit and does not automatically restart expensive searches.

## Learning — VERIFIED INITIAL CATALOG

The product includes **23 playable lessons** across beginner/intermediate/advanced/expert research, **10 composed puzzles**, **five opening studies** and **eight endgame studies**. Attempts, hints, completions and progress persist. Lesson/puzzle lines are rules-validated; mate objectives use legal enumeration where stated. Other tactical examples are labeled as validated teaching lines, not proofs of a unique solution. Opening frequencies are not fabricated.

The deterministic coach works without an LLM. Syzygy tablebases and optional local/external LLM providers are **UNCONFIGURED**. Endgame exercises and engine estimates remain useful without them. No unverified exact-tablebase claim is displayed.

## DRAGONHYDRA reuse and preservation — VERIFIED WITH EXPLICIT SCOPE

Read-only inspection covered DRAGONHYDRA, CORE NEXT and GENESIS 6/6.1/6.2. The small partial-pivot ridge solver and prospective-relevance safeguards were adapted; memory, bounded jobs, branching, API contracts, evaluation and packaging patterns were reconstructed for chess. Football probabilities, providers, odds, markets and operational databases were excluded. The detailed decision matrix is `docs/DRAGONHYDRA-REUSE-MATRIX.md`.

DRAGONHYDRA HEAD `a63068de10a111a7784bcf677101a66b693d0908` and its preexisting dirty status remain unchanged. CORE NEXT HEAD `a4c0ecf1b7d0eaf35afdb7367ce8e464f285037e` and clean status remain unchanged. The original 12-release GitHub inventory is unchanged. All 30 preexisting web/database process identities were preserved during extracted Joomla acceptance. No foreign operational database or Codex configuration was modified.

Machine inventory was refreshed narrowly from 1706 to 1710 records, preserving all prior records and histories. JSON/TOML parity and derived generation readback passed. New chess graph nodes remain metadata-only: automatic `find chess` routing has no curated candidates. Exact records and current evidence are inspectable; this limitation was recorded without modifying TRADING source.

## Relevance and mathematical research — EXPERIMENTAL

Decision-time features rank legal moves. A small ridge policy trains only on TRAIN families; validation selects its fixed penalty. Mirrored/transposed positions are grouped/deduplicated. The model is frozen before held-out labels; each held-out position's ranking/allocation receipt precedes that same position's expensive reference result. The model is not updated from held-out outcomes. Every legal candidate receives positive requested budget.

Final experiment: **bedf34f7d6b849d19598a503a8b412c7**, clean accepted source, seed 7331, 20,000 requested nodes per arm/position, 40,000 reference nodes. Six held-out positions produce 24 comparisons. Actual node use differs from requested budgets, including protocol overshoot and solved-position underspend.

| Method | Reference move agreement | Actual nodes | Measured search seconds |
|---|---:|---:|---:|
| Conventional | 6/6 | 102575 | 0.2391 |
| Uniform | 5/6 | 119054 | 2.7115 |
| Heuristic | 6/6 | 117920 | 2.6907 |
| Learned | 6/6 | 112249 | 2.6320 |

Uniform mean cp regret was 3 over the four cp-comparable positions; the other methods had 0. Mate positions stay separate. **No improvement over conventional Stockfish analysis was demonstrated.** This tiny sample is not evidence of general search superiority or calibrated probabilities. A strict-node negamax/alpha-beta/quiescence implementation provides a transparent experimental reference, not a replacement-strength claim.

Historical failed attempts and repairs remain in evidence. `research-verification-correction.json` supersedes an earlier overbroad aggregate chronology statement: the verified ordering is per position, not every prediction preceding every position's label.

## Tournaments and reproducibility — EXPERIMENTAL, EXECUTION VERIFIED

Final tournament: **9d492305e0314024bcd4f3e4bf0e2da9**. Two independent full-skill Stockfish processes (Threads 1; Hash 32 MB versus 16 MB) play two composed starting positions with color reversal, 3000 requested nodes/move and a 120-ply cap. Hash is cleared between games. Four games completed: **2 wins, 0 draws, 2 losses**, no unfinished games, crashes, timeouts, illegal moves or protocol failures.

The sample's smoothed relative Elo estimate is 0; exploratory Wilson score interval is [0.1500,0.8500]. It applies only to these participants/positions and establishes no official or universal rating. Source, engine, FEN, limits, actual nodes/time, outcomes and replay PGNs persist. Cancellation and persisted dashboard reload were tested. **ELO 5000 is brand identity, not achieved strength.**

## Performance — MEASURED ON THIS HOST

Final clean-source measurements:100 legal positions 0.0431s ; 1000 positions 0.4088s ; 10,000 positions 4.9498s (9914 unique FENs,276274 legal moves). Ranking100 positions took 0.6403s.10,000 SQLite upserts took 0.1001s.100 actual bounded Stockfish adapter analyses searched 320955 nodes in37.9081s total adapter elapsed, including process/protocol overhead.

Python traced peak was 736392 bytes for the measured generation workload; this excludes native Stockfish memory and is not total process RAM. Measurements are workload/host-specific and do not establish a hardware-independent advantage. Full per-position evidence is in `performance-final.json`.

## Databases and restart — VERIFIED

The game database has versioned schema 1. Independent research schema and immutable evidence retain experiments and learning. SQLite online backups were restored into a new runtime and checked. MariaDB backup/restore produced 76 tables ; 70 stable-table digests matched exactly. Six authentication/user tables, including `chess_users` and `chess_user_profiles`, were excluded from the live-source digest comparison; see the database receipt for the exact exclusions. No private SQL dump is shipped.

Actual backend process restart preserved the same FEN, moves, side, status, result and game identities; terminal games did not resume. Actual full extracted Apache/MariaDB stop/start retained site credentials and authenticated backend communication.

## Acceptance evidence

These are separate scopes, not a sum of unique tests:

| Acceptance scope | Actual result |
|---|---|
| Python rules/backend/security/research regressions |101 passed,0 failed/skipped |
| Node client contracts |6 passed |
| Primary browser gameplay/study/analysis/learning |39 passed,0 uncaught JS errors |
| Primary browser after real backend restart |8 passed |
| Exact native package through real Joomla administrator |13 passed, no missing-file warnings |
| Final source-bound research browser after restart |21 passed,0 uncaught JS errors |
| Additional post-publication keyboard browser check |7 passed; Enter, arrows, Escape, real accepted e2e4 |
| Fresh Development ZIP, isolated offline Python environment |43 passed |
| Fresh Python Backend ZIP, isolated offline Python environment |43 passed |
| Fresh Joomla site/API/database and full service restart |6 groups passed ; 21 HTTP checks before and21 after |
| Extracted launcher/source and cleanup |100 source hashes matched ; 0 test processes/listeners left |

Adversarial coverage includes illegal/special moves, claimable/automatic draws, expired clocks, duplicates/concurrency, stale engine results, malformed PGN/FEN/UCI/PV, genuine controlled UCI subprocess crashes/timeouts, interrupted jobs, cache mismatch, invalid puzzle lines, missing optional tools, nonfinite learning inputs, budget limits and authentication/bridge/package failures. Demonstrated defects were repaired; initial failing receipts remain available.

## Packaging and publication

Published prerelease: **[v0.1.0-dev.1-chess-elo-5000](https://github.com/chatgptopenaiagi/CHESS-ELO-5000/releases/tag/v0.1.0-dev.1-chess-elo-5000)** at `2026-11-07T02:56:55Z`. It is public, marked prerelease, and is no longer a draft. The annotated remote tag resolves to the accepted source commit.

All seven published assets were actually downloaded after publication. Each downloaded SHA256 equals its accepted local value and GitHub-reported digest; the downloaded checksum file and manifest also passed.

| Artifact | Bytes | SHA256 |
|---|---:|---|
| CHESS-ELO-5000-Development.zip | 82792911 | `62f38d7891f74f9ef230f41ee1f6d545cd67eba574fa04e20e3e9b962a1645a9` |
| CHESS-ELO-5000-Joomla-Package.zip | 40075 | `be3b5f9efa61455c1e3768f8ddf6990efe1503cff5bad94bbd5d61a2ee7f25b3` |
| CHESS-ELO-5000-Python-Backend.zip | 82738498 | `bab1817863197185c24a197a875f5801ecb8054bc463a248aeea9c43cc3e2fe6` |
| CHESS-ELO-5000-Source.zip | 926940 | `c5eb87dab5de8c74e148d76d7d6a3daa03311f645fada72ab46f6253ef376653` |
| CHESS-ELO-5000-Verification.zip | 7176491 | `7b390ca2e9c572252c08a057f21a9035ade3a42ffbb495bb236adf7e7f68e138` |
| MANIFEST.json | 3033 | `75a9cb73b39870ec06878ec150ae6b31d3ae1b97362ff91535e382fd5c274aff` |
| SHA256SUMS.txt | 492 | `80609ef686ef80c53cc62277d55866a47ec0917cd55ed2d55e745b9d77d4df41` |

Local artifacts: `dist/v0.1.0-dev.1-chess-elo-5000/`. Downloaded copies: `runtime/published-download-verification/`. Post-publication receipts are committed under `evidence/accepted/`; the full local evidence remains under `evidence/`.

Post-publication preservation rechecked the original Stockfish hash, both protected Git worktrees and all 12 DRAGONHYDRA releases. The primary chess website/API are left running; all extracted acceptance services are stopped.

The final four application artifacts are byte-identical to the extracted accepted candidate. The Verification ZIP was rebuilt to include final local acceptance. Source and Development packages preserve all 100 committed source files. Development/Backend include the unchanged Stockfish executable, corresponding source and eight offline Python 3.14 Windows runtime wheels. Source includes corresponding engine source and verified installation instructions. Python/XAMPP prerequisites are not redistributed.

Ten primary/extracted credential values were scanned against all five archives, including nested packages: 0 matches. No Desktop.exe or Setup.exe was built or advertised. Build/manifest/package verification and post-publication receipts are separate stages; post-publication receipts cannot be inside previously frozen ZIPs.

## Limits and final status

**COMPLETE for Development Preview 0.1.0 acceptance and delivery.** Gameplay, analysis, archiving, initial interactive learning, native Joomla integration, persisted research execution and reproducible packages are verified within the scopes above.

Research policy quality and tournament strength remain **EXPERIMENTAL/UNVERIFIED** beyond the small reported samples. Optional tablebases/LLMs remain **UNCONFIGURED**. Complete advanced curricula, public Internet production hosting, OS-reboot/service installation, native installers and native Linux/mobile applications are **NOT_RUN / outside this preview**. The loopback Flask server is development hosting. Offline wheels are tested for Python 3.14 x64; other supported Python versions require matching dependencies. No higher Elo or computational superiority is claimed.
