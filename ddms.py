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
"""

from imports import *     # need these in root namespace
from constants import *   # root namespace

# put a placeholder - so IDE works - this gets assigned for real in main()
GLOBAL_DATA = None

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
    """For a nodee of the browse list tree. object is the node in directory tree for browse list"""

    def __init__(self, path, node_type, parent=None):
        self.path = path
        self.type = node_type # 'file' or 'dir'
        self.parent = parent
        self.children = []

    def repr_children(self):
        """iterates over the children of a node, returning the recursive depth-first
        grandchildren"""
        output = ''
        for child in self.children:
            part_output = repr(child)
            if not (not BROWSE_LIST_INCLUDE_FILES and part_output == ''):
                output += part_output + ', '
            else:
                print('skipped file: ', child.path)
            # else: this is a file and we are not including those
        # omit the final comma and space
        return output[0:-2]

    def __repr__(self):
        """
        Override this function so we can output a JSON string representation via repr(obj)
        """
        if self.repr_children():   # i.e. are there children, if no, this is a file node
            output = f'{{"text": "{self.path}", '
            output += '"children": ['
            output += self.repr_children()
            output += ']}'
            return output

        if BROWSE_LIST_INCLUDE_FILES:
            output = f'{{"text": "{self.path}", '
            output += '"icon": "jstree-file"}'
            return output

        return ''


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


def bl_output_directories_structure():
    """
    Used to output json structure for browse list from just a list of directories instead of the
    above tree.
    """

    def closeout(levels):
        """Close out levels of hierarchy"""
        return ' ]} ' * levels

    output_string = ''
    parents_stack = list()

    for dire in GLOBAL_DATA.browse_list_object:
        path = Path(dire)
        path_parts = list(path.parts)
        path_len = len(path_parts)
        # after initial output, we need to separate each item with a comma.
        # if output_string:  # when output_str != ''
            # more logic goes here..:
            # output_string += ',' # insert comma at the beginning of each line

        if parents_stack:
            parents_len = len(parents_stack)
            matchthru = -1
            for idx in range(min(parents_len, path_len)):
                if parents_stack[idx] == path_parts[idx]:
                    matchthru = idx
                else:
                    break
            if matchthru == -1:
                output_string += closeout(parents_len)
                output_string += ', '
                del parents_stack[0:]  # empty list and then start from the top which

            elif matchthru < len(parents_stack) - 1:
                # have a partial match - closeout parent to that extent and then add
                output_string += closeout(parents_len - matchthru)
                output_string += ', '
                extend_parents = matchthru + 1
                for pcounter in path_parts[extend_parents:]:
                    output_string += f'{{"text": "{pcounter}", "children": ['
                    parents_stack[extend_parents] = pcounter
                    extend_parents += 1

            elif matchthru == parents_len - 1:
                # full match, so we just add children
                index = extend_parents = matchthru + 1
                for pcounter in path_parts[extend_parents:]:
                    output_string += f'{{"text": "{pcounter}", "children": ['
                    # print(f'len of parents_statck = {len(parents_stack)}, \
                    #   add entry via index {index}')
                    parents_stack.append(pcounter)
                    index += 1

            else:
                print("ERROR: should not happen #1")

        # either first starting out or have returned to the top level (just above)
        if not parents_stack:
            for pcounter in path_parts:
                output_string += f'{{"text": "{pcounter}", "children": ['
            parents_stack = path_parts

        # print(f'loop, os={output_string}')


    output_string += closeout(len(parents_stack))
    return output_string

    # desired format:
    #  {"text": "Dir.2",
    #    "children": [
    #       {"text": "Dir.3"},
    #       {"text": "Dir.4"}
    #    ]
    #  }


class GlobalData:
    """
    Holds various global values, pointers to services and database information
    for handy reference.
    """
    # py lint: disable=too-many-instance-attributes
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
                              Column('dir', String, index=True),
                              Column('path', String, primary_key=True, index=True),
                              Column('shahash', String, index=True),
                              Column('thumb', String),
                              Column('labels', String),
                              Column('bibleref', String, index=True),
                              Column('related', String),
                              Column('date_created', String))

        self.tb_labels = Table('labels', metadata,
                               Column('label', String, index=True))

        self.tb_mdata = Table('mdata', metadata,
                         Column('keycol', String, primary_key=True, index=True),
                         Column('valcol', String))

        self.tb_new = Table('new', metadata,
                            Column('path', String, primary_key=True))

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
        # sel = sqlselect([self.tb_labels.c.label, ]).order_by('label')
        # result = self.db_conn.execute(sel)
        # rows = result.fetchall()
        # result.close()
        # existing = [str(r[0]) for r in rows]
        # # which of desired_fruits is not already in table?
        # fruits = [f for f in DESIRED_FRUITS if f not in existing]
        # insert = self.tb_labels.insert(None)
        # for label in fruits:
        #     self.db_conn.execute(insert, label=label)

        # Other important data structures
        self.browse_list_object = None
        self.updates = False
        self.updates_browse_list = False
        self.search_results_map = None
        self.search_results_biblerefs = None
        self.New = False  # indicate whether new items have been added

    def nothing(self):
        """Keeping pylint happy"""


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
        # print(f'search_path: row[1] "{row[1]}" of type {type(row[1])}' \
        #      + f' row[3] "{row[3]}" of type {type(row[3])}')
        # sys.stdout.flush()
        if row[3] is None:
            item = ItemEntry(Path(row[1]), row[2], row[3], row[4])
        else:
            item = ItemEntry(Path(row[1]), row[2], Path(row[3]), row[4])
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

        
        


def get_preview(pathname):
    """ get jpeg preview of item """
    if isinstance(pathname, Path):
        pathname = str(pathname)
    try:
        preview = GLOBAL_DATA.preview.get_jpeg_preview(pathname, height=200, width=200)
        thumb_path = str(Path(preview).relative_to(THUMBNAIL_DIRECTORY))
        LOG.info('Preview generation complete')
    except Exception:
        ## handle unsupported mimetype exception -- create blank jpg file
        # preview = str(THUMBNAIL_DIRECTORY.joinpath( \
        #    str(random.randrange(100000000, 999999999)) + '.jpeg'))
        # open(preview, 'a').close()
        LOG.info('Preview generation failed, no thumbnail created')
        thumb_path = None

    return thumb_path


def add_item(pathname, shahash=None):
    """add a completely new item to database"""
    global GLOBAL_DATA

    LOG.info('adding item')
    str_pathname = str(pathname)
    str_dir = str(pathname.parent)
    if str_dir == '.':
        str_dir = ''

    if shahash is None:
        # Handle exception thrown if file is deleted between discovery and adding.
        try:
            shahash = get_hash(pathname)
        except:
            LOG.info('File has disappeared')
            return
    # generate jpeg thumbnail file and capture its path as string

    thumb_path = get_preview(pathname)

    # just for development - we will assign a random fruit label 50% of the time.
    # random_int = random.randrange(2*len(DESIRED_FRUITS))
    # if random_int < len(DESIRED_FRUITS):
    #     labels = DESIRED_FRUITS[random_int]
    # else:
    #     labels = ''

    labels = ''
    insert = GLOBAL_DATA.tb_items.insert(None)
    GLOBAL_DATA.db_conn.execute(insert, dir=str_dir, path=str_pathname, shahash=shahash,
                                thumb=thumb_path, labels=labels, bibleref=None, date_created=time.ctime(os.path.getctime(str_pathname)))
    # add to new items table
    insert = GLOBAL_DATA.tb_new.insert(None)
    GLOBAL_DATA.db_conn.execute(insert, path=str_pathname)

    # set the New flag
    GLOBAL_DATA.New = True

    LOG.info('Added item: %s', pathname)


def update_item_path(old_pathname, new_pathname):
    """update an existing database entry"""
    str_new_dir = str(new_pathname.parent)
    if str_new_dir == '.':
        str_new_dir = ''

    update = GLOBAL_DATA.tb_items.update(None) \
        .where(GLOBAL_DATA.tb_items.c.path == str(old_pathname)) \
        .values(dir=str_new_dir, path=str(new_pathname))
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
        thumb_path = get_preview(pathname)
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
        if item.thumbnail:
            thumb = Path(item.thumbnail)
            if thumb.exists():
                thumb.unlink()
        # delete item from database
        dele = GLOBAL_DATA.tb_items.delete(None).where(GLOBAL_DATA.tb_items.c.path == str(pathname))
        GLOBAL_DATA.db_conn.execute(dele)

        # and from new table if present
        dele = GLOBAL_DATA.tb_new.delete(None).where(GLOBAL_DATA.tb_new.c.path == str(pathname))
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
        if result is not None:
            try:
                RESULTSQ.put({'rows': result.fetchall()})
                result.close()
            except:
                RESULTSQ.put({'rows': None})
        else:
            RESULTSQ.put({'rows': None})

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


def initial_file_scan():
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



# -----------------------------------------------------------------------------------------------------
# Callbacks for Web GUI and helper functions

def generate_search_output(queue_entry):

    # this is the top menu-bar for the search results
    result_string = """
    <div class="mt-4 mb-2">
      <table class="bottom-border" width="100%">
        <tr>
          <td><b class="h4">Search Results:</b></td>
          <td>
            <span class="float-right" valign="middle">
              <button id="mark-action" class="nav-button p-0 mr-1 btn-sm btn-primary compact-button"
                 onclick="check_bulk_action()">
                 bulk action</button>
              <button id="mark-selected" class="nav-button p-0 mx-1 btn-sm btn-primary compact-button"
                onclick="mark_selected()">mark selected</button>
              <span class="ml-1 mr-0 mark-check">
                <input type="checkbox" id="checkbox-for-all" onchange="mark_all()"
                    valign="middle">
              </span>
            </span>
          </td>
        </tr>
      </table>
    </div>
    """


    GLOBAL_DATA.search_results_map = item_map = list()
    GLOBAL_DATA.search_results_biblerefs = biblerefs_map = list()
    item_counter = 0
    for row in queue_entry['rows']:
        path = row[0]
        item_map.append(path)

        if row[1]:  # handle blank thumbnail path
            thumbnail = f'thumbnails/{row[1]}'
        else:
            thumbnail = '/static_files/img/no-preview.png'

        if thumbnail is None:
            print(f'Thumbnail is None for {path}')
            thumbnail = '/static_files/img/no-preview.png'

        labels_str = f'<span id="labels-for-{item_counter}">'
        if row[2]:
            labels = row[2].split(',')
            separator = ''  # for first entry don't need to add a comma and space
            for label in labels:
                if not label:
                    continue  # skip blank ones

                label_key = f'search-{item_counter}-{label}'
                labels_str += f'<span id="{label_key}">{separator}{label}<span class="ml-1">'   \
                              + '<img src="/static_files/img/x-button.png" width="16px" ' \
                              + f'onclick="remove_a_label(\'{label_key}\')">' \
                              + '</span></span>'
                separator = ', '  # subsequently, separate with comma + space

        labels_str += '</span><button class="ml-2 p-0 btn-sm btn-primary compact-button"' \
            + f'onclick="start_add_a_label(\'search-{item_counter}\')" data-toggle="modal"' \
            + f'data-target="#add_label_modal">add</button>'


        if row[3]:
            biblerefs = row[3].split(',')
            biblerefs_str = f'<span id="biblerefs-for-{item_counter}" num="{len(biblerefs)}">'
            # we will only add things to this map, not remove them. This keeps the bibleref_nums fixed
            biblerefs_map.append(biblerefs)
            bibleref_cntr = 0
            separator = ''  # for first entry don't need to add a comma and space
            for bibleref in biblerefs:
                if not bibleref:
                    bibleref_cntr += 1
                    continue  # skip blank ones

                bibleref_key = f'search-{item_counter}-BR{bibleref_cntr}'
                biblerefs_str += f'<span id="{bibleref_key}">{separator}{bibleref}<span class="ml-1">'   \
                              + '<img src="/static_files/img/x-button.png" width="16px" ' \
                              + f'onclick="remove_a_bibleref(\'{bibleref_key}\')">' \
                              + '</span></span>'
                separator = ', '  # subsequently, separate with comma + space
                bibleref_cntr += 1

        else:
            biblerefs_str = f'<span id="biblerefs-for-{item_counter}" num="0">'
            biblerefs_map.append(list())  # create an entry for each one, even if it is blank.

        biblerefs_str += '</span><button class="ml-2 p-0 btn-sm btn-primary compact-button"' \
                      + f'onclick="start_add_a_bibleref(\'search-{item_counter}\')" data-toggle="modal"' \
                      + f'data-target="#add_bibleref_modal">add</button>'


        if row[4]:
            related_items = row[4].split(',')
            related_str = f'<span id="relateds-for-{item_counter}" num="{len(related_items)}">'
            related_cntr = 0
            separator = ''  # for first entry don't need to add a comma and space
            for related_item in related_items:
                related_key = f'search-{item_counter}-R{related_cntr}'
                related_str += f'<span id="{related_key}">{separator}{related_item}<span class="ml-1">'   \
                              + '<img src="/static_files/img/x-button.png" width="16px" ' \
                              + f'onclick="remove_a_related(\'{related_key}\')">' \
                              + '</span></span>'
                separator = ', '  # subsequently, separate with comma + space
                related_cntr += 1

        else:
            related_str = f'<span id="related-for-{item_counter}" num="0">'

        if row[5] == 1:
            new_indicator = f'<span class="ml-2" id="new-indicator-{item_counter}">' \
                              + f'<img src="/static_files/img/new.png" width="60px" ' \
                              + f'onclick="confirm_new_remove(\'{item_counter}\')"></span>'
        else:
            new_indicator = ''

        if row[6]:
            date_created = f'{row[6]}'
        else:
            date_created = f'Not available'

        item_entry = f"""
          <table width="100%" class="mt-2"><col width="230px"><col><col width="20px">
              <tr><td width="230px" height="200px" class="align-top"><img src="{thumbnail}"></td>
                  <td class="align-top">
                     <table>
                        <tr><td><b class="bigpath path-{item_counter}">{path}</b>{new_indicator}</td></tr>               
                        <tr><td><i>Labels: {labels_str}</i></td></tr>
                        <tr><td><i>Biblerefs: {biblerefs_str}</i></td></tr>
                        <tr><td><i>Related: {related_str}</i></td></tr>
                        <tr><td><i>Date Created: {date_created}</i></td></tr>
                     </table>
                  </td>
                  <td class="align-top mark-check"><span class="ml-auto mr-0 p-0">
                     <input type="checkbox" class="item-checkbox"
                      id="checkbox-for-{item_counter}"></span>
                  </td>
              </tr>
          </table>
        """
        result_string += item_entry
        item_counter += 1

    return result_string



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

    else:
        directories = []

    # correct windows backslashes to forward.
    # Scratch this -- need to do the correction in the sql instead since paths have backslashes in the database
    # for idx, dire in enumerate(directories):
    #   if '\\' in dire:
    #        directories[idx] = dire.replace('\\','/')
    #        LOG.info(directories[idx])

    if 'labels' in query_string_dict:
        labels = query_string_dict['labels']
    else:
        labels = []

    # log_msg = f'directories = "{directories}", mode = "{dir_mode}", labels = "{labels}"'
    # LOG.info(log_msg)

    textual_sql = ["SELECT items.path, items.thumb, items.labels, items.bibleref, " \
                   "items.related, EXISTS(select new.path from new where (new.path == items.path)), items.date_created FROM items ", ]
    if not directories:
        if not labels:
            # LOG.info('no dirs, no label, dir_mode: %s', dir_mode)
            # just do the top level unless in tree mode
            if dir_mode:
                textual_sql.append("WHERE ( path NOT LIKE '%/%' )")
        else:
            textual_sql.append("WHERE ( ")
            firsttime = True
            for label in labels:
                if firsttime:
                    firsttime = False
                    conn_str = ""
                else:
                    conn_str = " OR "
                textual_sql.append(conn_str + f"labels LIKE '%{label}%' ")
            textual_sql.append(")")

    else: # we have directory pieces
        if not labels:
            # have dirs without labels
            firsttime = True
            textual_sql.append("WHERE (")
            for dire in directories:
                if dir_mode:
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{dire}/%' AND path NOT LIKE '{dire}/%/%')")
                        firsttime = False
                    else:
                        textual_sql.append(f"OR (path LIKE '{dire}/%' AND path NOT LIKE " \
                                               + f"'{dire}/%/%')")
                else: # tree mode - want all subdirs
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{dire}/%')")
                        firsttime = False
                    else:
                        textual_sql.append(" OR (path LIKE '{d}/%')")
            textual_sql.append(")")

        else:   # both labels and dirs
            textual_sql.append("WHERE ( (")
            firsttime = True
            for label in labels:
                if firsttime:
                    firsttime = False
                    conn_str = ""
                else:
                    conn_str = " OR "
                textual_sql.append(conn_str + f"labels LIKE '%{label}%' ")

            textual_sql.append(") AND (")

            firsttime = True
            for dire in directories:
                if dir_mode:
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{dire}/%' AND path NOT LIKE '{dire}/%/%')")
                        firsttime = False
                    else:
                        textual_sql.append(f"OR (path LIKE '{dire}/%' AND path NOT LIKE "  \
                                               f"'{dire}/%/%')")
                else: # tree mode - want all subdirs
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{dire}/%')")
                        firsttime = False
                    else:
                        textual_sql.append(" OR (path LIKE '{d}/%')")
            textual_sql.append(") )")

    # LOG.info('textual_sql: %s', str(','.join(textual_sql)))

    
    sqlcommand = None
    try:
        if sys.platform == 'linux':
            sqlcommand = sqltext(''.join(textual_sql))
        else:
            #replace forward slashes with backslashes in Windows
            sqlcommand = sqltext(''.join(textual_sql).replace('/','\\'))
        #LOG.info(sqlcommand)
    
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


    return generate_search_output(queue_entry)


@bottle_route('/search_bible')
def search_biblerefs():
    """ Bottle handler for our bibleref searches.
    Expect input query string like /search_bible?labels=x,y,z;biblerefs=a,b,c .

    What do we need for output? We need html code that gives what is necessary
    to load up the main page view. For input we get a list of labels and a list
     of biblerefs. """

    query_string_dict = bottle_request.query.dict

    if 'biblerefs' in query_string_dict:
        raw_biblerefs = query_string_dict['biblerefs']
        search_keys_verses = list()
        search_keys_passages = list()
        for rb in raw_biblerefs:
            if rb.count('-') == 1:
                search_keys_passages.append(bible.Passage(rb))
            else:
                search_keys_verses.append(bible.Verse(rb))

    else:
        LOG.error('/search_biblerefs called without biblerefs!')
        return 'ERROR in search - no biblerefs given'

    labels = [rlabel for rlabel in query_string_dict['labels']
               if rlabel and len(rlabel) > 0]

    textual_sql = ["SELECT items.path, items.thumb, items.labels, items.bibleref, " \
                   "items.related, EXISTS(select new.path from new where (new.path == items.path)), items.date_created FROM items ", ]
    if labels:
        textual_sql.append("WHERE ( ")
        conn_str = ''
        for label in labels:
            textual_sql.append(conn_str + f"labels LIKE '%{label}%' ")
            conn_str = ' OR '
        textual_sql.append(")")

    LOG.info('textual_sql: %s', str(''.join(textual_sql)))

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

    # Next, look through the results for hits on the biblereferences and
    # add row to list
    hits = list()
    for row in queue_entry['rows']:
        if row[3]:
            item_biblerefs = row[3].split(',')
            found_hit = False
            for ib in item_biblerefs:
                if ib.count('-') == 1:
                    test_passage = bible.Passage(ib)
                    for key in search_keys_verses:
                        if test_passage.includes(key):
                            hits.append(row)
                            found_hit = True
                            break  # if a hit, we have nested loops to breakout of, so break out of inner
                    if found_hit:
                        break  # break out of outer loop on hit
                    for key in search_keys_passages:
                        if key.overlap(test_passage):
                            hits.append(row)
                            found_hit = True
                            break
                    if found_hit:
                        # we have captured, so move on to the next
                        break
                else:  # no dashes - not a range
                    test_verse = bible.Verse(ib)
                    for key in search_keys_verses:
                        if test_verse == key:
                            hits.append(row)
                            found_hit = True
                            break
                    if found_hit:
                        break
                    for key in search_keys_passages:
                        if key.includes(test_verse):
                            hits.append(row)
                            found_hit = True
                            break
                    if found_hit:
                        break

    # we create a simulated queue_entry, with filtered rows - pass that to the output
    # generator and return that.
    return generate_search_output({'rows': hits})




@bottle_route('/search_new')
def search_new_documents():
    """ Bottle handler for our new item searches.

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

    else:
        directories = []

    # correct windows backslashes to forward.
    for idx, dire in enumerate(directories):
        if '\\' in dire:
            directories[idx] = dire.replace('\\','/')

    if 'labels' in query_string_dict:
        labels = query_string_dict['labels']
    else:
        labels = []

    where_present = False  # whether a WHERE class as already been started

    textual_sql = ["SELECT items.path, items.thumb, items.labels, items.bibleref, " \
                   + "items.related, EXISTS(select new.path from new where (new.path == items.path)), items.date_created FROM items ", ]
    if not directories:
        if not labels:
            # just do the top level unless in tree mode
            if dir_mode:
                textual_sql.append("WHERE (path NOT LIKE '%/%' ")
                where_present = True
        else:
            textual_sql.append("WHERE ( ")
            where_present = True
            firsttime = True
            for label in labels:
                if firsttime:
                    firsttime = False
                    conn_str = ''
                else:
                    conn_str = ' OR '
                textual_sql.append(conn_str + f"labels LIKE '%{label}%' ")

    else: # we have directory pieces
        if not labels:
            # have dirs without labels
            firsttime = True
            textual_sql.append("WHERE (")
            where_present = True
            for dire in directories:
                if dir_mode:
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{dire}/%' AND path NOT LIKE '{dire}/%/%')")
                        firsttime = False
                    else:
                        textual_sql.append(f"OR (path LIKE '{dire}/%' AND path NOT LIKE " \
                                               + f"'{dire}/%/%')")
                else: # tree mode - want all subdirs
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{dire}/%')")
                        firsttime = False
                    else:
                        textual_sql.append(" OR (path LIKE '{d}/%')")

        else:   # both labels and dirs
            textual_sql.append("WHERE ( (")
            where_present = True
            firsttime = True
            for label in labels:
                if firsttime:
                    firsttime = False
                    conn_str = ""
                else:
                    conn_str = " OR "
                textual_sql.append(conn_str + f"labels LIKE '%{label}%' ")

            textual_sql.append(") AND (")

            firsttime = True
            for dire in directories:
                if dir_mode:
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{dire}/%' AND path NOT LIKE '{dire}/%/%')")
                        firsttime = False
                    else:
                        textual_sql.append(f"OR (path LIKE '{dire}/%' AND path NOT LIKE "  \
                                               f"'{dire}/%/%')")
                else: # tree mode - want all subdirs
                    if firsttime:
                        textual_sql.append(f"(path LIKE '{dire}/%')")
                        firsttime = False
                    else:
                        textual_sql.append(" OR (path LIKE '{d}/%')")
            textual_sql.append(") ")

    # Add the NEW condition
    if where_present:
        textual_sql.append(" AND ")
    else:
        textual_sql.append("WHERE ( ")

    textual_sql.append(" path in (SELECT path FROM new) )")

    LOG.info('textual_sql: %s', str(' '.join(textual_sql)))

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

    # OK, arbitrary choice - once you search the new items, clear the hot indicator
    GLOBAL_DATA.New = False

    return generate_search_output(queue_entry)



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

        if BROWSE_LIST_INCLUDE_FILES:
            sel = sqlselect([GLOBAL_DATA.tb_items.c.path,]).order_by('path')
        else:
            sel = sqlselect([GLOBAL_DATA.tb_items.c.dir, ]).where('dir' != '')

        QUEUE.put({'type': 'gui', 'select': sel})

        while RESULTSQ.empty():
            time.sleep(0.01)

        # set a longer timeout, cause we're not handling it if it expires
        queue_entry = RESULTSQ.get(True, 150)
        rows = queue_entry['rows']
        RESULTSQ.task_done()

        if BROWSE_LIST_INCLUDE_FILES:

            # convert to tree representation
            current_directory = Path('')
            current_node = BLPathTreeNode('{root}')
            GLOBAL_DATA.browse_list_object = current_node

            # REMEMBER: every row returned has a file and not a directory
            for row in rows:
                new_file_path = Path(row[0])
                new_file_parts = new_file_path.parts

                current_parts = current_directory.parts
                # test for the case that the new_file or current
                # is just a file, with no directory given
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
                        # current is top-level file, now build dir structure
                        # of new, if it doesn't exist
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

        else: # not BROWSE_LIST_INCLUDE_FILES
            # this is simplified vs above
            if GLOBAL_DATA.browse_list_object is not None:
                del GLOBAL_DATA.browse_list_object
            dirs_used = list()
            GLOBAL_DATA.browse_list_object = dirs_used
            top_dir = Path('.')
            slash_dir = Path('/')
            for row in rows:
                dire = row[0]
                if dire and top_dir != dire and slash_dir != dire and dire not in dirs_used:
                    dirs_used.append(dire)

        # processed all data returned from dB query. Now, generate the output.

    # else - already had an up-to-date browse list

    final_output = '{"core": {"data": [{"text": "{root}", "state": {"opened": true},"children": ['

    if BROWSE_LIST_INCLUDE_FILES:
        final_output += GLOBAL_DATA.browse_list_object.repr_children()
    else:
        final_output += bl_output_directories_structure()

    final_output += ']}]}}'
    # print('browse list:\n', final_output)
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



