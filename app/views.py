from flask import Response, request, Blueprint, jsonify, send_file
from flask_cors import CORS
from .download import list_formats, stream_download, create_progress_queue, generate_progress_events
import logging
import os


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

views = Blueprint("views", __name__)

CORS(views, resources={
    r"/*": {
        "origins": ["http://localhost:3000"],
        "methods": ["POST", "GET", "OPTIONS"],
        "allow_headers": ["Content-Type"],
        "expose_headers": ["Content-Disposition"]
    }
})

@views.route("/formats", methods=["POST"])
def list_format():
    try:
        req = request.get_json()
        url = req.get("url")
        if not url:
            return jsonify({"message": "You should provide a URL for the video"}), 400

        formats = list_formats(url)
        if isinstance(formats, str):
            return jsonify({"error": formats}), 500

        return jsonify({"formats": formats}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@views.route("/download", methods=["POST"])
def download_video():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        req = request.get_json()
        url = req.get("url")
        video_format = req.get("video_format")
        session_id = req.get("session_id")

        if not url or not video_format or not session_id:
            return jsonify({"message": "You must provide the video URL, format, and session ID"}), 400

        logger.info(f"Starting download - Format: {video_format}, Session: {session_id}")

        try:
            # stream_download now returns a Response object
            response = stream_download(url, video_format, session_id)
            return response

        except MemoryError:
            logger.error("Memory error occurred during download")
            return jsonify({
                "error": "Video file is too large to process. Please try a lower quality format."
            }), 413

        except TimeoutError:
            logger.error("Timeout occurred during download")
            return jsonify({
                "error": "Download timed out. Please try again or choose a lower quality format."
            }), 504

    except Exception as e:
        logger.error(f"Download endpoint error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@views.route("/progress/<session_id>")
def progress_stream(session_id):
    try:
        create_progress_queue(session_id)
        response = Response(
            generate_progress_events(session_id),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Transfer-Encoding': 'chunked',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'  # Disable proxy buffering
            }
        )
        return response
    except Exception as e:
        logger.error(f"Progress stream error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500