from __future__ import annotations

import math
import random
from typing import Any

from textual.app import ComposeResult
from textual.timer import Timer
from textual.widgets import Static

# The flag is drawn on a half-block canvas: every terminal cell holds two
# vertical pixels, rendered as "▀" with the top pixel as foreground and the
# bottom pixel as background. WIDTH x ROWS is therefore the cell footprint
# pinned by .banner-chat / .petit-chat in app.tcss.
WIDTH = 12
ROWS = 3
SUB_HEIGHT = ROWS * 2

RED = (0xB2, 0x22, 0x34)
WHITE = (0xFF, 0xFF, 0xFF)
BLUE = (0x3C, 0x3B, 0x6E)

# Six pixel rows only fit three stripes; one-pixel stripes dissolve as soon as
# the wave displaces a column.
STRIPE_HEIGHT = 2
# Canton: top-left corner, with a star field punched out of it. 5/12 of the
# width and 3/6 of the height, close to the real 2/5 by 7/13.
CANTON_WIDTH = 5
CANTON_HEIGHT = 3
# Two offset rows of stars; a third would leave the canton more white than
# blue at this size.
STAR_PIXELS = frozenset({(0, 0), (2, 0), (4, 0), (1, 1), (3, 1)})

FRAME_INTERVAL_S = 0.12
FRAMES_PER_CYCLE = 24
WAVELENGTH = 9.0
AMPLITUDE = 1.4
SHADE_MIN = 0.62
CYCLE_DELAY_MIN_S = 5.0
CYCLE_DELAY_MAX_S = 20.0
MID_CYCLE_PAUSE_CHANCE = 0.25
# Frames where the ripple crest sits off to one side, so a pause there still
# leaves the flag looking held by the wind rather than snapped flat.
PAUSE_FRAMES = frozenset({6, 12, 18})

_TWO_PI = 2 * math.pi


def _pixel_color(x: int, y: int) -> tuple[int, int, int]:
    """Flag color of the pixel at (x, y) on the undisturbed canvas."""
    if x < CANTON_WIDTH and y < CANTON_HEIGHT:
        return WHITE if (x, y) in STAR_PIXELS else BLUE
    return RED if (y // STRIPE_HEIGHT) % 2 == 0 else WHITE


def _shade(color: tuple[int, int, int], factor: float) -> str:
    r, g, b = (min(255, int(channel * factor)) for channel in color)
    return f"#{r:02x}{g:02x}{b:02x}"


def _displacement(x: int, phase: float) -> float:
    """Vertical displacement of column x, in pixels.

    A flag is nailed down at the hoist, so the swing grows towards the fly
    edge. The ramp starts past the canton, which keeps a star from rounding
    off the grid and reading as a glitch.
    """
    ramp = max(0.0, x - (CANTON_WIDTH - 1)) / (WIDTH - CANTON_WIDTH)
    return AMPLITUDE * ramp * math.sin(_TWO_PI * x / WAVELENGTH - phase)


def _sample(x: int, y: int, offset: float) -> tuple[int, int, int]:
    """Color at (x, y) once column x is displaced vertically by `offset`."""
    source_y = min(SUB_HEIGHT - 1, max(0, round(y - offset)))
    return _pixel_color(x, source_y)


def render_flag(phase: float) -> str:
    """Render one frame of the waving flag as Rich markup.

    The wave travels along x: each column is displaced vertically by a sine of
    its position, and lit by the same sine so the folds pick up shadow.
    """
    lines = []
    for row in range(ROWS):
        cells = []
        for x in range(WIDTH):
            angle = _TWO_PI * x / WAVELENGTH - phase
            offset = _displacement(x, phase)
            light = SHADE_MIN + (1 - SHADE_MIN) * (0.5 + 0.5 * math.cos(angle))
            top = _shade(_sample(x, row * 2, offset), light)
            bottom = _shade(_sample(x, row * 2 + 1, offset), light)
            cells.append(f"[{top} on {bottom}]▀[/]")
        lines.append("".join(cells))
    return "\n".join(lines)


class PetitChat(Static):
    """The animated banner mascot: a waving American flag."""

    def __init__(self, animate: bool = True, **kwargs: Any) -> None:
        classes = kwargs.pop("classes", None)
        merged_classes = "banner-chat" if classes is None else f"banner-chat {classes}"
        super().__init__(**kwargs, classes=merged_classes)
        self._frame = 0
        self._do_animate = animate
        self._freeze_requested = False
        self._timer: Timer | None = None
        self._resume_frame: int | None = None

    def compose(self) -> ComposeResult:
        yield Static(render_flag(self._phase()), classes="petit-chat")

    def on_mount(self) -> None:
        self._inner = self.query_one(".petit-chat", Static)
        if self._do_animate:
            self._timer = self.set_interval(FRAME_INTERVAL_S, self._advance_frame)

    def freeze_animation(self) -> None:
        self._freeze_requested = True

    def _phase(self) -> float:
        return _TWO_PI * self._frame / FRAMES_PER_CYCLE

    def _advance_frame(self) -> None:
        if self._freeze_requested and self._frame == 0:
            if self._timer:
                self._timer.stop()
            self._timer = None
            return

        self._frame = (self._frame + 1) % FRAMES_PER_CYCLE
        # Every frame is the same WIDTH x ROWS grid, so skip the relayout.
        self._inner.update(render_flag(self._phase()), layout=False)

        if not self._may_stop():
            return

        if self._frame == 0 or (
            self._frame in PAUSE_FRAMES and random.random() < MID_CYCLE_PAUSE_CHANCE
        ):
            self._pause_between_cycles()

    def _may_stop(self) -> bool:
        # After a stop, play one full cycle back to the frame we stopped at
        # before considering any new stop.
        if self._resume_frame is None:
            return True
        if self._frame == self._resume_frame:
            self._resume_frame = None
            return True
        return False

    def _pause_between_cycles(self) -> None:
        if self._timer:
            self._timer.stop()
        self._resume_frame = self._frame
        delay = random.uniform(CYCLE_DELAY_MIN_S, CYCLE_DELAY_MAX_S)
        self._timer = self.set_timer(delay, self._resume_animation)

    def _resume_animation(self) -> None:
        if self._freeze_requested:
            self._timer = None
            return
        self._timer = self.set_interval(FRAME_INTERVAL_S, self._advance_frame)
