#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ExtractedRoot,
    [ValidateRange(1024,65535)][int]$WebPort=18972,
    [ValidateRange(1024,65535)][int]$DatabasePort=18973,
    [switch]$LeaveRunning
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$resolved=[IO.Path]::GetFullPath($ExtractedRoot).TrimEnd('\')
if($resolved-eq$root -or -not$resolved.StartsWith((Join-Path $root 'runtime\'),[StringComparison]::OrdinalIgnoreCase)){throw 'Extracted acceptance must use an independent directory inside this product runtime.'}
foreach($name in @('Install-JoomlaChess.ps1','Build-JoomlaChessPackage.ps1','Start-JoomlaChess.ps1','Stop-JoomlaChess.ps1','Verify-JoomlaChess.ps1')){if(-not(Test-Path -LiteralPath (Join-Path $resolved "scripts\$name") -PathType Leaf)){throw "Extracted source is missing scripts/$name"}}
if(-not(Test-Path -LiteralPath (Join-Path $resolved 'runtime\private\config.json'))){throw 'Initialize the extracted backend and protected configuration before Joomla acceptance.'}
foreach($port in @($WebPort,$DatabasePort)){if(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue){throw "Extracted test port $port already has a listener."}}
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$evidence=Join-Path $root "evidence\joomla\extracted-$stamp"
$extractedEvidence=Join-Path $resolved 'evidence\joomla'
New-Item -ItemType Directory -Path $evidence,$extractedEvidence -Force|Out-Null
$protected=@(Get-CimInstance Win32_Process|Where-Object{$_.Name-in@('httpd.exe','mysqld.exe')}|Select-Object Name,ProcessId,ExecutablePath)
$protected|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $extractedEvidence 'protected-process-baseline.json') -Encoding utf8
$primaryConfigPath=Join-Path $root 'runtime\joomla\services.json'
$primary=Get-Content -LiteralPath $primaryConfigPath -Raw|ConvertFrom-Json
$primaryBefore=(Invoke-WebRequest -Uri ($primary.site_url+'/') -TimeoutSec 15).StatusCode
$checks=[Collections.Generic.List[object]]::new();$started=$false
function Check([string]$Name,[bool]$Pass,[object]$Details){$checks.Add([pscustomobject]@{name=$Name;status=$(if($Pass){'PASS'}else{'FAIL'});details=$Details});if(-not$Pass){throw "Extracted Joomla acceptance failed: $Name"}}
try{
    Write-Output 'Provisioning independent extracted Joomla site and database.'
    $site=Join-Path $resolved 'runtime\test-site'
    $install=& (Join-Path $resolved 'scripts\Install-JoomlaChess.ps1') -SitePath $site -WebPort $WebPort -DatabasePort $DatabasePort
    $started=$true
    $install|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $evidence 'installation.json') -Encoding utf8
    $artifact=& (Join-Path $resolved 'scripts\Build-JoomlaChessPackage.ps1') -OutputDirectory (Join-Path $resolved 'runtime\joomla\acceptance-dist')
    $config=Get-Content -LiteralPath (Join-Path $resolved 'runtime\joomla\services.json') -Raw|ConvertFrom-Json
    $output=& $config.php_exe -c $config.php_ini (Join-Path $site 'cli\joomla.php') extension:install "--path=$($artifact.file)" --no-interaction 2>&1
    $output|Set-Content -LiteralPath (Join-Path $evidence 'native-extension-install.log') -Encoding utf8
    Check 'Extracted native Joomla package installation' ($LASTEXITCODE-eq0-and($output-join' ')-notmatch'file does not exist|failed|could not') @{artifact_sha256=$artifact.sha256;site=$config.site_url}
    & (Join-Path $resolved 'scripts\Verify-JoomlaChess.ps1')|Out-Null
    $http=Get-Content -LiteralPath (Join-Path $extractedEvidence 'http-acceptance.json') -Raw|ConvertFrom-Json
    Copy-Item -LiteralPath (Join-Path $extractedEvidence 'http-acceptance.json') -Destination (Join-Path $evidence 'http-before-restart.json')
    Check 'Extracted real Joomla authentication and backend bridge' ($http.fail-eq0-and$http.not_run-eq0) @{passed_cases=$http.pass}
    Write-Output 'Stopping and restarting only extracted chess services.'
    & (Join-Path $resolved 'scripts\Stop-JoomlaChess.ps1')|Out-Null
    $deadline=[DateTime]::UtcNow.AddSeconds(15)
    do{Start-Sleep -Milliseconds 250;$listening=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object{$_.LocalPort-in@($WebPort,$DatabasePort)})}until($listening.Count-eq0-or[DateTime]::UtcNow-ge$deadline)
    Check 'Extracted services stop without touching primary' ($listening.Count-eq0-and(Invoke-WebRequest -Uri ($primary.site_url+'/') -TimeoutSec 15).StatusCode-eq200) @{ports=@($WebPort,$DatabasePort)}
    & (Join-Path $resolved 'scripts\Start-JoomlaChess.ps1')|Out-Null
    & (Join-Path $resolved 'scripts\Verify-JoomlaChess.ps1')|Out-Null
    $after=Get-Content -LiteralPath (Join-Path $extractedEvidence 'http-acceptance.json') -Raw|ConvertFrom-Json
    Copy-Item -LiteralPath (Join-Path $extractedEvidence 'http-acceptance.json') -Destination (Join-Path $evidence 'http-after-restart.json')
    Check 'Extracted Joomla and credentials survive full service restart' ($after.fail-eq0-and$after.not_run-eq0) @{passed_cases=$after.pass}
    $current=Get-CimInstance Win32_Process
    $missing=@($protected|Where-Object{[int]$_.ProcessId-notin$current.ProcessId})
    Check 'All preexisting Apache and MariaDB process identities preserved' ($missing.Count-eq0) @{protected_count=$protected.Count;missing_count=$missing.Count}
    Check 'Primary chess website remains responsive' ($primaryBefore-eq200-and(Invoke-WebRequest -Uri ($primary.site_url+'/') -TimeoutSec 15).StatusCode-eq200) @{primary_url=$primary.site_url}
}catch{
    $checks.Add([pscustomobject]@{name='Extracted acceptance execution';status='FAIL';details=$_.Exception.Message});throw
}finally{
    if($started-and-not$LeaveRunning){& (Join-Path $resolved 'scripts\Stop-JoomlaChess.ps1')|Out-Null}
    $receipt=[ordered]@{checked_utc=[DateTime]::UtcNow.ToString('o');extracted_root=$resolved;site_port=$WebPort;database_port=$DatabasePort;status=$(if(@($checks|Where-Object status -eq 'FAIL').Count-eq0){'PASS'}else{'FAIL'});checks=$checks;test_services_left_running=[bool]$LeaveRunning;scope='Actual source-extracted independent Joomla, MariaDB, native package, HTTP authentication/bridge and owned-process restart; existing primary remains unchanged'}
    $receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $evidence 'verification.json') -Encoding utf8
}
[pscustomobject]$receipt
