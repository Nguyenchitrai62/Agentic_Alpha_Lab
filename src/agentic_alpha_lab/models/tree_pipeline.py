"""Portable non-executable tree checkpoint for the multi-timeframe swing pipeline."""
import json
from pathlib import Path
import numpy as np
from agentic_alpha_lab.data.training import sha256


def export_forests(forests, output: Path):
    arrays, metadata = {}, {}
    for name, forest in forests.items():
        metadata[name] = {"trees": len(forest.estimators_), "features": int(forest.n_features_in_), "outputs": int(forest.n_outputs_)}
        for i, estimator in enumerate(forest.estimators_):
            tree = estimator.tree_
            for key, value in (("left", tree.children_left), ("right", tree.children_right),
                               ("feature", tree.feature), ("threshold", tree.threshold), ("value", tree.value[..., 0])):
                arrays[f"{name}_{i}_{key}"] = value
    if output.exists():
        raise FileExistsError("Do not overwrite checkpoint")
    output.mkdir(parents=True)
    np.savez_compressed(output / "forests.npz", **arrays)
    metadata["sha256"] = sha256(output / "forests.npz")
    (output / "forests.json").write_text(json.dumps(metadata, indent=2))


class PortableForest:
    def __init__(self, root: Path):
        self.meta = json.loads((root / "forests.json").read_text())
        if sha256(root / "forests.npz") != self.meta["sha256"]:
            raise ValueError("Forest checkpoint hash mismatch")
        with np.load(root / "forests.npz", allow_pickle=False) as f:
            self.arrays = {k: f[k] for k in f.files}

    def predict(self, name, features, dispersion=False):
        meta = self.meta[name]
        x = np.asarray(features, np.float32)
        if x.ndim != 2 or x.shape[1] != meta["features"] or not np.isfinite(x).all():
            raise ValueError("Invalid features")
        predictions = []
        for i in range(meta["trees"]):
            get = lambda field: self.arrays[f"{name}_{i}_{field}"]
            left, right, feature, threshold, values = [get(f) for f in ("left", "right", "feature", "threshold", "value")]
            node = np.zeros(len(x), dtype=int)
            for _ in range(len(left)):
                active = np.flatnonzero(left[node] != -1)
                if not len(active):
                    break
                n = node[active]
                node[active] = np.where(x[active, feature[n]] <= threshold[n], left[n], right[n])
            else:
                raise ValueError("Invalid/cyclic tree")
            predictions.append(values[node])
        stacked = np.stack(predictions)
        return (stacked.mean(0), stacked.std(0)) if dispersion else stacked.mean(0)

    def swing_prediction(self, features):
        expected, uncertainty = self.predict("expected", features, True)
        fill = np.clip(self.predict("fill", features), 1e-6, 1 - 1e-6)
        output = np.zeros((*expected.shape, 6), np.float32)
        output[..., 0] = expected / fill
        output[..., 4] = np.log(fill / (1 - fill))
        return output, uncertainty
