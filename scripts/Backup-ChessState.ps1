#requires -Version 7.0
[CmdletBinding()]
param([string]$Destination)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not$Destination){$Destination=Join-Path $root ('runtime\backups\'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))}
New-Item -ItemType Directory -Path $Destination -Force|Out-Null
$runtime=Join-Path $root 'runtime'
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'state_backup.py') backup --runtime $runtime --destination $Destination
if($LASTEXITCODE-ne0){throw 'Chess state backup failed'}
Write-Output $Destination
