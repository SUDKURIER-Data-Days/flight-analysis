from pathlib import Path
import os

import cherrypy
from server import AppServer, AuthenticationModule, AdminConsole
from dotenv import load_dotenv
from cherrypy.lib import auth_basic


if __name__ == '__main__':
    if "PORT" not in os.environ:
        load_dotenv(Path(__file__).resolve().parents[0].joinpath(".env"))


    class Root:
        @cherrypy.expose
        def index(self):
            return "Hello, world!"


    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': int(os.environ['PORT'])})

    cherrypy.tree.mount(Root(), '/', config = {'/static': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': Path(__file__).parents[0].resolve().joinpath('static')
        }})
    cherrypy.tree.mount(AppServer("survey"), '/survey', config =  {'/': {'tools.auth_basic.on': True,
        'tools.auth_basic.realm': 'survey',
        'tools.auth_basic.checkpassword': AuthenticationModule().check_password_in_db}})
    cherrypy.tree.mount(AdminConsole("admin"), '/admin',  config =  {'/':{'tools.auth_basic.on': True,
        'tools.auth_basic.realm': 'admin',
        'tools.auth_basic.checkpassword': AuthenticationModule().check_password_in_db,
        'tools.auth_basic.accept_charset': 'UTF-8'}})

    cherrypy.engine.start()
    cherrypy.engine.block()
