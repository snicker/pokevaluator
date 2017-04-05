#!/usr/bin/python
# Load Generated Protobuf
from pgoapi.protos.POGOProtos.Networking.Requests import Request_pb2
from pgoapi.protos.POGOProtos.Networking.Requests import RequestType_pb2
from pgoapi.protos.POGOProtos.Networking.Envelopes import ResponseEnvelope_pb2
from pgoapi.protos.POGOProtos.Networking.Envelopes import RequestEnvelope_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import EncounterMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import DiskEncounterMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Responses import DiskEncounterResponse_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import FortSearchMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import CatchPokemonMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import GetInventoryMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import GetMapObjectsMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import EvolvePokemonMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import ReleasePokemonMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import DownloadSettingsMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import UseItemEggIncubatorMessage_pb2
from pgoapi.protos.POGOProtos.Networking.Requests.Messages import RecycleInventoryItemMessage_pb2

import argparse
import pickle
import logging
import time
import sys
import os
from custom_exceptions import GeneralPogoException

from api import PokeAuthSession
from location import Location
from botdata import BotData

diskencounterresponse = DiskEncounterResponse_pb2.DiskEncounterResponse()
candies_per_evolve = {1: 25, 2: 100, 4: 25, 5: 100, 7: 25, 8: 100, 10: 12, 11: 50, 13: 12, 14: 50, 16: 12, 17: 50, 19: 25, 21: 50, 23: 50, 25: 50, 27: 50, 29: 25, 30: 100, 32: 25, 33: 100, 35: 50, 37: 50, 39: 50, 41: 50, 43: 25, 44: 100, 46: 50, 48: 50, 50: 50, 52: 50, 54: 50, 56: 50, 58: 50, 60: 25, 61: 100, 63: 25, 64: 100, 66: 25, 67: 100, 69: 25, 70: 100, 72: 50, 74: 25, 75: 100, 77: 50, 79: 50, 81: 50, 84: 50, 86: 50, 88: 50, 90: 50, 92: 25, 93: 100, 96: 50, 98: 50, 100: 50, 102: 50, 104: 50, 109: 50, 111: 50, 116: 50, 118: 50, 120: 50, 129: 400, 133: 25, 138: 50, 140: 50, 147: 25, 148: 100}

