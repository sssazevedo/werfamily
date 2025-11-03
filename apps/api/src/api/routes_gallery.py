# apps/api/src/api/routes_gallery.py - CÓDIGO INTEGRAL ATUALIZADO

import os
import secrets
from pathlib import Path
from flask import Blueprint, jsonify, request, session, send_from_directory, url_for
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload

# Importa o decorator de login
from .routes_auth import login_required
# Importa os modelos do banco de dados
from ..infra.db.models import SessionLocal, Family, Membership, Media, User

gallery_bp = Blueprint("gallery_bp", __name__)

UPLOAD_FOLDER = Path(__file__).resolve().parent.parent.parent / 'uploads'
UPLOAD_FOLDER.mkdir(exist_ok=True)
...
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@gallery_bp.route("/family/<string:slug>/gallery", methods=["POST"])
@login_required
def upload_media(slug: str):
    user_fs_id = session.get("user_fs_id")
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "no_file_part"}), 400
    
    file = request.files['file']
    caption = request.form.get("caption", "")

    if file.filename == '' or not _allowed_file(file.filename):
        return jsonify({"ok": False, "error": "invalid_file"}), 400

    db = SessionLocal()
    try:
        membership = db.query(Membership).join(Family).filter(
            Family.slug == slug,
            Membership.user_fs_id == user_fs_id
        ).first()

        if not membership:
            return jsonify({"ok": False, "error": "forbidden"}), 403

        filename = secure_filename(file.filename)
        random_hex = secrets.token_hex(8)
        _, f_ext = os.path.splitext(filename)
        unique_filename = f"{random_hex}{f_ext}"
        
        file_path = UPLOAD_FOLDER / unique_filename
        file.save(file_path)

        new_media = Media(
            family_id=membership.family_id,
            user_fs_id=user_fs_id,
            file_path=unique_filename,
            caption=caption,
            media_type='image'
        )
        db.add(new_media)
        db.commit()

        return jsonify({"ok": True, "message": "File uploaded successfully", "media_id": new_media.id}), 201
    finally:
        db.close()

@gallery_bp.route("/family/<string:slug>/gallery", methods=["GET"])
@login_required
def get_gallery(slug: str):
    user_fs_id = session.get("user_fs_id")
    db = SessionLocal()
    try:
        membership = db.query(Membership).join(Family).filter(
            Family.slug == slug,
            Membership.user_fs_id == user_fs_id
        ).first()

        if not membership:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        
        # <<< MUDANÇA: Faz join com User para obter informações do autor >>>
        media_items = db.query(Media).filter(
            Media.family_id == membership.family_id
        ).options(
            joinedload(Media.uploader)
        ).order_by(Media.created_at.desc()).all()

        result = []
        for item in media_items:
            result.append({
                "id": item.id,
                "url": url_for("gallery_bp.serve_uploaded_file", filename=item.file_path, _external=True),
                "caption": item.caption,
                "created_at": item.created_at.isoformat(),
                # <<< MUDANÇA: Adiciona o fs_id do autor para verificação no frontend >>>
                "uploader": {
                    "fs_id": item.user_fs_id,
                    "name": item.uploader.name if item.uploader else "Utilizador desconhecido"
                }
            })

        return jsonify({"ok": True, "data": result})
    finally:
        db.close()

@gallery_bp.route("/uploads/<string:filename>")
def serve_uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# <<< INÍCIO DA NOVA ROTA DE EXCLUSÃO >>>
@gallery_bp.route("/gallery/<int:media_id>", methods=["DELETE"])
@login_required
def delete_media(media_id: int):
    user_fs_id = session.get("user_fs_id")
    db = SessionLocal()
    try:
        media_item = db.query(Media).filter(Media.id == media_id).first()

        if not media_item:
            return jsonify({"ok": False, "error": "Mídia não encontrada."}), 404

        if media_item.user_fs_id != user_fs_id:
            return jsonify({"ok": False, "error": "Você não tem permissão para excluir esta mídia."}), 403

        # Exclui o arquivo físico do servidor
        try:
            file_to_delete = UPLOAD_FOLDER / media_item.file_path
            if file_to_delete.is_file():
                os.remove(file_to_delete)
        except Exception as e:
            print(f"AVISO: Não foi possível excluir o arquivo físico: {e}")
            # Continua para excluir o registro do DB mesmo que o arquivo não seja encontrado

        db.delete(media_item)
        db.commit()

        return jsonify({"ok": True, "message": "Mídia excluída com sucesso."})
    finally:
        db.close()
# <<< FIM DA NOVA ROTA DE EXCLUSÃO >>>