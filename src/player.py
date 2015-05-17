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

from lollypop.player_bin import BinPlayer
from lollypop.player_queue import QueuePlayer
from lollypop.player_linear import LinearPlayer
from lollypop.player_shuffle import ShufflePlayer
from lollypop.player_radio import RadioPlayer
from lollypop.player_userplaylist import UserPlaylistPlayer
from lollypop.define import Objects, Navigation, NextContext
from lollypop.define import Shuffle
from lollypop.track import Track


# Player object used to manage playback and playlists
class Player(BinPlayer, QueuePlayer, UserPlaylistPlayer, RadioPlayer,
             LinearPlayer, ShufflePlayer):
    """
        Create a gstreamer bin and listen to signals on bus
    """
    def __init__(self):
        BinPlayer.__init__(self)
        QueuePlayer.__init__(self)
        LinearPlayer.__init__(self)
        ShufflePlayer.__init__(self)
        UserPlaylistPlayer.__init__(self)
        RadioPlayer.__init__(self)

    """
        Play previous track
    """
    def prev(self):
        if self.prev_track.id is not None:
            self.context.current_position = self.context.prev_position
            self.load(self.prev_track.id)

    """
        Play next track
    """
    def next(self):
        if self.next_track.id is not None:
            self.context.current_position = self.context.next_position
            self.load(self.next_track.id)
        print('debug this:')
#        if self.context.next == NextContext.START_NEW_ALBUM:
#            self.context.next = NextContext.NONE

    """
        Stop.current_track track, load radio, play it
        @param name as string
        @param uri as string
    """
    def load_radio(self, name, uri):
        RadioPlayer.load(self, name, uri)

    """
        Play album
        @param album id as int
        @param genre id as int
    """
    def play_album(self, album_id, genre_id=None):
        # Empty user playlist
        self._user_playlist = None
        # Get first track from album
        track_id = Objects.albums.get_tracks(album_id, genre_id)[0]
        Objects.player.load(track_id)
        if not Objects.player.is_party():
            if genre_id:
                self.set_albums(self.current_track.id,
                                self.current_track.aartist_id,
                                genre_id)
            else:
                self.set_album(album_id)

    """
        Set album as.current_track album list (for next/prev)
        Set track as.current_track track in album
        @param album_id as int
    """
    def set_album(self, album_id):
        self._albums = [album_id]
        self.context.album_id = album_id
        self.context.genre_id = None
        tracks = Objects.albums.get_tracks(album_id, None)
        self.context.current_position = tracks.index(self.current_track.id)

    """
        Set album list (for next/prev)
        @param track id as int
        @param artist id as int
        @param genre id as int
    """
    def set_albums(self, track_id, artist_id, genre_id):
        # Invalid track
        if track_id is None:
            return
        album_id = Objects.tracks.get_album_id(track_id)
        self._albums = []
        self._played_tracks_history = []
        self._already_played_tracks = {}
        self._already_played_albums = []
        self.context.genre_id = genre_id

        # When shuffle from artist is active, we want only artist's albums,
        # we need to ignore genre
        # Do not set genre_id directly as it will changes.current_track context
        if self._shuffle in [Shuffle.TRACKS_ARTIST, Shuffle.ALBUMS_ARTIST]:
            genre_id_lookup = None
        else:
            genre_id_lookup = genre_id

        # We are not playing a user playlist anymore
        self._user_playlist = None
        # We are in all artists
        if genre_id_lookup == Navigation.ALL or artist_id == Navigation.ALL:
            self._albums = Objects.albums.get_compilations(Navigation.ALL)
            self._albums += Objects.albums.get_ids()
        # We are in populars view, add popular albums
        elif genre_id_lookup == Navigation.POPULARS:
            self._albums = Objects.albums.get_populars()
        # We are in recents view, add recent albums
        elif genre_id_lookup == Navigation.RECENTS:
            self._albums = Objects.albums.get_recents()
        # We are in randoms view, add random albums
        elif genre_id_lookup == Navigation.RANDOMS:
            self._albums = Objects.albums.get_cached_randoms()
        # We are in compilation view without genre
        elif genre_id_lookup == Navigation.COMPILATIONS:
            self._albums = Objects.albums.get_compilations(None)
        # Random tracks/albums for artist
        elif self._shuffle in [Shuffle.TRACKS_ARTIST, Shuffle.ALBUMS_ARTIST]:
            self._albums = Objects.albums.get_ids(artist_id, genre_id_lookup)
        # Add all albums for genre
        else:
            self._albums = Objects.albums.get_compilations(genre_id_lookup)
            self._albums += Objects.albums.get_ids(None, genre_id_lookup)

        self.context.album_id = album_id
        tracks = Objects.albums.get_tracks(album_id, genre_id_lookup)
        if track_id in tracks:
            self.context.current_position = tracks.index(track_id)
            self.context.genre_id = genre_id
            # Shuffle album list if needed
            self._shuffle_albums()
        elif self.current_track.id != Navigation.RADIOS:
            self.stop()

    """
        Restore player state
    """
    def restore_state(self):
        track_id = Objects.settings.get_value('track-id').get_int32()
        if Objects.settings.get_value('save-state') and track_id > 0:
            path = Objects.tracks.get_path(track_id)
            if path != "":
                self._load_track(track_id)
                self.set_albums(track_id, Navigation.ALL, Navigation.ALL)
                self.emit('current-changed')
            else:
                print("Player::restore_state(): track missing")

    """
        Announce album cover update
        @param album id as int
    """
    def announce_cover_update(self, album_id):
        self.emit("cover-changed", album_id)

    """
        Announce radio logo update
        @param radio name as string
    """
    def announce_logo_update(self, name):
        self.emit("logo-changed", name)

#######################
# PRIVATE             #
#######################
    """
        Set previous track
    """
    def _set_prev(self):
        # Look at radio
        self.prev_track = RadioPlayer.prev(self)

        # Look at user playlist then
        if self.prev_track.id is None:
            self.prev_track = UserPlaylistPlayer.prev(self)
        
        # Look at shuffle
        if self.prev_track.id is None:
            self.prev_track = ShufflePlayer.prev(self)

        # Get previous track in history
        if self.prev_track.id is None:
            self.prev_track = LinearPlayer.prev(self)

    """
        Play next track
        @param sql as sqlite cursor
    """
    def _set_next(self, sql=None):
        # Look at radio
        self.next_track = RadioPlayer.next(self)

        # Look first at user queue
        if self.next_track.id is None:
            self.next_track = QueuePlayer.next(self)

        # Look at user playlist then
        if self.next_track.id is None:
            self.next_track = UserPlaylistPlayer.next(self)

        # Get a random album/track then
        if self.next_track.id is None:
            self.next_track = ShufflePlayer.next(self, sql)

        # Get a linear track then
        if self.next_track.id is None:
            self.next_track = LinearPlayer.next(self, sql)

    """
        On stream start
        Emit .current_track-changed" to notify others components
    """
    def _on_stream_start(self, bus, message):
        BinPlayer._on_stream_start(self, bus, message)
        ShufflePlayer._on_stream_start(self, bus, message)
        self._set_next()
        self._set_prev()
