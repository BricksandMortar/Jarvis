import argparse
import logging
import sys
import shutil
import requests

from pathlib import Path, PosixPath
from os import path, mkdir, close, remove, scandir, name, makedirs
from tempfile import mkstemp

isUnix = False

# Recursively loop over the directory structure until it finds a file.
def get_entries(directory):
    entries = scandir(directory)
    if entries:
        for entry in entries:
            if entry.is_file() and check_file(entry.name):
                matches.append(entry)
            if entry.is_dir() and check_directory(entry.name):
                get_entries(entry.path)


# Returns false for hidden files like .gitignore or repo specific files likes README and LICENSE
def check_file(filename):
    return not (filename.startswith('.') or filename.rpartition('.')[0].isupper() if filename.__contains__(
        '.') else filename.isupper())


# Returns false for hidden directories like .git
def check_directory(dirname):
    return not (dirname.startswith('.'))


def generate_directories(dirpath):
    makedirs(dirpath, exist_ok=True)


def get_token():
    with open('./token.txt') as travis_token_file:
        for line in travis_token_file:
            if line.__contains__('token'):
                return line.rpartition(' ')[1]


# Takes a repository path and gets a Github repo name from it
def get_github_repo_name(git_dir):
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
    else:
        logging.warning('No .git directory found')


def get_github_org_name(git_dir):
    if path.exists(git_dir):
        with open(git_dir + '/config', 'r') as git_config:
            for line in git_config:
                if line.__contains__('origin'):
                    url = git_config.__next__()
                    if not url.__contains__('github.com'):
                        logging.warning('No Github remote found')
                    else:
                        logging.info('Github org/user name is ' + url)
                        return url.rpartition('/'+get_github_repo_name(git_dir))[0].rpartition('/')[2]
    else:
        logging.warning('No .git directory found')


# http://stackoverflow.com/questions/39086/search-and-replace-a-line-in-a-file-in-python
def replace(file_path, pattern, subst):
    # Create temp file
    fh, abs_path = mkstemp()
    with open(abs_path, 'w') as new_file:
        with open(file_path) as old_file:
            for line in old_file:
                new_file.write(line.replace(pattern, subst))
    close(fh)
    # Remove original file
    remove(file_path)
    # Move new file
    shutil.move(abs_path, file_path)

def trigger_build(out_dir, repo_id):
    if path.exists(out_dir + '.travis.yml'):
        travis_headers['Travis-API-Version'] = '3'
        travis_build_url = 'https://api.travis-ci.org/repo/' + repo_id + '/requests'
        travis_build_data = {
            "request": {
                "branch": "pages-ci"
            }}
        travis_build_request = requests.post(travis_build_url, json=travis_build_data, headers=travis_headers)
        if travis_build_request.status_code != 200 or travis_build_request.status_code != 202:
            travis_build_request.raise_for_status()


parser = argparse.ArgumentParser(description="Setups a jekyll template in a gh-pages repository")
parser.add_argument("--in", required=True, help="The directory where the jekyll template is stored", dest='in_path')
parser.add_argument("--out", nargs='?', default='./', const='./', help="The directory of the gh-pages repository",
                    dest='out_path')
parser.add_argument("--user-name, --org-name", nargs='?', default=False, const=False, help="The name of the user or organisation the repository belongs to. If not provided it is attempted to be scraped from the .git directory", dest='org_name')
parser.add_argument("--token", nargs='?', default=None, const=None, help="The token used to authenticate Travis API calls", dest='token')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

args = parser.parse_args()

args_copy = args.__dict__
# Loop over directory path arguments making sure they:
# * All end in '/', important for joining together the paths
# * Exist
for key, value in args_copy.items():
    if 'path' in key:
        value = path.expanduser(value)
        value = path.normpath(value)
        args_copy[key] = value
        if not path.exists(value):
            raise ValueError('Directory specified {} not found'.format(value))

in_path = args_copy['in_path']
out_path = args_copy['out_path']
org_name = args_copy['org_name']
token = args_copy['token']

# May not exist
git_dir = path.join(out_path + '/.git')
if org_name is False:
    if path.exists(git_dir):
        org_name = get_github_org_name(git_dir)
        if not isinstance(org_name, str):
            raise ValueError('No org or username was specified and no existing value could be found from .git directory')
    else:
        raise ValueError('Git directory specified {} not found'.format(git_dir))

matches = []
get_entries(in_path)

# Loop over valid files from matches and if they don't exist in the destination copy them across
copies = []
for entry in matches:
    #Path for .gitignore, relative to the repo directory
    rel_git_path = path.relpath(entry.path, in_path)
    new_path = path.join(out_path, rel_git_path)
    if path.exists(new_path):
        logging.info('Exists ' + new_path)
    else:
        generate_directories(path.dirname(new_path))
        logging.debug('Moving ' + entry.path + ' to ' + new_path)
        shutil.copy(entry.path, new_path)
        copies.append(rel_git_path)

