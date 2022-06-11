from FlightRadar24.api import FlightRadar24API

fr_api = FlightRadar24API()
'''zones = fr_api.get_zones()
print(zones)

airline_icao = "AZU"
thy_flights = fr_api.get_flights(airline = airline_icao)
print(thy_flights)

# bounds = fr_api.get_bounds(zone)
# flights = fr_api.get_flights(bounds = bounds)
bounds = fr_api.get_bounds(zones['europe']['subzones']['germany'])
print(bounds)
flights = fr_api.get_flights(bounds=bounds)
print(flights[0])
print(len(flights))
details = fr_api.get_flight_details(flights[5].id)
print(details)
print(details.keys())
print(details["flightHistory"])
print(details["trail"])


# details2 = fr_api.get_flight_details([flight.id for flight in flights])
# print(details2)

# 7.888184,47.092566,10.327148,48.107431
print(fr_api.get_bounds({'tl_y':47.092566,'tl_x':7.888184,'br_y':48.107431,'br_x':10.327148}))'''
bounds_sg = fr_api.get_bounds({'br_y':47.092566,'tl_x':7.888184,'tl_y':48.107431,'br_x':10.327148})
print(bounds_sg)
flights = fr_api.get_flights(bounds=bounds_sg)
print(len(flights))
flights_in_sector_details = {}
for flight in flights:
    if flight.altitude > 100:
        flights_in_sector_details[flight.id] = fr_api.get_flight_details(flight.id)

for item in flights_in_sector_details.values():
    try:
        print(item['aircraft']['model']['text'])
        print(item["airport"]["origin"]["name"])
        print(item["airport"]["destination"]["name"])
    except Exception as e:
        pass
# Maybe stop jupyter, documented problem if port already taken: https://github.com/cherrypy/cherrypy/issues/1963