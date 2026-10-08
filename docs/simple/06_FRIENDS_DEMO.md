# Friends demo — 3 steps

1. Create folders in `demo_photos` with your friends' names. Put 3–5 clear portraits
   in each (1 minimum). Everyone should agree to the demo.
2. Open `start_demo.bat`. On the page, confirm consent and click **Import photos**.
   Fix any photo errors shown. After restarting the server, import again.
3. Click **Start counting**, allow webcam access in Chrome, and test one person
   at a time. Look at the camera until your name appears, then walk slowly across
   the vertical line. Unknown people should also walk across it.

- Name = registered friend. Unknown = no confident match. Checking = confirming.
- Registered friend matched at crossing: staff-excluded counter increases.
- Other crossing: Visitor IN or OUT increases. Each Start resets all counts.
- No photo uploads to the cloud. Your original photos remain in demo_photos;
  imported face templates remain only in server memory. Remove originals yourself
  when no longer needed. Names/images are not written to crossing reports.
- Face visibility and full-person tracking matter. Ten people sequentially is the
  intended rehearsal; ten overlapping people is not validated. No liveness check.
- This is a separate laptop demo. The central deployment plan remains unchanged.
- New machine or missing models: run `setup_demo.bat` with internet first.
