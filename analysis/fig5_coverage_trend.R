#!/usr/bin/env Rscript
# Figure 5 - why so few counties state all four facts: they have not switched to
# the November election yet.
#
# Left panel:  counties whose captured pages reference the Nov 3 general at all.
# Right panel: counties stating each of the four facts.
#
# The right panel is the test that matters. POLLING HOURS is statutory - 7am-7pm
# for every Texas election - so it should NOT move as November approaches. The
# other three are election-specific and should. That is exactly the observed
# split, which is why "electoral lull" beats "these counties are just bad at
# documentation" as an explanation.

suppressPackageStartupMessages({
  library(ggmedsl); library(ggplot2); library(dplyr); library(readr); library(tidyr)
})
medsl_fonts(dpi = 300)

root <- "."
outdir <- file.path(root, "analysis", "output", "figures")
stopifnot(dir.exists(outdir))

trend <- read_csv(file.path(root, "analysis", "output", "tx_coverage_over_time.csv"),
                  show_col_types = FALSE)
nov3 <- read_csv(file.path(root, "analysis", "output", "tx_nov3_mentions.csv"),
                 show_col_types = FALSE)

fact_lab <- c(stated_election_date        = "Next election date",
              stated_early_voting_window  = "Early voting window",
              stated_registration_deadline = "Registration deadline",
              stated_polling_hours        = "Polling hours (statutory)")

long <- trend |>
  select(run_date, starts_with("stated_")) |>
  select(-any_of("stated_total")) |>
  pivot_longer(-run_date, names_to = "fact", values_to = "counties") |>
  mutate(series = unname(fact_lab[fact]),
         panel = "Counties stating each fact") |>
  filter(!is.na(series))

novp <- nov3 |>
  transmute(run_date, counties = counties_mentioning_nov3,
            series = "References the Nov 3 general",
            panel = "Counties referencing November 3")

dat <- bind_rows(novp, long) |>
  mutate(panel = factor(panel, levels = c("Counties referencing November 3",
                                          "Counties stating each fact")),
         series = factor(series, levels = c("References the Nov 3 general",
                                            "Next election date",
                                            "Registration deadline",
                                            "Early voting window",
                                            "Polling hours (statutory)")))

pal <- c("References the Nov 3 general" = medsl_colors[["navy"]],
         "Next election date"           = medsl_colors[["blue"]],
         "Registration deadline"        = medsl_colors[["green"]],
         "Early voting window"          = "#FF8318",
         # Muted on purpose: this is the control series, flat by construction.
         "Polling hours (statutory)"    = medsl_colors[["gold"]])

p <- ggplot(dat, aes(x = as.Date(run_date), y = counties,
                     colour = series, group = series)) +
  geom_line(linewidth = 0.85) +
  geom_point(size = 1.4) +
  facet_wrap(~panel, nrow = 1, scales = "free_y") +
  scale_colour_manual(values = pal, name = NULL) +
  scale_x_date(date_labels = "%b %d", date_breaks = "7 days") +
  labs(
    title    = "Counties Referencing the November Election and Stating Election Facts Over Time",
    subtitle = paste0("254 Texas counties, daily snapshots 2026-07-29 through 2026-08-20; ",
                      "general election is November 3. A stale page showing a past election does not count as stating a fact."),
    x = NULL, y = "Counties (of 254)",
    caption  = medsl_caption(source = "tx-county-watch snapshots, 2026-07-29 to 2026-08-20"),
    tag = paste0("Both panels are zoomed to their data range, not to 0-254. ",
                 "Polling hours are statutory and identical for every election, so that series is a control.")
  ) +
  guides(colour = guide_legend(nrow = 2, byrow = TRUE)) +
  theme_medsl() +
  theme(legend.position = "bottom",
        panel.spacing.x = unit(22, "pt"),
        plot.tag.position = c(0.99, 0.028),
        plot.tag = element_text(size = 7, colour = "#666666", hjust = 1, vjust = 0))

ggsave_medsl(file.path(outdir, "fig5_tx_coverage_trend.png"), plot = p,
             width = 11.5, height = 6)
cat("wrote fig5_tx_coverage_trend.png\n")
