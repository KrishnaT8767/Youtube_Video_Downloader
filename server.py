from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import yt_dlp, os, uuid, json, bcrypt, threading, webbrowser

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

USERS_FILE = "users.json"
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump({}, f)

def load_users():
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

# ===== Routes =====
@app.route("/")
def index():
    return send_from_directory(".", "yt.html")

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error":"Missing username or password"}), 400
    users = load_users()
    if username in users:
        return jsonify({"error":"Username already exists"}), 400
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[username] = {"password": hashed, "downloads":[]}
    save_users(users)
    return jsonify({"success": True})

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error":"Missing username or password"}), 400
    users = load_users()
    user = users.get(username)
    if not user:
        return jsonify({"error":"Invalid username"}), 400
    if not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return jsonify({"error":"Invalid password"}), 400
    return jsonify({"success": True})

@app.route("/video_info", methods=["POST"])
def video_info():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error":"No URL provided"}), 400
    try:
        ydl_opts = {"quiet":True, "skip_download":True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_info = {
                "title": info.get("title","Unknown Title"),
                "thumbnail": info.get("thumbnail",""),
                "uploader": info.get("uploader","Unknown"),
                "duration": int(info.get("duration",0))
            }
        return jsonify(video_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/formats", methods=["POST"])
def get_formats():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error":"No URL provided"}), 400
    try:
        ydl_opts = {"quiet": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            result_formats = []

            # Audio only
            result_formats.append({
                "format_id": "bestaudio",
                "ext": "mp3",
                "resolution": "Audio Only",
                "note": "MP3"
            })

            # Video+Audio dynamically
            available_resolutions = set()
            for f in info.get("formats", []):
                if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("ext")=="mp4":
                    res = f.get("height")
                    if res and res not in available_resolutions:
                        available_resolutions.add(res)
                        result_formats.append({
                            "format_id": f["format_id"],
                            "ext": "mp4",
                            "resolution": f"{res}p",
                            "note": "MP4 (video+audio)"
                        })

            # Sort: Audio first, then ascending resolution
            result_formats.sort(key=lambda x: (0 if x["resolution"]=="Audio Only" else int(x["resolution"].replace("p",""))))

        return jsonify({"formats": result_formats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/download", methods=["POST","OPTIONS"])
def download_video():
    if request.method=="OPTIONS": return jsonify({"status":"ok"}), 200
    data = request.get_json()
    url = data.get("url")
    format_id = data.get("format_id")
    username = data.get("username")
    if not url or not format_id or not username:
        return jsonify({"error":"Missing parameters"}), 400
    try:
        ext = "mp3" if format_id=="bestaudio" else "mp4"
        filename = f"{uuid.uuid4()}.{ext}"
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        ydl_opts = {"outtmpl": filepath}
        if ext=="mp3":
            ydl_opts["format"] = "bestaudio"
            ydl_opts["postprocessors"] = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
        else:
            ydl_opts["format"] = format_id
            ydl_opts["merge_output_format"] = "mp4"
            ydl_opts["postprocessor_args"] = ["-c:v","copy","-c:a","aac"]
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        users = load_users()
        if username in users:
            users[username]["downloads"].append(url)
            save_users(users)

        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

if __name__=="__main__":
    threading.Timer(1, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