@bottle_route('/remove_label')
def remove_label():
    # /remove_label?id=search-2-peaches
    label_id = bottle_request.query.id
    parts = label_id.split('-')
    assert len(parts) == 3
    assert parts[0] == 'search'
    path = GLOBAL_DATA.search_results_map[int(parts[1])]
    label = parts[2]
    # get existing labels
    textual_sql = f"SELECT labels from items WHERE path = '{path}';"
    sqlcommand = sqltext(textual_sql)
    QUEUE.put({'type': 'gui', 'select': sqlcommand})
    while RESULTSQ.empty():
        time.sleep(0.01)
    # set a longer timeout, cause we're not handling it if it expires
    queue_entry = RESULTSQ.get(True, 150)
    rows = queue_entry['rows']
    RESULTSQ.task_done()
    assert len(rows) == 1
    existing_labels = (rows[0][0]).split(',')
    if existing_labels.count(label) >= 0:
        existing_labels.remove(label)
        new_label_str = ','.join(existing_labels)
        textual_sql = f"UPDATE items set labels = '{new_label_str}' WHERE path = '{path}';"
        sqlcommand = sqltext(textual_sql)
        QUEUE.put({'type': 'gui', 'select': sqlcommand})
        while RESULTSQ.empty():
            time.sleep(0.01)
        # set a longer timeout, cause we're not handling it if it expires
        queue_entry = RESULTSQ.get(True, 150)
        RESULTSQ.task_done()

        # now - update the labels table, as needed
        # 1. are there any other items still having the same label?
        textual_sql = f"SELECT labels from items where labels LIKE '%{label}%'"
        sqlcommand = sqltext(textual_sql)
        QUEUE.put({'type': 'gui', 'select': sqlcommand})
        while RESULTSQ.empty():
            time.sleep(0.01)
        # set a longer timeout, cause we're not handling it if it expires
        queue_entry = RESULTSQ.get(True, 150)
        RESULTSQ.task_done()
        rows = queue_entry['rows']
        if len(rows) == 0:  # no other uses of the label, so can remove it
            textual_sql = f"DELETE FROM labels WHERE label = '{label}';"
            sqlcommand = sqltext(textual_sql)
            QUEUE.put({'type': 'gui', 'select': sqlcommand})
            while RESULTSQ.empty():
                time.sleep(0.01)
            # set a longer timeout, cause we're not handling it if it expires
            queue_entry = RESULTSQ.get(True, 150)
            RESULTSQ.task_done()

        # else nothing needs to be done because the label is still in use
        return 'success'


