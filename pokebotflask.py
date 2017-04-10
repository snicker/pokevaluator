# encoding=utf8
import sys
reload(sys)
sys.setdefaultencoding('utf8')
from math import sqrt, floor
from flask import Flask, redirect, render_template, request, jsonify
import json
from botdata import BotData
from pgoapi import PGoApi
from pgoapi.protos.pogoprotos.enums.pokemon_move_pb2 import PokemonMove
from datetime import datetime
import os
import time
import csv
import logging
app = Flask(__name__)
#https://github.com/DavydeVries/PoGO-Awesome todo
#moves data https://docs.google.com/spreadsheets/d/1vLkzORkHuiq5hGrI2Pc3ZQUM_aPKXpB6jUeg6dydNtQ/edit#gid=1493616609
ACCOUNTS = {}
POKEHASH = None
API = None
ENCRYPT_PATH = '/usr/home/snicker/devel/pyenvs/pokebot/libencrypt.so'

class StaticLocation(object):
    def setLocation(self, search):
        return 0, 0, 0

class FakeSession(object):
    def __init__(self, location):
        self.location = location

class InventoryItem(dict):
    def __init__(self, basedict):
        for key in basedict:
            self[key] = basedict[key]
        
    def __getattr__(self, name):
        if name in self:   
            return self[name]
        else:
            raise AttributeError

class PokemonItem(InventoryItem):
    @property
    def individual_attack(self):
        return self.get('individual_attack',0)
    @property
    def individual_defense(self):
        return self.get('individual_defense',0)
    @property
    def individual_stamina(self):
        return self.get('individual_stamina',0)
    @property
    def favorite(self):
        return self.get('favorite',0)
    @property
    def battles_attacked(self):
        return self.get('battles_attacked',0)
    @property
    def battles_defended(self):
        return self.get('battles_defended',0)
    @property
    def special_types(self):
        stypes = []
        if self.pokemon_id in (25,26): #raichu, pikachu
            catchtime = datetime.fromtimestamp(self.creation_time_ms/1000)
            if catchtime >= datetime(2017,2,26) and catchtime <= datetime(2017,3,8):
                stypes.append('party-hat')
            if catchtime >= datetime(2016,12,11) and catchtime <= datetime(2016,12,31):
                stypes.append('santa-hat')
        return stypes

class pgoapiSession(object):
    def __init__(self, account={}):
        self.account = account
        self.seshdata = None
        self.invdata = None
        self._api = None
        
    def refresh(self):
        self.seshdata = None
        self.invdata = None
    
    @property
    def api(self):
        if self._api is None:
            self._api = PGoApi(provider=self.account.get('auth') or 'google', username=self.account.get('user'), password = self.account.get('pass'))
            if POKEHASH is not None:
                self._api.activate_hash_server(POKEHASH)
        return self._api
        
    def get_seshdata(self,forcerefresh = False):
        if self.seshdata is None or forcerefresh:
            self.api.set_position(0,0)
            req = self.api.create_request()
            req.get_player()
            req.get_inventory()
            self.seshdata = req.call()
        return self.seshdata
        
    @property
    def inventory_items(self):
        if self.get_seshdata():
            return self.get_seshdata().get('responses',{}).get('GET_INVENTORY',{}).get('inventory_delta',{}).get('inventory_items',[])
    
    @property
    def player_data(self):
        if self.get_seshdata():
            return self.get_seshdata().get('responses',{}).get('GET_PLAYER',{}).get('player_data',{})
    
    def getInventory(self):
        if self.invdata is None:
            return self.checkInventory()
        return self.invdata

    def evolvePokemon(self, pokemon):
        self.api.set_position(0,0)
        request = self.api.create_request()
        request.evolve_pokemon(pokemon_id=pokemon.id)
        response = request.call()
        return response
        
    def releasePokemon(self, pokemon):
        self.api.set_position(0,0)
        request = self.api.create_request()
        request.release_pokemon(pokemon_id=pokemon.id)
        response = request.call()
        return response
        
    def favoritePokemon(self, pokemon, is_favorite=True):
        self.api.set_position(0,0)
        request = self.api.create_request()
        request.set_favorite_pokemon(pokemon_id=pokemon.id,is_favorite=is_favorite)
        response = request.call()
        return response
        
    def releaseMultiplePokemon(self, pokemen):
        self.api.set_position(0,0)
        request = self.api.create_request()
        pokemon_ids = []
        for pokemon in pokemen:
            pokemon_ids.append(pokemon.id)
        request.release_pokemon(pokemon_ids=pokemon_ids)
        response = request.call()
        return response
    
    def checkInventory(self):
        self.invdata = {}
        self.invdata["incubators"] = []
        self.invdata["pokedex"] = {}
        self.invdata["candies"] = {}
        self.invdata["stats"] = {}
        self.invdata["party"] = []
        self.invdata["eggs"] = []
        self.invdata["bag"] = {}
        seshdata = self.get_seshdata(forcerefresh=True)
        seshinvdata = seshdata.get('responses',{}).get('GET_INVENTORY',{}).get('inventory_delta',{}).get('inventory_items',[])
        for item in seshinvdata:
            data = item['inventory_item_data']
            if "player_stats" in data:
                self.invdata["stats"] = InventoryItem(data['player_stats'])
                continue
            pokedexEntry = data.get('pokedex_entry',None)
            if pokedexEntry:
                self.invdata["pokedex"][pokedexEntry['pokemon_id']] = InventoryItem(pokedexEntry)
                continue
            pokemonFamily = data.get('candy', None)
            if pokemonFamily:
                self.invdata["candies"][pokemonFamily.get('family_id')] = pokemonFamily.get('candy',0)
                continue
            pokemonData = data.get("pokemon_data", None)
            if pokemonData:
                if pokemonData.get('is_egg'):
                    self.invdata["eggs"].append(InventoryItem(pokemonData))
                else:
                    self.invdata["party"].append(PokemonItem(pokemonData))
                continue
            incubators = data.get("egg_incubators", None)
            if incubators:
                self.invdata["incubators"] = incubators.get('egg_incubator')
                continue
            bagItem = data.get("item", None)
            if bagItem:
                self.invdata["bag"][bagItem.get('item_id')] = bagItem.get('count')
                continue
        #self.invdata['party'] = [InventoryItem(item.get('inventory_item_data').get('pokemon_data')) for item in seshinvdata if 'pokemon_data' in item.get('inventory_item_data')]
        return self.invdata

