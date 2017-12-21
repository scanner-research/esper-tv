import pexpect
import os

# This script changes Jupyter from using a random hash by default to a custom password, set in configure.py.

if 'JUPYTER_PASSWORD' not in os.environ:
    exit()

JUPYTER_DIR = '/root/.jupyter'
if not os.path.isdir(JUPYTER_DIR):
    os.mkdir(JUPYTER_DIR)

p = pexpect.spawn('jupyter notebook password')
p.expect('Enter password: ')
p.sendline(os.environ['JUPYTER_PASSWORD'])
p.sendline(os.environ['JUPYTER_PASSWORD'])
p.read()
