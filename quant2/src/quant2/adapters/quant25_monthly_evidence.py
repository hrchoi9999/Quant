"""Read-only verification of an already received actual monthly input.

No labels, timestamps, receipts, or model targets are generated here.
"""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path, PurePosixPath

import pandas as pd

from .quant25_etf_intent_connection import validate_monthly_publication
from .quant25_incremental_selection import aware
from .quant25_monthly_start_contract import INITIAL_CONTRACT, read_contract, resolved_receipt, verify_bundle_files
from .quant25_paper_live import canonical_sha256, validate_freeze_bundle


def _read(path, expected=None):
    raw = Path(path).read_bytes()
    if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('monthly evidence hash mismatch')
    return raw, json.loads(raw)


def _verify_received_sources(freeze, freeze_dir):
    """Read frozen code only; never import it or change the producer's checks."""
    quant_root = Path(__file__).resolve().parents[4]
    freeze_dir = Path(freeze_dir).resolve()
    outputs = {}
    for name, digest in freeze['manifest']['output_hashes'].items():
        normalized = name.replace('\\', '/')
        relative = PurePosixPath(normalized)
        if (relative.is_absolute() or '..' in relative.parts or ':' in normalized
                or normalized != relative.as_posix() or normalized in outputs):
            raise ValueError('monthly evidence invalid frozen output path')
        outputs[normalized] = (name, digest)
    # These are the exact legacy paths copied by freeze_quant25_three_profiles.
    legacy = {
        'src/evaluation/normalized_nav.py', 'src/evaluation/corporate_actions.py',
        'src/backtest/configs/s6_defensive_config.py',
        'src/backtest/portfolio/s6_defensive_allocator.py',
    }
    sources = {p: h for p, h in freeze['manifest']['source_hashes'].items() if p.endswith('.py')}
    sources.update({p: h for p, h in freeze['execution_contract']['source_hashes'].items()
                    if p.replace('\\', '/').endswith('/etf_meta.csv')})
    for name, expected in sources.items():
        source = quant_root / Path(name)
        if '..' in source.parts or not source.is_relative_to(quant_root):
            raise ValueError('monthly evidence invalid source path')
        relative = source.relative_to(quant_root).as_posix()
        code = None
        if source.suffix == '.py' and relative.startswith(('quant2/src/', 'quant2/scripts/')):
            code = 'code/' + relative.removeprefix('quant2/')
        elif relative in legacy:
            code = 'code/legacy_dependency/' + source.name
        if code is not None:
            registered = outputs.get(code)
            if (registered is None or registered[1] != expected
                    or registered[0] not in freeze['verified_frozen_outputs']):
                raise ValueError('monthly evidence frozen code source binding mismatch')
            path = freeze_dir / Path(code)
            # Reject traversal, junction/symlink redirection and same-name alternatives.
            if path.resolve() != path or not path.is_relative_to(freeze_dir):
                raise ValueError('monthly evidence frozen code path redirected')
        else:
            # Original research receipts and metadata retain their exact source checks.
            # No basename search or latest-source fallback is allowed for these files.
            path = source
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('monthly evidence frozen source hash mismatch')


