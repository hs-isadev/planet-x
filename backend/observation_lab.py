"""Scoped same-origin bridge to the teammate SPHEREx workflow."""
import asyncio
import json
import os
import uuid
from http.server import ThreadingHTTPServer
import re
from threading import Lock, Thread
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

PREFIX = '/observation-lab'
INIT = Lock()
SERVICE = None

PUBLIC_GET = re.compile(
    r'(?:api/(?:library|pixel|identify|jobs/[a-f0-9]{32}|original/[a-f0-9]{64})'
    r'|cache/(?:[a-f0-9]{32}/[0-9]+(?:-quality)?\.png|[a-f0-9]{64}\.fits)'
    r'|data/(?:vesta|barnard|epsilon-indi|r-dra|rw-aur|wise-0855)/[\w.-]+\.(?:png|fits))'
)
PUBLIC_POST = {'api/jobs','api/spectrum','api/track'}


def start_service():
    global SERVICE
    with INIT:
        if SERVICE is not None:
            return SERVICE.server_address[1]
        from .observation_lab_core import server
        server.initialize()
        service = ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        Thread(target=service.serve_forever,daemon=True,name='observation-lab').start()
        SERVICE = service
        return service.server_address[1]


def rewrite_paths(value):
    if isinstance(value,str) and value.startswith(('/api/','/cache/','/data/')):
        return PREFIX+value
    if isinstance(value,list):
        return [rewrite_paths(v) for v in value]
    if isinstance(value,dict):
        return {k:rewrite_paths(v) for k,v in value.items()}
    return value


def install_lab_routes(app):
    if os.environ.get('SPHEREX_PREWARM') == '1':
        @app.on_event('startup')
        def start_cache_warmup():
            from .observation_lab_core.warm_cache import run_forever
            Thread(target=run_forever, daemon=True, name='spherex-prewarm').start()

    @app.api_route(PREFIX+'/{kind}/{path:path}',methods=['GET','POST'],include_in_schema=False)
    async def proxy(kind: str, path: str, request: Request):
        route = f'{kind}/{path}'
        if kind not in ('api','cache','data'):
            from .archive import ROOT
            if request.method!='GET' or not re.fullmatch(r'css/[\w-]+\.css',route):
                raise HTTPException(404)
            file=ROOT/'web/observation-lab'/route
            if not file.is_file():
                raise HTTPException(404)
            return FileResponse(file,media_type='text/css')
        query = request.url.query
        if len(query)>4096:
            raise HTTPException(414)
        if request.method=='POST':
            if route not in PUBLIC_POST:
                raise HTTPException(404)
            origin=request.headers.get('origin')
            if origin and urlsplit(origin).netloc!=request.url.netloc:
                raise HTTPException(403)
            if request.headers.get('content-type','').split(';')[0]!='application/json':
                raise HTTPException(415)
            data=bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data)>64*1024:
                    raise HTTPException(413)
            body=bytes(data)
            if route == 'api/jobs':
                from .observation_lab_core.featured_views import locate
                from .observation_lab_core.science import request_options
                from .observation_lab_core.server import cached_featured_session
                try:
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError('Expected a sky-field request.')
                    options = await asyncio.to_thread(request_options, payload)
                except (ValueError, TypeError) as error:
                    return JSONResponse({'error': str(error)}, status_code=400)
                field_key = payload.get('field')
                field = locate(None if field_key == 'custom' else field_key, options)
                if field and payload.get('source') != 'archive':
                    snapshot = await asyncio.to_thread(cached_featured_session, field, options, uuid.uuid4().hex)
                    if snapshot:
                        return JSONResponse(rewrite_paths({'result': snapshot}), headers={'Cache-Control': 'no-store'})
        else:
            if not PUBLIC_GET.fullmatch(route):
                raise HTTPException(404)
            if kind == 'cache':
                from .observation_lab_core.featured_views import cache_path
                file = cache_path(path)
                if not file:
                    raise HTTPException(404, 'The cached observation has expired.')
                return FileResponse(file, media_type='image/png' if file.suffix == '.png' else 'application/fits',
                                    headers={'Cache-Control': 'public, max-age=31536000, immutable'})
            body=None
        try:
            port=await asyncio.to_thread(start_service)
            url=f'http://127.0.0.1:{port}/'+route+('?' + query if query else '')
            headers={'content-type':'application/json'} if body is not None else None
            async with httpx.AsyncClient(timeout=85,trust_env=False) as client:
                response=await client.request(request.method,url,content=body,headers=headers)
        except (httpx.HTTPError,OSError,ValueError,ImportError):
            raise HTTPException(503,'The SPHEREx Observation Lab is still preparing its archive files.') from None
        content_type=response.headers.get('content-type','application/octet-stream').split(';')[0]
        if content_type=='application/json':
            return JSONResponse(rewrite_paths(response.json()),status_code=response.status_code)
        return Response(response.content,status_code=response.status_code,media_type=content_type,
                        headers={'Cache-Control':'private, max-age=3600'} if kind in ('cache','data') else {})
