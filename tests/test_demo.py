from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import cv2
import numpy as np

from vision.demo_identity import DemoIdentity, load_gallery
from vision.counting import Track
from demo_app import DemoSession


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.vector=np.zeros(128,np.float32);self.vector[0]=1
        self.recognizer=SimpleNamespace(feature=lambda *args:self.vector,enroll=lambda *args:self.vector)
        self.detector=SimpleNamespace(last_face_rows=np.array([[40,20,60,60]+[0]*11]),last_face_image=np.zeros((200,200,3),np.uint8))
        self.faces=[((.2,.1,.5,.4),.99)]
        self.person=Track(1,(0,0,1,1),0,.99)

    def test_registered_name_needs_confirmation_and_excludes_person(self):
        identity=DemoIdentity({'Rahul':np.array([self.vector])},self.recognizer)
        labels,staff=identity.update([self.person],self.detector,self.faces,0)
        self.assertEqual(labels[0]['status'],'checking');self.assertEqual(staff,set())
        labels,staff=identity.update([self.person],self.detector,self.faces,.2)
        self.assertEqual(labels[0]['name'],'Rahul');self.assertEqual(staff,{1})
        self.vector=np.roll(self.vector,1)
        labels,staff=identity.update([self.person],self.detector,self.faces,.4)
        self.assertEqual(labels[0]['name'],'Unknown');self.assertEqual(staff,set())

    def test_name_can_show_without_a_body_but_does_not_exclude_other_person(self):
        identity=DemoIdentity({'Rahul':np.array([self.vector])},self.recognizer)
        identity.update([],self.detector,self.faces,0)
        labels,staff=identity.update([],self.detector,self.faces,.2)
        self.assertEqual(labels[0]['name'],'Rahul');self.assertFalse(staff)
        labels,staff=identity.update([self.person,Track(2,(0,0,1,1),0,.99)],self.detector,self.faces,.4)
        self.assertFalse(staff)

    def test_competing_identities_are_unknown(self):
        identity=DemoIdentity({'A':np.array([self.vector]),'B':np.array([self.vector])},self.recognizer)
        for timestamp in (0,.2,.4):
            labels,staff=identity.update([self.person],self.detector,self.faces,timestamp)
            self.assertEqual(labels[0]['name'],'Unknown');self.assertFalse(staff)

    def test_import_consent_empty_and_valid_photos(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'Rahul';folder.mkdir()
            with self.assertRaises(ValueError):load_gallery(root,False,self.detector,self.recognizer)
            with self.assertRaises(ValueError):load_gallery(root,True,self.detector,self.recognizer)
            cv2.imwrite(str(folder/'front.jpg'),np.zeros((100,100,3),np.uint8))
            gallery=load_gallery(root,True,self.detector,self.recognizer)
            self.assertEqual(gallery['Rahul'].shape,(1,128))
            (folder/'broken.jpg').write_bytes(b'not an image')
            with self.assertRaisesRegex(ValueError,'broken.jpg'):load_gallery(root,True,self.detector,self.recognizer)

    def test_session_cannot_start_without_enrollment(self):
        session=DemoSession()
        with self.assertRaisesRegex(ValueError,'Import'):session.start({'mode':'browser'})


if __name__=='__main__':unittest.main()
