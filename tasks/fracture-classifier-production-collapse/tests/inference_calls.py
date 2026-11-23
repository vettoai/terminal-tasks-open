from pathlib import Path
import shlex
import threading

from rewardkit import Worker, WorkerError


class SubmissionError(Exception):
    def __init__(self, message, response_text=None):
        super().__init__(message)
        self.response_text = response_text


class InferenceCalls:
    def __init__(self):
        self.stopped = threading.Event()
        self.worker = Worker(env={
            "PATH": "/opt/runtime/bin:/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1",
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "BLIS_NUM_THREADS": "1",
        }, max_output_bytes=1024 * 1024)

    def cancel(self):
        self.stopped.set()

    def invoke(self, image):
        if self.stopped.is_set():
            raise SubmissionError("Inference collection stopped")
        image = Path(image)
        command = (
            f'target="$PWD"/{shlex.quote(image.name)}; errors="$PWD"/cli.stderr; cd /opt/vision && '
            'exec /opt/runtime/bin/python3 /opt/vision/infer.py --target "$target" --output-json 2>"$errors"'
        )
        try:
            result = self.worker.run(command, files=[image], outputs=["cli.stderr"], timeout_sec=120)
        except WorkerError as error:
            raise SubmissionError(str(error)) from error
        errors = result.files.get("cli.stderr")
        if errors is None:
            raise SubmissionError("Missing captured inference output")
        if len(result.stdout) + len(errors) > 1024 * 1024:
            raise SubmissionError("Inference output exceeded 1 MiB")
        try:
            text = result.stdout.decode("utf-8")
        except UnicodeError as error:
            raise SubmissionError("Inference output is not UTF-8 JSON", repr(result.stdout)) from error
        if result.returncode != 0:
            raise SubmissionError(f"Inference exited {result.returncode}: {errors[:1000]!r}", text)
        return text
