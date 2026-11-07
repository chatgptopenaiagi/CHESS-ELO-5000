#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$BackupDirectory,[Parameter(Mandatory)][string]$DestinationRuntime)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
# Restore only into a new independent runtime, preserving active games and credentials.
if(Test-Path -LiteralPath $DestinationRuntime){throw 'Restore destination must not exist; existing state is never overwritten.'}
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'state_backup.py') restore --runtime $DestinationRuntime --destination $BackupDirectory
if($LASTEXITCODE-ne0){throw 'Chess state restore failed'}
