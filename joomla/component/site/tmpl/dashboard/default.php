<?php
defined('_JEXEC') or die;
use Joomla\CMS\Factory;
use Joomla\CMS\Session\Session;
use Joomla\CMS\Uri\Uri;
$root=rtrim(Uri::root(),'/');$component=$root.'/index.php?option=com_chesselo5000';
$config=['joomla'=>true,'proxy'=>true,'apiBase'=>$root.'/index.php?option=com_chesselo5000&task=api.proxy&format=raw&path=','csrfParam'=>Session::getFormToken(),'loginUrl'=>$root.'/index.php?option=com_users&view=login&return='.urlencode(base64_encode($component)),'defaultView'=>Factory::getApplication()->input->getCmd('section','play')];
$index=JPATH_ROOT.'/media/com_chesselo5000/index.html';
if(!is_file($index)){echo '<h1>CHESS ELO 5000</h1><p>Install the complete chess package with its web client assets.</p>';return;}
$html=file_get_contents($index);preg_match('~<body[^>]*>(.*)</body>~is',$html,$match);$body=$match[1]??$html;
$body=preg_replace('~<script\b[^>]*>.*?</script>~is','',$body);
$this->getDocument()->addStyleSheet($root.'/media/com_chesselo5000/style.css');
echo $body;
echo '<script>window.CHESS_CONFIG='.json_encode($config,JSON_HEX_TAG|JSON_HEX_AMP|JSON_HEX_APOS|JSON_HEX_QUOT|JSON_THROW_ON_ERROR).';</script>';
echo '<script src="'.htmlspecialchars($root.'/media/com_chesselo5000/app.js',ENT_QUOTES).'" defer></script>';
