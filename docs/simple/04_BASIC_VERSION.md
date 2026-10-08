# Basic version — ready for footage testing

- Start: double-click `start.bat` in the main folder.
- New PC: Python 3.12 install karke pehle `setup.bat` run karo.
- Input: video file, webcam, ya authorized RTSP/HTTP camera stream.
- Face detection: visible faces par blue boxes.
- Footfall: entrance line cross karne par individual IN / OUT count.
- Video choose karke line position aur IN direction set karo, phir Start.
- Output: `output/<session>/events.csv` aur `summary.json`.
- Stop ke baad new Start = new counting session.

Abhi staff exclusion, family grouping aur same-day unique-client matching nahi hai. Staff/repeat entries bhi count hongi. Net IN-OUT verified occupancy nahi hai.

CPU-first prototype hai; showroom footage aur actual PC par accuracy/speed validate karni hai.
