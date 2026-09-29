from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import queue

import numpy as np
import pytest

import main
from main import FishingBot
from screen_detector import Layout,Observation,Fish


@pytest.fixture
def bot(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'RUNTIME',tmp_path)
    desktop=SimpleNamespace(commands=queue.Queue(),is_game_active=lambda:True,
                            state={'geometry':[0,0,1920,1080],'screens':1})
    detector=Mock()
    detector.capture.return_value=np.zeros((1080,1920,3),np.uint8)
    detector.observe.return_value=Observation(Layout(193,238,1713,764))
    detector.find_fish_ripples.return_value=[Fish(400,500,18,150)]
    detector.reacquire_fish.side_effect=lambda frame,layout,target: target
    mouse=Mock();sound=Mock()
    args=SimpleNamespace(dry_run=False,no_scroll=False)
    return FishingBot(desktop,detector,mouse,sound,args)


def test_protection_between_select_and_action_prevents_all_input(bot):
    bot.phase='SELECTING'
    bot.detector.observe.return_value=Observation(None,protection=True,blocked='Bot koruması')
    bot.tick()
    bot.mouse.click.assert_not_called()
    bot.mouse.scroll.assert_not_called()
    bot.sound.start_alarm_loop.assert_called_once()
    assert bot.gate.latched


def test_challenge_appearing_during_mouse_motion_aborts_click(bot):
    def click(*args,before_click,**kwargs):
        bot.detector.observe.return_value=Observation(None,protection=True,blocked='Bot koruması')
        before_click()
        pytest.fail('Doğrulama sonrasında tıklama yapılmamalı')
    bot.mouse.click.side_effect=click
    with pytest.raises(InterruptedError):bot.tick()
    assert bot.gate.latched and bot.attempts==0


def test_moving_fish_is_reacquired_and_returns_fresh_click_point(bot):
    target=Fish(400,500,18,150,'yesil')
    moved=Fish(431,516,18,170,'yesil')
    bot.detector.reacquire_fish.side_effect=None
    bot.detector.reacquire_fish.return_value=moved
    corrected=bot.fresh_guard(Layout(193,238,1713,764),target=target)
    assert corrected==(431,516)
    assert bot.target==moved
    bot.detector.reacquire_fish.assert_called_once()


def test_missing_fish_is_transient_and_can_be_reset_without_blacklist(bot):
    target=Fish(400,500,18,150,'yesil')
    bot.target=target
    bot.detector.reacquire_fish.side_effect=None
    bot.detector.reacquire_fish.return_value=None
    with pytest.raises(InterruptedError,match='kara listeye alınmadan'):
        bot.fresh_guard(Layout(193,238,1713,764),target=target)
    bot.reset_target(main.time.monotonic(),blacklist=False)
    assert bot.avoid==[]
    assert bot.target is None


def test_semantic_rejection_still_blacklists_target(bot):
    bot.target=Fish(400,500,18,150,'yesil')
    bot.reset_target(main.time.monotonic())
    assert len(bot.avoid)==1


def test_wrong_fish_never_starts_harvest(bot):
    bot.phase='SELECTING';bot.since=0
    bot.detector.find_yakala_button.return_value=(597,214)
    bot.detector.selected_fish_name.return_value='billur mersin baligi'
    bot.tick()
    bot.mouse.click.assert_not_called()
    assert bot.attempts==0


def test_scrolling_only_after_repeated_empty_frames(bot):
    bot.detector.find_fish_ripples.return_value=[]
    bot.tick();bot.tick()
    bot.mouse.scroll.assert_not_called()
    bot.tick()
    bot.mouse.scroll.assert_called_once()
    assert bot.scroll_before is not None
    assert bot.scrolls==1


def test_no_scrolling_during_harvesting(bot):
    bot.detector.observe.return_value=Observation(Layout(193,238,1713,764),harvesting=True)
    for _ in range(4):bot.tick()
    bot.mouse.click.assert_not_called();bot.mouse.scroll.assert_not_called()
    assert bot.cycles==0


def test_manual_pause_and_background_window_prevent_input(bot):
    bot.desktop.commands.put('pause');bot.tick()
    bot.mouse.click.assert_not_called();bot.mouse.scroll.assert_not_called()
    bot.manual_pause=False
    bot.desktop.is_game_active=lambda:False
    bot.tick()
    bot.mouse.click.assert_not_called();bot.mouse.scroll.assert_not_called()


