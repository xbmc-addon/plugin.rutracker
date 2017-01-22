# -*- coding: utf-8 -*-

import os
import sys
import time
import re
import urllib
import urllib2
import cookielib
import base64
import mimetools
import json
import itertools
import thread
import tempfile

try:
    import libtorrent
except ImportError:
    _IS_LIBTORRENT = False
else:
    _IS_LIBTORRENT = True

try:
    from TSCore import TSengine
except ImportError:
    _IS_TORRENTSTREAM = False
else:
    _IS_TORRENTSTREAM = True


import xbmc, xbmcgui, xbmcaddon, xbmcvfs

RE = {
    'content-disposition': re.compile('attachment;\sfilename="*([^"\s]+)"|\s')
}

# ################################
#
#   HTTP
#
# ################################

class HTTP:
    def __init__(self):
        self._dirname = xbmc.translatePath('special://temp')
        for subdir in ('xbmcup', sys.argv[0].replace('plugin://', '').replace('/', '')):
            self._dirname = os.path.join(self._dirname, subdir)
            if not xbmcvfs.exists(self._dirname):
                xbmcvfs.mkdir(self._dirname)
    
    
    def fetch(self, request, **kwargs):
        self.con, self.fd, self.progress, self.cookies, self.request = None, None, None, None, request
        
        if not isinstance(self.request, HTTPRequest):
            self.request = HTTPRequest(url=self.request, **kwargs)
        
        self.response = HTTPResponse(self.request)
        
        xbmc.log('XBMCup: HTTP: request: ' + str(self.request), xbmc.LOGDEBUG)
        
        try:
            self._opener()
            self._fetch()
        except Exception, e:
            xbmc.log('XBMCup: HTTP: ' + str(e), xbmc.LOGERROR)
            if isinstance(e, urllib2.HTTPError):
                self.response.code = e.code
            self.response.error = e
        else:
            self.response.code = 200
        
        if self.fd:
            self.fd.close()
            self.fd = None
            
        if self.con:
            self.con.close()
            self.con = None
        
        if self.progress:
            self.progress.close()
            self.progress = None
        
        self.response.time = time.time() - self.response.time
        
        xbmc.log('XBMCup: HTTP: response: ' + str(self.response), xbmc.LOGDEBUG)
        
        return self.response
            
    
    def _opener(self):
        
        build = [urllib2.HTTPHandler()]
        
        if self.request.redirect:
            build.append(urllib2.HTTPRedirectHandler())
        
        if self.request.proxy_host and self.request.proxy_port:
            build.append(urllib2.ProxyHandler({self.request.proxy_protocol: self.request.proxy_host + ':' + str(self.request.proxy_port)}))
            
            if self.request.proxy_username:
                proxy_auth_handler = urllib2.ProxyBasicAuthHandler()
                proxy_auth_handler.add_password('realm', 'uri', self.request.proxy_username, self.request.proxy_password)
                build.append(proxy_auth_handler)
        
        if self.request.cookies:
            self.request.cookies = os.path.join(self._dirname, self.request.cookies)
            self.cookies = cookielib.MozillaCookieJar()
            if os.path.isfile(self.request.cookies):
                self.cookies.load(self.request.cookies)
            build.append(urllib2.HTTPCookieProcessor(self.cookies))
                
        urllib2.install_opener( urllib2.build_opener(*build) )
    
    
    def _fetch(self):
        params = {} if self.request.params is None else self.request.params
        
        if self.request.upload:
            boundary, upload = self._upload(self.request.upload, params)
            req = urllib2.Request(self.request.url)
            req.add_data(upload)
        else:
            
            if self.request.method == 'POST':
                if isinstance(params, dict) or isinstance(params, list):
                    params = urllib.urlencode(params)
                req = urllib2.Request(self.request.url, params)
            else:
                req = urllib2.Request(self.request.url)
        
        for key, value in self.request.headers.iteritems():
            req.add_header(key, value)
        
        if self.request.upload:
            req.add_header('Content-type', 'multipart/form-data; boundary=%s' % boundary)
            req.add_header('Content-length', len(upload))
        
        if self.request.auth_username and self.request.auth_password:
            req.add_header('Authorization', 'Basic %s' % base64.encodestring(':'.join([self.request.auth_username, self.request.auth_password])).strip())
        
        #self.con = urllib2.urlopen(req, timeout=self.request.timeout)
        self.con = urllib2.urlopen(req)
        self.response.headers = self._headers( self.con.info() )
        
        if self.request.download:
            self._download()
        else:
            self.response.body = self.con.read()
        
        if self.request.cookies:
            self.cookies.save(self.request.cookies)
    
    
    def _download(self):
        fd = open(self.request.download, 'wb')
        if self.request.progress:
            self.progress = xbmcgui.DialogProgress()
            self.progress.create(u'Download')
        
        bs = 1024*8
        size = -1
        read = 0
        name = None
        
        if self.request.progress:
            if 'content-length' in self.response.headers:
                size = int(self.response.headers['content-length'])
            if 'content-disposition' in self.response.headers:
                r = RE['content-disposition'].search(self.response.headers['content-disposition'])
                if r:
                    name = urllib.unquote(r.group(1))
        
        while 1:
            buf = self.con.read(bs)
            if buf == '':
                break
            read += len(buf)
            fd.write(buf)
            
            if self.request.progress:
                self.progress.update(*self._progress(read, size, name))
        
        self.response.filename = self.request.download
    
    
    def _upload(self, upload, params):
        res = []
        boundary = mimetools.choose_boundary()
        part_boundary = '--' + boundary
        
        if params:
            for name, value in params.iteritems():
                res.append([part_boundary, 'Content-Disposition: form-data; name="%s"' % name, '', value])
        
        if isinstance(upload, dict):
            upload = [upload]
            
        for obj in upload:
            name = obj.get('name')
            filename = obj.get('filename', 'default')
            content_type = obj.get('content-type')
            try:
                body = obj['body'].read()
            except AttributeError:
                body = obj['body']
            
            if content_type:
                res.append([part_boundary, 'Content-Disposition: file; name="%s"; filename="%s"' % (name, urllib.quote(filename)), 'Content-Type: %s' % content_type, '', body])
            else:
                res.append([part_boundary, 'Content-Disposition: file; name="%s"; filename="%s"' % (name, urllib.quote(filename)), '', body])
        
        result = list(itertools.chain(*res))
        result.append('--' + boundary + '--')
        result.append('')
        return boundary, '\r\n'.join(result)
        
    
    def _headers(self, raw):
        headers = {}
        for line in raw.headers:
            pair = line.split(':', 1)
            if len(pair) == 2:
                tag = pair[0].lower().strip()
                value = pair[1].strip()
                if tag and value:
                    headers[tag] = value
        return headers
    
    
    def _progress(self, read, size, name):
        res = []
        if size < 0:
            res.append(1)
        else:
            res.append(int( float(read)/(float(size)/100.0) ))
        if name:
            res.append(u'File: ' + name)
        if size != -1:
            res.append(u'Size: ' + self._human(size))
        res.append(u'Load: ' + self._human(read))
        return res
    
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
    
        
        

