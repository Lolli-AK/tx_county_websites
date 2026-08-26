#!/usr/bin/env Rscript
# Figure 3 - county-by-fact tile matrix: does each Texas county STATE four
# operational election facts on its captured pages, and is the value right?
#
# Verdicts come from analysis/check_facts.py, which compares against the
# statewide authoritative values (TX SoS / Election Code), not county-vs-county.
# "Never states it" is a finding, not missing data, so it gets a real colour
# rather than the missing-data grey.
#
# 254 rows will not fit one column legibly, so counties are faceted into four
# columns, sorted by how many facts they state - the coverage gradient is the
# point of the figure.

suppressPackageStartupMessages({
  library(ggmedsl); library(ggplot2); library(dplyr); library(readr); library(tidyr)
})
medsl_fonts(dpi = 300)

root <- "."
stopifnot(dir.exists(file.path(root, "analysis", "output")))
outdir <- file.path(root, "analysis", "output", "figures")
dir.create(outdir, recursive = TRUE, showWarnings = FALSE)

facts <- read_csv(file.path(root, "analysis", "output", "tx_facts.csv"),
                  show_col_types = FALSE)
stopifnot(nrow(facts) == 254 * 4)

fact_lvl <- c("Polling hours", "Next election date",
              "Registration deadline", "Early voting window")
verdict_lvl <- c("Matches expected", "States something else",
                 "Shows only a past election", "Never states it")

pretty_county <- function(x) {
  x <- gsub("_", " ", x)
  gsub("\\b([a-z])", "\\U\\1", x, perl = TRUE)
}

# Sort counties by facts stated, then by facts matching, so the gradient runs
# cleanly from "states all four" at the top to "states none" at the bottom.
ord <- facts |>
  group_by(county) |>
  summarise(stated = sum(verdict %in% c("Matches expected", "States something else")),
            matched = sum(verdict == "Matches expected"), .groups = "drop") |>
  arrange(desc(stated), desc(matched), county)

n_col <- 4
ord <- ord |>
  mutate(rank = row_number(),
         col = ceiling(rank / ceiling(n() / n_col)),
         col_lab = paste0("Counties ", (col - 1) * ceiling(n() / n_col) + 1,
                          "-", pmin(col * ceiling(n() / n_col), n())))
# facet_wrap orders factor levels; a bare character column sorts "129-192"
# before "65-128" alphabetically, scrambling the coverage gradient.
ord$col_lab <- factor(ord$col_lab, levels = unique(ord$col_lab[order(ord$col)]))

dat <- facts |>
  left_join(ord, by = "county") |>
  mutate(fact_label = factor(fact_label, levels = fact_lvl),
         verdict = factor(verdict, levels = verdict_lvl),
         county_pretty = pretty_county(county))

# Within each facet, highest-coverage county at the top.
dat <- dat |>
  group_by(col) |>
  mutate(county_pretty = factor(county_pretty,
                                levels = rev(unique(county_pretty[order(rank)])))) |>
  ungroup()

pal <- c(
  "Matches expected"           = medsl_colors[["green"]],
  "States something else"      = "#FF8318",               # inspect, not "wrong"
  # Distinct from both: the county DID publish this fact, for an election that
  # has since passed. Staleness, not inaccuracy - 35 of the 36 cells previously
  # scored "states something else" for election date were past primaries.
  "Shows only a past election" = medsl_colors[["gold"]],
  "Never states it"            = medsl_colors[["navy"]]   # a finding, not absent
)
stopifnot(setequal(names(pal), verdict_lvl))

tot <- facts |> count(verdict)
gv <- function(v) { x <- tot$n[tot$verdict == v]; if (length(x)) x else 0L }
sub <- sprintf("254 counties x 4 facts; %d matching, %d another value, %d only a past election, %d never stated",
               gv("Matches expected"), gv("States something else"),
               gv("Shows only a past election"), gv("Never states it"))

p <- ggplot(dat, aes(x = fact_label, y = county_pretty, fill = verdict)) +
  geom_tile(colour = "white", linewidth = 0.35) +
  facet_wrap(~col_lab, nrow = 1, scales = "free_y") +
  scale_fill_manual(values = pal, name = "Verdict", drop = FALSE) +
  scale_x_discrete(position = "top",
                   labels = function(x) gsub(" ", "\n", x)) +
  labs(
    title    = "Statement of Four Operational Election Facts by Texas Counties",
    subtitle = sub,
    x = NULL, y = NULL,
    caption  = medsl_caption(
      source = "tx-county-watch snapshots, 2026-08-20; expected values from the TX Secretary of State")
  ) +
  guides(fill = guide_legend(title.position = "top", nrow = 1,
                             keywidth = unit(13, "pt"), keyheight = unit(13, "pt"))) +
  theme_medsl() +
  theme(legend.position = "bottom",
        panel.grid = element_blank(),
        axis.text.y = element_text(size = 4.4),
        axis.text.x = element_text(size = 6.6, angle = 0, hjust = 0.5),
        panel.spacing.x = unit(9, "pt"),
        strip.text = element_text(size = 8))

ggsave_medsl(file.path(outdir, "fig3_tx_facts_matrix.png"), plot = p,
             width = 12.5, height = 15)
cat("wrote fig3_tx_facts_matrix.png\n")
print(facts |> count(fact_label, verdict) |> pivot_wider(names_from = verdict, values_from = n, values_fill = 0))
