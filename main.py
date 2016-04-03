import argparse
import logging
import shutil
import json

from urllib2 import urlopen
from os import path, mkdir

try:
    from os import scandir, walk
except ImportError:
    from scandir import scandir, walk



# Recursively loop over the directory structure
def get_entries(directory):
    entries = scandir(directory)
    if entries:
        for entry in entries:
            if entry.is_file() and check_file(entry.name):
                matches.append(entry)
            if entry.is_dir() and check_directory(entry.name):
                get_entries(entry.path)

# Checks for hidden files like .gitingore or repo specific files likes README and LICENSE
def check_file(filename):
    return not (filename.startswith('.') or filename.rpartition('.')[0].isupper() if filename.__contains__('.') else filename.isupper())

# Checks for hidden directories like .git
def check_directory(dirname):
    return not (dirname.startswith('.'))

# Recursive algorithim that builds directories if they don't exist
def exists_directory(dirpath):
    if path.exists(dirpath):
        return
    else:
        delim_1 = dirpath.find('\\')
        delim_2 = dirpath.find('/')
        split = delim_1 if delim_1 > delim_2 else delim_2
        new_path = dirpath[:split]
        exists_directory(new_path)
        mkdir(path.abspath(dirpath))

parser = argparse.ArgumentParser(description="Setup the jekyll-template in a gh-pages repository")
parser.add_argument("--input", required=True, help="The directory where the jekyll template is stored", dest='in_path' )
parser.add_argument("--output", nargs='?', default='./', const='./', help="The directory of the gh-pages repository", dest='out_path' )

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

args = parser.parse_args()

# Loop over durectory arguments making sure they:
# * All end in '/', important for joining together the paths
# * Exist
for key, value in args.__dict__.items():
    if not (value.endswith('/') or value.endswith('\\')):
        value += '/'
    if not path.exists(value):
        raise ValueError('Directory specified {} not found'.format(value))

in_path = args.__dict__['in_path']
out_path = args.__dict__['out_path']

matches = []
get_entries(in_path)

#Loop over valid files from matches and if they don't exist in the destination copy them across
copies = []
for entry in matches:
    safe_path = entry.path.replace("\\", "/")
    new_path = out_path + (safe_path.replace(in_path, ''))
    if path.exists(new_path):
        logging.info('Exists ' + new_path)
    else:
        exists_directory(new_path.replace(entry.name, ''))
        logging.debug('Moving ' + entry.path + ' to ' + new_path)
        shutil.copy(safe_path, new_path)
        copies.append(new_path)

#Append copied files to .gitignore
with open(out_path+".gitignore", "a") as gitignore:
    gitignore.write('#Ignore as copied from jekyll-docs template\n')
    for ignore in copies:
        gitignore.write(ignore+'\n')
    gitignore.write('#Endignore as copied from jekyll-docs template\n')