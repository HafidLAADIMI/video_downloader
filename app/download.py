import io
import tempfile
import os
from flask import Response
from pathlib import Path
from yt_dlp import YoutubeDL
import logging
import json
import queue
import re
import shutil
import tempfile
import os
from pathlib import Path
from flask import Response
from yt_dlp import YoutubeDL
import logging

logger = logging.getLogger(__name__)

# Global progress queue for each download
progress_queues = {}


def create_progress_queue(session_id):
    progress_queues[session_id] = queue.Queue()
    return progress_queues[session_id]


def remove_progress_queue(session_id):
    if session_id in progress_queues:
        del progress_queues[session_id]


def progress_hook(d, session_id):
    if session_id in progress_queues and d['status'] == 'downloading':
        total_bytes = d.get('total_bytes')
        downloaded_bytes = d.get('downloaded_bytes', 0)

        if total_bytes:
            progress = (downloaded_bytes / total_bytes) * 100
            progress_data = {
                "progress": progress,
                "downloaded": downloaded_bytes,
                "total": total_bytes,
                "speed": d.get('speed', 0)
            }
            progress_queues[session_id].put(progress_data)


def generate_progress_events(session_id):
    try:
        q = progress_queues[session_id]
        while True:
            try:
                progress_data = q.get(timeout=30)  # 30 second timeout
                yield f"data: {json.dumps(progress_data)}\n\n"
            except queue.Empty:
                # Send keepalive comment to maintain connection
                yield ": keepalive\n\n"
    except GeneratorExit:
        remove_progress_queue(session_id)


def list_formats(url):
    try:
        with YoutubeDL({'listformats': True, 'noplayslist': True}) as yt:
            info = yt.extract_info(url, download=False)
            thumbnail_url = info.get("thumbnail", None)
            if 'formats' not in info:
                return "The provided URL does not point to a valid video."
            formats = [
                {
                    "format_id": fmt["format_id"],
                    "format_note": fmt.get("format_note", "N/A"),
                    "ext": fmt["ext"],
                    "resolution": fmt.get("resolution", "N/A"),
                    "filesize": fmt.get("filesize", "N/A")
                }
                for fmt in info.get('formats', [])
                if fmt.get("ext") in ["mp4", "webm"]
                   and fmt.get("format_note") not in ["N/A", None]
                   and fmt.get("resolution") not in ["N/A", None]
                   and any(char.isdigit() for char in fmt.get("resolution", ""))
            ]
            return {"formats": formats, "thumbnail": thumbnail_url}
    except Exception as e:
        return str(e)


def sanitize_filename(filename):
    """
    Sanitize the filename by removing or replacing invalid characters.
    """
    # Replace invalid characters with underscores
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)

    # Normalize Unicode characters
    sanitized = sanitized.encode('ascii', 'ignore').decode('ascii')

    # Ensure the filename is not empty
    return sanitized if sanitized else 'video'


def file_generator(file_path):
    """
    Generator function to stream the file in chunks.
    """
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):  # 8KB chunks
                yield chunk
    except FileNotFoundError as e:
        logger.error(f"File not found: {file_path}")
        raise e


def stream_download(url, format_id, session_id):
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            ydl_opts = {
                'format': format_id,
                'quiet': True,
                'noprogress': True,
                'progress_hooks': [lambda d: progress_hook(d, session_id)],
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'buffersize': 10 * 1024 * 1024,  # 10MB buffer
                'retries': 15,
                'fragment_retries': 15,
                'http_chunk_size': 20485760,  # 20MB chunks
                'timeout': 600,  # 10-minute timeouthunks

            }

            with YoutubeDL(ydl_opts) as ydl:
                try:
                    # Extract info to get the title and extension
                    info = ydl.extract_info(url, download=False)
                    title = sanitize_filename(info.get('title', 'video'))
                    ext = info.get('ext', 'mp4')

                    # Download the file
                    ydl.download([url])

                    # Get the downloaded file path
                    downloaded_file = next(Path(temp_dir).glob('*'))

                    # Copy the file to a safe temporary location
                    temp_file_path = tempfile.NamedTemporaryFile(delete=False)
                    temp_file_path.close()  # Close the handle so we can write to it

                    os.replace(downloaded_file, temp_file_path.name)

                    # Stream the file directly to the client
                    response = Response(
                        file_generator(temp_file_path.name),
                        mimetype='application/octet-stream',
                        headers={
                            'Content-Disposition': f'attachment; filename="{title}.{ext}"',
                            'Content-Length': str(os.path.getsize(temp_file_path.name)),
                            'Connection': 'keep-alive',
                            'Keep-Alive': 'timeout=300',
                        }
                    )

                    # Delete the temporary file after streaming
                    response.call_on_close(lambda: os.remove(temp_file_path.name))

                    return response

                except Exception as e:
                    logger.error(f"YouTube-DL error: {str(e)}", exc_info=True)
                    raise Exception(f"Failed to download video: {str(e)}")

    except Exception as e:
        logger.error(f"Stream download error: {str(e)}", exc_info=True)
        raise e
