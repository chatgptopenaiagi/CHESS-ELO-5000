#requires -Version 7.0
[CmdletBinding()]
param([string]$RuntimeDirectory)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not $RuntimeDirectory){$RuntimeDirectory=Join-Path $root 'runtime'}
$marker=Join-Path $RuntimeDirectory 'backend-process.json'
if(-not(Test-Path -LiteralPath $marker)){return}
$receipt=Get-Content -LiteralPath $marker -Raw|ConvertFrom-Json
$listener=Get-NetTCPConnection -State Listen -LocalPort $receipt.Port -ErrorAction SilentlyContinue|Select-Object -First 1
$targetProcessId=if($listener){$listener.OwningProcess}else{$receipt.ProcessId}
$process=Get-CimInstance Win32_Process -Filter "ProcessId=$targetProcessId"
if($process){
    $python=Join-Path $root '.venv\Scripts\python.exe'
    $venvConfig=Join-Path $root '.venv\pyvenv.cfg'
    $basePython=if(Test-Path -LiteralPath $venvConfig){Get-Content -LiteralPath $venvConfig|Where-Object {$_-match'^executable = (.+)$'}|ForEach-Object {$Matches[1]}}else{$null}
    if($process.ExecutablePath -notin @($python,$basePython) -or $process.CommandLine -notlike "*$python*" -or $process.CommandLine -notlike '*-m chess_elo_5000*' -or $process.CommandLine -notlike "*$RuntimeDirectory*"){throw 'Owned backend process identity changed; refusing to stop it.'}
    Stop-Process -Id $process.ProcessId
}
[pscustomobject]@{Product='CHESS ELO 5000';Status='Stopped';ProcessId=$targetProcessId}
