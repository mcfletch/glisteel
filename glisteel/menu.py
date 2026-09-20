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
    What is on offer, what it costs, whose it is, and how far a fetch has got.
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

from OpenGLContext.ui.gallery import Carousel
from OpenGLContext.ui.layout import Column, Row
from OpenGLContext.ui.panel import Panel
from OpenGLContext.ui.widgets import (
    Button,
    Label,
    ProgressBar,
    Select,
    Separator,
    Spacer,
)

__all__ = ['ALL_HERE', 'BEST', 'FINISHED', 'GAME_TITLE', 'NEVER_DRIVEN',
           'NO_TRACKS', 'STOPPED', 'download_screen', 'driving_screen',
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
ALL_HERE = 'Everything is downloaded'

#: What it says about a download the player stopped. Distinct from a failure:
#: nothing went wrong, and telling somebody their own decision was an error is
#: a poor way to answer it.
STOPPED = 'Stopped'

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

    def chose(_widget: Any = None) -> None:
        if on_choose is not None:
            on_choose(str(picker.value))
    use.on_activate = chose
    if on_cancel is not None:
        cancel.on_activate = lambda _widget=None: on_cancel()

    return Panel(title='Driving', scrim=True, modal=True,
                 preferredColumns=MENU_COLUMNS,
                 children=[Column(spacing=4, children=[
                     picker, caption, Separator(top=6),
                     Row(spacing=2, children=[use, Spacer(), cancel])])])


def _how(name: Any) -> str:
    """What one way of driving does, in its own words."""
    from glisteel import schemes
    try:
        return str(schemes.named(str(name)).summary)
    except (KeyError, ValueError):               # pragma: no cover - no such way
        return ''


def download_screen(packs: Sequence[Any],
                    job: Any = None,
                    on_fetch: Callable[[Any], None] | None = None,
                    on_cancel: Callable[[], None] | None = None,
                    wanted: Callable[[Any], Sequence[Any]] | None = None) -> Panel:
    """What is on offer, what it costs, and whose it is.

    A track is 22 MB and the set is 90 MB, so none of it ships in the wheel.
    This screen is where a player agrees to a download: the size before it
    starts, the terms the content carries, and -- since a track is incomplete
    without the art it shares -- the size of *everything* the choice pulls in
    rather than of the one pack named.

    ``packs`` is what is missing and ``wanted(pack)`` is the whole set choosing
    one pulls in -- the size shown is that set's, since a track's art is
    fetched with it and a player shown the track's own size alone would be told
    the wrong number. Without it a pack answers for itself. An empty ``packs``
    is :data:`ALL_HERE` rather than an empty screen. ``job`` is a
    :class:`~OpenGLContext.contentpacks.fetch.FetchJob` under way, and the
    screen is rebuilt from it as it is polled.
    """
    packs = list(packs)
    chooser = Select(name='offered', options=[one.key for one in packs],
                     value=packs[0].key if packs else None)
    caption = Label(text=_offer(packs[0], wanted) if packs else ALL_HERE,
                    wrap=True, name='offer')
    # A bar and the words: the bar is how far, the words are which pack and
    # what went wrong. Neither says the other's half.
    progress = ProgressBar(fraction=_fraction(job), text=_progress(job),
                           name='progress')
    fetch = Button(text='Download', name='fetch', role='primary')
    cancel = Button(text='Close', name='cancel')
    fetch.enabled = bool(packs) and not _running(job)

    def picked(widget: Any) -> None:
        caption.text = _offer(_pack_named(packs, widget.value), wanted)
    chooser.on_change = picked

    def start(_widget: Any = None) -> None:
        chosen = _pack_named(packs, chooser.value)
        if chosen is not None and on_fetch is not None:
            on_fetch(chosen)
    fetch.on_activate = start
    if on_cancel is not None:
        cancel.on_activate = lambda _widget=None: on_cancel()

    return Panel(title='Downloads', scrim=True, modal=True,
                 preferredColumns=MENU_COLUMNS * 2,
                 children=[Column(spacing=4, children=[
                     chooser, caption, progress, Separator(top=6),
                     Row(spacing=2, children=[fetch, Spacer(), cancel])])])


def _pack_named(packs: Sequence[Any], key: Any) -> Any:
    for one in packs:
        if one.key == key:
            return one
    return packs[0] if packs else None


def _offer(pack: Any, wanted: Callable[[Any], Sequence[Any]] | None = None
           ) -> str:
    """One choice as a player reads it before agreeing to fetch it.

    The size is the whole set the choice pulls in, and anything else in that
    set is named: a download screen that says 22 MB and fetches 54 has not
    asked the question it appears to be asking.
    """
    if pack is None:
        return ALL_HERE
    whole = list(wanted(pack)) if wanted is not None else [pack]
    said = ['%s — %s' % (pack.title, _size(whole))]
    if pack.notes:
        said.append(pack.notes)
    for one in whole:
        if one.key != pack.key:
            said.append('with %s — %s' % (one.title, one.human_size()))
    said.append(pack.copyright)
    return '\n'.join(said)


def _size(packs: Sequence[Any]) -> str:
    """What a set of packs costs, as the user reads it."""
    return '%d MB' % (round(sum(one.approximate_bytes for one in packs) / 1e6),)


def _fraction(job: Any) -> float:
    """How far the bar is filled. Nothing where there is no job to ask."""
    if job is None:
        return 0.0
    return float(getattr(job, 'fraction', 0.0))


def _running(job: Any) -> bool:
    return job is not None and not getattr(job, 'finished', False)


def _progress(job: Any) -> str:
    """How far a download has got, or why it stopped.

    A job that failed and a job the player stopped are different things and are
    said differently; a job that finished says nothing, because the screen it
    came back to already shows what arrived.
    """
    if job is None:
        return ''
    if getattr(job, 'cancelled', False):
        return STOPPED
    failed = getattr(job, 'failed', None)
    if failed is not None:
        return 'Could not download: %s' % (failed,)
    if getattr(job, 'finished', False):
        return ''
    return '%s — %d%%' % (getattr(job, 'state', '') or '',
                          round(float(getattr(job, 'fraction', 0.0)) * 100))


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
