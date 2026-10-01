import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import gui


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(tmp_path,app):
    window=gui.ControlWindow(tmp_path,status_reader=lambda:{'running':False})
    window.energy_cycle.setChecked(False)
    window.timer.stop();window.minimize.setChecked(False)
    yield window
    window.hide();window.deleteLater();app.processEvents()


def test_color_and_name_modes_keep_independent_choices(panel):
    panel.color_checks['mavi'].setChecked(True)
    assert panel.worker_command()[1:]==['--colors','yesil','mavi']
    panel.by_name.setChecked(True);panel.clear_selection()
    row=next(i for i,f in enumerate(panel.fishes) if f.id=='alacakaranlik')
    panel.table.item(row,0).setCheckState(Qt.CheckState.Checked)
    assert panel.worker_command()[1:]==['--fish','alacakaranlik']
    panel.by_color.setChecked(True)
    assert panel.worker_command()[1:]==['--colors','yesil','mavi']
    panel.by_name.setChecked(True)
    assert panel.worker_command()[1:]==['--fish','alacakaranlik']


def test_empty_selection_does_not_launch_and_limits_are_applied(panel):
    panel.color_checks['yesil'].setChecked(False)
    with pytest.raises(ValueError):panel.worker_command()
    panel.color_checks['mor'].setChecked(True)
    panel.cycle_limit.setValue(3);panel.minute_limit.setValue(2);panel.auto_scroll.setChecked(False)
    assert panel.worker_command()[1:]==['--colors','mor','--no-scroll','--max-cycles','3','--max-seconds','120']


def test_splinter_checkbox_only_emits_a_disable_flag(panel):
    panel.color_checks['yesil'].setChecked(True)
    # Kurtarma varsayılan açık: işaretliyken hiç bayrak gerekmez.
    panel.auto_splinter.setChecked(True)
    assert panel.worker_command()[1:]==['--colors','yesil']
    panel.auto_splinter.setChecked(False)
    assert panel.worker_command()[1:]==['--colors','yesil','--no-auto-splinter']


def test_search_accepts_alias_without_changing_selection(panel):
    before=panel.selection()
    panel.filter_rows('incibaligi')
    visible=[fish.id for i,fish in enumerate(panel.fishes) if not panel.table.isRowHidden(i)]
    assert visible==['alacakaranlik'] and panel.selection()==before


def test_close_during_startup_stops_worker_before_status_file_exists(panel,monkeypatch):
    process=SimpleNamespace(pid=876543,poll=lambda:None,terminate=Mock())
    monkeypatch.setattr(gui.subprocess,'Popen',Mock(return_value=process))
    panel.start_worker();panel.refresh()
    assert not panel.start_button.isEnabled() and panel.stop_button.isEnabled()
    event=Mock();panel.closeEvent(event)
    process.terminate.assert_called_once();event.accept.assert_called_once()


def test_applying_selection_waits_for_old_process_to_exit(panel):
    state={'running':False,'process_alive':True}
    panel.status_reader=lambda:state
    panel.launch=Mock()
    panel.start_worker();panel.refresh()
    panel.launch.assert_not_called()
    state['process_alive']=False
    panel.refresh()
    panel.launch.assert_called_once()


def test_stop_cancels_queued_restart(panel):
    panel.pending_launch=['run.sh','--colors','mor']
    panel.stop_worker()
    assert panel.pending_launch is None


def test_mastery_limit_is_optional_and_zero_is_valid(panel):
    assert '--mastery' not in panel.worker_command()
    panel.mastery.setValue(0)
    assert panel.worker_command()[-2:]==['--mastery','0']
    panel.mastery.setValue(120)
    assert panel.worker_command()[-2:]==['--mastery','120']


def test_console_log_is_rotated_before_each_launch(panel):
    path = panel.runtime / 'console.log'
    path.write_bytes(b'y' * (2 * 1024 * 1024 + 1))
    out = panel.console_output()
    out.close()
    assert (panel.runtime / 'console.log.1').exists()
    assert path.stat().st_size == 0


