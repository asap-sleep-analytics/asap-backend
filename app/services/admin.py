from collections import Counter
import csv
from datetime import datetime, timezone
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SleepDetectionLog, SleepSession, UserFeedback

DATASET_EXPORT_FIELDS = [
    "session_id",
    "user_id",
    "start_time",
    "end_time",
    "sleep_score",
    "snore_count",
    "apnea_events",
    "avg_oxygen",
    "ambient_noise_level",
    "detection_windows_total",
    "detection_apnea_windows",
    "detection_snore_windows",
    "detection_normal_windows",
    "detection_mean_confidence",
    "detection_model_source",
    "feedback_sleep_rating",
    "feedback_woke_tired",
    "feedback_comment",
    "feedback_created_at",
    "exported_at",
]


def build_dataset_export_rows(db: Session) -> list[dict]:
    sessions = db.scalars(select(SleepSession).order_by(SleepSession.created_at.desc())).all()
    exported_at = datetime.now(timezone.utc).isoformat()

    rows: list[dict] = []
    for session in sessions:
        logs = db.scalars(
            select(SleepDetectionLog)
            .where(SleepDetectionLog.session_id == session.id)
            .order_by(SleepDetectionLog.window_index.asc(), SleepDetectionLog.id.asc())
        ).all()

        feedback = db.scalar(
            select(UserFeedback)
            .where(UserFeedback.session_id == session.id, UserFeedback.user_id == session.user_id)
            .limit(1)
        )

        label_counts = Counter(log.label for log in logs)
        mean_confidence = None
        model_source = None
        if logs:
            mean_confidence = round(sum(log.confidence_score for log in logs) / len(logs), 4)
            model_source = logs[-1].model_source

        rows.append(
            {
                "session_id": session.id,
                "user_id": session.user_id,
                "start_time": session.start_time.isoformat() if session.start_time else None,
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "sleep_score": session.sleep_score,
                "snore_count": session.snore_count,
                "apnea_events": session.apnea_events,
                "avg_oxygen": session.avg_oxygen,
                "ambient_noise_level": session.ambient_noise_level,
                "detection_windows_total": len(logs),
                "detection_apnea_windows": label_counts.get("Apnea", 0),
                "detection_snore_windows": label_counts.get("Ronquido", 0),
                "detection_normal_windows": label_counts.get("Normal", 0),
                "detection_mean_confidence": mean_confidence,
                "detection_model_source": model_source,
                "feedback_sleep_rating": feedback.sleep_rating if feedback else None,
                "feedback_woke_tired": feedback.woke_tired if feedback else None,
                "feedback_comment": feedback.comment if feedback else None,
                "feedback_created_at": feedback.created_at.isoformat() if feedback and feedback.created_at else None,
                "exported_at": exported_at,
            }
        )

    return rows


def build_dataset_export_csv(rows: list[dict]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=DATASET_EXPORT_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()
