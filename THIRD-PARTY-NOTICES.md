# Third-party software

CHESS ELO 5000 source is distributed under GPL-3.0-or-later (see LICENSE).

- python-chess 1.11.2, Niklas Fiekas and contributors: GPL-3.0-or-later.
  https://github.com/niklasf/python-chess
- Stockfish 19, the Stockfish developers: GPLv3. The supplied Windows engine is
  unchanged. Development packages include its original corresponding source,
  AUTHORS, Copying.txt, build scripts and documentation with the executable.
  https://github.com/official-stockfish/Stockfish/tree/sf_19
- Flask 3.1.3 and its dependencies retain their upstream licenses and are
  installed using the pinned requirements rather than relabeled as original code.
- Joomla 6.2.0 is GPL software obtained from the official distribution. Its
  installer and XAMPP runtimes remain separate prerequisites; this project ships
  its native component, template and installer scripts.
- The numerical solver and engineering patterns adapted from the owner's
  DRAGONHYDRA GENESIS-6.1 source are attributed in the source and reuse matrix.
- Playwright is a test-only dependency. The existing Microsoft Edge installation
  is used for browser acceptance; no browser binary is redistributed.