def pokemonAsString(pokemon):
    return "{id}: {a}/{d}/{s} ({cp})".format(id=pokemon.pokemon_id,a=pokemon.individual_attack,d=pokemon.individual_defense,s=pokemon.individual_stamina,cp=pokemon.cp)        

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
        candy_per_evolve = (get_pokemon_data({'pokemon_id': id}) or {}).get('candy_to_evolve')
        if candy_per_evolve is not None:
            logging.debug("it takes {x} candies to evolve {y}".format(x=candy_per_evolve,y=id))
            remainingtokeep[id] = int(float(candies[id])/candy_per_evolve)
            remainingtokeep[id] += int(float(remainingtokeep[id]) / candy_per_evolve)
            logging.debug("we should keep {x} pokemon of id {y}".format(x=remainingtokeep[id],y=id))
    party = inv['party']
    tokeep = []
    for pokemon in party:
        if isPokemonGood(session,pokemon,minperfect=minperfect,minalmostperfect=minalmostperfect,mincp=mincp) or len(pokemon.special_types) > 0 or pokemon.get('favorite') == 1:
            if pokemon.id not in tokeep:
                logging.debug("{p} is good, adding to list...".format(p=pokemonAsString(pokemon)))
                if pokemon.get('favorite') == 1:
                    logging.debug("{p} is favorited, adding to list...".format(p=pokemonAsString(pokemon)))
                if len(pokemon.special_types) > 0:
                    logging.debug("{p} has special types {stypes}, adding to list...".format(p=pokemonAsString(pokemon), stypes=pokemon.special_types))
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
    if len(torelease) > 0:
        session.releaseMultiplePokemon(torelease)
    #for pokemon in torelease:
    #    logging.info("releasing pokemon {p}...".format(p=pokemonAsString(pokemon)))
    #    session.releasePokemon(pokemon)
    #    time.sleep(1)
        #session.getInventory()
        #time.sleep(1)
        

def updateBotData(session,botdata):
    inventory = session.checkInventory()
    botdata.updateStats(inventory['stats'])
    botdata.updateParty(inventory['party'])
    botdata.updateIncubators(inventory['incubators'])
    botdata.updateCandies(inventory['candies'])  
    if session.player_data:
        botdata.updatePlayerData(session.player_data)

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
    party = session.getInventory()['party']
    highestcp = -1
    for pp in party:
        if pp.pokemon_id == pokemon.pokemon_id and pp.cp > highestcp:
            highestcp = pp.cp
    return highestcp
    
