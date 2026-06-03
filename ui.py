import csv
import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ai_core import StudyBehaviorDetector
from auth import AuthError, AuthService
from db import Database
from network_utils import NetworkError, check_url
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


class UserManagementWindow(tk.Toplevel):
    def __init__(self, parent, auth_service, current_user):
        super().__init__(parent)
        self.title("Manage Users - Table View")
        self.geometry("750x500")
        self.auth = auth_service
        self.current_user = current_user
        self.users = []
        self.row_frames = []

        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)

        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="Add User", command=self.add_user).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Refresh", command=self.load_users).pack(side="left", padx=5)

        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(header_frame, text="ID", width=5, anchor="center", relief="ridge").pack(side="left", padx=1)
        ttk.Label(header_frame, text="Username", width=15, anchor="center", relief="ridge").pack(side="left", padx=1)
        ttk.Label(header_frame, text="Role", width=10, anchor="center", relief="ridge").pack(side="left", padx=1)
        ttk.Label(header_frame, text="Created At", width=20, anchor="center", relief="ridge").pack(side="left", padx=1)
        ttk.Label(header_frame, text="Operations", width=20, anchor="center", relief="ridge").pack(side="left", padx=1)

        canvas = tk.Canvas(main_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.load_users()

    def load_users(self):
        for frame in self.row_frames:
            frame.destroy()
        self.row_frames.clear()

        self.users = self.auth.list_users(self.current_user)
        for user in self.users:
            row_frame = ttk.Frame(self.scrollable_frame)
            row_frame.pack(fill="x", pady=2)

            ttk.Label(row_frame, text=str(user["id"]), width=5, anchor="center", relief="sunken").pack(side="left", padx=1)
            ttk.Label(row_frame, text=user["username"], width=15, anchor="center", relief="sunken").pack(side="left", padx=1)
            role_var = tk.StringVar(value=user["role"])
            role_combo = ttk.Combobox(row_frame, textvariable=role_var, values=["user", "admin"], width=8, state="readonly" if self.auth.is_admin(self.current_user) else "disabled")
            role_combo.pack(side="left", padx=1)
            role_combo.bind("<<ComboboxSelected>>", lambda e, u=user, var=role_var: self.change_role(u["username"], var.get()))
            ttk.Label(row_frame, text=user["created_at"], width=20, anchor="center", relief="sunken").pack(side="left", padx=1)

            btn_frame = ttk.Frame(row_frame)
            btn_frame.pack(side="left", padx=1)
            if self.auth.is_admin(self.current_user):
                ttk.Button(btn_frame, text="Reset Pwd", width=9,
                           command=lambda u=user: self.reset_password(u["username"])).pack(side="left", padx=2)
                if user["username"] != self.current_user["username"] and user["username"] != "admin":
                    ttk.Button(btn_frame, text="Delete", width=7,
                               command=lambda u=user: self.delete_user(u["username"])).pack(side="left", padx=2)
                else:
                    ttk.Label(btn_frame, text="(protected)", width=9).pack(side="left", padx=2)
            else:
                ttk.Label(btn_frame, text="(read only)", width=18).pack(side="left")

            self.row_frames.append(row_frame)

    def add_user(self):
        dialog = tk.Toplevel(self)
        dialog.title("Add User")
        dialog.geometry("300x200")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Username:").pack(pady=(10,0))
        username_entry = ttk.Entry(dialog)
        username_entry.pack(pady=5)

        ttk.Label(dialog, text="Password:").pack()
        password_entry = ttk.Entry(dialog, show="*")
        password_entry.pack(pady=5)

        ttk.Label(dialog, text="Role:").pack()
        role_var = tk.StringVar(value="user")
        role_combo = ttk.Combobox(dialog, textvariable=role_var, values=["user", "admin"], state="readonly")
        role_combo.pack(pady=5)

        def do_add():
            uname = username_entry.get().strip()
            pwd = password_entry.get()
            if not uname or not pwd:
                messagebox.showerror("Error", "Username and password required")
                return
            try:
                self.auth.register(uname, pwd, role_var.get(), operator=self.current_user)
                messagebox.showinfo("Success", f"User {uname} created")
                dialog.destroy()
                self.load_users()
            except AuthError as e:
                messagebox.showerror("Failed", str(e))

        ttk.Button(dialog, text="Create", command=do_add).pack(pady=10)

    def change_role(self, username, new_role):
        try:
            self.auth.change_role(username, new_role, self.current_user)
            self.load_users()
            messagebox.showinfo("Role changed", f"{username} is now {new_role}")
        except AuthError as e:
            messagebox.showerror("Error", str(e))
            self.load_users()

    def reset_password(self, username):
        new_pwd = simpledialog.askstring("Reset Password", f"New password for {username}:", show="*", parent=self)
        if new_pwd:
            try:
                self.auth.reset_password(username, new_pwd, self.current_user)
                messagebox.showinfo("Success", f"Password for {username} has been reset.")
            except AuthError as e:
                messagebox.showerror("Failed", str(e))

    def delete_user(self, username):
        if not messagebox.askyesno("Confirm Delete", f"Delete user '{username}'?"):
            return
        try:
            self.auth.delete_user(username, self.current_user)
            self.load_users()
        except AuthError as e:
            messagebox.showerror("Delete failed", str(e))


class ModelResourceManager(tk.Toplevel):
    def __init__(self, parent, database, current_user):
        super().__init__(parent)
        self.title("Model Resources - CRUD Table")
        self.geometry("800x450")
        self.db = database
        self.current_user = current_user
        self.tree = None
        self.build_ui()
        self.refresh_table()

    def build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        toolbar = ttk.Frame(main)
        toolbar.pack(fill="x", pady=(0,10))
        ttk.Button(toolbar, text="Add", command=self.add_resource).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Edit", command=self.edit_resource).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Delete", command=self.delete_resource).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Refresh", command=self.refresh_table).pack(side="left", padx=5)

        columns = ("ID", "Name", "URL", "Local Path", "Status", "Updated At")
        self.tree = ttk.Treeview(main, columns=columns, show="headings", height=15)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120 if col != "URL" else 200)

        scroll_y = ttk.Scrollbar(main, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

    def refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        resources = self.db.list_model_resources()
        for r in resources:
            self.tree.insert("", "end", values=(
                r["id"], r["name"], (r["url"] or "")[:50],
                (r["local_path"] or "")[:50], r["status"], r["updated_at"]
            ))

    def add_resource(self):
        dialog = tk.Toplevel(self)
        dialog.title("Add Model Resource")
        dialog.geometry("400x250")
        ttk.Label(dialog, text="Name (unique):").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack()
        ttk.Label(dialog, text="URL:").pack(pady=5)
        url_entry = ttk.Entry(dialog, width=40)
        url_entry.pack()
        ttk.Label(dialog, text="Local Path (optional):").pack(pady=5)
        path_entry = ttk.Entry(dialog, width=40)
        path_entry.pack()
        ttk.Label(dialog, text="Status:").pack(pady=5)
        status_combo = ttk.Combobox(dialog, values=["pending", "reachable", "failed", "downloaded"], state="readonly")
        status_combo.current(0)
        status_combo.pack()

        def save():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Error", "Name required")
                return
            self.db.upsert_model_resource(
                name, url_entry.get().strip(), path_entry.get().strip(), status_combo.get()
            )
            self.db.log_operation(self.current_user["id"], "add_model_resource", name)
            dialog.destroy()
            self.refresh_table()
        ttk.Button(dialog, text="Save", command=save).pack(pady=10)

    def edit_resource(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Select", "Please select a resource to edit")
            return
        item = self.tree.item(selected[0])
        values = item["values"]
        if not values:
            return
        resource_id, old_name, old_url, old_path, old_status, _ = values
        dialog = tk.Toplevel(self)
        dialog.title("Edit Resource")
        ttk.Label(dialog, text="Name (cannot change)").pack(pady=5)
        ttk.Label(dialog, text=old_name).pack()
        ttk.Label(dialog, text="URL:").pack(pady=5)
        url_entry = ttk.Entry(dialog, width=40)
        url_entry.insert(0, old_url or "")
        url_entry.pack()
        ttk.Label(dialog, text="Local Path:").pack(pady=5)
        path_entry = ttk.Entry(dialog, width=40)
        path_entry.insert(0, old_path or "")
        path_entry.pack()
        ttk.Label(dialog, text="Status:").pack(pady=5)
        status_combo = ttk.Combobox(dialog, values=["pending", "reachable", "failed", "downloaded"], state="readonly")
        status_combo.set(old_status)
        status_combo.pack()

        def update():
            self.db.upsert_model_resource(
                old_name, url_entry.get().strip(), path_entry.get().strip(), status_combo.get()
            )
            self.db.log_operation(self.current_user["id"], "edit_model_resource", old_name)
            dialog.destroy()
            self.refresh_table()
        ttk.Button(dialog, text="Update", command=update).pack(pady=10)

    def delete_resource(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Select", "Select a resource to delete")
            return
        item = self.tree.item(selected[0])
        name = item["values"][1]
        if messagebox.askyesno("Confirm Delete", f"Delete resource '{name}'?"):
            self.db.delete_model_resource(name)
            self.db.log_operation(self.current_user["id"], "delete_model_resource", name)
            self.refresh_table()


class TableViewWindow(tk.Toplevel):
    def __init__(self, parent, title, columns, data):
        super().__init__(parent)
        self.title(title)
        self.geometry("1000x600")
        self.state("zoomed")

        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(main, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, anchor="center")

        if "Detail" in columns:
            self.tree.column("Detail", width=300)
        if "Source" in columns:
            self.tree.column("Source", width=200)
        if "Summary" in columns:
            self.tree.column("Summary", width=220)
        if "Alerts" in columns:
            self.tree.column("Alerts", width=150)

        scroll_y = ttk.Scrollbar(main, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(main, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        for row in data:
            self.tree.insert("", "end", values=row)


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
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 12)
        )
        ttk.Button(self, text="Detect Image", command=self.detect_image).grid(
            row=1, column=0, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Start Camera", command=self.start_camera).grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Check Model URL", command=self.check_model_url).grid(
            row=1, column=2, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Detection Records", command=self.show_records_table).grid(
            row=2, column=0, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Operation Logs", command=self.show_logs_table).grid(
            row=2, column=1, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Export Logs CSV", command=self.export_logs_csv).grid(
            row=2, column=2, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(self, text="Export Chart", command=self.export_chart).grid(
            row=2, column=3, sticky="ew", pady=4
        )
        ttk.Button(self, text="Change Password", command=self.change_password).grid(
            row=3, column=0, sticky="ew", padx=(0, 8), pady=4
        )

        if self.auth.is_admin(self.user):
            ttk.Button(self, text="Manage Users", command=self.manage_users).grid(
                row=3, column=1, sticky="ew", padx=(0, 8), pady=4
            )
            ttk.Button(self, text="Model Resources", command=self.manage_models).grid(
                row=3, column=2, sticky="ew", padx=(0, 8), pady=4
            )

        ttk.Label(self, textvariable=self.status_var, foreground="#444").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(16, 0)
        )
        for column in range(4):
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
            result = check_url(url, timeout=8, retries=2)
            detail = json.dumps(result, ensure_ascii=False)
            self.db.upsert_model_resource("remote_check", url, None, "reachable")
            self.db.log_operation(self.user["id"], "check_url", detail)
            msg = f"URL is reachable!\nStatus: {result['status']}\nType: {result['content_type']}\nLength: {result['length']}"
            self.after(0, lambda: messagebox.showinfo("Network Check", msg))
        except NetworkError as exc:
            self.db.upsert_model_resource("remote_check", url, None, "failed")
            self.db.log_operation(self.user["id"], "check_url_failed", str(exc))
            self.after(0, lambda: messagebox.showerror("Network Check Failed", str(exc)))
        except Exception as exc:
            self.db.upsert_model_resource("remote_check", url, None, "failed")
            self.db.log_operation(self.user["id"], "check_url_failed", f"Unexpected: {exc}")
            self.after(0, lambda: messagebox.showerror("Unexpected Error", str(exc)))

    def show_records_table(self):
        records = self.db.list_detection_records()
        if not records:
            messagebox.showinfo("Detection Records", "No records found.")
            return
        columns = ("ID", "Time", "User", "Source", "Alerts", "Summary", "Output")
        data = []
        for rec in records:
            try:
                alerts = json.loads(rec["alerts_json"])
            except:
                alerts = []
            alerts_str = ", ".join(alerts) if alerts else "-"
            try:
                summary = json.loads(rec["summary_json"])
                event_count = summary.get("event_count", 0)
                eat_ratio = summary.get("eat_ratio", 0)
                sleep_frames = summary.get("sleep_frames", 0)
                summary_str = f"Events:{event_count} EatRatio:{eat_ratio:.2f} SleepFrames:{sleep_frames}"
            except:
                summary_str = "-"
            output = Path(rec["output_path"]).name if rec["output_path"] else "-"
            data.append((
                rec["id"],
                rec["created_at"],
                rec["username"] or "-",
                rec["source"],
                alerts_str,
                summary_str,
                output,
            ))
        TableViewWindow(self, "Detection Records Table", columns, data)

    def show_logs_table(self):
        logs = self.db.list_operation_logs(limit=10000)
        if not logs:
            messagebox.showinfo("Operation Logs", "No logs found.")
            return
        columns = ("ID", "Time", "User", "Action", "Detail")
        data = []
        for log in logs:
            data.append((
                log["id"],
                log["created_at"],
                log["username"] or "system",
                log["action"],
                log["detail"] or "",
            ))
        TableViewWindow(self, "Operation Logs Table", columns, data)

    def export_logs_csv(self):
        logs = self.db.list_operation_logs(limit=10000)
        if not logs:
            messagebox.showinfo("Export Logs", "No logs to export.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Save Logs as CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ["ID", "Timestamp", "Username", "Action", "Detail"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for log in logs:
                    writer.writerow({
                        "ID": log["id"],
                        "Timestamp": log["created_at"],
                        "Username": log["username"] or "system",
                        "Action": log["action"],
                        "Detail": log["detail"] or ""
                    })
            self.db.log_operation(self.user["id"], "export_logs_csv", f"Exported to {file_path}")
            messagebox.showinfo("Export Success", f"Logs exported to {file_path}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

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
        UserManagementWindow(self, self.auth, self.user)

    def manage_models(self):
        ModelResourceManager(self, self.db, self.user)

    def _run_task(self, target, status):
        self.status_var.set(status)

        def runner():
            try:
                target()
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Error", str(exc)))
            finally:
                self.after(0, lambda: self.status_var.set("Ready"))

        threading.Thread(target=runner, daemon=True).start()


class StudyMonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Study Behavior Monitor")
        self.geometry("720x360")
        self.minsize(640, 320)

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
