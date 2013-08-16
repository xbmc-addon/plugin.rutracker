#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import re
import time

try:
    from sqlite3 import dbapi2 as sqlite
except:
    from pysqlite2 import dbapi2 as sqlite

from xbmcup.app import Plugin, Handler, Link, Lang
from xbmcup.net import Torrent, LibTorrent, TorrentStream
from xbmcup.cache import Cache

import xbmc, xbmcgui, xbmcplugin, xbmcvfs

from drivers.rutracker import RuTracker
from drivers.kinopoisk import KinoPoisk
from drivers.tvdb import TvDb

CONTENT = {

'movie': {
    'index': (7, 22, 124, 93, 2198, 352),
    'ignore': (1640, 1454, 2374, 2373, 185, 254, 771, 44, 906, 69, 267, 65, 772, 789, 941, 1666, 531, 125, 149, 186, 96, 94, 653, 2344,
               514, 2097), # 3D - спорт, музыка (TODO - надо их куда-нибудь пристроить...)
    'media': 'video',
    'scraper': 'kinopoisk',
    'rating': u'%1.1f',
    'stream': True
},

'series': {
    'index': (9, 189, 2366, 911, 2100),
    'ignore': (26, 32, 67, 1147, 191, 190, 2369, 1493, 1500, 914, 915, 913, 2101, 2103),
    'media': 'video',
    'scraper': 'tvdb',
    'rating': u'%1.1f',
    'stream': True
},

'cartoon': {
    'index': (4, 921, 33),
    'ignore': (665, 86, 2343, 931, 932, 705, 1385, 535, 551, 1386, 1388, 282),
    'media': 'video',
    'scraper': None,
    'rating': False,
    'stream': True
},

'documentary': {
    # ID: 1495 (TODO - надо куда-нибудь пристроить (половина раздач - аудио)
    'index': (670, 46, 24),
    'ignore': (73, 77, 891, 518, 523, 1332),
    'media': 'video',
    'scraper': None,
    'rating': False,
    'stream': True
},

'training': {
    'index': (610, 1581, 1556),
    'ignore': (628, 1582, 1583, 1557),
    'media': 'video',
    'scraper': None,
    'rating': False,
    'stream': True
}



}

STATUS = {
    'moder':     (40501, 'FFFF0000'),
    'check':     (40502, 'FFFF0000'),
    'repeat':    (40503, 'FFFF0000'),
    'nodesc':    (40504, 'FFFF0000'),
    'copyright': (40505, 'FFFF0000'),
    'close':     (40506, 'FFFF0000'),
    'absorb':    (40507, 'FFFF0000'),
    
    'nocheck':   (40508, 'FFFF9900'),
    'neededit':  (40509, 'FFFF9900'),
    'doubtful':  (40510, 'FFFF9900'),
    'temp':      (40511, 'FFFF9900'),
    
    'ok':        (40512, 'FF339933')
}

GENRE = (
    ('anime', 80102),
    ('biography', 80103),
    ('action', 80104),
    ('western', 80105),
    ('military', 80106),
    ('detective', 80107),
    ('children', 80108),
    ('documentary', 80109),
    ('drama', 80110),
    ('game', 80111),
    ('history', 80112),
    ('comedy', 80113),
    ('concert', 80114),
    ('short', 80115),
    ('criminal', 80116),
    ('romance', 80117),
    ('music', 80118),
    ('cartoon', 80119),
    ('musical', 80120),
    ('news', 80121),
    ('adventures', 80122),
    ('realitytv', 80123),
    ('family', 80124),
    ('sports', 80125),
    ('talkshows', 80126),
    ('thriller', 80127),
    ('horror', 80128),
    ('fiction', 80129),
    ('filmnoir', 80130),
    ('fantasy', 80131)
)

WORK = (
    ('actor', u'Актер'),
    ('director', u'Режиссер'),
    ('writer', u'Сценарист'),
    ('producer', u'Продюсер'),
    ('composer', u'Композитор'),
    ('operator', u'Оператор'),
    ('editor', u'Монтажер'),
    ('design', u'Художник'),
    ('voice', u'Актер дубляжа'),
    ('voice_director', u'Режиссер дубляжа')
)

MPAA = ('G', 'PG', 'PG-13', 'R', 'NC-17', 'C', 'GP')


# ########################
#
#   COMMON
#
# ########################

class TrailerParser:
    def trailer_parser(self, trailers):
        popup = []
        
        # готовим список для попап-меню
        for r in trailers:
            name = r['name'] + u' [COLOR FFFFFFCC]['
            if r['ru']:
                name += u'RU, '
            if r['video'][0] > 3:
                name += u'HD, '
            if r['time']:
                name += r['time'] + u', '
            name += r['video'][2] + u'][/COLOR]'
            popup.append((name, r['video'][1]))
            
        label = self.lang[40101] + u' (' + str(len(popup)) + u')'
        if [1 for x in trailers if x['ru']]:
            label += u' RU'
        
        return label, popup

