<?php
declare(strict_types=1);
// CLI only, independent chess database identity. Never prints credentials.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
$c=json_decode(file_get_contents($argv[1]),true,512,JSON_THROW_ON_ERROR);
if (($c['product']??'')!=='CHESS-ELO-5000') { throw new RuntimeException('Wrong product identity'); }
mysqli_report(MYSQLI_REPORT_ERROR|MYSQLI_REPORT_STRICT);
$db=new mysqli('127.0.0.1','root',$c['database_root_password'],'',$c['database_port']);
$name='chess_elo_5000_db'; $user='chess_elo_5000';
$existing=$db->query("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='chess_elo_5000_db'")->num_rows;
if ($existing && !is_file(dirname($argv[1]).'/joomla-db-owned.marker')) { throw new RuntimeException('Existing database has no chess ownership marker'); }
$db->query("CREATE DATABASE IF NOT EXISTS `$name` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
$password=$db->real_escape_string($c['database_password']);
$db->query("CREATE USER IF NOT EXISTS '$user'@'127.0.0.1' IDENTIFIED BY '$password'");
$db->query("GRANT ALL PRIVILEGES ON `$name`.* TO '$user'@'127.0.0.1'");
file_put_contents(dirname($argv[1]).'/joomla-db-owned.marker','CHESS-ELO-5000');
echo json_encode(['database'=>$name,'user'=>$user,'created'=>!$existing,'version'=>$db->server_info],JSON_THROW_ON_ERROR)."\n";