@bottle_route('/add_label')
def add_label():
    # /add_label?item_id=3;labels=obstanant
    item_id = bottle_request.query.item_id
    path = GLOBAL_DATA.search_results_map[int(item_id)]
    new_labels_str = bottle_request.query.labels
    new_labels = new_labels_str.split(',')
    # get existing labels
    textual_sql = f"SELECT labels from items WHERE path = '{path}';"
    sqlcommand = sqltext(textual_sql)
    QUEUE.put({'type': 'gui', 'select': sqlcommand})
    while RESULTSQ.empty():
        time.sleep(0.01)
    # set a longer timeout, cause we're not handling it if it expires
    queue_entry = RESULTSQ.get(True, 150)
    rows = queue_entry['rows']
    RESULTSQ.task_done()
    assert len(rows) == 1
    raw_labels = str(rows[0][0])
    if raw_labels == '':
        existing_labels = list()
    else:
        existing_labels = raw_labels.split(',')
    updated_labels = list(set(existing_labels + new_labels))  # filter through set() to drop duplicates
    updated_label_str = ','.join(updated_labels)
    textual_sql = f"UPDATE items set labels = '{updated_label_str}' WHERE path = '{path}';"
    sqlcommand = sqltext(textual_sql)
    QUEUE.put({'type': 'gui', 'select': sqlcommand})
    while RESULTSQ.empty():
        time.sleep(0.01)
    # set a longer timeout, cause we're not handling it if it expires
    queue_entry = RESULTSQ.get(True, 150)
    RESULTSQ.task_done()

    # add to labels table, if not already present
    for label in new_labels:
        textual_sql = f"INSERT INTO labels(label) SELECT '{label}' "  \
                + f"WHERE NOT EXISTS(SELECT 1 FROM labels WHERE label = '{label}');"
        sqlcommand = sqltext(textual_sql)
        QUEUE.put({'type': 'gui', 'select': sqlcommand})
        while RESULTSQ.empty():
            time.sleep(0.01)
        # set a longer timeout, cause we're not handling it if it expires
        queue_entry = RESULTSQ.get(True, 150)
        RESULTSQ.task_done()

    return f'added {new_labels_str} to {path}'


