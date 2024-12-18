from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    app.config['SQLALCHEMY_ECHO'] = True

    
    @app.route('/debug/db-path')
    def debug_db_path():
        db_path = os.path.abspath('activityladdr2.db')
        app.logger.debug(f"SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

        return jsonify({"db_path": db_path, "exists": os.path.exists(db_path)})

    db.init_app(app)
    Migrate(app, db)

    # Register blueprints
    from .routes import main
    app.register_blueprint(main)

    return app