def test_all_creatures_dim_individual_choices(panel):
    """'Tüm yaratıklar' işaretliyken tek tek kutular etkisiz görünür; kullanıcı
    yalnızca Yaslı Phadd seçtiğini sanıp botun tümüne dalmasını anlamaz."""
    panel.mode_hunt.setChecked(True)
    panel.auto_battle_cb.setChecked(False);panel.mount_cb.setChecked(False);panel.provoke_cb.setChecked(False)
    panel.hunt_all.setChecked(True)
    assert not panel.hunt_checks['krogan'].isEnabled()
    assert panel.worker_command()[1:3]==['--hunt','--creatures']
    panel.hunt_all.setChecked(False)
    assert panel.hunt_checks['krogan'].isEnabled()
    panel.hunt_checks['maharetli_fitsilya'].setChecked(False)
    assert panel.worker_command()[1:]==['--hunt','--creatures','krogan']


def test_hunt_mode_builds_the_creature_command(panel):
    panel.mode_hunt.setChecked(True)
    panel.auto_battle_cb.setChecked(False);panel.mount_cb.setChecked(False);panel.provoke_cb.setChecked(False)
    panel.hunt_checks['maharetli_fitsilya'].setChecked(False)
    assert panel.worker_command()[1:]==['--hunt','--creatures','krogan']
    panel.hunt_all.setChecked(True)
    assert panel.worker_command()[1:]==['--hunt','--creatures','all']
    panel.hunt_min.setValue(2);panel.hunt_max.setValue(6)
    assert panel.worker_command()[1:]==['--hunt','--creatures','all','--min-level','2','--max-level','6']


def test_custom_creatures_can_be_added_and_removed(panel):
    panel.mode_hunt.setChecked(True)
    panel.auto_battle_cb.setChecked(False);panel.mount_cb.setChecked(False);panel.provoke_cb.setChecked(False)
    panel.hunt_input.setText('Ateş Kurbisi')
    panel.hunt_add_creature()
    key='ates_kurbisi'
    assert key in panel.hunt_checks and panel.hunt_checks[key].isChecked()
    panel.hunt_checks['maharetli_fitsilya'].setChecked(False)
    assert panel.worker_command()[1:]==['--hunt','--creatures','krogan','Ateş Kurbisi']
    panel.hunt_input.setText('Ateş Kurbisi')
    panel.hunt_remove_creature()
    assert key not in panel.hunt_checks
    assert panel.worker_command()[1:]==['--hunt','--creatures','krogan']


def test_fight_options_build_during_fight_flags(panel):
    panel.mode_hunt.setChecked(True)
    panel.hunt_all.setChecked(True)
    panel.auto_battle_cb.setChecked(True);panel.mount_cb.setChecked(True)
    panel.provoke_cb.setChecked(True)
    for spin,value in zip(panel.provoke_spins,(3,2,0,0,0)):spin.setValue(value)
    assert panel.worker_command()[1:]==['--hunt','--creatures','all','--auto-battle','--mount',
                                        '--provoke','--provoke-counts','3,2,0,0,0']
    # Provokasyon işaretli ama tüm adetler 0: başlatma reddedilir.
    for spin in panel.provoke_spins:spin.setValue(0)
    with pytest.raises(ValueError):panel.worker_command()


def test_hunt_mode_requires_a_creature(panel):
    panel.mode_hunt.setChecked(True)
    panel.auto_battle_cb.setChecked(False);panel.mount_cb.setChecked(False);panel.provoke_cb.setChecked(False)
    panel.hunt_all.setChecked(False)
    for checkbox in panel.hunt_checks.values():checkbox.setChecked(False)
    with pytest.raises(ValueError):panel.worker_command()


def test_hunt_mode_shares_limits_and_restores_fishing_controls(panel):
    panel.mode_hunt.setChecked(True)
    panel.auto_battle_cb.setChecked(False);panel.mount_cb.setChecked(False);panel.provoke_cb.setChecked(False)
    # Av modunda balıkçılık sayfası gösterilmez; ortak sınırlar av sayfasına taşınır.
    assert panel.stack.currentWidget() is panel.hunt_page
    assert not panel.table.isVisible()
    assert panel.hunt_page.isAncestorOf(panel.general_card)
    panel.cycle_limit.setValue(5);panel.auto_scroll.setChecked(False)
    assert panel.worker_command()[1:]==['--hunt','--creatures','maharetli_fitsilya','krogan',
                                        '--no-scroll','--max-cycles','5']
    panel.mode_fishing.setChecked(True)
    assert panel.stack.currentWidget() is panel.fishing_page
    assert panel.fishing_page.isAncestorOf(panel.general_card)
    assert panel.worker_command()[1:]==['--colors','yesil','--no-scroll','--max-cycles','5']


