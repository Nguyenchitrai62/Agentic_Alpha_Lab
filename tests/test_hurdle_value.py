import numpy as np
import pytest
from agentic_alpha_lab.models.hurdle_value import compose_hurdle, fit_hurdle, predict_hurdle


def test_hurdle_composition_probability_and_payoff_units():
    prediction = compose_hurdle(np.array([[.5]]), np.array([[.75]]), np.array([[4.]]), np.array([[2.]]))
    assert prediction[0, 0, 0] == pytest.approx(2.5)
    fill = 1/(1+np.exp(-prediction[...,4]))
    assert (prediction[...,0]*fill).item() == pytest.approx(1.25)
    assert np.isfinite(compose_hurdle(np.array([0.]), np.array([1.]), np.array([-1.]), np.array([-1.]))).all()


def test_hurdle_fit_predict_shapes_and_flatten_order():
    from threadpoolctl import threadpool_limits
    rng = np.random.default_rng(14)
    features = rng.normal(size=(350,2))
    candidates = np.array([[1.],[-1.]])
    x = np.concatenate((np.repeat(features,2,axis=0),np.tile(candidates,(350,1))),axis=1)
    labels = np.zeros((350,2,3))
    labels[...,0] = (x[:,0]*x[:,2]).reshape(350,2)
    labels[...,1] = 1
    labels[::4,:,0:2] = 0
    with threadpool_limits(limits=2):
        models = fit_hurdle(x, labels, {"loss":"squared_error","max_iter":3,"min_samples_leaf":10,"early_stopping":False})
        prediction = predict_hurdle(models,features[:5],candidates)
    assert prediction.shape == (5,2,6)
    assert np.isfinite(prediction).all()


def test_hurdle_rejects_absent_conditional_outcomes():
    with pytest.raises(ValueError,match="Insufficient"):
        fit_hurdle(np.ones((4,2)),np.zeros((2,2,3)),{})
