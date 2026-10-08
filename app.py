"""Local desktop application. Launch with start.bat; no browser or cloud needed."""
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from vision.counting import LineCounter
from vision.models import ROOT
from vision.pipeline import Config, annotate, run


class App:
    def __init__(self, root):
        self.root = root
        root.title("Maggpie | Face Detection & Footfall")
        root.geometry("1200x800")
        root.minsize(1000, 720)
        root.configure(bg="#101820")
        self.worker = None
        self.stop = threading.Event()
        self.frames = queue.Queue(maxsize=1)
        self.messages = queue.Queue()
        self.original = None
        self.last_frame = None
        self.closing = False
        self.output_folder = ROOT / "output"
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#101820")
        style.configure("TLabel", background="#101820", foreground="#dce5eb", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"), foreground="#ffffff")
        style.configure("Value.TLabel", font=("Segoe UI", 25, "bold"), foreground="#66dfc1")
        style.configure("Muted.TLabel", foreground="#91a5b5", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 10), padding=8)
        style.configure("TCheckbutton", background="#101820", foreground="#dce5eb")
        style.configure("TScale", background="#101820")

        outer = ttk.Frame(root, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="MAGGPIE  /  Vision", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="LOCAL PROTOTYPE     Face detection + physical IN / OUT counting", style="Muted.TLabel").pack(anchor="w", pady=(5, 18))
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        settings = ttk.Frame(body, width=285)
        settings.pack(side="left", fill="y", padx=(0, 22))
        settings.pack_propagate(False)
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        self.mode = tk.StringVar(value="Video file")
        self.source = tk.StringVar()
        self.axis = tk.StringVar(value="horizontal")
        self.position = tk.DoubleVar(value=50)
        self.direction = tk.StringVar(value="Down / Right")
        self.person_threshold = tk.StringVar(value="0.40")
        self.face_threshold = tk.StringVar(value="0.80")
        self.controls = []

        def label(text):
            ttk.Label(settings, text=text).pack(anchor="w", pady=(12, 5))

        def combo(variable, values):
            widget = ttk.Combobox(settings, textvariable=variable, values=values, state="readonly")
            widget.pack(fill="x")
            self.controls.append((widget, "readonly"))
            return widget

        label("1  Choose input")
        mode = combo(self.mode, ["Video file", "Webcam", "Camera stream"])
        mode.bind("<<ComboboxSelected>>", self.change_mode)
        self.source_entry = ttk.Entry(settings, textvariable=self.source)
        self.source_entry.pack(fill="x", pady=8)
        self.controls.append((self.source_entry, "normal"))
        self.browse = ttk.Button(settings, text="Browse video…", command=self.browse_video)
        self.browse.pack(fill="x")
        self.controls.append((self.browse, "normal"))
        self.source_hint = tk.StringVar(value="Choose an exported CCTV video to test first.")
        ttk.Label(settings, textvariable=self.source_hint, wraplength=275, style="Muted.TLabel").pack(anchor="w", pady=6)

        label("2  Place the entrance line")
        axis = combo(self.axis, ["horizontal", "vertical"])
        axis.bind("<<ComboboxSelected>>", self.refresh_still)
        self.position_text = tk.StringVar(value="Position: 50%")
        ttk.Label(settings, textvariable=self.position_text, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
        slider = ttk.Scale(settings, from_=10, to=90, variable=self.position, command=self.refresh_still)
        slider.pack(fill="x")
        self.controls.append((slider, "normal"))
        label("IN direction")
        direction = combo(self.direction, ["Down / Right", "Up / Left"])
        direction.bind("<<ComboboxSelected>>", self.refresh_still)
        ttk.Label(settings, text="Yellow arrow = IN. Green dot = person's feet. Both sides of the line must be visible.", wraplength=275, style="Muted.TLabel").pack(anchor="w", pady=8)

        label("3  Detection thresholds")
        for title, variable in [("Person", self.person_threshold), ("Face", self.face_threshold)]:
            row = ttk.Frame(settings)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=title).pack(side="left")
            entry = ttk.Entry(row, textvariable=variable, width=10)
            entry.pack(side="right")
            self.controls.append((entry, "normal"))
        self.start_button = ttk.Button(settings, text="Start counting", command=self.start)
        self.start_button.pack(fill="x", pady=(18, 6))
        self.stop_button = ttk.Button(settings, text="Stop", command=self.request_stop, state="disabled")
        self.stop_button.pack(fill="x")
        ttk.Button(settings, text="Open saved results", command=self.open_output).pack(fill="x", pady=8)

        cards = ttk.Frame(right)
        cards.pack(fill="x", pady=(0, 12))
        self.values = {}
        for name, key in [("ENTRIES", "entries"), ("EXITS", "exits"), ("FACES NOW", "faces_now"), ("NET IN − OUT", "net_flow")]:
            card = ttk.Frame(cards)
            card.pack(side="left", expand=True, fill="x")
            value = tk.StringVar(value="0")
            self.values[key] = value
            ttk.Label(card, textvariable=value, style="Value.TLabel").pack(anchor="w")
            ttk.Label(card, text=name, style="Muted.TLabel").pack(anchor="w")
        self.preview = tk.Label(right, text="Choose a video, or select a webcam and press Start.\n\nGreen = person   •   Blue = face   •   Yellow = counting line",
                                bg="#17242f", fg="#91a5b5", font=("Segoe UI", 12), anchor="center")
        self.preview.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="Ready. Processing stays on this PC.")
        ttk.Label(right, textvariable=self.status, wraplength=790).pack(anchor="w", pady=(12, 6))
        self.last_event = tk.StringVar(value="No crossings yet.")
        ttk.Label(right, textvariable=self.last_event, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(right, text="Counts people crossings, including staff and repeat visits. No face recognition or family grouping.\nNet flow is not verified occupancy. Only event CSV + summary are saved; no video or face images.",
                  wraplength=790, style="Muted.TLabel").pack(anchor="w", pady=(10, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(80, self.poll)

    def change_mode(self, _=None):
        self.source.set("0" if self.mode.get() == "Webcam" else "")
        self.source_entry.configure(show="*" if self.mode.get() == "Camera stream" else "")
        self.browse.configure(state="normal" if self.mode.get() == "Video file" else "disabled")
        self.source_hint.set({"Video file": "Choose an exported CCTV video to test first.",
                              "Webcam": "Camera index: usually 0. Camera opens only after Start.",
                              "Camera stream": "Enter an authorized RTSP/HTTP stream. Address is hidden and not saved."}[self.mode.get()])
        self.original = None

    def browse_video(self):
        name = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv *.webm"), ("All files", "*.*")])
        if not name:
            return
        self.source.set(name)
        capture = cv2.VideoCapture(name)
        try:
            ok, frame = capture.read()
        finally:
            capture.release()
        if ok:
            self.original = frame
            self.refresh_still()
        else:
            messagebox.showerror("Video preview", "Could not decode the selected video.")

    def refresh_still(self, _=None):
        self.position_text.set(f"Position: {self.position.get():.0f}%")
        if self.original is not None and not (self.worker and self.worker.is_alive()):
            counter = LineCounter(self.axis.get(), self.position.get() / 100, self.direction.get() == "Down / Right")
            frame = annotate(self.original.copy(), [], [], counter, {"processing_fps": 0})
            self.show_frame(frame)

    def show_frame(self, frame):
        self.last_frame = frame
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image.thumbnail((max(320, self.preview.winfo_width()), max(240, self.preview.winfo_height())))
        self.photo = ImageTk.PhotoImage(image)
        self.preview.configure(image=self.photo, text="")

    def start(self):
        try:
            config = Config(self.source.get().strip(), self.axis.get(), self.position.get() / 100,
                            self.direction.get() == "Down / Right", float(self.person_threshold.get()),
                            float(self.face_threshold.get()))
            config.validate()
        except ValueError as exc:
            messagebox.showerror("Check settings", str(exc))
            return
        self.stop.clear()
        for value in self.values.values():
            value.set("0")
        self.last_event.set("No crossings yet.")
        self.status.set("Loading models and opening input…")
        for widget, _ in self.controls:
            widget.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.worker = threading.Thread(target=self.work, args=(config,), daemon=True)
        self.worker.start()

    def work(self, config):
        last_event = "No crossings yet."

        def update(frame, stats, events):
            nonlocal last_event
            if events:
                event = events[-1]
                last_event = f"Last crossing: Person {event['track_id']} → {event['direction']} at {event['source_seconds']:.1f}s"
            try:
                self.frames.get_nowait()
            except queue.Empty:
                pass
            self.frames.put_nowait((frame, stats, last_event))

        try:
            self.messages.put(("done", run(config, update, self.stop)))
        except (ValueError, RuntimeError) as exc:
            self.messages.put(("error", str(exc)))
        except Exception:
            # Do not surface exception payloads that might contain a secret URL.
            self.messages.put(("error", "Processing failed. Check model setup, input codec and write access."))

    def request_stop(self):
        self.stop.set()
        self.stop_button.configure(state="disabled")
        self.status.set("Stopping and saving results… A network read may take a few seconds.")

    def poll(self):
        try:
            frame, stats, event = self.frames.get_nowait()
            self.show_frame(frame)
            for key, value in self.values.items():
                value.set(str(stats[key]))
            self.last_event.set(event)
            self.status.set(f"Processing · {stats['processing_fps']:.1f} FPS · {stats['frames']} frames · Source {stats['source_seconds']:.1f}s")
        except queue.Empty:
            pass
        try:
            kind, value = self.messages.get_nowait()
            if kind == "done":
                self.output_folder = Path(value["output_folder"])
                self.status.set(f"{value['status'].replace('_', ' ').capitalize()} · Saved in output/{self.output_folder.name}")
            else:
                self.status.set(value)
            for widget, state in self.controls:
                widget.configure(state=state)
            if self.mode.get() != "Video file":
                self.browse.configure(state="disabled")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
        except queue.Empty:
            pass
        if self.closing and not (self.worker and self.worker.is_alive()):
            self.root.destroy()
            return
        self.root.after(80, self.poll)

    def open_output(self):
        self.output_folder.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(self.output_folder)
        else:
            messagebox.showinfo("Saved results", str(self.output_folder))

    def close(self):
        self.closing = True
        self.request_stop()
        if not (self.worker and self.worker.is_alive()):
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
