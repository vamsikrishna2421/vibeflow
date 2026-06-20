"""Tests for persona sample storage and profiling logic (no network/LLM)."""

from vibeflow.persona import MIN_SAMPLES, REPROFILE_EVERY, Persona


def test_add_sample_length_gate():
    p = Persona()
    assert p.add_sample("too short") is False          # below MIN_SAMPLE_LEN
    assert p.add_sample("x" * 25) is True               # at the threshold
    assert p.add_sample("y" * 5000) is False            # above MAX_SAMPLE_LEN
    assert p.sample_texts() == ["x" * 25]


def test_rolling_window_cap():
    p = Persona()
    for i in range(120):
        p.add_sample(f"this is dictation sample number {i}")
    # capped to the most recent MAX_SAMPLES
    from vibeflow.persona import MAX_SAMPLES

    assert len(p.samples) == MAX_SAMPLES
    assert p.sample_texts()[-1].endswith("119")


def test_needs_profile_thresholds():
    p = Persona()
    for i in range(MIN_SAMPLES - 1):
        p.add_sample(f"dictation about kubernetes deployment number {i}")
    assert p.needs_profile() is False                   # not enough samples yet
    p.add_sample("one more dictation about devops pipelines and clusters")
    assert p.needs_profile() is True                    # enough, never profiled

    p.set_profile("The user works in DevOps.")
    assert p.needs_profile() is False                   # just profiled
    for i in range(REPROFILE_EVERY):
        p.add_sample(f"another devops dictation sample number {i} here")
    assert p.needs_profile() is True                    # enough new samples -> reprofile


def test_clear_and_persistence(tmp_path):
    path = tmp_path / "persona.json"
    p = Persona(path=path)
    for i in range(6):
        p.add_sample(f"sample dictation about data engineering number {i}")
    p.set_profile("The user is a data engineer.")
    p.save()

    reloaded = Persona(path=path)
    assert reloaded.profile_text() == "The user is a data engineer."
    assert len(reloaded.samples) == 6

    reloaded.clear()
    assert reloaded.profile_text() == "" and reloaded.samples == []


def test_reload_if_changed(tmp_path):
    path = tmp_path / "persona.json"
    a = Persona(path=path)
    a.add_sample("a dictation about data pipelines and warehouses today")
    a.save()
    # A second handle (like the manager window) edits and saves.
    b = Persona(path=path)
    b.set_profile("The user is a data engineer.")
    b.save()
    # The first handle picks up the change.
    assert a.reload_if_changed() is True
    assert a.profile_text() == "The user is a data engineer."
    assert a.reload_if_changed() is False   # no further change
