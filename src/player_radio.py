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

from gi.repository import TotemPlParser

from gettext import gettext as _

from lollypop.playlists import RadiosManager
from lollypop.player_base import BasePlayer
from lollypop.define import Navigation
from lollypop.track import Track


# This class neeed the parent object to be a BinPlayer
class RadioPlayer(BasePlayer):
    """
        Init radio player
    """
    def __init__(self):
        BasePlayer.__init__(self)
        self._radio_name = None
        self._radio_uri = None
        self._bus.connect("message::tag", self._on_bus_message_tag)

    """
        Load radio at uri
        @param name as string
        @param uri as string
    """
    def load(self, name, uri):
        self.current_track.id = Navigation.RADIOS
        self._radio_name = name
        self._radio_uri = uri
        try:
            parser = TotemPlParser.Parser.new()
            parser.connect("entry-parsed", self._on_entry_parsed, name)
            parser.parse_async(uri, False, None, self._on_parsed, name)
        except Exception as e:
            print("RadioPlayer::load(): ", e)
            return False
        self.set_party(False)
        self._albums = []
        return True

    """
        Return next radio name, uri
        @return (name, uri)
    """
    def next(self):
        return Track()
        radios_manager = RadiosManager()
        radios = radios_manager.get()
        i = 0
        for (radio_id, name) in radios:
            if name == self._radio_name:
                break
            i += 1
        # Get next radio
        if i + 1 >= len(radios):
            i = 0
        else:
            i += 1
        name = radios[i][1]
        uris = radios_manager.get_tracks(name)
        if len(uris) > 0:
            return (name, uris[0])
        else:
            return (None, None)

    """
        Return prev radio name, uri
        @return (name, uri)
    """
    def prev(self):
        return Track()
        radios_manager = RadiosManager()
        radios = radios_manager.get()
        i = 0
        for (radio_id, name) in radios:
            if name == self._radio_name:
                break
            i += 1
        # Get prev radio
        if i - 1 <= 0:
            i = len(radios) - 1
        else:
            i -= 1
        name = radios[i][1]
        uris = radios_manager.get_tracks(name)
        if len(uris) > 0:
            return (name, uris[0])
        else:
            return (None, None)

#######################
# PRIVATE             #
#######################
    """
        Set current state on radio
    """
    def _set_current(self):
        string = _("Radio")
        if self._radio_name is not None:
            self.current_track.artist = self._radio_name
        if self._radio_uri is not None:
            self.current_track.path = self._radio_uri
        self.current_track.title = string
        self.current_track.album_id = None
        self.current_track.album = string
        self.current_track.aartist_id = None
        self.current_track.aartist = string
        self.current_track.genre = string
        self.current_track.duration = 0.0
        self.current_track.number = 0

    """
        Read title from stream
        @param bus as Gst.Bus
        @param message as Gst.Message
    """
    def _on_bus_message_tag(self, bus, message):
        if self.current_track.id != Navigation.RADIOS:
            return
        tags = message.parse_tag()
        (exist, title) = tags.get_string_index('title', 0)
        if exist and title != self.current_track.title:
            self.current_track.title = title
            self.emit('current-changed')

    """
        If parsing failed, try to play uri
        @param parser as Totem.PlParser
        @param result as Gio.AsyncResult
        @param radio name as string
    """
    def _on_parsed(self, parser, result, name):
        if parser.parse_finish(result) != TotemPlParser.ParserResult.SUCCESS:
            # Only start playing if context always True
            if self._radio_name == name:
                self._stop()
                self._playbin.set_property('uri', self._radio_uri)
                self._set_current()
                self.play()

    """
        Play stream
        @param parser as TotemPlParser.Parser
        @param track uri as str
        @param metadata as GLib.HastTable
        @param radio name as string
    """
    def _on_entry_parsed(self, parser, uri, metadata, name):
        # Only start playing if context always True
        if self._radio_name == name:
            self._stop()
            self._playbin.set_property('uri', uri)
            self._set_current()
            self.play()
