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
