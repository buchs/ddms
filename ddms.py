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
import sys
import time
import json
import queue
import random
import logging
import argparse
import webbrowser

# About making use of pathlib, instead of os.path and some others.
# Mostly, paths stay Path objects unless a string is required, such as:
# the preview generator and the database storage. Otherwise, we can do
# most things from a Path object, such as reading a byte array from the
# file referenced by the Path object.
from pathlib import Path

from hashlib import sha512  # get sha 512 bit hash with sha512(string)
from shutil import rmtree
from threading import Thread
from tempfile import TemporaryFile

# needed setup: pip3.6 install preview_generator, watchdog and sqlalchemy
from preview_generator.manager import PreviewManager
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy import create_engine, Table, Column, String, MetaData
from sqlalchemy import select as sqlselect, text as sqltext
from bottle import route as bottle_route, run as bottle_run,  \
    static_file, request as bottle_request
# could include:  template,, response as bottle_response
# noinspection PyPep8,Pylint
from bottle import debug as bottle_debug

# Constants that may need to be changed
# start at the root level, e.g. c:/Users/david/...
if 'USER' in os.environ and os.environ['USER'] == 'buchs' and sys.platform == 'linux':
    # Could be Dad
    ROOT_DIRECTORY = Path('/home/buchs/Play').expanduser().resolve()
    DATABASE_PATH = Path('/home/buchs/Dropbox/DDMS/data.sqlite').expanduser().resolve()
    # SCRIPT_DIR = Path(__file__).expanduser().absolute().parent
    SCRIPT_DIR = Path('/home/buchs/Dropbox/DDMS')
else:
    # Should be David
    ROOT_DIRECTORY = Path("C:\\Users\\dbuchs\\Dropbox\\To File\\test").expanduser().resolve()
    DATABASE_PATH = Path('C:\\Users\\dbuchs\\Dropbox\\data.sqlite').expanduser().resolve()
    #  windows: 'C:\\path\\to\\database.db'   # those are backslashes doubled
    # you can nest this in the root directory, be sure the file ends with .sqlite
    SCRIPT_DIR = Path(__file__).expanduser().absolute().parent

THUMBNAIL_DIRECTORY = ROOT_DIRECTORY.joinpath('.thumbnails')

EXCLUDE_EXTENSIONS = ['sqlite']
IGNORED_DIRECTORIES = [Path('.thumbnails')]

NETWORK_PORT = 8080

# THINGS CONFIGURED TO SUPPORT DEVELOPMENT
DESIRED_FRUITS = ['apple', 'banana', 'orange', 'peaches', 'plums']
LOG_FILE = 'ddms.log' # just file name
LOGGING_FORMAT = '%(asctime)-15s  %(message)s'
logging.basicConfig(format=LOGGING_FORMAT)
LOG = logging.getLogger('DDMS')
LOG.setLevel('INFO')
LOG.addHandler(logging.FileHandler(SCRIPT_DIR.joinpath(LOG_FILE)))

# noinspection PyPep8,Pylint
bottle_debug(mode=True)


# This will be a work queue for items from file system
# monitoring and web server which run in other threads.
QUEUE = queue.Queue()

# This is for the main thread to return results to the
# GUI thread.
RESULTSQ = queue.Queue()


class DDMSException(Exception):
    """basic custom exception"""


class ItemEntry:
    """in memory item object"""

    def __init__(self, pathname, shahash, thumbnail, labels=''):
        self.shahash = shahash
        self.pathname = pathname
        self.thumbnail = thumbnail
        self.labels = labels


    def set_preview(self, preview):
        """setter"""
        self.thumbnail = preview


    def set_pathname(self, pathname):
        """setter"""
        self.pathname = pathname


    def set_shahash(self, shahash):
        """setter"""
        self.shahash = shahash


# Helper for File system monitor
# pylint: disable=no-self-use
def make_path_relative(str_pathname):
    """
    Transform from absolute file system paths to relative to the ROOT_DIRECTORY
    """
    corrected_path = str_pathname.replace(str(ROOT_DIRECTORY) + os.sep, '')
    for dire in IGNORED_DIRECTORIES:
        if corrected_path.startswith(str(dire)):
            return None
    return corrected_path


