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
from FlightRadar24.api import FlightRadar24API

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
        self.fr_api_object = FlightRadar24API()

    def _render_template(self, tmpl_name, params={}):
        """

        :param tmpl_name:
        :param params:
        :return:
        """
        tmpl = self._env.get_template(tmpl_name)
        return tmpl.render(**params)

    def clean_flight_details(self, flight_details_dict):
        """

        :param flight_details_dict:
        :return: should output dictionary with model, origin, destination
        """
        # look if data is missing (missing destination, origin or model)
        cleaned_data = []
        for flight_id, flight_specific_dict in flight_details_dict.items():
            temp_dict = {}
            try:
                temp_dict["model"] = flight_specific_dict['aircraft']['model']['text']
            except:
                temp_dict["model"] = ""
            try:
                temp_dict["origin"] = flight_specific_dict["airport"]["origin"]["name"]
            except:
                temp_dict["origin"] = "Origin unknown :/"
            try:
                temp_dict["destination"] = flight_specific_dict['airport']['destination']['name']
            except:
                temp_dict["destination"] = "Destination unknown :/"
            try:
                temp_dict["img"] = flight_specific_dict["aircraft"]["images"]["thumbnails"][0]["src"], temp_dict["model"]
            except:
                try:
                    temp_dict["img"] = flight_specific_dict["aircraft"]["images"]["medium"][0]["src"], temp_dict[
                        "model"]
                except:
                    try:
                        temp_dict["img"] = flight_specific_dict["aircraft"]["images"]["large"][0]["src"], \
                                           temp_dict["model"]
                    except:
                        temp_dict["img"] = None, "Sorry, no img found :/"
            try:
                temp_dict["airline"] = flight_specific_dict["airline"]["name"]
            except:
                temp_dict["airline"] = "Airline unknown :/"
            temp_dict["altitude"] = int(flight_specific_dict["altitude"]/3.2808)

            if (temp_dict["img"]
                and temp_dict["img"][0] == "https://www.flightradar24.com/static/images/sideviews/thumbnails/GLID.jpg") \
                    or (temp_dict["airline"]
                        and ("segel" in temp_dict["airline"].lower() or "glid" in temp_dict["airline"].lower())) \
                    or (temp_dict["model"]
                        and ("schempp-hirth" in temp_dict["model"].lower() or "lange" in temp_dict["model"].lower()
                             or "alexander schleicher" in temp_dict["model"].lower())):
                temp_dict["glider"] = True
            else:
                temp_dict["glider"] = False

            if temp_dict["model"]:
                cleaned_data.append(temp_dict)

        return cleaned_data

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

        # TODO need to pass user's location back from javascript/html
        location = {'br_y': 47.092566, 'tl_x': 7.888184, 'tl_y': 48.107431, 'br_x': 10.327148}
        bounds_sg = self.fr_api_object.get_bounds(location)
        print(bounds_sg)
        flights_in_sector = self.fr_api_object.get_flights(bounds=bounds_sg)

        print(len(flights_in_sector))
        flights_in_sector_details = {}
        for flight in flights_in_sector:
            if flight.altitude > 100:
                flight_details = self.fr_api_object.get_flight_details(flight.id)
                if isinstance(flight_details, dict):
                    flight_details["altitude"] = flight.altitude
                    flights_in_sector_details[flight.id] = flight_details

        self.db.insert_many(list(flights_in_sector_details.values())) # list of dictionaries

        return self._render_template('index.html', \
                                     params={'title': "Index Page", \
                                             "data": self.clean_flight_details(flights_in_sector_details), \
                                             "admin_mode": admin_mode})


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
