<?php
namespace Chesselo5000\Component\Chesselo5000\Administrator\View\Dashboard;
defined('_JEXEC') or die;
final class HtmlView extends \Joomla\CMS\MVC\View\HtmlView {
    public function display($tpl=null):void{\Joomla\CMS\Toolbar\ToolbarHelper::title('CHESS ELO 5000 · Administration','chess');\Joomla\CMS\Toolbar\ToolbarHelper::preferences('com_chesselo5000');parent::display($tpl);}
}