def test_resume_command_does_not_skip_protection_check(bot):
    bot.manual_pause=True
    bot.desktop.commands.put('resume')
    bot.detector.observe.return_value=Observation(None,protection=True,blocked='Bot koruması')
    bot.tick()
    assert bot.gate.latched
    bot.mouse.click.assert_not_called()


def test_pause_command_is_idempotent(bot):
    for _ in range(2):
        bot.desktop.commands.put('pause');bot.tick()
        assert bot.manual_pause
    bot.mouse.click.assert_not_called()


def test_scroll_at_boundary_reverses_direction_and_rechecks_targets(bot):
    frame=bot.detector.capture.return_value
    layout=bot.detector.observe.return_value.layout
    bot.scroll_before=bot.map_signature(frame,layout)
    bot.tick()
    assert bot.scroll_direction=='up'
    assert bot.scroll_before is None


def test_reported_alacakaranlik_error_is_accepted_only_when_selected(bot):
    assert bot.allowed_fish('alacakaranlik baliggi <i>') is None
    bot.selected_ids=('alacakaranlik',)
    assert bot.allowed_fish('alacakaranlik baliggi <i>').id=='alacakaranlik'
    assert bot.allowed_fish('Gümüş Kadife Balığı') is None


def test_color_mode_accepts_each_known_green_species_but_not_blue(bot):
    bot.selection_mode='color';bot.selected_colors=('yesil',)
    assert bot.allowed_fish('Alacakaranlık İncibalığı').id=='alacakaranlik'
    assert bot.allowed_fish('Kara Havuz Balığı').id=='kara_havuz'
    assert bot.allowed_fish('Elmas Som Balığı','yesil') is None
    assert bot.allowed_fish('gordt','yesil') is None


def test_gray_mode_accepts_ay_sazani_even_with_small_ocr_error(bot):
    bot.selection_mode='color';bot.selected_colors=('beyaz',)
    assert bot.allowed_fish('Ay Sazanı').id=='ay_sazani'
    assert bot.allowed_fish('Ay Sazam','beyaz').id=='ay_sazani'
    assert bot.allowed_fish('Felionlu Çamça').id=='felionlu_camca'
    assert bot.allowed_fish('Sazan','beyaz') is None


def test_unknown_species_color_requires_visible_color_confirmation(bot):
    bot.selection_mode='color';bot.selected_colors=('mor',)
    assert bot.allowed_fish('Kral Yengeç') is None
    assert bot.allowed_fish('Kral Yengeç','yesil') is None
    assert bot.allowed_fish('Kral Yengeç','mor').id=='kral_yengec'


def test_repeated_wrong_species_force_scroll_even_when_more_rings_remain(bot):
    bot.rejections=main.MAX_REJECTIONS_PER_VIEW
    bot.tick()
    bot.mouse.click.assert_not_called()
    bot.mouse.scroll.assert_called_once()


def test_completion_records_only_the_confirmed_species(bot):
    bot.pending_fish_id='alacakaranlik';bot.current_color='yesil'
    bot.detector.observe.return_value.harvesting=True
    bot.tick()
    assert bot.active_fish_id=='alacakaranlik'
    bot.tracker.started_at=main.time.monotonic()-9
    bot.tracker.last_seen_at=main.time.monotonic()-.4
    bot.detector.observe.return_value.harvesting=False
    bot.tick()
    assert bot.timings.summary('alacakaranlik')['count']==0
    bot.tracker.clear_since-=.2
    bot.tick()
    assert bot.cycles==1
    assert bot.timings.summary('alacakaranlik')['count']==1
    assert bot.timings.summary('gumus_kadife')['count']==0


def test_interrupted_collection_does_not_train_durations(bot):
    bot.active_fish_id='alacakaranlik';bot.pending_fish_id='alacakaranlik'
    bot.phase='HARVESTING';bot.tracker.update(True,False,0)
    bot.desktop.commands.put('pause');bot.tick()
    assert bot.active_fish_id is None and bot.tracker.started_at is None
    assert bot.timings.summary('alacakaranlik')['count']==0


