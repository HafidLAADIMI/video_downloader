import os
from pathlib import Path
from yt_dlp import YoutubeDL
import io
from  flask import jsonify,Response,request
import sys
from .download import  stream_download

import tempfile



def get_default_download_path():
    home_dir = Path.home()
    downloads_dir = home_dir / "Downloads"
    return downloads_dir if downloads_dir.exists() else home_dir

download_progress = {"percent": "0%", "speed": "0", "eta": "0"}

def progress_hook(d):
    if d["status"] == "downloading":
        download_progress["percent"] = d["_percent_str"]
        download_progress["speed"] = d["_speed_str"]
        download_progress["eta"] = d["_eta_str"]


# first try
def download_from_youtube(url, format_id):
    try:
        # Set yt-dlp options, specifying the chosen format_id
        download_path = get_default_download_path()
        ydl_opts = {
            "format": format_id,  # Use the format_id provided
            "outtmpl": str(download_path / "%(title)s.%(ext)s"),  # Save to Downloads folder
            "quiet": True,  # Suppress unnecessary logs
            "progress_hooks": [progress_hook],
        }

        # Use YoutubeDL to download the video
        with YoutubeDL(ydl_opts) as yt:
            yt.download([url])

        return jsonify({"message": f"Video downloaded successfully to {download_path}"}),
    except Exception as e:
        # Return the error as a string
        return str(e)


#second try
def download_from_yotube(url, video_formats):
    try:
        # Create an in-memory buffer
        buffer = io.BytesIO()

        # Redirect stdout to the buffer
        original_stdout = sys.stdout
        sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8")

        # yt-dlp options
        ydl_opts = {
            "format": video_formats,
            "outtmpl": "-",  # Stream output to stdout
            "quiet": True,  # Suppress logs
        }

        # Use yt-dlp to download the video
        with YoutubeDL(ydl_opts) as yt:
            yt.download([url])

        # Reset stdout and the buffer pointer
        sys.stdout = original_stdout
        buffer.seek(0)

        return buffer
    except Exception as e:
        # Reset stdout in case of an error
        sys.stdout = original_stdout
        raise Exception(f"Failed to download video: {str(e)}")



#thrid try


def download_from(url, video_formats, download_path=None):

    try:
        # Set the default download path if none is provided
        if not download_path:
            download_path = Path.home() / "Downloads"
        else:
            # Convert the provided path to a Path object
            download_path = Path(download_path)

            # Validate the provided path
            if not download_path.exists():
                return "The specified path does not exist."
            if not download_path.is_dir():
                return "The specified path is not a directory."
            if not os.access(download_path, os.W_OK):
                return "The specified path is not writable."

        # yt-dlp options with the custom download path
        ytb_opt = {
            "format": video_formats,
            "outtmpl": str(download_path / "%(title)s.%(ext)s"),
        }

        # Use YoutubeDL to download the video
        with YoutubeDL(ytb_opt) as yt:
            print("Downloading the video...")
            yt.download([url])

        return "Video downloaded successfully"
    except Exception as e:
        return str(e)






#the first endpoint
def download_vieo():
    try:
        # Parse the request
        req = request.get_json()
        url = req.get("url")
        video_format = req.get("video_format")

        if not url or not video_format:
            return jsonify({"message": "You must provide both the video URL and the format"}), 400

        # Download the video as a stream
        response = stream_download(url, video_format)
        if isinstance(response, str):
            return jsonify({"error": response}), 500

        # Send the buffer as a file attachment to the browser
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def start_download():
    try:
        req = request.get_json()
        url = req.get("url")
        video_format = req.get("video_format")

        if not url or not video_format:
            return jsonify({"message": "You must provide both the video URL and the format"}), 400

        video_id = download_from_youtube(url, video_format)
        return jsonify({"video_id": video_id}), 200

    except Exception as e:
        print(f"Download error: {str(e)}")
        return jsonify({"error": str(e)}), 500



def get_progress(video_id):
    progress = download_progress.get(video_id, {})
    return jsonify(progress)



def stream_download(url, format_id):
    try:
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            ydl_opts = {
                'format': format_id,
                'quiet': True,
                'noprogress': True,
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            }

            # First get the info to get the filename
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'video')
                ext = info.get('ext', 'mp4')

                # Download the file
                ydl.download([url])

                # Get the downloaded file path
                downloaded_file = next(Path(temp_dir).glob('*'))

                # Read the file into memory
                with open(downloaded_file, 'rb') as f:
                    file_data = io.BytesIO(f.read())

                return file_data, f"{title}.{ext}"

    except Exception as e:
        print(f"Download error: {str(e)}")
        raise e





#views
from flask import Response, request, Blueprint, jsonify, send_file
from flask_cors import CORS
from .download import  list_formats, stream_download
from flask_sse import sse
views = Blueprint("views", __name__)
CORS(views, resources={
    r"/*": {
        "origins": ["http://localhost:3000"],
        "methods": ["POST", "OPTIONS"],
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

    except Exception as e:
        return jsonify({"error": str(e)})


@views.route("/download", methods=["POST"])
def download_video():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        req = request.get_json()
        url = req.get("url")
        video_format = req.get("video_format")

        if not url or not video_format:
            return jsonify({"message": "You must provide both the video URL and the format"}), 400

        file_data, filename = stream_download(url, video_format)

        return send_file(
            file_data,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    except Exception as e:
        print(f"Download endpoint error: {str(e)}")
        return jsonify({"error": str(e)}), 500


views.register_blueprint(sse, url_prefix='/stream')


