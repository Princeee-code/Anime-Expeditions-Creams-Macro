"""
Herm's Engine | Anime Expeditions
Run:  python main.py            (launches the docked macro UI)
      python main.py --test     (CLI diagnostics for mouse/keyboard/window)
"""
import os
import re
import sys
import time
import json
import subprocess
import threading
from datetime import date

from core import window as wm
from core import config
from core import keys
from core import settings as cfg
from core.window import WindowManager
from core.mouse import Mouse
from core.keyboard import Keyboard
from core import updater

# The API module: Api class (pywebview bridge), all layout constants,
# _init_layout(), _mac_panel_layout, _debug_dir, and every helper function
# that Api depends on.
from core import api as capi


def _get_build_info() -> str:
    """A "sub-version" for the startup log line, below the granularity of
    VERSION (which only bumps on tagged releases) -- the exact git commit
    (+dirty flag for uncommitted local changes) when running from source,
    since that's most of this app's own testing between releases and a
    pasted debug.log with no way to tell WHICH of several untagged fixes
    it came from is a lot less useful. A packaged exe has no .git folder
    (see core.constants -- BUNDLE_DIR is a onefile build's temp extraction
    dir), so this just falls back to "release build" there instead of
    failing loudly over something that was never going to work."""
    try:
        repo_dir = os.path.dirname(os.path.abspath(__file__))
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir, capture_output=True, text=True, timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if commit.returncode != 0:
            return "release build"
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True, timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        suffix = "+dirty" if dirty.returncode == 0 and dirty.stdout.strip() else ""
        return f"src {commit.stdout.strip()}{suffix}"
    except Exception:
        return "release build"


# ── App launch ───────────────────────────────────────────────────────────────