def getPerfectForPokemon(session,pokemon):
    return float(int(pokemon.get('individual_attack') or 0) + int(pokemon.get('individual_defense') or 0) + int(pokemon.get('individual_stamina') or 0)) / 45
        
@app.route("/")
def index():
    out = ""
    for account in ACCOUNTS:
        name = account['name']
        out = out + "<a href='/{account}/'>{account}</a><br />".format(account=name)
    return out

@app.route("/<accountname>/release", methods=['POST'])
def release_pokemon(accountname):
    pokemon_ids = request.form.getlist('selected_pokemon')
    if len(pokemon_ids) > 0:
        torelease = []
        botdata = get_bot_data(accountname)
        session = get_poko_session(accountname)
        if botdata is not None and session is not None:
            party = get_party(session)
            for pokemon in party:
                for id in pokemon_ids:
                    if str(id) == str(pokemon.id):
                        torelease.append(pokemon)
            #session.releaseMultiplePokemon(torelease)
            for pokemon in torelease:
                session.releasePokemon(pokemon)
                time.sleep(0.1)
                session.getInventory()
                time.sleep(0.9)
            session.checkInventory()
            updateBotData(session,botdata)
    return redirect('/{}/'.format(accountname))
    
    
def batch_evolve(accountname, pokemen, delay=4):
    session = get_poko_session(accountname)
    results = []
    for pokemon in pokemen:
        print("evolving {}".format(pokemon))
        response = session.evolvePokemon(pokemon)
        success = response.get('responses',{}).get('EVOLVE_POKEMON',{}).get('result') == 1
        if success:
            evolved_pokemon = response.get('responses',{}).get('EVOLVE_POKEMON',{}).get('evolved_pokemon_data')
            if evolved_pokemon:
                evolved_pokemon = PokemonItem(evolved_pokemon)
                evolved_pokemon['previous_id'] = str(pokemon.id)
                results.append(evolved_pokemon)
        time.sleep(delay)
    session.checkInventory()
    return results
    
def batch_favorite(accountname, pokemen, delay=0.3):
    session = get_poko_session(accountname)
    results = []
    for pokemon in pokemen:
        fav_toggled = False if pokemon.favorite == 1 else True
        response = session.favoritePokemon(pokemon,fav_toggled)
        if response.get('responses',{}).get('SET_FAVORITE_POKEMON',{}).get('result') == 1:
            pokemon['favorite'] = 1 if fav_toggled else None
        time.sleep(delay)
    return pokemen

def batch_release(accountname, pokemen, delay=1):
    session = get_poko_session(accountname)
    session.releaseMultiplePokemon(pokemen)
    return pokemen
    
@app.route("/<accountname>/batch_action_on_selected", methods=['POST'])
def batch_action_on_selected_route(accountname):
    pokemon_ids = request.form.getlist('selected_pokemon')
    action = request.form.get('action_on_selected')
    batch_action_on_selected(accountname, pokemon_ids, action)
    return redirect('/{}/'.format(accountname))    

def batch_action_on_selected(accountname, pokemon_ids, action, delay=None):
    valid_actions = {'evolve': batch_evolve, 'favorite': batch_favorite, 'release': batch_release}
    pokemen_results = []
    if action in valid_actions:
        botdata = get_bot_data(accountname)
        session = get_poko_session(accountname)
        pokemen = []
        batch_results = []
        if botdata is not None and session is not None:
            party = get_party(session)
            for pokemon in party:
                for id in pokemon_ids:
                    if str(id) == str(pokemon.id):
                        pokemen.append(pokemon)
        if delay is not None:
            batch_results = valid_actions[action](accountname, pokemen, delay=delay)
        else:
            batch_results = valid_actions[action](accountname, pokemen)
        updateBotData(session,botdata)
        pokemen_results = pokemonlist(botdata,party=batch_results)
    return pokemen_results

@app.route("/<accountname>/rspbke2p", methods=['POST','GET'])
def rspbke2p(accountname):
    botdata = get_bot_data(accountname)
    session = get_poko_session(accountname)
    if botdata is not None and session is not None:
        releaseShittyPokemonButKeepEnoughToPowerLevel(session,minperfect=0.85,minalmostperfect=0.8,mincp=1300)
        updateBotData(session,botdata)
        return redirect('/{}/'.format(accountname))
    return redirect('/')
    