class HTTPRequest:
    def __init__(self, url, method='GET', headers=None, cookies=None, params=None, upload=None, download=None, progress=False, auth_username=None, auth_password=None, proxy_protocol='http', proxy_host=None, proxy_port=None, proxy_username=None, proxy_password='', timeout=20.0, redirect=True, gzip=False):
        
        if headers is None:
            headers = {}
        
        self.url = url
        self.method = method
        self.headers = headers
        
        self.cookies = cookies
        
        self.params = params
        
        self.upload = upload
        self.download = download
        self.progress = progress
        
        self.auth_username = auth_username
        self.auth_password = auth_password
        
        self.proxy_protocol = proxy_protocol
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        
        self.timeout = timeout
        
        self.redirect = redirect
        
        self.gzip = gzip
    
    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, ','.join('%s=%r' % i for i in self.__dict__.iteritems()))


class HTTPResponse:
    def __init__(self, request):
        self.request = request
        self.code = None
        self.headers = {}
        self.error = None
        self.body = None
        self.filename = None
        self.time = time.time()
    
    def __repr__(self):
        args = ','.join('%s=%r' % i for i in self.__dict__.iteritems() if i[0] != 'body')
        if self.body:
            args += ',body=<data>'
        else:
            args += ',body=None'
        return '%s(%s)' % (self.__class__.__name__, args)


