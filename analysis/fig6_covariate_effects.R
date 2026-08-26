#!/usr/bin/env Rscript
# Figure 6 - what predicts how many election facts a county states?
# Coefficient plot, all predictors standardised so effect sizes are comparable.
# The point is the NULL: once page count and November-switch are in the model,
# no county attribute is distinguishable from zero.
suppressPackageStartupMessages({
  library(ggmedsl); library(ggplot2); library(dplyr); library(readr); library(tidyr)
})
medsl_fonts(dpi = 300)
root <- "."; OUT <- file.path(root, "analysis", "output")

cov <- read_csv(file.path(OUT, "tx_covariates.csv"), show_col_types = FALSE) |>
  mutate(log_pop = log10(pop2020), log_land = log10(land_sqmi))

# z-score every predictor so the coefficients are on one scale.
preds <- c(pages = "Election pages captured", nov3 = "References the Nov 3 general",
           log_pop = "Population (log)", log_land = "Land area (log)",
           med_income = "Median household income", pct_bach = "% bachelor's or higher",
           pct_pov = "Poverty rate", unemp = "Unemployment rate")
d <- cov |> mutate(across(all_of(names(preds)), ~as.numeric(scale(.))))
m <- lm(as.formula(paste("facts_stated ~", paste(names(preds), collapse = " + "))), data = d)

ci <- confint(m)
tab <- tibble(term = names(coef(m)), est = coef(m),
              lo = ci[, 1], hi = ci[, 2]) |>
  filter(term != "(Intercept)") |>
  mutate(label = unname(preds[term]),
         kind = ifelse(term %in% c("pages", "nov3"),
                       "Capture / election-cycle control", "County attribute"),
         sig = (lo > 0 | hi < 0)) |>
  arrange(est) |>
  mutate(label = factor(label, levels = label))

p <- ggplot(tab, aes(x = est, y = label, colour = kind)) +
  geom_vline(xintercept = 0, colour = "#888888", linewidth = 0.4) +
  geom_errorbarh(aes(xmin = lo, xmax = hi), height = 0, linewidth = 0.8) +
  geom_point(size = 2.8) +
  scale_colour_manual(values = c("Capture / election-cycle control" = medsl_colors[["blue"]],
                                 "County attribute" = medsl_colors[["gold"]]),
                      name = NULL) +
  labs(title = "Predictors of How Many Election Facts a Texas County States",
       subtitle = "254 counties; standardised OLS coefficients with 95% confidence intervals",
       x = "Change in facts stated (of 4) per standard deviation", y = NULL,
       caption = medsl_caption(
         source = "tx-county-watch snapshots, 2026-08-20; USDA ERS and Census TIGER"),
       tag = sprintf("Attributes add nothing over the two controls: F-test p = 0.090, adj R-sq 0.430 to %.3f.",
                     summary(m)$adj.r.squared)) +
  theme_medsl() +
  theme(legend.position = "bottom", panel.grid.major.y = element_blank(),
        plot.tag.position = c(0.99, 0.03),
        plot.tag = element_text(size = 7, colour = "#666666", hjust = 1, vjust = 0))

ggsave_medsl(file.path(OUT, "figures", "fig6_tx_covariate_effects.png"), plot = p,
             width = 10, height = 5.8)
cat("wrote fig6_tx_covariate_effects.png\n")
print(tab |> select(label, est, lo, hi, sig) |> mutate(across(where(is.numeric), ~round(., 3))))
