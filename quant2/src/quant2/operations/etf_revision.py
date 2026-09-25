"""Pinned calculation revision layered on the unchanged Q25 strategy freeze."""
import hashlib
import json
from pathlib import Path
from types import FunctionType

ROOT = Path(__file__).resolve().parents[4]
REGISTRY = ROOT / 'quant2/config/operating_calculation_revisions.json'


def read_revision(revision_id, digest, freeze):
    registry = json.loads(REGISTRY.read_bytes())
    entry = registry['revisions'][revision_id]
    path = ROOT / entry['path']
    raw = path.read_bytes()
    if digest != entry['sha256'] or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Unregistered calculation revision')
    revision = json.loads(raw)
    if revision['revision_id'] != revision_id or revision['base_freeze_manifest_sha256'] != freeze['freeze_manifest_sha256']:
        raise ValueError('Calculation revision/freeze mismatch')
    for name, expected in revision['source_hashes'].items():
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT / 'quant2/src/quant2/operations'):
            raise ValueError('Calculation source outside revision namespace')
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError('Calculation revision source changed')
    return revision


def calculator(original, revision):
    from src.quant2.operations.s6_allocator_20260922 import allocate_s6_defensive

    if revision['revision_id'] != 'q25_etf_common_20260922_v1':
        raise ValueError('Unsupported calculation revision')
    namespace = dict(original.__globals__)
    namespace['allocate_s6_defensive'] = allocate_s6_defensive
    return FunctionType(original.__code__, namespace, original.__name__, original.__defaults__)


def revision_sources(revision):
    return {Path(name).name: digest for name, digest in revision['source_hashes'].items()}
