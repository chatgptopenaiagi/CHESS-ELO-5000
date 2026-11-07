#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$JoomlaArchive='',
    [string]$SitePath='C:\xampp\htdocs\chess-elo-5000',
    [int]$WebPort=18952,
    [int]$DatabasePort=18953
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$state=Join-Path $root 'runtime\joomla'
$private=Join-Path $root 'runtime\private'
$php='C:\xampp\php\php.exe'; $mysql='C:\xampp\mysql\bin\mysqld.exe'; $apache='C:\xampp\apache\bin\httpd.exe'
foreach($p in @($php,$mysql,$apache,'C:\xampp\mysql\bin\mariadb-install-db.exe')){if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "Required existing XAMPP executable unavailable: $p"}}
foreach($port in @($WebPort,$DatabasePort)){if($port-in(18740..18751)){throw 'Protected DRAGONHYDRA port excluded.'}}
New-Item -ItemType Directory -Path $state,$private,(Join-Path $state 'sessions'),(Join-Path $state 'tmp'),(Join-Path $state 'logs') -Force|Out-Null
$accessPath=Join-Path $private 'joomla-access.json'
if((Test-Path -LiteralPath (Join-Path $SitePath 'configuration.php')) -and -not(Test-Path -LiteralPath (Join-Path $private 'joomla-site-owned.marker'))){throw 'Existing target site has no CHESS-ELO-5000 ownership marker; inspect before reconfiguration.'}
if(Test-Path -LiteralPath $accessPath){$access=Get-Content -LiteralPath $accessPath -Raw|ConvertFrom-Json}else{
    function New-Secret { [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24)) }
    $access=[pscustomobject]@{product='CHESS-ELO-5000';site_url="http://127.0.0.1:$WebPort";administrator_url="http://127.0.0.1:$WebPort/administrator/";admin_username='chess-owner';admin_password=(New-Secret);database_name='chess_elo_5000_db';database_user='chess_elo_5000';database_password=(New-Secret);database_root_password=(New-Secret);database_port=$DatabasePort}
    $access|ConvertTo-Json|Set-Content -LiteralPath $accessPath -Encoding utf8
}
if($access.product-ne'CHESS-ELO-5000' -or $access.database_port-ne$DatabasePort){throw 'Existing private installation identity mismatch.'}
$data=Join-Path $state 'mariadb-data'
if(-not(Test-Path -LiteralPath (Join-Path $data 'mysql'))){
    $psi=[Diagnostics.ProcessStartInfo]::new('C:\xampp\mysql\bin\mariadb-install-db.exe');$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    foreach($a in @("--datadir=$data","--port=$DatabasePort","--password=$($access.database_root_password)",'--silent')){$psi.ArgumentList.Add($a)}
    $p=[Diagnostics.Process]::Start($psi);$stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync()
    if(-not$p.WaitForExit(120000)){$p.Kill();throw 'Chess MariaDB initialization deadline exceeded.'}
    if($p.ExitCode-ne0){throw ('Chess MariaDB initialization failed: '+$stderr.Result.Replace($access.database_root_password,'[redacted]'))}
}
$norm={param($p) $p.Replace('\','/')}
$dataWeb=&$norm $data; $stateWeb=&$norm $state; $siteWeb=&$norm $SitePath
$mysqlConfig=Join-Path $state 'my.ini'
@"
[mysqld]
basedir=C:/xampp/mysql
datadir=$dataWeb
port=$DatabasePort
bind-address=127.0.0.1
skip-name-resolve
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
max_allowed_packet=32M
innodb_buffer_pool_size=64M
pid-file=$stateWeb/mariadb.pid
log-error=$stateWeb/logs/mariadb.log
[client]
port=$DatabasePort
host=127.0.0.1
"@|Set-Content -LiteralPath $mysqlConfig -Encoding utf8
$ini=Get-Content -LiteralPath 'C:\xampp\php\php.ini' -Raw
$ini=$ini.Replace(';extension=zip','extension=zip').Replace('session.save_path="C:\xampp\tmp"',"session.save_path=`"$stateWeb/sessions`"").Replace('error_log="C:\xampp\php\logs\php_error_log"',"error_log=`"$stateWeb/logs/php_error.log`"")
$phpIni=Join-Path $state 'php.ini'; $ini|Set-Content -LiteralPath $phpIni -Encoding utf8
$apacheConfig=Join-Path $state 'httpd.conf'
@"
ServerRoot "C:/xampp/apache"
Listen 127.0.0.1:$WebPort
ServerName 127.0.0.1:$WebPort
PidFile "$stateWeb/apache.pid"
LoadModule authz_core_module modules/mod_authz_core.so
LoadModule authz_host_module modules/mod_authz_host.so
LoadModule dir_module modules/mod_dir.so
LoadModule mime_module modules/mod_mime.so
LoadModule log_config_module modules/mod_log_config.so
LoadModule alias_module modules/mod_alias.so
LoadModule env_module modules/mod_env.so
LoadModule headers_module modules/mod_headers.so
LoadModule rewrite_module modules/mod_rewrite.so
LoadModule setenvif_module modules/mod_setenvif.so
SetEnv CHESS_PRODUCT_CONFIG "$((&$norm (Join-Path $private 'config.json')))"
LoadFile "C:/xampp/php/php8ts.dll"
LoadFile "C:/xampp/php/libpq.dll"
LoadFile "C:/xampp/php/libsqlite3.dll"
LoadModule php_module "C:/xampp/php/php8apache2_4.dll"
PHPIniDir "$stateWeb"
DocumentRoot "$siteWeb"
<Directory "$siteWeb">
    Options -Indexes +FollowSymLinks
    AllowOverride All
    Require local
</Directory>
<FilesMatch "\.php$">
    SetHandler application/x-httpd-php
</FilesMatch>
DirectoryIndex index.php
TypesConfig "C:/xampp/apache/conf/mime.types"
ErrorLog "$stateWeb/logs/apache-error.log"
CustomLog "$stateWeb/logs/apache-access.log" common
Timeout 30
"@|Set-Content -LiteralPath $apacheConfig -Encoding utf8
$services=[ordered]@{product='CHESS-ELO-5000';site_path=$SitePath;site_url="http://127.0.0.1:$WebPort";web_port=$WebPort;database_port=$DatabasePort;mysql_exe=$mysql;mysql_config=$mysqlConfig;apache_exe=$apache;apache_config=$apacheConfig;php_exe=$php;php_ini=$phpIni}
$services|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $state 'services.json') -Encoding utf8
if(-not(Test-Path -LiteralPath (Join-Path $SitePath 'index.php'))){
    if(Test-Path -LiteralPath $SitePath){throw 'Target exists without expected Joomla source. Inspect it before extracting.'}
    if(-not$JoomlaArchive){
        $existing=Join-Path $env:USERPROFILE 'Downloads\Joomla_6.2.0-Stable-Full_Package.zip'
        if(Test-Path -LiteralPath $existing){$JoomlaArchive=$existing}else{
            $downloads=Join-Path $root 'runtime\downloads';New-Item -ItemType Directory -Path $downloads -Force|Out-Null
            $JoomlaArchive=Join-Path $downloads 'Joomla_6.2.0-Stable-Full_Package.zip'
            if(-not(Test-Path -LiteralPath $JoomlaArchive)){Invoke-WebRequest -Uri 'https://github.com/joomla/joomla-cms/releases/download/6.2.0/Joomla_6.2.0-Stable-Full_Package.zip' -OutFile $JoomlaArchive -TimeoutSec 120}
        }
    }
    $expected='67A107C83B3084701A1A4ACB151CD0452E5DEAAF'
    if((Get-FileHash -LiteralPath $JoomlaArchive -Algorithm SHA1).Hash-ne$expected){throw 'Joomla package official SHA1 mismatch.'}
    if((Get-FileHash -LiteralPath $JoomlaArchive -Algorithm SHA256).Hash-ne'EAAFC68B5990D7B9DD9156656D4C3C3547743D1D7A85682A92E2F9121B58F018'){throw 'Joomla package pinned SHA256 mismatch.'}
    Expand-Archive -LiteralPath $JoomlaArchive -DestinationPath $SitePath
}
& $apache -t -f $apacheConfig
if($LASTEXITCODE-ne0){throw 'Chess Apache configuration failed validation.'}
& (Join-Path $PSScriptRoot 'Start-JoomlaChess.ps1')|Out-Null
& $php -c $phpIni (Join-Path $PSScriptRoot 'joomla-provision-db.php') $accessPath
if($LASTEXITCODE-ne0){throw 'Independent chess database provisioning failed.'}
if(-not(Test-Path -LiteralPath (Join-Path $SitePath 'configuration.php'))){
    $psi=[Diagnostics.ProcessStartInfo]::new($php);$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true;$psi.WorkingDirectory=$SitePath
    foreach($a in @('-c',$phpIni,(Join-Path $SitePath 'installation\joomla.php'),'install','--no-interaction','--site-name=CHESS ELO 5000','--admin-user=Chess Owner',"--admin-username=$($access.admin_username)","--admin-password=$($access.admin_password)",'--admin-email=chess-owner@localhost.example','--db-type=mysqli',"--db-host=127.0.0.1:$DatabasePort","--db-user=$($access.database_user)","--db-pass=$($access.database_password)","--db-name=$($access.database_name)",'--db-prefix=chess_')){$psi.ArgumentList.Add($a)}
    $p=[Diagnostics.Process]::Start($psi);$stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync()
    if(-not$p.WaitForExit(120000)){$p.Kill();throw 'Joomla installation deadline exceeded.'}
    $output=($stdout.Result+"`n"+$stderr.Result).Replace($access.admin_password,'[redacted]').Replace($access.database_password,'[redacted]')
    $output|Set-Content -LiteralPath (Join-Path $root 'evidence\joomla\installation-cli.log') -Encoding utf8
    if($p.ExitCode-ne0){throw 'Joomla CLI installation failed. Read the redacted installation log.'}
}
'CHESS-ELO-5000'|Set-Content -LiteralPath (Join-Path $private 'joomla-site-owned.marker') -Encoding ascii
[pscustomobject]@{product='CHESS-ELO-5000';site_url=$services.site_url;admin_url=$access.administrator_url;database=$access.database_name;access_file=$accessPath;existing_sites_modified=$false}
