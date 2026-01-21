from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime
import datetime

Base = declarative_base()

class RequestLog(Base):
    __tablename__ = "request_logs"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(128))
    action = Column(String(128))
    payload = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class PendingApproval(Base):
    __tablename__ = "pending_approvals"
    id = Column(Integer, primary_key=True, index=True)
    owner = Column(String(128))
    repo = Column(String(128))
    title = Column(String(256))
    body = Column(Text)
    status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

