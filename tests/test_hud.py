"""The four numbers a driver acts on, and where they go."""


from glisteel.hud import FAST_KPH, HOME, RaceHUD
from glisteel.run import COUNTDOWN, ENDED, FINISHED, RACING
from glisteel.session import Readings


class _Lap:
    def __init__(self, seconds):
        self.seconds = seconds

    def clock(self):
        return '1:%06.3f' % self.seconds


class _Timing:
    def __init__(self, laps=(), current=0.0, last=None, best=None):
        self.laps = list(laps)
        self.current = current
        self.last = last
        self.best = best


class TestTheReadouts:
    def test_the_speed_is_shown_whole(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=87.6))
        assert str(hud.speed.value).strip() == '88'

    def test_a_stopped_car_reads_zero_rather_than_a_minus(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=-0.4))
        assert str(hud.speed.value).strip() == '0'

    def test_going_fast_is_flagged(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=FAST_KPH + 1))
        assert bool(hud.speed.critical)
        hud.show(Readings(speed_kph=FAST_KPH - 1))
        assert not bool(hud.speed.critical)

    def test_the_lap_clock_counts_up(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, timing=_Timing(current=65.25)))
        assert '1:05.250' in str(hud.lap.value)

    def test_the_lap_number_is_the_one_being_driven(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, timing=_Timing(laps=[_Lap(1.0), _Lap(2.0)])))
        assert str(hud.lap.value).startswith('3')

    def test_before_a_lap_the_times_are_blank_rather_than_zero(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, timing=_Timing()))
        assert '--' in str(hud.best.value) and '--' in str(hud.last.value)

    def test_the_best_and_last_appear_once_set(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0,
                 timing=_Timing(last=_Lap(21.5), best=_Lap(20.25))))
        assert '21.500' in str(hud.last.value)
        assert '20.250' in str(hud.best.value)

    def test_off_the_track_says_so_and_goes_quiet_again(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, off=True))
        assert str(hud.warning.value) == 'OFF TRACK'
        hud.show(Readings(speed_kph=0.0, off=False))
        assert str(hud.warning.value) == ''


class TestWhereTheyGo:
    def test_the_clocks_are_one_block_rather_than_a_pile(self) -> None:
        """Three readouts anchored to the same corner draw on top of one
        another; a group takes the corner and stacks them."""
        hud = RaceHUD()
        assert str(hud.times.anchor) == 'top-left'
        assert list(hud.times.children) == [hud.lap, hud.last, hud.best]

    def test_the_speed_is_out_of_the_way_of_the_clocks(self) -> None:
        hud = RaceHUD()
        assert str(hud.speed.anchor) == 'bottom-right'

    def test_the_warning_is_where_the_eye_is(self) -> None:
        assert str(RaceHUD().warning.anchor) == 'center'

    def test_it_lays_out_for_a_viewport(self) -> None:
        hud = _laid_out()
        assert hud.rect.width == 1280
        assert hud.times.rect.y >= 0
        assert hud.speed.rect.right <= 1280

    def test_the_three_clocks_end_up_on_three_lines(self) -> None:
        """The fault this group exists to fix: one corner, three readouts, all
        drawn at the same place."""
        hud = _laid_out()
        tops = sorted(widget.rect.y for widget in (hud.lap, hud.last, hud.best))
        assert len(set(tops)) == 3
        heights = [widget.rect.height for widget in (hud.lap, hud.last, hud.best)]
        assert tops[1] - tops[0] >= min(heights)
        assert tops[2] - tops[1] >= min(heights)

    def test_the_speed_does_not_land_on_the_clocks(self) -> None:
        """The HUD's y runs up the screen, so the bottom-right readout sits at
        a lower y than the top-left block."""
        hud = _laid_out()
        assert hud.speed.rect.y < hud.best.rect.y


def _laid_out(viewport=(1280, 720)):
    from OpenGLContext.ui.metrics import FontMetrics
    hud = RaceHUD()
    hud.show(Readings(speed_kph=120.0, timing=_Timing(current=12.0)))
    hud.layout(viewport, FontMetrics(char_width=9, char_height=16))
    return hud


class TestTheStartRig:
    """Five lamps across the top, and only while there is a start to watch."""

    def test_the_lamps_are_up_on_the_grid(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=COUNTDOWN, lit=2, lights=5))
        assert bool(hud.lights.visible)

    def test_and_show_how_much_of_the_rig_is_burning(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=COUNTDOWN, lit=3, lights=5))
        assert (hud.lights.lit, hud.lights.count) == (3, 5)

    def test_they_go_away_once_the_race_is_on(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=COUNTDOWN, lit=5, lights=5))
        hud.show(Readings(speed_kph=40.0, phase=RACING, lit=0, lights=5))
        assert not bool(hud.lights.visible)

    def test_a_race_with_no_rig_shows_none(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=COUNTDOWN, lit=0, lights=0))
        assert not bool(hud.lights.visible)


class TestTheMiddleOfTheScreen:
    def test_nothing_is_said_while_the_road_is_under_the_car(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=40.0, phase=RACING))
        assert str(hud.warning.value) == ''

    def test_leaving_the_road_is_said(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=40.0, phase=RACING, off=True))
        assert str(hud.warning.value) == 'OFF TRACK'

    def test_a_run_that_is_over_displaces_the_warning(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=ENDED, off=True, ended='mired off the road'))
        assert str(hud.warning.value) == 'MIRED OFF THE ROAD'

    def test_finishing_says_so_with_the_time(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=FINISHED,
                 timing=_Timing(best=_Lap(23.5))))
        assert str(hud.warning.value) == '%s   1:23.500' % HOME

    def test_finishing_without_a_time_still_says_so(self) -> None:
        """A race whose laps were all abandoned still ends."""
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=FINISHED, timing=_Timing()))
        assert str(hud.warning.value) == HOME

    def test_and_it_outranks_being_off_the_road(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=FINISHED, off=True,
                 timing=_Timing(best=_Lap(23.5))))
        assert str(hud.warning.value).startswith(HOME)

    def test_a_finish_is_not_a_warning(self) -> None:
        """Red is for something gone wrong; winning is not that."""
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=FINISHED, timing=_Timing(best=_Lap(23.5))))
        assert not bool(hud.warning.critical)

    def test_but_a_run_that_ended_badly_is(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=0.0, phase=ENDED, ended='wrecked'))
        assert bool(hud.warning.critical)
