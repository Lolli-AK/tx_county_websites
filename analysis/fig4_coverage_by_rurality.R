#!/usr/bin/env Rscript
# Figure 4 - does election-fact coverage track county rurality?
#
# THE ANSWER IS NO, AND THE FIGURE HAS TO SHOW WHY. Raw "facts stated" is weakly
# related to population (Spearman +0.157), but that relationship is entirely a
# capture artifact: rural counties publish fewer distinct election pages, so
# there is less surface on which to state anything. Pages captured vs rurality
# is rho = -0.410; controlling for it, the rurality coefficient is p = 0.44 and
# the residual correlation is +0.012.
#
# So the figure is deliberately TWO panels: the mechanism (pages captured, a
# strong gradient) and the outcome once you divide it out (facts per captured
# page, flat and slightly reversed). A single-panel "coverage by rurality" chart
# would imply a finding the data does not support.

suppressPackageStartupMessages({
  library(ggmedsl); library(ggplot2); library(dplyr); library(readr); library(tidyr)
})
medsl_fonts(dpi = 300)

root <- "."
stopifnot(dir.exists(file.path(root, "analysis", "output")))
outdir <- file.path(root, "analysis", "output", "figures")

f <- read_csv(file.path(root, "analysis", "output", "tx_facts.csv"), show_col_types = FALSE)
r <- read_csv(file.path(root, "analysis", "output", "tx_platform_rucc.csv"),
              col_types = cols(fips = col_character(), .default = col_guess()))

# DENOMINATOR = DISTINCT URLs, not page-type slots. 34 counties register one
# URL under two page types (usually polling and early_voting both pointing at a
# single "Current Elections" page), so counting slots double-counts them: 756
# slots but only 722 distinct pages. Using slots deflated those counties' rate.
# NB: nzchar(NA) is TRUE by default, so `nzchar(trimws(url))` KEEPS gap rows -
# readr parses the empty url cells as NA. Test for NA explicitly.
urls <- read_csv(file.path(root, "manifest", "targets.csv"), show_col_types = FALSE) |>
  filter(!is.na(url), trimws(url) != "") |>
  mutate(county = tolower(gsub(" ", "_", county))) |>
  group_by(county) |>
  summarise(pages = n_distinct(url), .groups = "drop")

cov <- f |>
  group_by(county) |>
  summarise(stated = sum(verdict %in% c("Matches expected", "States something else")), .groups = "drop") |>
  left_join(urls, by = "county") |>
  left_join(r |> select(county, rucc, rucc_band, pop2020), by = "county") |>
  mutate(per_page = stated / pages)
stopifnot(!any(is.na(cov$pages)), sum(cov$pages) == 722)
stopifnot(nrow(cov) == 254, !any(is.na(cov$rucc_band)))

band_order <- c("Large metro (1M+)", "Medium metro (250k-1M)", "Small metro (<250k)",
                "Nonmetro, has an urban core", "Nonmetro, rural")
band_n <- cov |> count(rucc_band)
cov <- cov |>
  left_join(band_n, by = "rucc_band") |>
  mutate(band_lab = sprintf("%s\n(n = %d)", rucc_band, n),
         band_lab = factor(band_lab,
                           levels = rev(sprintf("%s\n(n = %d)", band_order,
                                                band_n$n[match(band_order, band_n$rucc_band)]))))

long <- cov |>
  select(county, band_lab, pages, per_page) |>
  pivot_longer(c(pages, per_page), names_to = "metric", values_to = "value") |>
  mutate(metric = factor(metric, levels = c("pages", "per_page"),
                         labels = c("Distinct election pages captured (of 5)",
                                    "Facts stated per distinct page")))

means <- long |> group_by(band_lab, metric) |>
  summarise(m = mean(value), .groups = "drop")

set.seed(4)
p <- ggplot(long, aes(x = value, y = band_lab)) +
  geom_jitter(height = 0.22, width = 0.04, colour = "#C4C4C4",
              size = 0.85, alpha = 0.75) +
  geom_point(data = means, aes(x = m), colour = medsl_colors[["blue"]],
             size = 3.1) +
  facet_wrap(~metric, nrow = 1, scales = "free_x") +
  scale_x_continuous(expand = expansion(mult = c(0.04, 0.06))) +
  labs(
    title    = "Election Pages Captured and Fact Coverage by County Rurality",
    subtitle = "254 Texas counties; grey points are counties, blue points are band means",
    x = NULL, y = NULL,
    caption  = medsl_caption(
      source = "tx-county-watch snapshots, 2026-08-20; USDA ERS RUCC 2023"),
    tag = paste0("Facts stated vs rurality: Spearman rho = -0.07 (p = 0.26). ",
                 "Controlling for pages captured, p = 0.44.")
  ) +
  theme_medsl() +
  theme(panel.grid.major.y = element_blank(),
        strip.text = element_text(size = 9.5),
        # Without this the two panels' axes abut and "5 | 0.0" reads as one scale.
        panel.spacing.x = unit(26, "pt"),
        plot.tag.position = c(0.99, 0.028),
        plot.tag = element_text(size = 7, colour = "#666666", hjust = 1, vjust = 0))

ggsave_medsl(file.path(outdir, "fig4_tx_coverage_by_rurality.png"), plot = p,
             width = 11, height = 5.6)
cat("wrote fig4_tx_coverage_by_rurality.png\n")
print(cov |> group_by(rucc_band) |>
        summarise(n = n(), mean_pages = round(mean(pages), 2),
                  mean_stated = round(mean(stated), 2),
                  per_page = round(mean(per_page), 3)) |>
        arrange(match(rucc_band, band_order)) |> as.data.frame())
