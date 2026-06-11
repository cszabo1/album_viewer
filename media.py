"""CGI script that displays a hierarchical tree of media files in the directory passed as parameter.
The path parameter is expected to be relative to the root directory set by the ROOT_DIR variable.
The script performs the following steps:
1. Parses the query parameters to get the 'path' parameter.
2. Sanitizes the 'path' parameter to prevent directory traversal attacks.
3. Normalizes the sanitized path to get the absolute path on the server.
4. Checks if the target path is a directory or a zip file.
5. zip files are treated as directories, and their contents are listed in the same
   way as regular directories.
6. The directory specified by the 'path' parameter is classified in exactly one of the following
   categories:
   - Year Data Container:
     - Criterion: Its name is made of 4 digits (e.g., "2023").
     - Processing:
       - Each file directly inside the directory with an `.mp4` or `.m2ts` extension is considered a
         "movie item".
       - Each subdirectory whose name starts with exactly 8 digits (e.g., "20230101") is considered
         a "group container" named after the subdirectory.
       - For each "year data container" a node is created in the hierarchy.
       - This node has a single attribute "name" with the name of the directory.
       - Found media items and group containers are added as children to this node.
   - Simple Container:
     - Criterion: It does not meet the criteria for a "year data container" and is not inside a
       "year data container".
     - Processing:
       - Each file directly inside the directory with an `.mp4` or `.m2ts` extension is considered a
         "simple movie item".
       - Each subdirectory is classified as if it were a top-level directory, and its content
         is processed accordingly.
       - Each file with a ".jpg" extension directly inside the directory is considered a
         "picture item".
       - For each "simple container" a node is created in the hierarchy.
       - This node has an attribute named "name" containing the name of the directory.
       - If picture items are found in the directory an additional attribute is added to the
         node named "has_pictures" with the value "true".
       - Found "simple movie items", and subdirectories are added as children to this node.
7. Processing of nodes other than those specified above:
   - Movie Item:
     - Criterion: A file with an `.mp4` or `.m2ts` extension inside a "year data container" or a
       "group container".
     - Processing:
       - A node is created with the following attributes:
         - "name": The name of the file except for the extension.
         - "path": The path to the file relative to the root directory.
         - "sdPath": 
"""

import os
import re


ROOT_DIR = "/data/www"
year_re = re.compile(r"^\d{4}$")
date_re = re.compile(r"^(?P<date>\d{8})(?:-(?P<end>\d|\d{2}|\d{4}|\d{8}))?")

# Node Types:
YEAR_DATA_CONTAINER = 1
SIMPLE_CONTAINER = 2
GROUP_CONTAINER = 3
MOVIE_ITEM = 4
SIMPLE_MOVIE_ITEM = 5


def path_to_web_path(path):
  normalized = os.path.normpath(path)
  if os.path.commonpath([ROOT_DIR, normalized]) != ROOT_DIR:
    return None
  return normalized[len(ROOT_DIR):].lstrip("/").replace("\\", "/")


class Node:
  def __init__(self, path: str, yc_path_len: int | None):
    self.path = path_to_web_path(path)
    name = os.path.splitext(os.path.basename(path))[0]
    if not yc_path_len:
      if os.path.isdir(path):
        m = yc_path_len != 0 and year_re.match(name)
        if m:
          self.node_type = YEAR_DATA_CONTAINER
          self.name = name
          self._add_children(path, len(path))
          return
        self.node_type = SIMPLE_CONTAINER
        self._init_name_and_date(name)
        self._add_children(path, None)
        return
      self.node_type = SIMPLE_MOVIE_ITEM
      self._init_name_and_date(name)
      return
    if os.path.isdir(path):
      self.node_type = GROUP_CONTAINER
      self._init_name_and_date(name)
      self._add_children(path, yc_path_len)
      return
    self.node_type = MOVIE_ITEM
    self._init_name_and_date(name)
    path = os.path.splitext(path)[0]
    t = path[:yc_path_len] + "/SD" + path[yc_path_len:] + ".mp4"
    self.sd_path = path_to_web_path(t) if os.path.isfile(t) else None
    t = path[:yc_path_len] + "/Poze" + path[yc_path_len:]
    if os.path.isdir(t):
      self.album_path = path_to_web_path(t)
    else:
      t += ".zip"
      self.album_path = path_to_web_path(t) if os.path.isfile(t) else None

  def _init_name_and_date(self, name):
    m = date_re.match(name)
    if m:
      self.name = name[len(m.group(0)):]
      st_date = m.group(0).replace("-", "\xA0\x2013\xA0")
      st_date = f"{st_date[:4]}-{st_date[4:6]}-{st_date[6:]}"
      if len(st_date) == 17:
        st_date = "-".join((st_date[:15], st_date[15:]))
      self.date = st_date
    else:
      self.name = name
      self.date = None

  def _add_children(self, path, yc_path_len):
    children = []
    self.has_pictures = False
    for entry in os.listdir(path):
      entry_path = os.path.join(path, entry)
      if os.path.isdir(entry_path):
        if (not yc_path_len) or date_re.match(entry):
          children.append(Node(entry_path, yc_path_len))
        continue
      if entry_path.lower().endswith((".mp4", ".m2ts")):
        children.append(Node(entry_path, yc_path_len))
        continue
      if ((not yc_path_len) and (not self.has_pictures) and entry_path.lower().endswith(".jpg")):
        self.has_pictures = True
        children.append(Node(entry_path, yc_path_len))
    if self.node_type == YEAR_DATA_CONTAINER:
      path = os.path.join(path, "Poze")
      names = set(c.name for c in children)
      for entry in os.listdir(path):
        epath = os.path.join(path, entry)
        is_dir = os.path.isdir(epath)
        name = entry[:-4] if entry.endswith(".zip") and not is_dir else entry
        if name in names:
          continue
        children.append(Node(epath, 0))
      return
    if self.node_type == SIMPLE_CONTAINER:
      for entry in os.listdir(path):
        entry_path = os.path.join(path, entry)
        if os.path.isdir(entry_path):
          children.append(Node(entry_path, yc_path_len))
        if entry.endswith(".jpg") and not self.has_pictures:
          self.has_pictures = True
        if entry_path.lower().endswith((".mp4", ".m2ts")):
          children.append(Node(entry_path, yc_path_len))
    self.children = children
