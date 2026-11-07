<?php
namespace Chesselo5000\Component\Chesselo5000\Site\View\Dashboard;
defined('_JEXEC') or die;
final class HtmlView extends \Joomla\CMS\MVC\View\HtmlView {
    public function display($tpl=null):void{$this->getDocument()->setTitle('CHESS ELO 5000 · Chess laboratory');parent::display($tpl);}
}
