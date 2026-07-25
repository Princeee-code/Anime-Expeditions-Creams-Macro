FIXED_WIN_W = 1152
FIXED_WIN_H = 756

ROBLOX_WINDOW_TITLE = "Roblox"

# Minimum pixel width for the side-column panel. Below this the multi-column
# layout (Task, Macro Manager, Settings) becomes unusable, so the game window
# shrinks to leave room. Set to what fits on a 1366px screen with 1152:756
# aspect-ratio game.
PANEL_MIN_WIDTH = 214

# GUI chrome heights (mirrors main.py's constants -- duplicated here so
# compute_layout is self-contained and importable from tests/CLI).
_TITLEBAR_H = 44
_LOGS_H = 160
_COMPACT_STRIP_H = 50


def compute_layout(screen_w: int, screen_h: int) -> dict:
    """Return a layout dict that fits *screen_w x screen_h* at 100% scale.

    The game-window client area is sized to fill the available space while
    preserving the 1152:756 reference aspect ratio.  The vision pipeline
    normalises every capture back to FIXED_WIN_W/H before template matching
    and scales clicks back to the real window size (vision.ref_to_screen),
    so templates and hardcoded coordinates work unchanged at *any* game-
    window size as long as the aspect ratio is preserved.

    Returned keys:
      game_w, game_h  -- game-client pixel size
      panel_w         -- side-column width (0 = compact / no panel)
      full_w, full_h  -- total GUI-window outer size
      compact         -- True when the panel is too narrow for the full layout
      titlebar_h      -- title-bar height for the docked-game Y offset
    """
    # ── Available vertical space ────────────────────────────────────────
    avail_h = screen_h - _TITLEBAR_H - _LOGS_H
    if avail_h < 200:          # very cramped: drop the log strip
        avail_h = screen_h - _TITLEBAR_H - _COMPACT_STRIP_H

    game_h = min(FIXED_WIN_H, max(200, avail_h))
    # Preserve 1152:756 aspect ratio (≈1.5238)
    game_w = round(game_h * FIXED_WIN_W / FIXED_WIN_H)
    panel_w = screen_w - game_w

    # ── Wide screen: game at reference size, 400 px panel ───────────────
    if game_w >= FIXED_WIN_W and panel_w >= 400:
        p = min(panel_w, 400)
        return {
            "game_w": FIXED_WIN_W,
            "game_h": FIXED_WIN_H,
            "panel_w": p,
            "full_w": FIXED_WIN_W + p,
            "full_h": _TITLEBAR_H + FIXED_WIN_H + _LOGS_H,
            "compact": False,
            "titlebar_h": _TITLEBAR_H,
        }

    # ── Panel too narrow?  Shrink the game to free up width ─────────────
    if panel_w < PANEL_MIN_WIDTH and game_w > 0:
        game_w = screen_w - PANEL_MIN_WIDTH
        game_h = round(game_w * FIXED_WIN_H / FIXED_WIN_W)
        panel_w = PANEL_MIN_WIDTH

    # ── Still too narrow → compact mode (no panel, game fills) ──────────
    if panel_w < PANEL_MIN_WIDTH or panel_w <= 0:
        game_w = screen_w
        game_h = round(game_w * FIXED_WIN_H / FIXED_WIN_W)
        return {
            "game_w": game_w,
            "game_h": game_h,
            "panel_w": 0,
            "full_w": screen_w,
            "full_h": _TITLEBAR_H + game_h + _COMPACT_STRIP_H,
            "compact": True,
            "titlebar_h": _TITLEBAR_H,
        }

    # ── Normal: game fills avail height, panel gets the remainder ───────
    return {
        "game_w": game_w,
        "game_h": game_h,
        "panel_w": panel_w,
        "full_w": game_w + panel_w,
        "full_h": _TITLEBAR_H + game_h + _LOGS_H,
        "compact": False,
        "titlebar_h": _TITLEBAR_H,
    }
