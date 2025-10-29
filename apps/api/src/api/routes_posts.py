# apps/api/src/api/routes_posts.py - CÓDIGO INTEGRAL ATUALIZADO E ROBUSTO

from __future__ import annotations
from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError # <<< NOVO: Importa IntegrityError para tratamento
from datetime import datetime
import traceback

# Importa o decorator de login
from .routes_auth import login_required

# Importa os modelos do banco de dados
from ..infra.db.models import SessionLocal, Family, Membership, Post, Comment, User

posts_bp = Blueprint("posts_bp", __name__)

@posts_bp.route("/family/<string:slug>/posts", methods=["GET"])
@login_required
def get_posts(slug: str):
    user_fs_id = session.get("user_fs_id")
    db = SessionLocal()
    try:
        membership = db.query(Membership).join(Family).filter(
            Family.slug == slug,
            Membership.user_fs_id == user_fs_id
        ).first()

        if not membership:
            return jsonify({"ok": False, "error": "forbidden"}), 403

        posts_query = db.query(Post).filter(
            Post.family_id == membership.family_id
        ).options(
            joinedload(Post.author),
            joinedload(Post.comments).joinedload(Comment.author)
        ).order_by(Post.created_at.desc()).all()

        result = []
        for post in posts_query:
            comments_data = []
            
            safe_sorted_comments = sorted(
                post.comments, 
                key=lambda c: c.created_at if c.created_at else datetime.min
            )
            
            for comment in safe_sorted_comments:
                comment_author_data = {"fs_id": None, "name": "Utilizador Removido"}
                if comment.author:
                    comment_author_data = {"fs_id": comment.author.fs_id, "name": comment.author.name}

                comments_data.append({
                    "id": comment.id,
                    "content": comment.content,
                    "created_at": comment.created_at.isoformat() if comment.created_at else None,
                    "author": comment_author_data
                })

            post_author_data = {"fs_id": None, "name": "Utilizador Removido"}
            if post.author:
                post_author_data = {"fs_id": post.author.fs_id, "name": post.author.name}

            result.append({
                "id": post.id,
                "title": post.title,
                "content": post.content,
                "created_at": post.created_at.isoformat() if post.created_at else None,
                "author": post_author_data,
                "comments": comments_data
            })

        return jsonify({"ok": True, "data": result})

    except Exception as e:
        print(f"!!! ERRO INESPERADO EM GET_POSTS: {e} !!!")
        traceback.print_exc()
        return jsonify({"ok": False, "error": "Erro interno do servidor ao processar os posts."}), 500
    finally:
        db.close()


@posts_bp.route("/family/<string:slug>/posts", methods=["POST"])
@login_required
def create_post(slug: str):
    # ... (Esta função permanece a mesma) ...
    user_fs_id = session.get("user_fs_id")
    body = request.get_json(silent=True) or {}; title = body.get("title", "").strip(); content = body.get("content", "").strip()
    if not title or not content: return jsonify({"ok": False, "error": "title_and_content_required"}), 400
    db = SessionLocal()
    try:
        membership = db.query(Membership).join(Family).filter(Family.slug == slug, Membership.user_fs_id == user_fs_id).first()
        if not membership: return jsonify({"ok": False, "error": "forbidden"}), 403
        new_post = Post(family_id=membership.family_id, user_fs_id=user_fs_id, title=title, content=content)
        db.add(new_post); db.commit()
        return jsonify({"ok": True, "message": "Post created successfully", "post_id": new_post.id}), 201
    finally:
        db.close()


@posts_bp.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def create_comment(post_id: int):
    # ... (Esta função permanece a mesma) ...
    user_fs_id = session.get("user_fs_id")
    content = (request.get_json(silent=True) or {}).get("content", "").strip()
    if not content: return jsonify({"ok": False, "error": "content_required"}), 400
    db = SessionLocal()
    try:
        post = db.query(Post).filter_by(id=post_id).first()
        if not post: return jsonify({"ok": False, "error": "post_not_found"}), 404
        membership = db.query(Membership).filter_by(family_id=post.family_id, user_fs_id=user_fs_id).first()
        if not membership: return jsonify({"ok": False, "error": "forbidden"}), 403
        new_comment = Comment(post_id=post_id, user_fs_id=user_fs_id, content=content)
        db.add(new_comment); db.commit()
        return jsonify({"ok": True, "message": "Comment added successfully", "comment_id": new_comment.id}), 201
    finally:
        db.close()


@posts_bp.route("/post/<int:post_id>", methods=["DELETE"])
@login_required
def delete_post(post_id: int):
    user_fs_id = session.get("user_fs_id")
    db = SessionLocal()
    try:
        post = db.query(Post).options(joinedload(Post.comments)).filter(Post.id == post_id).first()
        if not post:
            return jsonify({"ok": False, "error": "Publicação não encontrada."}), 404

        # >>> aqui estava post.author_fs_id
        if post.user_fs_id != user_fs_id:
            return jsonify({"ok": False, "error": "Você não tem permissão para excluir esta publicação."}), 403

        db.delete(post)
        db.commit()
        return jsonify({"ok": True, "message": "Publicação excluída com sucesso."})
    except IntegrityError:
        db.rollback()
        return jsonify({"ok": False, "error": "Não foi possível excluir a publicação devido a dependências no banco de dados."}), 500
    except Exception:
        db.rollback()
        return jsonify({"ok": False, "error": "Erro interno do servidor."}), 500
    finally:
        db.close()
