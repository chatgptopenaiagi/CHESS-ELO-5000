<?php
declare(strict_types=1);
namespace Chesselo5000\Component\Chesselo5000\Site\Controller;
defined('_JEXEC') or die;
use Joomla\CMS\Session\Session;
use Chesselo5000\Component\Chesselo5000\Administrator\Service\ApiClient;
class ApiController extends \Joomla\CMS\MVC\Controller\BaseController {
    public function proxy():void{
        $this->app->setHeader('Cache-Control','private, no-store',true);
        $method=strtoupper($_SERVER['REQUEST_METHOD']??'GET');$path=$this->input->getString('path','');$identity=$this->app->getIdentity();
        if(!in_array($method,['GET','POST','PUT','PATCH','DELETE'],true)||!preg_match('~^/api/v1/[a-zA-Z0-9_/?=&.,:%+\-]+$~D',$path)||str_contains($path,'..')||str_contains(strtolower($path),'%2e')||strlen($path)>2048){$this->respond(400,['error'=>'invalid_api_path']);return;}
        $route=(string)parse_url($path,PHP_URL_PATH);
        // Flask decodes URL path escapes before routing. Reject escaped route
        // delimiters here so an encoded /admin/ cannot bypass Joomla ACL.
        if(!preg_match('~^/api/v1/[a-zA-Z0-9_\-]+(?:/[a-zA-Z0-9_\-]+)*$~D',$route)){$this->respond(400,['error'=>'noncanonical_api_route_rejected']);return;}
        if($route==='/api/v1/session'){
            if($method!=='GET'){$this->respond(405,['error'=>'use_joomla_login']);return;}
            if($identity->guest){$this->respond(401,['error'=>'authentication_required']);return;}
            $this->respond(200,['user'=>['id'=>'joomla:'.$identity->id,'name'=>$identity->name,'username'=>$identity->username],'csrf_token'=>null]);return;
        }
        $public=['/api/v1/system/status','/api/v1/lessons','/api/v1/puzzles','/api/v1/learning/studies','/api/v1/engines'];
        if($identity->guest&&($method!=='GET'||!in_array($route,$public,true))){$this->respond(401,['error'=>'authentication_required']);return;}
        if($method!=='GET'&&!Session::checkToken('get')){$this->respond(403,['error'=>'invalid_csrf_token']);return;}
        if(str_starts_with($route,'/api/v1/admin/')&&!$identity->authorise('core.manage','com_chesselo5000')){$this->respond(403,['error'=>'administrator_permission_required']);return;}
        $body=$method==='GET'?'':file_get_contents('php://input');
        if(strlen($body)>1024*1024){$this->respond(413,['error'=>'request_too_large']);return;}
        try{$client=new ApiClient();$r=$client->request($method,$path,$body,$identity->guest?'public':(string)$identity->id);http_response_code($r['status']);header('Content-Type: '.$r['content_type']);header('Cache-Control: private, no-store');echo $r['body'];$this->app->close();}
        catch(\Throwable $e){$code=in_array($e->getMessage(),['CHESS_BRIDGE_NOT_CONFIGURED','CHESS_BRIDGE_INVALID_CONFIGURATION','CHESS_BACKEND_UNREACHABLE'],true)?$e->getMessage():'CHESS_BRIDGE_FAILED';$this->respond(503,['error'=>$code]);}
    }
    private function respond(int $status,array $value):void{http_response_code($status);header('Content-Type: application/json');header('Cache-Control: private, no-store');echo json_encode($value,JSON_THROW_ON_ERROR);$this->app->close();}
}
