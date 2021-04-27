# Diamant / Incan Gold
import numpy
import random
import re
# import sqlite3
import json
from os import path
from TournamentDB import TournamentDB
from multiprocessing import Pool


def multiprocess_tournament(name, player_names, player_n, directory, game_ids):
    players = [gen_player_from_name(name) for name in player_names]
    t = Tournament(name=name, player_pool=players, player_n=player_n, directory=directory)
    t.hold_tournament(n=game_ids, supply_game_id=True)
    return True


class Tournament:
    def __init__(self, name, player_pool=None, player_n=8, directory="tournaments/"):
        self.player_pool = player_pool or []

        self.results = []
        self.players_games_played = [0]*len(player_pool)
        self.players_games_won = [0]*len(player_pool)
        self.players_n = player_n
        self.games_played = 0
        self.name = name
        self.retired_players = []

        self.db = TournamentDB(directory+self.name+".db")
        players, player_names = zip(*self.player_pool)
        self.db.write_players(player_names)

    # def add_players(self, players):
    #     if type(players) == list:
    #         self.player_pool += players
    #         self.players_games_played += [0]*len(players)
    #         self.players_games_won += [0] * len(players)
    #     else:
    #         self.player_pool.append(players)
    #         self.players_games_played.append(0)
    #         self.players_games_won.append(0)

    # def retire_players(self, player_names):
    #     players, old_player_names = zip(*self.player_pool)
    #     if type(player_names) is not list:
    #         player_names = [player_names]
    #     for player in player_names:
    #         self.retired_players.append(player)
    #         index = old_player_names.index(player)
    #         self.player_pool.pop(index)
    #         self.players_games_played.pop(index)
    #         self.players_games_won.pop(index)

    def db_save_game(self, result):
        self.db.write_game(result['players'])

    def db_save_games(self, games):
        self.db.write_games(games)

    def save(self):
        players, player_names = zip(*self.player_pool)
        with open(self.directory + self.name + '.json', 'w') as outfile:
            json.dump({"players_n": self.players_n,
                       "player_names": player_names,
                       "players_games_played": self.players_games_played,
                       "games_played": self.games_played,
                       "retired_players": self.retired_players}, outfile)
        # with open(self.name + '_results.json', 'a+') as outfile:
        #     for game in self.results:
        #         json.dump(game, outfile)
        #         outfile.write("\n")
        with open(self.directory + self.name + '_results.json', 'a+') as outfile:
            count_from = self.games_played - len(self.results)
            for n, result in enumerate(self.results):
                for p in result['players']:
                    p['game_num'] = count_from + n
                    json.dump(p, outfile)
                    outfile.write("\n")
        self.results = []

    def load(self):
        if path.exists(self.name + '.json'):
            with open(self.name + '.json') as json_file:
                data = json.load(json_file)
                for d in data:
                    self.players_n = d['players_n']
                    self.players_games_played = d['players_games_played']
                    player_names = d['player_names']
                    self.player_pool = [gen_player_from_name(name) for name in player_names]

    def play_game(self, game_id=None, save_db=True):
        # Find a player with fewest plays:
        player_0 = self.player_pool[self.players_games_played.index(min(self.players_games_played))]

        # Make a list of random players, make sure player_0 is in the list
        players = random.sample(self.player_pool, self.players_n)
        if player_0 not in players:
            players.pop()
            players.append(player_0)

        # Add plays to the list of games played
        for player in players:
            self.players_games_played[self.player_pool.index(player)] += 1

        result = Diamant(players, game_id=game_id).play_game()
        #self.results.append(result)

        if save_db:
            self.db_save_game(result)

        winners = result["winner"]
        if type(winners) is not list:
            winners = [winners]
        players, player_names = zip(*self.player_pool)
        for winner in winners:
            winner_index = player_names.index(winner)
            self.players_games_won[winner_index] += 1
        self.games_played += 1

        return result

    def hold_tournament(self, n=1000, save_db=True, offload_interval=10000, supply_game_id=False):
        games = []

        if type(n) is int:
            n = range(n)

        game_id = None

        for i in n:
            if supply_game_id:
                game_id = i
            result = self.play_game(game_id=game_id, save_db=False)
            games.append(result["players"])
            if save_db and ((i % offload_interval) == 0):
                self.db_save_games(games)
                games = []
        if save_db:
            self.db_save_games(games)

    def calc_winrates(self):
        for game in self.results:
            winner = game.winner
            if not isinstance(winner, list):
                winner = [winner]
            players = [p.name for p in game.players]


