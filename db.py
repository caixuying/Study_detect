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
        #用户表
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        #模型资源表
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

        #操作日志表
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

        #误识别样本表
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

        #训练周期
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

        #数据回流
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

    # 操作日志
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

    #误识别样本相关 
    def insert_misclassified_sample(self, image_path, original_predictions, user_id):
        """
        保存误识别样本
        original_predictions: list 或 dict，自动 JSON 序列化
        返回新记录的 ID
        """
        predictions_json = json.dumps(original_predictions, ensure_ascii=False)
        self.cursor.execute("""
            INSERT INTO misclassified_samples (image_path, original_predictions, user_id)
            VALUES (?, ?, ?)
        """, (image_path, predictions_json, user_id))
        self.connection.commit()
        return self.cursor.lastrowid

    def update_misclassified_corrected(self, sample_id, corrected_annotations):
        """更新用户修正后的标注（JSON 字符串或可序列化对象）"""
        if not isinstance(corrected_annotations, str):
            corrected_annotations = json.dumps(corrected_annotations, ensure_ascii=False)
        self.cursor.execute("""
            UPDATE misclassified_samples
            SET corrected_annotations = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (corrected_annotations, sample_id))
        self.connection.commit()

    def get_misclassified_sample(self, sample_id):
        """获取单个误识别样本记录"""
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
        """列出误识别样本，可筛选是否已审核回流"""
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
        """更新回流后的文件路径，并标记为已审核"""
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
        """删除误识别样本记录"""
        self.cursor.execute("DELETE FROM misclassified_samples WHERE id = ?", (sample_id,))
        self.connection.commit()

    #训练周期相关
    def create_training_cycle(self, version, base_dataset, created_by):
        """创建新的训练周期，返回新记录 ID"""
        self.cursor.execute("""
            INSERT INTO training_cycles (version, base_dataset, created_by)
            VALUES (?, ?, ?)
        """, (version, base_dataset, created_by))
        self.connection.commit()
        return self.cursor.lastrowid

    def update_training_cycle_status(self, cycle_id, status, mAP=None, model_path=None):
        """
        更新训练周期状态、指标和模型路径
        status: pending / training / completed / failed
        """
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
        """获取所有训练周期记录，按创建时间倒序"""
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
        """记录数据回流操作"""
        self.cursor.execute("""
            INSERT INTO data_reflux_log (sample_id, source_image_path, target_image_path,
                                        target_label_path, user_id)
            VALUES (?, ?, ?, ?, ?)
        """, (sample_id, source_image_path, target_image_path, target_label_path, user_id))
        self.connection.commit()

    def close(self):
        """关闭数据库连接"""
        self.connection.close()
