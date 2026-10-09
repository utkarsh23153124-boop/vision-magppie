"""Single-admin central pilot server. Place behind HTTPS reverse proxy in deployment."""
import argparse
import base64
import csv
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import signal
import threading
import time
from urllib.parse import urlsplit, parse_qs

import cv2
import numpy as np

from central.staff import StaffStore, Recognizer
from central.store import Store, IST
from central.uniform_store import UniformStore
from central.workers import Manager
from vision.detectors import Detectors
from vision.models import ROOT


class Application:
    def __init__(self, data_dir, password, key, origin, limit=4):
        if len(password) < 16:
            raise ValueError('MAGGPIE_ADMIN_PASSWORD must contain at least 16 characters.')
        parsed = urlsplit(origin)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('Set MAGGPIE_PUBLIC_ORIGIN to the exact dashboard origin without a trailing slash.')
        if parsed.scheme != 'https' and parsed.hostname not in ('127.0.0.1','localhost'):
            raise ValueError('Non-loopback dashboard origins require HTTPS.')
        self.origin, self.host, self.password = origin, parsed.netloc, password
        self.secure = parsed.scheme == 'https'
        self.store = Store(Path(data_dir) / 'maggpie.sqlite3')
        self.staff = StaffStore(self.store, key)
        self.uniforms = UniformStore(self.store)
        self.manager = Manager(self.store, self.staff, limit, uniform_store=self.uniforms)
        self.sessions, self.attempts = {}, {}
        self.lock, self.enroll_lock = threading.Lock(), threading.Lock()

    def session(self, cookie):
        try:
            jar = SimpleCookie(cookie or '')
            token = jar['maggpie_session'].value
        except (KeyError, ValueError):
            return None
        with self.lock:
            session = self.sessions.get(token)
            if not session or session['expires'] < time.monotonic():
                self.sessions.pop(token, None)
                return None
            return session

    def login(self, password, ip):
        now = time.monotonic()
        with self.lock:
            self.attempts = {key: [t for t in values if now-t < 60] for key, values in self.attempts.items()
                             if values and now-values[-1] < 60}
            attempts = self.attempts.setdefault(ip, [])
            if len(attempts) >= 5:
                raise ValueError('Too many login attempts. Wait one minute.')
            attempts.append(now)
            if not secrets.compare_digest(str(password).encode(), self.password.encode()):
                raise ValueError('Invalid password.')
            self.sessions = {key: value for key,value in self.sessions.items() if value['expires'] > now}
            token = secrets.token_urlsafe(32)
            self.sessions[token] = {'csrf': secrets.token_urlsafe(32), 'expires': now+8*3600}
            return token


