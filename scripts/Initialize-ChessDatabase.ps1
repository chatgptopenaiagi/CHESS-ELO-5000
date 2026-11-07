#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$previous=$env:PYTHONPATH
try{
    $env:PYTHONPATH=Join-Path $root 'src'
    & (Join-Path $root '.venv\Scripts\python.exe') -c 'import sys; from chess_elo_5000 import create_app; a=create_app(sys.argv[1]); a.extensions["research_lab"].shutdown(); a.extensions["chess_service"].close(); print("Independent chess databases initialized")' (Join-Path $root 'runtime')
    if($LASTEXITCODE-ne0){throw 'Database initialization failed'}
}finally{$env:PYTHONPATH=$previous}