def get_formatted_pokemon_name(p):
    return ("{nickname} ({name})" if p['nickname'] else "{name}").format(nickname=p['nickname'],name=p['name'])
    
def padded_pokemon_id(p):
    return "%03d" % int(p['pokemon_id'])

def get_battles(p):
    return "{attacked} :: {defended}".format(attacked=p['battles_attacked'],defended=p['battles_defended'])

def process_template_column(column,p):
    if callable(column):
        return column(p)
    return p[column]
        
@app.route("/<accountname>/")
def account_v2(accountname):
    accountdata = get_account_data(accountname)
    if accountdata is None:
        return redirect('/')
    username = accountdata['user']
    data = BotData('botdata/'+username+'.botdata.dat')
    pokemen = pokemonlist(data)
    evolvelist = list_of_evolvable_pokemon(pokemen,data.data['candies'])
    total_stardust_spent = sum([p.get('currency_spent_on_pokemon',{}).get('stardust_cost') for p in pokemen])
    stardust = sum([c.get('amount',0) for c in data.getPlayerData().get('currencies',[]) if c.get('name') == 'STARDUST'])
    total_stardust = total_stardust_spent + stardust
    stardust_per_day = int((total_stardust + 0.0) / (data.created() / 60 / 60 / 24))
    columns = [
        ['pokemon_id', 'Pokedex #', ['data-sortable-numeric']],
        ['name', 'Pokemon Name', []],
        ['candies', '# Candies', ['data-sortable-numeric']],
        ['level', 'Level', ['data-sortable-numeric']],
        ['cp', 'CP', ['data-sortable-numeric']],
        ['max_cp_at_player_level', 'Max CP', ['data-sortable-numeric']],
        ['max_cp_at_max_evolution', 'Max CP (fully evolved)', ['data-sortable-numeric']],
        ['attack', 'ATK', ['data-sortable-numeric']],
        ['defense', 'DEF', ['data-sortable-numeric']],
        ['stamina', 'STA', ['data-sortable-numeric']],
        ['perfect', '% Perfect', ['data-sortable-numeric']],
        ['move1', 'Primary Move', []],
        ['move2', 'Secondary Move', []],
        ['height', 'Height', ['data-sortable-numeric']],
        ['weight', 'Weight', ['data-sortable-numeric']],
        ['battles_attacked', 'Battles - Attacked', ['data-sortable-numeric']],
        ['battles_defended', 'Battles - Defended', ['data-sortable-numeric']],
        ['powerups', '# Power ups', ['data-sortable-numeric']],
        ['catchdate', 'Date Caught', []]
    ]
    return render_template('account.html',
        accountname=accountname,
        accountdata=accountdata,
        userdata=data,
        pokemen=pokemen,
        pokemon_columns=columns,
        evolvelist=evolvelist,
        totalevolutions=sum(evolvelist[x] for x in evolvelist),
        PDATA=PDATA,
        BETTERPDATA=BETTERPDATA,
        process_template_column=process_template_column,
        total_stardust_spent = total_stardust_spent,
        stardust = stardust,
        stardust_per_day = stardust_per_day
    )

@app.route("/<accountname>/evolvelist")
def evolvelist(accountname):
    accountdata = get_account_data(accountname)
    if accountdata is None:
        return redirect('/')
    username = accountdata['user']
    data = BotData('botdata/'+username+'.botdata.dat')
    pokemen = pokemonlist(data)
    evolvelist = list_of_evolvable_pokemon(pokemen,data.data['candies'])
    evolvablepokemon = []
    for id in evolvelist:
        if evolvelist[id] > 0:
            evolvablepokemon.append({
                'pokemon_id':id,
                'name': get_pokemon_name({'pokemon_id': id}), 
                'count': evolvelist[id]
            })
    evolvablepokemon = sorted(evolvablepokemon, key=lambda x: x['pokemon_id'])
    columns = [
        ['pokemon_id', 'Pokedex #'],
        ['name', 'Pokemon Name'],
        ['count', 'Available Pokemon To Evolve']
    ]
    return render_template('evolvelist.html',
        accountdata=accountdata,
        userdata=data,
        pokemen=evolvablepokemon,
        pokemon_columns=columns,
        evolvelist=evolvelist,
        totalevolutions=sum(evolvelist[x] for x in evolvelist),
        PDATA=PDATA,
        BETTERPDATA=BETTERPDATA,
        process_template_column=process_template_column
    )
    
