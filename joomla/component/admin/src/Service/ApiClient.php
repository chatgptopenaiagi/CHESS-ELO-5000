<?php
declare(strict_types=1);
namespace Chesselo5000\Component\Chesselo5000\Administrator\Service;
defined('_JEXEC') or die;
use Joomla\CMS\Component\ComponentHelper;
final class ApiClient {
    private string $base; private string $secret;
    public function __construct(){
        $path=(string)ComponentHelper::getParams('com_chesselo5000')->get('private_config','');
        if($path===''){$path=(string)getenv('CHESS_PRODUCT_CONFIG');}
        $real=realpath($path);$public=realpath(JPATH_ROOT);
        if(!$real||!is_file($real)||str_starts_with(strtolower(str_replace('\\','/',$real)),strtolower(str_replace('\\','/',$public)).'/')){throw new \RuntimeException('CHESS_BRIDGE_NOT_CONFIGURED');}
        $config=json_decode(file_get_contents($real),true,64,JSON_THROW_ON_ERROR);
        $this->base=rtrim((string)($config['backend_url']??''),'/');$this->secret=(string)($config['bridge_secret']??'');
        if(!preg_match('~^http://127\.0\.0\.1:[1-9][0-9]{1,4}$~D',$this->base)||strlen($this->secret)<32){throw new \RuntimeException('CHESS_BRIDGE_INVALID_CONFIGURATION');}
    }
    public function request(string $method,string $path,string $body,string $user):array{
        $time=(string)time();$nonce=bin2hex(random_bytes(16));
        $signedPath=(string)parse_url($path,PHP_URL_PATH);
        $signature=hash_hmac('sha256',implode("\n",[$time,$nonce,$user,$method,$signedPath,hash('sha256',$body)]),$this->secret);
        $response='';$contentType='application/json';$curl=curl_init($this->base.$path);
        curl_setopt_array($curl,[CURLOPT_CUSTOMREQUEST=>$method,CURLOPT_HTTPHEADER=>[
            'Content-Type: application/json','X-Chess-User: '.$user,'X-Chess-Time: '.$time,'X-Chess-Nonce: '.$nonce,'X-Chess-Signature: '.$signature,
        ],CURLOPT_CONNECTTIMEOUT=>3,CURLOPT_TIMEOUT=>35,CURLOPT_FOLLOWLOCATION=>false,CURLOPT_MAXREDIRS=>0,CURLOPT_PROXY=>'',
        CURLOPT_HEADERFUNCTION=>static function($h,string $header)use(&$contentType):int{if(stripos($header,'Content-Type:')===0){$contentType=trim(substr($header,13));}return strlen($header);},
        CURLOPT_WRITEFUNCTION=>static function($h,string $part)use(&$response):int{if(strlen($response)+strlen($part)>4*1024*1024){return 0;}$response.=$part;return strlen($part);}]);
        if($method!=='GET'&&$method!=='HEAD'){curl_setopt($curl,CURLOPT_POSTFIELDS,$body);}
        $ok=curl_exec($curl);$status=(int)curl_getinfo($curl,CURLINFO_RESPONSE_CODE);curl_close($curl);
        if($ok===false){throw new \RuntimeException('CHESS_BACKEND_UNREACHABLE');}
        return ['status'=>$status,'body'=>$response,'content_type'=>$contentType];
    }
}
