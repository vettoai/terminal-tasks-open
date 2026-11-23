import ctypes
import errno
import os
import resource
import socket
import sys


class ArgumentComparison(ctypes.Structure):
    _fields_ = [('argument', ctypes.c_uint), ('operation', ctypes.c_uint),
                ('first', ctypes.c_uint64), ('second', ctypes.c_uint64)]


def configure():
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    library = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                             ctypes.c_uint, ctypes.POINTER(ArgumentComparison)]
    library.seccomp_rule_add_array.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x7fff0000)
    if not context:
        raise OSError('seccomp initialization failed')
    try:
        comparison = ArgumentComparison(0, 1, int(socket.AF_UNIX), 0)
        for name in ('socket', 'socketpair'):
            number = library.seccomp_syscall_resolve_name(name.encode('ascii'))
            if library.seccomp_rule_add_array(context, 0x00050000 | errno.EPERM, number,
                                              1, ctypes.byref(comparison)) != 0:
                raise OSError('seccomp network rule failed: ' + name)
        for name in ('io_uring_setup', 'sched_setaffinity', 'setsid', 'setpgid', 'ptrace',
                     'process_vm_readv', 'process_vm_writev'):
            number = library.seccomp_syscall_resolve_name(name.encode('ascii'))
            if number >= 0 and library.seccomp_rule_add(context, 0x00050000 | errno.EPERM, number, 0) != 0:
                raise OSError('seccomp rule failed: ' + name)
        if library.seccomp_load(context) != 0:
            raise OSError('seccomp load failed')
    finally:
        library.seccomp_release(context)


control = int(sys.argv[1])
os.set_inheritable(control, False)
try:
    configure()
except BaseException as error:
    os.write(control, b'E' + repr(error).encode('utf-8')[:4095])
    os._exit(125)
os.write(control, b'R')
os.execv(sys.argv[2], sys.argv[2:])
