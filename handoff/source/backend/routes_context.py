import io
from typing import Literal
from PIL import Image,ImageDraw
from fastapi import HTTPException,Query,Request
from fastapi.responses import Response
from .catalogs import catalog_overlay


def install_context_routes(app,jobs,guard,render_frame):
    @app.get('/api/jobs/{identity}/catalog')
    def overlay(identity:str,frame:int=Query(ge=0),catalog:Literal['gaia','wise']='gaia'):
        with guard:
            if identity not in jobs:raise HTTPException(404,'Session expired.')
            job=jobs[identity]
            if frame>=len(job['frames']) or job['frames'][frame]['status']!='ready':raise HTTPException(422,'Select an available observation.')
        try:return catalog_overlay(job,frame,catalog)
        except Exception:raise HTTPException(503,f'{catalog.title()} catalog is temporarily unavailable. No substitute markers are shown.')

    @app.get('/api/jobs/{identity}/export.gif')
    def gif(identity:str,fps:float=Query(default=2,ge=.5,le=12),cmap:str='infrared',stretch:str='asinh',black:float|None=None,white:float|None=None,indices:str|None=None):
        if identity not in jobs:raise HTTPException(404,'Session expired.')
        job=jobs[identity];frames=[f for f in job['frames'] if f['status']=='ready']
        if indices is not None:
            try:
                chosen={int(x) for x in indices.split(',')}
                if len(chosen)>500 or any(x<0 or x>=len(job['frames']) for x in chosen):raise ValueError()
                frames=[f for f in frames if f['index'] in chosen]
            except ValueError:raise HTTPException(422,'Invalid observed-frame selection.')
        if not frames:raise HTTPException(422,'No observed frames available.')
        if len(frames)>500:raise HTTPException(422,'GIF export is limited to 500 observed frames. Select a detector or wavelength group.')
        images=[]
        for frame in frames:
            png=render_frame(identity,frame['index'],cmap,stretch,black,white,False)
            image=Image.open(io.BytesIO(png.body)).convert('RGBA');image=image.resize((320,320),Image.Resampling.NEAREST)
            background=Image.new('RGB',(320,366),'#080d13');background.paste(image,(0,0),image)
            draw=ImageDraw.Draw(background)
            draw.text((9,328),'OBSERVED / SPHEREx / NASA-IPAC-IRSA',fill='#efbb89')
            draw.text((9,345),frame['date'][:19]+' UTC  '+frame['band'],fill='#c6d5da')
            images.append(background)
        stream=io.BytesIO();images[0].save(stream,format='GIF',save_all=True,append_images=images[1:],duration=round(1000/fps),loop=0,comment=b'Observed SPHEREx data; fixed contrast. Dates and wavelengths vary. Not a motion detection.')
        return Response(stream.getvalue(),media_type='image/gif',headers={'Content-Disposition':'attachment; filename="planet-x-observed-flipbook.gif"'})
