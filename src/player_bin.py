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

from gi.repository import Gst, GLib, GstAudio

from gettext import gettext as _
from time import time

from lollypop.player_base import BasePlayer
from lollypop.tagreader import ScannerTagReader
from lollypop.player_rg import ReplayGainPlayer
from lollypop.define import GstPlayFlags, NextContext, Lp
from lollypop.define import Type
from lollypop.utils import debug


# Bin player class
class BinPlayer(BasePlayer):
    """
        Init playbin
    """
    def __init__(self):
        Gst.init(None)
        BasePlayer.__init__(self)
        self._playbin1 = Gst.ElementFactory.make('playbin', 'player')
        self._playbin2 = Gst.ElementFactory.make('playbin', 'player')
        flags = self._playbin1.get_property("flags")
        flags &= ~GstPlayFlags.GST_PLAY_FLAG_VIDEO
        self._playbin1.set_property('flags', flags)
        self._playbin2.set_property('flags', flags)
        self._rg1 = ReplayGainPlayer(self._playbin1)
        self._rg2 = ReplayGainPlayer(self._playbin2)
        self._playbin1.connect('about-to-finish',
                              self._on_stream_about_to_finish)
        self._playbin2.connect('about-to-finish',
                              self._on_stream_about_to_finish)
        for bus in [self._playbin1.get_bus(), self._playbin2.get_bus()]:
            bus.add_signal_watch()
            bus.connect('message::error', self._on_bus_error)
            bus.connect('message::stream-start', self._on_stream_start)
            bus.connect("message::tag", self._on_bus_message_tag)
        self._handled_error = None
        self._playbin = self._playbin1
        self._nextbin = None

    """
        True if player is playing
        @return bool
    """
    def is_playing(self):
        ok, state, pending = self._playbin.get_state(0)
        if ok == Gst.StateChangeReturn.ASYNC:
            return pending == Gst.State.PLAYING
        elif ok == Gst.StateChangeReturn.SUCCESS:
            return state == Gst.State.PLAYING
        else:
            return False

    """
        Playback status
        @return Gstreamer state
    """
    def get_status(self):
        ok, state, pending = self._playbin.get_state(0)
        if ok == Gst.StateChangeReturn.ASYNC:
            state = pending
        elif (ok != Gst.StateChangeReturn.SUCCESS):
            state = Gst.State.NULL
        return state

    """
        Stop current track, load track id and play it
        @param track as Track
    """
    def load(self, track):
        if self._nextbin is not None:
            self._playbin = self._nextbin
        self._stop()
        if self._load_track(track):
            self.play()

    """
        Change player state to PLAYING
    """
    def play(self):
        self._playbin.set_state(Gst.State.PLAYING)
        self.emit("status-changed")

    """
        Change player state to PAUSED
    """
    def pause(self):
        self._playbin.set_state(Gst.State.PAUSED)
        self.emit("status-changed")

    """
        Change player state to STOPPED
    """
    def stop(self):
        self._stop()
        self.emit("status-changed")

    """
        Set PLAYING if PAUSED
        Set PAUSED if PLAYING
    """
    def play_pause(self):
        if self.is_playing():
            self.pause()
        else:
            self.play()

    """
        Seek current track to position
        @param position as seconds
    """
    def seek(self, position):
        self._playbin.seek_simple(Gst.Format.TIME,
                                  Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                                  position * Gst.SECOND)
        self.emit("seeked", position)

    """
        Return bin playback position
        @return position as int
    """
    def get_position_in_track(self):
        position = self._playbin.query_position(Gst.Format.TIME)[1] / 1000
        return position * 60

    """
        Return player volume rate
        @return rate as double
    """
    def get_volume(self):
        return self._playbin.get_volume(GstAudio.StreamVolumeFormat.LINEAR)

    """
        Set player volume rate
        @param rate as double
    """
    def set_volume(self, rate):
        self._playbin.set_volume(GstAudio.StreamVolumeFormat.LINEAR, rate)
        self.emit('volume-changed')

    """
        Go next track
    """
    def next(self):
        pass

    """
        Set replaygain mode
        @param album mode as int
    """
    def set_rg_mode(self, album_mode):
         self._rg1.set_mode(album_mode)
         self._rg2.set_mode(album_mode)