# ################################
#
#   TORRENT
#
# ################################

class Torrent:
    def __init__(self, client, **kwargs):
        if client == 'utorrent':
            self.client = UTorrent()
        
        elif client == 'transmission':
            self.client = Transmission()
        
        self.client.config(login=kwargs.get('login'), password=kwargs.get('password'), host=kwargs.get('host'), port=kwargs.get('port'), url=kwargs.get('url'))
    
    def list(self):
        return self.client.list()
    
    def add(self, torrent, dirname):
        return self.client.add(torrent, dirname)
    
    def delete(self, id):
        return self.client.delete(id)



class UTorrent:
    def config(self, login, password, host, port, url=None):
        self.login = login
        self.password = password
        
        self.url = 'http://' + host
        if port:
            self.url += ':' + str(port)
        self.url += '/gui/'
            
        self.http = HTTP()
        
        self.re = {
            'cookie': re.compile('GUID=([^;]+);'),
            'token': re.compile("<div[^>]+id='token'[^>]*>([^<]+)</div>")
        }
        
        
    
    def list(self):
        obj = self.action('list=1')
        if not obj:
            return None
        
        res = []
        for r in obj.get('torrents', []):
            res.append({
                'id': r[0],
                'status': self.get_status(r[1], r[4]/10),
                'name': r[2],
                'size': r[3],
                'progress': r[4]/10,
                'download': r[5],
                'upload': r[6],
                'ratio': r[7],
                'upspeed': r[8],
                'downspeed': r[9],
                'eta': r[10],
                'peer': r[12] + r[14],
                'leach': r[12],
                'seed': r[14],
                'add': r[23],
                'finish': r[24],
                'dir': r[26]
            })
        
        return res
        
    
    def add(self, torrent, dirname):
        obj = self.action('action=getsettings')
        if not obj:
            return None
        
        old_dir = None
        setting = [x[2] for x in obj['settings'] if x[0] == 'dir_active_download']
        if setting:
            old_dir = setting[0]
        
        if isinstance(dirname, unicode):
            dirname = dirname.encode('windows-1251')
        
        obj = self.action('action=setsetting&s=dir_active_download&v=' + urllib.quote(dirname, ''))
        if not obj:
            return None
        
        res = self.action('action=add-file', {'name': 'torrent_file', 'content-type': 'application/x-bittorrent', 'body': torrent})
        
        if old_dir:
            self.action('action=setsetting&s=dir_active_download&v=' + urllib.quote(old_dir.encode('windows-1251'), ''))
        
        return True if res else None
        
        
    def delete(self, id):
        pass
    
    def action(self, uri, upload=None):
        cookie, token = self.get_token()
        if not cookie:
            return None
        
        req = HTTPRequest(self.url + '?' + uri + '&token=' + token, headers={'Cookie': cookie}, auth_username=self.login, auth_password=self.password)
        if upload:
            req.upload = upload
        
        response = self.http.fetch(req)
        if response.error:
            return None
        else:
            try:
                obj = json.loads(response.body)
            except:
                return None
            else:
                return obj
    
    def get_token(self):
        response = self.http.fetch(self.url + 'token.html', auth_username=self.login, auth_password=self.password)
        if response.error:
            return None, None
        
        r = self.re['cookie'].search(response.headers.get('set-cookie', ''))
        if r:
            cookie = r.group(1).strip()
            r = self.re['token'].search(response.body)
            if r:
                token = r.group(1).strip()
                if cookie and token:
                    return 'GUID=' + cookie, token
                    
        return None, None
    
    def get_status(self, status, progress):
        mapping = {
            'error':            'stopped',
            'paused':           'stopped',
            'forcepaused':      'stopped',
            'notloaded':        'check_pending',
            'checked':          'checking',
            'queued':           'download_pending',
            'downloading':      'downloading',
            'forcedownloading': 'downloading',
            'finished':         'seed_pending',
            'queuedseed':       'seed_pending',
            'seeding':          'seeding',
            'forceseeding':     'seeding'
        }
        return mapping[self.get_status_raw(status, progress)]
        
    
    def get_status_raw(self, status, progress):
        """
            Return status: notloaded, error, checked,
                           paused, forcepaused,
                           queued,
                           downloading, 
                           finished, forcedownloading
                           queuedseed, seeding, forceseeding
        """
        
        
        started = bool( status & 1 )
        checking = bool( status & 2 )
        start_after_check = bool( status & 4 )
        checked = bool( status & 8 )
        error = bool( status & 16 )
        paused = bool( status & 32 )
        queued = bool( status & 64 )
        loaded = bool( status & 128 )
        
        if not loaded:
            return 'notloaded'
        
        if error:
            return 'error'
        
        if checking:
            return 'checked'
        
        if paused:
            if queued:
                return 'paused'
            else:
                return 'forcepaused'
            
        if progress == 100:
            
            if queued:
                if started:
                    return 'seeding'
                else:
                    return 'queuedseed'
                
            else:
                if started:
                    return 'forceseeding'
                else:
                    return 'finished'
        else:
            
            if queued:
                if started:
                    return 'downloading'
                else:
                    return 'queued'
                
            else:
                if started:
                    return 'forcedownloading'
                
        return 'stopped'


