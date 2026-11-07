#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$backup=& (Join-Path $PSScriptRoot 'Backup-JoomlaChess.ps1')
$result=& 'C:\xampp\php\php.exe' -c (Join-Path $root 'runtime\joomla\php.ini') (Join-Path $PSScriptRoot 'joomla-verify-database.php') (Join-Path $root 'runtime\private\joomla-access.json') $backup.file
if($LASTEXITCODE-ne0){throw 'Joomla database restore verification failed.'}
$receipt=$result|ConvertFrom-Json
$receipt|Add-Member -NotePropertyName backup_sha256 -NotePropertyValue $backup.sha256
$receipt|Add-Member -NotePropertyName checked_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o'))
$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $root 'evidence\joomla\database-restore-verification.json') -Encoding utf8
$receipt|Select-Object status,restored_tables,content_tables_verified,backup_sha256,method|ConvertTo-Json