class DDMSFilesystemEventHandler(FileSystemEventHandler):
    """override the event handler used by the file system monitor"""

    def __init__(self):
        # super(DDMSFilesystemEventHandler, self).__init__()
        pass

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

    def add_item_from_event(self, event):
        """triggered by a file system event, a new file is added to database"""

        src = make_path_relative(event.src_path)
        if src is not None:
            QUEUE.put({"type": "filesystem-monitor", "action": "add", "src": src})
            # log_message = f'File system event: add item: {src}'
            # LOG.info(log_message)


    def delete_item_from_event(self, event):
        """triggered by a file system event, a file is deleted, so delete from database"""
        src = make_path_relative(event.src_path)
        if src is not None:
            QUEUE.put({"type": "filesystem-monitor", "action": "delete", "src": src})
            # log_message = f'File system event: delete item: {src}'
            # LOG.info(log_message)


    def item_modified_from_event(self, event):
        """triggered by a file system event, a file's content is updated, so update database"""
        src = make_path_relative(event.src_path)
        if src is not None:
            QUEUE.put({"type": "filesystem-monitor", "action": "modified", "src": src})
            # log_message = f'File system event: modify item: {src}'
            # LOG.info(log_message)


    def path_modified_from_event(self, event):
        """triggered by a file system event, a file is moved to a new location, update database"""
        src = make_path_relative(event.src_path)
        dest = make_path_relative(event.dest_path)
        if src is not None and dest is not None:
            QUEUE.put({"type": "filesystem-monitor", "action": "moved", "src": src, "dest": dest})
            # log_message = f'File system event: path mod item: {src} to {dest}'
            # LOG.info(log_message)


class BLPathTreeNode:
    """object is the node in directory tree for browse list"""
    def __init__(self, path, parent=None):
        self.path = path
        self.parent = parent
        self.children = []

    def repr_children(self):
        """iterates over the children of a node, returning the recursive depth-first
        grandchildren"""
        output = ''
        for child in self.children:
            output += repr(child)
            output += ', '
        # omit the final comma and space
        return output[0:-2]

    def __repr__(self):
        """
        Override this function so we can output a JSON string representation via repr(obj)
        """
        output = f'{{"text": "{self.path}", '
        if self.repr_children():   # i.e. are there children, if no, this is a file node
            output += '"children": ['
            output += self.repr_children()
            output += ']}'
        else:
            output += '"icon": "jstree-file"}'
        return output

    def add_child(self, path):
        """Add a new child on browse list tree"""
        child = BLPathTreeNode(path, self)
        self.children.append(child)
        return child

    def delete_tree(self):
        """Delete a child from browse list tree"""
        for child in self.children:
            child.delete_tree()
            del child

    def create_path(self, path_parts):
        """Prove a given path exists or create it, all the while finding the tree
        node at the bottom"""
        cp_node = GLOBAL_DATA.browse_list_object
        creating = False
        for pindex in range(len(path_parts)-1): # stop one short of filename (last element)
            if not creating:
                found_it = False
                for child in cp_node.children:
                    if child.path == path_parts[pindex]:
                        cp_node = child
                        found_it = True
                        break # inner for loop
                if not found_it:
                    creating = True  # we need to create, starting from here
                    returned = cp_node.add_child(path_parts[pindex])
                    cp_node = returned # and then we just let the loop iterate.
            else:
                returned = cp_node.add_child(path_parts[pindex])
                cp_node = returned  # and then we just let the loop iterate.

        return cp_node


