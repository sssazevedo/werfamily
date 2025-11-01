# apps/api/src/infra/db/models.py
from __future__ import annotations
import os
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, UniqueConstraint, Text, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# 1. Lê a URL do banco de dados da variável de ambiente do Render
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///wrfamily.db")

# 2. Corrige o prefixo da URL para o SQLAlchemy (específico para Heroku/Render)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 3. Cria o engine de forma condicional
if DATABASE_URL.startswith("sqlite"):
    # Configuração para SQLite (desenvolvimento local)
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Configuração para PostgreSQL (produção no Render)
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    fs_id = Column(String(32), primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    memberships = relationship("Membership", back_populates="user")
    paths = relationship("UserPath", back_populates="user")
    # --- Adicionado para aceder a posts, comentários e media de um utilizador ---
    posts = relationship("Post", back_populates="author")
    comments = relationship("Comment", back_populates="author")
    media_uploads = relationship("Media", back_populates="uploader")

class Family(Base):
    __tablename__ = "families"
    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # <<< MUDANÇA: Adicionada exclusão em cascata para snapshots >>>
    snapshots = relationship("Snapshot", back_populates="family", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="family")
    invites = relationship("Invite", back_populates="family")
    user_paths = relationship("UserPath", back_populates="family")
    posts = relationship("Post", back_populates="family", cascade="all, delete-orphan")
    media = relationship("Media", back_populates="family", cascade="all, delete-orphan")

class Membership(Base):
    __tablename__ = "memberships"
    user_fs_id = Column(String(32), ForeignKey("users.fs_id"), primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), primary_key=True)
    role = Column(String(16), nullable=False, default="member")
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="memberships")
    family = relationship("Family", back_populates="memberships")

class Person(Base):
    __tablename__ = "persons"
    id = Column(String(32), primary_key=True)
    name = Column(String(255)); gender = Column(String(16))
    birth = Column(String(64)); birth_place = Column(String(255))
    death = Column(String(64)); death_place = Column(String(255))
    extra = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Relation(Base):
    __tablename__ = "relations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    rel_type = Column("type", String(16), nullable=False)
    src_id = Column(String(32), ForeignKey("persons.id"), nullable=False)
    dst_id = Column(String(32), ForeignKey("persons.id"), nullable=False)
    __table_args__ = (UniqueConstraint("type", "src_id", "dst_id", name="uix_rel_type_src_dst"),)
    src = relationship("Person", foreign_keys=[src_id])
    dst = relationship("Person", foreign_keys=[dst_id])

class Snapshot(Base):
    __tablename__ = "snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    slug = Column(String(64), nullable=False, unique=True)
    root_husband_id = Column(String(32)); root_wife_id = Column(String(32))
    desc_depth = Column(Integer, nullable=False, default=3)
    asc_depth = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    family = relationship("Family", back_populates="snapshots")
    # <<< INÍCIO DA CORREÇÃO: Adiciona os relacionamentos com cascata >>>
    nodes = relationship("SnapshotNode", back_populates="snapshot", cascade="all, delete-orphan")
    edges = relationship("SnapshotEdge", back_populates="snapshot", cascade="all, delete-orphan")
    # <<< FIM DA CORREÇÃO >>>

class SnapshotNode(Base):
    __tablename__ = "snapshot_nodes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False)
    person_id = Column(String(32), ForeignKey("persons.id"), nullable=False)
    __table_args__ = (UniqueConstraint("snapshot_id", "person_id", name="uix_snapshot_node"),)
    # <<< INÍCIO DA CORREÇÃO: Adiciona o relacionamento de volta (back_populates) >>>
    snapshot = relationship("Snapshot", back_populates="nodes")
    # <<< FIM DA CORREÇÃO >>>

class SnapshotEdge(Base):
    __tablename__ = "snapshot_edges"
    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False)
    type = Column(String(16), nullable=False)
    src_id = Column(String(32), ForeignKey("persons.id"), nullable=False)
    dst_id = Column(String(32), ForeignKey("persons.id"), nullable=False)
    __table_args__ = (UniqueConstraint("snapshot_id", "type", "src_id", "dst_id"),)
    # <<< INÍCIO DA CORREÇÃO: Adiciona o relacionamento de volta (back_populates) >>>
    snapshot = relationship("Snapshot", back_populates="edges")
    # <<< FIM DA CORREÇÃO >>>

class Invite(Base):
    __tablename__ = "invites"
    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    email = Column(String(255), nullable=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    family = relationship("Family", back_populates="invites")

class UserPath(Base):
    __tablename__ = "user_paths"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_fs_id = Column(String(32), ForeignKey("users.fs_id"), nullable=False)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    path_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="paths")
    family = relationship("Family", back_populates="user_paths")

class Post(Base):
    """Representa um post no mural de uma família."""
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    user_fs_id = Column(String(32), ForeignKey("users.fs_id"), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    family = relationship("Family", back_populates="posts")
    author = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    media = relationship("Media", back_populates="post") # Media associada a este post

class Comment(Base):
    """Representa um comentário num post."""
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    user_fs_id = Column(String(32), ForeignKey("users.fs_id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="comments")
    author = relationship("User", back_populates="comments")

class Media(Base):
    """Representa um ficheiro de media (foto) numa família."""
    __tablename__ = "media"
    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    user_fs_id = Column(String(32), ForeignKey("users.fs_id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    
    file_path = Column(String(512), nullable=False)
    caption = Column(String(512), nullable=True)
    media_type = Column(String(32), default="image")
    created_at = Column(DateTime, default=datetime.utcnow)

    family = relationship("Family", back_populates="media")
    uploader = relationship("User", back_populates="media_uploads")
    post = relationship("Post", back_populates="media")

def init_db() -> None:
    """Cria todas as tabelas no banco de dados se elas não existirem."""
    Base.metadata.create_all(bind=engine)