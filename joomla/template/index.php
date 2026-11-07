<?php
defined('_JEXEC') or die;
use Joomla\CMS\Factory;
use Joomla\CMS\Uri\Uri;
$component=Factory::getApplication()->input->getCmd('option','');
?><!doctype html><html lang="<?php echo $this->language;?>" dir="<?php echo $this->direction;?>" data-theme="dark"><head><meta name="viewport" content="width=device-width,initial-scale=1"><jdoc:include type="metas"/><jdoc:include type="styles"/><jdoc:include type="scripts"/><link rel="stylesheet" href="<?php echo Uri::root();?>templates/chesslab/css/template.css"></head><body><jdoc:include type="message"/><?php if($component!=='com_chesselo5000'):?><header class="ch-login-header"><a href="<?php echo Uri::root();?>index.php?option=com_chesselo5000">♟ CHESS ELO 5000</a><span>Independent chess laboratory</span></header><main class="ch-system-content"><?php endif;?><jdoc:include type="component"/><?php if($component!=='com_chesselo5000'):?></main><?php endif;?></body></html>
