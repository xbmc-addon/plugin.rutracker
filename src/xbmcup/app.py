# -*- coding: utf-8 -*-

import sys
import os
import urllib
import json

import xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs

MODE = {
    'list':  50,
    'full':  51,
    'icon':  54,
    'round': 501,
    'thumb': 500
}


class Link:
    def __init__(self, route, argv=None, container=False, container_replace=False):
        app = {'route': route}
        if argv is not None:
            app['argv'] = argv
        if container:
            app['container'] = container
        if container_replace:
            app['container_replace'] = container_replace
        self.url = sys.argv[0] + '?' + urllib.quote_plus(json.dumps(app))


class Handler:
    def __init__(self, gsetting, link, argv=None):
        self.argv = argv
        self.link = link
        self.plugin = sys.argv[0].replace('plugin://', '').replace('/', '')
        self.addon = xbmcaddon.Addon(id=self.plugin)
        self.setting = Setting()
        self.lang = Lang()
        self.is_listitem = False
        self.is_render = False
        self._gsetting = gsetting
        
    
    def item(self, link, **kwarg):
        item = xbmcgui.ListItem()
        
        if 'title' in kwarg and kwarg['title']:
            item.setLabel(kwarg['title'])
            
        if 'label' in kwarg and kwarg['label']:
            item.setLabel2(kwarg['label'])
        
        if 'icon' in kwarg and kwarg['icon']:
            item.setIconImage(kwarg['icon'])
        
        if 'thumb' in kwarg and kwarg['thumb']:
            item.setThumbnailImage(kwarg['thumb'])
        
        if 'popup' in kwarg and kwarg['popup']:
            replace = False
            if 'popup_replace' in kwarg and kwarg['popup_replace']:
                replace = True
            menu = []
            for m in kwarg['popup']:
                #if len(m) > 2:
                #    if len(m) > 3:
                #        menu.append((m[1], 'Container.Update(%s,replace)' % m[0].url))
                #    else:
                #        menu.append((m[1], 'Container.Update(%s)' % m[0].url))
                #else:
                #    menu.append((m[1], 'XBMC.runPlugin(%s)' % m[0].url))
                menu.append((m[1], 'XBMC.runPlugin(%s)' % m[0].url))
            item.addContextMenuItems(menu, replace)
            
            
        if 'media' in kwarg and kwarg['media'] and 'info' in kwarg and kwarg['info']:
            item.setInfo(kwarg['media'], kwarg['info'])
        
        if 'property' in kwarg and kwarg['property']:
            for key, value in kwarg['property']:
                item.setProperty(key, value)
        
        fanart = self._gsetting.get('fanart')
        if 'fanart' in kwarg and kwarg['fanart']:
            fanart = kwarg['fanart']
        if fanart:
            item.setProperty('fanart_image', fanart)
        
        
        folder = True
        if 'folder' in kwarg and not kwarg['folder']:
            folder = False
        
        total = None
        if 'total' in kwarg and kwarg['total']:
            total = kwarg['total']
        
        self.add(link.url, item, folder, total)
        
    
    def add(self, url, item, folder=True, total=None):
        if total is None:
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, item, folder)
        else:
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, item, folder, total)
        self.is_listitem = True
        
    def render(self, **kwarg):
        if self.is_listitem and not self.is_render:
            
            replace = False
            if 'replace' in kwarg and kwarg['replace']:
                replace = True
            
            xbmcplugin.endOfDirectory(int(sys.argv[1]), updateListing=replace)
            
            if 'mode' in kwarg:
                xbmc.executebuiltin("Container.SetViewMode(%s)" % MODE[kwarg['mode']])
            
        self.is_render = True
    
    def run(self, link, replace=False):
        if replace:
            xbmc.executebuiltin('Container.Update(%s,replace)' % link.url)
        else:
            xbmc.executebuiltin('Container.Update(%s)' % link.url)
    
    def message(self, title, msg, times=5000, icon=None):
        if isinstance(title, unicode):
            title = title.encode('utf8')
        if isinstance(msg, unicode):
            msg = msg.encode('utf8')
        if icon and isinstance(icon, unicode):
            icon = icon.encode('utf8')
        try:
            xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s, "%s")' % (title, msg, times, icon))
        except Exception, e:
            xbmc.log('XBMCup: Handler: ' + str(e), xbmc.LOGERROR)
    
    def path(self, *path):
        dirname = [xbmc.translatePath('special://temp'), 'xbmcup', self.plugin, 'data']
        if path:
            dirname.extend(path)
        return os.path.join(*dirname)
    
    def handle(self):
        raise NotImplementedError()
    

