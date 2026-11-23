import os
from pathlib import Path
import stat
import subprocess

SUBMISSION_UID = 10001
SUBMISSION_GID = 10001


def delegate_tree(tree):
    tree = Path(tree)
    for directory, directories, files, descriptor in os.fwalk(tree, topdown=False, follow_symlinks=False):
        for name in directories + files:
            details = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(details.st_mode) or not (stat.S_ISREG(details.st_mode) or stat.S_ISDIR(details.st_mode)):
                raise RuntimeError('Unsafe node in tool working tree')
            if stat.S_ISREG(details.st_mode) and details.st_nlink != 1:
                raise RuntimeError('Hard-linked file in tool working tree')
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
            try:
                os.fchown(child, SUBMISSION_UID, SUBMISSION_GID)
            finally:
                os.close(child)
        os.fchown(descriptor, SUBMISSION_UID, SUBMISSION_GID)
    parent = tree.parent
    while parent != parent.parent:
        details = parent.stat()
        os.chmod(parent, stat.S_IMODE(details.st_mode) | 0o111)
        parent = parent.parent


def inspect_artifact(arguments, tree):
    environment = {
        'HOME': '/home/submission',
        'TMPDIR': '/home/submission/tmp',
        'PATH': '/usr/bin:/bin',
        'JAVA_HOME': '/usr/lib/jvm/java-17-openjdk-amd64',
        'LANG': 'C.UTF-8',
        'LC_ALL': 'C.UTF-8',
    }
    return subprocess.run([
        '/usr/bin/setpriv', '--reuid=10001', '--regid=10001', '--clear-groups', '--no-new-privs',
        '--bounding-set=-all', '--inh-caps=-all', '--ambient-caps=-all', '--', *map(str, arguments),
    ], cwd=tree, env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        errors='replace', timeout=120, check=False)
