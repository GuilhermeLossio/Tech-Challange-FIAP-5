import pandas as pd

from src.data.process import process_bank_marketing


def test_process_bank_marketing_removes_leakage_and_maps_target() -> None:
    raw = pd.DataFrame(
        {
            "Age": [35, 42, 35],
            "Job": ["admin.", "technician", "admin."],
            "Duration": [120, 80, 120],
            "Y": ["yes", "no", "yes"],
        }
    )

    processed = process_bank_marketing(raw)

    assert "duration" not in processed.columns
    assert processed["y"].tolist() == [1, 0]
    assert processed.columns.tolist() == ["age", "job", "y"]
