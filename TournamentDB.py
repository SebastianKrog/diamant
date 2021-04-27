import sqlite3


class TournamentDB:
    def __init__(self, db):
        self.conn = sqlite3.connect(db)
        self.init_tables()

    def init_tables(self):
        cur = self.conn.cursor()
        cur.execute("""create table if not exists players(
        id integer primary key,
        name text unique
        )""")
        cur.execute("""create table if not exists games_players(
        id integer primary key,
        game_id integer,
        player_id integer,
        win integer,    
        chest integer,
        deaths integer,
        gems_lost integer,
        relics integer,
        unique(game_id, player_id)
        )""")
        self.conn.commit()

    def write_players(self, player_names):
        cur = self.conn.cursor()
        cur.executemany("""insert or ignore into players (name) values (?)""", [(name,) for name in player_names])
        self.conn.commit()

    def get_players(self):
        cur = self.conn.cursor()
        return cur.execute("select * from players").fetchall()

    def get_player_ids_from_names(self, player_names):
        ids, db_names = zip(*self.get_players())
        return [ids[db_names.index(name)] for name in player_names]

    def write_game(self, players):
        if len(players) < 1:
            return True

        if type(players[0]) is not dict:
            return False

        cur = self.conn.cursor()
        create_game_id = False
        game_id = 0
        if "game_id" not in players[0]:
            create_game_id = True
            game_id = cur.execute("select max(game_id) from games_players").fetchone()[0] or 0

        ids, db_names = zip(*self.get_players())
        for player in players:
            player["player_id"] = ids[db_names.index(player["name"])]
            if create_game_id:
                player["game_id"] = game_id + 1

        cur.executemany("""insert into games_players (game_id, player_id, win, chest, deaths, gems_lost, relics) 
            values (:game_id, :player_id, :win, :chest, :deaths, :gems_lost, :relics)""", players)
        self.conn.commit()

        return True

    def write_games(self, games):
        if len(games) < 1:
            return True

        if type(games[0]) is not list:
            return False

        if type(games[0][0]) is not dict:
            return False

        cur = self.conn.cursor()
        create_game_id = False
        game_id = 0
        if "game_id" not in games[0][0]:
            create_game_id = True
            game_id = cur.execute("select max(game_id) from games_players").fetchone()[0] or 0

        ids, db_names = zip(*self.get_players())
        players = []
        for game in games:
            game_id += 1
            for player in game:
                player["player_id"] = ids[db_names.index(player["name"])]
                if create_game_id:
                    player["game_id"] = game_id
                players.append(player)

        cur.executemany("""insert into games_players (game_id, player_id, win, chest, deaths, gems_lost, relics) 
                    values (:game_id, :player_id, :win, :chest, :deaths, :gems_lost, :relics)""", players)
        self.conn.commit()

        return True
