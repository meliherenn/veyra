from state import HarvestTracker
from timing_store import TimingStore


def test_each_species_learns_separately_and_survives_restart(tmp_path):
    path=tmp_path/'times.json';store=TimingStore(path)
    assert store.estimate('alacakaranlik')==9
    assert store.summary('alacakaranlik')['count']==0
    store.record('alacakaranlik',10.2,.5,'yesil')
    store.record('alacakaranlik',10.6,.5,'yesil')
    store.record('elmas_som',14.3,.6,'mavi')
    restarted=TimingStore(path)
    assert restarted.estimate('alacakaranlik')==10.4
    assert restarted.estimate('elmas_som')==14.3
    assert restarted.summary('alacakaranlik')['count']==2
    assert restarted.summary('gumus_kadife')['count']==0
    assert restarted.estimate('kral_yengec') is None


def test_invalid_measurement_never_creates_sample(tmp_path):
    store=TimingStore(tmp_path/'times.json')
    for value in (0,-5,200,float('nan'),float('inf')):
        assert not store.record('gumus_kadife',value)
    assert not store.record('unknown',9)
    assert store.summary('gumus_kadife')['count']==0


def test_verification_wait_is_excluded_from_duration():
    tracker=HarvestTracker()
    tracker.update(True,False,100)
    tracker.update(True,False,108.5)
    assert not tracker.update(False,True,109.2)
    assert tracker.update(False,True,110.7)
    assert abs(tracker.measured_seconds-9.2)<.001
    assert abs(tracker.uncertainty-.7)<.001


def test_only_recent_samples_affect_new_estimates(tmp_path):
    store=TimingStore(tmp_path/'times.json')
    for _ in range(40):store.record('gumus_kadife',30)
    for _ in range(40):store.record('gumus_kadife',9)
    assert store.estimate('gumus_kadife')==9
    assert store.summary('gumus_kadife')['count']==80
