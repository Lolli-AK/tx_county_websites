#!/usr/bin/env Rscript
# Figure 1 - Texas county choropleth of website platform (the CMS behind the
# county's election site), all 254 counties.
#
# Platform comes from analysis/detect_platform.py, which uses SAME-HOST evidence
# only. Outbound links to election-services vendors are deliberately excluded -
# 24 counties link to a Tyler Technologies court-records portal, which says
# nothing about who built the site.

suppressPackageStartupMessages({
  library(ggmedsl); library(ggplot2); library(dplyr); library(readr)
  library(sf); library(tigris); library(stringr)
})
medsl_fonts(dpi = 300)
options(tigris_use_cache = TRUE, tigris_class = "sf")

# Run from the repo root.
root <- "."
stopifnot(dir.exists(file.path(root, "analysis", "output")))
outdir <- file.path(root, "analysis", "output", "figures")
dir.create(outdir, recursive = TRUE, showWarnings = FALSE)

# fips MUST be character: tigris GEOID is character, and a numeric join fails.
dat <- read_csv(file.path(root, "analysis", "output", "tx_platform_rucc.csv"),
                col_types = cols(fips = col_character(), .default = col_guess()))

# Collapse platforms seen on fewer than three counties, so the legend stays
# inside the 8-colour categorical palette. The unidentifiable bucket is named
# for WHY it is unidentifiable rather than "other".
small <- dat |> count(platform) |> filter(n < 5, platform != "Other / unknown") |> pull(platform)
dat <- dat |>
  mutate(plat = case_when(
    platform == "Other / unknown" ~ "Unidentifiable from snapshot",
    platform %in% small           ~ "Other identified platform",
    TRUE                          ~ platform))

lvl <- c("ezTask Titanium (TAC)", "CivicPlus", "WordPress", "Revize",
         "Granicus / Vision", "Other identified platform",
         "Unidentifiable from snapshot")
dat$plat <- factor(dat$plat, levels = lvl)
stopifnot(!any(is.na(dat$plat)))

# Hand-built from medsl_colors; the unidentifiable bucket takes the brand
# "Chart Gray" because it IS absent data, not a category.
pal <- c(
  "ezTask Titanium (TAC)"        = medsl_colors[["purple"]],
  "CivicPlus"                    = medsl_colors[["gold"]],
  "WordPress"                    = medsl_colors[["green"]],
  "Revize"                       = "#FF8318",
  "Granicus / Vision"            = medsl_colors[["sky"]],
  "Other identified platform"    = medsl_colors[["olive"]],
  "Unidentifiable from snapshot" = "#C4C4C4"
)

stopifnot(setequal(names(pal), lvl))   # every level must have a colour

geo <- counties(state = "TX", cb = TRUE, year = 2023, progress_bar = FALSE) |>
  select(GEOID, geometry)
map <- geo |> left_join(dat, by = c("GEOID" = "fips"))
stopifnot(nrow(map) == 254, !any(is.na(map$plat)))

n_unk <- sum(dat$plat == "Unidentifiable from snapshot")

p <- ggplot(map) +
  geom_sf(aes(fill = plat), colour = "white", linewidth = 0.12) +
  coord_sf(crs = 3083, datum = NA) +               # Texas Centric Albers
  scale_fill_manual(values = pal, drop = FALSE, name = "Detected platform") +
  labs(
    title    = "Website Platform of Texas County Election Sites",
    subtitle = sprintf("254 counties, detected from captured homepage HTML; %d not identifiable", n_unk),
    caption  = medsl_caption(source = "tx-county-watch snapshots, 2026-08-20"),
    tag      = "Same-host evidence only; outbound election-vendor links excluded."
  ) +
  guides(fill = guide_legend(title.position = "top", nrow = 2, byrow = TRUE,
                             keywidth = unit(11, "pt"), keyheight = unit(11, "pt"))) +
  theme_medsl_map() +
  theme(legend.position = "bottom",
        legend.box.margin = margin(t = 4),
        legend.title = element_text(hjust = 0),
        plot.tag.position = c(0.99, 0.012),   # below the legend, beside the caption
        plot.tag = element_text(size = 7, colour = "#666666", hjust = 1, vjust = 0))

ggsave_medsl(file.path(outdir, "fig1_tx_platform_map.png"), plot = p,
             width = 9, height = 8.2)
cat("wrote fig1_tx_platform_map.png\n")
print(dat |> count(plat) |> arrange(desc(n)), n = 20)