class Handler(BaseHTTPRequestHandler):
    server_version = 'Maggpie'

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass

    @property
    def app(self):
        return self.server.app

    def reply(self, status, data, content_type='application/json', cookie=None):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-ancestors 'none'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def allowed_host(self):
        return self.headers.get('Host') == self.app.host

    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403, {'error':'Invalid host.'})
        parsed = urlsplit(self.path)
        if parsed.path == '/healthz':
            return self.reply(200, {'status':'ok'})
        assets = {'/': ('index.html','text/html; charset=utf-8'),
                  '/app.js': ('app.js','text/javascript; charset=utf-8'),
                  '/style.css': ('style.css','text/css; charset=utf-8')}
        if parsed.path in assets:
            name, content_type = assets[parsed.path]
            return self.reply(200, (ROOT/'central'/'web'/name).read_bytes(), content_type)
        session = self.app.session(self.headers.get('Cookie'))
        if not session:
            return self.reply(401, {'error':'Sign in to continue.'})
        try:
            if parsed.path == '/api/session':
                return self.reply(200, {'csrf':session['csrf']})
            if parsed.path == '/api/preview':
                frame = self.app.manager.preview(parse_qs(parsed.query).get('id',[''])[0])
                return self.reply(200 if frame else 204, frame or b'', 'image/jpeg')
            if parsed.path == '/api/cameras/health':
                cam_id = parse_qs(parsed.query).get('id',[''])[0]
                worker = self.app.manager.workers.get(cam_id)
                if not worker:
                    return self.reply(404, {'error': 'Camera worker not found.'})
                return self.reply(200, worker.health.snapshot())
            if parsed.path == '/api/uniform':
                showroom = parse_qs(parsed.query).get('showroom', [None])[0]
                return self.reply(200, self.app.uniforms.list(showroom))
            if parsed.path == '/api/dashboard':
                date = parse_qs(parsed.query).get('date',[datetime.now(IST).strftime('%Y-%m-%d')])[0]
                return self.reply(200, {'cameras':self.app.store.cameras(), 'workers':self.app.manager.snapshot(),
                                        'report':self.app.store.report(date), 'staff':self.app.staff.list(),
                                        'uniforms':self.app.uniforms.list(),
                                        'staff_history':self.app.store.staff_crossings(100),
                                        'crossings_log':self.app.store.all_crossings(100)})
            if parsed.path == '/api/report.csv':
                date = parse_qs(parsed.query).get('date',[datetime.now(IST).strftime('%Y-%m-%d')])[0]
                report = self.app.store.report(date)
                stream = io.StringIO()
                writer = csv.writer(stream)
                writer.writerow(['date_IST','showroom','camera','visitor_entries','visitor_exits','staff_crossings_excluded'])
                def cell(value):
                    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
                for row in report['cameras']:
                    writer.writerow([date,cell(row['showroom']),cell(row['name']),row['entries'],row['exits'],row['staff_excluded']])
                return self.reply(200, stream.getvalue().encode(), 'text/csv; charset=utf-8')
            return self.reply(404, {'error':'Not found.'})
        except ValueError:
            return self.reply(400, {'error':'Invalid date. Use YYYY-MM-DD.'})

    def do_POST(self):
        if not self.allowed_host() or self.headers.get('Origin') != self.app.origin:
            return self.reply(403, {'error':'Invalid request origin.'})
        if self.path != '/api/login':
            session = self.app.session(self.headers.get('Cookie'))
            if not session:
                return self.reply(401, {'error':'Sign in to continue.'})
            if self.headers.get('X-CSRF-Token') != session['csrf']:
                return self.reply(403, {'error':'Refresh and sign in again.'})
        try:
            length = int(self.headers.get('Content-Length','0'))
            maximum = 16_000_000 if self.path == '/api/staff' else 16384
            if not 0 < length <= maximum:
                return self.reply(413, {'error':'Request too large or empty.'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Invalid request.')
            if self.path == '/api/login':
                token = self.app.login(data.get('password',''), self.client_address[0])
                cookie = f'maggpie_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800'
                if self.app.secure:
                    cookie += '; Secure'
                return self.reply(200, {'ok':True}, cookie=cookie)
            if self.path == '/api/logout':
                jar = SimpleCookie(self.headers.get('Cookie'))
                with self.app.lock:
                    self.app.sessions.pop(jar['maggpie_session'].value, None)
                return self.reply(200, {'ok':True}, cookie='maggpie_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
            if self.path == '/api/cameras':
                return self.reply(201, self.app.store.add_camera(data))
            if self.path == '/api/cameras/start':
                self.app.manager.start(str(data.get('id','')))
            elif self.path == '/api/cameras/configure':
                self.app.manager.configure(str(data.get('id','')),data)
            elif self.path == '/api/cameras/stop':
                self.app.manager.stop(str(data.get('id','')))
            elif self.path == '/api/cameras/delete':
                self.app.manager.delete(str(data.get('id','')))
            elif self.path == '/api/staff':
                if data.get('consent') is not True:
                    raise ValueError('Confirm staff consent before enrollment.')
                photos = data.get('photos', [])
                if not isinstance(photos,list) or not 1 <= len(photos) <= 10:
                    raise ValueError('Choose 1–10 portrait photos.')
                embeddings = []
                with self.app.enroll_lock:
                    detector, recognizer = Detectors(), Recognizer()
                    for photo in photos:
                        image = cv2.imdecode(np.frombuffer(base64.b64decode(photo, validate=True), np.uint8), cv2.IMREAD_COLOR)
                        if image is None or image.shape[0]*image.shape[1] > 16_000_000:
                            raise ValueError('Invalid image or image larger than 16 megapixels.')
                        embeddings.append(recognizer.enroll(image, detector))
                staff_id = self.app.staff.add(str(data.get('showroom','')),str(data.get('name','')),embeddings,True)
                return self.reply(201, {'id':staff_id})
            elif self.path == '/api/staff/delete':
                self.app.staff.delete(str(data.get('id','')))
            elif self.path == '/api/uniform':
                showroom = str(data.get('showroom', '')).strip()
                label = str(data.get('label', '')).strip()
                photos = data.get('photos', [])
                if not isinstance(photos, list) or not 1 <= len(photos) <= 10:
                    raise ValueError('Choose 1–10 uniform sample photos.')
                frames = []
                for p in photos:
                    img = cv2.imdecode(np.frombuffer(base64.b64decode(p, validate=True), np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        frames.append(img)
                pid = self.app.uniforms.register(showroom, label, frames)
                self.app.manager.reload_uniforms(showroom)
                return self.reply(201, {'id': pid, 'label': label, 'showroom': showroom})
            elif self.path == '/api/uniform/delete':
                showroom = str(data.get('showroom', '')).strip()
                label = str(data.get('label', '')).strip()
                self.app.uniforms.delete(showroom, label)
                self.app.manager.reload_uniforms(showroom)
            else:
                return self.reply(404, {'error':'Not found.'})
            return self.reply(200, {'ok':True})
        except ValueError as error:
            return self.reply(400, {'error':str(error)})
        except TypeError:
            return self.reply(400, {'error':'Invalid request fields.'})
        except Exception:
            return self.reply(500, {'error':'Server operation failed. Check model setup and database access.'})


def create_server(app, host='127.0.0.1', port=8010):
    server = ThreadingHTTPServer((host, port), Handler)
    server.app = app
    return server


def main():
    from central.env import load_env
    # Check root .env first, then deploy/.env
    load_env(ROOT / '.env', override=True)
    load_env(ROOT / 'deploy' / '.env', override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8010)
    parser.add_argument('--env-file', default=None, help='Custom path to .env file')
    args = parser.parse_args()

    if args.env_file:
        load_env(args.env_file, override=True)

    app = Application(os.environ.get('MAGGPIE_DATA_DIR', str(ROOT/'data')),
                      os.environ.get('MAGGPIE_ADMIN_PASSWORD',''), os.environ.get('MAGGPIE_STAFF_KEY',''),
                      os.environ.get('MAGGPIE_PUBLIC_ORIGIN',f'http://127.0.0.1:{args.port}'),
                      int(os.environ.get('MAGGPIE_MAX_CAMERAS','4')))
    server = create_server(app,args.host,args.port)
    def shutdown(*args):
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    app.manager.restore()
    print('Maggpie central service started.',flush=True)
    try:
        server.serve_forever()
    finally:
        app.manager.close()
        server.server_close()


if __name__ == '__main__':
    main()
