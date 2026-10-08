"""Loopback-only friends recognition demo; templates stay in process memory."""
import argparse
from http.server import ThreadingHTTPServer
import json
import secrets
import threading
import webbrowser

from vision.demo_identity import DemoIdentity, load_gallery
from vision.models import ROOT, require_models
from central.staff import MODEL, SHA256
from vision.models import verified
from web_app import Handler, Session


class DemoSession(Session):
    def __init__(self, photo_root=None):
        super().__init__()
        self.gallery = {}
        self.photo_root = photo_root or ROOT/'demo_photos'
        self.import_lock = threading.Lock()

    def import_photos(self, consent):
        with self.import_lock:
            if self.snapshot()['running']:
                raise ValueError('Stop the webcam session before importing photos.')
            gallery = load_gallery(self.photo_root,consent)
            self.gallery = gallery
            return self.gallery_info()

    def gallery_info(self):
        return {'people':[{'name':name,'photos':len(samples)} for name,samples in self.gallery.items()]}

    def start(self, data):
        with self.import_lock:
            if not self.gallery:
                raise ValueError('Import your friends’ photos first.')
            if data.get('mode')!='browser':
                raise ValueError('Use the browser webcam for this demo.')
            return super().start(data)

    def make_identity(self):
        return DemoIdentity(self.gallery)


class DemoHandler(Handler):
    def do_GET(self):
        if not self.valid_host():
            return self.reply(403,{'error':'Local access only.'})
        path=self.path.split('?',1)[0]
        if path=='/':
            page=(ROOT/'web'/'demo.html').read_text(encoding='utf-8')
            return self.reply(200,page.replace('__TOKEN__',self.server.token).encode(),'text/html; charset=utf-8')
        if path=='/api/gallery':
            return self.reply(200,self.server.session.gallery_info())
        return super().do_GET()

    def do_POST(self):
        if self.path not in ('/api/import','/api/start'):
            return super().do_POST()
        if (not self.valid_host() or self.headers.get('X-Session-Token')!=self.server.token
                or self.headers.get('Origin') not in {None,*self.server.allowed_origins}):
            return self.reply(403,{'error':'Invalid local session.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=16384:
                raise ValueError('Invalid request size.')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                raise ValueError('Invalid request.')
            if self.path=='/api/import':
                return self.reply(200,self.server.session.import_photos(data.get('consent')))
            return self.reply(200,{'ok':True,'capture_id':self.server.session.start(data)})
        except ValueError as error:
            return self.reply(400,{'error':str(error)})
        except Exception:
            return self.reply(500,{'error':'Import failed. Check photo files and run setup_demo.bat if models are missing.'})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8020)
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    require_models()
    if not verified(MODEL,SHA256):
        raise SystemExit('Staff model missing. Run setup_demo.bat first.')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),DemoHandler)
    server.session=DemoSession()
    server.token=secrets.token_urlsafe(32)
    server.allowed_hosts={f'127.0.0.1:{args.port}',f'localhost:{args.port}'}
    server.allowed_origins={f'http://{host}' for host in server.allowed_hosts}
    print(f'Maggpie friends demo: http://127.0.0.1:{args.port}',flush=True)
    if args.open:
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.session.stop.set()
        if server.session.worker:
            server.session.worker.join(timeout=15)
        server.server_close()


if __name__=='__main__':
    main()
