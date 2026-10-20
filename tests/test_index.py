import numpy as np

from kda import calibrate, products


def test_index_scale_and_cap():
    assert products.soiling_index(0.0) == 0
    assert products.soiling_index(0.4) == 50
    assert products.soiling_index(2.0) == 100


def test_class_breakpoints():
    names = products._class_names([0.1, 0.2, 0.349, 0.35, 0.5, np.nan])
    assert list(names) == ["Low", "Moderate", "Moderate", "High", "Very high", ""]


def test_correction_never_negative():
    assert calibrate.apply(0.0, 0.855, -0.073) == 0.0
    assert abs(calibrate.apply(0.5, 0.855, -0.073) - 0.3545) < 1e-9