def test_mastery_limit_applies_in_both_selection_modes(bot):
    bot.mastery=30;bot.selected_ids=('alacakaranlik','elmas_som')
    assert bot.allowed_fish('Alacakaranlık Balığı')
    assert bot.allowed_fish('Elmas Som Balığı') is None
    bot.selection_mode='color';bot.selected_colors=('yesil','mor')
    assert bot.allowed_fish('Alacakaranlık Balığı')
    assert bot.allowed_fish('Billur Mersin Balığı','mor') is None


def test_transient_action_read_retries_selected_fish_without_another_ring_click(bot):
    bot.phase='SELECTING';bot.since=main.time.monotonic()
    bot.target=Fish(400,500,18,150,'yesil')
    bot.detector.find_yakala_button.return_value=(597,214)
    bot.detector.selected_fish_name.return_value='Gümüş Kadife Balığı'
    bot.mouse.click.side_effect=InterruptedError('OCR okuması yenilenecek')
    with pytest.raises(InterruptedError) as error:bot.tick()
    bot.handle_interruption(error.value)
    assert bot.phase=='SELECTING' and bot.target is not None
    bot.mouse.click.side_effect=None
    bot.tick()
    assert bot.phase=='WAIT_START' and bot.attempts==1
    assert [c.args for c in bot.mouse.click.call_args_list]==[(597,214),(597,214)]
    bot.detector.find_fish_ripples.assert_not_called()


def test_unreadable_selection_waits_for_fresh_name_instead_of_rejecting(bot):
    bot.phase='SELECTING';bot.since=main.time.monotonic()-2
    bot.detector.find_yakala_button.return_value=(597,214)
    bot.detector.selected_fish_name.return_value='...??'
    bot.tick()
    assert bot.phase=='SELECTING' and bot.rejections==0
    bot.mouse.click.assert_not_called()
    bot.detector.selected_fish_name.return_value='Gümüş Kadife Balığı'
    bot.tick()
    assert bot.phase=='WAIT_START' and bot.attempts==1


def test_permanently_unreadable_action_has_bounded_retries(bot):
    bot.phase='SELECTING'
    for _ in range(3):bot.handle_interruption(InterruptedError('okuma başarısız'))
    assert bot.phase=='SEARCH' and bot.avoid==[]


def test_transient_capture_keeps_collection_tracking(bot):
    bot.phase='HARVESTING';bot.active_fish_id='gumus_kadife'
    bot.tracker.update(True,False,10)
    bot.handle_interruption(InterruptedError('ekran yakalanamadı'))
    assert bot.phase=='HARVESTING'
    assert bot.active_fish_id=='gumus_kadife' and bot.tracker.started_at==10


def test_repeated_fresh_checks_follow_last_confirmed_position(bot):
    original=Fish(400,500,18,150,'yesil')
    moved=Fish(421,510,18,150,'yesil')
    bot.target=original
    bot.detector.reacquire_fish.side_effect=[moved,moved]
    layout=Layout(193,238,1713,764)
    bot.fresh_guard(layout,target=original)
    bot.fresh_guard(layout,target=original)
    assert bot.detector.reacquire_fish.call_args_list[1].args[2]==moved


def test_live_ay_sazani_ocr_is_allowed_only_for_that_selected_species(bot):
    bot.selected_ids=('ay_sazani',)
    assert bot.allowed_fish('aysazam@').id=='ay_sazani'
    bot.selected_ids=('felionlu_camca',)
    assert bot.allowed_fish('aysazam@') is None


def test_single_bad_frame_never_discards_a_running_harvest(bot):
    from config import RESUME_FAST_SECONDS, TRANSIENT_BLOCK_FRAMES
    bot.phase = 'HARVESTING'
    bot.tracker.update(True, False, main.time.monotonic())
    started = bot.tracker.started_at
    assert started is not None
    bot.detector.observe.return_value = Observation(
        None, blocked='Avlan haritası görünmüyor veya ekran değişti.')
    for _ in range(TRANSIENT_BLOCK_FRAMES - 1):
        bot.tick()
    assert not bot.gate.latched
    assert bot.phase == 'HARVESTING'
    assert bot.tracker.started_at == started
    bot.tick()
    assert bot.gate.latched
    assert bot.phase == 'SEARCH'
    assert bot.tracker.started_at is None
    assert bot.gate.seconds == RESUME_FAST_SECONDS