@bottle_route('/remove_bibleref')
def remove_bibleref():
    # /remove_bibleref?id=search-2-BR3
    bibleref_id = bottle_request.query.id
    print(f'bibleref_id: {bibleref_id}')
    parts = bibleref_id.split('-')
    assert len(parts) == 3
    assert parts[0] == 'search'
    item_counter = int(parts[1])
    path = GLOBAL_DATA.search_results_map[item_counter]
    bibleref_num = int(parts[2][2:])  # Skip over fixed 'BR' string
    biblerefs = GLOBAL_DATA.search_results_biblerefs[item_counter]

    # keep an entry in the list, but null out the actual reference to keep numbering consistent
    biblerefs[bibleref_num] = None
    prefix = ''
    new_bibleref_str = ''
    for br in biblerefs:
        if br is not None:
            new_bibleref_str += prefix + br
            prefix = ','

    textual_sql = f"UPDATE items set bibleref = '{new_bibleref_str}' WHERE path = '{path}';"
    sqlcommand = sqltext(textual_sql)
    QUEUE.put({'type': 'gui', 'select': sqlcommand})
    while RESULTSQ.empty():
        time.sleep(0.01)
    # set a longer timeout, cause we're not handling it if it expires
    queue_entry = RESULTSQ.get(True, 150)
    RESULTSQ.task_done()
    return 'success'