@app.route("/<accountname>/refresh")
def refresh_account(accountname):
    try:
        botdata = get_bot_data(accountname)
        session = get_poko_session(accountname)
        if botdata is None or session is None:
            return redirect('/')
        updateBotData(session,botdata)
        return redirect('/{}/'.format(accountname))
    except Exception as e:
        raise e
        return redirect('/')
        
@app.route("/api/<accountname>/party",methods=['GET'],defaults={'refresh': False})
@app.route("/api/<accountname>/party/<refresh>",methods=['GET'])
def api_account_party(accountname,refresh=False):
    botdata = get_bot_data(accountname)
    session = get_poko_session(accountname)
    if botdata is None or session is None:
        return jsonify({'success': False})
    if refresh:
        updateBotData(session,botdata)
    pokemen = pokemonlist(botdata)
    return jsonify({'success': True, 'partydelta': {'added': pokemen}})
    
@app.route("/api/<accountname>/favorite", methods=['POST'])
def api_toggle_favorite(accountname):
    if not request.json or 'pokemon_ids' not in request.json:
        return jsonify({'success': False})
    pokemon_ids = request.json.get('pokemon_ids')
    if(len(pokemon_ids) > 0):
        delay = 0 if len(pokemon_ids) == 1 else None
        pokemen = batch_action_on_selected(accountname, pokemon_ids, 'favorite', delay=delay)
    return jsonify({'success': True, 'partydelta': {'changed': pokemen}})
    
@app.route("/api/<accountname>/evolve", methods=['POST'])
def api_evolve(accountname):
    if not request.json or 'pokemon_ids' not in request.json:
        return jsonify({'success': False})
    pokemon_ids = request.json.get('pokemon_ids')
    if(len(pokemon_ids) > 0):
        delay = 0 if len(pokemon_ids) == 1 else None
        pokemen = batch_action_on_selected(accountname, pokemon_ids, 'evolve', delay=delay)
    return jsonify({'success': True, 'partydelta': {'changed': pokemen}})
    
@app.route("/api/<accountname>/release", methods=['POST'])
def api_release(accountname):
    if not request.json or 'pokemon_ids' not in request.json:
        return jsonify({'success': False})
    pokemon_ids = request.json.get('pokemon_ids')
    if(len(pokemon_ids) > 0):
        delay = 0 if len(pokemon_ids) == 1 else None
        pokemen = batch_action_on_selected(accountname, pokemon_ids, 'release', delay=delay)
    return jsonify({'success': True, 'partydelta': {'released': pokemen}})
    
def get_party(session):
    inv = session.checkInventory()
    if inv:
        return inv['party']
    return None

def get_poko_session(accountname):
    try:
        accountdata = get_account_data(accountname)
        if accountdata is not None: 
            return pgoapiSession(account=accountdata)
            poko_session = PokeAuthSession(
                accountdata['user'],
                accountdata['pass'],
                accountdata['auth']
            )
            fakesesh = FakeSession(StaticLocation('',''))
            session = poko_session.reauthenticate(fakesesh)
            return session
    except Exception as e:
        raise e
    return None
        
def get_bot_data(accountname):
    try:
        accountdata = get_account_data(accountname)
        if accountdata is not None: 
            return BotData('botdata/'+accountdata['user']+'.botdata.dat')
    except Exception as e:
        raise e
    return None
        

@app.route("/botlist/")
def botlist():
    output = "bots:<br/>"
    for file in os.listdir('botdata/'):
        data = BotData('botdata/'+file)
        botname = file.replace('.botdata.dat','')
        output = output + '<a href="{botname}/">{botname}</a>: {botsummary}<br/>'.format(botsummary=data.botSummary(),botname=botname)
    return output

@app.route("/botlist/<username>/")
def botpage(username):
    data = BotData('botdata/'+username+'.botdata.dat')
    return """
    <html>
    <head>
    <script src="http://www.kryogenix.org/code/browser/sorttable/sorttable.js"></script>
    </head>
    <body>
    Trainer Summary for {username}: (<a href="incubators/">view incubators</a>)<br/>
    {summary}<br/>
    <a href="http://www.google.com/maps/search/{coords}" target="_new">{coords}</a><br/>
<iframe
  width="600"
  height="450"
  frameborder="0" style="border:0"
  src="https://www.google.com/maps/embed/v1/place?key=AIzaSyCPwgL4hSJmqS8dAIGQdnT_wlLoM7PAcIk&q={coords}" allowfullscreen>
</iframe>    <br/>
{plist}
</body>
""".format(username=username,summary=data.botSummary(),coords=data.getCoordinatesString(),plist=pokemonlist_html(data))


