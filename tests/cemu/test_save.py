"""Fixture editor tests; no copyrighted save data needed."""
import importlib.util
from pathlib import Path
import struct
import zlib
import pytest

spec = importlib.util.spec_from_file_location('cemu_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def fixture():
    data = bytearray(1027208)
    struct.pack_into('>I', data, 0, 0x471b)
    names = [('PlayerSavePos', 3), ('PlayerSavePosAngleYDegree', 1),
             ('MainField_TBox_Field_Stone_123', 1), ('PlayerSavePosMapType', 8),
             ('PlayerSavePosMapName', 8)]
    at = 12
    for name, count in names:
        for _ in range(count):
            struct.pack_into('>II', data, at, zlib.crc32(name.encode()), 1)
            at += 8
    return data, at


def test_editor_preserves_source_hashes_and_unrelated_bytes():
    source, end = fixture()
    original = bytes(source)
    output = runner.patch_save(source, [1, 2, 3], 180, 123)
    assert bytes(source) == original
    assert output[:12] == original[:12]
    assert output[end:] == original[end:]
    for at in range(12, end, 8):
        assert output[at:at+4] == original[at:at+4]
    assert [struct.unpack_from('>f', output, at)[0] for at in (16,24,32)] == [1,2,3]
    assert struct.unpack_from('>I', output, 48)[0] == 0


def test_missing_chest_flag_fails_instead_of_creating_unloadable_save():
    source, _ = fixture()
    with pytest.raises(ValueError, match='required field'):
        runner.patch_save(source, [1, 2, 3], 180, 456)


def test_wrong_version_rejected():
    source, _ = fixture()
    source[:4] = b'\x00\x00\x47\x1e'
    with pytest.raises(ValueError, match='v208'):
        runner.patch_save(source, [1,2,3], 180, 123)
