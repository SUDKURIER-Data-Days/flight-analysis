from pathlib import Path

from bson.objectid import ObjectId
import os
import cherrypy
from jinja2 import Environment, FileSystemLoader
from pymongo import MongoClient

from cherrypy.lib.static import serve_file
import bcrypt

import json
import pickle

class AuthenticationModule:
    def __init__(self):
        client = MongoClient(os.environ["MONGODB_URI"])
        self.db = client.flights["data"]["authentication"]

    def get_hashed_password(self, plain_text_password):
        # Hash a password for the first time
        #   (Using bcrypt, the salt is saved into the hash itself)
        # copied from https://stackoverflow.com/a/23768422
        return bcrypt.hashpw(plain_text_password.encode('utf-8'), bcrypt.gensalt())

    def check_password(self, plain_text_password, hashed_password):
        # Check hashed password. Using bcrypt, the salt is saved into the hash itself
        # copied from https://stackoverflow.com/a/23768422
        return bcrypt.checkpw(plain_text_password.encode('utf-8'), hashed_password)

    def check_password_in_db(self, realm, username, password):
        # signature as specified in https://docs.cherrypy.dev/en/latest/pkg/cherrypy.lib.auth_basic.html
        all_matching_data = [entry for entry in self.db.find({"realm":realm, "username":username})]
        if len(all_matching_data) == 1:
            return self.check_password(password, all_matching_data[0]["password"])
        else:
            return False

class AppServer:
    """
    Serves pages, deals with any APIs
    """
    def __init__(self, realm):
        """
        Sets up some basic information, like template path and environment.
        """
        self._tmpl_dir = Path(
            __file__).parents[0].resolve().joinpath('templates')
        print(self._tmpl_dir)
        self._env = Environment(loader=FileSystemLoader(self._tmpl_dir))


        # possibly init other APIs
        # locally, start mongo first: service mongod start
        # client = MongoClient("localhost", 27010)
        client = MongoClient(os.environ["MONGODB_URI"])
        print(client.list_database_names())
        # using collections instead of databases here now i think"f"]

        self.db = client.survey["data"]["flights"]
        self.realm = realm

    def _render_template(self, tmpl_name, params={}):
        """

        :param tmpl_name:
        :param params:
        :return:
        """
        tmpl = self._env.get_template(tmpl_name)
        return tmpl.render(**params)

    @cherrypy.expose
    def index(self, **kwargs):
        """

        :return:
        """
        all_data = self.db.find({})

        if "admin_mode" in kwargs:
            admin_mode = kwargs["admin_mode"]
        else:
            admin_mode = False

        return self._render_template('index.html', params={'title': "Index Page", "data": all_data, "admin_mode": admin_mode})

    @cherrypy.expose
    def upload(self):
        if "LOCAL" in os.environ and os.environ["LOCAL"]:
            return self._render_template("upload.html")
        else:
            return self._render_template("index.html")

    @cherrypy.expose
    def upload_file(self, starting_data):
        if "LOCAL" in os.environ and os.environ["LOCAL"]:
            out_file = Path(__file__).resolve().parents[1].joinpath("static/data/out.json")

            with open(out_file, "wb") as f:
                data = starting_data.file.read()
                f.write(data)

            with open(out_file, "rb") as f:
                entries = json.load(f)
            self.db.insert_many(entries)

    @cherrypy.expose
    def download(self):
        if "LOCAL" in os.environ and os.environ["LOCAL"]:
            all_data = [entry for entry in self.db.find({})]
            print(all_data)
            save_file = Path(__file__).resolve().parents[1].joinpath("static/data/data.pickle")

            with open(save_file, "wb") as f:
                pickle.dump(all_data, f)

            return serve_file(save_file, "application/x-download", "attachment")


class AdminConsole(AppServer):
    def __init__(self, realm):
        """
        Sets up some basic information, like template path and environment.
        """
        super().__init__(realm=realm)

        self.authentication = AuthenticationModule()

        try:
            self.enter_credentials_in_db("admin", "example1", "example-password1")
            self.enter_credentials_in_db("flights", "example2", "example-password2")
        except:
            pass

    @cherrypy.expose
    def POST_USER(self, **kwargs):
        self.enter_credentials_in_db(**kwargs)
        return self.index(admin_mode=True)

    @cherrypy.expose
    def add_user(self):
        return self._render_template("add_user.html", params={"post_route": f"{self.realm}/POST_USER"})

    def enter_credentials_in_db(self, realm, username, password):
        # only store hashed and salted passwords
        all_matching_data = [entry for entry in self.authentication.db.find({"username": username})]
        if len(all_matching_data) == 0:
            self.authentication.db.insert_one({"realm": realm, "username": username, "password": self.authentication.get_hashed_password(password)})
        else:
            raise ValueError("Username already is taken!")

    @cherrypy.expose
    def index(self, **kwargs):
        print([entry for entry in self.authentication.db.find({})])
        return super().index(admin_mode=True)