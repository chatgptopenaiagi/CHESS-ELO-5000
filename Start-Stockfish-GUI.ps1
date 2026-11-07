#requires -Version 7.0
<#
.SYNOPSIS
Launches the verified current-user En Croissant chess GUI.
.DESCRIPTION
Engine registration and UCI settings are saved by En Croissant itself.
This launcher checks both executable paths and reuses an existing GUI process.
.PARAMETER VerifyOnly
Checks paths and reports versions without opening a new GUI process.
#>
[CmdletBinding()]
param([switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
$gui = Join-Path $env:LOCALAPPDATA 'en-croissant\en-croissant.exe'
$engine = Join-Path $PSScriptRoot 'stockfish\stockfish\stockfish-windows-x86-64-universal.exe'
foreach ($path in @($gui,$engine)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required executable missing: $path" }
}
$running = @(Get-Process -Name 'en-croissant' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $gui })
if ($VerifyOnly) {
    [pscustomobject]@{ GuiPath=$gui; GuiVersion=(Get-Item -LiteralPath $gui).VersionInfo.ProductVersion; EnginePath=$engine; RunningProcessIds=@($running.Id); Status='Paths verified' }
    return
}
if ($running.Count -gt 0) {
    # Keep the existing application and its open boards/downloads intact.
    [pscustomobject]@{ GuiPath=$gui; ProcessId=$running[0].Id; Reused=$true; Status='En Croissant is already running' }
} else {
    # A visible window is intentional: this script is the user's GUI launcher.
    $started = Start-Process -FilePath $gui -WorkingDirectory $PSScriptRoot -PassThru
    [pscustomobject]@{ GuiPath=$gui; ProcessId=$started.Id; Reused=$false }
}
