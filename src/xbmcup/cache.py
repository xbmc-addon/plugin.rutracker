# -*- coding: utf-8 -*-

import os
import sys
import time
import pickle

import xbmc, xbmcvfs

try:
    from sqlite3 import dbapi2 as sqlite
except:
    from pysqlite2 import dbapi2 as sqlite

class Cache:
    def __init__(self, name, expire=0, size=0, step=100):
        self.name = name
        self._connect()
        if expire:
            self.expire(expire)
        if size:
            self.size(size, step)
    
    def get(self, token, callback, *param):
        cur = self.db.cursor()
        cur.execute('select expire,data from cache where id=? limit 1', (token, ))
        row = cur.fetchone()
        cur.close()
        
        if row:
            if row[0] and row[0] < int(time.time()):
                pass
            else:
                try:
                    obj = pickle.loads(row[1])
                except:
                    pass
                else:
                    return obj
        
        response = callback(*param)
        
        if response[0]:
            obj = sqlite.Binary(pickle.dumps(response[1]))
            curtime = int(time.time())
            cur = self.db.cursor()
            if isinstance(response[0], bool):
                cur.execute('replace into cache(id,addtime,expire,data) values(?,?,?,?)', (token, curtime, None, obj))
            else:
                cur.execute('replace into cache(id,addtime,expire,data) values(?,?,?,?)', (token, curtime, curtime + response[0], obj))
            self.db.commit()
            cur.close()
        
        return response[1]
    
    def expire(self, expire):
        cur = self.db.cursor()
        cur.execute('delete from cache where addtime<?', (int(time.time()) - expire, ))
        self.db.commit()
        cur.close()
    
    def size(self, size, step=100):
        while True:
            if os.path.getsize(self.filename) < size:
                break
            cur = self.db.cursor()
            cur.execute('select id from cache order by addtime asc limit ?', (step, ))
            rows = cur.fetchall()
            if not rows:
                cur.close()
                break
            cur.execute('delete from cache where id in (' + ','.join(len(rows)*'?') + ')', [x[0] for x in rows])
            self.db.commit()
            cur.close()
    
    def flush(self):
        cur = self.db.cursor()
        cur.execute('delete from cache')
        self.db.commit()
        cur.close()
    
    def _connect(self):
        dirname = xbmc.translatePath('special://temp')
        for subdir in ('xbmcup', sys.argv[0].replace('plugin://', '').replace('/', '')):
            dirname = os.path.join(dirname, subdir)
            if not xbmcvfs.exists(dirname):
                xbmcvfs.mkdir(dirname)
        
        self.filename = os.path.join(dirname, self.name)
        
        first = False
        if not xbmcvfs.exists(self.filename):
            first = True
            
        self.db = sqlite.connect(self.filename)
        if first:
            cur = self.db.cursor()
            cur.execute('pragma auto_vacuum=1')
            cur.execute('create table cache(id varchar(255) unique, addtime integer, expire integer, data blob)')
            cur.execute('create index time on cache(addtime asc)')
            self.db.commit()
            cur.close()
    