#requires -Version 7.0
[CmdletBinding()]
param([switch]$Live)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$required=@('src\chess_elo_5000\api.py','client\web\index.html','client\web\app.js','client\web\style.css','.venv\Scripts\python.exe')
foreach($relative in $required){if(-not(Test-Path -LiteralPath (Join-Path $root $relative))){throw "Required file missing: $relative"}}
$previous=$env:PYTHONPATH
try{
    $env:PYTHONPATH=Join-Path $root 'src'
    & (Join-Path $root '.venv\Scripts\python.exe') -c 'import chess, flask; from chess_elo_5000.research.content import lessons,puzzles,studies; assert len(list(chess.Board().legal_moves))==20; print("Rules and content imports PASS",len(lessons()),len(puzzles()),len(studies()))'
    if($LASTEXITCODE-ne0){throw 'Product import verification failed'}
}finally{$env:PYTHONPATH=$previous}
if($Live){
    $status=Invoke-RestMethod -Uri 'http://127.0.0.1:18961/api/v1/system/status' -TimeoutSec 10
    if($status.product-ne'CHESS ELO 5000'){throw 'Unexpected backend identity'}
    $page=Invoke-WebRequest -Uri 'http://127.0.0.1:18952/' -TimeoutSec 10
    if($page.Content-notmatch'CHESS ELO 5000'){throw 'Unexpected Joomla product page'}
}
[pscustomobject]@{Product='CHESS ELO 5000';Status='PASS';LiveChecked=[bool]$Live}