class Diamant:
    cards = "123455779bbdefhUUUVVVXXXYYYZZZ"
    relics = ".,:;!"  # 5 7 8 10 12
    relic_values = [5, 7, 8, 10, 12]

    def __init__(self, players, game_id=None):
        players, names = zip(*players)

        self.game_id = game_id

        self.rnd = 0
        self.trn = 0
        self.deck = self.cards
        self.players_n = len(players)
        self.players = players
        self.players_chest = [0]*self.players_n
        self.removed_traps = []
        self.verbose = False

        # Board variables (cleared each round)
        self.players_name = names
        self.players_escaped = []
        self.players_dead = []
        self.players_pocket = []
        self.players_gems_lost = []
        self.players_relics_collected = []
        self.players_escape_turn = []
        self.unclaimed_relics = []
        self.gems_on_board = []

        # Strategy variables TODO: this
        self.gems_seen = 0
        self.gem_tiles_seen = 0
        self.traps_seen = 0
        self.pred_risk = []  # List of predicted risk for drawing a killing tile
        self.continue_risk = 0  # Will be set to the current risk for the turn TODO: make into function?

        self.round_results = []
        self.results = []

    def reset_round(self):
        self.trn = 0
        self.deck = ''.join([self.deck, self.relics[self.rnd]])
        self.players_escaped = [False]*self.players_n
        self.players_dead = [False]*self.players_n
        self.players_pocket = [0]*self.players_n
        self.players_gems_lost = [0]*self.players_n
        self.players_relics_collected = [0]*self.players_n
        self.players_escape_turn = [None]*self.players_n
        self.unclaimed_relics = []
        self.gems_on_board = []
        self.shuffle()

        # Reset strategy vars
        self.gems_seen = 0
        self.gem_tiles_seen = 0
        self.traps_seen = 0
        self.pred_risk = []
        self.continue_risk = 0

    def shuffle(self):
        str_var = list(self.deck)
        numpy.random.shuffle(str_var)
        self.deck = ''.join(str_var)

    def calc_strat_vars(self):
        if not self.pred_risk:
            cards_n = len(self.deck)
            boom_n = 0
            traps_seen = set()
            for i, card in enumerate(self.deck):
                if card.isupper():
                    if card in traps_seen:
                        break
                    traps_seen.add(card)
                    boom_n += 2 - self.removed_traps.count(card)
                pred = boom_n / (cards_n - i)
                self.pred_risk.append(pred)
        self.continue_risk = self.pred_risk[self.trn]

    def play_turn(self):
        if self.verbose:
            print("Turn %d" % self.trn, end="")
            remaining_players = self.players_n - numpy.sum(self.players_escaped)
            if remaining_players < self.players_n:
                print(" (%d players remain):" % remaining_players)
            else:
                print(":")

        # Evaluate the next card
        turn_card = self.deck[self.trn]
        if self.verbose:
            print(" Card %s " % turn_card, end="")
        if turn_card.isupper():  # Trap!
            self.traps_seen += 1
            if self.verbose:
                print("(trap)")
            if turn_card in self.deck[0:self.trn]:
                # Those who continued lose their pockets and die!
                if self.verbose:
                    print(" Lethal!", end="")
                    verbose_players_died = []
                    verbose_gems_lost = []
                for n in range(len(self.players)):
                    if not self.players_escaped[n]:
                        self.players_gems_lost[n] = self.players_pocket[n]
                        self.players_pocket[n] = 0
                        self.players_dead[n] = True
                        if self.verbose:
                            verbose_players_died.append(self.players_name[n])
                            verbose_gems_lost.append(str(self.players_gems_lost[n]))
                if self.verbose:
                    if len(verbose_players_died) > 1:
                        verbose_players_died = ' and '.join([', '.join(verbose_players_died[0:-1]), verbose_players_died[-1]])
                        verbose_gems_lost = ' and '.join([', '.join(verbose_gems_lost[0:-1]), verbose_gems_lost[-1]])
                        end = "gems respectively."
                    else:
                        verbose_players_died = verbose_players_died[0]
                        verbose_gems_lost = verbose_gems_lost[0]
                        end = "gems."
                    print(" %s died losing %s %s" % (verbose_players_died, verbose_gems_lost, end))
                return False

        elif turn_card in self.relics:
            self.unclaimed_relics.append(turn_card)
            if self.verbose:
                print("(relic, value %d)" % self.relic_values[self.relics.index(turn_card)])

        else:  # Gems!
            if turn_card.islower():
                value = ord(turn_card) - 87
            else:
                value = int(turn_card)
            if self.verbose:
                print("(value %d)" % value)
            self.gems_seen += value
            self.gem_tiles_seen += 1
            split_n = len(self.players) - numpy.count_nonzero(self.players_escaped)
            quotient, remainder = divmod(value, split_n)
            if quotient > 0:
                if self.verbose:
                    print(" %d gems are given to each player." % quotient)
                for n in range(self.players_n):
                    if not self.players_escaped[n]:
                        self.players_pocket[n] += quotient

            if remainder > 0:
                self.gems_on_board.append(remainder)
            if self.verbose:
                print(" %d gems are placed on the board." % remainder)

        # Calculate strategy vars
        self.calc_strat_vars()

        # Evaluate players
        continues = []
        for n, p in enumerate(self.players):
            if self.players_escaped[n] or self.players_dead[n]:
                continues.append(None)
            else:
                continues.append(p(self))

        # For players that escaped, split the gems on the board
        split_n = self.players_n - numpy.count_nonzero(continues) - numpy.count_nonzero(self.players_escaped)
        if split_n > 0:
            quotient, remainder = numpy.divmod(self.gems_on_board, split_n)
            self.gems_on_board = remainder[remainder != 0].tolist()
            quotient_sum = int(numpy.sum(quotient))

            relics_collected = 0
            if split_n == 1:
                for relic in self.unclaimed_relics:
                    relics_collected = relics_collected + 1
                    quotient_sum += self.relic_values[self.relics.index(relic)]
                self.unclaimed_relics = []

            if self.verbose:
                verbose_players_escaped = []
                verbose_gems = []
            self.players_escaped = numpy.logical_not(continues)
            for n, cont in enumerate(continues):
                if not cont and cont is not None:
                    self.players_escape_turn[n] = self.trn
                    if quotient_sum > 0:
                        self.players_pocket[n] += quotient_sum
                    if relics_collected > 0:
                        self.players_relics_collected[n] += relics_collected
                    if self.verbose:
                        verbose_players_escaped.append(self.players_name[n])
                        verbose_gems.append(str(self.players_pocket[n]))

            if self.verbose:
                if len(verbose_players_escaped) > 1:
                    verbose_players_escaped = ' and '.join(
                        [', '.join(verbose_players_escaped[0:-1]), verbose_players_escaped[-1]])
                    verbose_gems = ' and '.join(
                        [', '.join(verbose_gems[0:-1]), verbose_gems[-1]])
                    end = "gems respectively."
                else:
                    verbose_players_escaped = verbose_players_escaped[0]
                    verbose_gems = verbose_gems[0]
                    end = "gems."
                print(" %s escaped securing %s %s" % (verbose_players_escaped, verbose_gems, end))
            if numpy.count_nonzero(self.players_escaped) == len(self.players):
                return False

        self.trn += 1
        return True

    def play_round(self):
        # Add the relic and shuffle the deck, reset the board
        self.reset_round()

        # Play
        while self.play_turn():
            pass

        # Put gems in chest
        self.players_chest = numpy.add(self.players_chest, self.players_pocket).tolist()

        # Collect the scores
        players = {
            "name": self.players_name,
            "gems_gained": self.players_pocket,
            "dead": self.players_dead,
            "escape_turn": self.players_escape_turn,
            "gems_lost": self.players_gems_lost,
            "chest": self.players_chest,
            "relics": self.players_relics_collected
        }

        deck_played = self.deck[0:self.trn+1]
        self.round_results.append({
            "round": self.rnd,
            "deck": deck_played,
            "turns_played": self.trn+1,
            "players": players
        })

        # Reset the game
        # We remove any relics met
        for relic in self.relics[0:self.rnd+1]:
            if relic in deck_played:
                self.deck = self.deck.replace(relic, '', 1)
        # We remove any traps that caused players' untimely devise
        if any(self.players_dead):
            self.removed_traps.append(deck_played[-1])
            self.deck = self.deck.replace(deck_played[-1], '', 1)

        self.rnd = self.rnd + 1
        if self.rnd < 5:
            return True
        else:
            return False

    def play_game(self):
        while self.play_round():
            pass

        # Final results:
        deaths, gems_lost, relics = [], [], []
        for rnd in self.round_results:
            deaths.append(rnd["players"]["dead"])
            gems_lost.append(rnd["players"]["gems_lost"])
            relics.append(rnd["players"]["relics"])
            rnd["players"] = [dict(zip(rnd["players"], col)) for col in zip(*rnd["players"].values())]

        deaths = numpy.add.reduce(deaths).tolist()
        escapes = numpy.subtract(5, deaths).tolist()
        gems_lost = numpy.add.reduce(gems_lost).tolist()
        relics = numpy.add.reduce(relics).tolist()

        winner_amount = max(self.players_chest)

        players = {
            "name": self.players_name,
            "chest": self.players_chest,
            "win": [n == winner_amount for n in self.players_chest],
            "deaths": deaths,
            "escapes": escapes,
            "gems_lost": gems_lost,
            "relics": relics
        }

        if self.game_id:
            players["game_id"] = [self.game_id]*self.players_n

        tie = self.players_chest.count(winner_amount) > 1
        if tie:
            tie_pos = [i for i, j in enumerate(self.players_chest) if j == winner_amount]
            winner = [self.players_name[i] for i in tie_pos]
        else:
            winner = self.players_name[self.players_chest.index(winner_amount)]

        self.results = {
            "winner": winner,
            "tie": tie,
            "winner_gems": int(winner_amount),
            "players": [dict(zip(players, col)) for col in zip(*players.values())],
            "rounds": self.round_results
        }

        return self.results

    def print_game(self):
        print("Game of Diamant\n")
        print("Players: %s\n" % ' '.join([p['name'] for p in self.results.players]))
        for n, rnd in enumerate(self.results.rounds):
            print("Round %d\n-------\n" % (n + 1))
            escapes = [p['escape_turn'] for p in rnd.players]
            for t, card in enumerate(rnd.deck):
                print("Turn %d: " % (t + 1))
                print("Card: %s " % card)
                if not card.isupper() and card.isalnum():
                    if card.islower():
                        value = ord(card) - 87
                    else:
                        value = int(card)
                    print("")
                if rnd.turns_played == t:
                    pass

    @classmethod
    def print_result(cls, result):
        diamant = cls([])
        diamant.results = result
        diamant.print_game()


