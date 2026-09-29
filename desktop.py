"""KDE Wayland: read actual cursor/window state; temporary F8/F9 shortcuts.

The small KWin helper runs in the desktop window manager, never in the game.
It is unloaded on exit and does not change mouse acceleration or permissions.
"""
from __future__ import annotations

import json
import os
import queue
import tempfile
import threading
import time
from pathlib import Path

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


INTERFACE = "local.DwarFishing.Desktop"
GAME_TITLE = "ejderhalar mirası"

# KWin can be busy with a fullscreen game while the helper is loaded, and a
# single attempt then reports nothing.  Reload instead of giving up: every
# attempt installs a fresh helper that reports as soon as it runs.
REPORT_ATTEMPTS = 3
REPORT_TIMEOUT = 4.0

# A process killed by a signal never unloads its KWin helper, and those helpers
# accumulate in the window manager.  Dead pids are pruned on the next start.
SCRIPT_REGISTRY = Path(__file__).resolve().parent / "runtime" / "kwin_scripts.json"


def is_game_title(title):
    """Only the game window itself, never an item wiki popup.

    An in-game item lookup opens a second window whose caption also contains
    the game name ("... Ejderhalar Mirası içindeki eşya hakkında bilgi"), so a
    plain substring test would send clicks into the wiki instead of the game.
    """
    return str(title or "").strip().lower().startswith(GAME_TITLE)


def game_window_id(candidates):
    """Pick the single game window out of the KWin candidates."""
    real = [c for c in candidates if is_game_title(c.get("title"))]
    chosen = real or list(candidates)
    if len(chosen) != 1:
        raise RuntimeError(f"{len(chosen)} oyun penceresi bulundu; tek oyun penceresini öne getirin.")
    return chosen[0]["id"]


class _Receiver(dbus.service.Object):
    def __init__(self, bus, owner):
        super().__init__(bus, "/Desktop")
        self.owner = owner

    @dbus.service.method(INTERFACE, in_signature="s", out_signature="")
    def State(self, payload):
        self.owner.state = json.loads(str(payload))
        self.owner.updated.set()

    @dbus.service.method(INTERFACE, in_signature="s", out_signature="")
    def Control(self, command):
        self.owner.commands.put(str(command))