class Transmission:
    def config(self, login, password, host, port, url):
        self.login = login
        self.password = password
        
        self.url = 'http://' + host
        if port:
            self.url += ':' + str(port)
        
        if url[0] != '/':
            url = '/' + url
        if url[-1] != '/':
            url += '/'
        
        self.url += url
            
        self.http = HTTP()
        
        self.token = '0'
    
    def list(self):
        obj = self.action({'method': 'torrent-get', 'arguments': {'fields': ['id', 'status', 'name', 'totalSize', 'sizeWhenDone', 'leftUntilDone', 'downloadedEver', 'uploadedEver', 'uploadRatio', 'rateUpload', 'rateDownload', 'eta', 'peersConnected', 'peersFrom', 'addedDate', 'doneDate', 'downloadDir', 'peersConnected', 'peersGettingFromUs', 'peersSendingToUs']}})
        if obj is None:
            return None
        
        res = []
        for r in obj['arguments'].get('torrents', []):
            res.append({
                'id': str(r['id']),
                'status': self.get_status(r['status']),
                'name': r['name'],
                'size': r['totalSize'],
                'progress': 0 if not r['sizeWhenDone'] else int(100.0 * float(r['sizeWhenDone'] - r['leftUntilDone']) / float(r['sizeWhenDone'])),
                'download': r['downloadedEver'],
                'upload': r['uploadedEver'],
                'upspeed': r['rateUpload'],
                'downspeed': r['rateDownload'],
                'ratio': float(r['uploadRatio']),
                'eta': r['eta'],
                'peer': r['peersConnected'],
                'seed': r['peersSendingToUs'],
                'leech': r['peersGettingFromUs'],
                'add': r['addedDate'],
                'finish': r['doneDate'],
                'dir': r['downloadDir']
            })
            
        return res
    
    def add(self, torrent, dirname):
        if self.action({'method': 'torrent-add', 'arguments': {'download-dir': dirname, 'metainfo': base64.b64encode(torrent)}}) is None:
            return None
        return True
    
    def delete(self, id):
        pass
    
    def action(self, request):
        try:
            jsobj = json.dumps(request)
        except:
            return None
        else:
            
            while True:
                # пробуем сделать запрос
                if self.login:
                    response = self.http.fetch(self.url+'rpc/', method='POST', params=jsobj, headers={'x-transmission-session-id': self.token}, auth_username=self.login, auth_password=self.password)
                else:
                    response = self.http.fetch(self.url+'rpc/', method='POST', params=jsobj, headers={'x-transmission-session-id': self.token})
                if response.error:
                    
                    # требуется авторизация?
                    if response.code == 401:
                        if not self.get_auth():
                            return None
                    
                    # требуется новый токен?
                    elif response.code == 409:
                        if not self.get_token(response.error):
                            return None
                    
                    else:
                        return None
                
                else:
                    try:
                        obj = json.loads(response.body)
                    except:
                        return None
                    else:
                        return obj
    
    def get_auth(self):
        response = self.http.fetch(self.url, auth_username=self.login, auth_password=self.password)
        if response.error:
            if response.code == 409:
                return self.get_token(response.error)
        return False
    
    def get_token(self, error):
        token = error.headers.get('x-transmission-session-id')
        if not token:
            return False
        self.token = token
        return True
    
    def get_status(self, code):
        mapping = {
            0: 'stopped',
            1: 'check_pending',
            2: 'checking',
            3: 'download_pending',
            4: 'downloading',
            5: 'seed_pending',
            6: 'seeding'
        }
        return mapping[code]



