import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ai_core import StudyBehaviorDetector
from auth import AuthError, AuthService
from db import Database
from network_utils import (NetworkError, DownloadError, check_url,
                           check_urls_batch, download_image_from_url,
                           test_connectivity)
from visualization import export_alert_chart


class LoginFrame(ttk.Frame):
    def __init__(self, master, auth_service, on_login):
        super().__init__(master, padding=24)
        self.auth = auth_service
        self.on_login = on_login
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()

        ttk.Label(self, text="Study Behavior Monitor", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 18)
        )
        ttk.Label(self, text="Username").grid(row=1, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.username_var, width=28).grid(
            row=1, column=1, sticky="ew", pady=4
        )
        ttk.Label(self, text="Password").grid(row=2, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.password_var, show="*", width=28).grid(
            row=2, column=1, sticky="ew", pady=4
        )
        ttk.Button(self, text="Login", command=self.login).grid(
            row=3, column=0, sticky="ew", pady=(12, 0)
        )
        ttk.Button(self, text="Register", command=self.register).grid(
            row=3, column=1, sticky="ew", pady=(12, 0), padx=(8, 0)
        )
        ttk.Label(
            self,
            text="Default admin: admin / admin123",
            foreground="#555",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.columnconfigure(1, weight=1)

    def login(self):
        try:
            user = self.auth.login(self.username_var.get(), self.password_var.get())
        except AuthError as exc:
            messagebox.showerror("Login failed", str(exc))
            return
        self.on_login(user)

    def register(self):
        try:
            user = self.auth.register(self.username_var.get(), self.password_var.get())
        except AuthError as exc:
            messagebox.showerror("Register failed", str(exc))
            return
        messagebox.showinfo("Registered", f"User {user['username']} has been created.")


class MainFrame(ttk.Frame):
    def __init__(self, master, database, auth_service, user):
        super().__init__(master, padding=18)
        self.db = database
        self.auth = auth_service
        self.user = user
        self.detector = StudyBehaviorDetector()
        self.status_var = tk.StringVar(value="Ready")
        self.running = False

        title = f"Logged in as {user['username']} ({user['role']})"
        ttk.Label(self, text=title, font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )
        # Row 1: AI detection
        ttk.Button(self, text="Detect Image", command=self.detect_image).grid(
            row=1, column=0, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Detect from URL", command=self.detect_from_url).grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Start Camera", command=self.start_camera).grid(
            row=1, column=2, sticky="ew", pady=4
        )
        # Row 2: network tools
        ttk.Button(self, text="Check Model URL", command=self.check_model_url).grid(
            row=2, column=0, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Batch URL Check", command=self.batch_url_check).grid(
            row=2, column=1, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Network Test", command=self.network_test).grid(
            row=2, column=2, sticky="ew", pady=4
        )
        # Row 3: data & records
        ttk.Button(self, text="Detection Records", command=self.show_records).grid(
            row=3, column=0, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Operation Logs", command=self.show_logs).grid(
            row=3, column=1, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Export Chart", command=self.export_chart).grid(
            row=3, column=2, sticky="ew", pady=4
        )
        # Row 4: account
        ttk.Button(self, text="Change Password", command=self.change_password).grid(
            row=4, column=0, sticky="ew", padx=(0, 8), pady=4
        )

        if self.auth.is_admin(self.user):
            ttk.Button(self, text="Manage Users", command=self.manage_users).grid(
                row=4, column=1, sticky="ew", padx=(0, 8), pady=4
            )

        ttk.Label(self, textvariable=self.status_var, foreground="#444").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(16, 0)
        )
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=200)
        self.progress.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.progress.grid_remove()
        for column in range(3):
            self.columnconfigure(column, weight=1)

    def detect_image(self):
        path = filedialog.askopenfilename(
            title="Choose image",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._run_task(lambda: self._detect_image_worker(path), "Detecting image...")

    def _detect_image_worker(self, path):
        output_path, events, summary = self.detector.predict_image(path)
        alerts = summary.get("alert_labels", [])
        self.db.record_detection(
            self.user["id"], str(path), summary, alerts, output_path=output_path
        )
        self.db.log_operation(
            self.user["id"], "detect_image", f"{Path(path).name} -> {output_path.name}"
        )
        message = (
            f"Output: {output_path}\n"
            f"Events: {len(events)}\n"
            f"Alerts: {', '.join(alerts) if alerts else 'none'}"
        )
        self.after(0, lambda: messagebox.showinfo("Detection finished", message))

    def start_camera(self):
        if self.running:
            messagebox.showinfo("Camera", "Camera detection is already running.")
            return
        source = simpledialog.askstring(
            "Camera source",
            "Input camera index or video path:",
            initialvalue="0",
            parent=self,
        )
        if source is None:
            return
        try:
            source_value = int(source)
        except ValueError:
            source_value = source
        self._run_task(lambda: self._camera_worker(source_value), "Camera running...")

    def _camera_worker(self, source):
        self.running = True
        self.db.log_operation(self.user["id"], "start_camera", str(source))
        try:
            self.detector.run_camera(source)
        finally:
            self.running = False
            self.db.log_operation(self.user["id"], "stop_camera", str(source))

    def check_model_url(self):
        url = simpledialog.askstring(
            "Model URL",
            "Input a model or dataset URL to check:",
            parent=self,
        )
        if not url:
            return
        self._run_task(lambda: self._check_url_worker(url), "Checking network...")

    def _check_url_worker(self, url):
        try:
            result = check_url(url)
            detail = json.dumps(result, ensure_ascii=False)
            self.db.upsert_model_resource("remote_check", url, None, "reachable")
            self.db.log_operation(self.user["id"], "check_url", detail)
            self.after(0, lambda: messagebox.showinfo("Network", detail))
        except NetworkError as exc:
            self.db.upsert_model_resource("remote_check", url, None, "failed")
            self.db.log_operation(self.user["id"], "check_url_failed", str(exc))
            self.after(0, lambda: messagebox.showerror("Network failed", str(exc)))

    def network_test(self):
        self._run_task(self._network_test_worker, "Testing connectivity...")

    def _network_test_worker(self):
        result = test_connectivity()
        self.db.log_operation(self.user["id"], "network_test", json.dumps(result))
        if result["reachable"]:
            msg = (f"Network reachable\n"
                   f"Latency: {result['latency_ms']} ms\n"
                   f"Resolved IP: {result['resolved_ip']}")
            self.after(0, lambda: messagebox.showinfo("Network Test", msg))
        else:
            self.after(0, lambda: messagebox.showerror(
                "Network Test", f"Not reachable: {result.get('error', 'unknown')}"))

    def detect_from_url(self):
        url = simpledialog.askstring(
            "Detect from URL",
            "Input an image URL:",
            parent=self,
        )
        if not url:
            return
        self._run_task(lambda: self._detect_url_worker(url), "Downloading & detecting...")

    def _detect_url_worker(self, url):
        try:
            local_path = download_image_from_url(url)
        except DownloadError as exc:
            self.after(0, lambda: messagebox.showerror("Download failed", str(exc)))
            return
        output_path, events, summary = self.detector.predict_image(str(local_path))
        alerts = summary.get("alert_labels", [])
        self.db.record_detection(
            self.user["id"], url, summary, alerts, output_path=output_path
        )
        self.db.log_operation(
            self.user["id"], "detect_url", f"{url} -> {output_path}"
        )
        message = (
            f"Source URL: {url}\n"
            f"Output: {output_path}\n"
            f"Events: {len(events)}\n"
            f"Alerts: {', '.join(alerts) if alerts else 'none'}"
        )
        self.after(0, lambda: messagebox.showinfo("Detection finished", message))

    def batch_url_check(self):
        text = simpledialog.askstring(
            "Batch URL Check",
            "Input URLs to check (one per line or comma-separated):",
            parent=self,
        )
        if not text:
            return
        urls = [u.strip() for line in text.splitlines() for u in line.split(",")
                if u.strip()]
        if not urls:
            return
        self._run_task(lambda: self._batch_url_worker(urls), "Checking URLs...")

    def _batch_url_worker(self, urls):
        results = check_urls_batch(urls)
        self.db.log_operation(
            self.user["id"], "batch_url_check", f"Checked {len(urls)} URLs"
        )
        lines = []
        for url, result in results.items():
            status = "OK" if result.get("ok") else "FAIL"
            detail = result.get("error", result.get("status", ""))
            lines.append(f"[{status}] {url}  {detail}")
        self.after(0, lambda: self._show_text("Batch URL Results", "\n".join(lines)))

    def show_records(self):
        records = self.db.list_detection_records()
        lines = []
        for record in records:
            lines.append(
                f"#{record['id']} {record['created_at']} {record['username'] or '-'}\n"
                f"source: {record['source']}\n"
                f"alerts: {record['alerts_json']}\n"
                f"output: {record['output_path'] or '-'}\n"
            )
        self._show_text("Detection Records", "\n".join(lines) or "No records.")

    def show_logs(self):
        logs = self.db.list_operation_logs()
        lines = [
            f"#{item['id']} {item['created_at']} {item['username'] or '-'} "
            f"{item['action']} {item['detail'] or ''}"
            for item in logs
        ]
        self._show_text("Operation Logs", "\n".join(lines) or "No logs.")

    def export_chart(self):
        target = filedialog.asksaveasfilename(
            title="Save chart",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
        )
        if not target:
            return
        try:
            output = export_alert_chart(self.db.list_detection_records(), target)
        except RuntimeError as exc:
            messagebox.showerror("Chart failed", str(exc))
            return
        self.db.log_operation(self.user["id"], "export_chart", str(output))
        messagebox.showinfo("Chart exported", str(output))

    def change_password(self):
        old_password = simpledialog.askstring(
            "Old password", "Input old password:", parent=self, show="*"
        )
        if old_password is None:
            return
        new_password = simpledialog.askstring(
            "New password", "Input new password:", parent=self, show="*"
        )
        if not new_password:
            return
        try:
            self.auth.change_password(
                self.user["username"], old_password, new_password, operator=self.user
            )
        except AuthError as exc:
            messagebox.showerror("Change failed", str(exc))
            return
        messagebox.showinfo("Password", "Password changed.")

    def manage_users(self):
        users = self.auth.list_users(self.user)
        lines = [
            f"#{item['id']} {item['username']} ({item['role']}) {item['created_at']}"
            for item in users
        ]
        if messagebox.askyesno(
            "Users",
            "\n".join(lines) + "\n\nDelete a normal user?",
        ):
            username = simpledialog.askstring(
                "Delete user", "Input username to delete:", parent=self
            )
            if username:
                try:
                    affected = self.auth.delete_user(username, self.user)
                except AuthError as exc:
                    messagebox.showerror("Delete failed", str(exc))
                    return
                messagebox.showinfo("Delete user", f"Deleted rows: {affected}")

    def _run_task(self, target, status):
        self.status_var.set(status)
        self.progress.grid()
        self.progress.start(10)

        def runner():
            try:
                target()
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Error", str(exc)))
            finally:
                self.after(0, lambda: self._task_done(status))

        threading.Thread(target=runner, daemon=True).start()

    def _task_done(self, status):
        self.progress.stop()
        self.progress.grid_remove()
        self.status_var.set("Ready")

    def _show_text(self, title, text):
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry("760x480")
        text_widget = tk.Text(window, wrap="word")
        text_widget.insert("1.0", text)
        text_widget.configure(state="disabled")
        text_widget.pack(fill="both", expand=True, padx=10, pady=10)


class StudyMonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Study Behavior Monitor")
        self.geometry("720x440")
        self.minsize(640, 400)

        self.db = Database()
        self.auth = AuthService(self.db)
        self.auth.ensure_default_admin()
        self.current_frame = None
        self.show_login()

    def show_login(self):
        if self.current_frame:
            self.current_frame.destroy()
        self.current_frame = LoginFrame(self, self.auth, self.show_main)
        self.current_frame.pack(fill="both", expand=True)

    def show_main(self, user):
        if self.current_frame:
            self.current_frame.destroy()
        self.current_frame = MainFrame(self, self.db, self.auth, user)
        self.current_frame.pack(fill="both", expand=True)


def main():
    app = StudyMonitorApp()
    app.mainloop()
