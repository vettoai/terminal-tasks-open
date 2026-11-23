import os
import sys
import tempfile

os.chdir('/home/submission')
profile = tempfile.mkdtemp(prefix='chromium-', dir=os.environ['TMPDIR'])
arguments = [f'--user-data-dir={profile}' if argument.startswith('--user-data-dir=') else argument for argument in sys.argv[1:]]
os.execv('/opt/chromium/chrome-linux/chrome', ['/opt/chromium/chrome-linux/chrome', *arguments])
