"""Astroquery SIMBAD, with documented mirror fallback and bounded requests."""
from astroquery.simbad import Simbad
from .archive import CONFIG,throttle

def query_names(names,fields=()):
    error=None
    for server in CONFIG.get('simbad_servers',['simbad.cds.unistra.fr']):
        try:
            client=Simbad();client.server=server
            original=client._session.request
            def bounded(*a,**kw):
                kw.setdefault('timeout',12)
                return original(*a,**kw)
            client._session.request=bounded
            if fields:client.add_votable_fields(*fields)
            throttle()
            table=client.query_objects(names)
            if table is None:raise ValueError('SIMBAD returned no matching objects.')
            return table,server
        except Exception as exc:error=exc
    raise error