@bottle_route('/add_bibleref')
def add_bibleref():
    # /add_bibleref?item_id=3;biblerefs=4
    item_id = int(bottle_request.query.item_id)
    path = GLOBAL_DATA.search_results_map[item_id]
    new_biblerefs_str = bottle_request.query.biblerefs
    print(f'add_bibleref called with biblerefs = {new_biblerefs_str}')
    new_biblerefs = new_biblerefs_str.split(',')
    biblerefs_list = GLOBAL_DATA.search_results_biblerefs[item_id]
    starting_num = len(biblerefs_list)
    last_num = starting_num
    for new_bibleref in new_biblerefs:
        if biblerefs_list.count(new_bibleref) == 0:
            biblerefs_list.append(new_bibleref)
            last_num += 1
    ignore_nones = [ br for br in biblerefs_list if br is not None ]
    updated_bibleref_str = ','.join(ignore_nones)
    print(f'updating biblerefs: {updated_bibleref_str}')
    textual_sql = f"UPDATE items set bibleref = '{updated_bibleref_str}' WHERE path = '{path}';"
    sqlcommand = sqltext(textual_sql)
    QUEUE.put({'type': 'gui', 'select': sqlcommand})
    while RESULTSQ.empty():
        time.sleep(0.01)
    # set a longer timeout, cause we're not handling it if it expires
    queue_entry = RESULTSQ.get(True, 150)
    RESULTSQ.task_done()
    print(f'added {new_biblerefs_str} to {path}')
    return last_num

