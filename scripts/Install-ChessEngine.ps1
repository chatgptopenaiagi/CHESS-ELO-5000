#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$engine=Join-Path $root 'stockfish\stockfish\stockfish-windows-x86-64-universal.exe'
if(Test-Path -LiteralPath $engine){return [pscustomobject]@{Path=$engine;Action='Reused';SHA256=(Get-FileHash -LiteralPath $engine -Algorithm SHA256).Hash}}
$downloads=Join-Path $root 'runtime\downloads'
New-Item -ItemType Directory -Path $downloads -Force|Out-Null
$zip=Join-Path $downloads 'stockfish-19-windows-x86-64-universal.zip'
$expected='3C8BF1F9EA66A09350A40DF4F632288285AC206D99F33AB5842C408FC30B48A7'
if(-not(Test-Path -LiteralPath $zip)){Invoke-WebRequest -Uri 'https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip' -OutFile $zip -TimeoutSec 180}
if((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash-ne$expected){throw 'Stockfish archive SHA256 mismatch; no engine was installed'}
$target=Join-Path $root 'stockfish'
if(Test-Path -LiteralPath $target){throw 'Existing Stockfish directory preserved. Inspect it before installing into a new directory.'}
Expand-Archive -LiteralPath $zip -DestinationPath $target
if(-not(Test-Path -LiteralPath $engine)){throw 'Expected engine path was not present in official archive'}
[pscustomobject]@{Path=$engine;Action='Installed official pinned archive';SHA256=(Get-FileHash -LiteralPath $engine -Algorithm SHA256).Hash}
