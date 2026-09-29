from config import RESUME_FAST_SECONDS
from state import ResumeGate,HarvestTracker


def test_one_missed_challenge_frame_cannot_resume():
    gate=ResumeGate();gate.block()
    assert not gate.update(True,0)
    assert not gate.update(False,.5)
    assert not gate.update(True,1)
    assert not gate.update(True,2)
    assert not gate.update(True,3)
    assert gate.update(True,4)


def test_background_window_does_not_count_as_solved():
    gate=ResumeGate();gate.block()
    for now in range(10): assert not gate.update(False,now)
    assert not gate.update(True,10)
    assert not gate.update(True,11)
    assert gate.update(True,13)


def test_time_passing_without_observations_does_not_resume():
    gate=ResumeGate();gate.block()
    assert not gate.update(True,0)
    assert not gate.update(True,100)
    assert gate.update(True,101)


def test_unstarted_or_interrupted_harvest_is_never_counted():
    h=HarvestTracker()
    assert not h.update(False,True,0)
    assert not h.update(False,True,20)
    assert not h.update(True,False,21)
    assert not h.update(False,False,22)  # CAPTCHA/unknown frame
    assert not h.update(False,True,23)
    assert not h.update(True,False,24)  # Still harvesting, previous gap was spurious
    assert not h.update(False,True,30)
    assert h.update(False,True,31)


def test_fast_gate_uses_shorter_resume_time():
    gate = ResumeGate()
    gate.block(RESUME_FAST_SECONDS)
    assert not gate.update(True, 0)
    assert not gate.update(True, 1)
    assert gate.update(True, 2)
    gate.block()
    assert not gate.update(True, 3)
    assert not gate.update(True, 4)
    assert not gate.update(True, 5)
    assert gate.update(True, 6)
