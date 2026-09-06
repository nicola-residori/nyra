from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]

def load_module(filename: str, name: str):
    path = ROOT / "speaker-id" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_one_sample_profile_is_immediately_usable(tmp_path):
    profiles = load_module("profiles.py", "nyra_speaker_profiles_one")
    store = profiles.ProfileStore(tmp_path)
    store.initialize()

    store.add_sample(
        user_id="user-123",
        source_id="kitchen",
        wav_bytes=b"processed",
        embedding=[1.0, 3.0],
        quality={"rms": 0.2},
    )

    profile = store.get_profile("user-123")
    assert profile is not None
    assert profile.user_id == "user-123"
    assert profile.centroid == [1.0, 3.0]
    assert profile.sample_count == 1


def test_add_sample_rebuilds_equal_weight_centroid(tmp_path):
    profiles = load_module("profiles.py", "nyra_speaker_profiles_add")
    store = profiles.ProfileStore(tmp_path)
    store.initialize()

    store.add_sample(user_id="u", source_id="a", wav_bytes=b"a", embedding=[1.0, 3.0], quality={})
    store.add_sample(user_id="u", source_id="b", wav_bytes=b"b", embedding=[3.0, 5.0], quality={})

    profile = store.get_profile("u")
    assert profile is not None
    assert profile.centroid == [2.0, 4.0]
    assert profile.sample_count == 2


def test_source_id_is_metadata_only_and_canonical_user_is_untouched(tmp_path):
    profiles = load_module("profiles.py", "nyra_speaker_profiles_source")
    store = profiles.ProfileStore(tmp_path)
    store.initialize()

    sample = store.add_sample(
        user_id="User:ABC/123",
        source_id="living-room-speaker",
        wav_bytes=b"wav",
        embedding=[0.2, 0.8],
        quality={"peak": 0.8},
    )

    profile = store.get_profile("User:ABC/123")
    assert profile is not None
    assert profile.user_id == "User:ABC/123"
    assert sample.user_id == "User:ABC/123"
    assert sample.source_id == "living-room-speaker"
    assert store.get_profile("living-room-speaker") is None


def test_delete_sample_rebuilds_centroid(tmp_path):
    profiles = load_module("profiles.py", "nyra_speaker_profiles_delete")
    store = profiles.ProfileStore(tmp_path)
    store.initialize()

    first = store.add_sample(user_id="u", source_id=None, wav_bytes=b"a", embedding=[1.0, 1.0], quality={})
    store.add_sample(user_id="u", source_id=None, wav_bytes=b"b", embedding=[5.0, 5.0], quality={})

    rebuilds_before = store.rebuild_count
    store.delete_samples("u", [first.sample_id])

    profile = store.get_profile("u")
    assert profile is not None
    assert profile.centroid == [5.0, 5.0]
    assert profile.sample_count == 1
    assert store.rebuild_count == rebuilds_before + 1
    assert not Path(first.wav_path).exists()


def test_multi_delete_performs_single_rebuild(tmp_path):
    profiles = load_module("profiles.py", "nyra_speaker_profiles_multi")
    store = profiles.ProfileStore(tmp_path)
    store.initialize()

    a = store.add_sample(user_id="u", source_id=None, wav_bytes=b"a", embedding=[1.0], quality={})
    b = store.add_sample(user_id="u", source_id=None, wav_bytes=b"b", embedding=[2.0], quality={})
    store.add_sample(user_id="u", source_id=None, wav_bytes=b"c", embedding=[9.0], quality={})

    rebuilds_before = store.rebuild_count
    deleted = store.delete_samples("u", [a.sample_id, b.sample_id])

    assert deleted == 2
    assert store.rebuild_count == rebuilds_before + 1
    assert store.get_profile("u").centroid == [9.0]


def test_deleting_last_sample_deletes_profile(tmp_path):
    profiles = load_module("profiles.py", "nyra_speaker_profiles_last")
    store = profiles.ProfileStore(tmp_path)
    store.initialize()

    sample = store.add_sample(user_id="u", source_id=None, wav_bytes=b"a", embedding=[1.0], quality={})
    store.delete_samples("u", [sample.sample_id])

    assert store.get_profile("u") is None
    assert store.list_samples("u") == []
