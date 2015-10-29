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

from lollypop.container import Container
from lollypop.define import Lp, NextContext, Shuffle
from lollypop.toolbar import Toolbar
from lollypop.utils import is_unity


class Window(Gtk.ApplicationWindow, Container):
    """
        Main window
    """

    def __init__(self, app):
        """
            Init window
        """
        Container.__init__(self)
        self._app = app
        self._signal1 = None
        self._signal2 = None
        Gtk.ApplicationWindow.__init__(self,
                                       application=app,
                                       title="Lollypop")
        self._nullwidget = Gtk.Label()  # Use to get selected background color
        self._timeout_configure = None
        seek_action = Gio.SimpleAction.new('seek',
                                           GLib.VariantType.new('i'))
        seek_action.connect('activate', self._on_seek_action)
        app.add_action(seek_action)
        player_action = Gio.SimpleAction.new('player',
                                             GLib.VariantType.new('s'))
        player_action.connect('activate', self._on_player_action)
        app.add_action(player_action)

        self._setup_content()
        self._setup_window()
        self._setup_media_keys()
        self.enable_global_shorcuts(True)

        self.connect('destroy', self._on_destroyed_window)
        self.connect('realize', self._on_realize)

    def setup_menu(self, menu):
        """
            Add an application menu to window
            @parma: menu as Gio.Menu
        """
        self._toolbar.setup_menu_btn(menu)

    def get_selected_color(self):
        """
            Return selected color
        """
        return self._nullwidget.get_style_context().\
            get_background_color(Gtk.StateFlags.SELECTED)

    def enable_global_shorcuts(self, enable):
        """
            Setup global shortcuts
            @param enable as bool
        """
        if enable:
            if Gtk.Widget.get_default_direction() == Gtk.TextDirection.RTL:
                self._app.set_accels_for_action("app.seek(10)",
                                                ["Left"])
                self._app.set_accels_for_action("app.seek(20)",
                                                ["<Control>Left"])
                self._app.set_accels_for_action("app.seek(-10)",
                                                ["Right"])
                self._app.set_accels_for_action("app.seek(-20)",
                                                ["<Control>Right"])
            else:
                self._app.set_accels_for_action("app.seek(10)",
                                                ["Right"])
                self._app.set_accels_for_action("app.seek(20)",
                                                ["<Control>Right"])
                self._app.set_accels_for_action("app.seek(-10)",
                                                ["Left"])
                self._app.set_accels_for_action("app.seek(-20)",
                                                ["<Control>Left"])

            self._app.set_accels_for_action("app.player::play_pause",
                                            ["space", "c"])
            self._app.set_accels_for_action("app.player::play",
                                            ["x"])
            self._app.set_accels_for_action("app.player::stop",
                                            ["v"])
            self._app.set_accels_for_action("app.player::next",
                                            ["n"])
            self._app.set_accels_for_action("app.player::next_album",
                                            ["<Control>n"])
            self._app.set_accels_for_action("app.player::prev",
                                            ["p"])
        else:
            self._app.set_accels_for_action("app.seek(10)", [None])
            self._app.set_accels_for_action("app.seek(20)", [None])
            self._app.set_accels_for_action("app.seek(-10)", [None])
            self._app.set_accels_for_action("app.seek(-20)", [None])
            self._app.set_accels_for_action("app.player::play_pause", [None])
            self._app.set_accels_for_action("app.player::play", [None])
            self._app.set_accels_for_action("app.player::stop", [None])
            self._app.set_accels_for_action("app.player::play_pause", [None])
            self._app.set_accels_for_action("app.player::play", [None])
            self._app.set_accels_for_action("app.player::stop", [None])
            self._app.set_accels_for_action("app.player::next", [None])
            self._app.set_accels_for_action("app.player::next_album", [None])
            self._app.set_accels_for_action("app.player::prev", [None])

    def do_hide(self):
        """
            Remove callbacks (we don't want to save an invalid value on hide
        """
        if self._signal1 is not None:
            self.disconnect(self._signal1)
        if self._signal2 is not None:
            self.disconnect(self._signal2)
        Gtk.ApplicationWindow.do_hide(self)

