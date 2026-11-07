# Preserved En Croissant and Stockfish integration

Verified 2026-11-07 before the independent web product was built.

| Item | Evidence |
|---|---|
| GUI | Existing current-user En Croissant 0.15.1 at `C:\Users\LOVE\AppData\Local\en-croissant\en-croissant.exe` |
| Installer | Existing official installer SHA256 `47E09AE4BF6DB2F41BCA4F82C23EFC578148BBBCC91FA114300CB8F65F8A0219` matched exactly; no reinstall required |
| Engine | `stockfish\stockfish\stockfish-windows-x86-64-universal.exe`, real UCI identity Stockfish 19 |
| Engine SHA256 | `45BC8E4969147DB9C2EB533810637994619BFF0EACC81CCFD9854394901BCBD0` |
| GUI registration | Added through Engines → Add → Local, using the existing workspace executable |
| Configuration | Threads6, Hash512MB, MultiPV3, Skill Level20, UCI_LimitStrength=false; persisted through the application's supported editor |
| UCI test | uciok, readyok, startpos, go depth20; actual `bestmove e2e4 ponder e7e5`, three depth20 PVs, normal exit0 |
| GUI analysis | Actual evaluations, three lines, node/depth counters and board arrows displayed |
| Game | Human-side e4 followed by actual Stockfish ...e5; GUI engine logs retained |
| PGN | Sample loaded; pre-mate position showed +M1 and Qxf7#; actual UCI bestmove h5f7 |

The original engine was neither reinstalled nor replaced. Existing GUI engine
entries and background state were preserved. Bounded searches were paused after
evidence capture. A complete human game and cold GUI restart were not claimed by
this initial smoke test; the independent chess product subsequently exercised
complete games and restart recovery separately.

The former GUI launcher is preserved as `Start-Stockfish-GUI.ps1`.
`Start-CHESS-ELO-5000.ps1` now launches the independent chess product.
Detailed screenshots, UCI transcripts and integrity receipts remain in the local
`evidence/` directory and the verification delivery.
