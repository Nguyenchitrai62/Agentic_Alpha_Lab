import importlib.util
from pathlib import Path
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA


def test_portable_projection_matches_train_only_sklearn():
    path = Path(__file__).resolve().parents[1] / "scripts/probe_swing_context.py"
    spec = importlib.util.spec_from_file_location("probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rng = np.random.default_rng(7)
    train, future = rng.normal(size=(80, 12)), rng.normal(size=(30, 12)) + 100
    scaler = StandardScaler().fit(train)
    pca = PCA(n_components=5, svd_solver="full", whiten=False).fit(scaler.transform(train))
    parameters = module.fit_projection(train, 5)
    np.testing.assert_allclose(module.project(future, parameters), pca.transform(scaler.transform(future)), rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(parameters["mean"], train.mean(0))