class Scrapers(TrailerParser):
    RE = {
        'year': re.compile(r'([1-2]{1}[0-9]{3})', re.U),
        'second': re.compile(r'^([^\[]*)\[(.+)\]([^\]]*)$', re.U)
    }
    kinopoisk = KinoPoisk()
    tvdb = TvDb()
    
    def scraper(self, content, item):
        # если есть специализированный скрабер, то запускаем его...
        if content == 'kinopoisk':
            return self.scraper_kinopoisk(item)
        
        elif content == 'tvdb':
            return self.scraper_tvdb(item)
        
        else:
            # иначе, используем стандартное отображение
            return self.scraper_default(item)
    
    def scraper_kinopoisk(self, item):
        scraper = self.scraper_default(item)
        
        # пробуем отделить основную часть имени фильма
        index = 1000000
        for token in (u'/', u'(', u'['):
            i = item['name'].find(token)
            if i != -1 and i < index:
                index = i
        if index == 1000000:
            return scraper
        
        first = item['name'][0:index].strip()
        second = item['name'][index:].strip()
        r = self.RE['second'].search(second)
        if r:
            g = []
            for i in range(1, 4):
                if r.group(i):
                    if i == 2:
                        g.append(u'[' + r.group(i).strip() + u']')
                    else:
                        g.append(r.group(i).strip())
                else:
                    g.append(u'')
            split = first, g[0], g[1], g[2]
        else:
            split = first, second, u'', u''
        
        # для поиска похожих раздач и поддиректорий
        scraper['search'] = scraper['subdir'] = split[0]
        
        # компилируем имя
        name = u'[COLOR FFEEEEEE][B]' + split[0] + u'[/B][/COLOR]'
        if split[1]:
            name += u' ' + split[1]
        if split[2]:
            name += u' [COLOR FFFFFFCC]' + split[2] + u'[/COLOR]'
        if split[3]:
            name += u' ' + split[3]
        
        # запрос для поиска
        search = split[0]
        
        # пробуем вытащить дату
        r = self.RE['year'].search(split[2])
        if r:
            year = int(r.group(1))
        else:
            year = None
        
        
        kinopoisk = self.kinopoisk.scraper(search, year, int(self.setting['kinopoisk_quality']) + 1)
        if not kinopoisk:
            return scraper
        
        # закладки
        scraper['bookmark'] = ('kinopoisk', kinopoisk['id'])
        
        # ХАК
        # добавляем runtime (длительность фильма) в описание (в скинах не видно)
        if 'runtime' in kinopoisk['info'] and kinopoisk['info']['runtime']:
            if 'plot' not in kinopoisk['info']:
                kinopoisk['info']['plot'] = u''
            kinopoisk['info']['plot'] = u''.join([self.lang[40102], u': [B]', kinopoisk['info']['runtime'], u'[/B] ', self.lang[40103], u'\n', kinopoisk['info']['plot']])
            del kinopoisk['info']['runtime']
        # ХАК
        
        scraper['title'] = name
        scraper['thumb'] = kinopoisk['thumb']
        scraper['fanart'] = kinopoisk['fanart']
        scraper['info'].update(kinopoisk['info'])
        
        # для поиска похожих раздач
        if kinopoisk['info'].get('originaltitle'):
            scraper['search'] = kinopoisk['info']['originaltitle']
        elif kinopoisk['info'].get('title'):
            scraper['search'] = kinopoisk['info']['title']
        
        # для создания поддиректорий
        scraper['subdir'] = scraper['search']
        if kinopoisk['info'].get('year'):
            scraper['subdir'] = u'.'.join([scraper['subdir'], str(kinopoisk['info']['year'])])
        
        # трейлеры
        if kinopoisk['trailers']:
            label, trailer_list = self.trailer_parser(kinopoisk['trailers'])
            scraper['popup'].append((Link('trailer', trailer_list), label))
        
        # рецензии
        scraper['popup'].append((Link('review', {'id': kinopoisk['id']}), self.lang[40007]))
        
        return scraper
    
    
    def scraper_tvdb(self, item):
        scraper = self.scraper_default(item)
        
        # пробуем получить сезон
        r = re.compile(u'Сезон[\:]{0,1}[\s]{1,}([0-9]+)', re.U).search(item['name'])
        if r:
            scraper['info']['season'] = int(r.group(1))
        
        # пробуем отделить основную часть имени фильма
        index = 1000000
        for token in (u'/', u'(', u'['):
            i = item['name'].find(token)
            if i != -1 and i < index:
                index = i
        if index == 1000000:
            return scraper
        
        first = item['name'][0:index].strip()
        second = item['name'][index:].strip()
        r = self.RE['second'].search(second)
        if r:
            g = []
            for i in range(1, 4):
                if r.group(i):
                    if i == 2:
                        g.append(u'[' + r.group(i).strip() + u']')
                    else:
                        g.append(r.group(i).strip())
                else:
                    g.append(u'')
            split = first, g[0], g[1], g[2]
        else:
            split = first, second, u'', u''
        
        # для поиска похожих раздач и поддиректорий
        scraper['search'] = scraper['subdir'] = split[0]
        
        # компилируем имя
        name = u'[COLOR FFEEEEEE][B]' + split[0] + u'[/B][/COLOR]'
        if split[1]:
            name += u' ' + split[1]
        if split[2]:
            name += u' [COLOR FFFFFFCC]' + split[2] + u'[/COLOR]'
        if split[3]:
            name += u' ' + split[3]
        
        # запрос для поиска
        search = split[0]
        
        # пробуем вытащить дату
        r = self.RE['year'].search(split[2])
        if r:
            year = int(r.group(1))
        else:
            year = None
        
        tvdb = self.tvdb.scraper(search, year)
        if not tvdb:
            return scraper
        
        # закладки
        scraper['bookmark'] = ('tvdb', tvdb['id'])
        
        # ХАК
        # добавляем runtime (длительность фильма) в описание (в скинах не видно)
        if 'runtime' in tvdb['info'] and tvdb['info']['runtime']:
            if 'plot' not in tvdb['info']:
                tvdb['info']['plot'] = u''
            tvdb['info']['plot'] = u''.join([self.lang[40102], u': [B]', tvdb['info']['runtime'], u'[/B] ', self.lang[40103], u'\n', tvdb['info']['plot']])
            del tvdb['info']['runtime']
        # ХАК
        
        scraper['title'] = name
        scraper['thumb'] = tvdb['thumb']
        scraper['fanart'] = tvdb['fanart']
        scraper['info'].update(tvdb['info'])
        
        # для поиска похожих раздач
        if tvdb['info'].get('originaltitle'):
            scraper['search'] = tvdb['info']['originaltitle']
        elif tvdb['info'].get('title'):
            scraper['search'] = tvdb['info']['title']
        
        # для создания поддиректорий
        scraper['subdir'] = scraper['search']
        
        # трейлеры
        #if kinopoisk['trailers']:
        #    label, trailer_list = self.trailer_parser(kinopoisk['trailers'])
        #    scraper['popup'].append((Link('trailer', trailer_list), label))
        
        # рецензии
        #scraper['popup'].append((Link('review', {'id': kinopoisk['id']}), self.lang[40007]))
        
        return scraper
    
    
    def scraper_default(self, item):
        return {
            'title': item['name'],
            'search': None,
            'subdir': item['name'],
            'icon': None,
            'thumb': None,
            'fanart': None,
            'popup': [],
            'bookmark': None,
            'info': {'size': item['size'], 'title': item['name']}
        }
    

# ########################
#
#   MENU
#
# ########################


class Menu(Handler):
    def handle(self):
        self.item(Link('menu-rutracker'), title=u'RuTracker')
        self.item(Link('menu-kinopoisk'), title=u'Кинопоиск')
        self.item(Link('bookmark'), title=u'Закладки')


class MenuRutracker(Handler):
    def handle(self):
        self.item(Link('rutracker-folder', {'content': 'movie'}), title=u'Фильмы')
        self.item(Link('rutracker-folder', {'content': 'series'}), title=u'Сериалы')
        self.item(Link('rutracker-folder', {'content': 'cartoon'}), title=u'Мультипликация')
        self.item(Link('rutracker-folder', {'content': 'documentary'}), title=u'Документалистика и юмор')
        self.item(Link('rutracker-folder', {'content': 'training'}), title=u'Обучающее видео')

class MenuKinopoisk(Handler):
    def handle(self):
        self.item(Link('kinopoisk-best-query', {}), title=u'Лучшие')
        self.item(Link('kinopoisk-search', {}), title=u'Поиск')
        self.item(Link('kinopoisk-person', {}), title=u'Персоны')



# ########################
#
#   TRACKER
#
# ########################