# ################################
#
#   LIBTORRENT
#
# ################################


class LibTorrentInfo:
    def __init__(self):

        self.lang = self._language()

        self.is_show = False
        self.window = xbmcgui.Window(12005)

        # get resolution
        # https://github.com/steeve/xbmctorrent/blob/master/resources/site-packages/xbmctorrent/player.py#L90
        import xml.etree.ElementTree as ET
        res = ET.parse(os.path.join(xbmc.translatePath('special://skin/'), 'addon.xml')).findall('./extension/res')[0]
        self._width = int(res.attrib['width'])
        self._height = int(res.attrib['height'])

        black = os.path.normpath(os.path.join(os.path.dirname(__file__), '../resources/media/black.jpg'))
        white = os.path.normpath(os.path.join(os.path.dirname(__file__), '../resources/media/white.jpg'))

        self.label = xbmcgui.ControlLabel(self.width(40), self.height(23) + 4, self.width(55), self.height(6), ' ', textColor='0xAAFFFFFF', alignment=5)

        self.controls = [
            xbmcgui.ControlImage(0, self.height(20), self.width(100), self.height(37), black, colorDiffuse='0xDD000000'),
            xbmcgui.ControlImage(0, self.height(31), self.width(100), 1, white, colorDiffuse='0x22FFFFFF'),
            xbmcgui.ControlLabel(self.width(5), self.height(23), self.width(25), self.height(6), '[B]LibTorrent Player[/B]', font='font16', textColor='0xAAFFFFFF'),
            self.label
        ]

        self.progress = {}
        self.percent = {}
        self.bytes = {}

        for i, tag in enumerate(('file', 'total')):
            self.controls.append(xbmcgui.ControlLabel(self.width(5), self.height(34) + self.height(11)*i, self.width(25), self.height(6), self.lang['label_' + tag], textColor='0xAAFFFFFF', alignment=4))
            self.controls.append(xbmcgui.ControlImage(self.width(5), self.height(40) + self.height(11)*i, self.width(90), self.height(2), white, colorDiffuse='0x22FFFFFF'))

            self.bytes[tag] = xbmcgui.ControlLabel(self.width(37), self.height(34) + self.height(11)*i, self.width(50), self.height(6), ' ', textColor='0xAAFFFFFF', alignment=5)
            self.controls.append(self.bytes[tag])

            self.percent[tag] = xbmcgui.ControlLabel(self.width(88), self.height(34) + self.height(11)*i, self.width(7), self.height(6), '[B]0%[/B]', font='font16', textColor='0xAAFFFFFF', alignment=5)
            self.controls.append(self.percent[tag])

            self.progress[tag] = xbmcgui.ControlImage(self.width(5), self.height(40) + self.height(11)*i, 0, self.height(2), white, colorDiffuse='0x77FFFFFF')
            self.controls.append(self.progress[tag])


    def show(self):
        if self.width and not self.is_show:
            self.window.addControls(self.controls)
            self.is_show = True


    def hide(self):
        if self.is_show:
            try:
                self.window.removeControls(self.controls)
            except RuntimeError:
                pass
            self.is_show = False


    def update(self, state, peers, seeds, down_speed, up_speed, download, size, total_download, total_size):
        if state in ('init', 'stop'):
            self.label.setLabel(self.lang[state])
        else:
            speed = self.human(up_speed if state == 'seed' else down_speed, True)
            self.label.setLabel(self.lang['status'] % (seeds, peers, speed, self.lang[state]))

            for tag, b, s in (('file', download, size), ('total', total_download, total_size)):
                percent = self.calc_percent(b, s)
                self.bytes[tag].setLabel(u' / '.join([self.human(b, False), self.human(s, False)]))
                self.percent[tag].setLabel(u'[B]' + str(percent) + u'%[/B]')
                self.progress[tag].setWidth(self.width(0.85*float(percent)))


    def human(self, bytes, is_bit):
        tags = ('kbit', 'mbit', 'gbit', 'tbit') if is_bit else ('kb', 'mb', 'gb', 'tb')
        human = None
        for h, f in ((tags[0], 1024), (tags[1], 1024*1024), (tags[2], 1024*1024*1024), (tags[3], 1024*1024*1024*1024)):
            if bytes/f > 0:
                human = h
                factor = f
            else:
                break
        if human is None:
            return (u'%10.1f %s' % (bytes, self.lang[tags[0]])).replace(u'.0', u'').strip()
        else:
            return (u'%10.2f %s' % (float(bytes)/float(factor), self.lang[human])).strip()


    def calc_percent(self, num, total):
        if not total:
            return 0
        if num == total:
            return 100
        r = int(float(num)*100.0/float(total))
        return 100 if r > 100 else r

    def width(self, percent):
        return int(self._width*(float(percent)/100.0))

    def height(self, percent):
        return int(self._height*(float(percent)/100.0))

    def _language(self):
        tags = dict(
            status = 100000,

            init   = 100001,
            buffer = 100002,
            down   = 100003,
            up     = 100004,
            seed   = 100005,
            stop   = 100006,
            copy   = 100007,

            label_buffer = 100031,
            label_file   = 100032,
            label_total  = 100033,

            b  = 100100,
            kb = 100101,
            mb = 100102,
            gb = 100103,
            tb = 100104,

            bit  = 100200,
            kbit = 100201,
            mbit = 100202,
            gbit = 100203,
            tbit = 100204
        )
        addon = xbmcaddon.Addon('plugin.rutracker')
        lang = {}
        for tag, key in tags.iteritems():
            lang[tag] = addon.getLocalizedString(key)
        return lang