############
# Private  #
############
    def _setup_media_keys(self):
        """
            Setup media player keys
        """
        self._proxy = Gio.DBusProxy.new_sync(Gio.bus_get_sync(Gio.BusType.
                                                              SESSION, None),
                                             Gio.DBusProxyFlags.NONE,
                                             None,
                                             'org.gnome.SettingsDaemon',
                                             '/org/gnome/SettingsDaemon/'
                                             'MediaKeys',
                                             'org.gnome.SettingsDaemon.'
                                             'MediaKeys',
                                             None)
        self._grab_media_player_keys()
        try:
            self._proxy.connect('g-signal', self._handle_media_keys)
        except GLib.GError:
            # We cannot grab media keys if no settings daemon is running
            pass

    def _grab_media_player_keys(self):
        """
            Do key grabbing
        """
        try:
            self._proxy.call_sync('GrabMediaPlayerKeys',
                                  GLib.Variant('(su)', ('Lollypop', 0)),
                                  Gio.DBusCallFlags.NONE,
                                  -1,
                                  None)
        except GLib.GError:
            # We cannot grab media keys if no settings daemon is running
            pass

    def _handle_media_keys(self, proxy, sender, signal, parameters):
        """
            Do player actions in response to media key pressed
        """
        if signal != 'MediaPlayerKeyPressed':
            print('Received an unexpected signal\
                   \'%s\' from media player'.format(signal))
            return
        response = parameters.get_child_value(1).get_string()
        if 'Play' in response:
            Lp.player.play_pause()
        elif 'Stop' in response:
            Lp.player.stop()
        elif 'Next' in response:
            Lp.player.next()
        elif 'Previous' in response:
            Lp.player.prev()

    def _setup_content(self):
        """
            Setup window content
        """
        self.set_icon_name('lollypop')
        self._toolbar = Toolbar(self.get_application())
        self._toolbar.show()
        if Lp.settings.get_value('disable-csd') or is_unity():
            vgrid = Gtk.Grid()
            vgrid.set_orientation(Gtk.Orientation.VERTICAL)
            vgrid.add(self._toolbar)
            vgrid.add(self.main_widget())
            vgrid.show()
            self.add(vgrid)
        else:
            self.set_titlebar(self._toolbar)
            self._toolbar.set_show_close_button(True)
            self.add(self.main_widget())

    def _setup_window(self):
        """
            Setup window position and size, callbacks
        """
        size_setting = Lp.settings.get_value('window-size')
        if isinstance(size_setting[0], int) and\
           isinstance(size_setting[1], int):
            self.resize(size_setting[0], size_setting[1])
        else:
            self.set_size_request(800, 600)
        position_setting = Lp.settings.get_value('window-position')
        if len(position_setting) == 2 and\
           isinstance(position_setting[0], int) and\
           isinstance(position_setting[1], int):
            self.move(position_setting[0], position_setting[1])

        if Lp.settings.get_value('window-maximized'):
            self.maximize()

        self._signal1 = self.connect("window-state-event",
                                     self._on_window_state_event)
        self._signal2 = self.connect("configure-event",
                                     self._on_configure_event)

    def _on_configure_event(self, widget, event):
        """
            Delay event
            @param: widget as Gtk.Window
            @param: event as Gdk.Event
        """
        self._toolbar.set_progress_width(widget.get_size()[0]/4)
        if self._timeout_configure:
            GLib.source_remove(self._timeout_configure)
        self._timeout_configure = GLib.timeout_add(500,
                                                   self._save_size_position,
                                                   widget)

    def _save_size_position(self, widget):
        """
            Save window state, update current view content size
            @param: widget as Gtk.Window
        """
        self._timeout_configure = None
        size = widget.get_size()
        Lp.settings.set_value('window-size',
                              GLib.Variant('ai', [size[0], size[1]]))

        position = widget.get_position()
        Lp.settings.set_value('window-position',
                              GLib.Variant('ai', [position[0], position[1]]))

    def _on_window_state_event(self, widget, event):
        """
            Save maximised state
        """
        Lp.settings.set_boolean('window-maximized',
                                'GDK_WINDOW_STATE_MAXIMIZED' in
                                event.new_window_state.value_names)

    def _on_destroyed_window(self, widget):
        """
            Save paned widget width
            @param widget as unused, data as unused
        """
        Lp.settings.set_value('paned-mainlist-width',
                              GLib.Variant('i',
                                           self._paned_main_list.
                                           get_position()))
        Lp.settings.set_value('paned-listview-width',
                              GLib.Variant('i',
                                           self._paned_list_view.
                                           get_position()))

    def _on_seek_action(self, action, param):
        """
            Seek in stream
            @param action as Gio.SimpleAction
            @param param as GLib.Variant
        """
        seconds = param.get_int32()
        position = Lp.player.get_position_in_track()
        seek = position/1000000/60+seconds
        if seek < 0:
            seek = 0
        if seek > Lp.player.current_track.duration:
            seek = Lp.player.current_track.duration - 2
        Lp.player.seek(seek)
        self._toolbar.update_position(seek*60)

    def _on_player_action(self, action, param):
        """
            Change player state
            @param action as Gio.SimpleAction
            @param param as GLib.Variant
        """
        string = param.get_string()
        if string == "play_pause":
            Lp.player.play_pause()
        elif string == "play":
            Lp.player.play()
        elif string == "stop":
            Lp.player.stop()
        elif string == "next":
            Lp.player.next()
        elif string == "next_album":
            # In party or shuffle, just update next track
            if Lp.player.is_party() or\
                    Lp.settings.get_enum('shuffle') == Shuffle.TRACKS:
                Lp.player.set_next()
                # We send this signal to update next popover
                Lp.player.emit("queue-changed")
            else:
                Lp.player.context.next = NextContext.START_NEW_ALBUM
                Lp.player.set_next()
                Lp.player.next()
        elif string == "prev":
            Lp.player.prev()

    def _on_realize(self, widget):
        """
            Run scanner on realize
            @param widget as Gtk.Widget
        """
        if Lp.settings.get_value('auto-update') or Lp.tracks.is_empty():
            # Delayed, make python segfault on sys.exit() otherwise
            # No idea why, maybe scanner using Gstpbutils before Gstreamer
            # initialisation is finished...
            GLib.timeout_add(2000, self.update_db)
