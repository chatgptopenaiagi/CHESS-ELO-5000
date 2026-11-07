#requires -Version 7.0
<# .SYNOPSIS Starts the independent chess backend and Joomla website. #>
[CmdletBinding()]
param([switch]$Standalone,[switch]$NoBrowser,[switch]$VerifyOnly,[int]$BackendPort=0)
$ErrorActionPreference='Stop'
if($VerifyOnly){& (Join-Path $PSScriptRoot 'scripts\Verify-ChessInstallation.ps1');return}
if(-not(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'stockfish\stockfish\stockfish-windows-x86-64-universal.exe'))){
    try{& (Join-Path $PSScriptRoot 'scripts\Install-ChessEngine.ps1')|Out-Null}catch{Write-Warning ('Local engine setup did not complete; human play and study remain available. '+$_.Exception.Message)}
}
$localConfig=Join-Path $PSScriptRoot 'runtime\private\config.json'
if($BackendPort-eq0){
    if(Test-Path -LiteralPath $localConfig){$savedConfig=Get-Content -LiteralPath $localConfig -Raw|ConvertFrom-Json;$BackendPort=([Uri]$savedConfig.backend_url).Port}
    if($BackendPort-lt1024){$BackendPort=18961}
}
$backend=& (Join-Path $PSScriptRoot 'scripts\Start-ChessBackend.ps1') -Port $BackendPort
if($Standalone){$url=$backend.Url}else{
    if(-not(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'runtime\joomla\services.json'))){& (Join-Path $PSScriptRoot 'scripts\Install-JoomlaChess.ps1')}
    $website=& (Join-Path $PSScriptRoot 'scripts\Start-JoomlaChess.ps1')
    $url=$website.url
}
if(-not$NoBrowser){Start-Process $url}
[pscustomobject]@{Product='CHESS ELO 5000';Url=$url;Backend=$backend;Credentials='runtime\private\joomla-access.json (Joomla) or runtime\private\config.json (standalone)'}