# noinspection Pylint
# pylint disable=too-few-public-methods
class GlobalData:
    """
    Holds various global values, pointers to services and database information
    for handy reference.
    """
    # pylint: disable=too-many-instance-attributes
    # I have what I need to have for this class. leave me alone.
    def __init__(self):
        """initialize this class"""

        # startup preview generator - this guy wants to emit useless messages
        # when starting, tried to throw away with assignmet to os.devnull. That
        # was broken, it wants to see a real file. So, try a temporary file.
        # THIS is DANGEROUS - you can miss a real error.
        save_stdout = sys.stdout
        tempfile = TemporaryFile(mode='w', suffix='txt')
        sys.stdout = tempfile
        try:
            self.preview = PreviewManager(THUMBNAIL_DIRECTORY, create_folder=True)

        # pylint bare-except
        except Exception as exception_info:
            LOG.error('Exception in Preview Generator startup')
            LOG.error(exception_info)

        sys.stdout.close()
        sys.stdout = save_stdout

        # place holder for file system monitoring
        self.observer = None

        # get the database interface up and setup the database if it is new
        self.fresh_data = not DATABASE_PATH.exists()  # is this the first time we have run?
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
            self.all_paths = set()  # empty set of existing paths in database
        else:
            # used to track databaase paths found (so that unfound ones can be deleted
            self.all_paths = set()
            sel = sqlselect([self.tb_items.c.path, ])
            result = self.db_conn.execute(sel)
            for row in result.fetchall():
                # have to make these paths match filesystem paths...
                self.all_paths.add(Path(row[0]))

        # fill lablels with fruits for dev testing, unless they already exist
        sel = sqlselect([self.tb_labels.c.label, ]).order_by('label')
        result = self.db_conn.execute(sel)
        rows = result.fetchall()
        result.close()
        existing = [str(r[0]) for r in rows]
        # which of desired_fruits is not already in table?
        fruits = [f for f in DESIRED_FRUITS if f not in existing]
        insert = self.tb_labels.insert(None)
        for label in fruits:
            self.db_conn.execute(insert, label=label)

        # Other important data structures
        self.browse_list_object = None
        self.updates = False
        self.updates_browse_list = False

    def nothing(self):
        """Keeping pylint happy"""
        pass


def search_path(pathname):
    """search database according to pathname"""
    if GLOBAL_DATA.tb_items is None:
        LOG.error(f'GLOBAL_DATA.tb_items is None in search_path')
        return False
    str_pathname = str(pathname)
    sel = sqlselect([GLOBAL_DATA.tb_items, ]).where(GLOBAL_DATA.tb_items.c.path == str_pathname)
    result = GLOBAL_DATA.db_conn.execute(sel)
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


def search_hash(shahash):
    """search database according to sha hash"""
    # return either False or the item found
    sel = sqlselect([GLOBAL_DATA.tb_items, ]).where(GLOBAL_DATA.tb_items.c.shahash == shahash)
    result = GLOBAL_DATA.db_conn.execute(sel)
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


def get_hash(pathname):
    """
    read a file and return the sha 512 hash of its contents
    """
    # read every file as an array of bytes
    return sha512(pathname.read_bytes()).digest()


def add_item(pathname, shahash=None):
    """add a completely new item to database"""
    LOG.info('adding item')
    str_pathname = str(pathname)
    if shahash is None:
        shahash = get_hash(pathname)
    # generate jpeg thumbnail file and capture its path as string
    try:
        preview = GLOBAL_DATA.preview.get_jpeg_preview(str_pathname, height=200, width=200)
        thumb_path = str(Path(preview).relative_to(THUMBNAIL_DIRECTORY))
        LOG.info('Preview generation complete')
    except Exception as except_info:
        ## handle unsupported mimetype exception -- create blank jpg file
        preview = str(THUMBNAIL_DIRECTORY.joinpath(str(random.randrange(100000000, 999999999)) + '.jpeg'))
        open(preview, 'a').close()
        LOG.info('Preview generation failed, dummy thumbnail created')

    # just for development - we will assign a random fruit label 50% of the time.
    random_int = random.randrange(2*len(DESIRED_FRUITS))
    if random_int < len(DESIRED_FRUITS):
        labels = DESIRED_FRUITS[random_int]
    else:
        labels = ''

    insert = GLOBAL_DATA.tb_items.insert(None)
    GLOBAL_DATA.db_conn.execute(insert, path=str_pathname, shahash=shahash,
                                thumb=thumb_path, labels=labels)
    LOG.info('Added item: %s', pathname)