@bottle_route('/relate')
def relate_items():
    raw_items = bottle_request.query.dict['items'][0]
    print('raw_items: ', type(raw_items).__name__)
    print(raw_items)
    items = raw_items.split(',')
    indicies = (int(items[0]), int(items[1]))
    paths = (GLOBAL_DATA.search_results_map[indicies[0]],
             GLOBAL_DATA.search_results_map[indicies[1]])
    textual_sql = f"SELECT path, related from items WHERE path in ('{paths[0]}', '{paths[1]}');"
    sqlcommand = sqltext(textual_sql)
    QUEUE.put({'type': 'gui', 'select': sqlcommand})
    while RESULTSQ.empty():
        time.sleep(0.01)
    # set a longer timeout, cause we're not handling it if it expires
    queue_entry = RESULTSQ.get(True, 150)
    rows = queue_entry['rows']
    RESULTSQ.task_done()
    existing_relateds = ['', '']
    for row in rows:
        which_one = paths.index(row[0])
        other_one = which_one ^ 1
        if row[1] is None:
            new_related = [paths[other_one], ]
        else:
            # filter through set to eliminate duplicates
            new_related = list(set(row[1].split(',') + [paths[other_one],]))
        textual_sql = f"UPDATE items set related = '{','.join(new_related)}' WHERE path = '{row[0]}';"
        sqlcommand = sqltext(textual_sql)
        QUEUE.put({'type': 'gui', 'select': sqlcommand})
        while RESULTSQ.empty():
            time.sleep(0.01)
        # set a longer timeout, cause we're not handling it if it expires
        queue_entry = RESULTSQ.get(True, 150)
        RESULTSQ.task_done()

    return 'relationship established'


