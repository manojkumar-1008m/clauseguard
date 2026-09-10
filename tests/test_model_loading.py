import pathlib
import sys

def test_model_file_exists():
    model_path = pathlib.Path(__file__).resolve().parents[1] / "model" / "clauseguard_model_v1.joblib"
    if not model_path.is_file():
        model_path = pathlib.Path(__file__).resolve().parents[2] / "model" / "clauseguard_model_v1.joblib"
    assert model_path.is_file(), f"Model file not found at {model_path}"