def update_item_path(old_pathname, new_pathname):
    """update an existing database entry"""
    update = GLOBAL_DATA.tb_items.update(None) \
        .where(GLOBAL_DATA.tb_items.c.path == str(old_pathname)) \
        .values(path=str(new_pathname))
    GLOBAL_DATA.db_conn.execute(update)
    LOG.info('Update path of item: was: %s, changed to %s', old_pathname, new_pathname)


def update_item_hash_thumb(pathname, shahash=None):
    """file contents changed, update hash and thumbnail"""
    item = search_path(pathname)
    if item:
        str_pathname = str(pathname)
        if shahash is None:
            shahash = get_hash(pathname)
        # going to change thumbnail, so delete the old file to keep things under control
        thumbpath = Path(item.thumbnail)
        thumbpath.unlink()
        # generate jpeg thumbnail
        preview = GLOBAL_DATA.preview.get_jpeg_preview(str_pathname, height=200, width=200)
        thumb_path = Path(preview).relative_to(THUMBNAIL_DIRECTORY)
        update = GLOBAL_DATA.tb_items.update(None) \
            .where(GLOBAL_DATA.tb_items.c.path == str_pathname) \
            .values(shahash=shahash, thumb=thumb_path)
        GLOBAL_DATA.db_conn.execute(update)
        LOG.info('Update hash/preview of item %s', str_pathname)


def delete_item(pathname):
    """delete an item from the database"""
    item = search_path(pathname)
    if item:
        # clean up the preview
        thumb = Path(item.thumbnail)
        if thumb.exists():
            thumb.unlink()
        # delete item from database
        dele = GLOBAL_DATA.tb_items.delete(None).where(GLOBAL_DATA.tb_items.c.path == str(pathname))
        GLOBAL_DATA.db_conn.execute(dele)
        LOG.info('Deleted item, path was %s', pathname)


def add_if_missing(pathname):
    """determine if the seemingly added file requires database update"""
    # is the path in the data?
    # we don't need to run this block if we are starting the first time
    if not GLOBAL_DATA.fresh_data:
        shahash = get_hash(pathname)
        # first look for the path
        found_path = search_path(pathname)
        if found_path:
            # remove this path from the set of all paths previously in db
            GLOBAL_DATA.all_paths.remove(found_path.pathname)

            if shahash == found_path.shahash:
                return  # it is already there, so return
            # hash changed, so update existing item
            update_item_hash_thumb(pathname, shahash)
        else:  # path not found, what about the shahash?
            found_hash = search_hash(shahash)
            if found_hash:
                # found a match for shahash,
                # if the filename matches, then assume the file was moved and if it
                # doesn't match, then the file name was changed. Either way, the action
                # is the same: update the path in the database
                update_item_path(found_hash.pathname, pathname)

            else:
                # no match for path or hash, this is a new file, so add it
                add_item(pathname, shahash)
    else:
        # there was no existing data, so just add this
        add_item(pathname, get_hash(pathname))


def found_create(qlist, queue_entry):
    """helper for monitor_queue (from filesystem monitor) """
    src = queue_entry['src']
    # my most complex list comprehension follows
    result = [True for alpha in qlist if alpha['src'] == src and alpha['action'] == 'add']
    # tests for the list to be not empty and the first item is True
    return result and result[0]


def monitor_filesystem():
    """
    starts up the file system monitor which runs in a separate thread
    """
    LOG.info('Starting file system monitor')
    GLOBAL_DATA.observer = Observer()
    GLOBAL_DATA.observer.schedule(DDMSFilesystemEventHandler(),
                                  str(ROOT_DIRECTORY), recursive=True)
    GLOBAL_DATA.observer.start()



