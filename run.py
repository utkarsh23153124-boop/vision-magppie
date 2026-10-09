"""Headless/video-preview entry point. Desktop UI: python app.py."""
import argparse
import json
import os
from pathlib import Path
import threading

from vision.pipeline import Config, run


def main():
    try:
        from central.env import load_env
        load_env()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Maggpie face detection + physical footfall counter")
    parser.add_argument("--source", default=os.environ.get("MAGGPIE_SOURCE", ""), help="Video path or webcam index. For secret URLs use MAGGPIE_SOURCE or the desktop app.")
    parser.add_argument("--axis", choices=["horizontal", "vertical"], default="horizontal")
    parser.add_argument("--position", type=float, default=0.5, help="Line position as fraction of frame, 0.1–0.9")
    parser.add_argument("--reverse", action="store_true", help="IN means upward/leftward instead of downward/rightward")
    parser.add_argument("--person-threshold", type=float, default=0.4)
    parser.add_argument("--face-threshold", type=float, default=0.8)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--preview", action="store_true", help="Show processed video; Q stops")
    args = parser.parse_args()
    config = Config(args.source, args.axis, args.position, not args.reverse,
                    args.person_threshold, args.face_threshold, args.output, args.max_frames)
    stop = threading.Event()

    def display(frame, stats, events):
        import cv2
        cv2.imshow("Maggpie - Q to stop", frame)
        if cv2.waitKey(1) & 0xFF == ord("q") or cv2.getWindowProperty("Maggpie - Q to stop", cv2.WND_PROP_VISIBLE) < 1:
            stop.set()

    try:
        result = run(config, display if args.preview else None, stop)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] in ("completed", "stopped", "frame_limit") else 1
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Stopped. Any processed events are saved in output/.")
        return 130
    except Exception:
        print("Processing failed. Check model setup, input codec and write access; saved events remain in output/.")
        return 1
    finally:
        if args.preview:
            import cv2
            cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
