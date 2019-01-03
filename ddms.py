#!/usr/bin/env python3.6
"""
What you need to run this:
 - installation of Python 3.6 or later
 - You should get a pip command with that install, if not, search for that
 - Execute these commands:
      pip install preview_generator
      pip install watchdog
      pip install sqlalchemy
 - Change the constants below for the path to ROOT DIRECTORY, etc.
 - Run the script in a terminal/cmd window: python3.6 ddms.py

What you have here is no GUI interface, just the file system scanning to populate
the database. So, if working, you should see messages about all your files
being added. Then, when the output stops and you see the file system monitor is
running, you can do additional tests to add a file, delete a file, change a file's
contents (just have a text file you edit), move file from one directory to
another, and rename a file keeping it in the same directory.

"""
import os
import time
import logging
import queue

# making use of pathlib, instead of os.path and some others.
# Mostly, paths stay Path objects unless a string is required, such as:
# the preview generator and the database storage. Otherwise, we can do
# most things from a Path object, such as reading a byte array from the
# file referenced by the Path object.
## import os.path
## import stat
from pathlib import Path
from hashlib import sha512   # get sha 512 bit hash with sha512(string)
from shutil import rmtree

# needed setup: pip3.6 install preview_generator, watchdog and sqlalchemy
from preview_generator.manager import PreviewManager
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy import create_engine, Table, Column, String, MetaData
from sqlalchemy import select as sqlselect


# Constants that may need to be changed
# start at the root level, e.g. c:/Users/david/...
ROOT_DIRECTORY = Path('/home/buchs/Play').expanduser().resolve()
THUMBNAIL_DIRECTORY = ROOT_DIRECTORY.joinpath('.thumbnails')
DATABASE_PATH = Path('/home/buchs/Dropbox/DDMS/data.sqlite').expanduser().resolve()
#  windows: 'C:\\path\\to\\database.db'   # those are backslashes doubled
# you can nest this in the root directory, be sure the file ends with .sqlite

EXCLUDE_EXTENSIONS = ['sqlite']
IGNORED_DIRECTORIES = [Path('.thumbnails')]

LOGGING_FORMAT = '%(asctime)-15s  %(message)s'
logging.basicConfig(format=LOGGING_FORMAT)
LOG = logging.getLogger('DDMS')
LOG.setLevel('INFO')

QUEUE = queue.Queue()  # This will be a work queue for items from file system
                       # monitoring which runs in another thread.


class DDMSException(Exception):
    "basic custom exception"


class ItemEntry:
    "in memory item object"
    def __init__(self, pathname, shahash, thumbnail, labels=''):
        self.shahash = shahash
        self.pathname = pathname
        self.thumbnail = thumbnail
        self.labels = labels

    def set_preview(self, preview):
        "setter"
        self.thumbnail = preview

    def set_pathname(self, pathname):
        "setter"
        self.pathname = pathname

    def set_shahash(self, shahash):
        "setter"
        self.shahash = shahash



