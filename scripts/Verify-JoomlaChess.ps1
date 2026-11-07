#requires -Version 7.0
[CmdletBinding()]
param([switch]$TestBackendWrites)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$config=Get-Content -LiteralPath (Join-Path $root 'runtime\joomla\services.json') -Raw|ConvertFrom-Json
$access=Get-Content -LiteralPath (Join-Path $root 'runtime\private\joomla-access.json') -Raw|ConvertFrom-Json
if($config.product-ne'CHESS-ELO-5000'-or$access.product-ne'CHESS-ELO-5000'){throw 'Wrong product identity.'}
$results=[Collections.Generic.List[object]]::new()
function Record([string]$Name,[bool]$Passed,[object]$Details){$results.Add([pscustomobject]@{name=$Name;status=$(if($Passed){'PASS'}else{'FAIL'});details=$Details});if(-not$Passed){throw "Joomla check failed: $Name"}}
function ProxyUrl([string]$Path,[bool]$Admin=$false,[string]$Token=''){
    $base=$config.site_url+$(if($Admin){'/administrator/index.php'}else{'/index.php'})
    $url=$base+'?option=com_chesselo5000&task=api.proxy&format=raw&path='+[Uri]::EscapeDataString('/api/v1'+$Path)
    if($Token){$url+='&'+$Token+'=1'}
    return $url
}
$session=[Microsoft.PowerShell.Commands.WebRequestSession]::new()
try{
    $frontendResponse=Invoke-WebRequest -Uri ($config.site_url+'/') -TimeoutSec 15
    Record 'Frontend renders installed chess client' ($frontendResponse.StatusCode-eq200-and$frontendResponse.Content-match'media/com_chesselo5000/app.js'-and$frontendResponse.Content-match'id="chessboard"') @{http_status=$frontendResponse.StatusCode;version='0.1.0-development'}
    foreach($item in @(@('/session',401),@('/games',401),@('/admin/settings',401))){
        $r=Invoke-WebRequest -Uri (ProxyUrl $item[0]) -SkipHttpErrorCheck -TimeoutSec 10
        Record ("Guest denied "+$item[0]) ($r.StatusCode-eq$item[1]) @{http_status=$r.StatusCode}
    }
    $bad=Invoke-WebRequest -Uri ($config.site_url+'/index.php?option=com_chesselo5000&task=api.proxy&format=raw&path='+[Uri]::EscapeDataString('/api/v1/../system/status')) -SkipHttpErrorCheck -TimeoutSec 10
    Record 'Traversal API path rejected' ($bad.StatusCode-eq400) @{http_status=$bad.StatusCode}
    $encoded=Invoke-WebRequest -Uri ($config.site_url+'/index.php?option=com_chesselo5000&task=api.proxy&format=raw&path='+[Uri]::EscapeDataString('/api/v1/admin%2Fsettings')) -SkipHttpErrorCheck -TimeoutSec 10
    Record 'Encoded administrator delimiter rejected before backend routing' ($encoded.StatusCode-eq400) @{http_status=$encoded.StatusCode}
    $dot=Invoke-WebRequest -Uri ($config.site_url+'/index.php?option=com_chesselo5000&task=api.proxy&format=raw&path='+[Uri]::EscapeDataString('/api/v1/./admin/settings')) -SkipHttpErrorCheck -TimeoutSec 10
    Record 'Dot-segment administrator bypass rejected before cURL normalization' ($dot.StatusCode-eq400) @{http_status=$dot.StatusCode}
    $login=Invoke-WebRequest -Uri ($config.site_url+'/administrator/') -WebSession $session -TimeoutSec 15
    $token=[regex]::Match($login.Content,'name="([a-f0-9]{32})"\s+value="1"').Groups[1].Value
    if(-not$token){throw 'Administrator login token missing'}
    $form=@{username=$access.admin_username;passwd=$access.admin_password;option='com_login';task='login';return='aW5kZXgucGhw'};$form[$token]='1'
    $signed=Invoke-WebRequest -Uri ($config.site_url+'/administrator/index.php') -WebSession $session -Method Post -Body $form -TimeoutSec 20
    $admin=Invoke-WebRequest -Uri ($config.site_url+'/administrator/index.php?option=com_chesselo5000') -WebSession $session -TimeoutSec 15
    Record 'Real Joomla administrator session and component' ($admin.StatusCode-eq200-and$admin.Content-match'Save a content revision') @{http_status=$admin.StatusCode;admin_username=$access.admin_username}
    $sessionInfo=Invoke-WebRequest -Uri (ProxyUrl '/session' $true) -WebSession $session -SkipHttpErrorCheck -TimeoutSec 15
    Record 'Joomla session is mapped to chess identity' ($sessionInfo.StatusCode-eq200-and(($sessionInfo.Content|ConvertFrom-Json).user.id-like'joomla:*')) @{http_status=$sessionInfo.StatusCode}
    $without=Invoke-WebRequest -Uri (ProxyUrl '/admin/settings' $true) -WebSession $session -Method Post -ContentType 'application/json' -Body '{}' -SkipHttpErrorCheck -TimeoutSec 10
    Record 'Authenticated mutation without CSRF rejected' ($without.StatusCode-eq403) @{http_status=$without.StatusCode}
    $wrong=Invoke-WebRequest -Uri (ProxyUrl '/admin/settings' $true '00000000000000000000000000000000') -WebSession $session -Method Post -ContentType 'application/json' -Body '{}' -SkipHttpErrorCheck -TimeoutSec 10
    Record 'Authenticated mutation with incorrect CSRF rejected' ($wrong.StatusCode-eq403) @{http_status=$wrong.StatusCode}
    $failedSession=[Microsoft.PowerShell.Commands.WebRequestSession]::new()
    $failedLogin=Invoke-WebRequest -Uri ($config.site_url+'/administrator/') -WebSession $failedSession -TimeoutSec 15
    $failedToken=[regex]::Match($failedLogin.Content,'name="([a-f0-9]{32})"\s+value="1"').Groups[1].Value
    $failedForm=@{username='chess-invalid-account';passwd='intentionally-invalid';option='com_login';task='login';return='aW5kZXgucGhw'};$failedForm[$failedToken]='1'
    $deniedLogin=Invoke-WebRequest -Uri ($config.site_url+'/administrator/index.php') -WebSession $failedSession -Method Post -Body $failedForm -SkipHttpErrorCheck -TimeoutSec 20
    $deniedAdmin=Invoke-WebRequest -Uri ($config.site_url+'/administrator/index.php?option=com_chesselo5000') -WebSession $failedSession -SkipHttpErrorCheck -TimeoutSec 15
    Record 'Invalid Joomla authentication cannot open chess administration' ($deniedAdmin.Content-match'id="mod-login-username"'-and$deniedAdmin.Content-notmatch'Save a content revision') @{http_status=$deniedAdmin.StatusCode}
    $status=Invoke-WebRequest -Uri (ProxyUrl '/system/status' $true) -WebSession $session -SkipHttpErrorCheck -TimeoutSec 40
    if($status.StatusCode-eq503){
        $results.Add([pscustomobject]@{name='Backend bridge';status='NOT_RUN';details=@{http_status=503;reason=($status.Content|ConvertFrom-Json).error}})
    }else{
        Record 'Real HMAC bridge backend status' ($status.StatusCode-eq200) @{http_status=$status.StatusCode}
        $backend=Get-Content -LiteralPath (Join-Path $root 'runtime\private\config.json') -Raw|ConvertFrom-Json
        $badPair=Invoke-WebRequest -Uri ($backend.backend_url+'/api/v1/games') -Headers @{'X-Chess-User'='invalid-pairing-test';'X-Chess-Time'=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString();'X-Chess-Nonce'=[Guid]::NewGuid().ToString('N');'X-Chess-Signature'=('0'*64)} -SkipHttpErrorCheck -TimeoutSec 15
        Record 'Invalid backend bridge pairing is rejected' ($badPair.StatusCode-eq401) @{http_status=$badPair.StatusCode}
        foreach($path in @('/engines','/admin/content/lessons','/admin/content/puzzles','/admin/content/studies','/admin/settings','/admin/jobs')){
            $r=Invoke-WebRequest -Uri (ProxyUrl $path $true) -WebSession $session -SkipHttpErrorCheck -TimeoutSec 40
            Record ("Administrator reads "+$path) ($r.StatusCode-eq200) @{http_status=$r.StatusCode}
        }
        if($TestBackendWrites){
            $token=[regex]::Match($admin.Content,'token="([a-f0-9]{32})"').Groups[1].Value
            if(-not$token){throw 'Administrator component token missing'}
            $stamp=[DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
            $baseFen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
            foreach($collection in @('lessons','puzzles','studies')){
                $item=@{id="joomla-acceptance-$collection-$stamp";title="Joomla verified $collection";fen=$baseFen;level='BEGINNER';category='practice';kind='opening';body='Independent Joomla content acceptance.';objective='Play the legal e-pawn move.';moves=@('e2e4');solution=@('e2e4')}
                $r=Invoke-WebRequest -Uri (ProxyUrl "/admin/content/$collection" $true $token) -WebSession $session -Method Post -ContentType 'application/json' -Body ($item|ConvertTo-Json -Compress) -SkipHttpErrorCheck -TimeoutSec 40
                Record ("Administrator persists $collection revision") ($r.StatusCode-in200,201) @{http_status=$r.StatusCode;item_id=$item.id}
            }
        }
    }
    $before=Get-Content -LiteralPath (Join-Path $root 'evidence\joomla\protected-process-baseline.json') -Raw|ConvertFrom-Json
    $current=Get-CimInstance Win32_Process
    $missing=@($before|Where-Object{[int]$_.ProcessId-notin$current.ProcessId})
    Record 'Protected existing web/database process identities preserved' ($missing.Count-eq0) @{protected_process_count=@($before).Count;missing_count=$missing.Count}
}catch{
    $results.Add([pscustomobject]@{name='Verification execution';status='FAIL';details=$_.Exception.Message})
    throw
}finally{
    $receipt=[ordered]@{checked_utc=[DateTime]::UtcNow.ToString('o');product='CHESS-ELO-5000';site=$config.site_url;cases=$results;pass=@($results|Where-Object status -eq 'PASS').Count;fail=@($results|Where-Object status -eq 'FAIL').Count;not_run=@($results|Where-Object status -eq 'NOT_RUN').Count;scope='Real HTTP/Joomla sessions and supported installed component; browser visual acceptance is separate.'}
    $receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $root 'evidence\joomla\http-acceptance.json') -Encoding utf8
    $receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $root ('evidence\joomla\http-acceptance-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'.json')) -Encoding utf8
}
[pscustomobject]$receipt|Select-Object checked_utc,site,pass,fail,not_run|ConvertTo-Json
