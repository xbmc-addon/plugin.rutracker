#!/bin/sh
cd `dirname $0`/../src
cp -r ./* $HOME/Library/Application\ Support/Kodi/addons/plugin.rutracker/
rm -f $HOME/.xbmc/temp/xbmcup/plugin.rutracker/kinopoisk.db
rm -f $HOME/.xbmc/temp/xbmcup/plugin.rutracker/rutracker_profile.db
rm -f $HOME/.xbmc/temp/xbmcup/plugin.rutracker/tvdb.db
