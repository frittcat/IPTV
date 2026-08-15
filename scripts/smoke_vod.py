import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.archive_org import ArchiveOrgProvider
from providers.public_media import WikimediaProvider, NASAProvider

for name, provider in [
    ('archive_org', ArchiveOrgProvider(rows=3)),
    ('wikimedia_commons', WikimediaProvider()),
    ('nasa', NASAProvider()),
]:
    try:
        items = list(provider.discover(limit=2, pages=1))[:2]
        print(name, len(items), [x.title for x in items])
    except Exception as exc:
        print(name, 'ERROR', type(exc).__name__, str(exc)[:200])
