"""Reviewed source discovery. Catalog entries give requirements, never execution authority."""
import hashlib
import json
from pathlib import Path

from .isolated_codex import PRIVATE_ROOT
from .source_adapters import REGISTRY

ARCHIVES = {
    'par-yield-curve-rates-2010-2019.csv': 'a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254',
    'par-yield-curve-rates-2020-2023.csv': '25877e5541442e8c8c642a3cf9709d8c20eb2c1603556e3ebd84545f1f0acfe2',
}
CATALOG = {
    'KOSPI': ('domestic_index_daily', 'KRX', 'KOSPI series daily index'),
    'KOSDAQ': ('domestic_index_daily', 'KRX', 'KOSDAQ series daily index'),
    'MARKET_BREADTH': ('market_breadth_summary', 'KRX', 'Market-wide issues advancing and declining'),
    'FOREIGN_SPOT': ('domestic_investor_daily', 'KRX', 'Investor trading by market'),
    'FOREIGN_FUTURES': (None, 'KRX', 'Derivatives investor trading'),
    'KRX_CALENDAR': (None, 'KRX', 'Exchange trading calendar'),
    'KOSPI200_MEMBERS': (None, 'KRX', 'Historical index membership and effective dates'),
    'CORPORATE_ACTIONS': (None, 'KRX', 'Dated corporate actions and adjustment factors'),
    'KOREAN_MACRO': (None, 'ECOS', 'Statistical series and publication vintage'),
}


def discover(requirement):
    for source, adapter in REGISTRY.items():
        if requirement in adapter.series:
            return dict(requirement=requirement, source=source, status='REVIEWED_ADAPTER',
                        pit='REQUIRES_ROW_RELEASE_AND_ACCESS_EVIDENCE')
    if requirement not in CATALOG:
        return dict(requirement=requirement, status='UNSUPPORTED', source=None)
    table, source, product = CATALOG[requirement]
    return dict(requirement=requirement, candidate_table=table, source=source, product=product,
                status='REQUIRES_ACCESS_AND_ADAPTER_REVIEW', pit='UNVERIFIED')


def archived_treasury(uri, state_dir):
    """Only use a host-staged, previously verified exact archive in this program."""
    archive = uri.rsplit('/', 1)[-1]
    digest = ARCHIVES.get(archive)
    if not digest or not uri.startswith('https://home.treasury.gov/'):
        return None
    if state_dir.parent.parent.name != 'jobs':
        return None
    directory = state_dir.parents[2] / 'official_sources'
    if directory.is_symlink() or not directory.resolve().is_relative_to(PRIVATE_ROOT):
        raise ValueError('Invalid local source directory')
    path = directory / archive
    if path.is_symlink():
        raise ValueError('Symlinked source archive')
    if not path.exists():
        return None
    if path.stat().st_size > 2000000:
        raise ValueError('Archive byte budget exceeded')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError('Historical Treasury archive hash mismatch')
    return payload


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('requirements', nargs='+')
    print(json.dumps([discover(item) for item in parser.parse_args().requirements], indent=2))
