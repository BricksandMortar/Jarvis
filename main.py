import argparse
import logging
import shutil
import json

from os import path, mkdir
from urllib.request import urlopen, Request

import sys

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


# Returns false for hidden files like .gitignore or repo specific files likes README and LICENSE, returns false if
def check_file(filename):
    return not (filename.startswith('.') or filename.rpartition('.')[0].isupper() if filename.__contains__(
        '.') else filename.isupper())


# Returns false for hidden directories like .git
def check_directory(dirname):
    return not (dirname.startswith('.'))


def generate_directories(dirpath):
    dirpath.rstrip('/\\')
    exists_directory(dirpath)


# Recursive algorithm that builds directories if they don't exist
def exists_directory(dirpath):
    if path.exists(dirpath):
        return True
    else:
        delim_1 = dirpath.rfind('\\')
        delim_2 = dirpath.rfind('/')
        split = delim_1 if delim_1 > delim_2 else delim_2
        new_path = dirpath[:split]
        exists_directory(new_path)
        mkdir(path.abspath(dirpath))


def get_github_repo_name(path_to):
    git_dir = path_to + '.git'
    if path.exists(git_dir):
        with open(git_dir + '/config', 'r') as git_config:
            for line in git_config:
                if line.__contains__('origin'):
                    url = git_config.__next__()
                    if not url.__contains__('github.com'):
                        logging.warning('No Github remote found')
                    else:
                        logging.info('Git url is ' + url)
                        return url.rpartition('.git')[0].rpartition('/')[2]


parser = argparse.ArgumentParser(description="Setup the jekyll-template in a gh-pages repository")
parser.add_argument("--input", required=True, help="The directory where the jekyll template is stored", dest='in_path')
parser.add_argument("--output", nargs='?', default='./', const='./', help="The directory of the gh-pages repository",
                    dest='out_path')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

args = parser.parse_args()

# Loop over directory arguments making sure they:
# * All end in '/', important for joining together the paths
# * Exist
for key, value in args.__dict__.items():
    if not (value.endswith('/') or value.endswith('\\')):
        value += '/'
    if not path.exists(value):
        raise ValueError('Directory specified {} not found'.format(value))

in_path = args.__dict__['in_path']
out_path = args.__dict__['out_path']
# TODO change this to be a command line param
org_name = 'BricksandMortar'

matches = []
get_entries(in_path)

# Loop over valid files from matches and if they don't exist in the destination copy them across
copies = []
for entry in matches:
    safe_path = entry.path.replace("\\", "/")
    rel_git_path = (safe_path.replace(in_path, ''))
    new_path = out_path + rel_git_path
    if path.exists(new_path):
        logging.info('Exists ' + new_path)
    else:
        generate_directories(new_path.replace(entry.name, ''))
        logging.debug('Moving ' + entry.path + ' to ' + new_path)
        shutil.copy(safe_path, new_path)
        copies.append(rel_git_path)

# Append copied files to .gitignore
# TODO Turn this into a method I can reuse when I append branch files with a string parameter for the 'copied from' part of the ignore comment
with open(out_path + '.gitignore', 'a') as gitignore:
    gitignore.write('#Ignore copied from jekyll-docs template\n')
    for ignore in copies:
        gitignore.write(ignore + '\n')
    gitignore.write('#Endignore copied from jekyll-docs template\n')

# Attempt to get repository name from .git config
repo_name = get_github_repo_name(out_path)
if repo_name is not None:
    logging.info('Repo name is: ' + repo_name)
else:
    logging.warning(
        'Cannot ignore other branch files. Not a Git repository or valid repository name could not be found')

# Query which branches exist for the repo
# https://api.github.com/repos/:org/:repo/branches
branches = set()
branch_request = Request('https://api.github.com/repos/' + org_name + '/' + repo_name + '/branches')
with urlopen(branch_request) as response:
    if response.status == 200:
        # Get response as a string rather than a series of bytes
        str_response = response.read().decode('utf-8')
        branch_response = json.loads(str_response)
        for branch in branch_response:
            branch_name = branch['name']
            if branch_name != 'gh-pages' and branch_name != 'pages-ci':
                branches.add(branch['name'])
        for branch in branches:
            logging.info('Branch found: ' + branch)
    else:
        logging.warning(response.status)
        sys.exit()

# Find file tree and ignore for each branch in branches
# https://api.github.com/repos/:org/:repo/git/trees/:branch?recursive=1
files = set()
for branch in branches:
    file_tree_request = Request(
        'https://api.github.com/repos/' + org_name + '/' + repo_name + '/git/trees/' + branch + '?recursive=1')
    with urlopen(file_tree_request) as response:
        if response.status == 200:
            str_response = response.read().decode('utf-8')
            file_tree_response = json.loads(str_response)
            tree = file_tree_response['tree']
            for item in tree:
                if item['type'] == 'blob':
                    files.add(item['path'])
        else:
            logging.warning('Request failed: ' + file_tree_request.__str__())

# If no files to write to .gitignore, quit
if not len(files) > 0:
    sys.exit()
else:
    logging.info(len(files).__str__() + 'files found to ignore')

# Write file paths to .gitignore file
with open(out_path + '.gitignore', 'a') as gitignore:
    gitignore.write('\n#Ignore copied from other repo branch\n')
    for file_path in files:
        if check_file(file_path):
            gitignore.write(file_path + '\n')
    gitignore.write('#Endignore copied from other repo branch\n')
