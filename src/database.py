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

import sqlite3
import os
from gi.repository import GLib

from lollypop.define import Lp


class Database:

    LOCAL_PATH = os.path.expanduser("~") + "/.local/share/lollypop"
    DB_PATH = "%s/lollypop.db" % LOCAL_PATH

    """
        SQLite documentation:
        In SQLite, a column with type INTEGER PRIMARY KEY
        is an alias for the ROWID.
        Here, we define an id INT PRIMARY KEY but never feed it,
        this make VACUUM not destroy rowids...
    """
    create_albums = '''CREATE TABLE albums (id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        noaartist BOOLEAN NOT NULL,
                        year INT,
                        path TEXT NOT NULL,
                        popularity INT NOT NULL,
                        mtime INT NOT NULL)'''
    create_artists = '''CREATE TABLE artists (id INTEGER PRIMARY KEY,
                                              name TEXT NOT NULL)'''
    create_genres = '''CREATE TABLE genres (id INTEGER PRIMARY KEY,
                                            name TEXT NOT NULL)'''
    create_album_artists = '''CREATE TABLE album_artists (
                                                album_id INT NOT NULL,
                                                artist_id INT NOT NULL)'''
    create_album_genres = '''CREATE TABLE album_genres (
                                                album_id INT NOT NULL,
                                                genre_id INT NOT NULL)'''
    create_tracks = '''CREATE TABLE tracks (id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        filepath TEXT NOT NULL,
                        length INT,
                        tracknumber INT,
                        discnumber INT,
                        album_id INT NOT NULL,
                        year INT,
                        popularity INT NOT NULL,
                        ltime INT,
                        mtime INT)'''
    create_track_artists = '''CREATE TABLE track_artists (
                                                track_id INT NOT NULL,
                                                artist_id INT NOT NULL)'''
    create_track_genres = '''CREATE TABLE track_genres (
                                                track_id INT NOT NULL,
                                                genre_id INT NOT NULL)'''
    version = 11

    """
        Create database tables or manage update if needed
    """
    def __init__(self):
        self._albums_popularity = {}
        self._albums_mtime = {}
        self._tracks_popularity = {}
        self._tracks_ltime = {}
        # Create db directory if missing
        if not os.path.exists(self.LOCAL_PATH):
            try:
                os.mkdir(self.LOCAL_PATH)
            except:
                print("Can't create %s" % self.LOCAL_PATH)

        if os.path.exists(self.DB_PATH):
            db_version = Lp.settings.get_value('db-version').get_int32()
            if db_version < self.version:
                self._set_albums_popularity()
                self._set_albums_mtime()
                self._set_tracks_popularity()
                self._set_tracks_ltime()
                os.remove(self.DB_PATH)
                Lp.settings.set_value('db-version',
                                      GLib.Variant('i', self.version))

        sql = self.get_cursor()
        # Create db schema
        try:
            sql.execute(self.create_albums)
            sql.execute(self.create_artists)
            sql.execute(self.create_genres)
            sql.execute(self.create_album_artists)
            sql.execute(self.create_album_genres)
            sql.execute(self.create_tracks)
            sql.execute(self.create_track_artists)
            sql.execute(self.create_track_genres)
            sql.commit()
            Lp.settings.set_value('db-version',
                                  GLib.Variant('i', self.version))
        except:
            pass

    """
        Get a dict with album name and popularity
        This is usefull for collection scanner be
        able to restore popularities after db reset
    """
    def get_albums_popularity(self):
        return self._albums_popularity

    """
        Get a dict with album name and mtime
        This is usefull for collection scanner be
        able to restore mtimes after db reset
    """
    def get_albums_mtime(self):
        return self._albums_mtime

    """
        Get a dict with track name and popularity
        This is usefull for collection scanner be
        able to restore popularities after db reset
    """
    def get_tracks_popularity(self):
        return self._tracks_popularity

    """
        Get a dict with track name and ltime
        This is usefull for collection scanner be
        able to restore ltimes after db reset
    """
    def get_tracks_ltime(self):
        return self._tracks_ltime
###########
# Private #
###########
    """
        Set a dict with album string and popularity
        This is usefull for collection scanner be
        able to restore popularities after db reset
    """
    def _set_albums_popularity(self):
        try:
            sql = self.get_cursor()
            result = sql.execute("SELECT albums.name, artists.name, popularity\
                                  FROM albums, artists\
                                  WHERE artists.rowid == albums.artist_id")
            for row in result:
                string = "%s_%s" % (row[0], row[1])
                self._albums_popularity[string] = row[2]
            sql.close()
        except Exception as e:
            print("Database::_set_albums_popularity: %s" % e)

    """
        Set a dict with album string and mtime
        This is usefull for collection scanner be
        able to restore mtimes after db reset
    """
    def _set_albums_mtime(self):
        try:
            sql = self.get_cursor()
            result = sql.execute("SELECT albums.name, artists.name, mtime\
                                  FROM albums, artists\
                                  WHERE artists.rowid == albums.artist_id")
            for row in result:
                string = "%s_%s" % (row[0], row[1])
                self._albums_mtime[string] = row[2]
            sql.close()
        except Exception as e:
            print("Database::_set_albums_mtime: %s" % e)

    """
        Set a dict with track string and popularity
        This is usefull for collection scanner be
        able to restore popularities after db reset
    """
    def _set_tracks_popularity(self):
        try:
            sql = self.get_cursor()
            result = sql.execute(
                "SELECT tracks.name, artists.name, popularity\
                 FROM tracks, track_artists, artists\
                 WHERE artists.rowid == track_artists.artist_id\
                 AND track_artists.track_id == tracks.rowid")
            for row in result:
                string = "%s_%s" % (row[0], row[1])
                self._tracks_popularity[string] = row[2]
            sql.close()
        except Exception as e:
            print("Database::_set_tracks_popularity: %s" % e)

    """
        Set a dict with track string and ltime
        This is usefull for collection scanner be
        able to restore mtimes after db reset
    """
    def _set_tracks_ltime(self):
        try:
            sql = self.get_cursor()
            result = sql.execute(
                "SELECT tracks.name, artists.name, ltime\
                 FROM tracks, track_artists, artists\
                 WHERE artists.rowid == track_artists.artist_id\
                 AND track_artists.track_id == tracks.rowid")
            for row in result:
                string = "%s_%s" % (row[0], row[1])
                self._tracks_ltime[string] = row[2]
            sql.close()
        except Exception as e:
            print("Database::_set_tracks_ltime: %s" % e)

    """
        Return a new sqlite cursor
    """
    def get_cursor(self):
        try:
            return sqlite3.connect(self.DB_PATH, 600.0)
        except:
            exit(-1)
