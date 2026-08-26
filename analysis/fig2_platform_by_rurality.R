#!/usr/bin/env Rscript
# Figure 2 - website platform by county rurality, all 254 Texas counties.
#
# COUNTS, not percentages: the bands are very unequal (17 small-metro counties
# vs 92 rural), and a 100% stacked bar would make n=1 look identical to a
# unanimous n=22.
#
# RUCC bands are the same five used by the Florida version of this chart, so the
# two are directly comparable. See analysis/join_rucc.py.

suppressPackageStartupMessages({
  library(ggmedsl); library(ggplot2); library(dplyr); library(readr); library(forcats)
})
medsl_fonts(dpi = 300)

root <- "."
stopifnot(dir.exists(file.path(root, "analysis", "output")))
outdir <- file.path(root, "analysis", "output", "figures")
dir.create(outdir, recursive = TRUE, showWarnings = FALSE)

dat <- read_csv(file.path(root, "analysis", "output", "tx_platform_rucc.csv"),
                col_types = cols(fips = col_character(), .default = col_guess()))
stopifnot(nrow(dat) == 254)

small <- dat |> count(platform) |> filter(n < 5, platform != "Other / unknown") |> pull(platform)
dat <- dat |>
  mutate(plat = case_when(
    platform == "Other / unknown" ~ "Unidentifiable from snapshot",
    platform %in% small           ~ "Other identified platform",
    TRUE                          ~ platform))

lvl <- c("ezTask Titanium (TAC)", "CivicPlus", "WordPress", "Revize",
         "Granicus / Vision", "Other identified platform",
         "Unidentifiable from snapshot")
# Every level in `lvl` MUST have an entry here. scale_fill_manual renders a
# level with no matching value as unlabelled grey, which silently turned the
# 167 ezTask counties - the largest category - into anonymous dark bars.
pal <- c("ezTask Titanium (TAC)"        = medsl_colors[["purple"]],
         "CivicPlus"                    = medsl_colors[["gold"]],
         "WordPress"                    = medsl_colors[["green"]],
         "Revize"                       = "#FF8318",
         "Granicus / Vision"            = medsl_colors[["sky"]],
         "Other identified platform"    = medsl_colors[["olive"]],
         "Unidentifiable from snapshot" = "#C4C4C4")
stopifnot(setequal(names(pal), lvl))   # fail loudly rather than render grey

band_order <- c("Large metro (1M+)", "Medium metro (250k-1M)", "Small metro (<250k)",
                "Nonmetro, has an urban core", "Nonmetro, rural")

plotdat <- dat |>
  count(rucc_band, plat) |>
  group_by(rucc_band) |>
  mutate(band_n = sum(n)) |>
  ungroup() |>
  # The county count goes IN the axis label - without it a reader cannot tell a
  # 17-county band from a 92-county one at a glance.
  mutate(band_lab = sprintf("%s\n(n = %d)", rucc_band, band_n),
         plat = factor(plat, levels = lvl))

lab_order <- plotdat |>
  distinct(rucc_band, band_lab) |>
  arrange(match(rucc_band, band_order)) |>
  pull(band_lab)
# rev() so the largest-metro band sits at the TOP of a horizontal chart.
plotdat$band_lab <- factor(plotdat$band_lab, levels = rev(lab_order))

p <- ggplot(plotdat, aes(x = n, y = band_lab, fill = plat)) +
  # reverse = TRUE makes segments follow legend order, anchoring the dominant
  # platform at zero instead of leaving it floating mid-bar.
  geom_col(position = position_stack(reverse = TRUE), width = 0.72) +
  scale_fill_manual(values = pal, drop = FALSE, name = "Detected platform") +
  scale_x_continuous(expand = expansion(mult = c(0, 0.02))) +
  labs(
    title    = "Website Platform by County Rurality in Texas",
    subtitle = "254 counties, USDA ERS Rural-Urban Continuum Codes 2023",
    x = "Counties", y = NULL,
    caption  = medsl_caption(
      source = "tx-county-watch snapshots, 2026-08-20; USDA ERS RUCC 2023")
  ) +
  guides(fill = guide_legend(title.position = "top", nrow = 2, byrow = TRUE,
                             keywidth = unit(11, "pt"), keyheight = unit(11, "pt"))) +
  theme_medsl() +
  theme(legend.position = "bottom",
        panel.grid.major.y = element_blank())

ggsave_medsl(file.path(outdir, "fig2_tx_platform_by_rurality.png"), plot = p,
             width = 10, height = 6.4)
cat("wrote fig2_tx_platform_by_rurality.png\n")
print(plotdat |> select(rucc_band, plat, n) |> arrange(match(rucc_band, band_order), plat), n = 40)
