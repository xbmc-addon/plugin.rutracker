# -*- coding: utf-8 -*-

import re
import cookielib

from xbmcup.app import Setting
from xbmcup.net import HTTP
from xbmcup.cache import Cache
from xbmcup.html import Clear

import xbmc
import xbmcgui

class RuTracker:
    def __init__(self, expire=0, size=0):
        
        self.cache_catalog = Cache('rutracker_catalog.db')
        self.cache_profile = Cache('rutracker_profile.db', expire, size)
        
        self.http = RuTrackerHTTP()
        
        self.re = {
            'is_int': re.compile(r'^([0-9]+)', re.U),
            'is_float': re.compile(r'^([0-9]{1,10}\.[0-9]+)', re.U),
            'hash': re.compile(r'<span id="tor-hash">([0-9A-F]{40})</span>', re.U)
        }
        
        self.html = Clear()
        
        self.status = {
            '%': 'check',
            'D': 'repeat',
            '!': 'nodesc',
            '&copy;': 'copyright',
            '&#8719;': 'moder',
            'x': 'close',
            '&sum;': 'absorb',
            
            '#': 'doubtful',
            '*': 'nocheck',
            '?': 'neededit',
            'T': 'temp',
            
            '&radic;': 'ok'
        }
    
    # API
    
    def get(self, id=None, page=1):
        """
            Получение списка директорий и раздач
            
            На вход функции надо подавать следующие параметры:
                id      - [int] id директории
                page    - [int] номер страницы
            
            Возвращает словарь, состоящий из следующих полей:
                pages  - [list] кортеж [int] для навигации = (кол-во страниц, предыдущая, текущая, следующая)
                data   - [list] данные выборки, состоящая из следующих полей:
                    
                    id            - [int] id (для директорий и топиков ID могут совпадать)
                    name          - [str] имя записи
                    type          - [str] тип записи (torrent - торрент, folder - директория)
                    
                    size          - [int] размер раздачи в байтах
                    seeder        - [int] кол-во сидов
                    leecher       - [int] кол-во личеров
                    download      - [int] кол-во скачиваний торрента
                    comment       - [int] кол-во комментариев
                    status        - [str] символ отметки модератора
                    status_human  - [str] отметка модератора в удобочитаемом виде (описание смотри ниже).
            
            Описание возвращаемых отметок status_human:
                Скачать торрент нельзя (красный):  moder - премодерация, check - проверяется, repeat - повтор, nodesc - не оформлено, copyright - закрыто правообладателем, close - закрыто, absorb - поглощено.
                Скачать торрент можно   (желтый):  nocheck - не проверено, neededit - недооформлено, doubtful - сомнительно, temp - временная
                Скачать торрент можно  (зеленый):  ok - проверено
        """
        
        # INDEX
        if id is None:
            html = self.http.get('http://rutracker.cr/forum/index.php')
            if not html:
                return html
            
            res = []

            r = re.compile(r'<div\sid="forums_wrap">(.+)<div\sclass="bottom_info">', re.U|re.S).search(html)
            if r:
                
                r = re.compile(r'<h4\sclass="forumlink"><a\shref="viewforum\.php\?f=([0-9]+)">(.+?)</a></h4>', re.U|re.S).findall(r.group(1))
                if r:
                    res = [{'id': int(i), 'name': self.html.string(x), 'type': 'folder'} for i, x in r]
            
            if not res:
                return None
            return {'pages': (1, 0, 1, 0), 'data': res}
        
        else:
            page_query = ''
            if page > 1:
                page_query = '&start=' + str(50*(page-1))
            
            html = self.http.get('http://rutracker.cr/forum/viewforum.php?f=' + str(id) + '&sort=2' + page_query)
            if not html:
                return html
            
            pages = self._compile_pages(html)
            
            folder = []
            torrent = []
            
            group_list = re.compile(r'<table class="forumline forum">(.+?)</table>', re.U|re.S).findall(html)
            if group_list:
                for group in group_list:
                    
                    # вытаскиваем папки (если есть)
                    r = re.compile(r'<h4\sclass="forumlink"><a\shref="viewforum\.php\?f=([0-9]+)">(.+?)</a></h4>', re.U|re.S).findall(group)
                    if r:
                        folder.extend([{'id': int(i), 'name': self.html.string(x), 'type': 'folder'} for i, x in r])

                    # нарубаем на строчки топиков
                    topic_list = group.split(u'topicSep">')
                    if len(topic_list) > 1:
                        topic_list = topic_list[1:]
                    
                    for html in topic_list:
                        
                        # вытаскиваем id
                        for text in re.compile(r'<tr\sid="tr\-[0-9]+"(.+?)</tr>', re.U|re.S).findall(html):
                            item = self._compile_topic(text)
                            if item:
                                torrent.append(item)

            
            folder.extend(torrent)

            return {'pages': pages, 'data': folder}
    
    
    def search(self, search, folder=None, index=None, ignore=None):
        """
            Поиск по РуТрекеру
            
            На вход функции надо подавать следующие параметры:
                search  - [str] поисковая строка запроса (Unicode)
                folder  - [list] список ID директорий, в которых необходимо искать (None - искать везде)
                
            Возвращает словарь, аналогичный выводу метода GET
        """

        if isinstance(search, unicode):
            search = search.encode('windows-1251')
        
        # проверяем авторизацию
        html = self.http.get('http://rutracker.cr/forum/index.php')
        if not html:
            return html
        
        # готовим запрос для получения дерева разделов
        if folder:
            if not isinstance(folder, list) and not isinstance(folder, tuple):
                folder = [folder]
        else:
            if index is not None:
                if not isinstance(index, list) and not isinstance(index, tuple):
                    index = [index]
            if ignore is not None:
                if not isinstance(ignore, list) and not isinstance(ignore, tuple):
                    ignore = [ignore]
            if not index and not ignore:
                folder = []
            else:
                folder = self._load_catalog(index, ignore)
                if not folder:
                    return folder


        # готовим запрос
        params = [('nm', search), ('o', 10), ('s', 2), ('prev_my', 0), ('prev_new', 0), ('prev_oop', 0), ('submit', r'Поиск')]
        params.extend([('f[]', x) for x in folder])

        # делаем поиск
        html = self.http.post('http://rutracker.cr/forum/tracker.php', params)
        if not html:
            return html

        res = []
        table = re.compile('id="tor\-tbl">(.+?)</table>', re.U|re.S).search(html)
        if table:
            for tr in re.compile('<tr\sclass="tCenter\shl\-tr">(.+?)</tr>', re.U|re.S).findall(table.group(1)):
                item = self._compile_topic(tr, True)
                if item:
                    res.append(item)
        
        return {'pages': (1, 0, 1, 0), 'data': res}
        
    
    
    def profile(self, id):
        """
            Получение дополнительной информации о раздачи
            
            На вход функции надо подавать следующие параметры:
                id  - [int] id топика с раздачей
                
            Возвращает словарь, состоящий из:
                descript    - [str] описание на RuTracker
                cover       - [str] url обложки
                screenshot  - [list] Список url скриншотов
        """
        return self.cache_profile.get('profile:' + str(id), self._profile, id)
    
    def comment(self, id, page=1):
        """
            Получение комментариев раздачи
            
            На вход функции надо подавать следующие параметры:
                id      - [int] id топика
                page    - [int] номер страницы
            
            Возвращает словарь, состоящий из следующих полей:
                pages  - [list] кортеж [int] для навигации = (кол-во страниц, предыдущая, текущая, следующая)
                data   - [list] данные выборки - список словарей, состоящих из следующих полей:
                    
                    nick      - [str] ник автора комментария
                    usertime  - [str] стаж юзера
                    count     - [str] кол-во сообщений у юзера
                    location  - [str] откуда юзер
                    time      - [str] время добавления комментария
                    message   - [str] комментарий
        """
        page_query = ''
        if page > 1:
            page_query = '&start=' + str(30*(page-1))
            
        html = self.http.get('http://rutracker.cr/forum/viewtopic.php?t=' + str(id) + page_query)
        if not html:
            return html
        
        res = {
            'pages': self._compile_pages(html),
            'comments': []
        }
        
        # нарубаем страницу по постам
        rows = re.compile('<tbody id="post_[0-9]+" class="row1|2">(.+?)<!\-\-/post_body\-\->', re.U|re.S).findall(html)
        if rows:
            if page == 1:
                rows.pop(0)
            if rows:
                
                # функция для очистки комментариев
                def _def_subn1(m):
                    return u'<div class="q-wrap"><div class="q">' + self.html.string(m.group(1)) + u':\n'
                    
                def _def_subn2(m):
                    r = u'[BR][I]' + m.group(1).replace(u'[I]', u'').replace(u'[/I]', u'') + u'[/I][BR]'
                    n = 1
                    while n:
                        r, n = re.compile(u'\[BR\]\[BR\]', re.U|re.S).subn(u'[BR]', r)
                    return r
                    
                    
                for html in rows:
                    
                    comment = {
                        'nick': None,
                        'usertime': None,
                        'count': None,
                        'location': u'',
                        'time': None,
                        'message': None
                    }
                    
                    # вытаскиваем ник
                    r = re.compile('<p class="nick[^>]+>([^<]+)</p>', re.U).search(html)
                    if r:
                        comment['nick'] = self.html.string(r.group(1).strip())
                    
                    # смотрим стаж
                    r = re.compile(u'<p class="joined"><em>Стаж:</em>([^<]+)</p>', re.U).search(html)
                    if r:
                        comment['usertime'] = r.group(1).strip()
                    
                    # смотрим кол-во коментов у юзера
                    r = re.compile(u'<p class="posts"><em>Сообщений:</em>([^<]+)</p>', re.U).search(html)
                    if r:
                        comment['count'] = r.group(1).strip()
                    
                    # смотрим город юзера
                    r = re.compile(u'<p class="from"><em>Откуда:</em>([^<]+)</p>', re.U).search(html)
                    if r:
                        comment['location'] = r.group(1).strip()
                    
                    # смотрим страну юзера
                    r = re.compile('<p class="flag"><img [^>]*title="([^"]+)"[^>]*></p>', re.U).search(html)
                    if r:
                        if comment['location']:
                            comment['location'] += u', '
                        comment['location'] += r.group(1).strip()
                    
                    # смотрим время коммента
                    r = re.compile('<a class="small" href="\./viewtopic.php\?p=[^>]+>([0-9]{1,2}\-[^\-]+\-[0-9]{2} [0-9]{1,2}\:[0-9]{1,2})</a>', re.U).search(html)
                    if r:
                        comment['time'] = r.group(1).strip()
                    
                    # вытаскиваем тело коммента
                    r = re.compile('<div class="post_body"[^>]+>(.+)$', re.U|re.S).search(html)
                    if r:
                        html = r.group(1).strip()
                        if html:
                            
                            # заменяем что можем...
                            for reg, rep in (
                                    ('<span class="post\-b">([^(?:</span>)]+)</span>', u'[B]\g<1>[/B]'),
                                ):
                                html = re.compile(reg, re.U|re.S).sub(rep, html)
                            
                            # конвертируем цитаты
                            html, n = re.compile('<div class="q-wrap">\s*<div class="q" head="([^"]+)">', re.U|re.S).subn(_def_subn1, html)
                            n = 1
                            while n:
                                html, n = re.compile('<div class="q-wrap">\s*<div class="q">(.+?)</div>\s*</div>', re.U|re.S).subn(_def_subn2, html)
                            
                            # прогоняем через полную очистку
                            comment['message'] = self.html.text(html)
                    
                    if comment['nick'] and comment['message']:
                        res['comments'].append(comment)
        
        return res
    
    
    def download(self, id):
        """
            Скачивание торрента раздачи
            
            На вход функции надо подавать следующие параметры:
                id        - [str] топика с раздачей
                
            Возвращает торрент или None (в случае неудачи)
        """
        return self.http.download(id)


    def hash(self, id):
        """
            Получение инфо-хеша раздачи

            На вход функции надо подавать следующие параметры:
                id        - [str] топика с раздачей

            Возвращает шеснадцатеричное число хэша (в виде строки) или None (в случае неудачи)
        """
        return self.cache_profile.get('hash:' + str(id), self._hash, id)


    def magnet(self, id):
        """
            Получение инфо-хеша раздачи

            На вход функции надо подавать следующие параметры:
                id        - [str] топика с раздачей

            Возвращает шеснадцатеричное число хэша (в виде строки) или None (в случае неудачи)
        """
        hash = self.hash(id)
        if hash:
            return 'magnet:?xt=urn:btih:' + hash
        return hash
        
    
    
    # PRIVATE
    
    def _compile_pages(self, text):
        r = re.compile(u'<p style="float\: left">Страница <b>([0-9]+)</b> из <b>([0-9]+)</b></p>', re.U|re.S).search(text)
        if r:
            current = int(r.group(1))
            total = int(r.group(2))
            next = current + 1
            if next > total:
                next = 0
            return total, current-1, current, next
        return 1, 0, 1, 0
    
    def _compile_topic(self, text, is_search=False):
        r = re.compile(r'<a\s[^>]*href="viewtopic\.php\?t=([0-9]+)"[^>]*>(.+?)</a>', re.U|re.S).search(text)
        if r:
            id = r.group(1)
            name = self.html.string(r.group(2))

            r = re.compile(r'<a[^>]+href="dl\.php\?t=' + id + '"[^>]*>(.+?)</a>', re.U|re.S).search(text)
            if r:
                size = self._compile_size(r.group(1))
                if size and name:
                    
                    item = self._create_torrent(int(id), name)
                    
                    item['size'] = size
                    
                    r = re.compile(r'"tor-icon[^>]+>([^<]+)<', re.U|re.S).search(text)
                    if r:
                        stat = r.group(1)
                        try:
                            status = self.status[stat]
                        except KeyError:
                            pass
                        else:
                            item['status'] = self.html.char(stat)
                            item['status_human'] = status
                    
                    if is_search:
                        item['comment'] = -1
                        query = (('download', '<td\sclass="row4\ssmall">([0-9]+)</td>'), ('seeder', '<b class="seedmed">([0-9]+)</b></td>'), ('leecher', '<td\sclass="row4 leechmed"[^>]+><b>([0-9]+)</b></td>'))
                    else:
                        query = (('comment', u'<span title="Ответов">([0-9]+)</span>'), ('download', u'title="Торрент скачан">[^<]*<b>([0-9]+)</b>[^<]*</p>'), ('seeder', 'title="Seeders"><b>([0-9]+)</b></span>'), ('leecher', 'title="Leechers"><b>([0-9]+)</b></span>'))
                    
                    for tag, reg in query:
                        r = re.compile(reg, re.U|re.S).search(text)
                        if r:
                            item[tag] = int(r.group(1))
                    
                    return item
        
        return None
    
    def _create_torrent(self, id, name):
        return {
            'id': id,
            'name': name,
            'type': 'torrent',
            'size': 0,
            'seeder': 0,
            'leecher': 0,
            'download': 0,
            'comment': 0,
            'status': None,
            'status_human': None
        }
    
    def _compile_size(self, text):
        text = self.html.string(text.replace(u'&#8595;', u''))
        if text:
            text = text.lower()
            prefix = 1
            for p, v in ((u'kb', 1024), (u'mb', 1024*1024), (u'gb', 1024*1024*1024), (u'tb', 1024*1024*1024*1024)):
                if text.find(p) != -1:
                    prefix = v
                    text = text.replace(p, u'').strip()
                    break
            
            num = self.re['is_float'].search(text)
            if num:
                return int(float(prefix)*float(num.group(1)))
            
            num = self.re['is_int'].search(text)
            if num:
                return prefix*int(num.group(1))
            
        return None

    def _hash(self, id):
        html = self.http.get('http://rutracker.cr/forum/viewtopic.php?t=' + str(id))
        if not html:
            return False, html
        r = self.re['hash'].search(html)
        if not r:
            return False, None
        return True, str(r.group(1))
    
    def _profile(self, id):
        html = self.http.guest('http://rutracker.cr/forum/viewtopic.php?t=' + str(id))
        if not html:
            return False, html
        
        res = {
            'descript': None,
            'cover': None,
            'screenshot': None
        }

        r = re.compile('<div class="post_body"[^>]+>(.+?)<legend>Download</legend>', re.U|re.S).search(html)
        if r:

            html = r.group(1)

            # ищем коверы (перебирая все возможные варианты хостингов картинок)
            for api in (self.pic_hosting_fastpic, ):
                cover = api('cover', html)
                if cover:
                    res['cover'] = cover
                    break

            # вытаскиваем блок со скриншотами
            r = re.compile(u'<span>Скриншоты</span></div>(.+?)</div>', re.U|re.S).search(html)
            if r:
                body = r.group(1)
                
                # ищем скрины (перебирая все возможные варианты хостингов картинок)
                for api in (self.pic_hosting_fastpic, ):
                    screenshot = api('screenshot', body)
                    if screenshot:
                        res['screenshot'] = screenshot
                        break

            # пытаемся получить текст описания
            # режем и заменяем все что можем...
            for reg, rep in (

                    (u'<div class="sp\-wrap">.+?<div class="sp-body">.+?</div>', u''), # удаляем все спойлеры
                    (u'<var[^>]+>[^<]+</var>', u''), # удаляем все изображения
                    (u'<span class="post\-hr">\-</span>', u'\n'), # удаляем HR
                    (u'<span class="post\-b">([^<]+)</span>', u'[COLOR FF0DA09E]\g<1>[/COLOR]') # заменяем болды

                ):
                html = re.compile(reg, re.U|re.S).sub(rep, html)

            # прогоняем через полную очистку
            html = self.html.text(html)
            if html:
                res['descript'] = html

        return True, res
    
    
    # CATALOG
    def _load_catalog(self, index, ignore):
        catalog = self.cache_catalog.get('catalog', self._load_catalog_http)
        if not catalog:
            return []
        
        res = []
        for key, folders in catalog.iteritems():
            if index is None or key in index:
                res.extend([x for x in folders if x not in ignore])
                
        return res
    
    def _load_catalog_http(self):
        html = self.http.get('http://rutracker.cr/forum/tracker.php')
        if not html:
            return html
        
        r = re.compile('<select id="fs-main"(.+?)</select>', re.U|re.S).search(html)
        if not r:
            return None
        
        res = {}
        root = None
        for cat, is_root_forum in re.compile('<option id="fs\-([0-9]+)"([^>]+)>', re.U).findall(r.group(1)):
            cat = int(cat)
            if is_root_forum.find('root_forum') != -1:
                root = cat
                res[root] = [cat]
            elif root:
                res[root].append(cat)
        
        return (86400 if res else False), res # day
    
    
    # SCREENSHOT
    
    def pic_hosting_fastpic(self, img, html):
        if img == 'cover':
            r = re.compile('<var[^>]+class="postImg postImgAligned img\-right"[^>]+title="(http\://[0-9a-z]+\.fastpic\.ru/big/[0-9a-f/]+\.[a-z]{3,4})"[^>]*>', re.U|re.S).search(html)
            if r:
                return r.group(1)
            return None
        else:
            res = []
            for r in re.compile('<a[^>]*href="http\://fastpic\.ru/view/[^\.]+\.([a-z]{3,4})\.html"[^>]*>[.]*?<var[^>]+title="(http\://[0-9a-z]+\.fastpic\.ru/thumb/[0-9a-f/]+)\.[a-z]{3,4}"[^>]*>', re.U|re.S).findall(html):
                res.append('.'.join([r[1].replace('thumb', 'big'), r[0]]))
            return res if res else None
        
        

