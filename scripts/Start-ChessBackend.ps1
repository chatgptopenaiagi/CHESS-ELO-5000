#requires -Version 7.0
[CmdletBinding()]
param([int]$Port=18961,[string]$RuntimeDirectory)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not $RuntimeDirectory){$RuntimeDirectory=Join-Path $root 'runtime'}
$RuntimeDirectory=[IO.Path]::GetFullPath($RuntimeDirectory)
New-Item -ItemType Directory -Path $RuntimeDirectory -Force|Out-Null
$private=Join-Path $RuntimeDirectory 'private'
New-Item -ItemType Directory -Path $private -Force|Out-Null
$cfgPath=Join-Path $private 'config.json'
if(-not(Test-Path -LiteralPath $cfgPath)){
    [ordered]@{schema_version='chesselo5000.local-config/1';backend_url="http://127.0.0.1:$Port";bridge_secret=[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant();owner_password=[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(24));joomla_url='http://127.0.0.1:18952'}|ConvertTo-Json|Set-Content -LiteralPath $cfgPath -Encoding utf8
}
$python=Join-Path $root '.venv\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $python)){& (Join-Path $PSScriptRoot 'Install-ChessDependencies.ps1');if(-not(Test-Path -LiteralPath $python)){throw 'Chess Python environment unavailable'}}
$venvConfig=Join-Path $root '.venv\pyvenv.cfg'
$basePython=if(Test-Path -LiteralPath $venvConfig){Get-Content -LiteralPath $venvConfig|Where-Object {$_-match'^executable = (.+)$'}|ForEach-Object {$Matches[1]}}else{$null}
$listener=Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue|Select-Object -First 1
if($listener){
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if($process.ExecutablePath -notin @($python,$basePython) -or $process.CommandLine -notlike "*$python*" -or $process.CommandLine -notlike '*-m chess_elo_5000*' -or $process.CommandLine -notlike "*$RuntimeDirectory*"){throw "Port $Port belongs to another application; choose another port and pair Joomla explicitly."}
    $status=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/system/status" -TimeoutSec 10
    if($status.product -ne 'CHESS ELO 5000'){throw 'Backend identity mismatch'}
    return [pscustomobject]@{Product=$status.product;Port=$Port;ProcessId=$listener.OwningProcess;Reused=$true;Url="http://127.0.0.1:$Port"}
}
$previousPath=$env:PYTHONPATH;$previousWorkspace=$env:CHESS_WORKSPACE
try{
    $env:PYTHONPATH=Join-Path $root 'src';$env:CHESS_WORKSPACE=$root
    $arguments=@('-m','chess_elo_5000','--host','127.0.0.1','--port',$Port,'--runtime',('"'+$RuntimeDirectory+'"'))
    $process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $RuntimeDirectory 'backend.stdout.log') -RedirectStandardError (Join-Path $RuntimeDirectory 'backend.stderr.log') -PassThru
}finally{$env:PYTHONPATH=$previousPath;$env:CHESS_WORKSPACE=$previousWorkspace}
$deadline=[DateTime]::UtcNow.AddSeconds(25)
do{
    Start-Sleep -Milliseconds 200
    if($process.HasExited){throw "Chess backend exited; inspect $RuntimeDirectory\backend.stderr.log"}
    try{$status=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/system/status" -TimeoutSec 1}catch{$status=$null}
}until($status -or [DateTime]::UtcNow-ge$deadline)
if(-not $status -or $status.product -ne 'CHESS ELO 5000'){throw 'Backend failed to become ready'}
$bound=Get-NetTCPConnection -State Listen -LocalPort $Port|Select-Object -First 1
[pscustomobject]@{Product=$status.product;Port=$Port;ProcessId=$bound.OwningProcess;LauncherProcessId=$process.Id;Reused=$false;Url="http://127.0.0.1:$Port"}|Tee-Object -Variable receipt
$receipt|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $RuntimeDirectory 'backend-process.json') -Encoding utf8