@app.route("/botlist/<username>/incubators/")
def incubators(username):
    data = BotData('botdata/'+username+'.botdata.dat')
    output = ""
    for incubator in data.getIncubators():
        output = output + "{incubator}<br/><br/>".format(incubator=incubator).replace("\n","<br/>")
    return output

def pokemon_formatted(pokemon):
    p = {}
    p['catchdate'] = time.strftime('%Y-%m-%d %H:%M',time.gmtime(pokemon.creation_time_ms/1000))
    p['pokemon_id'] = pokemon.pokemon_id
    p['name'] = get_pokemon_name(pokemon)
    p['nickname'] = pokemon.get('nickname')
    p['cp'] = pokemon.cp
    p['attack'] = pokemon.get('individual_attack',0)
    p['defense'] = pokemon.get('individual_defense',0)
    p['stamina'] = pokemon.get('individual_stamina',0)
    p['perfect'] = "{:0.1f}%".format(getPerfectForPokemon(None,pokemon)*100)
    p['move1'] = get_move_name(pokemon.move_1)
    p['move2'] = get_move_name(pokemon.move_2)
    p['height'] = "{:0.2f}".format(pokemon.height_m)
    p['weight'] = "{:0.2f}".format(pokemon.weight_kg)
    p['battles_attacked'] = pokemon.battles_attacked
    p['battles_defended'] = pokemon.battles_defended
    p['powerups'] = pokemon.get('num_upgrades',0)
    p['favorite'] = pokemon.get('favorite')
    p['id'] = str(pokemon.id)
    p['level'] = get_level_for_pokemon(p)
    p['cpl'] = p['cp'] / p['level'] if p['level'] > 0 else 0
    p['special_types'] = pokemon.special_types
    p['currency_spent_on_pokemon'] = get_currency_spent_on_pokemon(p)
    return p
    
def pokemonlist(botdata,party=None):
    global PDATA
    pokemen = []
    party = party or botdata.getParty()
    stats = botdata.getStats()
    level = 0
    if stats:
        level = stats.level
    for pokemon in party:
        p = pokemon_formatted(pokemon)
        candytypeforpokemon = get_candy_type_for_pokemon(p)
        p['candies'] = botdata.getCandiesFor(candytypeforpokemon)
        p['max_cp_at_player_level'] = get_cp_for_pokemon(p,level+1.5)
        p['max_cp_at_max_evolution'] = get_cp_for_fully_evolved_pokemon(p,level=level+1.5)
        p['previous_id'] = pokemon.get('previous_id')
        future_costs = get_currency_spent_on_pokemon(p,level=level+1.5)
        p['candy_cost_to_max_level'] = future_costs.get('candy_cost') - p['currency_spent_on_pokemon'].get('candy_cost')
        p['stardust_cost_to_max_level'] = future_costs.get('stardust_cost') - p['currency_spent_on_pokemon'].get('stardust_cost')
        pokemen.append(p)
    pokemen = sorted(pokemen, key=lambda k: k['cp'], reverse=True)
    return pokemen

def list_of_evolvable_pokemon(pokemonlist,candies):
    pokemon_by_candy = [x[1] for x in sorted(BESTPDATA.items(), key=lambda x: x[1].get('candy_to_evolve',0))]
    availablecandies = {}
    pokemon_to_evolve = {}
    remainingtokeep = {}
    for id in candies:
        availablecandies[id] = candies[id]
    for pdata in pokemon_by_candy:
        candies_per_evolve = int(pdata.get('candy_to_evolve',0))
        id = int(pdata['pokemon_id'])
        if candies_per_evolve > 0:
            if id in availablecandies and availablecandies[id] > 0:
                remainingtokeep[id] = int(float(availablecandies[id])/candies_per_evolve)
                remainingtokeep[id] += int(float(remainingtokeep[id]) / candies_per_evolve)
                availablecandies[id] -= remainingtokeep[id] * candies_per_evolve
    for id in remainingtokeep:
        pokemon_to_evolve[id] = min(remainingtokeep[id],sum(1 for p in pokemonlist if p['pokemon_id'] == id))
    return pokemon_to_evolve
    

def get_pokemon_data(pokemon):
    return BESTPDATA.get(pokemon['pokemon_id'])
    
