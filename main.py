from app import create_app
from flask_cors import CORS

app = create_app()

CORS(app, resources={
    r"/*": {
        "origins": "http://localhost:3000",  # Your Next.js frontend URL
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-Video-ID"],
        "expose_headers": ["Content-Disposition", "X-Video-ID"],
        "supports_credentials": True
    }
})

if __name__ == "__main__":
    app.run(debug=True)