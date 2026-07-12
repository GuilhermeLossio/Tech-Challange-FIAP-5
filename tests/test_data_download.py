from __future__ import annotations

from pathlib import Path

from src.data import download


class FakeKaggleApi:
    def authenticate(self) -> None:
        return None

    def dataset_download_files(self, dataset: str, path: str, unzip: bool) -> None:
        assert dataset == "custom/hillstrom"
        assert unzip is True
        Path(path, "downloaded_hillstrom.csv").write_text("segment,conversion\nNo E-Mail,0\n")


def test_download_dataset_renames_downloaded_csv(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RAW_FILENAME", "hillstrom.csv")
    monkeypatch.setattr(download, "KaggleApi", FakeKaggleApi)

    result = download.download_dataset(dataset="custom/hillstrom", output_dir=tmp_path)

    assert result == tmp_path / "hillstrom.csv"
    assert result.exists()
    assert not (tmp_path / "downloaded_hillstrom.csv").exists()