def get_candy_type_for_pokemon(pokemon):
    pdata = get_pokemon_data(pokemon)
    if pdata is not None:
        family = pdata.get('family_id')
        for p in BESTPDATA:
            if BESTPDATA[p].get('family_id') == family:
                return int(BESTPDATA[p]['pokemon_id'])
    return pokemon['pokemon_id']
    
CPM = [ 0.094     ,  0.16639787,  0.21573247,  0.25572005,  0.29024988,
        0.3210876 ,  0.34921268,  0.37523559,  0.39956728,  0.42250001,
        0.44310755,  0.46279839,  0.48168495,  0.49985844,  0.51739395,
        0.53435433,  0.55079269,  0.56675452,  0.58227891,  0.59740001,
        0.61215729,  0.62656713,  0.64065295,  0.65443563,  0.667934  ,
        0.68116492,  0.69414365,  0.70688421,  0.71939909,  0.7317    ,
        0.73776948,  0.74378943,  0.74976104,  0.75568551,  0.76156384,
        0.76739717,  0.7731865 ,  0.77893275,  0.78463697,  0.79030001]

def get_cpm_for_level(level):
    level = min(max(1,level),40)
    cpm1 = CPM[int(floor(level) - 1)]
    cpm2 = CPM[int(min(39,floor(level)))]
    return cpm1 + ( (cpm2-cpm1) * (level % 1) ) 
        
def get_cp_for_pokemon(pokemon,level=None):
    if level is None:
        return pokemon['cp']
    m = get_cpm_for_level(level)
    pdata = get_pokemon_data(pokemon)
    if pdata is not None:
        stats = pdata.get('stats',{})
        stam = (int(stats.get('base_stamina',0)) + pokemon['stamina']) * m
        attk = (int(stats.get('base_attack',0)) + pokemon['attack']) * m
        dfns = (int(stats.get('base_defense',0)) + pokemon['defense']) * m
        cp = int(max(10, floor(sqrt(attk * attk * dfns * stam) / 10)))
        return cp
    return -1
    
def get_cp_for_fully_evolved_pokemon(pokemon, level=None):
    if level is None:
        level = get_level_for_pokemon(pokemon)
    evolutions = get_final_evolution_for_pokemon(pokemon)
    results = []
    for evolution in evolutions:
        evolved_pokemon = pokemon.copy()
        evolved_pokemon['pokemon_id'] = evolution
        results.append((get_cp_for_pokemon(evolved_pokemon,level=level),evolution))
    results = sorted(results, key=lambda x: x[0],reverse=True)
    return results[0] if len(results) > 0 else (-1,-1)
        
def get_final_evolution_for_pokemon(pokemon):
    pdata = get_pokemon_data(pokemon)
    next_evolutions = [b.get('evolution') for b in pdata.get('evolution_branch',[])]
    if len(next_evolutions) == 0:
        return [pokemon.get('pokemon_id')]
    evolutions = []
    for evolution in next_evolutions:
        evolutions.extend(get_final_evolution_for_pokemon({'pokemon_id': evolution}))
    return evolutions

def get_level_for_pokemon(pokemon):
    levels = {}
    pdata = get_pokemon_data(pokemon)
    if pdata is not None:
        stats = pdata.get('stats',{})
        stam = int(stats.get('base_stamina',0)) + pokemon['stamina']
        attk = int(stats.get('base_attack',0)) + pokemon['attack']
        dfns = int(stats.get('base_defense',0)) + pokemon['defense']
        cp = pokemon['cp']
        levels[10] = ( ( 10 * cp / ( attk * sqrt(stam) * sqrt(dfns) ) ) - 0.01001625 ) / 0.01885225
        levels[20] = ( ( 10 * cp / ( attk * sqrt(stam) * sqrt(dfns) ) ) - 0.17850625 ) / 0.01783805 + 10
        levels[30] = ( ( 10 * cp / ( attk * sqrt(stam) * sqrt(dfns) ) ) - 0.35688675 ) / 0.01784981 + 20
        levels[40] = ( ( 10 * cp / ( attk * sqrt(stam) * sqrt(dfns) ) ) - 0.53538485 ) / 0.00891892 + 30
        for lmax in (10,20,30,40):
            if levels[lmax] <= lmax:
                return max(0,round(levels[lmax] * 2) / 2)
    return -1
    
def get_candy_spent_on_pokemon(pokemon, level = None):
    return get_currency_spent_on_pokemon(pokemon,'candy_cost', level=level)

