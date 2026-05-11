#!/home/www-data/python/bin/python3
import os
import sys
import traceback
import zipfile
import posixpath
from urllib.parse import parse_qs

ROOT_DIR = "/data/www"


def http_response(status_code, status_message, body, content_type="text/plain; charset=utf-8"):
  sys.stdout.write(f"Status: {status_code} {status_message}\r\n")
  sys.stdout.write(f"Content-Type: {content_type}\r\n\r\n")
  if isinstance(body, str):
    body = body.encode("utf-8", errors="replace")
  sys.stdout.buffer.write(body)


def error(message, status_code=400, status_message="Bad Request"):
  http_response(status_code, status_message, message)
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


def normalize_image_path(path):
  image_path = os.path.normpath(os.path.join(ROOT_DIR, path))
  if os.path.commonpath([ROOT_DIR, image_path]) != ROOT_DIR:
    return None
  return image_path


def split_zip_path(path):
  lower_path = path.lower()
  zip_marker = ".zip/"
  idx = lower_path.find(zip_marker)
  if idx == -1:
    return None, None
  zip_path = path[: idx + len(zip_marker) - 1]
  internal_path = path[idx + len(zip_marker):]
  if not internal_path:
    return None, None
  return zip_path, internal_path


def sanitize_zip_internal_path(internal_path):
  internal_path = internal_path.replace("\\", "/").strip().lstrip("/")
  if not internal_path:
    return None
  if any(part == ".." for part in internal_path.split("/")):
    return None
  normalized = posixpath.normpath(internal_path)
  if normalized.startswith("../") or normalized == ".." or "/../" in normalized:
    return None
  return normalized.lstrip("/")


def main():
  try:
    params = parse_parameters()
    path = get_first_param(params, "path")
    width_value = get_first_param(params, "width")
    height_value = get_first_param(params, "height")

    if not path:
      error("Missing required parameter: path", 400, "Bad Request")
    if not width_value:
      error("Missing required parameter: width", 400, "Bad Request")

    sanitized_path = sanitize_path(path)
    if not sanitized_path:
      error("Invalid path parameter", 400, "Bad Request")

    try:
      width = int(width_value)
    except (TypeError, ValueError):
      error("width must be an integer", 400, "Bad Request")

    if width <= 0:
      error("width must be a positive integer", 400, "Bad Request")

    height = None
    if height_value:
      try:
        height = int(height_value)
      except (TypeError, ValueError):
        error("height must be an integer", 400, "Bad Request")
      if height <= 0:
        error("height must be a positive integer", 400, "Bad Request")

    zip_source, internal_path = split_zip_path(sanitized_path)
    if zip_source:
      zip_file_path = normalize_image_path(zip_source)
      if zip_file_path is None or not os.path.isfile(zip_file_path):
        error("File not found", 404, "Not Found")

      internal_path = sanitize_zip_internal_path(internal_path)
      if internal_path is None:
        error("Invalid archive path", 400, "Bad Request")

      try:
        from PIL import Image
      except ImportError:
        error("Pillow is required to resize images. Install it with: pip install pillow",
              500, "Internal Server Error")

      try:
        with zipfile.ZipFile(zip_file_path, "r") as archive:
          with archive.open(internal_path) as fileobj:
            with Image.open(fileobj) as im:
              original_width, original_height = im.size
              if original_width == 0 or original_height == 0:
                error("Invalid image dimensions", 500, "Internal Server Error")

              if height is None:
                target_height = max(1, round(original_height * width / original_width))
                target_width = width
              else:
                scale = min(width / original_width, height / original_height)
                target_width = max(1, round(original_width * scale))
                target_height = max(1, round(original_height * scale))

              resized = im.resize((target_width, target_height), Image.LANCZOS)

              sys.stdout.write("Content-Type: image/jpeg\r\n\r\n")
              sys.stdout.flush()
              resized.convert("RGB").save(sys.stdout.buffer,
                                          format="JPEG", quality=85)
      except KeyError:
        error("File not found", 404, "Not Found")
      except zipfile.BadZipFile:
        error("Invalid ZIP archive", 400, "Bad Request")
      return

    image_path = normalize_image_path(sanitized_path)
    if image_path is None or not os.path.isfile(image_path):
      error("File not found", 404, "Not Found")

    try:
      from PIL import Image
    except ImportError:
      error("Pillow is required to resize images. Install it with: pip install pillow",
            500, "Internal Server Error")

    with Image.open(image_path) as im:
      original_width, original_height = im.size
      if original_width == 0 or original_height == 0:
        error("Invalid image dimensions", 500, "Internal Server Error")

      if height is None:
        target_height = max(1, round(original_height * width / original_width))
        target_width = width
      else:
        scale = min(width / original_width, height / original_height)
        target_width = max(1, round(original_width * scale))
        target_height = max(1, round(original_height * scale))

      resized = im.resize((target_width, target_height), Image.LANCZOS)

      sys.stdout.write("Content-Type: image/jpeg\r\n\r\n")
      sys.stdout.flush()
      resized.convert("RGB").save(sys.stdout.buffer, format="JPEG", quality=85)
  except Exception:
    traceback.print_exc(file=sys.stderr)
    error("Unexpected server error", 500, "Internal Server Error")


if __name__ == "__main__":
  main()
