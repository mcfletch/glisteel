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
:func:`download_screen`
    What is on offer, what it costs, whose it is, and how far a fetch has got;
    :class:`Downloads` keeps the download across openings of it.
:func:`driving_screen`
    Which of the five ways of driving is in use, each in its own words.
:func:`finish_screen`
    The time, where it came, and what to do next.

Everything a test needs to know about these is structural -- which buttons a
screen has, what each does, which tracks it offers -- so all of it is exercised
with no window at all. Building a panel touches no GL.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from OpenGLContext.ui import contentscreen
from OpenGLContext.ui.contentscreen import ContentScreen
from OpenGLContext.ui.gallery import Carousel
from OpenGLContext.ui.layout import Column, Row
from OpenGLContext.ui.panel import Panel
from OpenGLContext.ui.widgets import (
    Button,
    Label,
    Select,
    Separator,
    Spacer,
)

__all__ = ['ALL_HERE', 'BEST', 'FINISHED', 'GAME_TITLE', 'NEVER_DRIVEN',
           'NO_TRACKS', 'STOPPED', 'Downloads', 'download_screen',
           'driving_screen',
           'finish_screen', 'main_menu', 'track_screen']

#: The name of the game, in exactly one place.
GAME_TITLE = 'GLinting Steel'

#: How wide the menus are, in characters.
MENU_COLUMNS = 44

#: What the chooser says when there is nothing to drive. Not an error: a fresh
#: install is exactly this, and the answer is to fetch one or bake one.
NO_TRACKS = 'No tracks yet — download one, or bake one with glisteel-bake'

#: What the download screen says when there is nothing left to fetch. The
#: ordinary end state of downloading things, not a failure.
ALL_HERE = contentscreen.ALL_HERE

#: What it says about a download the player stopped. Distinct from a failure:
#: nothing went wrong, and telling somebody their own decision was an error is
#: a poor way to answer it.
STOPPED = contentscreen.STOPPED

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
              on_driving: Callable[[], None] | None = None,
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
        ('driving', 'Driving', on_driving, False),
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
                 on_cancel: Callable[[], None] | None = None,
                 on_downloads: Callable[[], None] | None = None) -> Panel:
    """Choose a world to drive.

    A drop-down is the wrong control. What tells one circuit from another is
    what it *looks* like and how long it is, and a list of names makes a player
    start each in turn to find out which is which. So the tracks are a band of
    their own pictures, with the length, what carries the road, and the quickest
    lap driven on it under the one selected.

    ``records`` is ``{track key: best Record}``; a track never driven shows
    :data:`NEVER_DRIVEN` rather than nothing, so the row is the same shape
    either way.

    **More** is offered here whether or not there are any, because this is
    where a player comes when they want something to drive: an install with
    nothing yet finds the answer in the same place as one looking for another
    circuit.
    """
    tracks = list(tracks)
    times = dict(records or {})
    chooser = _track_chooser(tracks, chosen)
    caption = Label(text=_caption(tracks, chooser, times), wrap=True,
                    name='caption')
    drive = Button(text='Drive', name='drive', role='primary')
    downloads = Button(text='Get more', name='downloads')
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
                      Row(children=[downloads, Spacer(), cancel, drive],
                          spacing=8, top=8, name='buttons')])])
    answered = False

    def finish(started: bool) -> None:
        # One answer per screen: Drive, Cancel and the panel closing all arrive
        # here, and the first of them is the designer's decision.
        nonlocal answered
        if answered:
            return
        answered = True
        panel.close(started)
        found = _selected(tracks, chooser) if started else None
        if found is not None and on_choose is not None:
            on_choose(found)
        elif not started and on_cancel is not None:
            on_cancel()

    def wanted_more(_widget: Any = None) -> None:
        # Not `finish`: asking for more is not answering the question this
        # screen asked, and a player who closes the downloads should find the
        # chooser where they left it.
        if on_downloads is not None:
            on_downloads()

    drive.on_activate = lambda _widget: finish(True)
    downloads.on_activate = wanted_more
    cancel.on_activate = lambda _widget: finish(False)
    panel.on_close = lambda _closing: finish(False)
    return panel


def driving_screen(chosen: str | None = None,
                   on_choose: Callable[[str], None] | None = None,
                   on_cancel: Callable[[], None] | None = None) -> Panel:
    """How the car is driven.

    Five ways exist and only one of them has ever been reachable: `DEFAULT` is
    the wheel, and `--control` is a command line a player starting the game the
    ordinary way never types. So the work that went into the others -- the lane
    switch that asks for the next lane over and takes the car there, the
    chauffeur that drives until anything is touched -- reads as missing because
    it *is* missing, to everyone who has not read the source.

    Each is offered with the summary it already carries, because a list of five
    names makes a player start five races to find out which is which.
    """
    from glisteel import schemes
    ways = list(schemes.available())
    picker = Select(name='scheme', options=ways,
                    value=chosen if chosen in ways else schemes.DEFAULT)
    caption = Label(text=_how(picker.value), wrap=True, name='how')
    use = Button(text='Use this', name='use', role='primary')
    cancel = Button(text='Cancel', name='cancel')

    def picked(widget: Any) -> None:
        caption.text = _how(widget.value)
    picker.on_change = picked

    panel = Panel(title='Driving', scrim=True, modal=True,
                  preferredColumns=MENU_COLUMNS,
                  children=[Column(spacing=4, children=[
                      picker, caption, Separator(top=6),
                      Row(spacing=2, children=[use, Spacer(), cancel])])])
    answered = False

    def finish(chosen: bool) -> None:
        # One answer per screen, and answering takes the screen away: what
        # comes next is the menu, and this left under it would stand over the
        # race once the menu was resumed.
        nonlocal answered
        if answered:
            return
        answered = True
        panel.close(chosen)
        if chosen and on_choose is not None:
            on_choose(str(picker.value))
        elif not chosen and on_cancel is not None:
            on_cancel()

    use.on_activate = lambda _widget: finish(True)
    cancel.on_activate = lambda _widget: finish(False)
    panel.on_close = lambda _closing: finish(False)
    return panel


