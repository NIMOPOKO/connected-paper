from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# SQLite の例。PostgreSQL 等にも変更可能。
SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    nodes = relationship('Node', back_populates='user', cascade='all, delete-orphan')
    edges = relationship('Edge', back_populates='user', cascade='all, delete-orphan')
    sessions = relationship('SessionToken', back_populates='user', cascade='all, delete-orphan')

class Node(Base):
    __tablename__ = 'nodes'
    id = Column(Integer, primary_key=True, index=True)
    openalex_id = Column(String, nullable=False)
    label = Column(String, nullable=False)
    title = Column(String, nullable=False)
    authors = Column(String, nullable=True)
    link = Column(String, nullable=True)
    memo = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user = relationship('User', back_populates='nodes')

class Edge(Base):
    __tablename__ = 'edges'
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String, nullable=False)
    target_id = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user = relationship('User', back_populates='edges')

class SessionToken(Base):
    __tablename__ = 'session_tokens'
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user = relationship('User', back_populates='sessions')


def init_db():
    Base.metadata.create_all(bind=engine)