class DDMSFilesystemEventHandler(FileSystemEventHandler):
    "override the event handler used by the file system monitor"

    def __init__(self, singleton):
        self.singleton = singleton


    def on_any_event(self, event):
        # pylint: disable=misplaced-comparison-constant
        if 'created' == event.event_type and not event.is_directory:
            self.add_item_from_event(event)
        if 'moved' == event.event_type and not event.is_directory:
            self.path_modified_from_event(event)
        if 'deleted' == event.event_type and not event.is_directory:
            self.delete_item_from_event(event)
        if 'modified' == event.event_type and not event.is_directory:
            self.item_modified_from_event(event)


    # pylint: disable=no-self-use
    def make_path_relative(self, str_pathname):
        """Transform from absolute file system paths to relative to the ROOT_DIRECTORY"""
        corrected_path = str_pathname.replace(str(ROOT_DIRECTORY) + os.sep, '')
        for dire in IGNORED_DIRECTORIES:
            if corrected_path.startswith(str(dire)):
                return None
        return corrected_path


    def add_item_from_event(self, event):
        "triggered by a file system event, a new file is added to database"
        src = self.make_path_relative(event.src_path)
        if src is not None:
            QUEUE.put({"action": "add", "src": src})
            # log_message = f'File system event: add item: {src}'
            # LOG.info(log_message)

    def delete_item_from_event(self, event):
        "triggered by a file system event, a file is deleted, so delete from database"
        src = self.make_path_relative(event.src_path)
        if src is not None:
            QUEUE.put({"action": "delete", "src": src})
            # log_message = f'File system event: delete item: {src}'
            # LOG.info(log_message)

    def item_modified_from_event(self, event):
        "triggered by a file system event, a file's content is updated, so update database"
        src = self.make_path_relative(event.src_path)
        if src is not None:
            QUEUE.put({"action": "modified", "src": src})
            # log_message = f'File system event: modify item: {src}'
            # LOG.info(log_message)

    def path_modified_from_event(self, event):
        "triggered by a file system event, a file is moved to a new location, update database"
        src = self.make_path_relative(event.src_path)
        dest = self.make_path_relative(event.dest_path)
        if src is not None and dest is not None:
            QUEUE.put({"action": "moved", "src": src, "dest": dest})
            # log_message = f'File system event: path mod item: {src} to {dest}'
            # LOG.info(log_message)


