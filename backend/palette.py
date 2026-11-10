import io
import numpy as np
from PIL import Image
from matplotlib import colormaps
from matplotlib.colors import LinearSegmentedColormap
from fastapi import HTTPException
from fastapi.responses import Response
def install_palette_routes(app):
    @app.get('/api/colorbar')
    def colorbar(cmap:str='gray',stretch:str='asinh'):
        if cmap not in ('inferno','magma','viridis','gray','infrared','coolwarm') or stretch not in ('linear','sqrt','log','asinh'):raise HTTPException(422,'Unknown color scale')
        values=np.linspace(0,1,260)
        if stretch=='sqrt':values=np.sqrt(values)
        elif stretch=='log':values=np.log1p(100*values)/np.log(101)
        elif stretch=='asinh':values=np.arcsinh(10*values)/np.arcsinh(10)
        color=LinearSegmentedColormap.from_list('infrared',['#050914','#3e124f','#a32b72','#e77352','#ffd18a','#fff4d8']) if cmap=='infrared' else colormaps[cmap]
        rgb=(color(values)[None,...,:3]*255).astype(np.uint8);image=Image.fromarray(rgb).resize((260,16));stream=io.BytesIO();image.save(stream,format='PNG');return Response(stream.getvalue(),media_type='image/png',headers={'Cache-Control':'public,max-age=86400'})
