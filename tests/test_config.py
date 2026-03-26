from ecg_lab.config import get_data_paths


def test_get_data_paths_uses_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ECG_LAB_DATA_ROOT", str(tmp_path))

    paths = get_data_paths()

    assert paths.root == tmp_path.resolve()
    assert paths.raw_record == tmp_path.resolve() / "records" / "raw_record"
    assert paths.registry == tmp_path.resolve() / "registry"


def test_ensure_directories_creates_tree(monkeypatch, tmp_path):
    monkeypatch.setenv("ECG_LAB_DATA_ROOT", str(tmp_path))

    paths = get_data_paths()
    paths.ensure_directories()

    assert paths.registry.exists()
    assert paths.raw_record.exists()
    assert paths.clean_record.exists()
    assert paths.raw_chunk.exists()
    assert paths.clean_chunk.exists()
