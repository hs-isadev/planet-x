"""Gzip text-like responses only.

Render's free instance has a fraction of a CPU, so spending it on PNG, FITS or GLB files
(already compressed or incompressible) would slow those requests down. Scripts, styles,
JSON and HTML shrink by 70-90 percent, which is where cold-load time goes.
"""
from pathlib import PurePosixPath

from starlette.middleware.gzip import GZipMiddleware

SKIP_SUFFIXES = frozenset({
    '.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.glb', '.fits', '.gz', '.zip',
    '.woff', '.woff2', '.mp4', '.webm',
})
SKIP_FRAGMENTS = ('/original/',)  # FITS bytes served without a file extension


class TextGZipMiddleware:
    def __init__(self, app, minimum_size=1024, compresslevel=5):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            path = scope.get('path', '')
            if (PurePosixPath(path).suffix.lower() in SKIP_SUFFIXES
                    or any(fragment in path for fragment in SKIP_FRAGMENTS)):
                return await self.app(scope, receive, send)
            return await self.compressed(scope, receive, send)
        return await self.app(scope, receive, send)
