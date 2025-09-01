from __future__ import annotations

import asyncio
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import time
from tkinter.scrolledtext import ScrolledText

 

from app.core.downloader import download_site


DEFAULT_ROOT = Path(r"e:\\Sites\\")
DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HTTrack Clone - Desktop (Tkinter)")
        self.geometry("900x650")

        # Styles
        self.style = ttk.Style(self)
        self.style.configure("Status.TLabel", font=("", 9))
        self.style.configure("StatusError.TLabel", foreground="#c62828")
        self.style.configure("StatusOk.TLabel", foreground="#2e7d32")
        # Green progressbar style (may vary by theme/OS)
        self.style.configure("Green.Horizontal.TProgressbar", background="#2ecc71")

        self.product_var = tk.StringVar(value="Aqua Vital Filter")
        self.url_var = tk.StringVar(value="https://offer.buyaquavitalfilter.com/offer/1/index-v1-dtcv3.php?C1=1573&uid=14773&oid=1573&affid=1267&AFFID=1267&utm_campaign=CPA_1267&utm_source=1267")
        self.root_var = tk.StringVar(value=str(DEFAULT_ROOT))

        self._last_folder: Path | None = None
        self._worker: threading.Thread | None = None
        self._timer_job: str | None = None
        self._start_ts: float | None = None
        self._progress_stage: str | None = None
        self._progress_total: int = 0
        self._progress_done: int = 0
        self._cancel_requested: bool = False
        self.preview_var = tk.BooleanVar(value=False)
        self.insecure_ssl_var = tk.BooleanVar(value=True)  # default to ignore for testing today
        # Per-asset UI state
        self._asset_rows: dict[tuple[str, str], dict] = {}
        self._asset_cancel_flags: set[tuple[str, str]] = set()

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True)

        # Product name
        ttk.Label(frm, text="Product Name").grid(row=0, column=0, sticky=tk.W, **pad)
        self.entry_product = ttk.Entry(frm, textvariable=self.product_var, width=60)
        self.entry_product.grid(row=0, column=1, columnspan=2, sticky=tk.EW, **pad)

        # URL
        ttk.Label(frm, text="URL to clone").grid(row=1, column=0, sticky=tk.W, **pad)
        self.entry_url = ttk.Entry(frm, textvariable=self.url_var, width=60)
        self.entry_url.grid(row=1, column=1, columnspan=2, sticky=tk.EW, **pad)

        # Download root
        ttk.Label(frm, text="Download location").grid(row=2, column=0, sticky=tk.W, **pad)
        self.entry_root = ttk.Entry(frm, textvariable=self.root_var, width=60)
        self.entry_root.grid(row=2, column=1, sticky=tk.EW, **pad)
        ttk.Button(frm, text="Browse...", command=self._browse).grid(row=2, column=2, sticky=tk.W, **pad)

        # Buttons
        self.btn_cancel = ttk.Button(frm, text="Cancel", command=self._cancel_download, state=tk.DISABLED)
        self.btn_cancel.grid(row=3, column=0, sticky=tk.W, **pad)
        self.btn_download = ttk.Button(frm, text="Download", command=self._start_download)
        self.btn_download.grid(row=3, column=1, sticky=tk.W, **pad)
        
        self.chk_preview = ttk.Checkbutton(frm, text="Preview (1 per type)", variable=self.preview_var)
        self.chk_preview.grid(row=3, column=3, sticky=tk.W, **pad)
        self.chk_insecure = ttk.Checkbutton(frm, text="Ignore SSL errors (insecure)", variable=self.insecure_ssl_var)
        self.chk_insecure.grid(row=3, column=4, sticky=tk.W, **pad)

        # Status
        self.status_var = tk.StringVar(value="Ready.")
        self.status = ttk.Label(frm, textvariable=self.status_var, style="Status.TLabel")
        self.status.grid(row=4, column=0, columnspan=5, sticky=tk.W, **pad)

        # Progress bar and elapsed timer
        self.progress = ttk.Progressbar(frm, mode="indeterminate", style="Green.Horizontal.TProgressbar")
        self.progress.grid(row=5, column=0, columnspan=5, sticky=tk.EW, **pad)
        self.elapsed_var = tk.StringVar(value="")
        self.elapsed = ttk.Label(frm, textvariable=self.elapsed_var)
        self.elapsed.grid(row=6, column=0, columnspan=5, sticky=tk.W, **pad)

        # Separator
        ttk.Separator(frm, orient="horizontal").grid(row=7, column=0, columnspan=5, sticky=tk.EW, padx=10)

        # Asset transfers (scrollable list)
        ttk.Label(frm, text="Asset Transfers").grid(row=8, column=0, sticky=tk.W, **pad)
        self.assets_canvas = tk.Canvas(frm, height=180)
        self.assets_canvas.grid(row=9, column=0, columnspan=4, sticky=tk.NSEW, **pad)
        self.assets_scroll = ttk.Scrollbar(frm, orient="vertical", command=self.assets_canvas.yview)
        self.assets_scroll.grid(row=9, column=4, sticky=tk.NS, padx=(0, 10))
        self.assets_canvas.configure(yscrollcommand=self.assets_scroll.set)
        self.assets_frame = ttk.Frame(self.assets_canvas)
        self.assets_window = self.assets_canvas.create_window((0, 0), window=self.assets_frame, anchor="nw")
        def _on_assets_configure(event):
            try:
                self.assets_canvas.configure(scrollregion=self.assets_canvas.bbox("all"))
                # Make inner frame width follow canvas
                self.assets_canvas.itemconfigure(self.assets_window, width=self.assets_canvas.winfo_width())
            except Exception:
                pass
        self.assets_frame.bind("<Configure>", _on_assets_configure)

        # Separator
        ttk.Separator(frm, orient="horizontal").grid(row=10, column=0, columnspan=5, sticky=tk.EW, padx=10)

        # Logs
        ttk.Label(frm, text="Logs").grid(row=11, column=0, sticky=tk.W, **pad)
        self.log = ScrolledText(frm, height=10, state="disabled")
        self.log.grid(row=12, column=0, columnspan=5, sticky=tk.NSEW, **pad)

        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(2, weight=1)
        frm.columnconfigure(3, weight=1)
        frm.rowconfigure(9, weight=1)   # assets area grows
        frm.rowconfigure(12, weight=1)  # logs area grows

    def _browse(self):
        selected = filedialog.askdirectory(initialdir=str(DEFAULT_ROOT))
        if selected:
            self.root_var.set(selected)

    def _start_download(self):
        product = self.product_var.get().strip()
        url = self.url_var.get().strip()
        root = Path(self.root_var.get().strip())
        preview = bool(self.preview_var.get())
        verify_ssl = not bool(self.insecure_ssl_var.get())

        if not product or not url:
            messagebox.showerror("Error", "Please enter Product Name and URL.")
            return

        try:
            root.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot create/access folder:\n{root}\n\n{e}")
            return

        # Disable UI during download
        self.btn_download.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        self._cancel_requested = False
        self.status_var.set("Downloading... This may take a while.")
        try:
            self.status.configure(style="Status.TLabel")
        except Exception:
            pass
        self.progress.start(10)
        self._start_timer()
        self._clear_log()
        self._clear_assets()
        self._asset_cancel_flags.clear()
        start_line = f"Starting job: product='{product}', url='{url}' -> root='{root}'"
        if preview:
            start_line += " [PREVIEW]"
        self._append_log(start_line)

        def _worker():
            try:
                # Progress callback from worker thread; marshal to UI thread via after()
                def progress_cb(done: int, total: int, stage: str):
                    self.after(0, lambda d=done, t=total, s=stage: self._on_progress(d, t, s))

                def log_cb(msg: str):
                    self.after(0, lambda m=msg: self._append_log(m))

                def cancel_cb() -> bool:
                    return self._cancel_requested

                def asset_cb(event: str, kind: str, url: str, meta: dict):
                    # events: start/progress/done/error/cancelled
                    self.after(0, lambda ev=event, k=kind, u=url, m=meta: self._on_asset_event(ev, k, u, m))

                def asset_cancel_cb(kind: str, url: str) -> bool:
                    return (kind, url) in self._asset_cancel_flags

                result = asyncio.run(
                    download_site(
                        url=url,
                        product_name=product,
                        download_root=root,
                        use_render=False,
                        progress_cb=progress_cb,
                        log_cb=log_cb,
                        cancel_cb=cancel_cb,
                        asset_cb=asset_cb,
                        asset_cancel_cb=asset_cancel_cb,
                        limit_per_type=1 if preview else None,
                        limit_css_refs=1 if preview else None,
                        verify_ssl=verify_ssl,
                    )
                )
                self._last_folder = result.folder
                msg = f"Done. Saved index.html and local-index.html to: {result.folder}"
                self.after(0, lambda: self._on_download_done(msg))
            except asyncio.CancelledError:
                self.after(0, self._on_cancelled)
            except Exception as e:
                self.after(0, lambda err=e: self._on_download_error(err))

        self._worker = threading.Thread(target=_worker, daemon=True)
        self._worker.start()

    def _on_download_done(self, message: str):
        self.status_var.set(message)
        try:
            self.status.configure(style="StatusOk.TLabel")
        except Exception:
            pass
        self.progress.stop()
        self._stop_timer()
        self.btn_download.config(state=tk.NORMAL)
        self.btn_cancel.config(state=tk.DISABLED)
        self._cancel_requested = False
        # Reset progress bar for next run
        try:
            self.progress.config(mode="indeterminate", value=0)
        except Exception:
            pass

    def _on_download_error(self, e: Exception):
        self.status_var.set("Error during download.")
        try:
            self.status.configure(style="StatusError.TLabel")
        except Exception:
            pass
        self.progress.stop()
        self._stop_timer()
        self.btn_download.config(state=tk.NORMAL)
        messagebox.showerror("Download failed", str(e))
        self.btn_cancel.config(state=tk.DISABLED)
        self._cancel_requested = False
        # Reset progress bar for next run
        try:
            self.progress.config(mode="indeterminate", value=0)
        except Exception:
            pass

    def _on_asset_event(self, event: str, kind: str, url: str, meta: dict):
        key = (kind, url)
        row = self._asset_rows.get(key)
        if event == "start":
            if row is not None:
                return
            # Build a row: kind, url, progress bar, cancel button
            row_frm = ttk.Frame(self.assets_frame)
            row_frm.pack(fill=tk.X, padx=4, pady=2)
            lbl_kind = ttk.Label(row_frm, text=f"[{kind}]", width=6)
            lbl_kind.pack(side=tk.LEFT)
            lbl_url = ttk.Label(row_frm, text=url, width=60)
            lbl_url.pack(side=tk.LEFT, padx=(6, 6))
            total = meta.get("total") if isinstance(meta, dict) else None
            pb = ttk.Progressbar(row_frm, style="Green.Horizontal.TProgressbar")
            if total and isinstance(total, int) and total > 0:
                pb.config(mode="determinate", maximum=total, value=0)
            else:
                pb.config(mode="indeterminate")
                try:
                    pb.start(15)
                except Exception:
                    pass
            pb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
            btn = ttk.Button(row_frm, text="Cancel", command=lambda k=kind, u=url: self._asset_cancel(k, u))
            btn.pack(side=tk.RIGHT)
            self._asset_rows[key] = {"frame": row_frm, "pb": pb, "btn": btn, "total": (total or 0), "read": 0}
        elif event == "progress":
            if row is None:
                # initialize if missing
                self._on_asset_event("start", kind, url, meta)
                row = self._asset_rows.get(key)
            if not row:
                return
            total = meta.get("total") if isinstance(meta, dict) else None
            read = meta.get("read") if isinstance(meta, dict) else None
            if total and isinstance(total, int) and total > 0:
                try:
                    row["pb"].stop()
                except Exception:
                    pass
                row["pb"].config(mode="determinate", maximum=total)
            if read and isinstance(read, int):
                try:
                    row["pb"]["value"] = read
                except Exception:
                    pass
        elif event in ("done", "error", "cancelled"):
            if row is None:
                return
            try:
                row["pb"].stop()
            except Exception:
                pass
            if event == "done":
                # fill bar if determinate
                try:
                    if str(row["pb"].cget("mode")) == "determinate":
                        row["pb"]["value"] = row["pb"].cget("maximum")
                except Exception:
                    pass
            # disable cancel button
            try:
                row["btn"].config(state=tk.DISABLED)
            except Exception:
                pass
            # annotate url label for status
            try:
                for child in row["frame"].winfo_children():
                    if isinstance(child, ttk.Label) and child.cget("text") == url:
                        suffix = {"done": "✓", "error": "✗", "cancelled": "✖"}[event]
                        child.config(text=f"{url}  {suffix}")
                        break
            except Exception:
                pass

    def _on_cancelled(self):
        self.status_var.set("Cancelled by user.")
        try:
            self.status.configure(style="Status.TLabel")
        except Exception:
            pass
        self.progress.stop()
        self._stop_timer()
        self.btn_download.config(state=tk.NORMAL)
        self.btn_cancel.config(state=tk.DISABLED)
        self._cancel_requested = False
        # Reset progress bar for next run
        try:
            self.progress.config(mode="indeterminate", value=0)
        except Exception:
            pass

    def _on_progress(self, done: int, total: int, stage: str):
        # Switch to determinate mode on first progress
        if str(self.progress.cget("mode")) != "determinate":
            try:
                self.progress.stop()
            except Exception:
                pass
            self.progress.config(mode="determinate", maximum=max(1, total), value=done)
        else:
            # If stage changes, reset maximum to new total
            if self._progress_stage != stage:
                self.progress.config(maximum=max(1, total))

        self._progress_stage = stage
        self._progress_total = max(0, total)
        self._progress_done = max(0, min(done, total))
        try:
            self.progress['value'] = self._progress_done
        except Exception:
            pass

        # Compute percent and ETA
        percent = 0
        if total > 0:
            percent = int((done / total) * 100)

        # Elapsed
        elapsed_s = 0
        if self._start_ts is not None:
            elapsed_s = int(time.perf_counter() - self._start_ts)
        hrs, rem = divmod(elapsed_s, 3600)
        mins, secs = divmod(rem, 60)
        elapsed_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"

        # ETA: naive proportional estimate
        eta_str = "--:--:--"
        if total > 0 and done > 0:
            remain = int(elapsed_s * (total / done - 1))
            rhrs, rrem = divmod(max(0, remain), 3600)
            rm_m, rm_s = divmod(rrem, 60)
            eta_str = f"{rhrs:02d}:{rm_m:02d}:{rm_s:02d}"

        self.elapsed_var.set(f"Stage: {stage} • {percent}% • Elapsed: {elapsed_str} • ETA: {eta_str}")

    def _start_timer(self):
        self._start_ts = time.perf_counter()
        self.elapsed_var.set("Elapsed: 00:00:00")
        self._schedule_timer_tick()

    def _schedule_timer_tick(self):
        if self._start_ts is None:
            return
        elapsed = int(time.perf_counter() - self._start_ts)
        hrs, rem = divmod(elapsed, 3600)
        mins, secs = divmod(rem, 60)
        mode = str(self.progress.cget("mode"))
        if mode == "determinate" and self._progress_total > 0:
            percent = int((self._progress_done / self._progress_total) * 100) if self._progress_done > 0 else 0
            # ETA recompute
            eta_str = "--:--:--"
            if self._progress_done > 0:
                remain = int(elapsed * (self._progress_total / self._progress_done - 1))
                rhrs, rrem = divmod(max(0, remain), 3600)
                rm_m, rm_s = divmod(rrem, 60)
                eta_str = f"{rhrs:02d}:{rm_m:02d}:{rm_s:02d}"
            self.elapsed_var.set(
                f"Stage: {self._progress_stage} • {percent}% • Elapsed: {hrs:02d}:{mins:02d}:{secs:02d} • ETA: {eta_str}"
            )
        else:
            self.elapsed_var.set(f"Elapsed: {hrs:02d}:{mins:02d}:{secs:02d}")
        self._timer_job = self.after(500, self._schedule_timer_tick)

    def _cancel_download(self):
        if not self._cancel_requested:
            self._cancel_requested = True
            self.btn_cancel.config(state=tk.DISABLED)
            self.status_var.set("Cancelling...")
            self._append_log("Cancellation requested by user.")

    def _asset_cancel(self, kind: str, url: str):
        key = (kind, url)
        self._asset_cancel_flags.add(key)
        row = self._asset_rows.get(key)
        if row:
            try:
                row["btn"].config(state=tk.DISABLED)
            except Exception:
                pass
            # annotate
            try:
                for child in row["frame"].winfo_children():
                    if isinstance(child, ttk.Label) and child.cget("text") == url:
                        child.config(text=f"{url}  (cancelling…)")
                        break
            except Exception:
                pass

    def _append_log(self, line: str):
        try:
            self.log.config(state="normal")
            self.log.insert(tk.END, line + "\n")
            self.log.see(tk.END)
            self.log.config(state="disabled")
        except Exception:
            pass

    def _clear_log(self):
        try:
            self.log.config(state="normal")
            self.log.delete("1.0", tk.END)
            self.log.config(state="disabled")
        except Exception:
            pass

    def _clear_assets(self):
        try:
            for child in list(self.assets_frame.winfo_children()):
                child.destroy()
            self._asset_rows.clear()
        except Exception:
            pass

    def _stop_timer(self):
        if self._timer_job:
            try:
                self.after_cancel(self._timer_job)
            except Exception:
                pass
            self._timer_job = None
        self._start_ts = None



if __name__ == "__main__":
    app = App()
    app.mainloop()