def verify_received_monthly(value, evidence, *, signal_day, checked_at, observation_root=None,
                            availability_cutoff=None):
    """Validate pinned file evidence against the original append-only journal."""
    if not isinstance(evidence, dict) or not all(evidence.get(k) for k in (
        'bundle_path', 'ready_sha256', 'visibility_sha256', 'receipt_path', 'receipt_sha256', 'freeze_dir',
    )):
        raise ValueError('complete monthly receipt evidence references required')
    checked = aware(checked_at)
    if checked > pd.Timestamp.now(tz='UTC'):
        raise ValueError('monthly evidence check cannot use a future clock')
    cutoff = aware(availability_cutoff) if availability_cutoff is not None else None
    if cutoff is not None and not aware(signal_day + 'T15:30:00+09:00') <= cutoff <= checked:
        raise ValueError('monthly availability cutoff outside signal/check interval')
    folder = Path(evidence['bundle_path']).resolve()
    _, ready = _read(folder / 'READY.json', evidence['ready_sha256'])
    verify_bundle_files(folder)
    target_raw, target = _read(folder / 'target.json', ready['file_sha256']['target.json'])
    pub_raw, pub = _read(folder / 'publication.json', ready['file_sha256']['publication.json'])
    _, visibility = _read(folder / 'VISIBILITY.json', evidence['visibility_sha256'])
    _, receipt_file = _read(evidence['receipt_path'], evidence['receipt_sha256'])
    _, calendar = _read(folder / 'calendar.json', ready['file_sha256']['calendar.json'])
    if value != target or any(
        item.get('actual_publication') is not True or item.get('active') is not True for item in (target, pub)
    ) or target.get('evidence_state') != 'ACTUAL_PRODUCER_PUBLICATION':
        raise ValueError('actual target bytes and publication required; TEST_ONLY forbidden')
    contract = read_contract(pub['initial_contract_path'], pub['initial_contract_sha256'])
    if (pub.get('timing_contract_id') != INITIAL_CONTRACT
            or folder.parent != Path(contract['publication_root']).resolve()
            or folder.name != contract['decision_date']):
        raise ValueError('monthly evidence approved root/contract mismatch')
    freeze = validate_freeze_bundle(Path(evidence['freeze_dir']).resolve())
    for key in ('freeze_id', 'freeze_manifest_sha256', 'execution_contract_sha256'):
        if freeze[key] != contract[key] or pub[key] != freeze[key]:
            raise ValueError('monthly evidence frozen revision mismatch')
    _verify_received_sources(freeze, evidence['freeze_dir'])
    for key, name in (('prices', 'prices.csv'), ('calendar', 'calendar.json'),
                      ('previous_target_state', 'previous_target_state.json')):
        digest = ready['file_sha256'][name]
        if pub['generation_input_sha256'][key] != digest:
            raise ValueError('monthly generation source binding mismatch')
        if key in ('prices', 'calendar') and contract[key + '_sha256'] != digest:
            raise ValueError('monthly generation contract input mismatch')
    if (visibility.get('contract_id') != INITIAL_CONTRACT
            or visibility.get('classification') != 'ACTUAL_PRODUCER_PUBLICATION'
            or ready.get('classification') != 'ACTUAL_PRODUCER_PUBLICATION'
            or visibility.get('ready_sha256') != evidence['ready_sha256']
            or visibility.get('publication_sha256') != ready['file_sha256']['publication.json']
            or visibility.get('target_sha256') != ready['file_sha256']['target.json']):
        raise ValueError('monthly visibility binding mismatch')
    target_hash = hashlib.sha256(target_raw).hexdigest()
    receipt_id = 'receipt:etf_intent:' + target_hash
    db = Path(contract['observation_root']).resolve() / 'forward_receipts.sqlite3'
    if observation_root is not None and Path(observation_root).resolve() != db.parent:
        raise ValueError('monthly receipt belongs to a different observation session')
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as con:
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        row = con.execute("SELECT body,raw FROM journal WHERE key=? AND kind='receipt'", (receipt_id,)).fetchone()
        if row is None or row[1] != target_raw:
            raise ValueError('original monthly receipt missing or target differs')
        primary = json.loads(row[0])
        if (primary.get('completion_required') is not True or primary.get('actual_receipt') is not True
                or primary.get('classification') != 'ACTUAL_PRODUCER_PUBLICATION'
                or primary.get('timing_contract_id') != INITIAL_CONTRACT):
            raise ValueError('original actual completion-required receipt required')
        resolved = resolved_receipt(con, primary)
        if resolved != receipt_file:
            raise ValueError('pinned receipt/completion evidence mismatch')
        binding_key = f"monthly-etf:{freeze['freeze_id']}:{target['decision_date']}"
        row = con.execute("SELECT body,raw FROM journal WHERE key=? AND kind='monthly_etf_publication'",
                          (binding_key,)).fetchone()
        if row is None or row[1] != pub_raw:
            raise ValueError('original monthly publication binding missing')
        binding = json.loads(row[0])
        expected_binding = {
            'publication':pub, 'publication_sha256':ready['file_sha256']['publication.json'],
            'calendar_sha256':ready['file_sha256']['calendar.json'], 'receipt_id':receipt_id,
            'validation':'CONTRACT_AND_HASH_ONLY_OWNER_AUTHENTICITY_REQUIRED',
            'visibility':visibility, 'visibility_sha256':evidence['visibility_sha256'],
            'timing_contract_id':INITIAL_CONTRACT,
        }
        if binding != expected_binding or canonical_sha256(binding) != resolved['publication_binding_sha256']:
            raise ValueError('monthly receipt/publication binding mismatch')
        config = con.execute("SELECT body FROM journal WHERE key='config' AND kind='config'").fetchone()
        if config is None or any(json.loads(config[0])[k] != freeze[k] for k in (
            'freeze_id', 'freeze_manifest_sha256', 'execution_contract_sha256',
        )):
            raise ValueError('monthly receipt session freeze mismatch')
    done = resolved['completion_evidence']
    if (done.get('classification') != 'ACTUAL_PRODUCER_PUBLICATION'
            or done.get('contract_id') != INITIAL_CONTRACT
            or done.get('basis') != 'POST_PRIMARY_COMMIT_VERIFIED_OR_CURRENT_RESTART_OBSERVATION'):
        raise ValueError('monthly completion contract mismatch')
    moments = [pub['generated_at'], pub['published_at'], ready['commit_started_at'],
               visibility['confirmed_visible_at'], primary['first_observed_at'], resolved['available_at']]
    stamps = [aware(t) for t in moments]
    if (stamps != sorted(stamps) or stamps[-1] > checked
            or resolved['arrived_at'] != resolved['available_at']
            or resolved['provider_available_at'] != visibility['confirmed_visible_at']):
        raise ValueError('monthly evidence future availability or nonchronological time')
    validate_monthly_publication(target, pub, calendar, freeze=freeze,
                                received_at=primary['first_observed_at'], target_sha256=target_hash,
                                calendar_sha256=ready['file_sha256']['calendar.json'])
    day = pd.Timestamp(signal_day)
    completed = day.to_period('M') - 1
    month_days = [d for d in calendar if pd.Timestamp(d).to_period('M') == day.to_period('M')]
    if month_days and signal_day == max(month_days) and calendar[-1] >= day.to_period('M').end_time.strftime('%Y-%m-%d'):
        completed = day.to_period('M')
    eligible = [d for d in calendar if pd.Timestamp(d).to_period('M') == completed]
    if (not eligible or target['decision_date'] != max(eligible)
            or (aware(resolved['available_at']) > cutoff if cutoff is not None else
                aware(resolved['available_at']).tz_convert('Asia/Seoul').date() > day.date())):
        raise ValueError('monthly receipt not available for latest completed signal month')
    return resolved