# Append copied files to .gitignore
# TODO Turn this into a method I can reuse when I append branch files with a string parameter for the 'copied from' part of the ignore comment
with open(out_path + '.gitignore', 'a') as gitignore:
    gitignore.write('#Ignore copied from jekyll-docs template\n')
    for ignore in copies:
        gitignore.write(ignore + '\n')
    gitignore.write('#Endignore copied from jekyll-docs template\n')

repo_name = get_github_repo_name(git_dir)

#Configure config.yml
replace(out_path+'/_config.yml', 'REPLACE', repo_name)
# Configure install script
replace(out_path + '/script/ciinstall.sh', 'GIT_URL', 'https://github.com/BricksandMortar/'+repo_name+'/.git')

if repo_name is not None:
    logging.info('Repo name is: ' + repo_name)
else:
    logging.warning(
        'Cannot ignore other branch files. Not a Git repository or valid repository name could not be found')
    sys.exit()

# Query which branches exist for the repo
# https://api.github.com/repos/:org/:repo/branches
branches = set()
branches_url = 'https://api.github.com/repos/' + org_name + '/' + repo_name + '/branches'
logging.info('Querying ' + branches_url)
branch_request = requests.get(branches_url)
if branch_request.status_code != 200:
    logging.warning('Response was: ' + str(branch_request.status_code))
else:
    for branch in branch_request.json():
        branch_name = branch['name']
        if branch_name != 'gh-pages' and branch_name != 'pages-ci':
            branches.add(branch['name'])
    for branch in branches:
        logging.info('Branch found: ' + branch)

# Find file tree and ignore for each branch in branches
# https://api.github.com/repos/:org/:repo/git/trees/:branch?recursive=1
if branches is not None:
    files = set()
    for branch in branches:
        file_tree_url = 'https://api.github.com/repos/' + org_name + '/' + repo_name + '/git/trees/' + branch + '?recursive=1'
        logging.info('Querying ' + branches_url)
        file_tree_request = requests.get(file_tree_url)
        if file_tree_request.status_code == 200:
            file_tree_response = file_tree_request.json()
            tree = file_tree_response['tree']
            for item in tree:
                if item['type'] == 'blob':
                    files.add(item['path'])
        else:
            logging.warning('Request failed: ' + file_tree_request.__str__())

    # If no files to write to .gitignore, quit
    if len(files) > 0:
        logging.info(len(files).__str__() + ' files found to ignore')

        # Write file paths to .gitignore file
        with open(out_path + '/.gitignore', 'a') as gitignore:
            gitignore.write('\n#Ignore copied from other repo branch\n')
            for file_path in files:
                if check_file(file_path):
                    gitignore.write(file_path + '\n')
            gitignore.write('#Endignore copied from other repo branch\n')

branches_url = 'https://api.github.com/repos/' + org_name + '/' + repo_name + '/branches'
logging.info('Querying ' + branches_url)
branch_request = requests.get(branches_url)
if branch_request.status_code == 200:
    branch_response = branch_request.json()
    for branch in branch_response:
        branch_name = branch['name']
        if branch_name != 'gh-pages' and branch_name != 'pages-ci':
            branches.add(branch['name'])
    for branch in branches:
        logging.info('Branch found: ' + branch)
else:
    logging.warning('Response: ' + str(branch_request.status_code))

# Get travis auth token
if token is None:
    token = get_token()

if token is not None:
    logging.info('Token is :' + token)
else:
    logging.warning('No token could be found')

travis_headers = {'Accept': 'application/json', 'Authorization': 'token ' + token}

# Get repo id
travis_repo_id_url = 'https://api.travis-ci.org/repos/BricksandMortar/' + repo_name
logging.info('Querying ' + travis_repo_id_url)
travis_repo_id_request = requests.get(travis_repo_id_url, headers=travis_headers)
if travis_repo_id_request.status_code == 200:
    travis_repo_id_response = travis_repo_id_request.json()
    repo_id = str(travis_repo_id_response['id'])
    logging.info('Repo Id: ' + repo_id)
else:
    travis_repo_id_request.raise_for_status()
    sys.exit()

# Add repo to Travis
travis_repo_add_url = 'https://api.travis-ci.org/hooks/'+repo_id
travis_add_data = {'hook[active]': 'true'}
logging.info('Adding Repo to Travis')
travis_repo_add_request = requests.put(travis_repo_add_url, headers=travis_headers, data=travis_add_data)
if travis_repo_add_request.status_code != 200:
    travis_repo_add_request.raise_for_status()
    sys.exit()

# Ensure setting to only branches with .travis.yml present
logging.info('Configuring only to build this branch')
travis_settings_url = 'https://api.travis-ci.org/repos/'+repo_id+'/settings'
travis_settings_data = {"settings": {
  "builds_only_with_travis_yml": "true"}
}
travis_settings_request = requests.patch(travis_settings_url, json=travis_settings_data, headers=travis_headers)
if travis_settings_request.status_code != 200:
    travis_settings_request.raise_for_status()

