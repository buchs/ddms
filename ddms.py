#!/usr/bin/env python3.6

import time
import os.path
from hashlib import sha512   # get sha512hash with sha512(string)
from preview_generator.manager import PreviewManager
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlite3 import dbapi2 as sqlite

# Constants that may need to be changed
root_directory = '/home/buchs/Play'  # start at the root level, e.g. c:/Users/david/...
thumbnail_directory = root_directory + '/.thumbnails'
database_path = '/home/buchs/Dropbox/DDMS/data.sqlite'
     # 'C:\\path\\to\\database.db'  # you can nest this in the root directory, be sure the file ends with .sqlite

exclude_extensions = ['sqlite']

db_connection_string = 'sqlite+pysqlite:///' + database_path
db_engine = None

# import logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s',
#                    datefmt='%Y-%m-%d %H:%M:%S')

def DatabaseExists():
    return os.path.exists(database_path)

def SetupDatabase():
    global db_engine
    db_engine = create_engine(db_connection_string)

def GetHash(pathname):
    # read every file as an array of bytes
    fp = open(pathname,'rb')
    data = fp.read()
    fp.close()
    return sha512(data).digest


def AddItem(pathname,sha512hash=None):
    if sha512hash is None:
        sha512hash = GetHash(pathname)
    item = ItemEntry()
    item.hash = sha512hash
    item.path = pathname
    item.filename = os.path.basename(pathname)
    ...


def UpdateItem(found_item,pathname,sha512hash=None):
    if sha512hash is None:
        sha512hash = GetHash(pathname)
    found_item.hash = sha512hash
    found_item.path = pathname
    item.filename = os.path.basename(pathname)



def AddItemFromEvent(event):
    # at: event.src_path
    # generate jpeg thumbnail
    # preview = preview_manager.get_jpeg_preview(file_path, height=200, width=200)
    pass


def DeleteItemFromEvent(event):
    # event.src_path
    pass


def ItemModifiedFromEvent(event):
    # event.src
    # generate jpeg thumbnail
    # preview = preview_manager.get_jpeg_preview(file_path, height=200, width=200)
    pass


def PathModifiedFromEvent(event):
    # event.src_path, event.dest_path
    pass


# override the event handler used by the file system monitor
class DDMSFilesystemEventHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if 'created' == event.event_type and not event.is_directory:
            AddItemFromEvent(event)
        if 'moved' == event.event_type:
            PathModifiedFromEvent(event)
        if 'deleted' == event.event_type and not event.is_directory:
            DeleteItemFromEvent(event)
        if 'modified' == event.event_type:
            ItemModifiedFromEvent(event)


def ComparesHash(sha512hash,found_path):
    # return true or false
    pass


def SearchPath(pathname)
    pass


def SearchHash(sha512hash):
    # return either False or the pointer to the item found
    pass


class ItemEntry:
    self.hash = ''
    self.path = ''
    self.filename = ''
    self.thumbnail = ''

def AddIfMissing(pathname):
    # is the path in the data?
    global fresh_data
    if not fresh_data: # we don't need to run this block if we are starting the first time
        sha512hash = GetHash(pathname)
        # first look for the path
        found_path = SearchPath(pathname)
        if found_path:
            if sha512hash == found_path.hash:
                return   # it is already there, so return
            else:
                # hash changed, so update existing item
                UpdateItem(found_path,pathname,sha512hash)
        else: # path not found, what about the sha512hash?
            found_hash = SearchHash(sha512hash)
            if found_hash:
                # found a match for sha512hash, see if the filename matches, then assume the file was moved
                if found_hash.filename == os.path.basename(pathname):
                    UpdateItem(found_hash,pathname,sha512hash)
                else: # if file name doesn't match, then assume the file was renamed
                    UpdateItem(found_hash,pathname,sha512hash)
            else:
                AddItem(pathname,sha512hash)
    else:
        AddItem(pathname,GetHash(pathname))



# Run this in subprocess
def MonitorFilesystem():
    observer = Observer()
    observer.schedule(DDMSFilesystemEventHandler(), root_directory, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

def WalkDirectoryTree(dir):
  for f in os.listdir(dir):
    pathname = os.path.join(dir,f)
    mode = os.stat(pathname).st_mode
    if stat.S_ISDIR(mode): # if directory, descend into it now
      WalkDirectoryTree(pathname)
    elif stat.S_ISREG(mode): # if regular file, check and add it if required.
      # find the extension and if on an exclude list, just return
      bname = os.path.basename(pathname)
      bname_parts = bname.split('.')
      if bname_parts[-1] in exclude_extensions:
          return
      print(f'file: {pathname}')
      AddIfMissing(pathname)
    else:
      print(f'skipping: {pathname} - what is that anyway?')

def InitialScan():
    # determine if the database has anything in it
    global fresh_data
    fresh_data = not DatabaseExists()

    # walk the directory tree, adding whatever you find that is missing and if this is the first time (because database is empty) just blindly add it all without checking.
    os.chdir(root_directory)
    WalkDirectoryTree('.')

# What we need to do
# 1. scan entire file tree, updating item records, as required
# 2. launch web UI/server
# 3. launch the filesystem monitor

# Open questions
# 1) show should filesystem monitor communicate to the web server changes that are noticed?
# 2) how should the web GUI indicate changes?
# and more