class RutrackerBase(Handler, Scrapers):
    def render_rutracker(self, is_search, folder, data):
        RE_SPACE = re.compile('\s{1,}', re.U)
        
        err = None
        if data is None:
            err = 30001
        elif data == 0:
            err = 30002
        
        if err:
            lang = self.lang[err].split('|')
            xbmcgui.Dialog().ok('RuTracker', lang[0], lang[1])
        else:
            
            rating_view = bool(self.setting['rutracker_rating'] == 'true')
            status_view = bool(self.setting['rutracker_status'] == 'true')
            fanart_view = bool(self.setting['rutracker_fanart'] == 'true')
            
            if not folder and not is_search:
                items = [x for x in data['data'] if x['id'] in CONTENT[self.argv['content']]['index']]
            else:
                items = [x for x in data['data'] if x['type'] == 'torrent' or x['id'] not in CONTENT[self.argv['content']]['ignore']]
            
            # подбиваем общее кол-во строк
            total = len(items)
            if data['pages'][1]:
                total += 1
            if data['pages'][3]:
                total += 1
            
            # меню для поиска (только на первой странице в категории)
            if not folder and not is_search:
                total += 1
                self.item(Link('rutracker-search', {'content': self.argv['content']}), title=u'[COLOR FF0DA09E][B][' + self.lang[30114] + u'][/B][/COLOR]', total=total)
            
            # верхний паджинатор
            if data['pages'][1]:
                self.item(Link('rutracker-folder', {'content': self.argv['content'], 'id': self.argv['id'], 'page': data['pages'][1]}), title=u'[COLOR FF0DA09E][B][' + self.lang[30101] + u'][/B][/COLOR] - [' + str(data['pages'][1]) + u'/' + str(data['pages'][0]) + u']', popup=[(Link('setting'), self.lang[40015])], popup_replace=True, total=total)
                
            for item in items:
                if item['type'] == 'folder':
                    self.item(Link('rutracker-folder', {'content': self.argv['content'], 'id': item['id']}), title=item['name'], popup=[(Link('force-cache', {'content': self.argv['content'], 'id': item['id']}), self.lang[40030])], total=total)
                else:
                    
                    # раздача
                    
                    # получаем инфу по скриншотам, коверу и описанию
                    profile = self.rutracker.profile(item['id'])
                    
                    # общий для всех popup (Info)
                    popup = [(Link('info'), self.lang[40001])]
                    
                    if profile and profile['descript']:
                        popup.append( (Link('descript', profile['descript']), self.lang[40002]) )
                    
                    # получаем данные из скрапера
                    scraper = self.scraper(CONTENT[self.argv['content']]['scraper'], item)
                    
                    # если фанарт выключен принудительно, то отключаем его
                    if not fanart_view:
                        scraper['fanart'] = None
                    
                    # чистим название файла для поддиректории
                    for char in u'\\/:*?"<>|':
                        scraper['subdir'] = scraper['subdir'].replace(char, u' ')
                    scraper['subdir'] = RE_SPACE.sub(u' ', scraper['subdir']).strip().replace(u' ', u'.')
                    
                    # если в скрапере были доп. попапы, то добавляем их
                    popup.extend(scraper['popup'])
                    
                    # если в скрапере нет обложки, то добавляем с трэкера
                    if not scraper['thumb'] and profile and profile['cover']:
                        scraper['thumb'] = profile['cover']
                    
                    # добиваем стандартные для всех попапы
                    
                    # скриншоты (для видео)
                    #if profile and profile['screenshot']:
                    #    popup.append( (Link('screenshot', profile['screenshot']), self.lang[40003] + u' (' + str(len(profile['screenshot'])) + u')') )
                    
                    # комментарии с раздачи
                    if item['comment'] == -1:
                        popup.append( (Link('comment', {'id': item['id']}), self.lang[40004]) )
                    elif item['comment']:
                        popup.append( (Link('comment', {'id': item['id']}), self.lang[40004] + u' (' + str(item['comment']) + u')') )
                    
                    # статус раздачи
                    popup.append( (Link('status', {'seeder': item['seeder'], 'leecher': item['leecher'], 'download': item['download'], 'comment': item['comment'], 'status': item['status'], 'status_human': item['status_human']}), self.lang[40005] + u' (' + str(item['seeder']) + u'/' + str(item['leecher']) + u')') )
                    
                    # поиск похожих раздач
                    if scraper['search']:
                        popup.append( (Link('rutracker-search', {'content': self.argv['content'], 'search': scraper['search']}, True), self.lang[40006]) )
                    
                    # закладки
                    if scraper['bookmark']:
                        popup.append( (Link('bookmark-add', {'scrapper': scraper['bookmark'][0], 'id': scraper['bookmark'][1]}), self.lang[40009]) )
                    
                    # настройки плагина
                    popup.append( (Link('setting'), self.lang[40015]) )
                    
                    # выставляем статус в наименование
                    if status_view:
                        try:
                            STATUS[item['status_human']]
                        except KeyError:
                            scraper['title'] = u'    ' + scraper['title']
                        else:
                            scraper['title'] = u'[COLOR ' + STATUS[item['status_human']][1] + ']' + item['status'] + u'[/COLOR]  ' + scraper['title']
                    
                    # выставляем рейтинг в наименование
                    if rating_view and CONTENT[self.argv['content']]['rating']:
                        rating = CONTENT[self.argv['content']]['rating'] % scraper['info'].get('rating', 0.0)
                        if rating == u'0.0':
                            rating = u'[COLOR 22FFFFFF]0.0[/COLOR]'
                        elif rating == u'10.0':
                            rating = u'[B]10[/B]'
                        scraper['title'] = rating + u'  ' + scraper['title']
                    
                    # вывод
                    self.item(Link('download', {'id': item['id'], 'content': self.argv['content'], 'subdir': scraper['subdir'], 'icon': scraper['icon'], 'thumb': scraper['thumb'], 'fanart': scraper['fanart'], 'bookmark': scraper['bookmark'], 'title': scraper['title']}), title=scraper['title'], icon=scraper['icon'], thumb=scraper['thumb'], fanart=scraper['fanart'], media=CONTENT[self.argv['content']]['media'], info=scraper['info'], popup=popup, popup_replace=True, folder=False, total=total)
            
            # нижний паджинатор
            if data['pages'][3]:
                self.item(Link('rutracker-folder', {'content': self.argv['content'], 'id': self.argv['id'], 'page': data['pages'][3]}), title=u'[COLOR FF0DA09E][B][' + self.lang[30102] + u'][/B][/COLOR] - [' + str(data['pages'][3]) + u'/' + str(data['pages'][0]) + u']', popup=[(Link('setting'), self.lang[40015])], popup_replace=True, total=total)
                
        # финал
        replace = False
        if 'page' in self.argv:
            replace = True
        
        self.render(replace=replace)
    
    

class RutrackerFolder(RutrackerBase):
    def handle(self):
        folder = self.argv.get('id')
        self.rutracker = RuTracker()
        self.render_rutracker(False, folder, self.rutracker.get(folder, self.argv.get('page', 1)))


class RutrackerSearch(RutrackerBase):
    def handle(self):
        content = self.argv['content']
        search = self.argv.get('search')
        
        if not search:
            kb = xbmc.Keyboard('', self.lang[30114])
            kb.doModal()
            if kb.isConfirmed():
                search = kb.getText()
        if not search:
            return True
        
        self.rutracker = RuTracker()
        
        data = self.rutracker.search(search, index=CONTENT[content]['index'], ignore=CONTENT[content]['ignore'])
        
        # not found
        if data and not data['data']:
            xbmcgui.Dialog().ok('RuTracker', self.lang[30008])
            return True
        
        self.render_rutracker(True, None, data)


