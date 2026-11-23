import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from rewardkit import Worker, WorkerError, WorkerSetupError


@dataclass(frozen=True, kw_only=True)
class ReconstructionWorker(Worker):
    prepare_script: str
    collect_script: str
    owned_directories: tuple[Path, ...] = ()
    transfer_timeout_sec: float = 120
    timings: dict = field(default_factory=dict, compare=False)

    def _phase(self, name, script, stdin_data, outputs, timeout_sec, scratch, uid):
        started = time.monotonic()
        try:
            return super()._execute(script, stdin_data, outputs, timeout_sec, scratch, uid)
        except WorkerError as error:
            raise WorkerError(f'{name}: {error}', stderr=error.stderr) from error
        finally:
            self.timings[name] = time.monotonic() - started

    def _execute(self, script, stdin_data, outputs, timeout_sec, scratch, uid):
        self.timings.clear()
        try:
            for directory in self.owned_directories:
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY |
                                       os.O_NOFOLLOW | os.O_CLOEXEC)
                try:
                    os.fchown(directory_fd, uid, uid)
                finally:
                    os.close(directory_fd)
        except OSError as error:
            raise WorkerSetupError(f'Cannot prepare worker directory ownership: {error}') from error
        prepared = self._phase('prepare', self.prepare_script, b'', (),
                               self.transfer_timeout_sec, scratch, uid)
        if prepared.returncode != 0:
            raise WorkerError('Input preparation failed', stderr=prepared.stderr)
        invocation = self._phase('invocation', script, stdin_data, (),
                                 timeout_sec, scratch, uid)
        if invocation.returncode != 0:
            return invocation
        collected = self._phase('collect', self.collect_script, b'', outputs,
                                self.transfer_timeout_sec, scratch, uid)
        if collected.returncode != 0:
            raise WorkerError('Output collection failed', stderr=collected.stderr)
        return replace(invocation, files=collected.files)
