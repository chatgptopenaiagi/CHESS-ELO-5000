<?php
defined('_JEXEC') or die;
use Joomla\CMS\Factory;
use Joomla\CMS\Table\Menu;
use Joomla\Database\DatabaseInterface;
class pkg_chesselo5000InstallerScript {
    public function preflight($type,$parent):bool{if(\Joomla\CMS\Version::MAJOR_VERSION<6){throw new RuntimeException('CHESS ELO 5000 requires Joomla 6 or later.');}return true;}
    public function postflight($type,$parent):void{
        if($type==='uninstall'){return;}
        $db=Factory::getContainer()->get(DatabaseInterface::class);
        $extension=(int)$db->setQuery($db->getQuery(true)->select('extension_id')->from('#__extensions')->where("element='com_chesselo5000' AND type='component'"))->loadResult();
        if(!$extension){throw new RuntimeException('Chess component installation not found.');}
        $found=(int)$db->setQuery($db->getQuery(true)->select('id')->from('#__menu')->where("link='index.php?option=com_chesselo5000' AND client_id=0"))->loadResult();
        if(!$found){
            $db->setQuery("UPDATE #__menu SET home=0 WHERE client_id=0 AND language='*'")->execute();
            $menu=new Menu($db);$menu->setLocation(1,'last-child');
            $menu->bind(['menutype'=>'mainmenu','title'=>'Play Chess','alias'=>'chess-laboratory','path'=>'chess-laboratory','link'=>'index.php?option=com_chesselo5000','type'=>'component','published'=>1,'parent_id'=>1,'component_id'=>$extension,'access'=>1,'home'=>1,'language'=>'*','client_id'=>0,'params'=>'{}']);
            if(!$menu->check()||!$menu->store()){throw new RuntimeException('Chess home menu creation failed.');}
        }
        $template=(int)$db->setQuery("SELECT id FROM #__template_styles WHERE template='chesslab' AND client_id=0")->loadResult();
        if($template){$db->setQuery("UPDATE #__template_styles SET home='0' WHERE client_id=0")->execute();$db->setQuery("UPDATE #__template_styles SET home='1' WHERE id=".$template)->execute();}
        Factory::getApplication()->enqueueMessage('CHESS ELO 5000 installed. Configure the protected backend connection and sign in to play.');
    }
}
