<?php
defined('_JEXEC') or die;
use Joomla\CMS\Dispatcher\ComponentDispatcherFactoryInterface;
use Joomla\CMS\Extension\ComponentInterface;
use Joomla\CMS\Extension\Service\Provider\ComponentDispatcherFactory;
use Joomla\CMS\Extension\Service\Provider\MVCFactory;
use Joomla\CMS\MVC\Factory\MVCFactoryInterface;
use Joomla\DI\Container;
use Joomla\DI\ServiceProviderInterface;
use Chesselo5000\Component\Chesselo5000\Administrator\Extension\Chesselo5000Component;
return new class implements ServiceProviderInterface {
    public function register(Container $container): void {
        $container->registerServiceProvider(new MVCFactory('\\Chesselo5000\\Component\\Chesselo5000'));
        $container->registerServiceProvider(new ComponentDispatcherFactory('\\Chesselo5000\\Component\\Chesselo5000'));
        $container->set(ComponentInterface::class,static function(Container $c){
            $component=new Chesselo5000Component($c->get(ComponentDispatcherFactoryInterface::class));
            $component->setMVCFactory($c->get(MVCFactoryInterface::class)); return $component;
        });
    }
};