def get_stardust_spent_on_pokemon(pokemon, level = None):
    return get_currency_spent_on_pokemon(pokemon,'stardust_cost', level=level)
    
def get_currency_spent_on_pokemon(pokemon,currency_type = None, level = None):
    valid_currency_types = ('candy_cost','stardust_cost')
    if currency_type not in valid_currency_types:
        out = {}
        map(lambda x: out.update(get_currency_spent_on_pokemon(pokemon, x, level=level)),valid_currency_types)
        return out
    currency_per_level = next((x['pokemon_upgrades'] for x in POKEMONDATA['responses']['DOWNLOAD_ITEM_TEMPLATES']['item_templates'] if 'pokemon_upgrades' in x),{}).get(currency_type)
    pokemon_level = min(40,level or get_level_for_pokemon(pokemon))
    num_upgrades = pokemon.get('powerups',0)
    totalcost = 0
    if currency_per_level is not None and pokemon_level > -1 and num_upgrades > 0:
        while num_upgrades > 0:
            pokemon_level -= 0.5
            totalcost += currency_per_level[max(0,int(pokemon_level-1))]
            num_upgrades -= 1
    return {currency_type: totalcost}

def get_move_name(moveid):
    desc = PokemonMove.DESCRIPTOR
    for (k,v) in desc.values_by_name.items():
        if v.number == moveid:
            return k.replace('_FAST','').replace("_"," ").title()
    return None # if val isn't a value in MyEnumType    

def get_pokemon_name(pokemon):
    pdata = get_pokemon_data(pokemon)
    if pdata is not None:
        template_id = pdata.get('template_id','')
        return template_id[template_id.find('POKEMON_')+8:].title()
    return 'unknown pkmn ({})'.format(pokemon_id)
    
def pokemonlist_html(botdata):
    output = "<table class='sortable'><tr><th>Pokedex #</th><th>pokemon</th><th>nickname</th><th>candy</th><th>cp</th><th>attack</th><th>def</th><th>stam</th><th>perfect</th><th>date caught</th></tr>"
    for p in botdata.getParty():
        pokemen.append(p)
    pokemen = sorted(pokemen, key=lambda k: k.cp, reverse=True)
    for p in pokemen:
        catchdate = time.strftime('%Y-%m-%d %H:%M',time.gmtime(p.creation_time_ms/1000))
        perfect = getPerfectForPokemon(None,p)
        candies = botdata.getCandiesFor(p.pokemon_id)
        output = output + "<tr><td>{id}</td><td>{pokename}</td><td>{nickname}</td><td>{candies}</td><td>{cp}</td><td>{attack}</td><td>{defense}</td><td>{stam}</td><td>{perfect:0.2f}%</td><td>{date}</tr>".format(nickname=p.nickname,date=catchdate,candies=candies,id=p.pokemon_id,pokename=pdata[p.pokemon_id]['Name'],cp=p.cp,attack=p.individual_attack,defense=p.individual_defense,stam=p.individual_stamina,perfect=perfect)
    output = output + "</table>"
    return output
        
def load_accounts():
    with open('accounts.json','r') as f:
        return json.load(f)

def get_account_data(accountname):
    for account in ACCOUNTS:
        if account['name'] == accountname:
            return account
    return None
    
account_data = load_accounts()
ACCOUNTS = account_data.get('accounts')
POKEHASH = account_data.get('pokehash')
pjson = None
with open('data/pokemon.json','r') as f:
    pjson = json.load(f)
PDATA = {}
for pdatum in pjson:
    PDATA[int(pdatum['Number'])] = pdatum
BETTERPDATA = {}
with open('data/GAME_MASTER_POKEMON_v0_2_reva.tsv') as f:
    reader = csv.reader(f,delimiter="\t")
    headerrow = reader.next()
    for row in reader:
        pokedata = {}
        for i, column in enumerate(headerrow):
            pokedata[column] = row[i]
        BETTERPDATA[int(pokedata['PkMn'])] = pokedata
from data.pokemongodata import POKEMONDATA
ITEMDATA = POKEMONDATA.get('responses').get('DOWNLOAD_ITEM_TEMPLATES').get('item_templates')
BESTPDATA = {p['pokemon_id']: p for p in [dict(template_id=k.get('template_id'),**k['pokemon_settings']) for k in ITEMDATA if 'pokemon_settings' in k.keys()]}
        
if __name__ == "__main__":
    app.run(port=9999,host="0.0.0.0")