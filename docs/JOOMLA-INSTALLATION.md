# Independent Joomla chess website

The tested installation uses Joomla 6.2.0 and the existing XAMPP executables. It has its own website, PHP configuration, Apache process, MariaDB process, data directory, database, Joomla secret, administrator and database credentials.

| Resource | Tested identity |
|---|---|
| Website | `http://127.0.0.1:18952/` |
| Administrator | `http://127.0.0.1:18952/administrator/` |
| Site files | `C:\xampp\htdocs\chess-elo-5000` |
| Database | `chess_elo_5000_db`, loopback port 18953 |
| Chess backend | Configured in this product's `runtime/private/config.json`; tested at port 18961 |
| PHP | `C:\xampp\php\php.exe`, 8.5.12 |
| Apache | `C:\xampp\apache\bin\httpd.exe`, 2.4.65 |
| MariaDB | `C:\xampp\mysql\bin\mysqld.exe`, 10.11.16 |
| Service configuration | `runtime/joomla/services.json` and adjacent configuration files |
| Owner credentials | `runtime/private/joomla-access.json`, local only |

Run the product dependency/backend setup first, then:

```powershell
pwsh -NoProfile -File .\scripts\Install-JoomlaChess.ps1
pwsh -NoProfile -File .\scripts\Build-JoomlaChessPackage.ps1
```

The installer reuses an existing official Joomla 6.2.0 full ZIP in the current user's Downloads folder. If it is absent, it obtains the pinned official GitHub release asset and verifies SHA1 `67a107c83b3084701a1a4acb151cd0452e5deaaf` and SHA256 `eaafc68b5990d7b9dd9156656d4c3c3547743d1d7a85682a92e2f9121b58f018` before extracting. The published SHA1 is recorded on the [official Joomla release page](https://downloads.joomla.org/us/cms/joomla6/6-2-0). Installation runs Joomla's supported `installation/joomla.php install` command. It does not clone another site's users or configuration.

Sign in to the new Joomla administrator using the locally generated account from the private access file. Under **System → Install → Extensions**, upload `dist/CHESS-ELO-5000-Joomla-Package.zip`. This package installs the native `com_chesselo5000` component and `chesslab` site template. Its supported Joomla installer creates the chess homepage. Installing the package again updates the same extension identities.

The CLI alternative is also supported and was exercised:

```powershell
C:\xampp\php\php.exe -c .\runtime\joomla\php.ini C:\xampp\htdocs\chess-elo-5000\cli\joomla.php extension:install --path=C:\xampp\CHESS-ELO-5000\dist\CHESS-ELO-5000-Joomla-Package.zip --no-interaction
```

The frontend is the complete local client installed into `media/com_chesselo5000`. The native administrator manages lesson, puzzle and study revisions, bounded research settings, and displays actual engine availability and job status. Content changes pass through the Python API and its legal-position validation.

Joomla authenticates browser users. Persistent requests require Joomla's session token. A server-side HMAC bridge signs the timestamp, nonce, numeric Joomla identity, method, canonical API path and exact body hash. The bridge secret stays in the protected product configuration outside the website. Administrator API paths additionally require `core.manage` on the chess component. Encoded or noncanonical paths are rejected before cURL routing. The frontend receives no backend credential. A separate Joomla frontend sign-in may be required after an administrator sign-in because Joomla maintains separate client sessions.

The dedicated Apache configuration supplies `CHESS_PRODUCT_CONFIG`; the component's options can alternatively point to a protected JSON file. Only an explicit loopback backend URL is accepted. Keep `runtime/private` out of Git, archives and public document roots.

```powershell
pwsh -NoProfile -File .\scripts\Start-JoomlaChess.ps1
pwsh -NoProfile -File .\scripts\Verify-JoomlaChess.ps1
pwsh -NoProfile -File .\scripts\Backup-JoomlaChess.ps1
pwsh -NoProfile -File .\scripts\Test-JoomlaChessDatabase.ps1
```

The verification script's optional `-TestBackendWrites` creates clearly named synthetic content revisions in the independent chess backend. The database test creates a real consistent SQL backup, restores it into a new temporary database, verifies stable table contents, then removes only that temporary database. SQL backups contain private site data and stay under `runtime/private/joomla-backups`.

`Stop-JoomlaChess.ps1` targets only process identities bound to the chess configuration and requests graceful MariaDB shutdown with private credentials. Its complete stop/start cycle was not part of the initial HTTP acceptance while the owner-facing browser session was active. It must never be used to stop existing DRAGONHYDRA services.

For an extracted package on the same verified XAMPP host, setup scripts resolve their source/runtime paths from their own location. A fresh independent Joomla target can be selected with `-SitePath`, `-WebPort` and `-DatabasePort`. Existing targets without a chess ownership marker and ports owned by other processes are refused. Ports 18740–18751 remain excluded. No CHESS ELO 5000 runtime imports another project's source or data directories.
