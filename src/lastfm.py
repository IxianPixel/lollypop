#!/usr/bin/python
# Copyright (c) 2014-2015 Cedric Bellegarde <cedric.bellegarde@adishatz.org>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

from gi.repository import GLib, Gio

from gettext import gettext as _
try:
    from gi.repository import Secret
except Exception as e:
    print(e)
    print(_("Lastfm authentication disabled"))
    Secret = None

from pylast import LastFMNetwork, md5, BadAuthenticationError
from pylast import SCROBBLE_SOURCE_USER, SCROBBLE_MODE_PLAYED
import urllib.request
from gettext import gettext as _
import re
import html.parser
from locale import getdefaultlocale
from _thread import start_new_thread

from lollypop.define import Lp, SecretSchema, SecretAttributes
from lollypop.utils import translate_artist_name

class LastFM(LastFMNetwork):
    """
       We recommend you don't distribute the API key and secret with your app, 
       and that you ask users who want to build it to apply for a key of
       their own. We don't believe that this would violate the terms of most
       open-source licenses.
       That said, we can't stop you from distributing the key and secret if you
       want, and if your app isn't written in a compiled language, you don't
       really have much option :).
    """
    _API_KEY = '7a9619a850ccf7377c46cf233c51e3c6'
    _API_SECRET = '9254319364d73bec6c59ace485a95c98'
    """
        Init lastfm
    """
    def __init__(self):
        LastFMNetwork.__init__(self,
                               api_key=self._API_KEY,
                               api_secret=self._API_SECRET)
        self._albums_queue = []
        self._is_auth = False
        self._in_albums_download = False
        self.connect(None)

    """
        Connect lastfm
        @param password as str
    """
    def connect(self, password):
        if Secret is None:
            return
        if password is None:
            schema = Secret.Schema.new("org.gnome.Lollypop",
                                       Secret.SchemaFlags.NONE,
                                       SecretSchema)
            Secret.password_lookup(schema, SecretAttributes, None,
                                   self._on_password_lookup)
        else:
            username = Lp.settings.get_value('lastfm-login').get_string()
            start_new_thread(self._connect, (username, password))

    """
        Download album image
        @param album id as int
    """
    def download_album_img(self, album_id):
        if Gio.NetworkMonitor.get_default().get_network_available() and\
           album_id is not None:
            album = Lp.albums.get_name(album_id)
            artist = Lp.albums.get_artist_name(album_id)
            self._albums_queue.append((translate_artist_name(artist), album))
            if not self._in_albums_download:
                start_new_thread(self._download_albums_imgs, ())

    """
        Get artist infos
        @param artist as str
        @return (url as str, image url as str, content as str)
    """
    def get_artist_infos(self, artist):
        if not Gio.NetworkMonitor.get_default().get_network_available():
            return (None, None, None)
        try:
            last_artist = self.get_artist(artist)
            url = last_artist.get_url()
            try:
                content = last_artist.get_bio_summary(
                                           language=getdefaultlocale()[0][0:2])
            except:
                content = last_artist.get_bio_summary()
            content = re.sub(r'.*Last.fm.*', '', content)
            content = re.sub(r'<.*?>', '', content)
            image_url = last_artist.get_cover_image(3)
            return (url, image_url, html.parser.HTMLParser().unescape(content))
        except:
            return (None, None, None)

    """
        Scrobble track
        @param artist as str
        @param title as str
        @param timestamp as int
        @param duration as int
    """
    def scrobble(self, artist, title, timestamp, duration):
        if Gio.NetworkMonitor.get_default().get_network_available() and\
           self._is_auth and Secret is not None:
            start_new_thread(self._scrobble, (artist,
                                              title,
                                              timestamp,
                                              duration))

    """
        Return True if valid authentication send
        @return bool
    """
    def is_auth(self):
        return self._is_auth

#######################
# PRIVATE             #
#######################
    """
        Connect lastfm
        @param username as str
        @param password as str
        @thread safe
    """
    def _connect(self, username, password):
        if password != '' and username != '':
            self._is_auth = True
        else:
            self._is_auth = False
        try:
            LastFMNetwork.__init__(
             self,
             api_key = self._API_KEY,
             api_secret=self._API_SECRET,
             username = Lp.settings.get_value('lastfm-login').get_string(),
             password_hash = md5(password))
        except:
            pass

    """
        Scrobble track
        @param artist as str
        @param title as str
        @param timestamp as int
        @param duration as int
        @thread safe
    """
    def _scrobble(self, artist, title, timestamp, duration):
        if duration < 30.0:
            return
        try:
            LastFMNetwork.scrobble(self,
                                   artist=artist,
                                   title=title,
                                   timestamp=timestamp)
        except BadAuthenticationError:
            GLib.idle_add(Lp.notify.send, _("Wrong Last.fm credentials"))
        except Exception as e:
            print("LastFM::scrobble: %s" % e)

    """
        Download albums images
    """
    def _download_albums_imgs(self):
        self._in_albums_download = True
        sql = Lp.db.get_cursor()
        while self._albums_queue:
            (artist, album) = self._albums_queue.pop()
            try:
                last_album = self.get_album(artist, album)
                url = last_album.get_cover_image(4)
                if url is None:
                    continue
                artist_id = Lp.artists.get_id(artist, sql)
                album_id = Lp.albums.get_id(album, artist_id, sql)
                # Compilation or album without album artist
                if album_id is None:
                    album_id = Lp.albums.get_compilation_id(album, sql)
                filepath = Lp.art.get_album_art_filepath(album_id, sql)
                urllib.request.urlretrieve(url, filepath)
                Lp.art.clean_album_cache(album_id, sql)
                GLib.idle_add(Lp.art.announce_cover_update, album_id)
            except Exception as e:
                print("LastFM::download_album_img: %s" % e)
        self._in_albums_download = False
        sql.close()

    """
        Init self object
        @param source as GObject.Object
        @param result Gio.AsyncResult
    """
    def _on_password_lookup(self, source, result):
        username = Lp.settings.get_value('lastfm-login').get_string()
        password = Secret.password_lookup_finish(result)
        start_new_thread(self._connect, (username, password))
