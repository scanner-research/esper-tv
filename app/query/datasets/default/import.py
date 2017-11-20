from query.datasets.prelude import *
import pexpect
import os

if not os.path.isfile('db-dump.sql'):
    print('Error: missing file db-dump.sql')
    exit()

def send_command(cmd, db):
    user = os.environ['DJANGO_DB_USER']
    p = pexpect.spawn('bash -c "{} | psql -h db {} {}"'.format(cmd, db, user))
    p.expect('Password for user {}: '.format(user))
    p.sendline(os.environ['DJANGO_DB_PASSWORD'])
    p.read()  # Changes don't actually happen unless you read output?

send_command('echo \'DROP DATABASE esper; CREATE DATABASE esper;\'', 'postgres')
send_command('cat db-dump.sql', 'esper')
print('Successfully imported db-dump.sql')




