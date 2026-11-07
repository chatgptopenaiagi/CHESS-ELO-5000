# Joomla integration evidence

The independent Joomla 6.2.0 site is installed and connected to the local chess API. This report distinguishes supported CLI installation, actual HTTP/session acceptance and browser visual acceptance.

| Scope | Result | Evidence |
|---|---|---|
| Official Joomla package identity | VERIFIED | `evidence/joomla/environment-verification.json` |
| Supported fresh Joomla CLI installation | VERIFIED | `evidence/joomla/installation-cli.log` |
| Native component/template initial and repeated installation | VERIFIED through Joomla CLI | `evidence/joomla/extension-cli-install.log`, `extension-cli-repeat.log` |
| Frontend component and installed web assets | VERIFIED HTTP 200, correct title and interactive client markup | `evidence/joomla/http-acceptance.json` |
| Real Joomla administrator authentication and native component | VERIFIED HTTP session | Same receipt |
| Authenticated HMAC bridge | VERIFIED against backend port 18961 | Same receipt |
| Lesson, puzzle and study revision persistence | VERIFIED through Joomla session + token + bridge | Timestamped HTTP acceptance receipt |
| Authentication, CSRF, malformed path and pairing failures | VERIFIED rejection | Same receipt |
| Invalid extension installation | VERIFIED expected installer exit 1; installed manifest retained | `evidence/joomla/invalid-extension-verification.json` |
| MariaDB recovery | VERIFIED real backup and disposable restore: 76 tables restored; exact digests over 70 stable tables | `evidence/joomla/database-restore-verification.json` |
| Protected existing web/database process identities | VERIFIED at HTTP acceptance | `evidence/joomla/protected-process-baseline.json`, HTTP receipt |
| Actual browser package upload/reinstall, administrator connection/content revision, frontend authentication, gameplay and analysis | VERIFIED: 11 PASS, zero FAIL; no JavaScript errors or installer warnings | `evidence/browser/20261107T022453Z-joomla-install/verification.json` |

The final agent-owned HTTP run recorded **24 PASS, zero FAIL and zero NOT_RUN**. It includes the three content writes. Timestamped receipts retain the exact case inventory. The subsequent invalid-extension test is a separate case, not included in that 24-case count.

The SQL recovery test excludes six volatile authentication/user tables from live-source row-digest comparison because concurrent browser sessions can legitimately update them. All 76 tables were restored; 70 stable tables had matching row counts and SHA256 digests. This does not claim a whole-host or service-account recovery. The original database was never overwritten. Private SQL dumps are excluded from source and release assets.

Observed repairs were retained:

- The XAMPP Apache build compiles `mpm_winnt` in; an attempted dynamic module load failed configuration validation. `httpd -l` established the correct route and the redundant load was removed.
- The existing default PHP configuration did not enable its installed ZIP extension. A chess-only copied PHP configuration enables it; the global PHP configuration remains unchanged.
- Windows Apache's `-k restart` searched for an absent default service. The failed call changed no service. Only the chess configuration-bound Apache processes were restarted.
- The first HTTP harness reused PowerShell's reserved `HOME` variable, and the next used a board selector different from the client's actual `chessboard` identity. Both harness defects were corrected and failed receipts retained. They are not counted as passing application cases.
- Security review identified encoded and dot-segment path normalization risks in proxy ACL checks. Canonical route validation and real HTTP rejection tests now cover both paths.
- The first real browser upload reported a missing `media/assets` directory: the buildless client has no separate assets, but the manifest declared an empty folder. The declaration and empty build directory were removed. The native package regression now verifies all 15 declared files/folders contain actual files; the preserved pre-repair package is correctly rejected. A real browser reinstall then passed cleanly with no warning. The tested package SHA256 is `e2a6573d89a0c2a1e08ef198d27ab0df2b11c0d0c783b0661a42da26bff07898`.

The native extension adapts the existing DRAGONHYDRA component's MVC/DI and server-side bounded HMAC transport pattern. It uses its own namespaces, headers, packet contract, identities, storage and product-specific content controllers. No football interface, betting model, existing administrator account or mutable DRAGONHYDRA runtime path was copied.

Sources inspected read-only included `DRAGONHYDRA-CORE-NEXT/server/joomla/com_dragonhydra/admin/services/provider.php`, `admin/src/Service/ApiClient.php`, component manifest and site MVC controller/view. Their purpose was architectural reuse; successful operation is established by the new chess evidence above.

The Joomla artifact is built from `joomla/` plus the final `client/web/` files using `scripts/Build-JoomlaChessPackage.ps1`. `evidence/joomla/package-manifest.json` binds its inputs and SHA256. The final release builder must rebuild this artifact after source freeze and verify that final artifact's own hash; earlier development hashes must not be reused as final release identities.

`scripts/Test-ExtractedJoomlaChess.ps1` supports source-extracted acceptance with a separate target website and separate MariaDB process/data directory. Its execution receipt must be consulted before claiming that extracted full-service lifecycle scope passed; source parsing alone establishes no runtime proof.
