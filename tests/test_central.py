from contextlib import closing
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error

from cryptography.fernet import Fernet
import numpy as np

from central.store import Store
from central.staff import StaffStore, StaffMatcher
from central.workers import LatestFrames
from central.server import Application, create_server
from vision.counting import Track


class CentralTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name)/'test.sqlite3')
        self.camera = self.store.add_camera({'showroom':'Delhi','name':'Entry','source_ref':'MAGGPIE_CAMERA_TEST'})
        self.staff = StaffStore(self.store,Fernet.generate_key())

    def test_reports_day_boundary_and_staff_audit(self):
        camera_id=self.camera['id']
        self.store.record(camera_id,'run',[{'track_id':1,'direction':'IN'}],'2026-09-21T18:29:59+00:00')
        self.store.record(camera_id,'run',[{'track_id':2,'direction':'IN'}],'2026-09-21T18:30:00+00:00')
        self.store.record(camera_id,'run',[{'track_id':3,'direction':'OUT','category':'staff'}],'2026-09-21T18:31:00+00:00')
        report=self.store.report('2026-09-22')
        self.assertEqual(report['cameras'][0]['entries'],1)
        self.assertEqual(report['cameras'][0]['exits'],0)
        self.assertEqual(report['cameras'][0]['staff_excluded'],1)
        self.assertEqual(report['hours'][0]['entries'],1)
        restored=Store(self.store.path)
        self.assertEqual(restored.report('2026-09-22'),report)

    def test_encryption_scope_consent_and_delete(self):
        vector=np.ones(128,dtype=np.float32)
        with self.assertRaises(ValueError):
            self.staff.add('Delhi','A',[vector],False)
        staff_id=self.staff.add('Delhi','A',[vector],True)
        self.assertEqual(self.staff.gallery('Mumbai'),[])
        np.testing.assert_equal(self.staff.gallery('Delhi')[0][1][0],vector)
        with closing(self.store.connect()) as db:
            blob=db.execute('SELECT templates FROM staff').fetchone()[0]
        self.assertNotIn(b'[1.0',blob)
        self.staff.delete(staff_id)
        self.assertEqual(self.staff.gallery('Delhi'),[])

    def test_staff_requires_two_matches_and_unambiguous_person(self):
        vector=np.zeros(128,dtype=np.float32);vector[0]=1
        self.staff.add('Delhi','A',[vector],True)
        matcher=StaffMatcher.__new__(StaffMatcher)
        matcher.store=self.staff;matcher.showroom='Delhi';matcher.matches={}
        matcher.recognizer=type('R',(),{'feature':lambda *args:vector})()
        detector=type('D',(),{'last_face_image':np.zeros((200,200,3),np.uint8),
                             'last_face_rows':np.array([[60,20,60,60]+[0]*11],dtype=np.float32)})()
        track=Track(1,(.1,0,.9,1),0,.9)
        matcher.update([track],detector,1)
        self.assertFalse(matcher.is_staff(1,1))
        matcher.update([track],detector,1.2)
        self.assertTrue(matcher.is_staff(1,1.2))
        self.assertFalse(matcher.is_staff(1,3))
        matcher.matches.clear()
        matcher.update([track,Track(2,(.1,0,.9,1),0,.9)],detector,4)
        self.assertFalse(matcher.is_staff(1,4))
        matcher.update([track],detector,5)
        matcher.update([track],detector,5.2)
        self.staff.delete(self.staff.list()[0]['id'])
        matcher.update([track],detector,5.3)
        self.assertFalse(matcher.is_staff(1,5.3))

    def test_latest_frame_never_builds_backlog(self):
        reader=LatestFrames('unused',threading.Event(),lambda state:None)
        for i in range(100):
            reader.put(i)
        self.assertEqual(reader.queue.qsize(),1)
        self.assertEqual(reader.queue.get(),99)

    def test_reconnect_changes_generation_and_releases_capture(self):
        stop=threading.Event();states=[];captures=[]
        class Capture:
            def __init__(self):self.reads=0;self.released=False
            def read(self):
                self.reads+=1
                return (True,np.zeros((10,10,3),np.uint8)) if self.reads==1 else (False,None)
            def release(self):self.released=True
        def open_fake(*args):
            cap=Capture();captures.append(cap);return cap
        reader=LatestFrames('unused',stop,states.append,open_fake);reader.thread.start()
        deadline=time.monotonic()+4
        while len(captures)<2 and time.monotonic()<deadline:time.sleep(.02)
        stop.set();reader.thread.join(2)
        self.assertGreaterEqual(len(captures),2)
        self.assertTrue(all(c.released for c in captures))
        self.assertGreaterEqual(reader.queue.get()[0],2)
        self.assertIn('reconnecting',states)

    def test_http_auth_csrf_and_secret_not_exposed(self):
        app=Application(Path(self.temp.name)/'http','test-password-123456789',Fernet.generate_key(),'http://127.0.0.1:8010')
        server=create_server(app,port=0);port=server.server_address[1]
        app.origin=f'http://127.0.0.1:{port}';app.host=f'127.0.0.1:{port}'
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=app.origin
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/api/dashboard')
        self.assertEqual(error.exception.code,401)
        req=urllib.request.Request(base+'/api/login',data=json.dumps({'password':'test-password-123456789'}).encode(),headers={'Origin':base})
        response=urllib.request.urlopen(req);cookie=response.headers['Set-Cookie'].split(';')[0]
        session=json.load(urllib.request.urlopen(urllib.request.Request(base+'/api/session',headers={'Cookie':cookie})))
        payload=json.dumps({'showroom':'Delhi','name':'Entry','source_ref':'MAGGPIE_CAMERA_TEST'}).encode()
        req=urllib.request.Request(base+'/api/cameras',data=payload,headers={'Cookie':cookie,'Origin':base})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        self.assertEqual(error.exception.code,403)
        req.add_header('X-CSRF-Token',session['csrf'])
        self.assertEqual(urllib.request.urlopen(req).status,201)
        dashboard=urllib.request.urlopen(urllib.request.Request(base+'/api/dashboard',headers={'Cookie':cookie})).read()
        self.assertNotIn(b'test-password',dashboard)
        self.assertNotIn(b'templates',dashboard)


if __name__=='__main__':unittest.main()
