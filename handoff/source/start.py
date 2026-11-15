"""No frontend build step. Run from the project root: python start.py"""
import argparse,os
from pathlib import Path
from dotenv import load_dotenv
import uvicorn
if __name__=='__main__':
    load_dotenv(Path(__file__).with_name('.env'), override=False)
    parser=argparse.ArgumentParser(description='Parallax / SPHEREx observatory')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8000')))
    args=parser.parse_args()
    uvicorn.run('backend.main:app',host=args.host,port=args.port,workers=1)