class LibTorrent:
    def __init__(self):
        self.is_install = _IS_LIBTORRENT    
    
    def list(self, torrent, reverse=False):
        files = [{'id': i, 'name': x.path.split(os.sep)[-1], 'size': x.size} for i, x in enumerate(self._torrent_info(torrent).files())]
        files.sort(cmp=lambda f1, f2: cmp(f1['name'], f2['name']))
        if reverse:
            files.reverse()
        return files
        
    
    def play(self, torrent, file_id, dirname, seed=None, info=None, notice=False, buffer=45):
        torrent_info = self._torrent_info(torrent)
        
        # length
        selfile = torrent_info.files()[file_id]
        self._filename = os.path.join(dirname, selfile.path.decode('utf8'))
        self._fname = self._filename.split(os.sep.decode('utf8'))[-1].encode('utf8')
        offset = (buffer+20)*1024*1024 / torrent_info.piece_length()
        start = selfile.offset / torrent_info.piece_length()
        end = (selfile.offset + selfile.size) / torrent_info.piece_length()
        buffer = buffer*1024*1024
        
        # start session
        self._session = libtorrent.session()
        
        # start DHT
        self._session.start_dht()
        self._session.add_dht_router('router.bittorrent.com', 6881)
        self._session.add_dht_router('router.utorrent.com', 6881)
        self._session.add_dht_router('router.bitcomet.com', 6881)
        self._session.listen_on(6881, 6891)
        
        # events
        self._session.set_alert_mask(libtorrent.alert.category_t.storage_notification)
        
        # add torrent
        if seed is not None:
            if seed:
                self._session.set_upload_rate_limit(seed)
            #self._handle = self._session.add_torrent({'ti': torrent_info, 'save_path': dirname.encode('utf8'), 'paused': False, 'auto_managed': False, 'seed_mode': True})
            self._handle = self._session.add_torrent({'ti': torrent_info, 'save_path': dirname.encode('utf8')})
        else:
            self._handle = self._session.add_torrent({'ti': torrent_info, 'save_path': dirname.encode('utf8')})
        
        # low priority
        for i in range(torrent_info.num_pieces()):
            self._handle.piece_priority(i, 0)
        
        # high priority
        for i in range(start, start + offset):
            if i <= end:
                self._handle.piece_priority(i, 7)
        
        # sequential
        self._handle.set_sequential_download(True)
        
        self._stop = False
        self._complete = False
        
        thread.start_new_thread(self._download, (start, end))
        
        percent = 0
        size = 0
        firstsize = selfile.size if selfile.size < buffer else buffer
        persize = firstsize/100
        
        progress = xbmcgui.DialogProgress()
        progress.create(u'Please Wait')
        progress.update(0, self._fname, u'Size: ' + self._human(firstsize) + u' / ' + self._human(selfile.size).strip(), u'Load: ' + self._human(0))
        
        while percent < 100:
            time.sleep(1)
            size = self._handle.file_progress()[file_id]
            percent = int(size/persize)
            progress.update(percent, self._fname, u'Size: ' + self._human(firstsize) + u' / ' + self._human(selfile.size).strip(), u'Load: ' + self._human(size))
            if progress.iscanceled():
                progress.close()
                return self._end()
        progress.close()

        xbmcvfs.rename(self._filename, self._filename)        
        if info:
            info['size'] = selfile.size
            xbmc.Player().play(self._filename.encode('utf8'), info)
        else:
            xbmc.Player().play(self._filename.encode('utf8'))

        window_info = LibTorrentInfo()

        while xbmc.Player().isPlaying():

            if xbmc.getCondVisibility('Player.Paused'):
                window_info.show()
            else:
                window_info.hide()

            window_info.update(**self._get_state(file_id, selfile.size))

            if not self._complete:
                priorities = self._handle.piece_priorities()
                status = self._handle.status()

                download = 0
                
                if len(status.pieces):
                    
                    for i in range(start, end + 1):
                        if priorities[i] != 0 and not status.pieces[i]:
                            download += 1
                            
                    for i in range(start, end + 1):
                        if priorities[i] == 0 and download < offset:
                            self._handle.piece_priority(i, 1)
                            download += 1
                    
                    for i in range(start, end + 1):
                        if not status.pieces[i]:
                            break
                    else:
                        self._complete = True
                        
                        if notice:
                            if not isinstance(notice, basestring):
                                notice = xbmcaddon.Addon(id=sys.argv[0].replace('plugin://', '').replace('/', '')).getAddonInfo('icon')
                            if notice:
                                xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s, "%s")' % ('Download complete', self._fname, 5000, notice))
                            else:
                                xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s)' % ('Download complete', self._fname, 5000))
            
            time.sleep(1)

        window_info.hide()
        
        return self._end()


    def _get_state(self, fid, size):
        res = dict(
            state='init',
            peers=0,
            seeds=0,
            down_speed=0,
            up_speed=0,
            total_download=0,
            total_size=0
        )

        try:
            info = self._handle.get_torrent_info()
        except RuntimeError:
            pass
        else:
            states = {
                'queued_for_checking': 'init',
                'checking_files': 'init',
                'downloading_metadata': 'down',
                'downloading': 'down',
                'seeding': 'seed',
                'allocating': 'init',
                'checking_resume_data': 'init'
            }

            progress = self._handle.file_progress()
            status = self._handle.status()
            state = str(status.state)

            if state == 'finished':
                res['state'] = 'seed' if status.is_seeding else 'down'
            else:
                res['state'] = states.get(state, 'init')

            res['peers'] = status.num_peers
            res['seeds'] = status.num_seeds
            res['down_speed'] = 8*status.download_payload_rate  # 8*byte
            res['up_speed'] = 8*status.upload_payload_rate  # 8*byte

            res['download'] = progress[fid]
            res['size'] = size

            res['total_download'] = sum(progress)
            res['total_size'] = info.total_size() if self._handle.has_metadata else 0

        return res
    
    
    def _end(self):
        self._stop = True
        
        try:
            self._session.remove_torrent(self._handle)
        except:
            pass
        
        return self._filename if self._complete else None
        
        
    def _download(self, start, end):
        cache = {}
        
        for i in range(start, end + 1):
            
            if i in cache:
                del cache[i]
                continue
            
            while True:
                status = self._handle.status()
                if not status.pieces or status.pieces[i]:
                    break
                time.sleep(0.5)
                if self._stop:
                    return
                
            self._handle.read_piece(i)
            
            while True:
                part = self._session.pop_alert()
                if isinstance(part, libtorrent.read_piece_alert):
                    if part.piece == i:
                        break
                    else:
                        cache[part.piece] = part.buffer
                    break
                time.sleep(0.5)
                if self._stop:
                    return
            
            time.sleep(0.1)
            if self._stop:
                return
    
    
    def _torrent_info(self, torrent):
        filename = os.tempnam()
        file(filename, 'wb').write(torrent)
        torrent_info = libtorrent.torrent_info(filename)
        os.unlink(filename)
        return torrent_info
    
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
    