def _launch_ui():
    import webview  # imported lazily so --test works without pywebview/keyboard installed
    import keyboard

    # pywebview's frameless drag region defaults to starting a window-drag on
    # ANY mousedown inside .pywebview-drag-region, including on buttons/icons
    # nested in it (there's no CSS opt-out on Windows, unlike Electron's
    # -webkit-app-region) -- this restricts a drag to only start when the
    # click's literal target is the drag-region element itself, so clicking a
    # nav/titlebar button no longer drags the whole window.
    webview.settings['DRAG_REGION_DIRECT_TARGET_ONLY'] = True

    api = capi.Api()
    # First line of every session's debug.log on purpose -- exactly which
    # tagged version AND which exact source revision (for anyone running
    # from source between releases, which is most of this app's own
    # testing) produced a given log is otherwise unrecoverable once
    # several untagged fixes have landed since the last real release, and
    # a pasted debug.log with no version context at all wastes a round
    # trip just asking "which build is this from?" every time.
    api.push_log(f"[Macro] Herm's Engine v{updater.get_current_version()} ({_get_build_info()}) starting...")
    # Diagnostic: confirms whether set_dpi_aware() (called at import time,
    # above the wm.set_dpi_aware() call at module scope) actually took --
    # a non-100% value here with docking/clicks still landing wrong would
    # point elsewhere; still 100 despite real display scaling means it
    # didn't take and every fixed coordinate in core.runner is off. Every
    # fixed coordinate in core.runner was captured/tuned at 100% Windows
    # display scale -- set_dpi_aware() makes the PROCESS report real
    # physical pixels regardless of scale, but Windows still stretches
    # what's actually drawn on screen at non-100%, which is a real (if
    # smaller) source of drift set_dpi_aware() can't fix on its own. Below
    # 100% shows a one-time warning telling the user to fix it at the
    # source, same troubleshooting-log spirit as the DPI/focus fixes
    # already in core.window.
    if sys.platform == "darwin":
        # The two macOS permissions everything depends on -- surfaced
        # loudly at startup instead of letting "clicks do nothing" or
        # "windows won't move" be diagnosed from symptoms. See
        # core/window_mac.py's module docstring.
        try:
            from core import window_mac
            if not window_mac.ax_trusted():
                api.push_log("[Macro] macOS Accessibility permission NOT granted -- window arranging and "
                              "input will not work. Enable this app under System Settings > Privacy & "
                              "Security > Accessibility (and Input Monitoring), then restart it.")
        except Exception as exc:
            api.push_log(f"[Macro] Couldn't check macOS permissions: {exc}")
    scale = wm.get_display_scale_percent()
    api.push_log(f"[Macro] Display scale: {scale}%.")
    if scale != 100:
        api.push_log(f"[Macro] Windows display scale is {scale}%, not 100% -- this is a common cause of "
                       f"clicks/detection landing slightly wrong. Set it to 100% in Settings > System > Display, "
                       f"then restart your computer (not just the macro) so it fully takes effect.")
        api.push_ui("showScaleWarning")
    gui_wm = WindowManager(capi.GUI_TITLE)
    roblox_wm = WindowManager(config.ROBLOX_WINDOW_TITLE)  # only used for its resize/client-rect helpers below

    screen_w, screen_h = wm.get_screen_size()
    capi._init_layout()  # recalc all GUI constants from actual screen size
    l = capi.LAYOUT  # shorthand

    if sys.platform == "darwin":
        # Side-by-side arrangement (see core/dock.py's darwin GameDocker) needs the panel width
        # plus the full fixed game size in logical points. Smaller/lower-scaled MacBook displays
        # (e.g. a 13" panel left at its default 1280x800 scaled resolution) don't have that much
        # logical width even though the physical panel is plenty big -- Roblox ends up parked
        # partly or fully off-screen with no error, which just looks like "the game is too big".
        needed_w = capi.PANEL_WIDTH + 12 + l["game_w"]
        if screen_w < needed_w or screen_h < l["game_h"]:
            api.push_log(
                f"[Macro] Your display's logical resolution ({screen_w}x{screen_h}pt) is smaller than "
                f"what side-by-side docking needs ({needed_w}x{l['game_h']}pt) -- Roblox will be "
                f"placed partly or fully off-screen. Fix: System Settings > Displays > select a scaled "
                f"resolution with \\\"More Space\\\" (a higher point resolution, not necessarily higher "
                f"physical res) so it's at least that wide.")
    start_w, start_h = capi.GUI_WIDTH_COMPACT, capi.GUI_HEIGHT_COMPACT
    start_x = (screen_w - start_w) // 2
    start_y = (screen_h - start_h) // 2

    window = webview.create_window(
        capi.GUI_TITLE,
        url=capi.UI_INDEX,
        js_api=api,
        width=start_w,
        height=start_h,
        x=start_x,
        y=start_y,
        resizable=False,
        frameless=True,
        easy_drag=False,  # dragging is handled by the .pywebview-drag-region element in ui/index.html instead
    )
    api.set_window(window)

    def _set_window_icon_background():
        # pywebview's own icon= start() param only works on GTK/QT, not the
        # Windows EdgeChromium backend this app actually uses (see
        # core.window.set_window_icon) -- and the native window doesn't
        # exist to set an icon ON until webview.start()'s GUI loop actually
        # creates it, hence polling here rather than doing this right after
        # create_window() above.
        deadline = time.time() + 10
        while time.time() < deadline:
            hwnd = gui_wm.find()
            if hwnd:
                wm.set_window_icon(hwnd, capi.LOGO_ICO)
                return
            time.sleep(0.2)

    threading.Thread(target=_set_window_icon_background, daemon=True).start()

    def _check_for_update_background():
        # A few seconds after launch, not immediately -- so a slow/offline
        # GitHub request can never compete with the app's own startup for
        # attention. push_ui (no args, same pattern as showDocked/
        # showWaiting) just tells the UI to go ask get_update_info() for the
        # details once it actually has something to show.
        time.sleep(4)
        try:
            api._update_info = updater.check_for_update(log=api.push_log)
        except Exception as exc:
            api.push_log(f"[Update] Check failed: {exc}")
            return
        if api._update_info.get("available"):
            api.push_log(f'[Update] Version {api._update_info["version"]} is available.')
            api.push_ui("showUpdateAvailable")

    threading.Thread(target=_check_for_update_background, daemon=True).start()

    def _ensure_assets_background():
        # Assets/ ships as a loose folder beside the exe (see core.constants.
        # ASSETS_DIR), so a bare exe with no Assets next to it (shared solo,
        # or an old bootstrapper install from before the zip layout) would
        # have every image search dead on arrival. This restores it from the
        # release zip's Assets when missing -- a no-op costing one isdir/
        # listdir in the normal case, and on a background thread so a slow
        # download can never hold up startup.
        try:
            updater.ensure_assets_present(api.push_log)
        except Exception as exc:
            api.push_log(f"[Update] Assets check failed: {exc}")

    threading.Thread(target=_ensure_assets_background, daemon=True).start()

    def _dock_watchdog():
        """Runs for the app's whole lifetime, not just once at startup, so it
        also catches Roblox being launched late, or relaunched after a crash
        (a new hwnd that needs re-docking), not just the first window found.

        Wrapped in try/except per iteration on purpose: an unhandled exception
        in a daemon thread just kills the thread silently, and the UI would be
        stuck showing "waiting" forever with no error and no further retries,
        which looked exactly like the app being frozen/broken.
        """
        while not api.stopping.is_set():
            try:
                if api.game_hwnd and not wm.is_window(api.game_hwnd):
                    # tracked window died (closed/crashed): allow re-attaching to a new one
                    api.docker.docked = False
                    api.game_hwnd = None
                    api.push_ui("showWaiting")
                    api.push_log("Roblox window closed, waiting for it again.")

                # Explicit Un-Attach (Settings > Debug): skip auto-detect
                # entirely until the user picks a window and clicks Attach
                # again -- otherwise find_roblox_window() below would just
                # find the same still-open window and instantly redock it,
                # making Un-Attach a no-op.
                if api.dock_suspended:
                    time.sleep(2)
                    continue

                # A manual Attach pins the NEXT dock to a specific window
                # (see attach_roblox_window) instead of whatever
                # find_roblox_window() would grab on its own -- with
                # multiple Roblox windows open, that's always just the
                # first one EnumWindows happens to return, not necessarily
                # the one actually picked.
                if api.pinned_hwnd and wm.is_window(api.pinned_hwnd):
                    hwnd = api.pinned_hwnd
                else:
                    api.pinned_hwnd = None
                    hwnd = wm.find_roblox_window()  # title AND process name: a Chrome tab titled "Roblox" won't match
                if hwnd and (not api.docker.docked or hwnd != api.game_hwnd):
                    api.push_log("Roblox found, settling before docking...")
                    api.game_hwnd = hwnd

                    # Give a freshly-launched Roblox window a moment to finish its own
                    # startup/resize before we touch its borders and reparent it:
                    # docking it mid-launch is what left the game looking broken.
                    time.sleep(1.0)
                    if api.stopping.is_set():
                        return
                    if not wm.is_window(hwnd):
                        api.push_log("Roblox window disappeared before docking, will retry.")
                        api.game_hwnd = None
                        time.sleep(2)
                        continue

                    # Un-Attach (or a different Attach pick) can land WHILE
                    # this settle sleep was running -- without this check,
                    # the dock below would commit anyway, ignoring it: the
                    # window would end up reparented and hidden with
                    # api.game_hwnd already cleared back to None (Detach
                    # already ran), so nothing would be left tracking it to
                    # ever show it again. That's exactly what "Roblox just
                    # disappears and stays gone until I close the macro"
                    # was -- a still-hidden, still-parented child window
                    # that only went away when closing the app destroyed it.
                    if api.dock_suspended or (api.pinned_hwnd and api.pinned_hwnd != hwnd):
                        api.push_log("Dock aborted -- the Roblox Window selection changed while settling.")
                        api.game_hwnd = None
                        time.sleep(1)
                        continue

                    roblox_wm.hwnd = hwnd
                    lw = capi.LAYOUT  # computed game-window client size
                    roblox_wm.resize_client_to(lw["game_w"], lw["game_h"])

                    if sys.platform == "darwin":
                        # macOS can't embed another app's window (no
                        # SetParent -- see core/dock.py's darwin
                        # GameDocker), so instead of growing the GUI to
                        # make room for a docked child, the panel stays
                        # compact at the screen's left edge and Roblox is
                        # arranged immediately to its right at the exact
                        # reference size. (One-shot per dock, same as the
                        # Windows path -- if the game gets dragged away
                        # mid-session, image search still lands correctly
                        # via vision's reference-space scaling; it's just
                        # no longer beside the panel.)
                        # Both windows are placed from one layout (see
                        # _mac_panel_layout): the panel is created centered and
                        # compact, so it has to be moved AND grown to the left
                        # strip here -- leaving it centered is what put it
                        # floating over the middle of the game, and leaving it
                        # compact is what made the real UI unreachable.
                        layout = capi._mac_panel_layout()
                        gui_hwnd = gui_wm.find()
                        if gui_hwnd and not api.stopping.is_set():
                            api.gui_hwnd = gui_hwnd
                            with api._mac_geometry_lock:
                                api._apply_panel_geometry(
                                    layout["x"], layout["y"], layout["panel_w"], layout["panel_h"])
                                api._mac_panel_ready = True
                            api.docker.dock(hwnd, gui_hwnd, x=layout["game_x"], y=layout["game_y"])
                            api.pinned_hwnd = None
                            api.push_ui("showDocked")
                            api.push_log(
                                f'Roblox arranged beside the panel (macOS side-by-side mode): panel '
                                f'{layout["panel_w"]}x{layout["panel_h"]}, game at x={layout["game_x"]}.')
                        else:
                            api.push_log("Could not find the macro's own window, will retry.")
                        time.sleep(2)
                        continue

                    # The window may be minimized right now (Start Minimized, or
                    # the user minimized it while waiting). A resize issued on a
                    # minimized window is silently dropped and it restores at the
                    # old compact size (verified against pywebview 6.2.1), which
                    # docked Roblox into a 400px-wide window. Restore first.
                    window.restore()
                    time.sleep(0.2)
                    window.resize(capi.GUI_WIDTH_FULL, capi.GUI_HEIGHT_FULL)
                    window.move(0, 0)
                    time.sleep(0.3)
                    gui_hwnd = gui_wm.find()
                    if gui_hwnd and not api.stopping.is_set():
                        # Belt and braces: confirm the resize actually took before
                        # parenting Roblox into the window, falling back to a
                        # native MoveWindow if pywebview's resize was lost. Never
                        # dock into a still-compact window.
                        gui_wm.hwnd = gui_hwnd
                        l, t, r, b = wm.get_window_rect_screen(gui_hwnd)
                        if (r - l, b - t) != (capi.GUI_WIDTH_FULL, capi.GUI_HEIGHT_FULL):
                            wm.move_window(gui_hwnd, 0, 0, capi.GUI_WIDTH_FULL, capi.GUI_HEIGHT_FULL)
                            time.sleep(0.2)
                            l, t, r, b = wm.get_window_rect_screen(gui_hwnd)
                            if (r - l) <= capi.GUI_WIDTH_COMPACT + 50:
                                api.push_log("Macro window still compact, retrying dock...")
                                time.sleep(2)
                                continue
                            elif (r - l, b - t) != (capi.GUI_WIDTH_FULL, capi.GUI_HEIGHT_FULL):
                                api.push_log(f"Warning: Macro window size ({r - l}x{b - t}) is smaller than requested "
                                             f"({capi.GUI_WIDTH_FULL}x{capi.GUI_HEIGHT_FULL}) due to display resolution or DPI scaling. Docking anyway.")
                        api.gui_hwnd = gui_hwnd
                        # Final stopping re-check: several sleeps have passed
                        # since the one guarding this branch, and a dock()
                        # committed AFTER close set stopping would re-parent
                        # Roblox right before the window dies -- recreating
                        # the cascade the whole close path exists to prevent.
                        if api.stopping.is_set():
                            return
                        api.docker.dock(hwnd, gui_hwnd, x=0, y=capi.TITLEBAR_H,
                                        width=lw["game_w"], height=lw["game_h"])
                        # Stay hidden until the JS side explicitly shows it for the Task
                        # screen (showDocked() does that) -- Info/Settings/Macro Manager are the
                        # default/other screens now, and Roblox is a native window that
                        # would otherwise render on top of them regardless of DOM state.
                        # Cutout mode never hides the window (captures read its
                        # contents) -- "hidden" there is parked at the bottom of
                        # the z-order until show_game promotes it.
                        if api.docker.cutout:
                            wm.send_to_bottom(hwnd)
                        else:
                            wm.hide_window(hwnd)
                        api.pinned_hwnd = None  # dock succeeded -- back to normal auto-tracking of this hwnd
                        api.push_ui("showDocked")
                        api.push_log("Roblox docked.")
                    else:
                        api.push_log("Could not find the macro's own window to dock into, will retry.")
            except Exception as exc:
                api.push_log(f"Dock watchdog error: {exc}")

            # Cutout mode's glue: while the game is meant to be visible,
            # re-assert its over-the-slot position every tick (tracks a
            # dragged GUI, heals lost topmost). Skipped while hidden --
            # re-promoting the game over the Settings screen every 2s would
            # BE the bug.
            try:
                if (sys.platform != "darwin" and api.docker.cutout and api.docker.docked
                        and api._cutout_game_visible
                        and api.game_hwnd and wm.is_window(api.game_hwnd)
                        and api.gui_hwnd and wm.is_window(api.gui_hwnd)):
                    api.docker.dock(api.game_hwnd, api.gui_hwnd, x=0, y=capi.TITLEBAR_H,
                                    width=capi.LAYOUT["game_w"], height=capi.LAYOUT["game_h"])
            except Exception:
                pass

            time.sleep(2)

    def _register_hotkeys(hotkeys: dict):
        # The `keyboard` lib's global hooks need root on macOS -- a plain
        # user launch raises OSError somewhere in here. Hotkeys just being
        # unavailable (use the on-screen buttons) beats the app dying, so
        # the whole registration is best-effort on that platform.
        try:
            keyboard.unhook_all()
        except (OSError, ImportError):
            api.push_log("[Macro] Global hotkeys unavailable (macOS needs the app run with elevated "
                          "permissions for keyboard hooks) -- use the on-screen buttons instead.")
            return
        actions = {
            # Routed through JS so each reuses its existing JS-side logic
            # (switchScreen's hide/show coordination, startMacro's button-
            # state + error-log handling) instead of a second, competing
            # implementation living here in Python.
            "toggle_game": lambda: api.push_ui("toggleGameScreenHotkey"),
            "skip_waiting": lambda: api.push_ui("skipWaiting"),
            "macro_start": lambda: api.push_ui("startMacro"),
            "macro_pause": lambda: api.push_ui("togglePauseMacro"),
            "debug_screenshot": lambda: api.push_ui("saveDebugScreenshot"),
            "image_manager": lambda: api.push_ui("toggleImageManagerHotkey"),
            "toggle_compact": lambda: api.push_ui("toggleCompactStrip"),
            # NOT routed through push_ui/JS: stopping has to win over
            # everything else regardless of what the UI thread is doing
            # (mid screen-switch animation, waiting on an evaluate_js round
            # trip, etc.), so this calls straight into the runner's
            # threading.Event from the hotkey's own thread. The button-state
            # sync (disabling Start, etc.) still happens -- refreshStatus's
            # poll picks up is_macro_running() within its own next tick --
            # it just isn't gating the actual stop signal anymore.
            "macro_stop": lambda: api.stop_macro(),
        }
        for action, fn in actions.items():
            key = hotkeys.get(action) or capi.HOTKEY_DEFAULTS.get(action, "")
            if not key:
                continue
            try:
                keyboard.add_hotkey(key, fn, suppress=False)
            except (ValueError, ImportError, OSError):
                pass

    def on_shown():
        threading.Thread(target=_dock_watchdog, daemon=True).start()
        _register_hotkeys(api.get_hotkeys())
        api._on_hotkeys_changed = _register_hotkeys
        if cfg.load().get("start_minimized", False):
            window.minimize()

    def on_closing():
        # Fallback for close paths other than our custom titlebar button
        # (e.g. Alt+F4): close_window() already handles the normal case.
        api.detach_game_safely()
        api.persist_all_time()
        return True

    # Last-resort backstop: if the app exits any OTHER way -- an unhandled
    # exception during teardown, or webview.start() returning without the
    # graceful path having run -- atexit still detaches Roblox before the
    # process (and its child windows) go away. Cheap and idempotent.
    import atexit
    atexit.register(api.detach_game_safely)

    window.events.shown += on_shown
    window.events.closing += on_closing
    webview.start()
    # webview.start() returns once the window is gone -- detach here too, in
    # case the window died without firing our handlers.
    api.detach_game_safely()
    try:
        keyboard.unhook_all()
    except OSError:
        pass  # macOS without hook permissions -- nothing was ever hooked