class Plugin:
    def __init__(self, *handler):
        dirname = xbmc.translatePath('special://temp')
        for subdir in ('xbmcup', sys.argv[0].replace('plugin://', '').replace('/', ''), 'data'):
            dirname = os.path.join(dirname, subdir)
            if not xbmcvfs.exists(dirname):
                xbmcvfs.mkdir(dirname)
        
        self._index = None
        self._route = []
        self._global_setting = {}
        
        if handler:
            self.route(handler[0])
            for i in range(1, len(handler), 2):
                self.route(handler[i], handler[i+1])
    
    def route(self, route, handler=None):
        if handler is None:
            self._index = route
        else:
            self._route.append((route, handler))
    
        
    def run(self, **kwarg):
        xbmc.log('XBMCup: Plugin: sys.argv: ' + str(sys.argv), xbmc.LOGDEBUG)
        
        if len(sys.argv) > 2 and sys.argv[2]:
            link_t = json.loads(urllib.unquote_plus(sys.argv[2][1:]))
        else:
            link_t = {}
        
        link = {
            'route': link_t.get('route', None),
            'argv': link_t.get('argv', {}),
            'container': link_t.get('container', False),
            'container_replace': link_t.get('container_replace', False)
        }
        
        xbmc.log('XBMCup: Plugin: input param: ' + str(link), xbmc.LOGDEBUG)
        
        gsetting = {}
        
        xbmcplugin.setContent(int(sys.argv[1]), 'movies')
        
        if 'fanart' in kwarg:
            if kwarg['fanart'] and isinstance(kwarg['fanart'], basestring):
                fanart = kwarg['fanart']
            else:
                fanart = xbmcaddon.Addon(id=sys.argv[0].replace('plugin://', '').replace('/', '')).getAddonInfo('fanart')
            if fanart:
                gsetting['fanart'] = fanart
        
        try:
            app = None
            if link['route'] is None:
                app = self._index(gsetting=gsetting, link=None, argv=link['argv'])
            else:
                handler = [x[1] for x in self._route if x[0] == link['route']]
                if not handler:
                    xbmc.log('XBMCup: Plugin: handler not found: (sys.argv: ' + str(sys.argv) + ')', xbmc.LOGERROR)
                else:
                    if link['container']:
                        if link['container_replace']:
                            xbmc.executebuiltin('Container.Update(%s,replace)' % Link(link['route'], link['argv']).url)
                        else:
                            xbmc.executebuiltin('Container.Update(%s)' % Link(link['route'], link['argv']).url)
                    else:
                        app = handler[0](gsetting=gsetting, link=link['route'], argv=link['argv'])
            
            if app:
                app.handle()
                app.render()
        
        except Exception, e:
            xbmc.log('XBMCup: Plugin: error exec handler: ' + str(e) + '(sys.argv: ' + str(sys.argv) + ')', xbmc.LOGERROR)
            raise
        
                
                
class Setting(object):
    def __init__(self):
        self._cache = {}
        self._addon = xbmcaddon.Addon(id=sys.argv[0].replace('plugin://', '').replace('/', ''))
        
    def __getitem__(self, key):
        try:
            return self._cache[key]
        except KeyError:
            self._cache[key] = self._addon.getSetting(id=key)
            return self._cache[key]
        
    def __setitem__(self, key, value):
        self._cache[key] = value
        self._addon.setSetting(id=key, value=value)
    
    def dialog(self):
        self._cache = {}
        self._addon.openSettings()


class Lang(object):
    def __init__(self):
        self._cache = {}
        self._addon = xbmcaddon.Addon(id=sys.argv[0].replace('plugin://', '').replace('/', ''))
        
    def __getitem__(self, token):
        try:
            return self._cache[token]
        except KeyError:
            self._cache[token] = self._addon.getLocalizedString(id=token)
            return self._cache[token]
            