def monitor_queue():
    """
    We have two separate threads: 1) running the file system monitor and 2) running the bottle
    web server. We need to have this original thread look at a queue of work items coming from
    those other threads. And, this also monitors for a Control-C keyboard input.
    """

    # The complexity here is almost entirely driven by the events coming from the
    # file system monitor. The file system monitor is too noisy, sending events that are not
    # interesting, like a create event and 12 modify events. To avoid extra work, buffer these
    # events for 15 seconds. Also a create followed by modified are combined into one create.
    # When a event arrives, it is first inspected to see if it is a modified following
    # a create, and if so, it is dropped. Otherwise it is added to a queue with a timestamp
    # of 15 seconds into the future. We then monitor the queue to see if the top event's
    # time is up. If it is, then that event is processed. Think of it as one queue feeding
    # another queue, and that other one has a time buffer on it.

    qlist = list()
    queue_delay = 15  # seconds
    time_counter = 0

    def execute_queue_task_file(queue_entry):
        LOG.info("Dequeued filesystem event: %s, src: %s",
                 queue_entry['action'], queue_entry['src'])
        # squash modified events right after create
        if queue_entry['action'] == 'modified' \
                and found_create(qlist, queue_entry):
            pass  # squash
        else:
            queue_entry['timestamp'] = time.time() + queue_delay
            qlist.append(queue_entry)  # add to second queue

    def execute_queue_task_gui(queue_entry):
        # run the provided query and return the results on the results queue
        result = GLOBAL_DATA.db_conn.execute(queue_entry['select'])
        RESULTSQ.put({'rows': result.fetchall()})
        result.close()

    def execute_queue_task_delayed():
        queue_entry = qlist.pop(0)
        action = queue_entry['action']
        src = queue_entry['src']
        LOG.info("popped from secondary queue: action: %s, src: %s", action, src)
        if action == 'add':
            add_item(Path(src))
        if action == 'delete':
            delete_item(Path(src))
        if action == 'modified':
            update_item_hash_thumb(Path(src))
        if action == 'moved':
            update_item_path(Path(src), Path(queue_entry['dest']))


    # pylint: disable=misplaced-comparison-constant
    try:
        while True:
            time.sleep(0.1) # need to speed this up because the UI is waiting.
            while not QUEUE.empty():
                queue_entry = QUEUE.get_nowait()
                if queue_entry['type'] == 'filesystem-monitor':
                    execute_queue_task_file(queue_entry)
                elif queue_entry['type'] == 'gui':
                    execute_queue_task_gui(queue_entry)
                QUEUE.task_done()

            # now process events from the secondary queue whose time is up,
            # but only do 1 each 1 second of loop iteration
            # in order to not consume too much time, impacting GUI
            if qlist and time.time() > qlist[0]['timestamp']:
                execute_queue_task_delayed()
            # done, back to sleep
            time_counter += 1
            if time_counter > 9:
                time_counter = 0

    except KeyboardInterrupt:
        GLOBAL_DATA.observer.stop()

    GLOBAL_DATA.observer.join()  # wait for observer thread to exit


def walk_directory_tree(directory):
    """inspect every item in the directory tree, add if it is missing"""
    for filesystem_item in directory.iterdir():
        pathname = Path(filesystem_item)
        if pathname.is_dir():  # if directory, descend into it now unless excluded
            if pathname not in IGNORED_DIRECTORIES:
                walk_directory_tree(pathname)
        elif pathname.is_file():  # if regular file, check and add it if required.
            # find the extension and if on an exclude list, just return
            if pathname.suffix in EXCLUDE_EXTENSIONS:
                return
            add_if_missing(pathname)
        else:
            LOG.info(f'skipping: %s - what is this anyway?', pathname)


def initial_scan():
    """do this when first starting up - re-sync with directory tree"""
    # get positioned at the root of file system tree
    os.chdir(ROOT_DIRECTORY)

    # walk the directory tree, adding whatever you find that is missing
    # determine if the database has anything in it, if not, we can blindly add
    walk_directory_tree(Path('.'))

    if GLOBAL_DATA.all_paths.__len__() > 0:
        print('Left over paths from database:')
        for leftover_path in GLOBAL_DATA.all_paths:
            print(str(leftover_path))
            delete_item(leftover_path)

# ----------------------------------------------------
# Callbacks for Web GUI

