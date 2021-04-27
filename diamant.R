#library("rjson")
#library("jsonlite")
#library("ndjson")
library(DBI)
library("tidyverse")
library("RSQLite")

db <- "C:/projects/diamant/tournaments/mp_test.db"
con <- dbConnect(SQLite(), db)

players_db <- tbl(con, "players")
games_players_db <- tbl(con, "games_players")

players <- players_db %>% collect()
games_players <- games_players_db %>% collect() %>% filter(game_id != 1) %>% arrange(game_id, player_id)



#input <- input %>% group_by(game_num) %>% mutate(
#  win = chest == max(chest),
#  tie = sum(win) > 1
#)

player_results <- games_players %>% group_by(player_id) %>% 
  summarize(
    wins = sum(win),
    losses = n()-wins,
    games = n(),
    win_percentage = wins/games,
    avg_gems = mean(chest),
    avg_deaths = mean(deaths),
    avg_relics = mean(relics),
    avg_gems_lost = mean(gems_lost)
  ) %>% inner_join(players, by=c("player_id"="id"))


# To make the result matrix, lets create a filter 
# for each player_id and whether they played in each game
# TODO: we should probably use games_players %>% distinct(player_id) instead
games_players_join_table <- games_players %>% select(game_id) %>% filter(FALSE)
for (player in players$id) {
  games_players_join_table <-
    full_join(
      games_players %>% 
        filter(player_id == player) %>% 
        select(game_id) %>% 
        mutate("{player}" := TRUE),
      games_players_join_table,
      by="game_id"
    )
}
games_players_filtered <- left_join(
  games_players,
  games_players_join_table,
  by="game_id"
)
rm(games_players_join_table)

# Now we can create the matrix
# For each pair of players, lets get the wins and losses
seen <- c()
matrix_long <- tibble()
for (player in players$id) {
  seen <- append(seen, player)
  cat(player)
  for (player2 in players %>% distinct(id) %>% pull()) {
    if (player != player2 && !(player2 %in% seen)) {
      player_res <- games_players_filtered %>% 
        filter(.data[[paste(player)]], 
               .data[[paste(player2)]], 
               player_id == player | player_id == player2) %>% 
        count(player_id, win) %>% 
        arrange(player_id) %>% 
        mutate(oponent_id = case_when(player < player2 ~ 
                                    c(player2, player2, player, player),  
                                   T ~ c(player, player, player2, player2)))
      matrix_long <- bind_rows(matrix_long, player_res)
    }
  }
}

# Now we have all pairs in a list
matrix_wider <- pivot_wider(matrix_long, names_from = "win", 
                            values_from = "n", names_prefix = "win_") %>% 
  rename(won = win_1, lost = win_0)
# Would be nive to know results for both sides, let's fix that
matrix_wider <- left_join(matrix_wider, matrix_wider %>% 
                            rename(o_id = player_id, 
                                   p_id = oponent_id, 
                                   won_against = won, 
                                   lost_against = lost), 
                          by=c(player_id="p_id", oponent_id="o_id"))

# Finally, we can do chisq test between each player
matrix_wider <- matrix_wider %>% mutate(
  better = case_when( 
    won/(won+lost) > won_against/(won_against+lost_against) ~ T, T~F
)) %>% 
  rowwise() %>% 
  mutate(
    p_val = chisq.test(matrix(c(won, won_against, lost, lost_against), ncol=2))$p.value,
    sig_better = better && p_val < 2.87e-7 # 5-sigma
  )

# We can look at the players which significantly (5-sigma) outperform others'
sig_test <- matrix_wider %>% count(player_id, sig_better) %>% filter(sig_better) %>% arrange(desc(n))

# We should be able to plot a contingency matrix