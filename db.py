# db.py
import sqlite3
import json
from datetime import datetime

class Database:
    def __init__(self, db_path="system.db"):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                local_path TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                detail TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS misclassified_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL,
                original_predictions TEXT,
                corrected_annotations TEXT,
                user_id INTEGER,
                is_reviewed INTEGER DEFAULT 0,
                relabel_image_path TEXT,
                relabel_label_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT UNIQUE NOT NULL,
                base_dataset TEXT,
                additional_sample_count INTEGER DEFAULT 0,
                mAP REAL,
                status TEXT DEFAULT 'pending',
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                model_path TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(created_by) REFERENCES users(id)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_reflux_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER,
                source_image_path TEXT,
                target_image_path TEXT,
                target_label_path TEXT,
                operation TEXT DEFAULT 'relabel',
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sample_id) REFERENCES misclassified_samples(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_name TEXT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                total_duration_seconds INTEGER,
                effective_study_seconds INTEGER,
                focus_score INTEGER CHECK(focus_score BETWEEN 0 AND 100),
                total_alerts INTEGER DEFAULT 0,
                phone_alerts INTEGER DEFAULT 0,
                sleep_alerts INTEGER DEFAULT 0,
                eat_alerts INTEGER DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS study_behavior_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id INTEGER,
                timestamp TIMESTAMP NOT NULL,
                behavior_type TEXT NOT NULL CHECK(behavior_type IN ('normal', 'phone', 'sleep', 'eat', 'other')),
                confidence REAL NOT NULL,
                is_alert INTEGER NOT NULL DEFAULT 0,
                alert_reason TEXT,
                source_type TEXT NOT NULL DEFAULT 'image' CHECK(source_type IN ('image', 'camera', 'video')),
                source_path TEXT,
                image_path TEXT,
                output_image_path TEXT,
                extra_info TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(session_id) REFERENCES study_sessions(id) ON DELETE SET NULL
            )
        """)

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_behavior_user_time ON study_behavior_records(user_id, timestamp)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_behavior_type ON study_behavior_records(behavior_type)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_time ON study_sessions(user_id, start_time)")

        self.connection.commit()

    def add_user(self, username, password, role="user"):
        self.cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                            (username, password, role))
        self.connection.commit()

    def get_user(self, username):
        self.cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = self.cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "password": row[2],
                "role": row[3],
                "created_at": row[4]
            }
        return None

    def user_exists(self, username):
        self.cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        return self.cursor.fetchone() is not None

    def upsert_model_resource(self, name, url, local_path, status):
        self.cursor.execute("""
            INSERT INTO model_resources (name, url, local_path, status, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                url = excluded.url,
                local_path = excluded.local_path,
                status = excluded.status,
                updated_at = CURRENT_TIMESTAMP
        """, (name, url, local_path, status))
        self.connection.commit()

    def list_model_resources(self):
        self.cursor.execute("SELECT * FROM model_resources ORDER BY updated_at DESC")
        rows = self.cursor.fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "url": row[2],
                "local_path": row[3],
                "status": row[4],
                "created_at": row[5],
                "updated_at": row[6]
            }
            for row in rows
        ]

    def delete_model_resource(self, name):
        self.cursor.execute("DELETE FROM model_resources WHERE name = ?", (name,))
        self.connection.commit()

    def log_operation(self, user_id, action, detail=""):
        self.cursor.execute("INSERT INTO system_logs (user_id, action, detail) VALUES (?, ?, ?)",
                            (user_id, action, detail))
        self.connection.commit()

    def get_logs(self, limit=100):
        self.cursor.execute("SELECT * FROM system_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = self.cursor.fetchall()
        return [
            {
                "id": row[0],
                "user_id": row[1],
                "action": row[2],
                "detail": row[3],
                "timestamp": row[4]
            }
            for row in rows
        ]

    def insert_misclassified_sample(self, image_path, original_predictions, user_id):
        predictions_json = json.dumps(original_predictions, ensure_ascii=False)
        self.cursor.execute("""
            INSERT INTO misclassified_samples (image_path, original_predictions, user_id)
            VALUES (?, ?, ?)
        """, (image_path, predictions_json, user_id))
        self.connection.commit()
        return self.cursor.lastrowid

    def update_misclassified_corrected(self, sample_id, corrected_annotations):
        if not isinstance(corrected_annotations, str):
            corrected_annotations = json.dumps(corrected_annotations, ensure_ascii=False)
        self.cursor.execute("""
            UPDATE misclassified_samples
            SET corrected_annotations = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (corrected_annotations, sample_id))
        self.connection.commit()

    def get_misclassified_sample(self, sample_id):
        self.cursor.execute("SELECT * FROM misclassified_samples WHERE id = ?", (sample_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "image_path": row[1],
                "original_predictions": row[2],
                "corrected_annotations": row[3],
                "user_id": row[4],
                "is_reviewed": row[5],
                "relabel_image_path": row[6],
                "relabel_label_path": row[7],
                "created_at": row[8],
                "updated_at": row[9]
            }
        return None

    def list_misclassified_samples(self, reviewed_only=False):
        if reviewed_only:
            self.cursor.execute(
                "SELECT * FROM misclassified_samples WHERE is_reviewed = 1 ORDER BY created_at DESC"
            )
        else:
            self.cursor.execute("SELECT * FROM misclassified_samples ORDER BY created_at DESC")
        rows = self.cursor.fetchall()
        return [
            {
                "id": row[0],
                "image_path": row[1],
                "original_predictions": row[2],
                "corrected_annotations": row[3],
                "user_id": row[4],
                "is_reviewed": row[5],
                "relabel_image_path": row[6],
                "relabel_label_path": row[7],
                "created_at": row[8],
                "updated_at": row[9]
            }
            for row in rows
        ]

    def update_misclassified_relabel_paths(self, sample_id, relabel_image_path, relabel_label_path):
        self.cursor.execute("""
            UPDATE misclassified_samples
            SET relabel_image_path = ?,
                relabel_label_path = ?,
                is_reviewed = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (relabel_image_path, relabel_label_path, sample_id))
        self.connection.commit()

    def delete_misclassified_sample(self, sample_id):
        self.cursor.execute("DELETE FROM misclassified_samples WHERE id = ?", (sample_id,))
        self.connection.commit()

    def create_training_cycle(self, version, base_dataset, created_by):
        self.cursor.execute("""
            INSERT INTO training_cycles (version, base_dataset, created_by)
            VALUES (?, ?, ?)
        """, (version, base_dataset, created_by))
        self.connection.commit()
        return self.cursor.lastrowid

    def update_training_cycle_status(self, cycle_id, status, mAP=None, model_path=None):
        updates = ["status = ?"]
        params = [status]
        if mAP is not None:
            updates.append("mAP = ?")
            params.append(mAP)
        if model_path is not None:
            updates.append("model_path = ?")
            params.append(model_path)
        if status == "completed":
            updates.append("finished_at = CURRENT_TIMESTAMP")
        elif status == "training":
            updates.append("started_at = CURRENT_TIMESTAMP")
        params.append(cycle_id)
        sql = f"UPDATE training_cycles SET {', '.join(updates)} WHERE id = ?"
        self.cursor.execute(sql, params)
        self.connection.commit()

    def get_training_cycles(self):
        self.cursor.execute("SELECT * FROM training_cycles ORDER BY created_at DESC")
        rows = self.cursor.fetchall()
        return [
            {
                "id": row[0],
                "version": row[1],
                "base_dataset": row[2],
                "additional_sample_count": row[3],
                "mAP": row[4],
                "status": row[5],
                "started_at": row[6],
                "finished_at": row[7],
                "model_path": row[8],
                "created_by": row[9],
                "created_at": row[10]
            }
            for row in rows
        ]

    def log_data_reflux(self, sample_id, source_image_path, target_image_path,
                        target_label_path, user_id):
        self.cursor.execute("""
            INSERT INTO data_reflux_log (sample_id, source_image_path, target_image_path,
                                        target_label_path, user_id)
            VALUES (?, ?, ?, ?, ?)
        """, (sample_id, source_image_path, target_image_path, target_label_path, user_id))
        self.connection.commit()

    def start_study_session(self, user_id, session_name=""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute("""
            INSERT INTO study_sessions (user_id, session_name, start_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, session_name, now, now, now))
        self.connection.commit()
        return self.cursor.lastrowid

    def end_study_session(self, session_id, focus_score=None, effective_seconds=None,
                          notes=None, alert_stats=None):
        self.cursor.execute("SELECT start_time FROM study_sessions WHERE id = ?", (session_id,))
        row = self.cursor.fetchone()
        if not row:
            return False
        start = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        duration = int((datetime.now() - start).total_seconds())
        updates = ["end_time = ?", "total_duration_seconds = ?", "updated_at = ?"]
        params = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), duration,
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        if focus_score is not None:
            updates.append("focus_score = ?")
            params.append(focus_score)
        if effective_seconds is not None:
            updates.append("effective_study_seconds = ?")
            params.append(effective_seconds)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if alert_stats:
            if "total" in alert_stats:
                updates.append("total_alerts = ?")
                params.append(alert_stats["total"])
            if "phone" in alert_stats:
                updates.append("phone_alerts = ?")
                params.append(alert_stats["phone"])
            if "sleep" in alert_stats:
                updates.append("sleep_alerts = ?")
                params.append(alert_stats["sleep"])
            if "eat" in alert_stats:
                updates.append("eat_alerts = ?")
                params.append(alert_stats["eat"])
        params.append(session_id)
        sql = f"UPDATE study_sessions SET {', '.join(updates)} WHERE id = ?"
        self.cursor.execute(sql, params)
        self.connection.commit()
        return True

    def list_study_sessions(self, user_id=None, limit=50, offset=0):
        if user_id:
            self.cursor.execute("""
                SELECT * FROM study_sessions
                WHERE user_id = ?
                ORDER BY start_time DESC
                LIMIT ? OFFSET ?
            """, (user_id, limit, offset))
        else:
            self.cursor.execute("""
                SELECT * FROM study_sessions
                ORDER BY start_time DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def add_behavior_record(self, user_id, behavior_type, confidence, session_id=None,
                            is_alert=False, alert_reason="", source_type="image",
                            source_path="", image_path="", output_image_path="", extra_info=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        extra_json = json.dumps(extra_info, ensure_ascii=False) if extra_info else None
        self.cursor.execute("""
            INSERT INTO study_behavior_records
            (user_id, session_id, timestamp, behavior_type, confidence, is_alert, alert_reason,
             source_type, source_path, image_path, output_image_path, extra_info)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, session_id, timestamp, behavior_type, confidence,
              1 if is_alert else 0, alert_reason,
              source_type, source_path, image_path, output_image_path, extra_json))
        self.connection.commit()
        return self.cursor.lastrowid

    def get_behavior_records(self, user_id=None, session_id=None, limit=100, offset=0,
                             behavior_type=None, start_time=None, end_time=None):
        sql = "SELECT * FROM study_behavior_records WHERE 1=1"
        params = []
        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        if behavior_type:
            sql += " AND behavior_type = ?"
            params.append(behavior_type)
        if start_time:
            sql += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            sql += " AND timestamp <= ?"
            params.append(end_time)
        sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        self.cursor.execute(sql, params)
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def get_behavior_statistics(self, user_id, start_time, end_time):
        self.cursor.execute("""
            SELECT behavior_type, COUNT(*) as total, SUM(is_alert) as alerts
            FROM study_behavior_records
            WHERE user_id = ? AND timestamp BETWEEN ? AND ?
            GROUP BY behavior_type
        """, (user_id, start_time, end_time))
        rows = self.cursor.fetchall()
        stats = {}
        for row in rows:
            stats[row[0]] = {"total": row[1], "alerts": row[2] or 0}
        return stats

    def close(self):
        self.connection.close()
