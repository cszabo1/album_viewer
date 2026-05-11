#!/home/www-data/python/bin/python3
import os
import sys
import traceback
import zipfile
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

def normalize_path(path):
    full_path = os.path.normpath(os.path.join(ROOT_DIR, path))
    if os.path.commonpath([ROOT_DIR, full_path]) != ROOT_DIR:
        return None
    return full_path

def list_directory_files(root_dir):
    results = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            relative = os.path.relpath(os.path.join(dirpath, filename), root_dir)
            results.append(relative.replace(os.sep, "/"))
    return sorted(results)

def list_zip_files(zip_path):
    with zipfile.ZipFile(zip_path, "r") as archive:
        return sorted(name for name in archive.namelist() if not name.endswith("/"))

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

        if os.path.isdir(target_path):
            files = list_directory_files(target_path)
        elif os.path.isfile(target_path) and target_path.lower().endswith(".zip"):
            try:
                files = list_zip_files(target_path)
            except zipfile.BadZipFile:
                error("Invalid ZIP archive", 400, "Bad Request")
        else:
            error("Path is not a directory or zip file", 400, "Bad Request")

        sys.stdout.write("Content-Type: text/plain; charset=utf-8\r\n\r\n")
        sys.stdout.write("\n".join(files))
    except Exception:
        traceback.print_exc(file=sys.stderr)
        error("Unexpected server error", 500, "Internal Server Error")

if __name__ == "__main__":
    main()
