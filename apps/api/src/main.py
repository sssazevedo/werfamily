# apps/api/src/main.py - CÓDIGO INTEGRAL ATUALIZADO

import os
from pathlib import Path
from flask import Flask, send_file, send_from_directory, render_template

from .infra.db.models import init_db

def create_app():
    # Define o caminho para as pastas 'web' (templates) e 'static' (imagens, css, etc.)
    app = Flask(__name__, template_folder='web', static_folder='static')

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["FAMILYSEARCH_ENV"] = os.getenv("FAMILYSEARCH_ENV", "beta")
    app.config["FAMILYSEARCH_APP_KEY"] = os.getenv("FAMILYSEARCH_APP_KEY", "")
    app.config["FAMILYSEARCH_REDIRECT_URI"] = os.getenv("FAMILYSEARCH_REDIRECT_URI", "https://127.0.0.1:5000/callback")

    with app.app_context():
        init_db()

    # Blueprints
    from .api.routes_auth import auth_bp, login_required
    from .api.routes_persons_matches import persons_matches_bp
    from .infra.familysearch.fs_routes import fs_bp
    from .api.routes_snapshot import snapshot_bp
    from .api.routes_invites import invites_bp
    from .api.routes_posts import posts_bp
    from .api.routes_gallery import gallery_bp
    from .api.routes_family import family_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(fs_bp)
    app.register_blueprint(persons_matches_bp)
    app.register_blueprint(snapshot_bp)
    app.register_blueprint(invites_bp)
    app.register_blueprint(posts_bp)
    app.register_blueprint(gallery_bp)
    app.register_blueprint(family_bp)


    HERE = Path(__file__).resolve().parent
    WEB_DIR = HERE / "web"

    @app.route("/")
    def index_page():
        # A lógica de redirecionamento está no blueprint de autenticação
        from .api.routes_auth import index as auth_index
        return auth_index()

    @app.route("/app")
    @login_required
    def app_main():
        from flask import session
        user_name = session.get("user_name", "")
        # Passa o nome do usuário para o template, para ser usado em `{{ user_name }}`
        return render_template("app.html", user_name=user_name)

    # <<< INÍCIO DA NOVA ROTA PARA A PÁGINA "SOBRE" >>>
    @app.route("/about")
    def about_page():
        """Renderiza a página 'Sobre'."""
        return render_template("about.html")
    # <<< FIM DA NOVA ROTA >>>

    # Esta rota serve arquivos estáticos como CSS, JS e imagens da pasta 'static'
    # Ela não foi alterada, mas é importante para servir o logo.
    @app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(app.static_folder, filename)
    
    # Esta rota serve os arquivos da aplicação web (mas a rota /app é a principal)
    @app.route("/web/<path:filename>")
    def web_static(filename):
        return send_from_directory(WEB_DIR, filename)

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, ssl_context=("cert.pem", "key.pem"))