class KinopoiskBase(Handler, TrailerParser):
    def render_kinopoisk(self, data):
        if data is None:
            lang = self.lang[30001].split('|')
            xbmcgui.Dialog().ok('Kinopoisk', lang[0], lang[1])
        elif not data['data']:
            xbmcgui.Dialog().ok('Kinopoisk', self.lang[30008])
        else:

            rating_view = bool(self.setting['rutracker_rating'] == 'true')
            fanart_view = bool(self.setting['rutracker_fanart'] == 'true')
            
            total = len(data['data'])
            if data['pages'][1]:
                total += 1
            if data['pages'][3]:
                total += 1
            
            # верхний паджинатор
            if data['pages'][1]:
                self.argv['page'] = data['pages'][1]
                self.item(Link(self.link, self.argv), title=u'[COLOR FF0DA09E][B][' + self.lang[30101] + u'][/B][/COLOR] - [' + str(data['pages'][1]) + u'/' + str(data['pages'][0]) + u']', popup=[(Link('setting'), self.lang[40015])], popup_replace=True, total=total)
            
            for id in data['data']:
                movie = self.kinopoisk.movie(id, None)
                if movie:
                    
                    # общий для всех popup (Info)
                    popup = [(Link('info'), self.lang[40001])]
                    
                    # трэйлеры
                    if movie['trailers']:
                        label, trailer_list = self.trailer_parser(movie['trailers'])
                        popup.append((Link('trailer', trailer_list), label))
                    
                    # рецензии
                    popup.append((Link('review', {'id': id}), self.lang[40007]))
                    
                    # добавить в закладки
                    popup.append( (Link('bookmark-add', {'scrapper': 'kinopoisk', 'id': id}), self.lang[40009]) )
                    
                    # настройки плагина
                    popup.append( (Link('setting'), self.lang[40015]) )
                    
                    # имя для поиска на RuTracker
                    search = movie['info']['title']
                    if movie['info'].get('originaltitle'):
                        search = movie['info']['originaltitle']

                    # если фанарт выключен принудительно, то отключаем его
                    if not fanart_view:
                        movie['fanart'] = None

                    # выставляем рейтинг в наименование
                    if rating_view:
                        rating = u'%1.1f' % movie['info'].get('rating', 0.0)
                        if rating == u'0.0':
                            rating = u'[COLOR 22FFFFFF]0.0[/COLOR]'
                        elif rating == u'10.0':
                            rating = u'[B]10[/B]'
                        movie['info']['title'] = rating + u'  ' + movie['info']['title']
                        
                    # вывод
                    self.item(Link('rutracker-search', {'content': 'movie', 'search': search}), title=movie['info']['title'], thumb=movie['thumb'], media='video', info=movie['info'], fanart=movie['fanart'], popup=popup, popup_replace=True, total=total)
            
            # нижний паджинатор
            if data['pages'][3]:
                self.argv['page'] = data['pages'][3]
                self.item(Link(self.link, self.argv), title=u'[COLOR FF0DA09E][B][' + self.lang[30102] + u'][/B][/COLOR] - [' + str(data['pages'][3]) + u'/' + str(data['pages'][0]) + u']', popup=[(Link('setting'), self.lang[40015])], popup_replace=True, total=total)
            
            # финал
            replace = False
            if data['pages'][2] > 1:
                replace = True
            
            self.render(replace=replace)
                    
            
class KinopoiskBestQuery(Handler):
    def handle(self):
        self.kinopoisk = KinoPoisk()
        
        genre_lang = {'all': self.lang[70301]}
        for tag, code in GENRE:
            genre_lang[tag] = self.lang[code]
        
        if self.argv.get('change'):
            
            # ввод жанра
            if self.argv['change'] == 'genre':
                genre_list = [u'[B]' + self.lang[80101] + u'[/B]']
                genre_list.extend([genre_lang[x[0]] for x in GENRE])
                sel = xbmcgui.Dialog()
                gnr = sel.select(self.lang[70202], genre_list)
                if gnr > -1:
                    if gnr == 0:
                        genre = 'all'
                    else:
                        genre = GENRE[gnr - 1][0]
                    self.setting['kinopoisk_genre'] = genre
            
            # ввод даты
            if self.argv['change'] == 'decade':
                decade_list = [u'[B]' + self.lang[70301] + u'[/B]']
                for y in range(201, 188, -1):
                    decade_list.append(str(10*y) + '-e')
                
                sel = xbmcgui.Dialog()
                d = sel.select(self.lang[70203], decade_list)
                if d > -1:
                    if d == 0:
                        self.setting['kinopoisk_decade'] = '0'
                    else:
                        self.setting['kinopoisk_decade'] = decade_list[d][0:4]
            
            # ввод рейтинга
            if self.argv['change'] == 'rate':
                rate_list = [u'[B]' + self.lang[70301] + u'[/B]']
                for r in range(10, 0, -1):
                    rate_list.append(str(r))
                
                sel = xbmcgui.Dialog()
                r = sel.select(self.lang[70204], rate_list)
                if r > -1:
                    if r == 0:
                        self.setting['kinopoisk_rate'] = '0'
                    else:
                        self.setting['kinopoisk_rate'] = rate_list[r]
            
            # ввод кол-ва оценок
            if self.argv['change'] == 'votes':
                vot = xbmcgui.Dialog()
                v = vot.numeric(0, self.lang[70205])
                if v:
                    v = int(v)
                    if v < 100:
                        v = 100
                    self.setting['kinopoisk_votes'] = str(v)
            
            # ввод страны производства
            if self.argv['change'] == 'country':
                countries = self.kinopoisk.countries()
                countries_list = [u'[B]' + countries[0][1] + u'[/B]']
                countries_list.extend([x[1] for x in countries[1:]])
                sel = xbmcgui.Dialog()
                country = sel.select(self.lang[70208], countries_list)
                if country > -1:
                    self.setting['kinopoisk_country'] = str(countries[country][0])
            
            # ввод mpaa
            if self.argv['change'] == 'mpaa':
                mpaa_list = [u'[B]' + self.lang[70301] + u'[/B]']
                mpaa_list.extend(MPAA)
                
                sel = xbmcgui.Dialog()
                m = sel.select(self.lang[70206], mpaa_list)
                if m > -1:
                    if m == 0:
                        self.setting['kinopoisk_mpaa'] = 'all'
                    else:
                        self.setting['kinopoisk_mpaa'] = mpaa_list[m]
            
            # ввод DVD
            if self.argv['change'] == 'dvd':
                sel = xbmcgui.Dialog()
                d = sel.select(self.lang[70207], [self.lang[70304], self.lang[70303]])
                if d > -1:
                    if d == 0:
                        self.setting['kinopoisk_dvd'] = 'true'
                    else:
                        self.setting['kinopoisk_dvd'] = 'false'
                
        
        # получение текущих параметров поиска
        genre = self.setting['kinopoisk_genre']
        decade = int(self.setting['kinopoisk_decade'])
        rate = int(self.setting['kinopoisk_rate'])
        votes = int(self.setting['kinopoisk_votes'])
        country = int(self.setting['kinopoisk_country'])
        mpaa = self.setting['kinopoisk_mpaa']
        dvd = bool(self.setting['kinopoisk_dvd'] == 'true')
        
        
        # начинаем вывод
        
        # вывод жанра
        self.item(Link('kinopoisk-best-query', {'change': 'genre'}), title=self.lang[70102] + u': [B]' + genre_lang[genre] + u'[/B]', popup=[(Link('setting'), self.lang[40015])], popup_replace=True)
        
        # вывод даты
        decade_title = u'[B]' + self.lang[70301] + u'[/B]'
        if decade:
            decade_title = u'[B]' + str(decade) + '[/B]-e'
        self.item(Link('kinopoisk-best-query', {'change': 'decade'}), title=self.lang[70103] + u': ' + decade_title, popup=[(Link('setting'), self.lang[40015])], popup_replace=True)
        
        # вывод рейтинга
        rate_title = u'[B]' + self.lang[70301] + u'[/B]'
        if rate:
            rate_title = self.lang[70302] + u' [B]' + str(rate) + u'[/B]'
        self.item(Link('kinopoisk-best-query', {'change': 'rate'}), title=self.lang[70104] + u': ' + rate_title, popup=[(Link('setting'), self.lang[40015])], popup_replace=True)
        
        # вывод кол-во оценок
        self.item(Link('kinopoisk-best-query', {'change': 'votes'}), title=self.lang[70105] + u': ' + self.lang[70302] + u' [B]' + str(votes) + u'[/B]', popup=[(Link('setting'), self.lang[40015])], popup_replace=True)
        
        # вывод страны производства
        self.item(Link('kinopoisk-best-query', {'change': 'country'}), title=self.lang[70106] + u':  [B]' + self.kinopoisk.country(country, u' ') + u'[/B]', popup=[(Link('setting'), self.lang[40015])], popup_replace=True)
        
        # вывод MPAA
        self.item(Link('kinopoisk-best-query', {'change': 'mpaa'}), title=u'MPAA: [B]' + (self.lang[70301] if mpaa == 'all' else mpaa) + u'[/B]', popup=[(Link('setting'), self.lang[40015])], popup_replace=True)
        
        # вывод DVD
        self.item(Link('kinopoisk-best-query', {'change': 'dvd'}), title=u'DVD: [B]' + (self.lang[70304] if dvd else self.lang[70303]) + u'[/B]', popup=[(Link('setting'), self.lang[40015])], popup_replace=True)
        
        # кнопка ПОИСК
        self.item(Link('kinopoisk-best', {'genre': genre, 'decade': decade, 'rate': rate, 'votes': votes, 'country': country, 'mpaa': mpaa, 'dvd': dvd}), title=u''.join([u'[COLOR FF0DA09E][B][', self.lang[70110], u'][/B][/COLOR]']), popup=[(Link('setting'), self.lang[40015])], popup_replace=True)
        
        # финал
        replace = False
        if self.argv.get('change'):
            replace = True
        
        self.render(replace=replace)
    
            