def test_hunt_preferences_survive_a_restart(tmp_path,app):
    window=gui.ControlWindow(tmp_path,status_reader=lambda:{'running':False})
    window.timer.stop();window.minimize.setChecked(False)
    window.mode_hunt.setChecked(True);window.hunt_checks['krogan'].setChecked(False)
    window.hunt_input.setText('Ateş Kurbisi');window.hunt_add_creature()
    window.hunt_min.setValue(3)
    window.auto_battle_cb.setChecked(False);window.mount_cb.setChecked(True)
    window.provoke_cb.setChecked(True)
    for spin,value in zip(window.provoke_spins,(2,0,1,0,0)):spin.setValue(value)
    window.save_preferences()
    window.hide();window.deleteLater();app.processEvents()
    reopened=gui.ControlWindow(tmp_path,status_reader=lambda:{'running':False})
    reopened.timer.stop()
    assert reopened.mode_hunt.isChecked()
    assert not reopened.hunt_checks['krogan'].isChecked()
    assert reopened.hunt_checks['maharetli_fitsilya'].isChecked()
    assert reopened.hunt_checks['ates_kurbisi'].isChecked() and reopened.hunt_checks['ates_kurbisi'].text()=='Ateş Kurbisi'
    assert reopened.hunt_min.value()==3
    assert not reopened.auto_battle_cb.isChecked() and reopened.mount_cb.isChecked()
    assert reopened.provoke_cb.isChecked()
    assert [spin.value() for spin in reopened.provoke_spins]==[2,0,1,0,0]
    reopened.hide();reopened.deleteLater();app.processEvents()


def test_panel_opens_on_mode_chooser_and_cards_pick_the_page(panel):
    """Uygulama açılınca önce Meslek / Avlan seçimi gelir; kart seçilen modun sayfasını açar."""
    assert panel.stack.currentWidget() is panel.launcher_page
    assert not panel.back_button.isVisibleTo(panel)
    panel.card_hunt.click()
    assert panel.mode_hunt.isChecked() and panel.stack.currentWidget() is panel.hunt_page
    assert panel.back_button.isVisibleTo(panel)
    panel.show_launcher()
    assert panel.stack.currentWidget() is panel.launcher_page
    panel.card_fishing.click()
    assert panel.mode_fishing.isChecked() and panel.stack.currentWidget() is panel.fishing_page


def test_panel_skips_chooser_when_a_hunt_is_already_running(tmp_path,app):
    window=gui.ControlWindow(tmp_path,status_reader=lambda:{'running':True,'mode':'hunt','pid':1})
    window.timer.stop()
    assert window.stack.currentWidget() is window.hunt_page
    window.hide();window.deleteLater();app.processEvents()


def test_provoke_slots_follow_the_checkbox_and_total_is_shown(panel):
    panel.mode_hunt.setChecked(True)
    panel.provoke_cb.setChecked(False)
    assert not panel.provoke_row.isEnabled()
    panel.provoke_cb.setChecked(True)
    assert panel.provoke_row.isEnabled()
    for spin,value in zip(panel.provoke_spins,(3,4,0,2,0)):spin.setValue(value)
    assert '9' in panel.provoke_total.text()
    assert panel.provoke_spins[0].maximum()==gui.HUNT_SUMMON_MAX_PER_SLOT


def test_creatures_learned_by_the_bot_appear_unchecked_in_the_list(panel):
    import hunt_catalog
    path=panel.runtime/'creatures.json'
    assert hunt_catalog.remember_seen(path,'yasli phadd ayisi')
    assert not hunt_catalog.remember_seen(path,'Yasli Phadd Ayisi')   # tekrar yazılmaz
    assert not hunt_catalog.remember_seen(path,'Krogan')               # katalog türü yazılmaz
    panel.sync_seen_creatures()
    box=panel.hunt_checks['yasli_phadd_ayisi']
    assert not box.isChecked() and box.text()=='Yasli Phadd Ayisi'
    panel.mode_hunt.setChecked(True)
    panel.auto_battle_cb.setChecked(False);panel.mount_cb.setChecked(False);panel.provoke_cb.setChecked(False)
    box.setChecked(True)
    assert panel.worker_command()[-1]=='Yasli Phadd Ayisi'
    panel.hunt_input.setText('Yasli Phadd Ayisi');panel.hunt_remove_creature()
    assert 'yasli_phadd_ayisi' not in panel.hunt_checks
    assert hunt_catalog.load_seen(path)==[]
