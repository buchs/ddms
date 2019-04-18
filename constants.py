from imports import *
# Constants that may need to be changed
# start at the root level, e.g. c:/Users/david/...
if 'USER' in os.environ and os.environ['USER'] == 'buchs' and sys.platform == 'linux':
    # Could be Dad
    ROOT_DIRECTORY = Path('/home/buchs/Play').expanduser().resolve()
    DATABASE_PATH = Path('/home/buchs/Dropbox/DDMS/data.sqlite').expanduser().resolve()
    SCRIPT_DIR = Path('/home/buchs/Dropbox/DDMS')
else:
    # Should be David
    ROOT_DIRECTORY = Path("C:\\Users\\dbuchs\\Dropbox\\DDMS").expanduser().resolve()
    DATABASE_PATH = Path('C:\\Users\\dbuchs\\Dropbox\\data.sqlite').expanduser().resolve()
    SCRIPT_DIR = Path(__file__).expanduser().absolute().parent


THUMBNAIL_DIRECTORY = ROOT_DIRECTORY.joinpath('.thumbnails')

EXCLUDE_EXTENSIONS = ['sqlite']
IGNORED_DIRECTORIES = [Path('.thumbnails')]

NETWORK_PORT = 8080
BROWSE_LIST_INCLUDE_FILES = False

# THINGS CONFIGURED TO SUPPORT DEVELOPMENT
LOG_FILE = 'ddms.log'  # just file name
LOGGING_FORMAT = '%(asctime)-15s  %(message)s'
logging.basicConfig(format=LOGGING_FORMAT)
LOG = logging.getLogger('DDMS')
LOG.setLevel('INFO')
LOG.addHandler(logging.FileHandler(SCRIPT_DIR.joinpath(LOG_FILE)))
