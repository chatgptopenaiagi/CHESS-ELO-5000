<?php
namespace Chesselo5000\Component\Chesselo5000\Site\Controller;
defined('_JEXEC') or die;
final class DisplayController extends \Joomla\CMS\MVC\Controller\BaseController {
    protected $default_view='dashboard';
    public function display($cachable=false,$urlparams=[]){$this->app->setHeader('Cache-Control','private, no-store',true);$this->input->set('view','dashboard');return parent::display(false,$urlparams);}
}
