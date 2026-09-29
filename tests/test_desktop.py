from types import SimpleNamespace
import json
import os

import pytest

import desktop
from desktop import Desktop, game_window_id, is_game_title

GAME = {'id': '{game}', 'title': 'Ejderhalar Mirası - Chromium'}
WIKI = {'id': '{wiki}',
        'title': 'Ahşap Ok - ücretsiz çevrimiçi rol yapma oyunu (RPG) '
                 'Ejderhalar Mirası içindeki eşya hakkında bilgi - Chromium'}


def test_only_the_game_window_carries_the_game_title():
    assert is_game_title(GAME['title'])
    assert is_game_title('  ejderhalar mirası - chromium')
    assert not is_game_title(WIKI['title'])
    assert not is_game_title('')
    assert not is_game_title(None)


def test_focus_ignores_the_item_wiki_window():
    assert game_window_id([WIKI, GAME]) == '{game}'
    assert game_window_id([GAME, WIKI]) == '{game}'
    with pytest.raises(RuntimeError):
        game_window_id([GAME, dict(GAME, id='{other}')])
    with pytest.raises(RuntimeError):
        game_window_id([])
    # A single window without a known title keeps the previous behaviour.
    assert game_window_id([WIKI]) == '{wiki}'


def active(title, app='chromium', window='{game}'):
    return Desktop.is_game_active(SimpleNamespace(state={
        'title': title, 'app': app, 'window': window, 'candidates': [GAME, WIKI]}))


def test_game_is_active_only_while_the_game_window_has_focus():
    assert active(GAME['title'])
    assert not active(WIKI['title'], window='{wiki}')
    assert not active(GAME['title'], app='konsole')


def test_loose_name_check_survives_a_renamed_game_tab():
    state = {'title': 'Avlan Ekranı Ejderhalar Mirası', 'app': 'chromium',
             'window': '{renamed}', 'candidates': []}
    assert Desktop.is_game_active(SimpleNamespace(state=state))
    # ...but never while the real game window is reported next to it.
    state['candidates'] = [GAME]
    assert not Desktop.is_game_active(SimpleNamespace(state=state))


class _FakeHelper:
    """Desktop startup without D-Bus: every step is observable."""

    def __init__(self, waits, fails=0):
        self.plugin = 'dwar-fishing-test'
        self.waits = list(waits)
        self.fails = fails
        self.loads = 0
        self.unloads = []
        self.pruned = 0
        self.remembered = 0
        self.updated = self

    def wait(self, timeout):
        return self.waits.pop(0) if self.waits else False

    def _prune_stale_scripts(self):
        self.pruned += 1

    def _remember_script(self):
        self.remembered += 1

    def _unload_quiet(self, name):
        self.unloads.append(name)

    def _load(self, report, name):
        self.loads += 1
        if self.loads <= self.fails:
            raise RuntimeError('KWin yardımcısı yüklenemedi (JS hatası olabilir)')


def test_a_silent_helper_is_reloaded_until_a_report_arrives():
    helper = _FakeHelper(waits=[False, False, True])
    Desktop._start_helper(helper, 'report();')
    assert helper.loads == 3
    assert helper.unloads == ['dwar-fishing-test'] * 2
    assert helper.remembered == 3
    assert helper.pruned == 1


def test_startup_gives_up_only_after_the_last_attempt():
    helper = _FakeHelper(waits=[False] * 6)
    with pytest.raises(RuntimeError, match='KWin'):
        Desktop._start_helper(helper, 'report();')
    assert helper.loads == 3


def test_a_failing_load_is_retried_and_still_recovers():
    helper = _FakeHelper(waits=[True], fails=1)
    Desktop._start_helper(helper, 'report();')
    assert helper.loads == 2
    assert helper.unloads == ['dwar-fishing-test']


def test_a_started_helper_is_recorded_for_the_next_start(monkeypatch, tmp_path):
    registry = tmp_path / 'kwin_scripts.json'
    monkeypatch.setattr(desktop, 'SCRIPT_REGISTRY', registry)
    Desktop._remember_script(_FakeHelper(waits=[True]))
    assert json.loads(registry.read_text()) == [os.getpid()]


def test_only_helpers_of_dead_processes_are_unloaded(monkeypatch, tmp_path):
    registry = tmp_path / 'kwin_scripts.json'
    registry.write_text(json.dumps([2222, os.getpid()]))
    monkeypatch.setattr(desktop, 'SCRIPT_REGISTRY', registry)
    real_kill = os.kill

    def kill(pid, sig):
        if pid == 2222:
            raise ProcessLookupError(pid)
        return real_kill(pid, sig)

    monkeypatch.setattr(os, 'kill', kill)
    helper = _FakeHelper(waits=[True])
    Desktop._prune_stale_scripts(helper)
    assert helper.unloads == ['dwar-fishing-2222']


def test_a_missing_registry_is_not_an_error(monkeypatch, tmp_path):
    helper = _FakeHelper(waits=[True])
    monkeypatch.setattr(desktop, 'SCRIPT_REGISTRY', tmp_path / 'gone.json')
    Desktop._prune_stale_scripts(helper)
    assert helper.unloads == []
