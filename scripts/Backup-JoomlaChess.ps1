#requires -Version 7.0
[CmdletBinding()]
param([string]$OutputDirectory)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not$OutputDirectory){$OutputDirectory=Join-Path $root 'runtime\private\joomla-backups'}
$access=Get-Content -LiteralPath (Join-Path $root 'runtime\private\joomla-access.json') -Raw|ConvertFrom-Json
if($access.product-ne'CHESS-ELO-5000'-or$access.database_name-ne'chess_elo_5000_db'){throw 'Independent chess database identity required.'}
New-Item -ItemType Directory -Path $OutputDirectory -Force|Out-Null
$output=Join-Path $OutputDirectory ('joomla-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'.sql')
$psi=[Diagnostics.ProcessStartInfo]::new('C:\xampp\mysql\bin\mysqldump.exe');$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardError=$true
$psi.Environment['MYSQL_PWD']=$access.database_password
foreach($a in @('--host=127.0.0.1',"--port=$($access.database_port)","--user=$($access.database_user)",'--single-transaction','--skip-lock-tables','--skip-add-drop-table','--skip-comments','--default-character-set=utf8mb4',"--result-file=$output",$access.database_name)){$psi.ArgumentList.Add($a)}
$p=[Diagnostics.Process]::Start($psi);$errors=$p.StandardError.ReadToEndAsync()
if(-not$p.WaitForExit(60000)){$p.Kill();throw 'Chess Joomla backup deadline exceeded.'}
if($p.ExitCode-ne0){throw ('Chess Joomla backup failed: '+$errors.Result.Replace($access.database_password,'[redacted]'))}
$receipt=[ordered]@{product='CHESS-ELO-5000';created_utc=[DateTime]::UtcNow.ToString('o');database=$access.database_name;file=$output;bytes=(Get-Item -LiteralPath $output).Length;sha256=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash;method='MariaDB single-transaction logical snapshot; private credentials remain outside artifacts'}
$receipt|ConvertTo-Json|Set-Content -LiteralPath ($output+'.json') -Encoding utf8
[pscustomobject]$receipt
