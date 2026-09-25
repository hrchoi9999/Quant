"""Retired T publication must stop before source IO or transport calls."""
import hashlib

import pytest

from src.quant2.storage import private_tseries_candidate as candidate
from src.quant2.storage.admin_publish_candidate import (
    PRIVATE_BUCKET,
    CandidateError,
    conditional_private_upload,
)


def test_retired_supplementary_plan_does_not_read_source(monkeypatch):
    class Unreadable:
        def read_bytes(self):
            raise AssertionError("retired source must not be read")

    monkeypatch.setattr(candidate, "SOURCE", Unreadable())
    with pytest.raises(CandidateError, match="retired"):
        candidate.build_private_tseries_plan(
            expected_sha256="0" * 64, private_bucket=PRIVATE_BUCKET,
            supplementary_opt_in=True,
        )


@pytest.mark.parametrize("name", [
    "quantservice_tseries_discovery.json", "ai_learning_models_current.json",
    "internal_models_ai_overlay_shadow_current.json",
    "e_series_etf_sleeve_portfolio_current.json",
])
def test_even_previously_approved_plan_cannot_upload_retired_current(name):
    class ForbiddenTransport:
        def get(self, *args, **kwargs):
            raise AssertionError("retired upload must not contact cloud")

        post = get

    raw = b"{}"
    entry = {"bucket": PRIVATE_BUCKET, "object": "admin/current/" + name,
             "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
             "supplementary_opt_in": True, "research_opt_in": True}
    with pytest.raises(CandidateError, match="retired"):
        conditional_private_upload(entry, raw, ForbiddenTransport(), supplementary_opt_in=True)
