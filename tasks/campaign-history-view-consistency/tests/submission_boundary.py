import contextlib
import os
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

UID = 10001
GID = 10001
WORK = Path('/home/submission/work')
SCRATCH = Path('/home/submission/tmp')
LOGS = Path('/run/console-process-logs')
PREFIX = ['/usr/bin/setpriv', '--reuid=10001', '--regid=10001', '--clear-groups',
          '--no-new-privs', '--bounding-set=-all', '--inh-caps=-all', '--ambient-caps=-all', '--']
MAX_TOTAL = 8 * 1024**3
MAX_FILE = 1024**3

def validate_tree(path, remaining=MAX_TOTAL):
    path = Path(path)
    assert path.is_dir() and not path.is_symlink(), f'Artifact is not a directory: {path}'
    used = 0
    for directory, directories, files, descriptor in os.fwalk(path, follow_symlinks=False):
        for name in directories + files:
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            child = Path(directory) / name
            if stat.S_ISLNK(info.st_mode):
                resolved = child.resolve()
                allowed = (Path('/workspace/console'), Path('/workspace/api'), Path('/opt/console-deps/node_modules'))
                assert any(resolved.is_relative_to(root) for root in allowed), f'Unsafe artifact link: {child}'
            elif stat.S_ISREG(info.st_mode):
                assert info.st_nlink == 1, f'Hard-linked artifact: {child}'
                assert info.st_size <= MAX_FILE, f'Oversized artifact: {child} ({info.st_size} bytes)'
                used += info.st_size
                assert used <= remaining, f'Artifacts exceed safety cap: {used} bytes in {path}'
                with open(child, 'rb') as stream:
                    stream.read(1)
            else:
                assert stat.S_ISDIR(info.st_mode), f'Non-source artifact entry: {child}'
    return used

def delegate_tree(root):
    root = Path(root)
    assert root == WORK and not root.is_symlink(), 'Only the working tree is delegated'
    for parent in root.parents:
        if parent == Path('/'):
            continue
        os.chmod(parent, stat.S_IMODE(parent.stat().st_mode) | 0o111)
    for directory, directories, files, descriptor in os.fwalk(root, follow_symlinks=False):
        os.fchown(descriptor, UID, GID)
        os.fchmod(descriptor, 0o755)
        for name in directories + files:
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError(f'Refusing hard-linked file: {directory}/{name}')
            os.chown(name, UID, GID, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode):
                os.chmod(name, stat.S_IMODE(info.st_mode) | 0o600, dir_fd=descriptor, follow_symlinks=False)

def traversable_parents(path):
    for parent in Path(path).parents:
        if parent != Path('/'):
            os.chmod(parent, stat.S_IMODE(parent.stat().st_mode) | 0o111)

def environment(extra=None):
    result = {
        'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/submission', 'TMPDIR': str(SCRATCH),
        'LANG': 'C.UTF-8', 'NEXT_TELEMETRY_DISABLED': '1', 'NODE_ENV': 'production',
        'BUNDLE_PATH': '/usr/local/bundle', 'RAILS_ENV': 'development',
        'npm_config_cache': str(SCRATCH / 'npm-cache'), 'npm_config_offline': 'true',
        'XDG_CONFIG_HOME':str(SCRATCH / 'config'), 'XDG_CACHE_HOME':str(SCRATCH / 'cache'),
    }
    if extra:
        result.update(extra)
    return result

def start(command, cwd, label, extra=None, uid=UID, capture=False):
    LOGS.mkdir(mode=0o700, exist_ok=True)
    descriptor = os.open(LOGS / f'{label}.log', os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    output = os.fdopen(descriptor, 'wb', buffering=0)
    try:
        prefix = [part.replace('=10001', '='+str(uid)) if part.startswith(('--reuid=', '--regid=')) else part for part in PREFIX]
        child_environment = environment(extra)
        if uid != UID:
            child_environment.update(HOME='/home/original', TMPDIR='/home/original/tmp')
        return subprocess.Popen(prefix + [str(item) for item in command], cwd=cwd,
                                env=child_environment, stdin=subprocess.PIPE if capture else subprocess.DEVNULL,
                                stdout=subprocess.PIPE if capture else output, stderr=output if capture else subprocess.STDOUT,
                                close_fds=True, start_new_session=True)
    finally:
        output.close()

def run(command, cwd, label, timeout=600, extra=None):
    process = start(command, cwd, label, extra)
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop(process)
        raise AssertionError(f'Individual call did not finish: {label}')
    assert code == 0, f'{label} exited {code}: {read_log(label)}'

def exchange(command, cwd, label, request, timeout=300, limit=1024**2):
    process = start(command, cwd, label, capture=True)
    deadline = time.monotonic() + timeout
    reply = bytearray()
    try:
        try:
            process.stdin.write(request)
            process.stdin.close()
        except BrokenPipeError:
            pass
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                assert remaining > 0, f'Worker operation did not finish: {label}'
                assert selector.select(remaining), f'Worker operation did not finish: {label}'
                chunk = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(reply)))
                if not chunk:
                    break
                reply.extend(chunk)
                assert len(reply) <= limit, f'Worker reply exceeds safety cap: {label}'
        try:
            code = process.wait(timeout=max(.001, deadline-time.monotonic()))
        except subprocess.TimeoutExpired as error:
            raise AssertionError(f'Worker operation did not finish: {label}') from error
        assert code == 0, f'Worker operation exited {code}: {label}'
        return bytes(reply)
    finally:
        process.stdout.close()
        stop(process)

def read_log(label):
    try:
        descriptor = os.open(LOGS / (label + '.log'), os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                return '<log is not an ordinary file>'
            stream.seek(max(0, info.st_size - 12000))
            return stream.read().decode(errors='replace')
    except OSError:
        return '<log unavailable>'

def stop(process):
    if process is None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)

def browser_wrapper():
    wrapper = Path('/opt/submission-chromium')
    Path('/run/console-browser').mkdir(exist_ok=True, mode=0o755)
    wrapper.write_text('''#!/usr/bin/python3
import os, sys, tempfile
arguments = sys.argv[1:]
for index, argument in enumerate(arguments):
    if argument.startswith('--user-data-dir='):
        profile = tempfile.mkdtemp(prefix='profile-', dir='/run/console-browser')
        descriptor = os.open(profile, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        os.fchown(descriptor, 10001, 10001)
        os.close(descriptor)
        arguments[index] = '--user-data-dir=' + profile
command = ''' + repr(PREFIX + ['/usr/bin/chromium']) + ''' + arguments
os.chdir('/home/submission/tmp')
os.execve(command[0], command, ''' + repr(environment()) + ''')
''')
    wrapper.chmod(0o755)
    return str(wrapper)

def seal_original(source):
    target = Path('/opt/original-console')
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(source), target)
    for directory, directories, files, descriptor in os.fwalk(target, follow_symlinks=False):
        os.fchown(descriptor, 0, 10002)
        os.fchmod(descriptor, 0o750)
        for name in files:
            info = os.stat(name,dir_fd=descriptor,follow_symlinks=False)
            if stat.S_ISREG(info.st_mode):
                os.chown(name,0,10002,dir_fd=descriptor,follow_symlinks=False)
                os.chmod(name,0o550 if info.st_mode & 0o111 else 0o440,dir_fd=descriptor)
    return target

def stage(source, name):
    target = WORK / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns('.next', '*.tsbuildinfo', '.git'))
    if not (target / 'node_modules').exists():
        (target / 'node_modules').symlink_to('/opt/console-deps/node_modules', target_is_directory=True)
    delegate_tree(WORK)
    return target