def _how(name: Any) -> str:
    """What one way of driving does, in its own words."""
    from glisteel import schemes
    try:
        return str(schemes.named(str(name)).summary)
    except (KeyError, ValueError):               # pragma: no cover - no such way
        return ''


def download_screen(packs: Sequence[Any],
                    on_fetch: Callable[[Any], Any] | None = None,
                    wanted: Callable[[Any], Sequence[Any]] | None = None,
                    on_finished: Callable[[Any], None] | None = None,
                    on_close: Callable[[], None] | None = None,
                    job: Any = None) -> ContentScreen:
    """What is on offer, what it costs, whose it is, and how far a fetch is.

    The engine's :class:`~OpenGLContext.ui.contentscreen.ContentScreen`, as
    this game shows it: ``packs`` is what is missing and ``wanted(pack)`` the
    whole set choosing one pulls in, whose size is the one shown, since a
    track is fetched with the art it shares. ``on_fetch(pack)`` returns the
    :class:`~OpenGLContext.contentpacks.fetch.FetchJob` it started; ``job`` is
    one a previous screen started. Its panel is named ``downloads``.
    """
    screen = ContentScreen(packs, on_fetch=on_fetch, wanted=wanted,
                           on_finished=on_finished, on_close=on_close,
                           title='Downloads', columns=MENU_COLUMNS * 2,
                           job=job)
    screen.panel.name = 'downloads'
    return screen


class Downloads:
    """The download screen across openings, and the download it started.

    A player may close the screen while a track is fetched and open it again;
    the download carries on and the next screen shows it. :meth:`poll` is
    called once a frame whether or not the screen is open. When a download
    arrives, ``on_arrived()`` is called and the offer is refreshed, which is
    what lets the track screen show the new track.

    ``offered()`` returns what is on offer now, ``wanted(pack)`` the set
    choosing one fetches, and ``start(pack)`` the job that fetches it.
    """

    def __init__(self, offered: Callable[[], Sequence[Any]],
                 wanted: Callable[[Any], Sequence[Any]],
                 start: Callable[[Any], Any],
                 on_arrived: Callable[[], None] | None = None,
                 on_close: Callable[[], None] | None = None) -> None:
        self.offered = offered
        self.wanted = wanted
        self.start = start
        self.on_arrived = on_arrived
        self.on_close = on_close
        #: The screen last opened, open or not.
        self.screen: ContentScreen | None = None

    @property
    def open(self) -> bool:
        """Whether the screen is on show."""
        return self.screen is not None and not self.screen.panel.closed

    def show(self) -> Panel:
        """A new screen, over the download under way if there is one."""
        self.screen = download_screen(
            self.offered(), on_fetch=self.start, wanted=self.wanted,
            on_finished=self._finished, on_close=self.on_close,
            job=self.screen.job if self.screen is not None else None)
        return self.screen.panel

    def poll(self) -> bool:
        """Poll the download; whether the screen changed."""
        return self.screen.poll() if self.screen is not None else False

    def _finished(self, job: Any) -> None:
        if job.failed is not None or job.cancelled:
            return
        if self.screen is not None:
            self.screen.offer(self.offered())
        if self.on_arrived is not None:
            self.on_arrived()


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
    is over and the choice of what happens next has to be made. **Making one
    takes it away**, before the handler runs: what happens next is a fresh race
    or another screen, and this one left standing over either is a modal panel
    with nothing behind it to dismiss it.
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
    answered: list[str] = []

    def choose(name: str, handler: Callable[[], None] | None) -> Callable[[], None]:
        def chosen() -> None:
            if answered:
                return
            answered.append(name)
            panel.close(name)
            if handler is not None:
                handler()
        return chosen

    children.extend(_buttons([
        (name, text, choose(name, handler), primary) for name, text, handler,
        primary in (('again', 'Drive it again', on_again, True),
                    ('tracks', 'Another track', on_tracks, False),
                    ('quit', 'Quit', on_quit, False))]))
    panel = Panel(title='', scrim=True, modal=True, closeOnEscape=False,
                  preferredColumns=MENU_COLUMNS,
                  children=[Column(children=children, spacing=4)])
    return panel


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
