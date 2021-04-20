#library("rjson")
#library("jsonlite")
library("ndjson")
library("tidyverse")

filename <- "test_results.json"
results_file <- file(filename)

input <- stream_in(filename)

input <- input %>% group_by(game_num) %>% mutate(
  win = chest == max(chest),
  tie = sum(win) > 1
)

players <- input %>% group_by(name) %>% 
  summarize(
    wins = sum(win),
    games = n(),
    win_percentage = wins/games,
    avg_gems = mean(chest),
    avg_deaths = mean(deaths),
    avg_relics = mean(relics),
    avg_gems_lost = mean(gems_lost)
  )
