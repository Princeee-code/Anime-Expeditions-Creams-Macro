"""
Click-site coordinate defaults for the macro runner.

Every coordinate is in the docked 1152x756 game-client space.
These are the factory defaults — the user can override any of them
via Settings without a code change.

Extracted from core.runner_constants so the runner module can import
them without pulling in the rest of the constants file.
"""

__all__ = ["DEFAULT_COORDS"]

DEFAULT_COORDS = {
    "difficulty_normal_x": 311,
    "difficulty_normal_y": 315,
    "difficulty_hard_x": 364,
    "difficulty_hard_y": 315,
    "matchmaking_region_x": 277,
    "matchmaking_region_y": 543,
    "matchmaking_region_w": 437,
    "matchmaking_region_h": 45,
    "story_click_x": 666,
    "story_click_y": 147,
    "stage_row_x": 246,
    "stage_row_y": 230,
    "stage_row_height": 56,
    "act_row_x": 250,
    "act_row_y": 267,
    "act_row_height": 129,
    "challenge_stage_1_x": 460,
    "challenge_stage_1_y": 277,
    "challenge_stage_2_x": 460,
    "challenge_stage_2_y": 400,
    "challenge_stage_3_x": 460,
    "challenge_stage_3_y": 533,
    "expedition_difficulty_x": 1094,
    "expedition_difficulty_y": 456,
    "team_loadout_x": 800,
    "team_loadout_y": 324,
    "team_loadout_row_height": 126,
    "screen_middle_x": 576,
    "screen_middle_y": 378,
    "unit_info_reset_x": 3,
    "unit_info_reset_y": 3,
}
