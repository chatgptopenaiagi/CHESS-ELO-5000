#requires -Version 7.0
[CmdletBinding()]
param([switch]$ProbeEngine)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$result=[ordered]@{product='CHESS ELO 5000';checked_utc=[DateTime]::UtcNow.ToString('o');powershell=$PSVersionTable.PSVersion.ToString();tools=@();engine=$null}
$registry=Join-Path $env:USERPROFILE '.codex\machine-capabilities\software-capabilities.json'
if(Test-Path -LiteralPath $registry){
    $inv=Get-Content -LiteralPath $registry -Raw|ConvertFrom-Json
    $result.tools=@($inv.software|Where-Object { $_.name-match 'GitHub CLI|^Git$|^Node.js$|XAMPP|Python environment|Stockfish|Croissant|CMake|Ninja|CUDA|\.NET' }|ForEach-Object {[pscustomobject]@{name=$_.name;path=$_.executable_path;recorded_version=$_.version;recorded_status=$_.verification_status;recorded_date=$_.verification_date;exists=($_.executable_path-ne'UNKNOWN'-and(Test-Path -LiteralPath $_.executable_path -PathType Leaf));scope='Dated inventory plus current existence; no new workload inferred'}})
}
$engine=Join-Path $root 'stockfish\stockfish\stockfish-windows-x86-64-universal.exe'
$result.engine=@{path=$engine;exists=(Test-Path -LiteralPath $engine);status='DISCOVERED'}
if(Test-Path -LiteralPath $engine){$result.engine.sha256=(Get-FileHash -LiteralPath $engine -Algorithm SHA256).Hash}
if($ProbeEngine){$result.engine.probe=& (Join-Path $root 'Test-Stockfish-UCI.ps1') -Depth 10|ConvertFrom-Json;$result.engine.status=$result.engine.probe.status}
$result|ConvertTo-Json -Depth 12
