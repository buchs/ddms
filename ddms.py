#!/usr/bin/env python3.6

import time
from preview_generator.manager import PreviewManager
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# Constants that may need to be changed
root_directory = '/home/buchs/Play'  # start at the root level, e.g. c:/Users/david/...
thumbnail_directory = root_directory + '/.thumbnails'

# import logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s',
#                    datefmt='%Y-%m-%d %H:%M:%S')

def AddItem(event):
    # at: event.src_path
    # generate jpeg thumbnail
    # preview = preview_manager.get_jpeg_preview(file_path, height=200, width=200)
    pass

def DeleteItem(event):
    # event.src_path
    pass

def ItemModified(event):
    # event.src
    # generate jpeg thumbnail
    # preview = preview_manager.get_jpeg_preview(file_path, height=200, width=200)
    pass

def PathModified(event):
    # event.src_path, event.dest_path
    pass


# override the event handler used by the file system monitor
class DDMSFilesystemEventHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if 'created' == event.event_type and not event.is_directory:
            AddItem(event)
        if 'moved' == event.event_type:
            PathModified(event)
        if 'deleted' == event.event_type and not event.is_directory:
            DeleteItem(event)
        if 'modified' == event.event_type:
            ItemModified(event)



# Run this in subprocess
def monitor_filesystem():
    observer = Observer()
    observer.schedule(DDMSFilesystemEventHandler(), root_directory, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


# What we need to do
# 1. scan entire file tree, updating item records, as required
# 2. launch web UI/server
# 3. launch the filesystem monitor

# Open questions
# 1) show should filesystem monitor communicate to the web server changes that are noticed?
# 2) how should the web GUI indicate changes?
# and more
