""" provides GUI """

import os
from bottle import route, run, template

INDEX_HTM = '''My first web app! By <strong>{{ author }}</strong>.'''


@route('/')
def index():
    "routing for /"
    return template(INDEX_HTM, author='Real Python')


@route('/name/<name>')
def xname(name):
    "routing for /name/<name>"
    return template(INDEX_HTM, author=name)


if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8080))
    run(host='0.0.0.0', port=PORT, debug=True)