@bottle_route('/search')
def search_documents():
    """ Bottle handler for our main searches.

    Expect input query string like /search?dirs=a,b,c*labels=x,y,z for directory
    contents and /search?trees=a,b,c*labels=x,y,z for tree contents.

    What do we need for output? We need html code that gives what is necessary
    to load up the main page view. For input we get a list of dirs and a list
     of labels. """

    query_string_dict = bottle_request.query.dict
    # if no dirs or trees in the query string, then mode should be dirs
    dir_mode = True
    if 'dirs' in query_string_dict or 'trees' in query_string_dict:
        if 'dirs' in query_string_dict:
            directories = query_string_dict['dirs']
        else:
            directories = query_string_dict['trees']
            # add wildcard to each directory
            dir_mode = False
        if directories and len(directories) == 1 and directories[0] == '':
            directories = []
        LOG.info(f'directories = {directories}')

    else:
        directories = []

    if 'labels' in query_string_dict:
        labels = query_string_dict['labels']
    else:
        labels = []

    log_msg = f'directories = "{directories}", mode = "{dir_mode}", labels = "{labels}"'
    LOG.info(log_msg)

    textual_sql = ["SELECT path, thumb, labels FROM items "]
    if not directories:
        if not labels:
            LOG.info('no dirs, no label, dir_mode: %s', dir_mode)
            # just do the top level unless in tree mode
            if dir_mode:
                textual_sql.append("WHERE path NOT LIKE '%/%' ")
        else:
            textual_sql.append("WHERE ( ")
            firsttime = True
            for l in labels:
                if firsttime:
                    firsttime = False
                    conn_str = ""
                else:
                    conn_str = " OR "
                textual_sql.append(conn_str + f"labels LIKE '%{l}%' ")
            textual_sql.append(")")

    else: # we have directory pieces
        if not labels:
            # have dirs without labels
            firsttime = True
            textual_sql.append("WHERE (")
            for d in directories:
                if dir_mode:
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{d}/%' AND path NOT LIKE '{d}/%/%')")
                        firsttime = False
                    else:
                        textual_sql.append(f"OR (path LIKE '{d}/%' AND path NOT LIKE '{d}/%/%')")
                else: # tree mode - want all subdirs
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{d}/%')")
                        firsttime = False
                    else:
                        textual_sql.append(" OR (path LIKE '{d}/%')")
            textual_sql.append(")")

        else:   # both labels and dirs
            textual_sql.append("WHERE ( (")
            firsttime = True
            for l in labels:
                if firsttime:
                    firsttime = False
                    conn_str = ""
                else:
                    conn_str = " OR "
                textual_sql.append(conn_str + f"labels LIKE '%{l}%' ")

            textual_sql.append(") AND (")

            firsttime = True
            for d in directories:
                if dir_mode:
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{d}/%' AND path NOT LIKE '{d}/%/%')")
                        firsttime = False
                    else:
                        textual_sql.append(f"OR (path LIKE '{d}/%' AND path NOT LIKE '{d}/%/%')")
                else: # tree mode - want all subdirs
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{d}/%')")
                        firsttime = False
                    else:
                        textual_sql.append(" OR (path LIKE '{d}/%')")
            textual_sql.append(") )")

    LOG.info('textual_sql:')
    LOG.info(repr(textual_sql))

    sqlcommand = None
    try:
        sqlcommand = sqltext(''.join(textual_sql))
    except TypeError as exc:
        msg = '<h2>Error creating SQL query</h2>'
        msg += '<pre>' + str(exc) + '</pre>'
        msg += '<pre>' + str(sqlcommand) + '</pre>'
        LOG.error(msg)
        return msg
    except Exception as exc:
        msg = '<h2>Error creating SQL query</h2>'
        msg += '<pre>' + str(exc) + '</pre>'
        msg += '<pre>' + str(sqlcommand) + '</pre>'
        LOG.error(msg)
        return msg

    queue_entry = {"rows": []}
    try:
        # Ok, we are in the wrong thread to run a SQL query - so use the queues to get
        # the request to the right thread. Results are
        QUEUE.put({'type': 'gui', 'select': sqlcommand})
        while RESULTSQ.empty():
            time.sleep(0.02)
        queue_entry = RESULTSQ.get(True, 150)
        RESULTSQ.task_done()
        # more processing below

    except Exception as exc:
        msg = 'Error executing SQL query'
        msg += '<pre>' + str(exc) + '</pre>'
        msg += '<pre>' + str(sqlcommand) + '</pre>'
        msg += '<h4>Result</h4>'
        msg += '<pre>' + str(queue_entry['rows']) + '</pre>'
        LOG.error(msg)
        return msg

    result_string = '<h2>Search Results:</h2>\n'
    for row in queue_entry['rows']:
        path = row[0]
        thumbnail = f'thumbnails/{row[1]}'
        labels = row[2]
        item_entry = f"""
          <table><tr><td width="200px"><img src="{thumbnail}"><td><b>{path}</b> 
            &nbsp;  &nbsp; <i>Labels: {labels}</i></tr></table><br>
        """
        result_string += item_entry


    LOG.info('Query Results:')
    for row in queue_entry['rows']:
        tstr = f'{row[0]}, {row[1]}, {row[2]}'
        LOG.info(tstr)

    return result_string


