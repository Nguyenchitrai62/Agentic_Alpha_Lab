"""Learn fill, conditional win probability and conditional gain/loss separately."""
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor


def fit_hurdle(x, labels, params):
    net = labels[..., 0].reshape(-1)
    filled = labels[..., 1].reshape(-1) > .5
    won = net > 0
    if not np.isfinite(x).all() or not np.isfinite(labels).all():
        raise ValueError("Invalid training samples")
    if any(mask.sum() < 100 for mask in (filled, filled & won, filled & ~won)):
        raise ValueError("Insufficient filled/win/loss outcomes")
    classifier_params = dict(params, loss="log_loss")
    return {
        "fill": HistGradientBoostingClassifier(**classifier_params).fit(x, filled),
        "win": HistGradientBoostingClassifier(**classifier_params).fit(x[filled], won[filled]),
        "gain": HistGradientBoostingRegressor(**params).fit(x[filled & won], net[filled & won]),
        "loss": HistGradientBoostingRegressor(**params).fit(x[filled & ~won], -net[filled & ~won])
    }


def compose_hurdle(fill, win, gain, loss):
    fill, win = np.clip(fill, 1e-6, 1-1e-6), np.clip(win, 1e-6, 1-1e-6)
    conditional_net = win * np.maximum(gain, 0) - (1-win) * np.maximum(loss, 0)
    output = np.zeros((*conditional_net.shape, 6), np.float32)
    output[..., 0] = conditional_net
    output[..., 4], output[..., 5] = np.log(fill/(1-fill)), np.log(win/(1-win))
    return output


def predict_hurdle(models, features, candidates):
    n, k = len(features), len(candidates)
    x = np.concatenate((np.repeat(features, k, axis=0), np.tile(candidates, (n, 1))), axis=1)
    values = [models[name].predict_proba(x)[:, 1].reshape(n, k) for name in ("fill", "win")]
    values += [models[name].predict(x).reshape(n, k) for name in ("gain", "loss")]
    return compose_hurdle(*values)