# Routes related to New indicator

def check_new_table():
    textual_sql = "SELECT 1 from new;"
    sqlcommand = sqltext(textual_sql)
    QUEUE.put({'type': 'gui', 'select': sqlcommand})
    while RESULTSQ.empty():
        time.sleep(0.01)
    # set a longer timeout, cause we're not handling it if it expires
    queue_entry = RESULTSQ.get(True, 150)
    rows = queue_entry['rows']
    RESULTSQ.task_done()
    if len(rows) > 0:
        return True
    else:
        return False

@bottle_route('/new')
def check_new():
    if GLOBAL_DATA.New:
        return 'hot'
    else:
        if check_new_table():
            return 'cold'
        else:
            return 'none'

@bottle_route('/new-reset')
def reset_new():
    global GLOBAL_DATA
    GLOBAL_DATA.New = False

@bottle_route('/new-remove')
def remove_new():
    """Remove the selected path (via item id) from the new table"""
    item_id = int(bottle_request.query.item_id)
    path = GLOBAL_DATA.search_results_map[item_id]
    textual_sql = f"DELETE FROM new WHERE ( path = '{path}' );"
    sqlcommand = sqltext(textual_sql)
    QUEUE.put({'type': 'gui', 'select': sqlcommand})
    while RESULTSQ.empty():
        time.sleep(0.01)
    # set a longer timeout, cause we're not handling it if it expires
    queue_entry = RESULTSQ.get(True, 150)
    RESULTSQ.task_done()
    # did we happen to remove the last new item? If so, shut off the lights
    if not check_new_table():
        GLOBAL_DATA.New = False



