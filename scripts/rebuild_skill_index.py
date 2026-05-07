from __future__ import annotations

from config import SETTINGS
from tools.skill_index_tools import rebuild_skill_faiss_index


def main() -> int:
    metadata_dir = SETTINGS.sandbox_dir / 'skills' / 'metadatas'
    index_dir = SETTINGS.sandbox_dir / 'skills' / 'indexes'

    metadata_paths = [
        path.relative_to(SETTINGS.sandbox_dir).as_posix()
        for path in sorted(metadata_dir.glob('*.json'))
    ]

    if metadata_paths:
        print(rebuild_skill_faiss_index(metadata_paths))
        return 0

    index_dir.mkdir(parents=True, exist_ok=True)
    for name in ('skills.faiss', 'skills.map.json', 'skills.stats.json'):
        path = index_dir / name
        if path.exists():
            path.unlink()
            print(f'removed {path}')

    print({'status': 'ok', 'message': 'no skills found; index cleared'})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
