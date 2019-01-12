""" provides GUI """

import os

from bottle import route, run, template, Bottle, static_file

from sqlalchemy import create_engine, Table, Column, String, MetaData
from sqlalchemy import select as sqlselect

from pathlib import Path


INDEX_HTM = '''My first web app! By <strong>{{ author }}</strong>.'''

# ## Initialize database connection
DATABASE_PATH = Path('C:\\Users\\dbuchs\\Dropbox\\data.sqlite').expanduser().resolve()
db_connection_string = 'sqlite+pysqlite:///' + str(DATABASE_PATH)
db_engine = create_engine(db_connection_string)
db_conn = db_engine.connect()
metadata = MetaData()
tb_items = Table('items', metadata,
              Column('path', String, primary_key=True, index=True),
              Column('shahash', String, index=True),
              Column('thumb', String),
              Column('labels', String))
tb_labels = Table('labels', metadata,
              Column('label', String, index=True))

### Set this constant to define the root dir for serving static files
LOCAL_ROOT = "C:\\Users\\dbuchs\\Dropbox\\"


@route('/')
def index():
    """routing for /"""
    return template(INDEX_HTM, author='Kevin Buchs')

# ## Route for serving up static files -- needed
# ## for serving the thumbnails

@route('/static/<path:path>')
def callback(path):
    return static_file(path, root=LOCAL_ROOT)

# ## Route for showing all the items in the items table
# ## -- calls up the show_all.tpl template file

@route('/showall')
def showall():
    sel = sqlselect([tb_items.c.path, tb_items.c.thumb, tb_items.c.labels])
    result = db_conn.execute(sel)
    return template('show_all', rows=result.fetchall())


@route('/name/<name>')
def xname(name):
    """routing for /name/<name>"""
    return template(INDEX_HTM, author=name)


if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8080))
    run(host='0.0.0.0', port=PORT, debug=True)


# pylint: disable-pointless-string-statement
COMMENTS = """
What does the UI look like?

Kinds of things it should show:
1) a browseable listing of the whole directory tree, just text
2) a display of the results of a search. Search can be from a combination of 0 or more labels and directory path or
   directory tree. This result will have the previews inserted into it. 
3) a click on a file item from the browsable tree or from the search results should either open the file in a new
   browser tab or an external tool. 
   
So, the browseable tree can be a transient GUI feature, click a button and the tree is shown. Make a selection from
the tree and it goes away. Also needs a closer. Each item is a hyperlink. File hyperlinks open the file, 
but directory hyperlinks do a search on that directory.

Up top: [ browseable tree ]   search: [] dir / [] tree, directory: [txt box]  labels: [txt box]  [run search]

Text boxes show the current items. May be populated from a browseable selection or typed into the box, with completion. 
With the labels box: you can type with completion for a comma delimited list or pull up a list (with current
labels already selected. 

Also need an add label pop-up. Choice to lable selected or all items. Maybe we select from a little checkbox by each 
item. Do selection before accessing the label pop-up. 
"""