class KinopoiskBest(KinopoiskBase):
    def handle(self):
        self.argv['limit'] = int(self.setting['kinopoisk_limit'])
        if not self.argv['limit']:
            self.argv['limit'] = 50
        
        if self.argv['genre'] == 'all':
            self.argv['genre'] = None
        if self.argv['mpaa'] == 'all':
            self.argv['mpaa'] = None
        
        self.kinopoisk = KinoPoisk()
        self.render_kinopoisk(self.kinopoisk.best(**self.argv))


class KinopoiskSearch(KinopoiskBase):
    def handle(self):
        kb = xbmc.Keyboard(u'', self.lang[70201])
        kb.doModal()
        if kb.isConfirmed():
            name = kb.getText().decode('utf8')
            if name:
                self.kinopoisk = KinoPoisk()
                self.render_kinopoisk(self.kinopoisk.search(name))


class KinopoiskPerson(Handler):
    def handle(self):
        kb = xbmc.Keyboard(u'', self.lang[70401])
        kb.doModal()
        if kb.isConfirmed():
            name = kb.getText().decode('utf8')
            if name:
                self.kinopoisk = KinoPoisk()
                
                data = self.kinopoisk.person(name)
                
                if data is None:
                    lang = self.lang[30001].split('|')
                    xbmcgui.Dialog().ok('Kinopoisk', lang[0], lang[1])
                elif not data['data']:
                    xbmcgui.Dialog().ok('Kinopoisk', self.lang[30008])
                else:
                    
                    for d in data['data']:
                        title = u'[B]' + d['name'] + u'[/B]'
                        if d['originalname'] and d['year']:
                            title += u' / ' + d['originalname'] + u' (' + str(d['year']) + u')'
                        elif d['originalname']:
                            title += u' / ' + d['originalname']
                        elif d['year']:
                            title += u' /  (' + str(d['year']) + u')'
                        
                        self.item(Link('kinopoisk-work', {'id': d['id']}), title=title, thumb=d['poster'], popup=[(Link('setting'), self.lang[40015])], popup_replace=True)


class KinopoiskWork(KinopoiskBase):
    def handle(self):
        self.kinopoisk = KinoPoisk()
        
        data = self.kinopoisk.work(self.argv['id'])
        
        if not data:
            xbmcgui.Dialog().ok('Kinopoisk', self.lang[30008])
        else:
            
            works = [x for x in WORK if x[0] in data]
            
            sel = xbmcgui.Dialog()
            work = sel.select(self.lang[70402], [x[1] + u' (' + str(len(data[x[0]])) + u')' for x in works])
            if work == -1:
                work = 0
            
            self.render_kinopoisk({'pages': (1, 0, 1, 0), 'data': data[works[work][0]]})
            
                                

class BookmarkDB:
    def __init__(self, filename):
        self.filename = filename
        
        if not xbmcvfs.exists(self.filename):
            self._connect()
            self.cur.execute('pragma auto_vacuum=1')
            self.cur.execute('create table bookmark(addtime integer, scrapper varchar(32), id varchar(32))')
            self.cur.execute('create index time on bookmark(addtime desc)')
            self.db.commit()
            self._close()
    
    def get(self):
        self._connect()
        self.cur.execute('select scrapper,id from bookmark order by addtime desc')
        res = [{'scrapper': x[0], 'id': x[1]} for x in self.cur.fetchall()]
        self._close()
        return res
        
    def add(self, scrapper, id):
        self.delete(scrapper, id)
        self._connect()
        self.cur.execute('insert into bookmark(addtime,scrapper,id) values(?,?,?)', (int(time.time()), scrapper, str(id)))
        self.db.commit()
        self._close()
    
    def delete(self, scrapper, id):
        self._connect()
        self.cur.execute('delete from bookmark where scrapper=? and id=?', (scrapper, id))
        self.db.commit()
        self._close()
    
    def _connect(self):
        self.db = sqlite.connect(self.filename)
        self.cur = self.db.cursor()
    
    def _close(self):
        self.cur.close()
        self.db.close()


class Bookmark(Handler, TrailerParser):
    def handle(self):
        bookmark = BookmarkDB(self.path('bookmark.db'))
        
        if 'scrapper' in self.argv:
            bookmark.delete(self.argv['scrapper'], self.argv['id'])
            xbmcgui.Dialog().ok('RuTracker', self.lang[30021])
        
        kinopoisk = KinoPoisk()
        
        data = bookmark.get()
        if not data:
            xbmcgui.Dialog().ok('RuTracker', self.lang[30008])
        else:

            rating_view = bool(self.setting['rutracker_rating'] == 'true')
            fanart_view = bool(self.setting['rutracker_fanart'] == 'true')
            
            total = len(data)
            
            for d in data:
                
                # общий для всех popup (Info)
                popup = [(Link('info'), self.lang[40001])]
                
                if d['scrapper'] == 'kinopoisk':
                    
                    movie = kinopoisk.movie(d['id'])
                    
                    # трэйлеры
                    if movie['trailers']:
                        label, trailer_list = self.trailer_parser(movie['trailers'])
                        popup.append((Link('trailer', trailer_list), label))
                    
                    # рецензии
                    popup.append((Link('review', {'id': d['id']}), self.lang[40007]))
                    
                    # удалить из закладок
                    popup.append( (Link('bookmark', {'scrapper': d['scrapper'], 'id': d['id']}), self.lang[40010], True, True) )
                    
                    # настройки плагина
                    popup.append( (Link('setting'), self.lang[40015]) )
                    
                    # имя для поиска на RuTracker
                    search = movie['info']['title']
                    if movie['info'].get('originaltitle'):
                        search = movie['info']['originaltitle']

                    # если фанарт выключен принудительно, то отключаем его
                    if not fanart_view:
                        movie['fanart'] = None

                    # выставляем рейтинг в наименование
                    if rating_view:
                        rating = u'%1.1f' % movie['info'].get('rating', 0.0)
                        if rating == u'0.0':
                            rating = u'[COLOR 22FFFFFF]0.0[/COLOR]'
                        elif rating == u'10.0':
                            rating = u'[B]10[/B]'
                        movie['info']['title'] = rating + u'  ' + movie['info']['title']
                    
                    # вывод
                    self.item(Link('rutracker-search', {'content': 'movie', 'search': search}), title=movie['info']['title'], thumb=movie['thumb'], media='video', info=movie['info'], fanart=movie['fanart'], popup=popup, popup_replace=True, total=total)
                
                else:
                    # TODO - для других скраперов
                    pass