@bottle_route('/static_files/<path:path>')
def serve_static(path):
    """
    General service of static file paths
    """
    # if sys.platform == 'linux':
    #     new_path = SCRIPT_DIR.joinpath(path)
    # else:
    #     new_path = SCRIPT_DIR.joinpath(PureWindowsPath(path))
    try:
        LOG.info('serving static path %s', path)
        return static_file('static_files/'+path, root=str(SCRIPT_DIR))
    except Exception as exception_info:
        LOG.info('Exception in serving static_file(): ')
        LOG.info(sys.exc_info())
        LOG.info(exception_info)
        return "error"


@bottle_route('/thumbnails/<path:path>')
def serve_thumb(path):
    """
    General service of thumbnail image file paths
    """
    try:
        LOG.info('serving thumbnail %s', path)
        return static_file(path, root=str(THUMBNAIL_DIRECTORY))
    except Exception as exception_info:
        LOG.info('Exception in serving static_file(): ')
        LOG.info(sys.exc_info())
        LOG.info(exception_info)
        return "error"


@bottle_route('/')
def handle_home_path():
    """routing for / is to static_files/html/home.html """

    path = 'static_files/html/home.html'
    LOG.info('serving home_path:  %s', path)
    return static_file(path, root=str(SCRIPT_DIR))


@bottle_route('/favicon.ico')
def favicon():
    path = 'static_files/img/favicon.png'
    return static_file(path, root=str(SCRIPT_DIR))


