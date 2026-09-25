from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from src.quant2.operations.ai_retirement import is_retired_object

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.quant2.storage.admin_publish_candidate import (  # noqa: E402
    PRIVATE_BUCKET,
    PRIVATE_STANDARD_NAMES,
    PUBLIC_BUCKET,
    RESEARCH_OBJECTS,
    CandidateError,
    build_plan,
    conditional_private_upload,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network/credential access is forbidden in local tests")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


@pytest.fixture
def publisher(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "publisher_under_test", ROOT.parent / "scripts/publish_public_current_to_gcs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key in ("CURRENT_DIR", "PUBLIC_HISTORY_DIR", "ADMIN_CURRENT_DIR", "TRADING_SIGN_CURRENT_DIR"):
        directory = tmp_path / key
        directory.mkdir()
        monkeypatch.setattr(module, key, directory)
    for name in module.ROOT_OBJECTS:
        (module.CURRENT_DIR / name).write_text('{"as_of_date":"2026-09-04"}')
    for name, _ in module.USER_HISTORY_OBJECTS:
        (module.PUBLIC_HISTORY_DIR / name).write_text('{}')
    (module.CURRENT_DIR / module.T_SERIES_OBJECT[0]).write_text('{}')
    (module.PUBLIC_HISTORY_DIR / module.T_SERIES_HISTORY_OBJECT[0]).write_text('{}')
    for key, pair in vars(module).items():
        if key.startswith("ADMIN_") and isinstance(pair, tuple):
            (module.ADMIN_CURRENT_DIR / pair[0]).write_text('{}')
    for name, _ in module.ADMIN_VALUATION_AI_OBJECTS:
        (module.ADMIN_CURRENT_DIR / name).write_text('{}')
    for name in RESEARCH_OBJECTS:
        (module.ADMIN_CURRENT_DIR / name).write_text('{}')
    for name, _ in module.TRADING_SIGN_OBJECTS:
        (module.TRADING_SIGN_CURRENT_DIR / name).write_text('{}')
    def forbidden(*args, **kwargs):
        raise AssertionError("credentials must not be resolved")
    monkeypatch.setattr(module, "_resolve_cred_path", forbidden)
    monkeypatch.setattr(module, "_access_token", forbidden)
    return module


def arguments(**kwargs):
    values = dict(bucket=PUBLIC_BUCKET, admin_bucket=None, admin_research_object=[], dry_run=True,
                  admin_strategy_research_observation_only=False, skip_user_current=False,
                  skip_user_history=False, skip_tseries_current=False, skip_tseries_history=False,
                  skip_admin_current=False, skip_admin_history=False, skip_trading_sign_current=False)
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_default_plan_has_legacy_objects_no_research(publisher):
    plan = build_plan(arguments(), vars(publisher))
    assert plan["object_count"] == 17
    assert len(plan["retired_objects_skipped"]) == 12
    assert not any(is_retired_object(e["object"]) for e in plan["objects"])
    assert {e["bucket"] for e in plan["objects"]} == {PUBLIC_BUCKET}
    assert plan["research_selected"] == []
    assert plan["credential_resolution"] is False


def test_split_preserves_every_public_key(publisher):
    old = build_plan(arguments(), vars(publisher))
    new = build_plan(arguments(admin_bucket=PRIVATE_BUCKET), vars(publisher))
    assert len(new["objects"]) == len(old["objects"])
    for before, after in zip(old["objects"], new["objects"]):
        assert before["source"] == after["source"]
        assert before["object"] == after["object"]
        assert after["bucket"] == (PRIVATE_BUCKET if after["object"].startswith("admin/current/")
                                   else PUBLIC_BUCKET)
    assert sum(e["bucket"] == PRIVATE_BUCKET for e in new["objects"]) == 5


def test_shared_total_return_research_survives_ai_retirement(publisher):
    plan = build_plan(arguments(admin_bucket=PRIVATE_BUCKET,
                                admin_research_object=["e_series_etf_total_return_adjustment_current.json"]), vars(publisher))
    selected = [e for e in plan["objects"] if e["research_opt_in"]]
    assert len(selected) == 1
    assert len(plan["objects"]) == 18
    assert all(e["required"] and e["bucket"] == PRIVATE_BUCKET for e in selected)


@pytest.mark.parametrize("changes", [
    {"bucket": PRIVATE_BUCKET}, {"bucket": "wrong-public"},
    {"admin_bucket": PUBLIC_BUCKET}, {"admin_bucket": "wrong-private"},
    {"admin_bucket": "gs://" + PRIVATE_BUCKET},
    {"admin_research_object": ["ai_learning_overlay_monitor_current.json"]},
    {"admin_bucket": PRIVATE_BUCKET, "admin_research_object": ["../secret.json"]},
    {"admin_bucket": PRIVATE_BUCKET, "admin_research_object": ["all"]},
    {"admin_bucket": PRIVATE_BUCKET, "admin_research_object": ["ai_learning_overlay_monitor_current.json"] * 2},
    {"admin_bucket": PRIVATE_BUCKET, "skip_admin_current": True,
     "admin_research_object": ["ai_learning_overlay_monitor_current.json"]},
    {"admin_bucket": PRIVATE_BUCKET, "admin_strategy_research_observation_only": True,
     "admin_research_object": ["ai_learning_overlay_monitor_current.json"]},
])
def test_invalid_selection_fail_closed(publisher, changes):
    with pytest.raises(CandidateError):
        build_plan(arguments(**changes), vars(publisher))


@pytest.mark.parametrize("directory,name,changes", [
    ("CURRENT_DIR", "user_model_catalog.json", {}),
    ("ADMIN_CURRENT_DIR", "admin_new_entry_tracker.json", {"admin_bucket": PRIVATE_BUCKET}),
    ("ADMIN_CURRENT_DIR", "internal_model_performance_history.json", {"admin_bucket": PRIVATE_BUCKET}),
    ("ADMIN_CURRENT_DIR", "e_series_etf_total_return_adjustment_current.json",
     {"admin_bucket": PRIVATE_BUCKET, "admin_research_object": ["e_series_etf_total_return_adjustment_current.json"]}),
])
def test_required_input_missing_aborts_whole_plan(publisher, directory, name, changes):
    (getattr(publisher, directory) / name).unlink()
    with pytest.raises(CandidateError, match="missing required"):
        build_plan(arguments(**changes), vars(publisher))


def test_missing_retired_artifact_is_never_read(publisher):
    (publisher.ADMIN_CURRENT_DIR / "valuation_ai_challenger_current.json").unlink()
    plan = build_plan(arguments(), vars(publisher))
    assert plan["object_count"] == 17
    assert len(plan["skipped_optional"]) == 0
    assert "admin/current/valuation_ai_challenger_current.json" in plan["retired_objects_skipped"]


@pytest.mark.parametrize("name", sorted(n for n in PRIVATE_STANDARD_NAMES if not is_retired_object(n)))
def test_private_selected_admin_all_required(publisher, name):
    (publisher.ADMIN_CURRENT_DIR / name).unlink()
    with pytest.raises(CandidateError, match="missing required"):
        build_plan(arguments(admin_bucket=PRIVATE_BUCKET), vars(publisher))


def test_quant_does_not_own_qa_portfolio(publisher):
    with pytest.raises(CandidateError):
        build_plan(arguments(admin_bucket=PRIVATE_BUCKET,
                             admin_research_object=["investment_portfolio_latest.json"]),
                   vars(publisher))


@pytest.mark.parametrize("raw", ["not-json", "null", '{"x":NaN}'])
def test_bad_input_rejected(publisher, raw):
    (publisher.CURRENT_DIR / "user_model_catalog.json").write_text(raw)
    with pytest.raises((CandidateError, ValueError)):
        build_plan(arguments(), vars(publisher))


def test_cli_dry_run_exits_before_credentials(publisher, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["publisher", "--dry-run", "--admin-bucket", PRIVATE_BUCKET])
    publisher.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["object_count"] == 17 and plan["network_calls"] == 0


def test_private_cli_cannot_activate(publisher, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["publisher", "--admin-bucket", PRIVATE_BUCKET])
    with pytest.raises(CandidateError, match="inactive"):
        publisher.main()


@pytest.mark.parametrize("flag", [None, "--skip-user-current", "--skip-user-history",
                                  "--skip-tseries-current", "--skip-tseries-history",
                                  "--skip-admin-current", "--skip-admin-history",
                                  "--skip-trading-sign-current",
                                  "--admin-strategy-research-observation-only"])
def test_legacy_public_cli_stays_blocked_before_io(publisher, monkeypatch, flag):
    calls = []
    monkeypatch.setattr(publisher, "_upload_file", lambda bucket, src, name, token:
                        calls.append((bucket, str(src), name)))
    monkeypatch.setattr(sys, "argv", ["publisher"] + ([flag] if flag else []))
    with pytest.raises(RuntimeError, match="exact legacy public destination is disabled"):
        publisher.main()
    assert calls == []
    kwargs = {flag[2:].replace("-", "_"): True} if flag else {}
    plan = build_plan(arguments(**kwargs), vars(publisher))
    assert not any(is_retired_object(e["object"]) for e in plan["objects"])
    assert plan["credential_resolution"] is False


class Response:
    def __init__(self, code=200, body=None, content=b'{}'):
        self.status_code, self.body, self.content = code, body, content

    def json(self):
        return self.body


class Transport:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def _call(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def get(self, url, **kwargs):
        return self._call("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._call("POST", url, kwargs)


NAME = "admin/current/admin_new_entry_tracker.json"


def metadata(gen="12", size="2", name=NAME, bucket=PRIVATE_BUCKET):
    return {"generation": gen, "size": size, "name": name, "bucket": bucket}


def entry(**kwargs):
    return dict({"bucket": PRIVATE_BUCKET, "object": NAME, "size_bytes": 2,
                 "sha256": hashlib.sha256(b'{}').hexdigest(), "research_opt_in": False}, **kwargs)


@pytest.mark.parametrize("existing", [True, False])
def test_conditional_write_content_and_live_generation_verified(existing):
    first = Response(body=metadata("11")) if existing else Response(404)
    io = Transport([first, Response(201, metadata()), Response(), Response(body=metadata())])
    evidence = conditional_private_upload(entry(), b'{}', io)
    assert evidence["verified"] is True
    assert evidence["verified_generation"] == "12"
    assert evidence["sha256"] == evidence["observed_sha256"]
    assert io.calls[1][2]["params"]["ifGenerationMatch"] == ("11" if existing else "0")
    assert all(c[0] != "DELETE" for c in io.calls)
    for c in io.calls[2:]:
        assert c[2]["params"]["ifGenerationMatch"] == "12"
        assert "generation" not in c[2]["params"]
    assert all(c[2]["allow_redirects"] is False for c in io.calls)


@pytest.mark.parametrize("code", [409, 412, 401, 403, 500])
def test_upload_failure_never_retries_or_deletes(code):
    io = Transport([Response(404), Response(code)])
    with pytest.raises(CandidateError) as error:
        conditional_private_upload(entry(), b'{}', io)
    assert [c[0] for c in io.calls] == ["GET", "POST"]
    assert not error.value.evidence["retry_allowed"]


@pytest.mark.parametrize("response", [Response(403), Response(500), Response(302),
                                      Response(body=metadata(gen=None)),
                                      Response(body=metadata(bucket=PUBLIC_BUCKET))])
def test_preflight_failure_no_write(response):
    io = Transport([response])
    with pytest.raises(CandidateError):
        conditional_private_upload(entry(), b'{}', io)
    assert len(io.calls) == 1


@pytest.mark.parametrize("responses", [
    [Response(412)], [Response(content=b'[]')],
    [Response(), Response(body=metadata("13"))],
    [Response(), Response(412)], [Response(), Response(body=metadata(size="999"))],
])
def test_readback_mismatch_or_live_replacement_is_not_success(responses):
    io = Transport([Response(404), Response(201, metadata()), *responses])
    with pytest.raises(CandidateError) as error:
        conditional_private_upload(entry(), b'{}', io)
    assert error.value.evidence["uploaded_generation"] == "12"
    assert error.value.evidence["write_outcome"] == "accepted_not_yet_verified"
    assert not error.value.evidence["verified"]
    assert sum(c[0] == "POST" for c in io.calls) == 1


def test_timeout_has_unknown_write_outcome_and_no_token_leak():
    io = Transport([Response(404), TimeoutError("secret-token")])
    with pytest.raises(CandidateError) as error:
        conditional_private_upload(entry(), b'{}', io)
    assert error.value.evidence["write_outcome"] == "unknown"
    assert "secret-token" not in str(error.value.evidence)
    assert len(io.calls) == 2


@pytest.mark.parametrize("changes", [
    {"bucket": PUBLIC_BUCKET}, {"object": "user_model_catalog.json"},
    {"object": "admin/current/../../secret.json"}, {"sha256": "changed"},
    {"object": "admin/current/ai_learning_overlay_monitor_current.json"},
])
def test_invalid_private_entry_no_io(changes):
    io = Transport([])
    with pytest.raises(CandidateError):
        conditional_private_upload(entry(**changes), b'{}', io)
    assert not io.calls