class BookmarkAdd(Handler):
    def handle(self):
        BookmarkDB(self.path('bookmark.db')).add(self.argv['scrapper'], self.argv['id'])
        xbmcgui.Dialog().ok('RuTracker', self.lang[30020])
        return True



# ########################
#
#   ACTION
#
# ########################


class TorrentBase(Handler):
    def download(self):
        self.rutracker = RuTracker()
        torrent = self.rutracker.download(self.argv['id'])
        if torrent:
            return torrent
        xbmcgui.Dialog().ok('RuTracker', *self.lang[30001].split('|'))
    
    def get_dirname(self, prefix):
        dirname = self.setting[prefix + '_dir']
        if dirname and self.setting[prefix + '_save'] == '0':
            dirname = None
        
        if not dirname:
            dirname = xbmcgui.Dialog().browse(3, 'RuTracker', CONTENT[self.argv['content']]['media'], '', False, False, '')
        
        return bool(self.setting[prefix + '_subdir'] == 'true'), dirname.decode('utf8') if dirname else None
    
    def _mkdir(self, root, path):
        if not isinstance(path, list):
            path = [path]
        for subdir in path:
            root = os.path.join(root, subdir)
            try:
                os.mkdir(root)
                os.chmod(root, 0777)
            except:
                pass
        return root
    
    def _clear(self, dirname):
        for filename in os.listdir(dirname):
            filename = os.path.join(dirname, filename)
            if os.path.isfile(filename):
                os.unlink(filename)
            else:
                self._clear(filename)
                os.rmdir(filename)


class Download(TorrentBase):
    def handle(self):
        config = self.get_torrent_client()
        
        stream = None
        if CONTENT[self.argv['content']]['stream'] and (LibTorrent().is_install or TorrentStream().is_install):

            msg = []

            if LibTorrent().is_install:
                msg.append(('libtorrent', self.lang[40008]))

            if TorrentStream().is_install:
                msg.append(('torrentstream', self.lang[40023]))

            if config['client'] == 'utorrent':
                msg.append(('utorrent', self.lang[40020]))
            else:
                msg.append(('transmission', self.lang[40021]))
            
            dialog = xbmcgui.Dialog()
            index = dialog.select(u'RuTracker', [x[1] for x in msg])
            if index < 0:
                return True
            else:
                stream = msg[index][0]
        
        if stream in ('libtorrent', 'torrentstream'):
            self.argv['engine'] = stream
            self.run(Link('stream', self.argv))
        else:
            torrent = self.download()
            if torrent:
                
                subdir, rootdir = self.get_dirname('torrent')
                if not rootdir:
                    return True
                dirname = self._mkdir(rootdir, self.argv['subdir']) if subdir else rootdir
                
                client = Torrent(client=config['client'], host=config['host'], port=config['port'], login=config['login'], password=config['password'], url=config['url'])
                if client.add(torrent, dirname) is None:
                    if subdir:
                        dirname = os.path.join(rootdir, self.argv['subdir'][0])
                        self._clear(dirname)
                        os.rmdir(dirname)
                    xbmcgui.Dialog().ok('RuTracker', *self.lang[30014].split('|'))
                else:
                    if config['client'] == 'utorrent':
                        msg = 30015
                        cmd = 'plugin.program.utorrent'
                    else:
                        msg = 30016
                        cmd = 'script.transmission'
                    
                    if self.argv['bookmark']:
                        BookmarkDB(self.path('bookmark.db')).delete(self.argv['bookmark'][0], self.argv['bookmark'][1])
                    
                    if xbmcgui.Dialog().yesno('RuTracker', *self.lang[msg].split('|')):
                        xbmc.executebuiltin('XBMC.RunAddon(' + cmd + ')')
            
        return True
    
    def get_torrent_client(self):
        torrent = self.setting['torrent']
        
        if torrent == '0':
            config = {
                'client': 'utorrent',
                'host': self.setting['torrent_utorrent_host'],
                'port': self.setting['torrent_utorrent_port'],
                'url': '',
                'login': self.setting['torrent_utorrent_login'],
                'password': self.setting['torrent_utorrent_password']
            }
            
        elif torrent == '1':
            config = {
                'client': 'transmission',
                'host': self.setting['torrent_transmission_host'],
                'port': self.setting['torrent_transmission_port'],
                'url': self.setting['torrent_transmission_url'],
                'login': self.setting['torrent_transmission_login'],
                'password': self.setting['torrent_transmission_password']
            }
        
        return config
    

