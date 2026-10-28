"""The instrument's reproduction skips a registered value whose k / n / value is not a number. A quant registered
{"k": "40/50", "n": "rank 1 of 20"} as a result value (T2, 2026-10-28); float() on it crashed the run at its end,
after every order had returned — $0.08 and three settled questions lost to one label in the wrong field."""
from hypswarm.reproduce import check_output


def test_a_text_k_n_is_skipped_not_fatal():
    values = {"best_of_grid": {"k": "40/50", "n": "rank 1 of 20"}, "oos_return": {"value": -0.19},
              "n_settings": 20, "flag": {"value": True}}
    out = check_output(values, "oos_return -0.19\nn_settings 20\n")
    assert isinstance(out, dict)
    assert "oos_return" in out.get("confirmed", []) and "n_settings" in out.get("confirmed", [])
    assert "best_of_grid" not in out.get("contradicted", [])
