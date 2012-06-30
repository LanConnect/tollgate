from fabric.api import *
from fabric.contrib import project
from fabric.contrib import files

import os, sys, platform, subprocess
from argparse import ArgumentError

env.hosts = ['your_username@yourhost:yourport']
env.web_path = '/var/www/django'
env.log_root ='/var/log/apache'
env.project = '.'
env.environ = 'environ'
env.static_dir = "tollgate/frontend/static/tollgate"

@task
def develop():
    try:
        compass = subprocess.Popen("compass watch",
            stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=env.static_dir)
        coffee  = subprocess.Popen("coffee --output js --watch --bare --compile coffee",
            stdout=sys.stdout, stderr=sys.stderr, shell=True, cwd=env.static_dir)
        with lcd(env.project):
            local("python manage.py runserver") # this will take up most of the shell output
    except KeyboardInterrupt:
        print "killing server..."
    finally:
        try: compass.kill() ; coffee.kill()
        except: pass

@task
def bootstrap_dev():
    """ Bootstrap your local development environment """
    local('virtualenv --distribute ./%(environ)s' % env)
    with prefix('source ./%(environ)s/bin/activate' % env):
        local('pip install -r requirements.txt')
        local('python %(project)s/manage.py syncdb --all' % env)
        local('python %(project)s/manage.py migrate --fake' % env)
    with cd(env.static_dir):
        sudo('gem install compass omg-text')
        sudo('npm install coffeescript')

@task
def bootstrap(hostname, path=env.web_path, **kwargs):
    """ Creates a virtualhost instance on the box you specify
        `fab -H server1,server2 bootstrap:tollgate.example.com[,deploy_options...]` """

    run('mkdir -p %(web_path)s/%(hostname)s/' % locals())
    with cd('%(web_path)s/%(hostname)s/' % locals()):
        run('git init .')

    locals().update(kwargs)
    deploy(**locals()) # deploy script takes care of the rest

@task
def deploy(hostname, ref='master', path=env.web_path, apache_conf_path=None, distro=None, \
           log_root=env.log_root, thread_count=2, process_count=4):
    """ deploy the project to your webserver.
        `fab -H server1,server2 deploy:tollgate.example.com` """
    if not apache_conf_path: apache_conf_path=find_apache_path(distro)

    local('git push -f ssh://%(host_string)s/%(web_path)s/%(hostname)s/ %(ref)s' % locals())
    with cd('%(web_path)s/%(hostname)s' % locals()):
        run('git checkout -f %(ref)s' % locals())
        run('pip install -r requirements.txt')
        with cd(env.project):
            files.upload_template('apache.conf', apache_conf_path+hostname,
                                  context=locals(), mode=0755, use_sudo=True)
            run('python manage.py collectstatic -v0 --noinput')
            run('python manage.py syncdb')
            run('python manage.py migrate')
            run('touch serve.wsgi') # restart the wsgi process


#-------- Utils ----------

def find_apache_path(distro):
    if not distro:
        system, distro = run('python -c "import platform; print platform.system(), platform.dist()[0]"').split()
    if distro in ('debian', 'ubuntu'):
        return '/etc/apache2/sites-enabled/'
    elif system == "Darwin":
        ArgumentError('PN is not tested on OSX')
    elif system == "Windows":
        ArgumentError('PN is not tested on Windows')
    else:
        raise ArgumentError('Cannot automatically determine apache_conf_path')
