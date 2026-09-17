from backend import model_loader


def test_model_loader_uses_v3_when_present():
    assert model_loader.get_model_version() == "clauseguard-text-v3"
    assert model_loader.get_model_path().name == "clauseguard_model_v3.joblib"


def test_model_loader_uses_exact_v3_metadata():
    metadata = model_loader.get_model_metadata()
    assert metadata["model_version"] == "clauseguard-text-v3"
    assert metadata["artifact"] == "clauseguard_model_v3.joblib"