def random_gen(p=0.2):
    p = round(max(min(p, 1), 0), 2)

    def random(game_state):
        if numpy.random.rand() < p:
            return False
        return True
    return random, "random_%.2f" % p


def gems_gen(n=6):
    n = int(n)

    def gems(game_state):
        if game_state.gems_seen >= n:
            return False
        return True
    return gems, "gems_%d" % n


def tiles_gen(n=3):
    n = int(n)

    def tiles(game_state):
        if game_state.gem_tiles_seen >= n:
            return False
        return True
    return tiles, "tiles_%d" % n


def traps_gen(n=2):
    n = int(n)

    def traps(game_state):
        if game_state.traps_seen >= n:
            return False
        return True
    return traps, "traps_%d" % n


def relic_gen(p=1, fallback=random_gen, *args):
    p = round(max(min(p, 1), 0), 2)

    if callable(fallback):
        fallback = fallback(*args)
    elif type(fallback) == str:
        fallback = gen_player_from_name(fallback)
    fallback_func, fallback_name = fallback

    def relic(game_state):
        if game_state.unclaimed_relics:
            if numpy.random.rand() < p:
                return False
        return fallback_func(game_state)

    return relic, "relic_%.2f_%s" % (p, fallback_name)


def gen_player_from_name(player_name):
    dict_name_to_gen = {
        r"^relic_(\d\.\d\d)_(.+)": relic_gen,
        r"^traps_(\d+)": traps_gen,
        r"^tiles_(\d+)": tiles_gen,
        r"^gems_(\d+)": gems_gen,
        r"^random_(\d\.\d\d)": random_gen
    }

    for regex in dict_name_to_gen:
        match = re.match(regex, player_name)
        if match:
            return dict_name_to_gen[regex](*match.groups())
    raise ValueError('Player could not be generated from name')


