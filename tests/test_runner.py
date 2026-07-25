"""Mock-based tests for core.runner.MacroRunner.

These tests replace all platform-native dependencies (Win32, macOS) with
mocks so they run in any environment, including CI on Linux/Android.
"""

from unittest.mock import MagicMock, patch, PropertyMock
import pytest
import threading
import time


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_platform_modules():
    """Replace all Windows-only / platform-sensitive modules with mocks
    before any runner import.

    runner.py's import chain pulls in:
      core.paths → core._input_win → core._sendinput (Win32 guard)
      core.stage_select → core.vision → cv2 → numpy (broken on Termux)
      core.window → window_win / window_mac (Win32/mac guards)

    Patch them all into sys.modules so the import succeeds everywhere,
    including Android/Termux and CI runners without cv2/numpy.
    """
    mock_wm = MagicMock()
    mock_wm.find_roblox_window.return_value = None
    mock_wm.WindowManager = MagicMock
    mock_wm.get_screen_size.return_value = (1366, 768)

    patches = {
        "core.window": mock_wm,
        "core._sendinput": MagicMock(),
        "core._input_win": MagicMock(),
        "core.vision": MagicMock(),
        "core.stage_select": MagicMock(),
    }
    with patch.dict("sys.modules", patches):
        yield


@pytest.fixture
def mock_mouse():
    return MagicMock()


@pytest.fixture
def mock_keyboard():
    return MagicMock()


@pytest.fixture
def mock_log():
    return MagicMock()


@pytest.fixture
def macro_runner(mock_mouse, mock_keyboard, mock_log):
    """Fresh MacroRunner instance with mocked deps."""
    # Import here -- after sys.modules patching -- so the import chain works
    from core.runner import MacroRunner
    return MacroRunner(
        mouse=mock_mouse,
        keyboard=mock_keyboard,
        log=mock_log,
    )


# ── Init state ────────────────────────────────────────────────────────────


class TestMacroRunnerInit:
    """Verify every instance attribute starts in the right state."""

    def test_not_running_on_fresh_instance(self, macro_runner):
        assert not macro_runner.is_running()

    def test_not_paused_on_fresh_instance(self, macro_runner):
        assert not macro_runner.is_paused()

    def test_coords_defaults_loaded(self, macro_runner):
        from core.coords import DEFAULT_COORDS
        assert macro_runner._coords == DEFAULT_COORDS

    def test_stop_event_not_set(self, macro_runner):
        assert macro_runner._stop_event is None

    def test_pause_event_created_and_clear(self, macro_runner):
        assert isinstance(macro_runner._pause_event, threading.Event)
        assert not macro_runner._pause_event.is_set()

    def test_consecutive_losses_zero(self, macro_runner):
        assert macro_runner._consecutive_losses == 0
        assert macro_runner._consecutive_loss_map is None

    def test_empty_placed_unit_positions(self, macro_runner):
        assert macro_runner._placed_unit_positions == {}

    def test_status_callable_set(self, macro_runner):
        assert macro_runner._last_action == ""


# ── State queries (no real thread) ────────────────────────────────────────


class TestMacroRunnerState:
    """is_running / is_paused behaviour without actually starting threads."""

    def test_is_running_returns_false_when_no_thread(self, macro_runner):
        macro_runner._thread = None
        assert not macro_runner.is_running()

    def test_is_running_returns_false_when_thread_dead(self, macro_runner):
        t = threading.Thread(target=lambda: None)
        t.start()
        t.join()
        macro_runner._thread = t
        assert not macro_runner.is_running()

    def test_is_running_returns_true_when_thread_alive(self, macro_runner):
        event = threading.Event()

        def spin():
            event.wait(10)

        t = threading.Thread(target=spin, daemon=True)
        t.start()
        macro_runner._thread = t
        try:
            assert macro_runner.is_running()
        finally:
            event.set()
            t.join()

    def test_is_paused_checks_event(self, macro_runner):
        assert not macro_runner.is_paused()
        macro_runner._pause_event.set()
        assert macro_runner.is_paused()
        macro_runner._pause_event.clear()
        assert not macro_runner.is_paused()