class DDMSSingleton:
    "put all things under this singleton class"

    # pylint: disable=too-many-instance-attributes
    # I have what I need to have for this class. leave me alone.

    def __init__(self):
        """initialize this class"""
        # startup preview generator
        self.preview = PreviewManager(THUMBNAIL_DIRECTORY, create_folder=True)

        # place holder for file system monitoring
        self.observer = None

        # get the database interface up and setup the database if it is new
        self.fresh_data = not DATABASE_PATH.exists() # is this the first time we have run?
        self.db_connection_string = 'sqlite+pysqlite:///' + str(DATABASE_PATH)
        self.db_engine = create_engine(self.db_connection_string)
        self.db_conn = self.db_engine.connect()
        metadata = MetaData()
        self.tb_items = Table('items', metadata,
                              Column('path', String, primary_key=True, index=True),
                              Column('shahash', String, index=True),
                              Column('thumb', String),
                              Column('labels', String))
        self.tb_labels = Table('labels', metadata,
                               Column('label', String, index=True))

        if self.fresh_data:  # first time through, create the tables
            metadata.create_all(self.db_engine)
            LOG.info('First time database setup completed.')
            self.all_paths = set() # empty set of existing paths in database
        else:
            # used to track databaase paths found (so that unfound ones can be deleted
            self.all_paths = set()
            sel = sqlselect([self.tb_items.c.path,])
            result = self.db_conn.execute(sel)
            for row in result.fetchall():
                # have to make these paths match filesystem paths...
                self.all_paths.add(Path(row[0]))



    def search_path(self, pathname):
        "search database according to pathname"
        if self.tb_items is None:
            LOG.error(f'self.tb_items is None in search_path')
            return False
        str_pathname = str(pathname)
        sel = sqlselect([self.tb_items,]).where(self.tb_items.c.path == str_pathname)
        result = self.db_conn.execute(sel)
        rows = result.fetchall()
        result.close()
        # expect only one result
        if len(rows) == 1:
            row = rows[0]
            item = ItemEntry(Path(row[0]), row[1], Path(row[2]), row[3])
            return item
        if len(rows) > 1:
            raise DDMSException(f'Multiple matches for path {str_pathname}')
        else:
            return False


    def search_hash(self, shahash):
        "search database according to sha hash"
        # return either False or the item found
        sel = sqlselect([self.tb_items,]).where(self.tb_items.c.shahash == shahash)
        result = self.db_conn.execute(sel)
        rows = result.fetchall()
        result.close()
        # expect only one result
        if len(rows) == 1:
            row = rows[0]
            item = ItemEntry(Path(row[0]), row[1], Path(row[2]), row[3])
            return item
        if len(rows) > 1:
            raise DDMSException(f'Multiple matches for shashash {shahash}')
        else:
            return False


    # pylint: disable=no-self-use
    def get_hash(self, pathname):
        "read a file and return the sha 512 hash of its contents"
        # read every file as an array of bytes
        return sha512(pathname.read_bytes()).digest()


    def add_item(self, pathname, shahash=None):
        "add a completely new item to database"
        str_pathname = str(pathname)
        if shahash is None:
            shahash = self.get_hash(pathname)
        # generate jpeg thumbnail file and capture its path as string
        preview = self.preview.get_jpeg_preview(str_pathname, height=200, width=200)

        insert = self.tb_items.insert(None)
        self.db_conn.execute(insert, path=str_pathname, shahash=shahash,
                             thumb=preview, labels='')
        LOG.info('Add item: %s', pathname)


    def update_item_path(self, old_pathname, new_pathname):
        "update an existing database entry"
        update = self.tb_items.update(None) \
            .where(self.tb_items.c.path == str(old_pathname)) \
            .values(path=str(new_pathname))
        self.db_conn.execute(update)
        LOG.info('Update path of item: was: %s, changed to %s', old_pathname, new_pathname)


    def update_item_hash_thumb(self, pathname, shahash=None):
        "file contents changed, update hash and thumbnail"
        item = self.search_path(pathname)
        if item:
            str_pathname = str(pathname)
            if shahash is None:
                shahash = self.get_hash(pathname)
            # going to change thumbnail, so delete the old file to keep things under control
            thumbpath = Path(item.thumbnail)
            thumbpath.unlink()
            # generate jpeg thumbnail
            preview = self.preview.get_jpeg_preview(str_pathname, height=200, width=200)
            update = self.tb_items.update(None) \
                .where(self.tb_items.c.path == str_pathname) \
                .values(shahash=shahash, thumb=preview)
            self.db_conn.execute(update)
            LOG.info('Update hash/preview of item %s', str_pathname)


    def delete_item(self, pathname):
        "delete an item from the database"
        item = self.search_path(pathname)
        if item:
            # clean up the preview
            thumb = Path(item.thumbnail)
            if thumb.exists():
                thumb.unlink()
            # delete item from database
            dele = self.tb_items.delete(None).where(self.tb_items.c.path == str(pathname))
            self.db_conn.execute(dele)
            LOG.info('Deleted item, path was %s', pathname)


    def add_if_missing(self, pathname):
        "determine if the seemingly added file requires database update"
        # is the path in the data?
        if not self.fresh_data:  # we don't need to run this block if we are starting the first time
            shahash = self.get_hash(pathname)
            # first look for the path
            found_path = self.search_path(pathname)
            if found_path:
                # remove this path from the set of all paths previously in db
                self.all_paths.remove(found_path.pathname)

                if shahash == found_path.shahash:
                    return   # it is already there, so return
                # hash changed, so update existing item
                self.update_item_hash_thumb(pathname, shahash)
            else: # path not found, what about the shahash?
                found_hash = self.search_hash(shahash)
                if found_hash:
                    # found a match for shahash,
                    # if the filename matches, then assume the file was moved and if it
                    # doesn't match, then the file name was changed. Either way, the action
                    # is the same: update the path in the database
                    self.update_item_path(found_hash.pathname, pathname)

                else:
                    # no match for path or hash, this is a new file, so add it
                    self.add_item(pathname, shahash)
        else:
            # there was no existing data, so just add this
            self.add_item(pathname, self.get_hash(pathname))



    def found_create(self, qlist, queue_entry):
        """helper for monitor_filesystem() """
        src = queue_entry['src']
        # my most complex list comprehension follows
        result = [True for alpha in qlist if alpha['src'] == src and alpha['action'] == 'add']
        # tests for the list to be not empty and the first item is True
        return result and result[0]

    # Run this in subprocess
    def monitor_filesystem(self):
        "starts up the file system monitor and waits for a keyboard interrupt"
        LOG.info('Starting file system monitor')
        self.observer = Observer()
        self.observer.schedule(DDMSFilesystemEventHandler(self),
                               str(ROOT_DIRECTORY), recursive=True)
        self.observer.start()
        # The watchdog monitor is too noisy, sending events that are not interesting,
        # like a create event and 12 modify events. To avoid extra work, buffer these events
        # for 15 seconds. Also a create followed by modified are combined into one create.
        # When a event arrives, it is first inspected to see if it is a modified following
        # a create, and if so, it is dropped. Otherwise it is added to a queue with a timestamp
        # of 15 seconds into the future. We then monitor the queue to see if the top event's
        # time is up. If it is, then that event is processed.
        qlist = list()
        queue_delay = 15 # seconds

        # pylint: disable=misplaced-comparison-constant
        try:
            while True:
                time.sleep(1)
                while not QUEUE.empty():
                    queue_entry = QUEUE.get_nowait()
                    LOG.info("Dequeued filesystem event: %s, src: %s",
                             queue_entry['action'], queue_entry['src'])
                    # squash modified events right after create
                    if 'modified' == queue_entry['action']  \
                            and self.found_create(qlist, queue_entry):
                        pass # squash
                    else:
                        queue_entry['timestamp'] = time.time() + queue_delay
                        qlist.append(queue_entry) # add to second queue
                    QUEUE.task_done()
                # now process events whose time is up, but only do 1 each second
                # in order to not consume too much time, impacting GUI
                if qlist and time.time() > qlist[0]['timestamp']:
                    queue_entry = qlist.pop(0)
                    action = queue_entry['action']
                    src = queue_entry['src']
                    LOG.info("popped from secondary queue: action: %s, src: %s", action, src)
                    if action == 'add':
                        self.add_item(Path(src))
                    if action == 'delete':
                        self.delete_item(Path(src))
                    if action == 'modified':
                        self.update_item_hash_thumb(Path(src))
                    if action == 'moved':
                        self.update_item_path(Path(src), Path(queue_entry['dest']))
                # done, back to sleep
        except KeyboardInterrupt:
            self.observer.stop()
        self.observer.join() # wait for observer thread to exit



    def walk_directory_tree(self, directory):
        "inspect every item in the directory tree, add if it is missing"
        for filesystem_item in directory.iterdir():
            pathname = Path(filesystem_item)
            if pathname.is_dir(): # if directory, descend into it now unless excluded
                if pathname not in IGNORED_DIRECTORIES:
                    self.walk_directory_tree(pathname)
            elif pathname.is_file(): # if regular file, check and add it if required.
                # find the extension and if on an exclude list, just return
                if pathname.suffix in EXCLUDE_EXTENSIONS:
                    return
                self.add_if_missing(pathname)
            else:
                LOG.warning(f'skipping: %s - what is this anyway?', pathname)


    def initial_scan(self):
        "do this when first starting up - re-sync with directory tree"
        # get positioned at the root of file system tree
        os.chdir(ROOT_DIRECTORY)

        # walk the directory tree, adding whatever you find that is missing
        # determine if the database has anything in it, if not, we can blindly add
        self.walk_directory_tree(Path('.'))

        if self.all_paths.__len__() > 0:
            print('Left over paths from database:')
            for leftover_path in self.all_paths:
                print(str(leftover_path))
                self.delete_item(leftover_path)



    def run_web_ui(self):
        "start up the web server in another process"

    def main(self):
        "top level function"

        # initially, scan the whole directory to rationalize any changes
        self.initial_scan()

        # run the web UI in other process
        #self.run_web_ui()

        # run the filesystem monitor in other process
        self.monitor_filesystem()


# Open questions
# 1) show should filesystem monitor communicate to the web server changes that are noticed?
# 2) how should the web GUI indicate changes?
# and more

if __name__ == "__main__":
    # for testing only, let's clear the board before we run
    WIPE_EXISTING = False
    if WIPE_EXISTING:
        if DATABASE_PATH.exists():
            DATABASE_PATH.unlink()
        rmtree(THUMBNAIL_DIRECTORY)

    DDMS = DDMSSingleton()
    DDMS.main()