#######################
# PRIVATE             #
#######################
    """
        Set next track
    """
    def _set_next(self):
        pass

    """
        Set prev track
    """
    def _set_prev(self):
        pass

    """
        Stop current track (for track change)
    """
    def _stop(self):
        self._playbin.set_state(Gst.State.NULL)

    """
        Load track
        @param track as Track
        @param sql as sqlite cursor
        @return False if track not loaded
    """
    def _load_track(self, track, sql=None):
        stop = False

        # Stop if needed
        if self.context.next == NextContext.STOP_TRACK:
            stop = True

        # Stop if album changed
        if self.context.next == NextContext.STOP_ALBUM and\
           self.current_track.album_id != track.album_id:
            stop = True

        # Stop if aartist changed
        if self.context.next == NextContext.STOP_ARTIST and\
           self.current_track.aartist_id != track.aartist_id:
            stop = True

        if stop:
            return False

        self.current_track = track

        if self.current_track.uri is not None:
            try:
                self._playbin.set_property('uri',
                                           self.current_track.uri)
            except Exception as e:  # Gstreamer error, stop
                print("BinPlayer::_load_track(): ", e)
                self.stop()
                return False
        else:
            GLib.timeout_add(2000, self.next)
            return False
        return True

    """
        Read tags from stream
        @param bus as Gst.Bus
        @param message as Gst.Message
    """
    def _on_bus_message_tag(self, bus, message):
        if self.current_track.id >= 0:
            return
        reader = ScannerTagReader()
        tags = message.parse_tag()

        self.current_track.title = reader.get_title(tags,
                                                    self.current_track.uri)
        if self.current_track.id == Type.EXTERNAL:
            self.current_track.duration =\
                    self._playbin.query_duration(Gst.Format.TIME)[1]/1000000000
            self.current_track.album = reader.get_album_name(tags)
            self.current_track.artist = reader.get_artists(tags)
            self.current_track.aartist = reader.get_album_artist(tags)
            if self.current_track.aartist is None:
                self.current_track.aartist = self.current_track.artist
            self.current_track.genre = reader.get_genres(tags)
        self.emit('current-changed')

    """
        Handle first bus error, ignore others
        @param bus as Gst.Bus
        @param message as Gst.Message
    """
    def _on_bus_error(self, bus, message):
        debug("Error playing: %s" % self.current_track.uri)
        if self._handled_error != self.current_track.uri:
            self._handled_error = self.current_track.uri
            Lp.notify.send(_("File doesn't exist: %s") %\
                                                   self.current_track.uri)
            self._set_next()
            self.next()
        return False

    """
        When stream is about to finish, switch to next track without gap
        @param playbin as Gst bin
    """
    def _on_stream_about_to_finish(self, playbin):
        if self.current_track.id == Type.RADIOS:
            return
        previous_track_id = self.current_track.id
        # We are in a thread, we need to create a new cursor
        sql = Lp.db.get_cursor()

        # Workaround broken mp3s if asked for
        if Lp.settings.get_value('force-gapless'):
            finished_in = self.current_track.duration -\
                   self._playbin.query_position(Gst.Format.TIME)[1]/1000000000
            timeout = (finished_in-0.10)*1000
            if timeout < 0:
                timeout = 0
            if playbin == self._playbin1:
                self._nextbin = self._playbin2
            else:
                self._nextbin = self._playbin1
            GLib.timeout_add(timeout, self.next)
        else:
            GLib.idle_add(self.next)

        # Scrobble on lastfm
        if Lp.lastfm is not None:
            if self.current_track.aartist_id == Type.COMPILATIONS:
                artist = self.current_track.artist
            else:
                artist = self.current_track.aartist
            timestamp = time() - self.current_track.duration
            Lp.lastfm.scrobble(artist,
                               self.current_track.title,
                               int(timestamp),
                               int(self.current_track.duration))
        # Add populariy if we listen to the song
        album_id = Lp.tracks.get_album_id(previous_track_id,
                                          sql)
        if not Lp.scanner.is_locked():
            Lp.albums.set_more_popular(album_id, sql)
        sql.close()

    """
        On stream start
        Emit "current-changed" to notify others components
        @param bus as Gst.Bus
        @param message as Gst.Message
    """
    def _on_stream_start(self, bus, message):
        debug("Player::_on_stream_start(): %s" % self.current_track.uri)
        self.emit("current-changed")
        self._handled_error = None
