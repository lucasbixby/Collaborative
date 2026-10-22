"""Unit tests for ordering.py (#8 / #9): plain Python, no Blender API used."""

from collaborative_blender import ordering


def test_tick_increases():
    clock = ordering.LamportClock()

    assert clock.tick() == 1
    assert clock.tick() == 2
    assert clock.tick() == 3


def test_observe_takes_the_max_and_a_following_tick_exceeds_it():
    clock = ordering.LamportClock()
    clock.tick()  # 1

    clock.observe(10)
    assert clock.tick() == 11

    clock.observe(3)  # lower than the current value; must not move backwards
    assert clock.tick() == 12


def test_newer_breaks_ties_by_origin():
    assert ordering.newer((5, "b"), (5, "a"))
    assert not ordering.newer((5, "a"), (5, "b"))
    assert ordering.newer((6, "a"), (5, "z"))  # higher lamport wins outright
    assert not ordering.newer((5, "z"), (6, "a"))
    assert not ordering.newer((5, "a"), (5, "a"))  # equal is not newer


def test_should_apply_is_true_for_an_unknown_key():
    versions = ordering.Versions()

    assert versions.should_apply(("obj-1", "location"), (1, "a"))


def test_should_apply_is_true_for_a_newer_operation():
    versions = ordering.Versions()
    versions.record(("obj-1", "location"), (5, "a"))

    assert versions.should_apply(("obj-1", "location"), (6, "a"))  # higher lamport
    assert versions.should_apply(("obj-1", "location"), (5, "b"))  # tie, bigger origin


def test_should_apply_is_false_for_an_older_or_equal_operation():
    versions = ordering.Versions()
    versions.record(("obj-1", "location"), (5, "b"))

    assert not versions.should_apply(("obj-1", "location"), (5, "a"))  # tie, smaller origin
    assert not versions.should_apply(("obj-1", "location"), (4, "z"))  # lower lamport
    assert not versions.should_apply(("obj-1", "location"), (5, "b"))  # exact duplicate
