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

from gi.repository import Gtk, Gio, GLib

from threading import Thread, Lock
from gettext import gettext as _

from lollypop.define import Lp, Type
from lollypop.selectionlist import SelectionList
from lollypop.view_container import ViewContainer
from lollypop.view_albums import AlbumsView
from lollypop.view_artist import ArtistView
from lollypop.view_radios import RadiosView
from lollypop.view_playlists import PlaylistView
from lollypop.view_playlists import PlaylistsManageView, PlaylistEditView
from lollypop.view_device import DeviceView, DeviceLocked


# This is a multimedia device
class Device:
    id = None
    name = None
    uri = None


class Loader(Thread):
    """
        Helper to load data on a separate thread and
        dispatch it to the UI thread
    """
    active = {}
    active_lock = Lock()

    def __init__(self, target, view=None, on_finished=None):
        Thread.__init__(self)
        self.daemon = True
        self._target = target
        self._view = view
        self._on_finished = on_finished
        self._invalidated = False
        self._invalidated_lock = Lock()

    def is_invalidated(self):
        with self._invalidated_lock:
            return self._invalidated

    def invalidate(self):
        with self._invalidated_lock:
            self._invalidated = True

    def run(self):
        with Loader.active_lock:
            active = Loader.active.get(self._view, None)
            if active:
                active.invalidate()
            Loader.active[self._view] = self
        result = self._target()
        if not self.is_invalidated():
            if self._on_finished:
                GLib.idle_add(self._on_finished, (result))
            elif self._view:
                GLib.idle_add(self._view.populate, (result))
            with Loader.active_lock:
                Loader.active.pop(self._view, None)


class Container:
    """
        Container for main view
    """
    def __init__(self):
        """
            Init container
        """
        # Index will start at -VOLUMES
        self._devices = {}
        self._devices_index = Type.DEVICES
        self._show_genres = Lp.settings.get_value('show-genres')
        self._stack = ViewContainer(500)
        self._stack.show()

        self._setup_view()
        self._setup_scanner()

        (list_one_id, list_two_id) = self._get_saved_view_state()
        self._list_one.select_id(list_one_id)
        self._list_two.select_id(list_two_id)

        # Volume manager
        self._vm = Gio.VolumeMonitor.get()
        self._vm.connect('mount-added', self._on_mount_added)
        self._vm.connect('mount-removed', self._on_mount_removed)

        Lp.playlists.connect('playlists-changed',
                             self._update_playlists)

    def update_db(self):
        """
            Update db at startup only if needed
        """
        # Stop previous scan
        if Lp.scanner.is_locked():
            Lp.scanner.stop()
            GLib.timeout_add(250, self.update_db)
        else:
            # Something (device manager) is using progress bar
            progress = None
            if not self._progress.is_visible():
                progress = self._progress
            Lp.scanner.update(progress)

    def get_genre_id(self):
        """
            Return current selected genre
            @return genre id as int
        """
        if self._show_genres:
            return self._list_one.get_selected_id()
        else:
            return None

    def init_list_one(self):
        """
            Init list one
        """
        self._update_list_one(None)

    def save_view_state(self):
        """
            Save view state
        """
        Lp.settings.set_value("list-one",
                              GLib.Variant('i',
                                           self._list_one.get_selected_id()))
        Lp.settings.set_value("list-two",
                              GLib.Variant('i',
                                           self._list_two.get_selected_id()))

    def show_playlist_manager(self, object_id, genre_id, is_album):
        """
            Show playlist manager for object_id
            Current view stay present in ViewContainer
            @param object id as int
            @param genre id as int
            @param is_album as bool
        """
        view = PlaylistsManageView(object_id, genre_id, is_album)
        view.populate()
        view.show()
        self._stack.add(view)
        self._stack.set_visible_child(view)

    def show_playlist_editor(self, playlist_id):
        """
            Show playlist editor for playlist
            Current view stay present in ViewContainer
            @param playlist id as int
            @param playlist name as str
        """
        view = PlaylistEditView(playlist_id)
        view.show()
        self._stack.add(view)
        self._stack.set_visible_child(view)
        view.populate()

    def main_widget(self):
        """
            Get main widget
            @return Gtk.HPaned
        """
        return self._paned_main_list

    def stop_all(self):
        """
            Stop current view from processing
        """
        view = self._stack.get_visible_child()
        if view is not None:
            self._stack.clean_old_views(None)

    def show_genres(self, show):
        """
            Show/Hide genres
            @param bool
        """
        self._show_genres = show
        self._list_one.clear()
        self._update_list_one(None)

    def destroy_current_view(self):
        """
            Destroy current view
        """
        view = self._stack.get_visible_child()
        for child in self._stack.get_children():
            if child != view:
                self._stack.set_visible_child(child)
                self._stack.clean_old_views(child)
                break

    def update_view(self):
        """
            Update current view
        """
        view = self._stack.get_visible_child()
        if view:
            view.update_covers()

    def on_scan_finished(self, scanner):
        """
            Mark force scan as False, update lists
            @param scanner as CollectionScanner
        """
        self._update_lists(scanner)

