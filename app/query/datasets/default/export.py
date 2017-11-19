from query.datasets.prelude import *
import subprocess as sp
import pexpect

p = pexpect.spawn('pg_dump -h db -U {} -d esper'.format(os.environ['DJANGO_DB_USER']))
p.expect('Password: ')
p.sendline(os.environ['DJANGO_DB_PASSWORD'])
sql = p.read()

with open('db-dump.sql', 'w') as f:
    f.write(sql)

print('Successfully exported database to db-dump.sql')