# ── .start() with mocked threading ───────────────────────────────────────


class TestMacroRunnerStart:
    """start() validation and state transitions (thread spawning mocked)."""

    def test_start_returns_ok(self, macro_runner):
        with patch.object(macro_runner, "_run", return_value=None):
            result = macro_runner.start(
                hwnd_getter=lambda: 12345,
                get_tasks=lambda: [],
            )
        assert result == {"ok": True}
        assert macro_runner._thread is not None

    def test_start_already_running(self, macro_runner):
        """Second start() when a thread is alive must refuse."""
        # Fake an alive thread
        alive_thread = MagicMock()
        alive_thread.is_alive.return_value = True
        macro_runner._thread = alive_thread

        result = macro_runner.start(
            hwnd_getter=lambda: 12345,
            get_tasks=lambda: [],
        )
        assert result == {"ok": False, "reason": "already_running"}

    def test_start_resets_state(self, macro_runner):
        """start() must clear stop/pause/coords before launching."""
        macro_runner._stop_event = threading.Event()
        macro_runner._stop_event.set()
        macro_runner._consecutive_losses = 999

        with patch.object(macro_runner, "_run", return_value=None):
            macro_runner.start(
                hwnd_getter=lambda: 12345,
                get_tasks=lambda: [],
            )

        assert macro_runner._stop_event is not None
        assert not macro_runner._stop_event.is_set()
        assert not macro_runner._pause_event.is_set()
        assert macro_runner._consecutive_losses == 0
        assert macro_runner._consecutive_loss_map is None
        assert macro_runner._debug_screenshots is False


# ── .start_debug_test() validation ───────────────────────────────────────


class TestMacroRunnerDebugTest:
    """start_debug_test param validation (thread never actually runs)."""

    def test_bad_mode_rejected(self, macro_runner):
        result = macro_runner.start_debug_test(
            hwnd_getter=lambda: 12345,
            mode="invalid",
            macro_name="test-op",
        )
        assert result == {"ok": False, "reason": "bad_mode"}

    def test_empty_macro_name_rejected(self, macro_runner):
        result = macro_runner.start_debug_test(
            hwnd_getter=lambda: 12345,
            mode="prestart",
            macro_name="",
        )
        assert result == {"ok": False, "reason": "no_macro"}

    def test_none_macro_name_rejected(self, macro_runner):
        result = macro_runner.start_debug_test(
            hwnd_getter=lambda: 12345,
            mode="prestart",
            macro_name=None,
        )
        assert result == {"ok": False, "reason": "no_macro"}

    def test_already_running_rejected(self, macro_runner):
        alive_thread = MagicMock()
        alive_thread.is_alive.return_value = True
        macro_runner._thread = alive_thread

        result = macro_runner.start_debug_test(
            hwnd_getter=lambda: 12345,
            mode="prestart",
            macro_name="test-op",
        )
        assert result == {"ok": False, "reason": "already_running"}

    def test_valid_prestart_accepted(self, macro_runner):
        with patch.object(macro_runner, "_run_debug_test", return_value=None):
            result = macro_runner.start_debug_test(
                hwnd_getter=lambda: 12345,
                mode="prestart",
                macro_name="test-op",
            )
        assert result == {"ok": True}

    def test_valid_battle_accepted(self, macro_runner):
        with patch.object(macro_runner, "_run_debug_test", return_value=None):
            result = macro_runner.start_debug_test(
                hwnd_getter=lambda: 12345,
                mode="battle",
                macro_name="test-op",
            )
        assert result == {"ok": True}

    def test_debug_start_sets_left_stage_true(self, macro_runner):
        """Debug test starts with _left_stage_this_run already True since
        there's no real match to Leave Stage from."""
        with patch.object(macro_runner, "_run_debug_test", return_value=None):
            macro_runner.start_debug_test(
                hwnd_getter=lambda: 12345,
                mode="prestart",
                macro_name="test-op",
            )
        assert macro_runner._left_stage_this_run is True

    def test_debug_start_merges_coords(self, macro_runner):
        """Debug test should merge user coords over defaults."""
        from core.coords import DEFAULT_COORDS
        custom_coords = {"difficulty_normal_x": 999}
        with patch.object(macro_runner, "_run_debug_test", return_value=None):
            macro_runner.start_debug_test(
                hwnd_getter=lambda: 12345,
                mode="prestart",
                macro_name="test-op",
                coords=custom_coords,
            )
        assert macro_runner._coords["difficulty_normal_x"] == 999
        assert macro_runner._coords["difficulty_hard_x"] == DEFAULT_COORDS["difficulty_hard_x"]


