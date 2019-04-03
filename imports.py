import os
import sys
import time
import json
import queue
import random
import shutil
import logging
import argparse
import datetime
import threading
import subprocess
import webbrowser

# About making use of pathlib, instead of os.path and some others.
# Mostly, paths stay Path objects unless a string is required, such as:
# the preview generator and the database storage. Otherwise, we can do
# most things from a Path object, such as reading a byte array from the
# file referenced by the Path object.
from pathlib import Path

from hashlib import sha512  # get sha 512 bit hash with sha512(string)
from shutil import rmtree
from tempfile import TemporaryFile

import bible

# needed setup: pip3.6 install preview_generator, watchdog and sqlalchemy
from preview_generator.manager import PreviewManager
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy import create_engine, Table, Column, String, MetaData
from sqlalchemy import select as sqlselect, text as sqltext,  \
    update as sqlupdate, insert as sqlinsert
from bottle import route as bottle_route, run as bottle_run,  \
    static_file, request as bottle_request
# could include:  template,, response as bottle_response
# noinspection PyPep8,Pylint
from bottle import debug as bottle_debug
