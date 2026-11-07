#requires -Version 7.0
[CmdletBinding()]
param([string]$OutputDirectory)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not$OutputDirectory){$OutputDirectory=Join-Path $root 'dist\v0.1.0-dev.1-chess-elo-5000'}
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'build_release.py') --output $OutputDirectory
if($LASTEXITCODE-ne0){throw 'Release build failed'}