class Stream(TorrentBase):
    def handle(self):
        if self.argv['engine'] == 'libtorrent':
            self._libtorrent()
        else:
            self._torrentstream()



    def _torrentstream(self):
        # проигрываем файл
        if 'file_id' in self.argv:
            torrent = file(xbmc.translatePath('special://temp/plugin.rutracker.torrentstream.cache.torrent'), 'rb').read()
            filename = TorrentStream(self.setting['torrentstream_port']).play(torrent, self.argv['file_id'], self.argv['title'], self.argv['icon'], self.argv['thumb'])
            return True
        
        # получаем список файлов из торрента
        else:
            torrent = self.download()
            if not torrent:
                return True
            
            # кэшируем торрент
            file(xbmc.translatePath('special://temp/plugin.rutracker.torrentstream.cache.torrent'), 'wb').write(torrent)
            
            filelist = TorrentStream(self.setting['torrentstream_port']).list(torrent, bool(self.setting['torrentstream_reverse'] == 'true'))
            if not filelist:
                return True
            
            total = len(filelist)
            
            for f in filelist:
                self.argv['file_id'] = f['id']
                self.argv['title'] = f['name']
                self.item(Link('stream', self.argv), title=f['name'], media=CONTENT[self.argv['content']]['media'], popup=[(Link('setting'), self.lang[40015])], icon=self.argv['icon'], thumb=self.argv['thumb'], fanart=self.argv['fanart'], popup_replace=True, folder=False, total=total)
                
            self.render(mode='full')
            

    def _libtorrent(self):
        # первый запуск
        buffer = self.path(u'libtorrent')
        if not os.path.isdir(buffer):
            os.mkdir(buffer)
            os.chmod(buffer, 0777)
        buffer = self.path(u'libtorrent', u'buffer')
        if not os.path.isdir(buffer):
            os.mkdir(buffer)
            os.chmod(buffer, 0777)
        
        # получаем буфер
        buffer = None
        if bool(self.setting['libtorrent_buffer'] == 'true'):
            buffer = self.setting['libtorrent_dir_buffer'].decode('utf8')
        
        if not buffer:
            buffer = self.path(u'libtorrent', u'buffer')
        
        # проигрываем файл
        if 'file_id' in self.argv:
            torrent = file(self.path(u'libtorrent', u'buffer.torrent'), 'rb').read()
            
            if bool(self.setting['libtorrent_seed'] == 'true'):
                seed = 0
                if bool(self.setting['libtorrent_seed_limit'] == 'true'):
                    seed = self.setting['libtorrent_seed_speed']
                    seed = 125000*(int(seed) if seed else 0)
            else:
                seed = None
            
            filename = LibTorrent().play(torrent=torrent, file_id=self.argv['file_id'], dirname=buffer, seed=seed, info=None, notice=bool(self.setting['libtorrent_notice'] == 'true'), buffer=int(self.setting['libtorrent_buffer_size']))
            
            if self.argv['bookmark']:
                BookmarkDB(self.path('bookmark.db')).delete(self.argv['bookmark'][0], self.argv['bookmark'][1])
            
            if filename:
                
                is_keep = int(self.setting['libtorrent_keep'])
                if is_keep == 2:
                    is_keep = xbmcgui.Dialog().yesno(u'RuTracker', *self.lang[30011].split('|'))
                
                if is_keep:
                    subdir, rootdir = self.get_dirname('libtorrent')
                    if not rootdir:
                        return True
                    dirname = self._mkdir(rootdir, self.argv['subdir']) if subdir else rootdir
                    
                    self._copy(filename, dirname)
                    
                    xbmcgui.Dialog().ok(u'RuTracker', self.lang[30013])
                    
            return True
        
        # получаем список файлов из торрента
        else:
            torrent = self.download()
            if not torrent:
                return True
            
            filelist = LibTorrent().list(torrent, bool(self.setting['libtorrent_reverse'] == 'true'))
            if not filelist:
                return True
            
            # чистим кэш
            if os.path.isfile(self.path(u'libtorrent', u'buffer.torrent')) and torrent != file(self.path(u'libtorrent', u'buffer.torrent'), 'rb').read():
                self._clear(buffer)
            
            # кэшируем торрент
            file(self.path(u'libtorrent', u'buffer.torrent'), 'wb').write(torrent)
            
            total = len(filelist)
            
            for f in filelist:
                self.argv['file_id'] = f['id']
                self.item(Link('stream', self.argv), title=f['name'], media=CONTENT[self.argv['content']]['media'], info={'size': f['size']}, popup=[(Link('setting'), self.lang[40015])], icon=self.argv['icon'], thumb=self.argv['thumb'], fanart=self.argv['fanart'], popup_replace=True, folder=False, total=total)
                
            self.render(mode='full')


    def _copy(self, filename, dirname):
        progress = xbmcgui.DialogProgress()
        progress.create(u'RuTracker')
        full = os.path.getsize(filename)
        message, fname, fullsize = self.lang[30012], filename.split(os.sep.decode('utf8'))[-1].encode('utf8'), self._human(full).strip()
        progress.update(0, message, 'File: ' + fname, 'Size: ' + self._human(0) + ' / ' + fullsize)
        
        load = 0
        ff = open(filename, 'rb')
        ft = open(os.path.join(dirname, filename.split(os.sep.decode('utf8'))[-1]), 'wb')
        
        loop = 0.0
        
        while True:
            buf = ff.read(8192)
            if not buf:
                break
            load += len(buf)
            ft.write(buf)
            
            if loop + 0.5 < time.time():
                progress.update(int(load/(full/100)), message, 'File: ' + fname, 'Size: ' + self._human(load) + ' / ' + fullsize)
                loop = time.time()
        
        progress.close()
        
        ff.close()
        ft.close()
        
    
    def _human(self, size):
        human = None
        for h, f in (('KB', 1024), ('MB', 1024*1024), ('GB', 1024*1024*1024), ('TB', 1024*1024*1024*1024)):
            if size/f > 0:
                human = h
                factor = f
            else:
                break
        if human is None:
            return (u'%10.1f %s' % (size, u'byte')).replace(u'.0', u'')
        else:
            return u'%10.2f %s' % (float(size)/float(factor), human)
            
class ForceCache(Handler, Scrapers):
    def handle(self):
        if xbmcgui.Dialog().yesno('RuTracker', *self.lang[30030].split('|')):
            
            rutracker = RuTracker()
            
            items = {}
            page = 1
            total = 1
            
            progress = xbmcgui.DialogProgress()
            progress.create(u'RuTracker')
            progress.update(0, self.lang[40801], self.lang[40802] + u':   ' + str(page) + u' / ' + str(total))
            
            while True:
                
                data = rutracker.get(self.argv['id'], page)
                if not data:
                    break
                
                for item in [x for x in data['data'] if x['type'] == 'torrent']:
                    items[item['id']] = item
                
                if not data['pages'][3]:
                    break
                page = data['pages'][3]
                total = data['pages'][0]
                
                progress.update(int(float(page)/(float(total)/100.0)), self.lang[40801], self.lang[40802] + u':   ' + str(page) + u' / ' + str(total))
                
                if progress.iscanceled():
                    progress.close()
                    return True
            
            progress.close()
            if progress.iscanceled():
                return True
            
            if items:
                total = len(items)
                i = 0
                
                progress = xbmcgui.DialogProgress()
                progress.create(u'RuTracker')
                
                for id, item in items.iteritems():
                    i += 1
                    progress.update(int(float(i)/(float(total)/100.0)), self.lang[40803], self.lang[40804] + u':   ' + str(i) + u' / ' + str(total))
                    
                    # кэшируем описание
                    rutracker.profile(item['id'])
                    
                    # кэшируем скрапер
                    self.scraper(CONTENT[self.argv['content']]['scraper'], item)
                    
                    if progress.iscanceled():
                        progress.close()
                        return True
            
            progress.close()
            
            xbmcgui.Dialog().ok('RuTracker', *self.lang[30031].split('|'))
        
        return True
    
    
class Setting(Handler):
    def handle(self):
        self.setting.dialog()
        return True


class Info(Handler):
    def handle(self):
        xbmc.executebuiltin('Action(Info)')
        return True
    

class Trailer(Handler):
    def handle(self):
        dialog = xbmcgui.Dialog()
        index = dialog.select(self.lang[40101], [x[0] for x in self.argv])
        if index < 0:
            return True
        xbmc.Player().play(self.argv[index][1])
        return True
    
    
class Screenshot(Handler):
    def handle(self):
        xbmc.executehttpapi('ClearSlideshow')
        for url in self.argv:
            xbmc.executehttpapi('AddToSlideshow(%s)' % url)
            #xbmc.executehttpapi('AddToSlideshow(%s)' % 'http://st-im.kinopoisk.ru/im/wallpaper/1/3/7/kinopoisk.ru-Stone-1372763--w--1280.jpg')
        xbmc.executebuiltin('SlideShow(,recursive,notrandom)')
        return True


class Status(Handler):
    def handle(self):
        line = self.lang[40491] + u':  [B]' + str(self.argv['seeder']) + u'[/B]    ' + self.lang[40492] + u':  [B]' + str(self.argv['leecher']) + u'[/B]    ' + self.lang[40493] + u':  [B]' + str(self.argv['download']) + u'[/B]'
        
        try:
            lang, color = STATUS[self.argv['status_human']]
        except KeyError:
            xbmcgui.Dialog().ok(self.lang[40005], line)
        else:
            xbmcgui.Dialog().ok(self.lang[40005], u'[COLOR ' + color + ']' + self.argv['status'] + u'[/COLOR] ' + self.lang[lang], u'   ' + line)
            
        return True


class FlushCache(Handler):
    def handle(self):
        if self.argv['cache'] == 1:
            cache_name = u'RuTracker'
            Cache('rutracker_catalog.db').flush()
            Cache('rutracker_profile.db').flush()
        else:
            cache_name = u'KinoPoisk'
            Cache('kinopoisk.db').flush()
        xbmcgui.Dialog().ok(cache_name, self.lang[30010])
        return True


class Descript(Handler):
    def handle(self):
        gui = GuiDescript('DialogTextViewer.xml', sys.argv[0], descript=self.argv)
        gui.doModal()
        del gui
        return True