# ── CLI diagnostics ──────────────────────────────────────────────────────────


def test_mouse():
    mouse = Mouse()
    print("Current cursor position:", mouse.position())
    print("Moving mouse in a small square in 2s...")
    time.sleep(2)
    x, y = mouse.position()
    for dx, dy in [(100, 0), (0, 100), (-100, 0), (0, -100)]:
        mouse.move_to(x + dx, y + dy)
        time.sleep(0.3)


def test_keyboard():
    print("Typing 'hello' in 3s -- click into a text field now...")
    time.sleep(3)
    kb = Keyboard()
    kb.type_text("hello")
    kb.tap(keys.VK_RETURN)


def test_window():
    hwnd = wm.find_roblox_window()
    if not hwnd:
        print("Roblox window not found -- open Roblox and try again.")
        return
    wm_ = WindowManager("Roblox")
    wm_.hwnd = hwnd
    print("Found Roblox window:", hwnd)
    print("Client size before:", wm_.get_client_size())
    wm_.resize_client_to()
    print("Client size after resize:", wm_.get_client_size())
    print("Client (0,0) -> screen:", wm_.client_to_screen(0, 0))


TEST_MENU = {
    "1": ("Test mouse", test_mouse),
    "2": ("Test keyboard", test_keyboard),
    "3": ("Test window (find + resize Roblox)", test_window),
}


def run_diagnostics():
    print("Anime Expeditions -- core input/window diagnostics")
    for key, (label, _) in TEST_MENU.items():
        print(f"  {key}) {label}")
    print("  4) Run all")
    choice = input("Select: ").strip()

    if choice == "4":
        for _, fn in TEST_MENU.values():
            fn()
        return

    entry = TEST_MENU.get(choice)
    if not entry:
        print("Unknown option.")
        return
    entry[1]()


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_diagnostics()
    else:
        _launch_ui()
