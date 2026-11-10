from fastapi import Query,HTTPException,Request
import threading,time
from typing import Literal
from .coordinates import parse_coordinates
from .space import space_catalog


def install_space_routes(app):
    recent={}
    lock=threading.Lock()
    @app.get('/api/space')
    def space(request:Request,ra:str='232.663579354',dec:str='-10.7213238583',fov:float=Query(default=8,ge=2,le=120),scope:Literal['nearby','field']='nearby',radius_pc:float=Query(default=25,ge=5,le=1000),include_simbad:bool=False,mjd:float|None=Query(default=None,ge=40000,le=90000)):
        client=request.client.host if request.client else 'unknown'
        now=time.monotonic()
        with lock:
            hits=[t for t in recent.get(client,[]) if now-t<60]
            if len(hits)>=20:raise HTTPException(429,'Please wait before requesting more catalog volumes.')
            recent[client]=hits+[now]
        try:
            coord=parse_coordinates(ra,dec)
            return space_catalog(float(coord.ra.deg),float(coord.dec.deg),fov,scope,radius_pc,include_simbad,mjd)
        except ValueError as exc:raise HTTPException(422,str(exc))
        except Exception:raise HTTPException(503,'Catalog distances are temporarily unavailable. No synthetic 3D stars or invented distances are shown.')
