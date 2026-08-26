#!/usr/bin/env Rscript
# Do county ATTRIBUTES predict how much election information a county states?
#
# The two things we already know dominate are included as controls, because any
# covariate has to beat them to mean anything:
#   pages_captured  - a county with 2 election pages has less surface than one
#                     with 5 (Spearman +0.26 with facts stated)
#   mentions_nov3   - counties that have switched to the November general state
#                     2.21 facts on average vs 0.51 for those that have not
#
# Covariates, all county-level and complete for 254:
#   population 2020, land area (TIGER ALAND), population density,
#   RUCC 2023, median household income 2022, unemployment rate 2023,
#   % adults with a bachelor's degree 2019-23, poverty rate 2021
#
# ERS files are LATIN-1 and LONG format (Attribute/Value), same as RUCC.
# PovertyEstimates uses `Stabr` where the others use `State`.
#
# Output: analysis/output/tx_covariates.csv

suppressPackageStartupMessages({
  library(dplyr); library(readr); library(tidyr); library(stringr)
  library(sf); library(tigris)
})
options(tigris_use_cache = TRUE, tigris_class = "sf")
root <- "."
OUT <- file.path(root, "analysis", "output")
L1 <- locale(encoding = "latin1")

pull_attr <- function(file, statecol, fipscol, attrs) {
  read_csv(file.path(root, "analysis", "data", file), locale = L1,
           show_col_types = FALSE, progress = FALSE) |>
    rename(state = all_of(statecol), fips = all_of(fipscol)) |>
    # FIPS must be character everywhere: TIGER GEOID is character, and these
    # files parse it as a double, which makes every join fail.
    mutate(fips = sprintf("%05d", as.integer(fips))) |>
    filter(state == "TX", Attribute %in% attrs,
           !str_ends(fips, "000")) |>            # drop the state-level row
    mutate(Value = parse_number(as.character(Value))) |>
    select(fips, Attribute, Value) |>
    pivot_wider(names_from = Attribute, values_from = Value)
}

une <- pull_attr("Unemployment2023.csv", "State", "FIPS_Code",
                 c("Median_Household_Income_2022", "Unemployment_rate_2023"))
edu <- pull_attr("Education2023.csv", "State", "FIPS Code",
                 c("Percent of adults with a bachelor's degree or higher, 2019-23"))
pov <- pull_attr("PovertyEstimates.csv", "Stabr", "FIPS_Code",
                 c("PCTPOVALL_2021"))

# Land area: TIGER ALAND is square metres.
geo <- counties(state = "TX", cb = TRUE, year = 2023, progress_bar = FALSE) |>
  st_drop_geometry() |>
  transmute(fips = GEOID, land_sqmi = ALAND / 2589988.11)

facts <- read_csv(file.path(OUT, "tx_facts.csv"), show_col_types = FALSE)
base  <- read_csv(file.path(OUT, "tx_platform_rucc.csv"),
                  col_types = cols(fips = col_character(), .default = col_guess()))
why   <- read_csv(file.path(OUT, "tx_why_silent.csv"), show_col_types = FALSE)

cov <- facts |>
  group_by(county) |>
  summarise(facts_stated = sum(verdict %in% c("Matches expected", "States something else")),
            pages = first(pages_captured), .groups = "drop") |>
  left_join(base |> select(county, fips, rucc, rucc_band, pop2020, platform), by = "county") |>
  left_join(why |> select(county, mentions_nov3, has_elections_page), by = "county") |>
  left_join(une, by = "fips") |> left_join(edu, by = "fips") |>
  left_join(pov, by = "fips") |> left_join(geo, by = "fips") |>
  rename(med_income = Median_Household_Income_2022,
         unemp = Unemployment_rate_2023,
         pct_bach = `Percent of adults with a bachelor's degree or higher, 2019-23`,
         pct_pov = PCTPOVALL_2021) |>
  mutate(density = pop2020 / land_sqmi,
         nov3 = as.integer(mentions_nov3 == "yes"))

stopifnot(nrow(cov) == 254)
miss <- sapply(cov[c("pop2020","land_sqmi","med_income","unemp","pct_bach","pct_pov")],
               function(x) sum(is.na(x)))
cat("missing values per covariate:\n"); print(miss)
cov <- cov |> filter(!is.na(med_income), !is.na(pct_bach), !is.na(pct_pov), !is.na(unemp))
cat(sprintf("\ncomplete cases: %d of 254\n", nrow(cov)))
write_csv(cov, file.path(OUT, "tx_covariates.csv"))

vars <- c(pop2020 = "Population 2020", land_sqmi = "Land area (sq mi)",
          density = "Population density", rucc = "RUCC (higher = rural)",
          med_income = "Median household income", pct_pov = "Poverty rate",
          pct_bach = "% bachelor's or higher", unemp = "Unemployment rate",
          pages = "Pages captured [control]", nov3 = "Mentions Nov 3 [control]")

cat("\n=== BIVARIATE: Spearman vs facts stated ===\n")
for (v in names(vars)) {
  t <- suppressWarnings(cor.test(cov[[v]], cov$facts_stated, method = "spearman"))
  cat(sprintf("  %-30s rho = %+.3f   p = %.3g%s\n", vars[[v]], t$estimate, t$p.value,
              ifelse(t$p.value < .05, "  *", "")))
}

cat("\n=== MULTIVARIATE: facts_stated ~ controls + attributes ===\n")
# density = pop / land, so log10(density) = log10(pop) - log10(land) EXACTLY.
# Including all three is a perfect linear dependency: VIF is Inf and R silently
# drops one as aliased. Keep population and land area; density is implied.
m <- lm(facts_stated ~ pages + nov3 + log10(pop2020) + log10(land_sqmi) +
          scale(med_income) + scale(pct_bach) + scale(pct_pov) + scale(unemp),
        data = cov)
print(round(summary(m)$coefficients, 4))
cat(sprintf("\nadj R^2 = %.3f  (n = %d)\n", summary(m)$adj.r.squared, nobs(m)))

cat("\n=== controls only, for comparison ===\n")
m0 <- lm(facts_stated ~ pages + nov3, data = cov)
cat(sprintf("adj R^2 = %.3f\n", summary(m0)$adj.r.squared))
cat("\nF-test: do the county attributes add anything over the two controls?\n")
print(anova(m0, m))

cat("\n=== collinearity (VIF) ===\n")
X <- model.matrix(m)[, -1]
vif <- sapply(seq_len(ncol(X)), function(i) 1 / (1 - summary(lm(X[, i] ~ X[, -i]))$r.squared))
print(round(setNames(vif, colnames(X)), 2))

# Robustness: the outcome is a bounded count (0-4), not continuous. A Poisson
# fit should agree with OLS on which terms matter; if it does not, prefer it.
cat("\n=== robustness: Poisson on the same terms ===\n")
mp <- glm(facts_stated ~ pages + nov3 + log10(pop2020) + log10(land_sqmi) +
            scale(med_income) + scale(pct_bach) + scale(pct_pov) + scale(unemp),
          family = poisson, data = cov)
print(round(summary(mp)$coefficients, 4))