def test_repeated_block_only_discards_state_on_the_first_latch(bot):
    from state import HarvestTracker
    bot.phase = 'HARVESTING'
    bot.tracker.update(True, False, main.time.monotonic())
    bot.block('harita kayboldu')
    assert bot.phase == 'SEARCH'
    assert bot.tracker.started_at is None
    bot.phase = 'SELECTING'
    bot.tracker = HarvestTracker()
    bot.tracker.update(True, False, main.time.monotonic())
    bot.block('harita kayboldu')
    assert bot.phase == 'SELECTING'
    assert bot.tracker.started_at is not None


def game_warning():
    return Observation(Layout(193,238,1713,764),
                       blocked='Oyun uyarısı: nesne artık mevcut değil',
                       close_button=(953,499))


def arm_warning_close(bot):
    """Kapat düğmesi algılanmış bir oyun uyarısı karesi hazırla."""
    bot.detector.observe.return_value = game_warning()
    bot.detector.find_close_button.return_value = (953,499)
    bot.detector.check_bot_protection.return_value = (False, None)


def test_game_warning_dialog_is_closed_before_any_alarm(bot):
    arm_warning_close(bot)
    confirmed = {}
    def click(*args, before_click, **kwargs):
        confirmed['point'] = before_click()
    bot.mouse.click.side_effect = click
    bot.tick()
    bot.mouse.click.assert_called_once()
    assert confirmed['point'] == bot.pixel_to_desktop((953,499),
                                                      bot.detector.capture.return_value)
    assert not bot.gate.latched
    bot.sound.start_alarm_loop.assert_not_called()
    assert bot.blocked_frames == 1 and bot.warning_closes


def test_warning_close_is_rate_limited_without_blocking_the_screen(bot):
    arm_warning_close(bot)
    bot.warning_close_at = main.time.monotonic()
    bot.tick()
    bot.mouse.click.assert_not_called()
    assert not bot.gate.latched
    assert bot.blocked_frames == 1


def test_unclosable_warning_gives_up_with_an_alarm(bot):
    arm_warning_close(bot)
    bot.warning_closes = [main.time.monotonic()-1 for _ in range(main.WARNING_CLOSE_LIMIT)]
    bot.tick()
    bot.mouse.click.assert_not_called()
    assert bot.gate.latched
    bot.sound.start_alarm_loop.assert_called_once()


def test_dry_run_never_clicks_a_warning_button(bot):
    bot.args.dry_run = True
    arm_warning_close(bot)
    for _ in range(main.TRANSIENT_BLOCK_FRAMES):
        bot.tick()
    bot.mouse.click.assert_not_called()
    assert bot.gate.latched


def test_blocked_screen_without_a_locatable_button_never_clicks(bot):
    # Ustalık uyarısı gibi kapatılamayacak ekranlar körlemesine tıklamaz.
    bot.detector.observe.return_value = Observation(
        Layout(193,238,1713,764),
        blocked='Yeterli ustalığınız yok. Panelde ustalık sınırını veya hedefleri değiştirin.')
    for _ in range(main.TRANSIENT_BLOCK_FRAMES):
        bot.tick()
    bot.mouse.click.assert_not_called()
    assert bot.gate.latched


def test_failed_harvest_avoids_the_ring_it_started_from(bot):
    import math
    bot.selected_ids = ('ay_sazani',)
    ring = Fish(224,349,18,150,'beyaz')
    # Tıklama koruması reacquire ile hedefi başka bir halkaya kaydırabilir;
    # oyun o noktaya basar, günlükteki konum ise ilk halkanınki kalır.
    bot.detector.find_fish_ripples.return_value = [ring]
    bot.detector.find_yakala_button.return_value = (597,214)
    bot.detector.selected_fish_name.return_value = 'Ay Sazanı'
    bot.detector.selected_fish_color.return_value = 'beyaz'
    bot.tick()
    assert bot.phase == 'SELECTING'
    bot.target = Fish(266,377,18,150,'beyaz')
    bot.tick()
    assert bot.phase == 'WAIT_START'
    bot.since = 0
    bot.tick()                      # toplama başlamadı: hedef elenmeli
    assert bot.avoid
    assert any(math.hypot(x-224, y-349) < 6 for x, y, _t in bot.avoid), bot.avoid
    clicks = bot.mouse.click.call_count
    bot.tick()                      # aynı halka hemen yeniden seçilememeli
    assert bot.mouse.click.call_count == clicks, 'başlamayan hedef kara listede değil'
