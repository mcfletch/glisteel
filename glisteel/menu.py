"""The screens around the outside of the race.

Starting the game with no arguments should be a reasonable thing to do, and this
is what makes it one: a menu that offers what can be driven, a chooser that
shows each track by its own picture and its own best time, and a finish that
says where the lap just driven came.

Each is a plain function returning a ``Panel`` built from OpenGLContext's
overlay UI, so they take the player's interface scale, their skin and their key
handling without knowing anything about any of it:

:func:`main_menu`
    Drive, Tracks, Settings, Quit -- and Resume when a race is running.
:func:`track_screen`
    The library (:mod:`glisteel.tracks`) as a band of pictures, each with what
    the track is and the quickest lap driven on it.
:func:`finish_screen`
    The time, where it came, and what to do next.

Everything a test needs to know about these is structural -- which buttons a
screen has, what each does, which tracks it offers -- so all of it is exercised
with no window at all. Building a panel touches no GL.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from OpenGLContext.ui.gallery import Carousel
from OpenGLContext.ui.layout import Column, Row
from OpenGLContext.ui.panel import Panel
from OpenGLContext.ui.widgets import Button, Label, Select, Separator, Spacer

__all__ = ['GAME_TITLE', 'NO_TRACKS', 'NEVER_DRIVEN', 'FINISHED', 'BEST',
           'main_menu', 'track_screen', 'finish_screen']

#: The name of the game, in exactly one place.
GAME_TITLE = 'GLinting Steel'

#: How wide the menus are, in characters.
MENU_COLUMNS = 44

#: What the chooser says when there is nothing to drive. Not an error: a fresh
#: install is exactly this, and the answer is to bake a world.
NO_TRACKS = 'No tracks yet — bake one with oglc-bake'

#: What stands where a best lap would go on a track never driven.
NEVER_DRIVEN = '--:--.---'

#: What the finish says when the race was driven home, and when the lap just
#: driven is the quickest on this track.
FINISHED = 'FINISHED'
BEST = 'A NEW BEST'

#: How many tracks the band shows at once. Odd, so the chosen one has a middle
#: to sit in.
TRACKS_SHOWN = 5


def main_menu(on_drive: Callable[[], None] | None = None,
              on_tracks: Callable[[], None] | None = None,
              on_settings: Callable[[], None] | None = None,
              on_quit: Callable[[], None] | None = None,
              on_resume: Callable[[], None] | None = None,
              subtitle: str = '') -> Panel:
    """The first screen, and the one Escape brings up mid-race.

    From a standing start there is nothing behind it, so Escape does nothing and
    leaving is what Quit is for. **Mid-race there is**, and ``on_resume`` is
    then offered first and Escape leaves the screen -- because a player who
    pressed Escape meaning "close this" must never find they have thrown the
    race away instead.
    """
    racing = on_resume is not None
    buttons = [
        ('resume', 'Resume', on_resume, True) if racing else None,
        ('drive', 'Drive', on_drive, not racing),
        ('tracks', 'Tracks', on_tracks, False),
        ('settings', 'Settings', on_settings, False),
        ('quit', 'Quit', on_quit, False),
    ]
    children: list[Any] = [Label(text=GAME_TITLE, name='title')]
    if subtitle:
        children.append(Label(text=subtitle, wrap=True, name='subtitle'))
    children.append(Separator(top=6))
    children.extend(_buttons(buttons))
    panel = Panel(title='', scrim=True, modal=True, closeOnEscape=racing,
                  preferredColumns=MENU_COLUMNS,
                  children=[Column(children=children, spacing=4)])
    if on_resume is not None:
        panel.on_close = lambda _closing, resume=on_resume: resume()
    return panel


def track_screen(tracks: Sequence[Any],
                 chosen: Any = None,
                 records: Any = None,
                 on_choose: Callable[[Any], None] | None = None,
                 on_cancel: Callable[[], None] | None = None) -> Panel:
    """Choose a world to drive.

    A drop-down is the wrong control. What tells one circuit from another is
    what it *looks* like and how long it is, and a list of names makes a player
    start each in turn to find out which is which. So the tracks are a band of
    their own pictures, with the length, what carries the road, and the quickest
    lap driven on it under the one selected.

    ``records`` is ``{track key: best Record}``; a track never driven shows
    :data:`NEVER_DRIVEN` rather than nothing, so the row is the same shape
    either way.
    """
    tracks = list(tracks)
    times = dict(records or {})
    chooser = _track_chooser(tracks, chosen)
    caption = Label(text=_caption(tracks, chooser, times), wrap=True,
                    name='caption')
    drive = Button(text='Drive', name='drive', role='primary')
    cancel = Button(text='Cancel', name='cancel')
    drive.enabled = bool(tracks)

    def picked(widget: Any) -> None:
        caption.text = _caption(tracks, widget, times)
    chooser.on_change = picked

    panel = Panel(title='Tracks', scrim=True, modal=True,
                  # Wider than the other screens: a band of pictures needs the
                  # room, and cramping them defeats showing art at all.
                  preferredColumns=MENU_COLUMNS * 2,
                  children=[Column(spacing=4, children=[
                      chooser, caption, Separator(top=6),
                      Row(children=[Spacer(), cancel, drive], spacing=8, top=8,
                          name='buttons')])])
    answered: list[bool] = []

    def finish(started: bool) -> None:
        if answered:
            return
        answered.append(started)
        panel.close(started)
        found = _selected(tracks, chooser) if started else None
        if found is not None and on_choose is not None:
            on_choose(found)
        elif not started and on_cancel is not None:
            on_cancel()

    drive.on_activate = lambda _widget: finish(True)
    cancel.on_activate = lambda _widget: finish(False)
    panel.on_close = lambda _closing: finish(False)
    return panel


def finish_screen(result: Any, place: int | None = None,
                  records: Sequence[Any] = (),
                  track: Any = None,
                  on_again: Callable[[], None] | None = None,
                  on_tracks: Callable[[], None] | None = None,
                  on_quit: Callable[[], None] | None = None) -> Panel:
    """The end of a race: what happened, and what to do about it.

    Two things a driver wants and no more: **the time**, and **whether it beat
    anything**. ``place`` is where the lap landed in this track's table,
    counting from one, or None for one that did not make it -- which is not a
    failure and is not dressed as one.

    There is nothing behind this screen, so Escape does not close it: the race
    is over and the choice of what happens next has to be made.
    """
    heading = FINISHED if result.finished else str(result.outcome or '').upper()
    children: list[Any] = [Label(text=heading, name='heading')]
    if track is not None:
        children.append(Label(text=str(track.name), name='track'))
    if result.seconds is not None:
        children.append(Label(text=_clock(result.seconds), name='time'))
        children.append(Label(text=_placing(place), name='placing'))
    children.append(Separator(top=6))
    children.extend(_table(records))
    children.append(Separator(top=6))
    children.extend(_buttons([
        ('again', 'Drive it again', on_again, True),
        ('tracks', 'Another track', on_tracks, False),
        ('quit', 'Quit', on_quit, False)]))
    return Panel(title='', scrim=True, modal=True, closeOnEscape=False,
                 preferredColumns=MENU_COLUMNS,
                 children=[Column(children=children, spacing=4)])


# -- the pieces ----------------------------------------------------------------

def _buttons(entries: Sequence[Any]) -> list[Any]:
    """One button per entry of ``(name, text, handler, primary)``."""
    made = []
    for entry in entries:
        if entry is None:
            continue
        name, text, handler, primary = entry
        widget = Button(text=text, name=name,
                        role='primary' if primary else '')
        if handler is not None:
            widget.on_activate = lambda _widget, call=handler: call()
        else:
            widget.on_activate = lambda _widget: None
        made.append(widget)
    return made


def _track_chooser(tracks: Sequence[Any], chosen: Any) -> Any:
    """The band of tracks, or a dead drop-down when there are none."""
    if not tracks:
        empty = Select(name='track', options=[''], optionLabels=[NO_TRACKS])
        empty.enabled = False
        return empty
    wanted = chosen.tileset if chosen is not None else tracks[0].tileset
    return Carousel(
        name='track', visibleCount=TRACKS_SHOWN,
        options=[track.tileset for track in tracks],
        optionLabels=[track.name for track in tracks],
        # Empty for a track with no picture, which the band draws as a plate.
        optionImages=[track.picture or '' for track in tracks],
        value=wanted)


def _selected(tracks: Sequence[Any], chooser: Any) -> Any:
    """Which track the chooser is on, or None where there are none."""
    for track in tracks:
        if track.tileset == chooser.value:
            return track
    return None


def _caption(tracks: Sequence[Any], chooser: Any, times: Any) -> str:
    """What the selected track is, and the quickest lap driven on it."""
    track = _selected(tracks, chooser)
    if track is None:
        return NO_TRACKS
    best = times.get(track.key)
    return '%s   best %s' % (track.summary(),
                             best.clock() if best is not None else NEVER_DRIVEN)


def _table(records: Sequence[Any]) -> list[Any]:
    """The kept times for this track, quickest first."""
    return [Label(text='%d   %s   %s' % (place, one.clock(), one.when),
                  name='record-%d' % place)
            for place, one in enumerate(records, start=1)]


def _placing(place: int | None) -> str:
    """Where a lap landed, said the way a driver would hear it."""
    if place is None:
        return ''
    return BEST if place == 1 else 'Number %d on this track' % place


def _clock(seconds: float) -> str:
    """A lap time as a driver reads it."""
    minutes, rest = divmod(max(0.0, float(seconds)), 60.0)
    return '%d:%06.3f' % (int(minutes), rest)