def setupLogger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('Line %(lineno)d,%(filename)s - %(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


# Example functions
# Get profile
def getProfile(session):
        logging.info("Printing Profile:")
        profile = session.getProfile()
        logging.info(profile)

pokeballName = {
    0: "None",
    1: "PokeBall",
    2: "Great Ball",
    3: "Ultra Ball",
    4: "Master Ball"
}    

def getAvailablePokeball(session,pokeball=1):
    bag = session.checkInventory()['bag']
    while pokeball > 0:
        if pokeball in bag and bag[pokeball] > 0:
            return pokeball
        pokeball -= 1
    return pokeball

# Grab the nearest pokemon details
def findClosestPokemon(session,radius=5):
    # Get Map details and print pokemon
    logging.info("Printing Nearby Pokemon:")
    cells = session.getMapObjects(radius=radius)
    closest = float("Inf")
    pokemonBest = None
    latitude, longitude, _ = session.getCoordinates()
    for cell in cells.map_cells:
        for pokemon in cell.wild_pokemons:
            # Log the pokemon found
            logging.info("%i at %f,%f" % (
                pokemon.pokemon_data.pokemon_id,
                pokemon.latitude,
                pokemon.longitude
            ))

            # Fins distance to pokemon
            dist = Location.getDistance(
                latitude,
                longitude,
                pokemon.latitude,
                pokemon.longitude
            )

            # Greedy for closest
            if dist < closest:
                pokemonBest = pokemon
    return pokemonBest

def releaseShittyPokemonButKeepEnoughToPowerLevel(session,minperfect=0.9,minalmostperfect=0.85,mincp=1600):
    logging.info("Releasing lousy pokemon but keeping enough to power level...")
    inv = session.checkInventory()
    if not inv:
        logging.info("Couldn't get inventory!")
        return
    candies = inv['candies']
    remainingtokeep = {}
    for id in candies:
        logging.debug("we have {x} candies for pokemon id {y}".format(x=candies[id],y=id))
        if id in candies_per_evolve:
            logging.debug("it takes {x} candies to evolve {y}".format(x=candies_per_evolve[id],y=id))
            remainingtokeep[id] = int(float(candies[id])/candies_per_evolve[id])
            remainingtokeep[id] += int(float(remainingtokeep[id]) / candies_per_evolve[id])
            logging.debug("we should keep {x} pokemon of id {y}".format(x=remainingtokeep[id],y=id))
    party = inv['party']
    tokeep = []
    for pokemon in party:
        if isPokemonGood(session,pokemon,minperfect=minperfect,minalmostperfect=minalmostperfect,mincp=mincp) or pokemon.favorite == 1:
            if pokemon.id not in tokeep:
                logging.debug("{p} is good, adding to list...".format(p=pokemonAsString(pokemon)))
                tokeep.append(pokemon.id)
                if pokemon.pokemon_id in remainingtokeep:
                    remainingtokeep[pokemon.pokemon_id] -= 1
    party = sorted(party, key=lambda k: k.cp, reverse=True)
    for id in remainingtokeep:
        while remainingtokeep[id] > 0:
            logging.debug("still need {x} more of pokemon {y}".format(x=remainingtokeep[id],y=id))
            for pokemon in party:
                if pokemon.pokemon_id == id and pokemon.id not in tokeep and remainingtokeep[id] > 0:
                    logging.debug("keeping {p} for evolving".format(p=pokemonAsString(pokemon)))
                    tokeep.append(pokemon.id)
                    remainingtokeep[id] -= 1
            break
    torelease = []
    for pokemon in party:
        if pokemon.id not in tokeep:
            torelease.append(pokemon)
    logging.info("releasing {x} pokemon...".format(x=len(torelease)))
    for pokemon in torelease:
        logging.info("releasing pokemon {p}...".format(p=pokemonAsString(pokemon)))
        session.releasePokemon(pokemon)
        time.sleep(1)
        session.getInventory()
        time.sleep(1)
        
        
            
    
def pokemonAsString(pokemon):
    return "{id}: {a}/{d}/{s} ({cp})".format(id=pokemon.pokemon_id,a=pokemon.individual_attack,d=pokemon.individual_defense,s=pokemon.individual_stamina,cp=pokemon.cp)
    
def releaseShittyPokemon(session,minperfect=0.9,minalmostperfect=0.8):
    logging.info("Releasing lousy pokemon")
    if session is None:
        return
    inv = session.checkInventory()
    if 'party' in inv:
        pokemen = inv['party']
        for i in xrange(0,len(pokemen)):
            pokemon = pokemen[i]
            if not isPokemonGood(session,pokemon,minperfect=minperfect,minalmostperfect=minalmostperfect):
                logging.info("Releasing Pokemon: {p}".format(p=pokemon))
                session.releasePokemon(pokemon)
                pokemen = session.getInventory()['party']
                i = 0
    return

def evolveEvolvablePokemon(session):
    logging.info("Evolving pokemon with available candies...")
    if session is None:
        return
    inv = session.checkInventory()
    if 'party' in inv:
        pokemen = inv['party']
        candies = inv['candies']
        for pokemon in pokemen:
            if pokemon.pokemon_id in candies_per_evolve:
                if pokemon.pokemon_id in candies:
                    if candies[pokemon.pokemon_id] >= candies_per_evolve[pokemon.pokemon_id]:
                        if getPerfectForPokemon(session,pokemon) == 1 or pokemon.cp >= getHighestCPForPokemonType(session,pokemon):
                            logging.info("Evolving Pokemon {p} ({cp})".format(p=pokemon.pokemon_id,cp=pokemon.cp))
                            logging.info(session.evolvePokemon(pokemon))
                            candies = session.getInventory()['candies']
    return
    

def cleanUpPokemon(session):
    logging.info("Cleaning up Pokemon...")
    if session is None:
        return
    releaseShittyPokemon(session,minalmostperfect=0.86)
    evolveEvolvablePokemon(session)
    return

def isPokemonGood(session,pokemon,minperfect=0.9,minalmostperfect=0.8,mincp=1600):
    logging.debug("Checking if {p} ({cp}) is good...".format(p=pokemon.pokemon_id,cp=pokemon.cp))
    mincpformon = getHighestCPForPokemonType(session,pokemon)
    perfect = getPerfectForPokemon(session,pokemon)
    logging.debug("req'd min cp for {p} is {min}, this one is {perf:0.2f}% perfect".format(p=pokemon.pokemon_id,min=mincpformon,perf=perfect))
    if pokemon.cp >= mincp or pokemon.cp >= mincpformon or perfect >= minperfect or (perfect>=minalmostperfect and (pokemon.individual_attack == 15 or pokemon.individual_defense == 15)):
        logging.debug("good pokemon.")
        return True
    logging.debug("bad pokemon.")
    return False

def getHighestCPForPokemonType(session,pokemon):
    party = session.checkInventory()['party']
    highestcp = -1
    for pp in party:
        if pp.pokemon_id == pokemon.pokemon_id and pp.cp > highestcp:
            highestcp = pp.cp
    return highestcp
    
def getPerfectForPokemon(session,pokemon):
    return float(int(pokemon.individual_attack) + int(pokemon.individual_defense) + int(pokemon.individual_stamina)) / 45
    
# Catch a pokemon at a given point
def walkAndCatch(session, pokemon,step=7.5,delay=2,pokeball=1):
    if pokemon:
        logging.info("Catching nearest pokemon:")
        if getAvailablePokeball(session,pokeball) == 0:
            logging.info("No pokeballs available.")
            return None
        session.walkTo(pokemon.latitude, pokemon.longitude,step=step)
        encounterdata = session.encounterPokemon(pokemon)
        logging.info("Encounter data: {encounter}".format(encounter=encounterdata))
        if encounterdata.capture_probability is not None:
            prob = encounterdata.capture_probability.capture_probability
            if prob[0] < 0.25:
                logging.info("Low capture probability, using a Great Ball if we have one...")
                pokeball = getAvailablePokeball(session,2)
            if prob[1] < 0.25:
                logging.info("Even lower capture probability, using an Ultra Ball if we have one...")
                pokeball = getAvailablePokeball(session,3)
            time.sleep(delay)
            logging.info("Attempting capture with {pokeball}...".format(pokeball=pokeballName[pokeball]))
            catchdata = session.catchPokemon(pokemon, pokeball)
            logging.info("Catch data: {catch}".format(catch=catchdata))
            return catchdata

def encounterAndCatchPokemonAtLure(self, fort, pokeball=1, delay=2):
        if getAvailablePokeball(self,pokeball) == 0:
            logging.info("No pokeballs available.")
            return None

        # Create request
        payload = [Request_pb2.Request(
            request_type=RequestType_pb2.DISK_ENCOUNTER,
            request_message=DiskEncounterMessage_pb2.DiskEncounterMessage(
                encounter_id=fort.lure_info.encounter_id,
                fort_id=fort.lure_info.fort_id,
                player_latitude=self.location.latitude,
                player_longitude=self.location.longitude
            ).SerializeToString()
        )]
        logging.debug("payload built")
        logging.debug(payload)
        # Send
        res = self.wrapAndRequest(payload)
        logging.debug("response rcv, parsing")

        # Parse
        diskencounterresponse.ParseFromString(res.returns[0])
        encounterdata = diskencounterresponse
        logging.debug(encounterdata)
        
        logging.info("Encounter data: {encounter}".format(encounter=encounterdata))
        if encounterdata.capture_probability is not None:
            prob = encounterdata.capture_probability.capture_probability
            if prob[0] < 0.25:
                logging.info("Low capture probability, using a Great Ball if we have one...")
                pokeball = getAvailablePokeball(self,2)
            if prob[1] < 0.25:
                logging.info("Even lower capture probability, using an Ultra Ball if we have one...")
                pokeball = getAvailablePokeball(self,3)
            time.sleep(delay)
            logging.info("Attempting capture with {pokeball}...".format(pokeball=pokeballName[pokeball]))

            # Return everything
            time.sleep(delay)
            
            # Create request
            payload = [Request_pb2.Request(
                request_type=RequestType_pb2.CATCH_POKEMON,
                request_message=CatchPokemonMessage_pb2.CatchPokemonMessage(
                    encounter_id=fort.lure_info.encounter_id,
                    pokeball=pokeball,
                    normalized_reticle_size=1.950,
                    spawn_point_guid=fort.lure_info.fort_id,
                    hit_pokemon=True,
                    spin_modifier=0.850,
                    normalized_hit_position=1.0
                ).SerializeToString()
            )]
            logging.debug("payload built")
            logging.debug(payload)

            # Send
            res = self.wrapAndRequest(payload)
            logging.debug("response sent")

            # Parse
            self.state.catch.ParseFromString(res.returns[0])

            # Return everything
            return self.state.catch

# Do Inventory stuff
def getInventory(session):
    logging.info("Get Inventory:")
    logging.info(session.getInventory())

def getTrainerSummary(session):
    inv = session.checkInventory()
    stats = inv['stats']
    xp = stats.experience
    nextlvlxp = stats.next_level_xp
    prevlvlxp = stats.prev_level_xp
    xptnl = int(nextlvlxp) - int(xp)
    xpthislevel = int(nextlvlxp) - int(prevlvlxp)
    tnlpct = (1-(float(xptnl)/xpthislevel))*100
    return "Trainer Summary: Level {level}, {xp}xp, {xptnl}xp tnl ({tnlpct:3.2f}%), {km:3.2f}km walked, {pokemon} pokemon in party".format(level=stats.level,xp=xp,xptnl=xptnl,tnlpct=tnlpct,km=stats.km_walked,pokemon=len(inv['party']))

# Basic solution to spinning all forts.
# Since traveling salesman problem, not
# true solution. But at least you get
# those step in
def sortCloseForts(session,radius=10):
    # Sort nearest forts (pokestop)
    logging.info("Sorting Nearest Forts:")
    cells = session.getMapObjects(radius=radius)
    latitude, longitude, _ = session.getCoordinates()
    ordered_forts = []
    for cell in cells.map_cells:
        for fort in cell.forts:
            dist = Location.getDistance(
                latitude,
                longitude,
                fort.latitude,
                fort.longitude
            )
            if fort.type == 1:
                ordered_forts.append({'distance': dist, 'fort': fort, 'islured': (fort.lure_info is not None and fort.lure_info.encounter_id != 0)})

    ordered_forts = sorted(ordered_forts, key=lambda k: k['distance'])
    ordered_forts = sorted(ordered_forts, key=lambda k: k['islured'], reverse=True)
    return [instance['fort'] for instance in ordered_forts]


# Find the fort closest to user
def findClosestFort(session):
    # Find nearest fort (pokestop)
    logging.info("Finding Nearest Fort:")
    return sortCloseForts(session)[0]

def distanceToFort(session, fort):
    latitude, longitude, _ = session.getCoordinates()
    return Location.getDistance(
        latitude,
        longitude,
        fort.latitude,
        fort.longitude
    )
    
def walkToNonBlock(self, olatitude, olongitude, epsilon=10, step=7.5, interval=-1):
    if step >= epsilon:
        raise Exception("Walk may never converge")

    # Calculate distance to position
    latitude, longitude, _ = self.getCoordinates()
    dist = closest = Location.getDistance(
        latitude,
        longitude,
        olatitude,
        olongitude
    )

    # Run walk
    divisions = closest / step
    dLat = (latitude - olatitude) / divisions
    dLon = (longitude - olongitude) / divisions
    while dist > epsilon:
        logging.info("%f m -> %f m away", closest - dist, closest)
        latitude -= dLat
        longitude -= dLon
        self.setCoordinates(
            latitude,
            longitude
        )
        if interval > -1 and (closest - dist) > interval:
            return False
        time.sleep(1)
        dist = Location.getDistance(
            latitude,
            longitude,
            olatitude,
            olongitude
        )
    return True

# Walk to fort and spin
def walkAndSpin(session, fort, step=7.5):
    # No fort, demo == over
    if fort:
        logging.info("Spinning a Fort:")
        # Walk over
        session.walkTo(fort.latitude, fort.longitude, step=step)
        # Give it a spin
        fortResponse = session.getFortSearch(fort)
        logging.info(fortResponse)


# Walk and spin everywhere
def walkAndSpinMany(session, forts):
    for fort in forts:
        walkAndSpin(session, fort)


# A very brute force approach to evolving
def evolveAllPokemon(session):
    inventory = session.checkInventory()
    for pokemon in inventory["party"]:
        logging.info(session.evolvePokemon(pokemon))
        time.sleep(1)


# You probably don't want to run this
def releaseAllPokemon(session):
    inventory = session.checkInventory()
    for pokemon in inventory["party"]:
        session.releasePokemon(pokemon)
        time.sleep(1)


# Just incase you didn't want any revives
def tossRevives(session):
    bag = session.checkInventory()["bag"]

    # 201 are revives.
    # TODO: We should have a reverse lookup here
    if 201 in bag:
        if bag[201] > 0:
            session.recycleItem(201, bag[201])
    if 101 in bag:
        if bag[101] > 0:
            session.recycleItem(101,bag[101])
    return None

def cleanInventory(session):
    tossItem(session,201) #revive
    tossItem(session,202) #max revive
    tossItem(session,101) #potions
    tossItem(session,102)
    tossItem(session,103)
    tossItem(session,104)
    tossItem(session,1,minimum=60) #pokeball
    tossItem(session,2,minimum=60) #greatball
    tossItem(session,701,minimum=20) #razzberry
    

def tossItem(session,itemid,minimum=0):
    bag = session.checkInventory()['bag']
    
    if itemid in bag:
        if bag[itemid] > minimum:
            logging.info("tossing out ({n}) {id} items...".format(n=(bag[itemid]-minimum),id=itemid))
            return session.recycleItem(itemid,bag[itemid]-minimum)

# Set an egg to an incubator
def setEgg(session):
    inventory = session.checkInventory()

    # If no eggs, nothing we can do
    if len(inventory["eggs"]) == 0:
        return None

    egg = inventory["eggs"][0]
    incubator = inventory["incubators"][0]
    eggresult = session.setEgg(incubator, egg)
    if eggresult:
        return eggresult.result
    return None
        
def updateBotData(session,botdata):
    botdata.updateStats(session.checkInventory()['stats'])
    botdata.updateParty(session.checkInventory()['party'])
    botdata.updateIncubators(session.checkInventory()['incubators'])
    botdata.updateCandies(session.checkInventory()['candies'])

# Basic bot
def simpleBot(poko_session,session,botdata,args):
    # Trying not to flood the servers
    botdata.started()
    updateBotData(session,botdata)
    cooldown = 1
    reconnect = False

    # Run the bot
    while True:
        try:
            while False: #reconnect or session is None:
                reconnect = False
                try:
                    logging.info("Trying to reconnect...")
                    newsession = None
                    if session is None:
                        newsession = poko_session.authenticate(botdata.getCoordinatesString())
                    else:
                        newsession = poko_session.reauthenticate(session)
                    if newsession is None:
                        reconnect = True
                    else:
                        session = newsession
                        session.location = LocationPersistent(session.location,botdata)
                except KeyboardInterrupt:
                    raise
                except:
                    #session = None
                    cooldown *= 2
                    time.sleep(cooldown)
                    reconnect = True
            cooldown = 1
            #find and catch all nearby pokemon
            #go to the nearest pokestop
            #empty inventory
            #sacrifice duplicate pokemon
            cleanUpPokemon(session)
            forts = sortCloseForts(session,radius=3)
            logging.info("going through {count} forts...".format(count=len(forts)))
            for fort in forts:
                logging.info("Cleaning out inventory...")
                cleanInventory(session)
                logging.info("Heading to {fort} Pokestop...".format(fort=fort))
                while not walkToNonBlock(session,fort.latitude,fort.longitude,step=args.velocity,interval=25):
                    egg = setEgg(session)
                    if egg is not None:
                        logging.info("dropped an egg in the incubator: {egg}".format(egg=egg))
                    pokemon = findClosestPokemon(session,radius=int(args.velocity*1.6))
                    bag = session.checkInventory()['bag']
                    while pokemon is not None and bag[1] is not None and bag[1] > 0:
                        logging.info("Taking a break to catch Pokemon...")
                        walkAndCatch(session, pokemon, step=args.velocity)
                        cleanUpPokemon(session)
                        updateBotData(session,botdata)
                        logging.info(getTrainerSummary(session))
                        bag = session.getInventory()['bag']
                        pokemon = findClosestPokemon(session,radius=int(args.velocity*1.6))
                        if pokemon is None or bag[1] is None or (bag[1] is not None and bag[1] == 0):
                            logging.info("Continuing back to {fort} Pokestop...".format(fort=fort))
                    if distanceToFort(session,fort) > (args.velocity*75):
                        break
                if distanceToFort(session,fort) > (args.velocity*75):
                    logging.info("fort is way too far away, reseting fort loop")
                    break
                walkAndSpin(session, fort, step=args.velocity)
                cfort = findClosestFort(session)
                bag = session.checkInventory()['bag']
                if bag[1] is not None and bag[1] > 0 and cfort.id == fort.id and cfort.lure_info is not None and cfort.lure_info.encounter_id != 0:
                    logging.info("Pokestop is lured, trying to catch the pokemon!")
                    logging.info(encounterAndCatchPokemonAtLure(session,cfort))
                updateBotData(session,botdata)
                logging.info(getTrainerSummary(session))
                cooldown = 1
                time.sleep(1)
        except KeyboardInterrupt:
            raise
        # Catch problems and reauthenticate
        except GeneralPogoException as e:
            logging.critical('GeneralPogoException raised: %s', e)
            reconnect = True
            session = poko_session.reauthenticate(session)
            session.location = LocationPersistent(session.location,botdata)
            time.sleep(cooldown)
            cooldown *= 2

        except Exception as e:
            logging.critical('Exception raised: %s', e)
            reconnect = True
            session = poko_session.reauthenticate(session)
            session.location = LocationPersistent(session.location,botdata)
            time.sleep(cooldown)
            cooldown *= 2

def cleanpokemonBot(poko_session,session,botdata,args):
    updateBotData(session,botdata)
    releaseShittyPokemonButKeepEnoughToPowerLevel(session,minperfect=0.85,minalmostperfect=0.8,mincp=1300)
    #releaseShittyPokemon(session,minperfect=0.8,minalmostperfect=0.7)
    updateBotData(session,botdata)
    return

def justUpdateBot(poko_session,session,botdata,args):
    updateBotData(session,botdata)
    return
            
class LocationPersistent(Location):
    def __init__(self, location, botdata):
        self.geo_key = location.geo_key
        self.locator = location.locator
        self.location = location
        self.latitude, self.longitude, self.altitude = location.getCoordinates()
        self.botdata = botdata
    
    def setCoordinates(self, latitude, longitude):
        logging.debug("persisting coordinates: {lat} {long}".format(lat=latitude, long=longitude))
        Location.setCoordinates(self,latitude,longitude)
        self.botdata.setCoordinates(latitude,longitude)            
            
# Entry point
# Start off authentication and demo
if __name__ == '__main__':
    setupLogger()
    logging.debug('Logger set up')
    
    # Read in args
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--auth", help="Auth Service", required=True)
    parser.add_argument("-u", "--username", help="Username", required=True)
    parser.add_argument("-p", "--password", help="Password", required=True)
    parser.add_argument("--velocity", help="travel speed in m/s",type=float,default=3)
    parser.add_argument("--bottype", help="bot to run",default="simplebot")
    parser.add_argument("-l", "--location", help="Location")
    parser.add_argument("-g", "--geo_key", help="GEO API Secret")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    
    botdata = BotData('botdata/'+args.username+'.botdata.dat')
    
    if not args.location:
        args.location = botdata.getCoordinatesString()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    #if not args.geo_key:
    #    args.geo_key = "AIzaSyDT0PgHB8T4wYFw0_YDyStrp49bcktEsBI"

    # Check service
    if args.auth not in ['ptc', 'google']:
        logging.error('Invalid auth service {}'.format(args.auth))
        sys.exit(-1)
    
    # Create PokoAuthObject
    poko_session = PokeAuthSession(
        args.username,
        args.password,
        args.auth,
        geo_key=args.geo_key
    )

    # Authenticate with a given location
    # Location is not inherent in authentication
    # But is important to session
    session = poko_session.authenticate(args.location)
    session.location = LocationPersistent(session.location,botdata)
    updateBotData(session,botdata)

    # Time to show off what we can do
    if session:

        # General
        getProfile(session)
        logging.info("Starting a bot from {coords}...".format(coords=botdata.getCoordinatesString()))
        
        if args.bottype == "simplebot":
            simpleBot(poko_session,session,botdata,args)
        if args.bottype == "cleanpokemon":
            cleanpokemonBot(poko_session,session,botdata,args)
        if args.bottype == "justupdate":
            justUpdateBot(poko_session,session,botdata,args)

    else:
        logging.critical('Session not created successfully')