def async_test(i):
    print(i)


if __name__ == '__main__':
    #diamant = Diamant([relic_gen(p) for p in numpy.linspace(0.2, 1, num=8)])

    with Pool(6) as pool:
        pf, player_ns = zip(*[gems_gen(i) for i in numpy.linspace(1, 60, num=60)])
        games_per_pool = 100000

        #multiple_results = [pool.apply_async(multiprocess_tournament, ("mp_test", player_names, 8, "tournaments/", range(games_per_pool*i, games_per_pool*(i+1)))) for i in range(4)]
        multiple_res = []
        for i in range(12):
            res = pool.apply_async(multiprocess_tournament, ("mp_test", player_ns, 8, "tournaments/", range(games_per_pool*i, games_per_pool*(i+1))))
            multiple_res.append(res)

        pool.close()
        pool.join()
        print([res.get() for res in multiple_res])

# Plan:
# Create a tournament structure where algorithms battle:
# 20 permanent base algorithms among the best or most prominent std. ones
# 20 best performing among candidates
# 10 clones of previous best performing
# 10 newly created algorithms
# Each iteration, clones that do better than their originals (significantly so) replace their counterparts
# New algorithms get a spot in the best performing if they outperform these
# The overall n best algorithm gets a permanent spot in the next level tournament
# Tournaments are held until 30 best algorithms are collected
# Then an a new tournaments are held where these 30 algorithms battle their clones
# If the clones outperform, they replace their original
# This continues until parameters have been optimized