# Routes that serve up files

# ok, this one doesn't quite fit the above category, but it's close
@bottle_route('/items-native/<path:path>')
def open_item_native(path):
    """"
    Starts up native tool for opening a given file
    """
    filepath = str( ROOT_DIRECTORY / path )
    if sys.platform == 'linux':
        subprocess.run(f'/usr/bin/xdg-open {filepath}', shell=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # hoping this works as expected on Windows...
        subprocess.run(filepath, shell=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 'opened'

@bottle_route('/items/<path:path>')
def open_item(path):
    """
    Serves search result files to browser
    """
    return static_file(str(path), root=str(ROOT_DIRECTORY))

@bottle_route('/static_files/<path:path>')
def serve_static(path):
    """
    General service of static file paths
    """
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
    """ Return the favicon """
    path = 'static_files/img/favicon.png'
    return static_file(path, root=str(SCRIPT_DIR))


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
    LOG.info(f'Running bottle UI in thread {threading.get_ident()}')
    bottle_run(host='0.0.0.0', port=NETWORK_PORT, debug=True)


def main():
    """top level function"""
    global GLOBAL_DATA

    # proceess arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--clear', dest='clear', action='store_true',
                        help='wipe any existing data and recreate')
    args = parser.parse_args()

    # pre-run cleanup
    wipe_existing = args.clear  # False/True for testing only, clear the board before we run if True
    if wipe_existing:
        print('clearing data to start fresh')
        if DATABASE_PATH.exists():
            DATABASE_PATH.unlink()
        rmtree(THUMBNAIL_DIRECTORY)

    # Set up lots of stuff
    GLOBAL_DATA = GlobalData()

    # initially, scan the whole directory to rationalize any changes
    initial_file_scan()

    # run the web UI in other process
    threading.Thread(group=None, target=run_ui, name="run_ui").start()
    time.sleep(0.5)  # let web server spin up, then open 'home' page
    # try:
    #     web = webbrowser.open_new_tab(f'http://localhost:{NETWORK_PORT}/')
    #     LOG.info(f'webbrowser returns {web}')
    # except ResourceWarning:
    #     print('Caputred the Resource Warning')

    # run the filesystem monitor in other process
    monitor_filesystem()

    # in this process, run a loop looking for work on the QUEUE or a
    # keyboard interrupt.
    monitor_queue()


if __name__ == "__main__":

    main()