class GuiDescript(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.descript = kwargs['descript']
        xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
        
    def onInit(self):
        lang = Lang()
        self.getControl(1).setLabel(lang[40002])
        self.getControl(5).setText(self.descript)
    
    def onFocus(self, control):
        pass


class Comment(Handler):
    def handle(self):
        gui = GuiComment('DialogTextViewer.xml', sys.argv[0], id=self.argv['id'])
        gui.doModal()
        del gui
        return True


class GuiComment(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.id = kwargs['id']
        xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
        
    def onInit(self):
        self._lang = Lang()
        self.lang = {
            'comment': self._lang[40004],
            'page': self._lang[30103],
            'load': self._lang[30104],
            'usertime': self._lang[30111],
            'count': self._lang[30112],
            'location': self._lang[30113]
        }
        
        self.label = self.getControl(1)
        self.text = self.getControl(5)
        
        self.rutracker = RuTracker()
        self.comment = []
        self.page = 1
        self.page_total = None
        if self.load():
            self.cursor = 0
            self.render()
        
    def onFocus(self, control):
        pass
    
    def onAction(self, action):
        id = action.getId()
        if id == 1:
            self.left()
        elif id == 2:
            self.right()
        elif id in (9, 10, 92):
            self.close()
    
    def left(self):
        if not self.lock:
            if self.cursor > 0:
                self.cursor -= 1
                self.render()
                
    
    def right(self):
        if not self.lock:
            if self.cursor + 1 < len(self.comment):
                self.cursor += 1
                self.render()
            else:
                
                if self.page < self.page_total:
                    self.page += 1
                    if self.load():
                        self.cursor += 1
                        self.render()
                    else:
                        self.page -= 1
                    
    
    def load(self):
        self.lock = True
        self.label.setLabel(self.lang['comment'])
        self.text.setText(self.lang['load'])
        
        data = self.rutracker.comment(self.id, self.page)
        
        if not data or not data['comments']:
            if data is None:
                code_msg = 30001
            elif not data:
                code_msg = 30002
            else:
                code_msg = 30005
            xbmcgui.Dialog().ok('RuTracker', *self._lang(code_msg).split('|'))
            
            if self.page_total is None:
                self.close()
                return False
            
            self.lock = False
            return False
            
        else:
            self.comment.extend(data['comments'])
            if self.page_total is None:
                self.page_total = data['pages'][0]
            
            self.lock = False
            return True
            
            
    def render(self):
        self.label.setLabel(self.lang['comment'] + u':  ' + str(self.cursor + 1) + u'/' + str(len(self.comment)) + u'     ' + self.lang['page'] + u':  ' + str(self.page) + u'/' + str(self.page_total))
        
        msg = self.comment[self.cursor]
        text = u''
        
        if msg['time']:
            text += msg['time'] + '\n'
        
        text += u'[COLOR FF0DA09E][B]' + msg['nick'] + u'[/B][/COLOR]'
        
        profile = []
        for tag, lang in (('usertime', self.lang['usertime']), ('count', self.lang['count']), ('location', self.lang['location'])):
            if msg[tag]:
                profile.append(lang + u':  ' + msg[tag])
        if profile:
            text += u'   [ ' + u',  '.join(profile) + u' ]'
        
        text += u'\n\n\n' + msg['message'].replace(u'[BR]', u'\n').strip()
        
        self.text.setText(text)



class Review(Handler):
    def handle(self):
        self.kinopoisk = KinoPoisk()
        stat = self.kinopoisk.review(self.argv['id'], 'stat')
        
        if stat is None:
            xbmcgui.Dialog().ok('Kinopoisk', *self.lang[30001].split('|'))
        elif stat['all'] == 0:
            xbmcgui.Dialog().ok('Kinopoisk', self.lang[30009])
        else:
            
            self.langs = {
                'all': self.lang[90014],
                'good': self.lang[90011],
                'bad': self.lang[90012],
                'neutral': self.lang[90013]
            }
            
            menu = []
            for tag in ('good', 'bad', 'neutral', 'all'):
                menu.append((tag, self.langs[tag] + u' (' + str(stat[tag]) + u')'))
            
            sel = xbmcgui.Dialog()
            r = sel.select(self.lang[90001], [x[1] for x in menu])
            if r > -1:
                
                gui = GuiReview('DialogTextViewer.xml', sys.argv[0], id=self.argv['id'], query=menu[r][0])
                gui.doModal()
                del gui
                    
        return True
                
    
class GuiReview(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.id = kwargs['id']
        self.query = kwargs['query']
        xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
        
    def onInit(self):
        self._lang = Lang()
        self.lang = {
            'review': self._lang[40007],
            'load': self._lang[30105],
            'count': self._lang[30112]
        }
        
        self.label = self.getControl(1)
        self.text = self.getControl(5)
        
        self.kinopoisk = KinoPoisk()
        self.review = []
        if self.load():
            self.cursor = 0
            self.render()
        
    def onFocus(self, control):
        pass
    
    def onAction(self, action):
        id = action.getId()
        if id == 1:
            self.left()
        elif id == 2:
            self.right()
        elif id in (9, 10, 92):
            self.close()
    
    def left(self):
        if not self.lock:
            if self.cursor > 0:
                self.cursor -= 1
                self.render()
                
    
    def right(self):
        if not self.lock:
            if self.cursor + 1 < len(self.review):
                self.cursor += 1
                self.render()
            
    
    def load(self):
        self.lock = True
        self.label.setLabel(self.lang['review'])
        self.text.setText(self.lang['load'])
        
        data = self.kinopoisk.review(self.id, self.query)
        
        if not data:
            if data is None:
                err = 30001
            else:
                err = 30009
            xbmcgui.Dialog().ok('Kinopoisk', *self._lang[err].split('|'))
            return False
        
        self.review = data[:]
        self.lock = False
        return True
            
            
    def render(self):
        self.label.setLabel(self.lang['review'] + u':  ' + str(self.cursor + 1) + u'/' + str(len(self.review)))
        
        msg = self.review[self.cursor]
        text = u''
        
        if msg['time']:
            text += msg['time'] + '\n'
        
        text += u'[COLOR FF0DA09E][B]' + msg['nick'] + u'[/B][/COLOR]'
        
        if msg['count']:
            text += u'   [ ' + self.lang['count'] + u':  ' + str(msg['count']) + u' ]'
        
        text += u'\n\n\n'
        
        if msg['title']:
            text += u'[COLOR FF0DA09E][B]' + msg['title'] + u'[/B][/COLOR]\n\n'
        
        text += msg['review'].replace(u'\n', u'\n\n').strip()
        
        self.text.setText(text)




plugin = Plugin(Menu)

plugin.route('menu-rutracker', MenuRutracker)
plugin.route('menu-kinopoisk', MenuKinopoisk)

plugin.route('rutracker-folder', RutrackerFolder)
plugin.route('rutracker-search', RutrackerSearch)

plugin.route('kinopoisk-best-query', KinopoiskBestQuery)
plugin.route('kinopoisk-best', KinopoiskBest)
plugin.route('kinopoisk-search', KinopoiskSearch)
plugin.route('kinopoisk-person', KinopoiskPerson)
plugin.route('kinopoisk-work', KinopoiskWork)

plugin.route('bookmark', Bookmark)
plugin.route('bookmark-add', BookmarkAdd)

plugin.route('download', Download)
plugin.route('stream', Stream)

plugin.route('force-cache', ForceCache)
plugin.route('setting', Setting)
plugin.route('info', Info)
plugin.route('trailer', Trailer)
plugin.route('screenshot', Screenshot)
plugin.route('status', Status)
plugin.route('flush-cache', FlushCache)
plugin.route('descript', Descript)
plugin.route('comment', Comment)
plugin.route('review', Review)

plugin.run(fanart=True)
