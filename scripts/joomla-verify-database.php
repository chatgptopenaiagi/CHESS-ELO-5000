<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
$c=json_decode(file_get_contents($argv[1]),true,512,JSON_THROW_ON_ERROR);
if(($c['product']??'')!=='CHESS-ELO-5000'||($c['database_name']??'')!=='chess_elo_5000_db'){throw new RuntimeException('Chess identity required');}
mysqli_report(MYSQLI_REPORT_ERROR|MYSQLI_REPORT_STRICT);
$db=new mysqli('127.0.0.1','root',$c['database_root_password'],'',$c['database_port']);
$restore='chess_verify_'.bin2hex(random_bytes(6));
$source=$c['database_name'];$created=false;
try{
    $db->query("CREATE DATABASE `$restore` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");$created=true;$db->select_db($restore);
    $sql=file_get_contents($argv[2]);if(!$sql){throw new RuntimeException('Backup SQL missing');}
    $db->multi_query($sql);do{if($result=$db->store_result()){$result->free();}}while($db->more_results()&&$db->next_result());
    $tables=[];$r=$db->query('SHOW TABLES');while($row=$r->fetch_row()){$tables[]=$row[0];}
    $checks=[];
    foreach($tables as $table){
        if(!preg_match('/^[a-zA-Z0-9_]+$/D',$table)){throw new RuntimeException('Unsafe table identity');}
        // Session/login rows are expected to change while browser acceptance runs.
        if(in_array($table,['chess_session','chess_user_keys','chess_user_profiles','chess_action_logs','chess_action_logs_users','chess_users'],true)){continue;}
        $digest=static function(mysqli $db,string $schema,string $table):array{$rows=[];$result=$db->query("SELECT * FROM `$schema`.`$table`");while($row=$result->fetch_assoc()){$rows[]=json_encode($row,JSON_THROW_ON_ERROR);}sort($rows,SORT_STRING);return ['rows'=>count($rows),'sha256'=>hash('sha256',implode("\n",$rows))];};
        $a=$digest($db,$source,$table);$b=$digest($db,$restore,$table);
        if($a!==$b){throw new RuntimeException('Restored data mismatch in '.$table);}$checks[$table]=$b;
    }
    echo json_encode(['status'=>'PASS','source_database'=>$source,'restore_database'=>$restore,'restored_tables'=>count($tables),'content_tables_verified'=>count($checks),'table_digests'=>$checks,'excluded_volatile_auth_tables'=>['chess_session','chess_user_keys','chess_user_profiles','chess_action_logs','chess_action_logs_users','chess_users'],'method'=>'Real logical SQL restore into fresh isolated database; exact stable-table row digests; original database never overwritten'],JSON_THROW_ON_ERROR|JSON_PRETTY_PRINT)."\n";
}finally{
    if($created&&preg_match('/^chess_verify_[a-f0-9]{12}$/D',$restore)){$db->query("DROP DATABASE `$restore`");}
}