# ################################
#
#   TORRENT STREAM
#
# ################################

class TorrentStream:
    def __init__(self, portfile=None):
        self.is_install = _IS_TORRENTSTREAM
        self._portfile = portfile
    
    def list(self, torrent, reverse=False):
        ts = TSengine()
        if str(ts.load_torrent(base64.b64encode(torrent), 'RAW', port=self._get_port())).upper() != 'OK':
            ts.end()
            return None
        
        if not ts.files or not isinstance(ts.files, dict):
            ts.end()
            return None
        
        files = [{'id': v, 'name': urllib.unquote(k)} for k, v in ts.files.iteritems()]
        ts.end()
        files.sort(cmp=lambda f1, f2: cmp(f1['name'], f2['name']))
        if reverse:
            files.reverse()
        return files
        
    
    def play(self, torrent, file_id, title=None, icon=None, cover=None):
        if not title:
            title = ''
        if not icon:
            icon = ''
        if not cover:
            cover = ''
            
        ts = TSengine()
        if str(ts.load_torrent(base64.b64encode(torrent), 'RAW', port=self._get_port())).upper() != 'OK':
            ts.end()
            return
        
        ts.play_url_ind(int(file_id), title, icon, cover)
        ts.end()

    def _get_port(self):
        port = None
        if self._portfile:
            try:
                port = int(file(self._portfile, 'rb').read())
            except:
                pass
        if not port:
            try:
                port = int(file(os.path.normpath(os.path.join(os.path.expanduser('~'), 'AppData/Roaming/TorrentStream/engine', 'acestream.port')), 'rb').read())
            except:
                pass
        return port if port else 62062




