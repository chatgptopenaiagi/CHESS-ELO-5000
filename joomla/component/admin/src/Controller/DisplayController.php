<?php
namespace Chesselo5000\Component\Chesselo5000\Administrator\Controller;
defined('_JEXEC') or die;
final class DisplayController extends \Joomla\CMS\MVC\Controller\BaseController {
    protected $default_view='dashboard';
    public function display($cachable=false,$urlparams=[]){if(!$this->app->getIdentity()->authorise('core.manage','com_chesselo5000')){throw new \RuntimeException('Administrator access required',403);}$this->input->set('view','dashboard');return parent::display(false,$urlparams);}
}
