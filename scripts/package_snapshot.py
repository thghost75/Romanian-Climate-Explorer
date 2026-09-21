"""Create release assets without modifying either verified SQLite database."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'version': 1, 'files': []}
    total_size = sum((args.data_root / name).stat().st_size for name in ('climate.sqlite', 'climatology.sqlite'))
    if total_size >= 4_800_000_000:
        raise RuntimeError('Snapshot exceeds the safe Vercel function size; keep the current deployment')
    for name in ('climate.sqlite', 'climatology.sqlite'):
        source = args.data_root / name
        for suffix in ('-wal', '-journal'):
            sidecar = Path(str(source) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise RuntimeError('Snapshot requires a closed, checkpointed database: ' + name)
        before = source.stat()
        digest = hashlib.sha256()
        asset = args.output / (name + '.gz')
        partial = asset.with_suffix('.gz.part')
        print('Compressing ' + name + '…', flush=True)
        with source.open('rb') as incoming, partial.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=6, mtime=0) as compressed:
                while chunk := incoming.read(4 * 1024 * 1024):
                    digest.update(chunk)
                    compressed.write(chunk)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            partial.unlink()
            raise RuntimeError('Source changed while packaging: ' + name)
        if partial.stat().st_size >= 2 * 1024**3:
            raise RuntimeError('Compressed asset exceeds GitHub release limit: ' + name)
        partial.replace(asset)
        manifest['files'].append({'name': name, 'asset': asset.name, 'bytes': before.st_size,
                                  'sha256': digest.hexdigest(), 'compressed_bytes': asset.stat().st_size})
        print(f'{asset.name}: {asset.stat().st_size:,} bytes; source hash {digest.hexdigest()}', flush=True)
    notes = (args.data_root / 'processed/phase3/candidate_review_notes.json').read_bytes()
    (PROJECT / 'snapshots/candidate_review_notes.json').write_bytes(notes)
    manifest['review_notes_sha256'] = hashlib.sha256(notes).hexdigest()
    (PROJECT / 'snapshots/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Snapshot manifest written.', flush=True)


if __name__ == '__main__':
    main()
