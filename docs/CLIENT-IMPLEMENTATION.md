# Browser client

The buildless client is in `client/web`. It uses local HTML, CSS, and JavaScript;
there are no CDN, external font, image, or package dependencies. The backend
serves these assets and remains authoritative for legal moves and game state.

The client implements a responsive board with pointer and touch movement,
keyboard square navigation, legal destination highlights, promotion selection,
last-move and check highlights, rotation, captured pieces, clocks, history and
replay. A move request contains the saved game version and a fresh request ID.
Engine replies use explicit bounded thinking time. Reopening a board does not
automatically launch engine work.

The remaining sections call actual API contracts for archived games, PGN import
and export, FEN copying, separate variations, bounded analysis, deterministic
coaching, learning exercises, puzzle attempts, studies, relevance experiments and
paired tournaments. Unavailable API calls produce visible diagnostics rather
than fabricated content or metrics.

Standalone authentication uses the backend's HttpOnly session and CSRF token.
The owner password is never stored by the client. A local-storage pointer retains
only the last game identity and display theme. Joomla supplies its authenticated
server proxy and form token through `window.CHESS_CONFIG` before `app.js`:

```javascript
window.CHESS_CONFIG = {
  joomla: true,
  proxy: true,
  apiBase: '/index.php?option=com_chesselo5000&task=api.proxy&format=raw&path=',
  csrfParam: 'THE_CURRENT_JOOMLA_FORM_TOKEN',
  loginUrl: '/index.php?option=com_users&view=login',
  defaultView: 'play'
};
```

Proxy values encode the complete `/api/v1` path and query as a single `path`
parameter. Joomla signs the outgoing backend request; no bridge credential is
sent to browser JavaScript.

Focused checks:

```powershell
& 'C:\Program Files\nodejs\node.exe' --check .\client\web\app.js
& 'C:\Program Files\nodejs\node.exe' --test .\tests\web_contract.test.cjs
```

These checks cover proxy URL boundaries, valid board rendering inputs, malformed
FEN rejection, rotation, text escaping and clock display.

The live browser harness uses Python Playwright and the exact existing Microsoft
Edge executable. It opens isolated headless contexts and closes only its own
browser. It never attaches to the owner's browser or downloads a browser binary.

```powershell
& .\.venv\Scripts\python.exe -m pip install -r .\tests\requirements-browser.txt
& .\.venv\Scripts\python.exe .\tests\browser_acceptance.py --phase before-restart
# Restart the owned chess backend through its normal lifecycle scripts.
& .\.venv\Scripts\python.exe .\tests\browser_acceptance.py --phase after-restart
# Recheck a repaired extension without repeating unrelated gameplay acceptance.
& .\.venv\Scripts\python.exe .\tests\browser_acceptance.py --phase joomla-install
```

Actual acceptance on 2026-11-07 used Microsoft Edge 156.0.4314.58 and Playwright
1.64.1. The accepted main browser scenario had 39 passing checks; the subsequent
backend restart scenario had eight. The repaired Joomla ZIP was then uploaded
and installed through the real administrator with 11 passing checks and no
installer warnings. These batches overlap and are not 58 unique test cases.

The evidence is retained in `evidence/browser`. The first failed attempt is also
preserved: the test harness tried to clear the optional FEN input while its
details panel was collapsed. That was corrected by opening the actual summary
control only when needed. Browser inspection also exposed an extension manifest
reference to a missing assets directory. The Joomla package was repaired and
then passed a separate clean browser installation with its exact ZIP hash bound
immediately before upload.

Credentials are read from `runtime/private`; authenticated browser state stays
there. Evidence receipts and screenshots contain no password or bridge secret.
