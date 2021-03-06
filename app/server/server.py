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

from scipy.spatial import distance

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
        self.user_db = client.survey["data"]["user_db"]

        # TODO: hack since we don't have real users
        self.user_db.delete_many({})

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

    def clean_flight_details(self, flight_details_dict, latitude, longitude, demo):
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
                        temp_dict["img"] = "../static/images/ufo_placeholder.png", "We have no idea how this one looks"
            try:
                temp_dict["airline"] = flight_specific_dict["airline"]["name"]
            except:
                temp_dict["airline"] = "Airline unknown :/"
            temp_dict["altitude"] = int(flight_specific_dict["altitude"]/3.2808)
            temp_dict["latitude"] = flight_specific_dict["latitude"]
            temp_dict["longitude"] = flight_specific_dict["longitude"]

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

            if temp_dict["airline"] and ("rettung" in temp_dict["airline"].lower()
                                         or "ambulanz" in temp_dict["airline"].lower()):
                temp_dict["badge"] = "rescue-helicopter"
            elif temp_dict["model"] and "zeppelin" in temp_dict["model"].lower():
                temp_dict["badge"] = "zeppelin"
            elif temp_dict["model"] and ("airbus a350" in temp_dict["model"].lower()
                                         or "airbus a380" in temp_dict["model"].lower()
                                         or "boeing 747" in temp_dict["model"].lower()
                                         or "boeing 777" in temp_dict["model"].lower()):
                temp_dict["badge"] = "jumbo-plane"
            elif temp_dict["img"][1] == "We have no idea how this one looks":
                temp_dict["badge"] = "ufo"
            elif temp_dict["glider"]:
                temp_dict["badge"] = "glider"
            else:
                temp_dict["badge"] = ""

            if temp_dict["badge"]:
                temp_dict["badge_link"] = f'<a href="new_badge?badge_type={temp_dict["badge"]}">', '</a>'
            else:
                temp_dict["badge_link"] = '', ''

            temp_dict["distance"] = str(round(
                distance.euclidean((latitude, longitude, 0),
                                   (temp_dict["latitude"], temp_dict["longitude"], 0)), 4)).replace(".", "").zfill(7)

            if temp_dict["model"]:
                cleaned_data.append(temp_dict)

        return sorted(cleaned_data, key=lambda x: x["distance"])

    def get_flights(self, longitude, latitude, displacement_x = 0.25, displacement_y = 0.25, demo=False):
        if demo:
            bounds_sg = self.fr_api_object.get_bounds(
                {'br_y': 47.092566, 'tl_x': 7.888184, 'tl_y': 48.107431, 'br_x': 10.327148})
        else:
            location = {'br_y': latitude -displacement_y, 'tl_x': longitude - displacement_x, 'tl_y': latitude+displacement_y, 'br_x': longitude +displacement_x }
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
                    flight_details["longitude"] = flight.longitude
                    flight_details["latitude"] = flight.latitude
                    flights_in_sector_details[flight.id] = flight_details

        self.db.insert_many(list(flights_in_sector_details.values())) # list of dictionaries

        return self.clean_flight_details(flights_in_sector_details, latitude, longitude, demo)

    @cherrypy.expose
    def pokeplane(self, **kwargs):
        if "latitude" in kwargs:
            latitude = float(kwargs["latitude"])
        else:
            latitude = 47.68

        if "longitude" in kwargs:
            longitude = float(kwargs["longitude"])
        else:
            longitude = 9.1488

        # TODO: this could check the boolean
        if "demo" in kwargs:
            demo = True
        else:
            demo = False

        cleaned_flights = self.get_flights(longitude, latitude, demo=demo)

        return self._render_template('pokeplane.html', \
                                     params={'title': "Index Page", \
                                             "data": cleaned_flights[:6]} )

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

        if "latitude" in kwargs:
            latitude = float(kwargs["latitude"])
        else:
            latitude = 47.68

        if "longitude" in kwargs:
            longitude = float(kwargs["longitude"])
        else:
            longitude = 9.1488

        # TODO: this could check the boolean
        if "demo" in kwargs:
            demo = True
        else:
            demo = False

        cleaned_flights = self.get_flights(longitude, latitude, demo=demo)

        return self._render_template('index.html', \
                                     params={'title': "Index Page", \
                                             "data":  cleaned_flights, \
                                             "admin_mode": admin_mode})


    @cherrypy.expose
    def upload(self):
        if "LOCAL" in os.environ and os.environ["LOCAL"]:
            return self._render_template("upload.html")
        else:
            return self._render_template("index.html")

    @cherrypy.expose
    def new_badge(self, badge_type):
        try:
            with open(f"static/text/{badge_type}.txt", "r") as f:
                lines = f.readlines()

            # check if user in user database, otherwise add them
            if len(list(self.user_db.find({"user": cherrypy.request.login}))) == 0:
                self.user_db.insert_one({'user': cherrypy.request.login, 'badges': []})

            user_curr_badges = list(self.user_db.find({"user": cherrypy.request.login}))[0]["badges"]
            if badge_type not in user_curr_badges:
                self.user_db.find_one_and_update({"user":cherrypy.request.login}, {"$set": {"badges": user_curr_badges + [badge_type]}})

            return self._render_template("new_badge.html", \
                                         params= {
                                            "text":"\n".join(lines), \
                                            "image":f"../../static/badges/{badge_type}.png"})
        except:
            raise cherrypy.HTTPError(404, "No such badge")

    @cherrypy.expose
    def badges_list(self):
        possible_badges = [curr_file.stem for curr_file in sorted(list(Path(__file__).parents[1].joinpath("static/badges/").glob("*")))]

        # check if user in user database, otherwise add them
        if len(list(self.user_db.find({"user": cherrypy.request.login}))) == 0:
            self.user_db.insert_one({'user': cherrypy.request.login, 'badges': []})

        user_curr_badges = list(self.user_db.find({"user": cherrypy.request.login}))[0]["badges"]

        images = [f"../../static/badges/{badge_type}.png" if badge_type in user_curr_badges else f"../../static/images/unearned.png" for badge_type in possible_badges]

        return self._render_template("badges_list.html", \
                                     params = {"images":images})
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
