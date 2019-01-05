""" provides GUI """

import os
from bottle import route, run, template

INDEX_HTM = '''My first web app! By <strong>{{ author }}</strong>.'''


@route('/')
def index():
    "routing for /"
    return template(INDEX_HTM, author='Kevin Buchs')


@route('/name/<name>')
def xname(name):
    "routing for /name/<name>"
    return template(INDEX_HTM, author=name)


if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8080))
    run(host='0.0.0.0', port=PORT, debug=True)


#pylint: disable-pointless-string-statement
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