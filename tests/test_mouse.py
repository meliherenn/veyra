from types import SimpleNamespace
import math
import threading
from unittest.mock import Mock
import pytest

import mouse_control
from mouse_control import MouseController


@pytest.fixture
def mouse(monkeypatch):
    monkeypatch.setattr(mouse_control.shutil,'which',lambda name:'/usr/bin/'+name)
    monkeypatch.setattr(mouse_control.os.path,'exists',lambda path:True)
    desktop=SimpleNamespace(state={'geometry':[0,0,1920,1080]},
                            updated=threading.Event(),is_game_active=lambda:True)
    cursor=[300,400]
    desktop.cursor=lambda:tuple(cursor)
    mouse=MouseController(desktop)
    mouse._run=Mock()
    return mouse,cursor


def test_motion_uses_measured_position_when_acceleration_changes(mouse):
    m,cursor=mouse
    def run(*args):
        assert args[0]=='mousemove'
        dx,dy=int(args[2]),int(args[4])
        gain=1.4 if math.hypot(dx,dy)>20 else .8
        cursor[0]+=round(dx*gain);cursor[1]+=round(dy*gain)
        m.desktop.updated.set()
    m._run.side_effect=run
    m.move_to(750,650)
    assert math.dist(cursor,(750,650))<=2.5


def test_moved_cursor_during_final_screen_check_never_clicks(mouse):
    m,cursor=mouse
    m.move_to=Mock(side_effect=lambda x,y:cursor.__setitem__(slice(None),[x,y]))
    def user_moved():cursor[:]=[900,600]
    with pytest.raises(InterruptedError):m.click(400,500,before_click=user_moved)
    m._run.assert_not_called()


def test_pointer_in_corner_stops_before_any_input(mouse):
    m,cursor=mouse;cursor[:]=[0,0]
    with pytest.raises(InterruptedError):m.move_to(400,500)
    m._run.assert_not_called()


def test_stalled_relative_motion_is_transient_not_fatal(mouse):
    m,cursor=mouse
    m._run.side_effect=lambda *args:m.desktop.updated.set()
    with pytest.raises(InterruptedError):m.move_to(750,650)


def test_final_check_can_retarget_cursor_before_click(mouse):
    m,cursor=mouse
    moves=[]
    def move_to(x,y):
        moves.append((x,y));cursor[:]=[x,y]
    m.move_to=Mock(side_effect=move_to)
    m.click(400,500,before_click=lambda:(431,516))
    assert moves==[(400,500),(431,516)]
    m._run.assert_called_once_with('click','-D',40,'0xC0')


def test_invalid_retarget_value_never_clicks(mouse):
    m,cursor=mouse
    m.move_to=Mock(side_effect=lambda x,y:cursor.__setitem__(slice(None),[x,y]))
    with pytest.raises(TypeError):
        m.click(400,500,before_click=lambda:'wrong')
    m._run.assert_not_called()

def test_moving_target_is_revalidated_after_correction(mouse):
    m,cursor=mouse
    m.move_to=Mock(side_effect=lambda x,y:cursor.__setitem__(slice(None),[x,y]))
    guard=Mock(side_effect=[(430,510),InterruptedError('Koruma açıldı')])
    with pytest.raises(InterruptedError):m.click(400,500,before_click=guard)
    assert guard.call_count==2
    m._run.assert_not_called()


def test_ring_animation_within_hit_area_clicks_without_chasing(mouse):
    m,cursor=mouse
    m.move_to=Mock(side_effect=lambda x,y:cursor.__setitem__(slice(None),[x,y]))
    guard=Mock(side_effect=[(406,503),(399,496),(407,502)])
    m.click(400,500,before_click=guard,target_tolerance=8)
    assert guard.call_count==1
    m.move_to.assert_called_once_with(400,500)
    m._run.assert_called_once_with('click','-D',40,'0xC0')


def test_ring_tolerance_does_not_allow_user_cursor_movement(mouse):
    m,cursor=mouse
    m.move_to=Mock(side_effect=lambda x,y:cursor.__setitem__(slice(None),[x,y]))
    def guard():
        cursor[:]=[406,503]
        return (406,503)
    with pytest.raises(InterruptedError,match='kullanıcı'):
        m.click(400,500,before_click=guard,target_tolerance=8)
    m._run.assert_not_called()
