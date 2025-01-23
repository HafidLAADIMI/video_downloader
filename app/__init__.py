from flask import Flask


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "HELLOthishafid@2003^***é^jzefjzeé__nfnfé"
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB
    app.config['REQUEST_TIMEOUT'] = 3000  # 50 minutes
    from .views import views
    app.register_blueprint(views)
    return app
