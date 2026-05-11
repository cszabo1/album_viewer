#!/home/www-data/python/bin/python3
import os
import sys
import traceback
import html
from urllib.parse import parse_qs

ROOT_DIR = "/data/www"


def http_response(status_code, status_message, body, content_type="text/html; charset=utf-8"):
  sys.stdout.write(f"Status: {status_code} {status_message}\r\n")
  sys.stdout.write(f"Content-Type: {content_type}\r\n\r\n")
  sys.stdout.flush()
  if isinstance(body, str):
    body = body.encode("utf-8", errors="replace")
  sys.stdout.buffer.write(body)


def error(message, status_code=400, status_message="Bad Request"):
  http_response(status_code, status_message, f"<h1>{html.escape(message)}</h1>")
  sys.exit(0)


def parse_parameters():
  params = parse_qs(os.environ.get("QUERY_STRING", ""), keep_blank_values=True)
  method = os.environ.get("REQUEST_METHOD", "GET").upper()

  if method == "POST":
    content_length = int(os.environ.get("CONTENT_LENGTH", "0") or "0")
    if content_length > 0:
      body = sys.stdin.read(content_length)
      params.update(parse_qs(body, keep_blank_values=True))

  return params


def get_first_param(params, name, default=""):
  values = params.get(name)
  return values[0] if values else default


def sanitize_path(path):
  path = path.replace("\\", "/").strip()
  if not path:
    return None
  if os.path.isabs(path):
    return None
  normalized = os.path.normpath(path)
  if normalized.startswith("../") or normalized == ".." or "/../" in normalized:
    return None
  return normalized.lstrip("/")


def normalize_path(path):
  full_path = os.path.normpath(os.path.join(ROOT_DIR, path))
  if os.path.commonpath([ROOT_DIR, full_path]) != ROOT_DIR:
    return None
  return full_path


def main():
  try:
    params = parse_parameters()
    path = get_first_param(params, "path")

    if not path:
      error("Missing required parameter: path", 400, "Bad Request")

    sanitized_path = sanitize_path(path)
    if not sanitized_path:
      error("Invalid path parameter", 400, "Bad Request")

    target_path = normalize_path(sanitized_path)
    if target_path is None:
      error("Invalid path parameter", 400, "Bad Request")

    if not os.path.isdir(target_path) and not (os.path.isfile(target_path) and target_path.lower().endswith(".zip")):
      error("Path is not a directory or zip file", 400, "Bad Request")

    escaped_path = html.escape(sanitized_path)
    escaped_js_path = html.escape(sanitized_path).replace('\\', '/')

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Album Viewer - {escaped_path}</title>
  <style>
    html, body {{
      margin: 0;
      height: 100%;
      background: #000;
      color: #fff;
      font-family: sans-serif;
    }}
    body {{
      display: grid;
      place-items: center;
      overflow: hidden;
    }}
    #container {{
      width: 100%;
      height: 100%;
      position: relative;
      display: grid;
      place-items: center;
      overflow: hidden;
    }}
    img {{
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      display: block;
    }}
    #caption {{
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      padding: 0.6rem 1rem;
      background: rgba(0, 0, 0, 0.5);
      text-align: center;
      font-size: 0.95rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    #message {{
      position: absolute;
      padding: 1rem 1.2rem;
      background: rgba(0,0,0,0.7);
      border-radius: 0.5rem;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div id="container">
    <img id="photo" alt="Album image">
    <div id="caption"></div>
    <div id="message" style="display:none;"></div>
  </div>
  <script>
    const albumPath = {escaped_js_path!r};
    const listUrl = '/cgi-bin/list_album.py?path=' + encodeURIComponent(albumPath);
    const imageUrlBase = '/cgi-bin/picture.py';
    const images = [];
    let currentIndex = 0;
    const photo = document.getElementById('photo');
    const caption = document.getElementById('caption');
    const message = document.getElementById('message');

    function showMessage(text) {{
      message.textContent = text;
      message.style.display = 'block';
    }}

    function hideMessage() {{
      message.style.display = 'none';
    }}

    function setCaption() {{
      if (images.length === 0) {{
        caption.textContent = '';
        return;
      }}
      caption.textContent = `${{currentIndex + 1}} / ${{images.length}} — ${{images[currentIndex]}}`;
    }}

    function imagePath() {{
      return albumPath + '/' + images[currentIndex];
    }}

    function loadImage() {{
      if (images.length === 0) {{
        showMessage('No JPG images found in this album.');
        photo.src = '';
        caption.textContent = '';
        return;
      }}
      hideMessage();
      const width = Math.max(1, window.innerWidth);
      const height = Math.max(1, window.innerHeight);
      const src = `${{imageUrlBase}}?path=${{encodeURIComponent(imagePath())}}&width=${{width}}&height=${{height}}`;
      photo.src = src;
      setCaption();
    }}

    function step(delta) {{
      if (images.length === 0) return;
      currentIndex = (currentIndex + delta + images.length) % images.length;
      loadImage();
    }}

    function handlePointer(event) {{
      if (images.length === 0) return;
      const x = event.clientX;
      const w = window.innerWidth;
      if (typeof x !== 'number') return;
      if (x < w / 2) {{
        step(-1);
      }} else {{
        step(1);
      }}
    }}

    function handleKey(event) {{
      if (event.key === 'ArrowRight' || event.key === 'PageDown') {{
        step(1);
      }} else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {{
        step(-1);
      }}
    }}

    function resizeImage() {{
      if (images.length === 0) return;
      loadImage();
    }}

    function isJpg(filename) {{
      return /\\.(jpe?g)$/i.test(filename);
    }}

    function init() {{
      fetch(listUrl)
        .then(response => {{
          if (!response.ok) throw new Error('Failed to load album listing');
          return response.text();
        }})
        .then(text => {{
          const names = text.split(/\\r?\\n/).map(line => line.trim()).filter(line => line && isJpg(line));
          images.push(...names);
          if (images.length === 0) {{
            showMessage('No JPG images found in this album.');
            return;
          }}
          loadImage();
        }})
        .catch(err => {{
          showMessage(err.message);
        }});
    }}

    window.addEventListener('pointerdown', handlePointer);
    window.addEventListener('keydown', handleKey);
    window.addEventListener('resize', () => {{
      window.requestAnimationFrame(resizeImage);
    }});

    init();
  </script>
</body>
</html>
"""

    http_response(200, "OK", body)
  except Exception:
    traceback.print_exc(file=sys.stderr)
    error("Unexpected server error", 500, "Internal Server Error")


if __name__ == "__main__":
  main()