############
# Private  #
############
    def _setup_view(self):
        """
            Setup window main view:
                - genre list
                - artist list
                - main view as artist view or album view
        """
        self._paned_main_list = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        self._paned_list_view = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        vgrid = Gtk.Grid()
        vgrid.set_orientation(Gtk.Orientation.VERTICAL)

        self._list_one = SelectionList()
        self._list_one.show()
        self._list_two = SelectionList()
        self._list_one.connect('item-selected', self._on_list_one_selected)
        self._list_one.connect('populated', self._on_list_populated)
        self._list_two.connect('item-selected', self._on_list_two_selected)

        self._progress = Gtk.ProgressBar()
        self._progress.set_property('hexpand', True)

        vgrid.add(self._stack)
        vgrid.add(self._progress)
        vgrid.show()

        separator = Gtk.Separator()
        separator.show()
        self._paned_list_view.add1(self._list_two)
        self._paned_list_view.add2(vgrid)
        self._paned_main_list.add1(self._list_one)
        self._paned_main_list.add2(self._paned_list_view)
        self._paned_main_list.set_position(
            Lp.settings.get_value('paned-mainlist-width').get_int32())
        self._paned_list_view.set_position(
            Lp.settings.get_value('paned-listview-width').get_int32())
        self._paned_main_list.show()
        self._paned_list_view.show()

    def _get_saved_view_state(self):
        """
            Get save view state
            @return (list one id, list two id)
        """
        list_one_id = Type.POPULARS
        list_two_id = Type.NONE
        if Lp.settings.get_value('save-state'):
            position = Lp.settings.get_value('list-one').get_int32()
            if position != -1:
                list_one_id = position
            position = Lp.settings.get_value('list-two').get_int32()
            if position != -1:
                list_two_id = position

        return (list_one_id, list_two_id)

    def _add_genre(self, scanner, genre_id):
        """
            Add genre to genre list
            @param scanner as CollectionScanner
            @param genre id as int
        """
        if self._show_genres:
            genre_name = Lp.genres.get_name(genre_id)
            self._list_one.add_value((genre_id, genre_name))

    def _add_artist(self, scanner, artist_id, album_id):
        """
            Add artist to artist list
            @param scanner as CollectionScanner
            @param artist id as int
            @param album id as int
        """
        artist_name = Lp.artists.get_name(artist_id)
        if self._show_genres:
            genre_ids = Lp.albums.get_genre_ids(album_id)
            genre_ids.append(Type.ALL)
            if self._list_one.get_selected_id() in genre_ids:
                self._list_two.add_value((artist_id, artist_name))
        else:
            self._list_one.add_value((artist_id, artist_name))

    def _setup_scanner(self):
        """
            Run collection update if needed
            @return True if hard scan is running
        """
        Lp.scanner.connect('scan-finished', self.on_scan_finished)
        Lp.scanner.connect('genre-update', self._add_genre)
        Lp.scanner.connect('artist-update', self._add_artist)

    def _update_playlists(self, playlists, playlist_id):
        """
            Update playlists in second list
            @param playlists as Playlists
            @param playlist_id as int
        """
        if self._list_one.get_selected_id() == Type.PLAYLISTS:
            if Lp.playlists.exists(playlist_id):
                self._list_two.update_value(playlist_id,
                                            Lp.playlists.get_name(playlist_id))
            else:
                self._list_two.remove(playlist_id)

    def _update_lists(self, updater=None):
        """
            Update lists
            @param updater as GObject
        """
        self._update_list_one(updater)
        self._update_list_two(updater)

    def _update_list_one(self, updater):
        """
            Update list one
            @param updater as GObject
        """
        update = updater is not None
        if self._show_genres:
            self._setup_list_genres(self._list_one, update)
        else:
            self._setup_list_artists(self._list_one, Type.ALL, update)

    def _update_list_two(self, updater):
        """
            Update list two
            @param updater as GObject
        """
        update = updater is not None
        object_id = self._list_one.get_selected_id()
        if object_id == Type.PLAYLISTS:
            self._setup_list_playlists(update)
        elif self._show_genres and object_id != Type.NONE:
            self._setup_list_artists(self._list_two, object_id, update)

    def _get_headers(self):
        """
            Return list one headers
        """
        items = []
        items.append((Type.POPULARS, _("Popular albums")))
        items.append((Type.RECENTS, _("Recently added albums")))
        items.append((Type.RANDOMS, _("Random albums")))
        items.append((Type.PLAYLISTS, _("Playlists")))
        items.append((Type.RADIOS, _("Radios")))
        if self._show_genres:
            items.append((Type.ALL, _("All artists")))
        else:
            items.append((Type.ALL, _("All albums")))
        return items

    def _setup_list_genres(self, selection_list, update):
        """
            Setup list for genres
            @param list as SelectionList
            @param update as bool, if True, just update entries
            @thread safe
        """
        def load():
            sql = Lp.db.get_cursor()
            genres = Lp.genres.get(sql)
            sql.close()
            return genres

        def setup(genres):
            items = self._get_headers()
            items.append((Type.SEPARATOR, ''))
            items += genres
            selection_list.mark_as_artists(False)
            if update:
                selection_list.update_values(items)
            else:
                selection_list.populate(items)

        loader = Loader(target=load, view=selection_list, on_finished=setup)
        loader.start()

    def _setup_list_artists(self, selection_list, genre_id, update):
        """
            Setup list for artists
            @param list as SelectionList
            @param update as bool, if True, just update entries
            @thread safe
        """
        def load():
            sql = Lp.db.get_cursor()
            artists = Lp.artists.get(genre_id, sql)
            compilations = Lp.albums.get_compilations(genre_id, sql)
            sql.close()
            return (artists, compilations)

        def setup(artists, compilations):
            if selection_list == self._list_one:
                items = self._get_headers()
                items.append((Type.SEPARATOR, ''))
            else:
                items = []
            if compilations:
                items.append((Type.COMPILATIONS, _("Compilations")))
            items += artists
            selection_list.mark_as_artists(True)
            if update:
                selection_list.update_values(items)
            else:
                selection_list.populate(items)

        if selection_list == self._list_one:
            if self._list_two.is_visible():
                self._list_two.hide()
            self._list_two_restore = Type.NONE
        loader = Loader(target=load, view=selection_list,
                        on_finished=lambda r: setup(*r))
        loader.start()

    def _setup_list_playlists(self, update):
        """
            Setup list for playlists
            @param update as bool
            @thread safe
        """
        playlists = [(Type.LOVED, Lp.playlists._LOVED)]
        playlists.append((Type.MPD, Lp.playlists._MPD))
        playlists.append((Type.POPULARS, _("Popular tracks")))
        playlists.append((Type.RECENTS, _("Recently played")))
        playlists.append((Type.NEVER, _("Never played")))
        playlists.append((Type.RANDOMS, _("Random tracks")))
        playlists.append((Type.SEPARATOR, ''))
        playlists += Lp.playlists.get()
        if update:
            self._list_two.update_values(playlists)
        else:
            self._list_two.mark_as_artists(False)
            self._list_two.populate(playlists)

    def _update_view_device(self, device_id):
        """
            Update current view with device view,
            Use existing view if available
            @param device id as int
        """
        device = self._devices[device_id]

        child = self._stack.get_child_by_name(device.uri)
        if child is None:
            if DeviceView.get_files(device.uri):
                child = DeviceView(device, self._progress)
                self._stack.add_named(child, device.uri)
            else:
                child = DeviceLocked()
                self._stack.add(child)
            child.show()
        child.populate()
        self._stack.set_visible_child(child)
        self._stack.clean_old_views(child)

    def _update_view_artists(self, artist_id, genre_id):
        """
            Update current view with artists view
            @param artist id as int
            @param genre id as int
        """
        def load():
            sql = Lp.db.get_cursor()
            if artist_id == Type.COMPILATIONS:
                albums = Lp.albums.get_compilations(genre_id, sql)
            elif genre_id == Type.ALL:
                albums = Lp.albums.get_ids(artist_id, None, sql)
            else:
                albums = Lp.albums.get_ids(artist_id, genre_id, sql)
            sql.close()
            return albums

        view = ArtistView(artist_id, genre_id)
        loader = Loader(target=load, view=view)
        loader.start()
        view.show()
        self._stack.add(view)
        self._stack.set_visible_child(view)
        self._stack.clean_old_views(view)

    def _update_view_albums(self, genre_id, is_compilation=False):
        """
            Update current view with albums view
            @param genre id as int
            @param is compilation as bool
        """
        def load():
            sql = Lp.db.get_cursor()
            albums = []
            if genre_id == Type.ALL:
                if is_compilation:
                    albums = Lp.albums.get_compilations(None, sql)
                else:
                    if Lp.settings.get_value('show-compilations'):
                        albums = Lp.albums.get_compilations(None, sql)
                    albums += Lp.albums.get_ids(None, None, sql)
            elif genre_id == Type.POPULARS:
                albums = Lp.albums.get_populars(sql)
            elif genre_id == Type.RECENTS:
                albums = Lp.albums.get_recents(sql)
            elif genre_id == Type.RANDOMS:
                albums = Lp.albums.get_randoms(sql)
            elif is_compilation:
                albums = Lp.albums.get_compilations(genre_id, sql)
            else:
                if Lp.settings.get_value('show-compilations'):
                    albums = Lp.albums.get_compilations(genre_id, sql)
                albums += Lp.albums.get_ids(None, genre_id, sql)
            sql.close()
            return albums

        view = AlbumsView(genre_id, is_compilation)
        loader = Loader(target=load, view=view)
        loader.start()
        view.show()
        self._stack.add(view)
        self._stack.set_visible_child(view)
        self._stack.clean_old_views(view)

    def _update_view_playlists(self, playlist_id):
        """
            Update current view with playlist view
            @param playlist id as int
        """
        def load():
            sql = Lp.db.get_cursor()
            if playlist_id == Lp.player.get_user_playlist_id():
                tracks = [t.id for t in Lp.player.get_user_playlist()]
            elif playlist_id == Type.POPULARS:
                tracks = Lp.tracks.get_populars(sql)
            elif playlist_id == Type.RECENTS:
                tracks = Lp.tracks.get_recently_listened_to(sql)
            elif playlist_id == Type.NEVER:
                tracks = Lp.tracks.get_never_listened_to(sql)
            elif playlist_id == Type.RANDOMS:
                tracks = Lp.tracks.get_randoms(sql)
            else:
                sql_p = Lp.playlists.get_cursor()
                tracks = Lp.playlists.get_tracks_ids(playlist_id,
                                                     sql, sql_p)
                sql_p.close()
            sql.close()
            return tracks

        view = None
        if playlist_id is not None:
            view = PlaylistView(playlist_id)
        else:
            view = PlaylistsManageView(Type.NONE, None, False)
        if view:
            # Management or user playlist
            if playlist_id is None:
                view.populate()
            else:
                loader = Loader(target=load, view=view)
                loader.start()
            view.show()
            self._stack.add(view)
            self._stack.set_visible_child(view)
            self._stack.clean_old_views(view)

    def _update_view_radios(self):
        """
            Update current view with radios view
        """
        view = RadiosView()
        view.populate()
        view.show()
        self._stack.add(view)
        self._stack.set_visible_child(view)
        self._stack.clean_old_views(view)

    def _add_device(self, volume):
        """
            Add volume to device list
            @param volume as Gio.Volume
        """
        if volume is None:
            return
        root = volume.get_activation_root()
        if root is None:
            return

        uri = root.get_uri()
        # Just to be sure
        if uri is not None and len(uri) > 1 and uri[-1:] != '/':
            uri += '/'
        if uri is not None and uri.find('mtp:') != -1:
            self._devices_index -= 1
            dev = Device()
            dev.id = self._devices_index
            dev.name = volume.get_name()
            dev.uri = uri
            self._devices[self._devices_index] = dev
            self._list_one.add_value((dev.id, dev.name))

    def _remove_device(self, volume):
        """
            Remove volume from device list
            @param volume as Gio.Volume
        """
        if volume is None:
            return
        root = volume.get_activation_root()
        if root is None:
            return

        uri = root.get_uri()
        for dev in self._devices.values():
            if dev.uri == uri:
                self._list_one.remove(dev.id)
                child = self._stack.get_child_by_name(uri)
                if child is not None:
                    child.destroy()
                del self._devices[dev.id]
            break

    def _on_list_one_selected(self, selection_list, selected_id):
        """
            Update view based on selected object
            @param list as SelectionList
            @param selected id as int
        """
        if selected_id == Type.PLAYLISTS:
            self._list_two.clear()
            self._list_two.show()
            if not self._list_two.will_be_selected():
                self._update_view_playlists(None)
            self._setup_list_playlists(False)
        elif selected_id < Type.DEVICES:
            self._list_two.hide()
            if not self._list_two.will_be_selected():
                self._update_view_device(selected_id)
        elif selected_id in [Type.POPULARS,
                             Type.RECENTS,
                             Type.RANDOMS]:
            self._list_two.hide()
            self._update_view_albums(selected_id)
        elif selected_id == Type.RADIOS:
            self._list_two.hide()
            self._update_view_radios()
        elif selection_list.is_marked_as_artists():
            self._list_two.hide()
            if selected_id == Type.ALL:
                self._update_view_albums(selected_id)
            elif selected_id == Type.COMPILATIONS:
                self._update_view_albums(None, True)
            else:
                self._update_view_artists(selected_id, None)
        else:
            self._list_two.clear()
            self._setup_list_artists(self._list_two, selected_id, False)
            self._list_two.show()
            if not self._list_two.will_be_selected():
                self._update_view_albums(selected_id, False)

    def _on_list_populated(self, selection_list):
        """
            Add device to list one and update db
            @param selection list as SelectionList
        """
        for dev in self._devices.values():
            self._list_one.add_value((dev.id, dev.name))

    def _on_list_two_selected(self, selection_list, selected_id):
        """
            Update view based on selected object
            @param list as SelectionList
            @param selected id as int
        """
        genre_id = self._list_one.get_selected_id()
        if genre_id == Type.PLAYLISTS:
            self._update_view_playlists(selected_id)
        elif selected_id == Type.COMPILATIONS:
            self._update_view_albums(genre_id, True)
        else:
            self._update_view_artists(selected_id, genre_id)

    def _on_mount_added(self, vm, mnt):
        """
            On volume mounter
            @param vm as Gio.VolumeMonitor
            @param mnt as Gio.Mount
        """
        self._add_device(mnt.get_volume())

    def _on_mount_removed(self, vm, mnt):
        """
            On volume removed, clean selection list
            @param vm as Gio.VolumeMonitor
            @param mnt as Gio.Mount
        """
        self._remove_device(mnt.get_volume())
