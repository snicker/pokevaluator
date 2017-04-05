import pickle
import os
import logging
from datetime import datetime
from data.leveldata import LEVELDATA

class BotData(object):
    def __init__(self, file):
        self.file = file
        self.data = self.load()
        self.startxp = 0
    
    def save(self):
        logging.debug("saving bot data")
        if 'uptime' not in self.data:
            self.data['uptime'] = {}
        self.data['uptime']['lastupdate'] = datetime.now()
        with open(self.file,'wb') as f:
            pickle.dump(self.data,f)
        return self.data
    
    def load(self):
        if os.path.isfile(self.file):
            with open(self.file,'r') as f:
                self.data = pickle.load(f)
        else:
            self.data = {'location': {
                    'lat': 39.738439, 
                    'long': -104.9266169,
                    'alt': 0
                    },
                    'stats': None,
                    'party': [],
                    'incubators': [],
                          'candies': {},
                    'uptime': {
                        'start': datetime.now(),
                        'lastupdate': datetime.now()
                    },
                    'startxp': 0,
                    'player_data': {}
                }
        return self.data
        
    def uptime(self):
        if 'uptime' not in self.data:
            return 0
        return (self.data['uptime']['lastupdate'] - self.data['uptime']['start']).total_seconds()
    
    def started(self):
        if 'uptime' not in self.data:
            self.data['uptime'] = {}
        self.data['uptime']['start'] = datetime.now()
        if self.data['stats'] is not None:
            self.data['startxp'] = self.data['stats'].experience
        return self.save()
    
    def xp_per_hour(self):
        if self.uptime() > 0:
            return float(self.xp_delta()) / (self.created() / 60 / 60)
        return 0
        
    def xp_delta(self):
        if self.data['stats'] is not None:
            return self.data['stats'].experience - self.data['startxp']
        return 0
    
    def updateParty(self,party):
        self.data['party'] = party
        return self.save()
     
    def updateCandies(self,candies):
        self.data['candies'] = candies
        return self.save()
    
    def updateIncubators(self,incubators):
        self.data['incubators'] = []
        for incubator in incubators:
            self.data['incubators'].append(incubator)
        return self.save()
    
    def updateStats(self,stats):
        self.data['stats'] = stats
        return self.save()
        
    def updatePlayerData(self, player_data):
        self.data['player_data'] = player_data
        return self.save()
        
    def getPlayerData(self):
        return self.data.get('player_data',{})

    def getParty(self):
        return self.data['party']
    
    def getStats(self):
        return self.data['stats']
    
    def getIncubators(self):
        return self.data['incubators']
     
    def getCandiesFor(self,pokemon_id):
        if 'candies' in self.data and self.data['candies'] is not None and pokemon_id in self.data['candies']:
            return self.data['candies'][pokemon_id]
        return 0
        
    def created(self):
        creation = self.getPlayerData().get('creation_timestamp_ms',0) / 1000
        return (datetime.now() - datetime.fromtimestamp(creation)).total_seconds()
        
    def elapsedTimeString(self, seconds, granularity = 4):
        result = []
        intervals = (
        ('w', 604800),  # 60 * 60 * 24 * 7
        ('d', 86400),    # 60 * 60 * 24
        ('h', 3600),    # 60 * 60
        ('m', 60),
        ('s', 1),
        )
        for name, count in intervals:
            value = seconds // count
            if value:
                seconds -= value * count
                if value == 1:
                    name = name.rstrip('s')
                result.append("{}{}".format(int(value), name))
        return ''.join(result[:granularity])
    
    def uptimeString(self, granularity=4):
        return self.elapsedTimeString(self.uptime())
    
    def createdString(self, granularity=4):
        return self.elapsedTimeString(self.created())
    
    def botSummary(self):
        stats = self.getStats()
        party = self.getParty()
        if stats is None:
            return "No stats"
        level = stats.get('level')
        if level is None:
            return "No stats"
        ld = LEVELDATA[int(stats.get('level'))]
        xp = stats.experience
        nextlvlxp = stats.next_level_xp
        prevlvlxp = stats.prev_level_xp
        xptnl = int(nextlvlxp) - int(xp)
        xpthislevel = int(ld['xptnl'])
        tnlpct = (1-(float(xptnl)/xpthislevel))*100
        return "Level {level}, {xp}xp, {xptnl}xp tnl ({tnlpct:3.2f}%), {km:3.2f}km walked, {pokemon} pokemon in party. xp/hr: {xphr:0.0f} created:{created} ago".format(created=self.createdString(),xphr=self.xp_per_hour(),level=stats.level,xp=xp,xptnl=xptnl,tnlpct=tnlpct,km=stats.km_walked,pokemon=len(party))
    
    def getCoordinatesString(self):
        return "{lat}, {long}".format(lat=self.data['location']['lat'],long=self.data['location']['long'])
    
    def setCoordinates(self,lat,long):
        self.data['location']['lat'] = lat
        self.data['location']['long'] = long
        return self.save()