class Desktop:
    def __init__(self, shortcuts=True):
        DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus(private=True)
        self.name = f"local.DwarFishing.p{os.getpid()}"
        self.bus_name = dbus.service.BusName(self.name, bus=self.bus, do_not_queue=True)
        self._await_own_name()
        self.state = {}
        self.updated = threading.Event()
        self.commands = queue.Queue()
        self.receiver = _Receiver(self.bus, self)
        self.loop = GLib.MainLoop()
        self.thread = threading.Thread(target=self.loop.run, daemon=True)
        self.thread.start()
        self.scripting = dbus.Interface(
            self.bus.get_object("org.kde.KWin", "/Scripting"), "org.kde.kwin.Scripting"
        )
        self.plugin = f"dwar-fishing-{os.getpid()}"
        self.closed = False
        report = """
function report() {
    var w = workspace.activeWindow;
    var g = workspace.virtualScreenGeometry;
    var candidates = workspace.windowList().filter(function(c) {
        return /ejderhalar/i.test(c.caption) && /chrome|chromium|brave/i.test(c.resourceClass);
    }).map(function(c) { return {id: String(c.internalId), title: c.caption}; });
    var data = {cursor: [workspace.cursorPos.x, workspace.cursorPos.y],
        geometry: [g.x, g.y, g.width, g.height],
        screens: workspace.screens.length,
        title: w ? w.caption : '', app: w ? w.resourceClass : '',
        window: w ? String(w.internalId) : '', candidates: candidates};
    callDBus(SERVICE, '/Desktop', 'local.DwarFishing.Desktop', 'State', JSON.stringify(data));
}
workspace.cursorPosChanged.connect(report);
workspace.windowActivated.connect(report);
workspace.screensChanged.connect(report);
function watchWindow(w) {
    w.captionChanged.connect(report);
    w.frameGeometryChanged.connect(report);
    report();
}
workspace.windowList().forEach(watchWindow);
workspace.windowAdded.connect(watchWindow);
workspace.windowRemoved.connect(report);
report();
""".replace("SERVICE", json.dumps(self.name))
        if shortcuts:
            report += """
registerShortcut(PLUGIN + '-pause', 'Balık botunu duraklat / devam', 'F8', function() {
    callDBus(SERVICE, '/Desktop', 'local.DwarFishing.Desktop', 'Control', 'toggle');
});
registerShortcut(PLUGIN + '-stop', 'Balık botunu durdur', 'F9', function() {
    callDBus(SERVICE, '/Desktop', 'local.DwarFishing.Desktop', 'Control', 'stop');
});
""".replace("SERVICE", json.dumps(self.name)).replace("PLUGIN", json.dumps(self.plugin))
        try:
            self._start_helper(report)
        except Exception:
            self.close()
            raise

    def _start_helper(self, report):
        """Load the KWin helper and wait for its first report.

        A helper can load without ever reporting (KWin busy with a fullscreen
        game, a JavaScript error, a lost name), so the load is repeated instead
        of failing the whole bot on the first silent attempt.
        """
        self._prune_stale_scripts()
        error = RuntimeError("KWin imleç/pencere bilgisi alınamadı; fare kullanılmadı.")
        for attempt in range(REPORT_ATTEMPTS):
            if attempt:
                self._unload_quiet(self.plugin)
            try:
                self._load(report, self.plugin)
            except Exception as exc:
                error = exc
                continue
            self._remember_script()
            if self.updated.wait(REPORT_TIMEOUT):
                return
        raise error

    def _unload_quiet(self, name):
        try:
            self.scripting.unloadScript(name)
        except Exception:
            pass

    def _remember_script(self):
        """Record our helper name so a later start can prune it if we die hard."""
        try:
            seen = json.loads(SCRIPT_REGISTRY.read_text())
        except (OSError, ValueError):
            seen = []
        seen = [pid for pid in seen if pid != os.getpid()]
        seen.append(os.getpid())
        try:
            SCRIPT_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
            SCRIPT_REGISTRY.write_text(json.dumps(seen[-20:]))
        except OSError:
            pass

    def _prune_stale_scripts(self):
        """Unload helpers left behind by processes that are gone."""
        try:
            pids = json.loads(SCRIPT_REGISTRY.read_text())
        except (OSError, ValueError):
            return
        for pid in pids:
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, 0)
            except OSError:
                self._unload_quiet(f"dwar-fishing-{pid}")

    def _await_own_name(self):
        """Block until the session bus really owns our well-known name.

        Name ownership is confirmed by the bus asynchronously: a KWin helper
        loaded in that window would have its first ``report()`` dropped, and a
        quiet desktop then delivers no further state within the startup
        timeout.  Waiting here removes that race.
        """
        daemon = dbus.Interface(
            self.bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus"),
            "org.freedesktop.DBus")
        deadline = time.monotonic() + 2.0
        while not daemon.NameHasOwner(self.name):
            if time.monotonic() > deadline:
                raise RuntimeError(f"D-Bus adı alınamadı: {self.name}")
            time.sleep(0.02)

    def _load(self, code, name):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(code)
            path = f.name
        try:
            script_id = int(self.scripting.loadScript(path, name, signature="ss"))
            if script_id < 0:
                raise RuntimeError("Geçici KWin yardımcısı yüklenemedi.")
            script = self.bus.get_object("org.kde.KWin", f"/Scripting/Script{script_id}")
            dbus.Interface(script, "org.kde.kwin.Script").run()
            # A JavaScript error during evaluation (missing API, typo) leaves
            # the helper unloaded: no report ever arrives and every mouse move
            # then times out.  Fail here, with the reason in the log.
            if not self.scripting.isScriptLoaded(name):
                raise RuntimeError(
                    f"KWin yardımcısı yüklenemedi (JS hatası olabilir): {name}; "
                    "ayrıntı için `journalctl --user -g 'error:' -n 20`")
        finally:
            Path(path).unlink(missing_ok=True)

    def focus_game(self):
        target = game_window_id(self.state.get("candidates", []))
        name = self.plugin + "-focus"
        code = """
workspace.windowList().forEach(function(w) {
    if (String(w.internalId) === TARGET) {
        w.minimized = false;
        workspace.activeWindow = w;
    }
});
""".replace("TARGET", json.dumps(target))
        try:
            self._load(code, name)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if self.state.get("window") == target:
                    return
                time.sleep(0.03)
            raise RuntimeError("Oyun penceresi öne getirilemedi.")
        finally:
            self.scripting.unloadScript(name)

    def is_game_active(self):
        s = self.state
        if not any(browser in s.get("app", "").lower() for browser in ("chrome", "chromium", "brave")):
            return False
        title = str(s.get("title", "")).lower()
        if is_game_title(title):
            return True
        # An item wiki window also names the game; only trust the loose name
        # check while no properly named game window exists to disagree.
        if GAME_TITLE not in title:
            return False
        return not [c for c in s.get("candidates", [])
                    if is_game_title(c.get("title")) and c.get("id") != s.get("window")]

    def cursor(self):
        return tuple(self.state["cursor"])

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._unload_quiet(self.plugin)
        self.receiver.remove_from_connection()
        self.loop.quit()
        self.thread.join(timeout=1)
        self.bus_name = None
        self.bus.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