# pylint: disable-too-many-nested-blocks
@bottle_route('/browselist')
def browse_list():
    "return JSON data on the file/directory structure"

    # do I NOT already have up-to-date browse list?
    if GLOBAL_DATA.browse_list_object is None or GLOBAL_DATA.updates_browse_list:

        if GLOBAL_DATA.browse_list_object is not None:
            # delete the existing tree of BLPathTreeNode objects
            GLOBAL_DATA.browse_list_object.delete_tree()
            del GLOBAL_DATA.browse_list_object

        # I am now updating it, so clear updates flag
        GLOBAL_DATA.updates_browse_list = False

        # a little safety check before the database query
        if GLOBAL_DATA.tb_items is None:
            LOG.error(f'GLOBAL_DATA.tb_items is None in search_path')
            raise NotImplementedError('Database data structures not ready')

        # do database query - this must happen in the main thread because that
        # is where the SQLite objects are created and must be used. So put
        # the request on the queue QUEUE and wait for the results on the queue
        # RESULTSQ
        sel = sqlselect([GLOBAL_DATA.tb_items.c.path,]).order_by('path')
        QUEUE.put({'type': 'gui', 'select': sel})

        while RESULTSQ.empty():
            time.sleep(0.01)

        # set a longer timeout, cause we're not handling it if it expires
        queue_entry = RESULTSQ.get(True, 150)
        rows = queue_entry['rows']
        RESULTSQ.task_done()

        # convert to tree representation
        current_directory = Path('')
        current_node = BLPathTreeNode('{root}')
        GLOBAL_DATA.browse_list_object = current_node

        # REMEMBER: every row returned has a file and not a directory
        for row in rows:
            new_file_path = Path(row[0])
            new_file_parts = new_file_path.parts

            current_parts = current_directory.parts
            # test for the case that the new_file or current is just a file, with no directory given
            if len(new_file_parts) == 1:
                # new is just a file, what about current?
                if len(current_parts) == 1:
                    # ok, we are transitioning from top level file to top level file,
                    # no directory action necessary
                    pass
                else:
                    # new is just a file, old was a subdirectory, so we can drop dir stuff
                    current_directory = Path('')
                    current_node = GLOBAL_DATA.browse_list_object
            else:
                # now, new file in subdirectory, what about current
                if len(current_parts) == 1:
                    # current is top-level file, now build dir structure of new, if it doesn't exist
                    current_node = current_node.create_path(new_file_parts)
                    current_node.add_child(new_file_parts[-1]) # then add the file
                else:
                    # have we come to the same directory?
                    if len(current_parts) == len(new_file_parts) - 1:
                        idx = 0
                        no_deal = False
                        for current_part in current_parts:
                            if current_part != new_file_parts[idx]:
                                no_deal = True
                                break
                            idx += 1
                        if no_deal:
                            # just work through the path
                            current_node = current_node.create_path(new_file_parts)
                            current_node.add_child(new_file_parts[-1])
                        else:
                            # current directory is the same as the new one, so just add the node
                            current_node.add_child(new_file_parts[-1])
                    else: # new file parts has different number of parts than current, so
                        # just work through the path
                        current_node = current_node.create_path(new_file_parts)
                        current_node.add_child(new_file_parts[-1])


        # processed all data returned from dB query. Now, generate the output.
    # else - already had an up-to-date browse list


    final_output = '{"core": {"data": [{"text": "{root}", "state": {"opened": true},"children": ['
    final_output += GLOBAL_DATA.browse_list_object.repr_children()
    final_output += ']}]}}'

    return final_output

    # from above, for output, we need a string like this:  {
    #     "core": {
    #         "data": [{
    #             "text": "Root node",
    #             "state": {"opened": true},
    #             "children": [
    #                 {"text": "File.1", "icon": "jstree-file"},
    #                 {"text": "Dir.2",
    #                  "children": [
    #                      {"text": "Dir.3"},
    #                      {"text": "File.4", "icon": "jstree-file"}
    #                  ]
    #                  }]
    #         }]
    #     }
    # }


@bottle_route('/labels')
def get_labels():
    "return JSON of array of labels"

    sel = sqlselect([GLOBAL_DATA.tb_labels.c.label, ]).order_by('label')
    QUEUE.put({'type': 'gui', 'select': sel})

    while RESULTSQ.empty():
        time.sleep(0.01)  # Again, keep this timing tight, user is waiting!

    # set a longer timeout, cause we're not handling it if it expires
    queue_entry = RESULTSQ.get(True, 150)
    rows = queue_entry['rows']
    RESULTSQ.task_done()
    results = [str(r[0]) for r in rows]

    return json.dumps(results)


# other bottle notes
    # bottle_response.set_header('Kevin', 'Buchs')
    # bottle_response.status = 200

    # @bottle_route('/name/<name>')
    # def xname(name):
    #     """routing for /name/<name>"""
    #     return f'you entered a url of /name/${name}'


def run_ui():
    """
    Start up the bottle server - running this entire function in a
    separate thread.
    """
    bottle_run(host='0.0.0.0', port=NETWORK_PORT, debug=True)


def main():
    """top level function"""

    # initially, scan the whole directory to rationalize any changes
    initial_scan()

    # run the web UI in other process
    Thread(group=None, target=run_ui, name="run_ui").start()
    time.sleep(0.5)  # let web server spin up, then open 'home' page
    webbrowser.open_new_tab(f'http://localhost:{NETWORK_PORT}/')

    # run the filesystem monitor in other process
    monitor_filesystem()

    # in this process, run a loop looking for work on the QUEUE or a
    # keyboard interrupt.
    monitor_queue()


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--clear', dest='clear', action='store_true',
                        help='wipe any existing data and recreate')
    args = parser.parse_args()
    WIPE_EXISTING = args.clear  # False/True for testing only, clear the board before we run if True
    if WIPE_EXISTING:
        print('clearing data to start fresh')
        if DATABASE_PATH.exists():
            DATABASE_PATH.unlink()
        rmtree(THUMBNAIL_DIRECTORY)

    GLOBAL_DATA = GlobalData()
    main()