class RuTrackerHTTP:
    def __init__(self):
        self.setting = Setting()
        self.re_auth = re.compile(r'profile\.php\?mode=sendpassword"')
        self.re_captcha = re.compile(r'<img src="(\/\/[^\/]+/captcha/[^"]+)"')
        self.re_captcha_sid = re.compile(r'<input type="hidden" name="cap_sid" value="([^"]+)">')
        self.re_captcha_code = re.compile(r'<input type="text" name="(cap_code_[^"]+)"')
        self.captcha_sid = None
        self.captcha_code = None
        self.captcha_code_value = None
        self.http = HTTP()
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-ru,ru;q=0.8,en-us;q=0.5,en;q=0.3',
            'Cache-Control': 'no-cache',
            'Referer': 'http://rutracker.cr/forum/index.php'
        }
    
    def guest(self, url):
        response = self.http.fetch(url, headers=self.headers)
        if response.error:
            return None
        else:
            body = response.body.decode('windows-1251')
            if body.find(u'>форум временно отключен</p>') != -1:
                return 0
            return body
    
    def get(self, url):
        return self._fetch('GET', url)
    
    def post(self, url, params):
        return self._fetch('POST', url, params)
    
    def download(self, id):
        id = str(id)

        # проверяем авторизацию
        html = self.get('http://rutracker.cr/forum/viewtopic.php?t=' + id)
        if not html:
            return html

        # хакаем куки
        cookies = cookielib.MozillaCookieJar()
        cookies.load(self.http.request.cookies)
        cookies.set_cookie(cookielib.Cookie(version=0, name='bb_dl', value=id, port=None, port_specified=False, domain='.rutracker.cr', domain_specified=False, domain_initial_dot=False, path='/', path_specified=True, secure=False, expires=None, discard=True, comment=None, comment_url=None, rest={'HttpOnly': None}, rfc2109=False))
        cookies.save(self.http.request.cookies, ignore_discard=True, ignore_expires=True)

        # тянем торрент
        response = self.http.fetch('http://rutracker.cr/forum/dl.php?t=' + id, cookies='rutracker.moz', headers=self.headers, method='POST')
        if response.error:
            return None
        else:
            return response.body
    
    
    def _fetch(self, method, url, params=None):
        while True:
            response = self.http.fetch(url, cookies='rutracker.moz', headers=self.headers, method=method, params=params)
            if response.error:
                return None
            else:
                body = response.body.decode('windows-1251')
                if body.find(u'>форум временно отключен</p>') != -1:
                    return 0
                if not self.re_auth.search(body):
                    return body
                xbmc.log('RUTRACKER: Request auth', xbmc.LOGDEBUG)
                auth = self._auth()
                if not auth:
                    return auth
        
    def _auth(self):
        self.captcha_sid, self.captcha_code, self.captcha_code_value = None, None, None
        while True:
            login = self.setting['rutracker_login']
            password = self.setting['rutracker_password']
            if not login or not password:
                self.setting.dialog()
                login = self.setting['rutracker_login']
                password = self.setting['rutracker_password']
                if not login or not password:
                    return None

            params = {'login_username': login, 'login_password': password, 'login': r'вход'}
            if self.captcha_sid:
                params['login'] = r'Вход'
                params['cap_sid'] = self.captcha_sid
                params[self.captcha_code] = self.captcha_code_value

            response = self.http.fetch('http://rutracker.cr/forum/login.php', cookies='rutracker.moz', headers=self.headers, method='POST', params=params)
            self.captcha_sid, self.captcha_code, self.captcha_code_value = None, None, None
            if response.error:
                return None

            body = response.body.decode('windows-1251')

            if body.find(u'>форум временно отключен</p>') != -1:
                return 0

            if not self.re_auth.search(body):
                return True

            # проверяем капчу
            r = self.re_captcha.search(body)
            if r:
                r_sid = self.re_captcha_sid.search(body)
                if not r_sid:
                    return None
                self.captcha_sid = r_sid.group(1)
                r_code = self.re_captcha_code.search(body)
                if not r_code:
                    return None
                self.captcha_code = r_code.group(1)
                self.captcha_code_value = self._captcha('http:' + r.group(1))
                if not self.captcha_code_value:
                    return None

            # get login
            k = xbmc.Keyboard('', 'Enter login')
            k.doModal()
            if k.isConfirmed():
                login = k.getText()
            else:
                return None

            # get password
            k = xbmc.Keyboard('', 'Enter password', True)
            k.doModal()
            if k.isConfirmed():
                password = k.getText()
            else:
                return None

            if not login or not password:
                return None

            self.setting['rutracker_login'] = login
            self.setting['rutracker_password'] = password


    def _captcha(self, captcha):
        response = self.http.fetch(captcha, headers=self.headers, method='GET')
        if response.error:
            return

        import tempfile
        filename = tempfile.gettempdir() + '/captcha'
        file(filename, 'wb').write(response.body)

        win = xbmcgui.Window(xbmcgui.getCurrentWindowId())

        # width = 120px, height = 72px
        image = xbmcgui.ControlImage(win.getWidth()/2 - int(120/2), 20, 120, 72, filename)
        win.addControl(image)
        k = xbmc.Keyboard('', 'Enter captcha code')
        k.doModal()
        code = k.getText() if k.isConfirmed() else None
        win.removeControl(image)
        return code if code else None