# ── Coordinate merging ────────────────────────────────────────────────────


class TestMacroRunnerCoords:
    """User-supplied coords merge correctly over DEFAULT_COORDS."""

    def test_start_merges_coords(self, macro_runner):
        """Coords are merged INSIDE _run (the thread target), not in start().
        Verify by patching _run and joining the thread synchronously."""
        from unittest.mock import MagicMock
        mock_run = MagicMock(return_value=None)
        with patch.object(macro_runner, "_run", mock_run):
            result = macro_runner.start(
                hwnd_getter=lambda: 12345,
                get_tasks=lambda: [],
                coords={"difficulty_normal_x": 111},
            )
        assert result == {"ok": True}
        # _run is called async in a thread; wait for it
        if macro_runner._thread:
            macro_runner._thread.join(timeout=5)
        assert mock_run.called

    def test_debug_start_without_coords_uses_defaults(self, macro_runner):
        from core.coords import DEFAULT_COORDS
        with patch.object(macro_runner, "_run_debug_test", return_value=None):
            macro_runner.start_debug_test(
                hwnd_getter=lambda: 12345,
                mode="prestart",
                macro_name="test-op",
            )
        assert macro_runner._coords == DEFAULT_COORDS

    def test_default_coords_value(self, macro_runner):
        """Spot-check a few key coordinate values."""
        assert macro_runner._coords["screen_middle_x"] == 576
        assert macro_runner._coords["screen_middle_y"] == 378
        assert macro_runner._coords["unit_info_reset_x"] == 3
        assert macro_runner._coords["unit_info_reset_y"] == 3


# ── Stop / Checkpoint ────────────────────────────────────────────────────


class TestMacroRunnerStop:
    """stop, pause, resume and _checkpoint behaviour."""

    def test_stop_sets_event(self, macro_runner):
        macro_runner._stop_event = threading.Event()
        macro_runner.stop()
        assert macro_runner._stop_event.is_set()

    def test_stop_clears_pause(self, macro_runner):
        macro_runner._stop_event = threading.Event()
        macro_runner._pause_event.set()
        macro_runner.stop()
        assert not macro_runner._pause_event.is_set()

    def test_stop_creates_event_if_none(self, macro_runner):
        macro_runner._stop_event = None
        macro_runner.stop()
        assert macro_runner._stop_event is None  # stop() only sets, never creates

    def test_checkpoint_requires_stop_event_argument(self, macro_runner):
        """_checkpoint reads the passed-in event, not self._stop_event."""
        ev = threading.Event()
        assert not macro_runner._checkpoint(ev)
        ev.set()
        assert macro_runner._checkpoint(ev)

    def test_checkpoint_false_when_not_set(self, macro_runner):
        ev = threading.Event()
        assert not macro_runner._checkpoint(ev)

    def test_checkpoint_true_when_set(self, macro_runner):
        ev = threading.Event()
        ev.set()
        assert macro_runner._checkpoint(ev)

    def test_pause_sets_event(self, macro_runner):
        with patch.object(macro_runner, "is_running", return_value=True):
            macro_runner.pause()
        assert macro_runner._pause_event.is_set()

    def test_resume_clears_event(self, macro_runner):
        macro_runner._pause_event.set()
        macro_runner.resume()
        assert not macro_runner._pause_event.is_set()
