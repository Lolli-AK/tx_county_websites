#!/usr/bin/env python3
"""One-shot builder for manifest/counties.csv — the seed of truth for all 254 counties.

Every other script reads that CSV instead of carrying its own county list, so
adding or correcting a county is a manifest edit, never a code change.

Columns: county, seat, batch, homepage
  batch 1 = the 24 counties whose homepages were pre-verified (homepage filled in)
  batch 2 = 100 counties, homepage discovered in Phase 1 (left blank here)
  batch 3 = 130 counties, homepage discovered in Phase 1 (left blank here)

Kept in the repo as the record of how the seed was assembled.
"""
from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "manifest" / "counties.csv"

# batch 1 — (county, seat, verified homepage)
BATCH1 = [
    ("Harris", "Houston", "https://www.harriscountytx.gov/"),
    ("Dallas", "Dallas", "https://www.dallascounty.org/"),
    ("Tarrant", "Fort Worth", "https://www.tarrantcountytx.gov/"),
    ("Bexar", "San Antonio", "https://www.bexar.org/"),
    ("Travis", "Austin", "https://www.traviscountytx.gov/"),
    ("Collin", "McKinney", "https://www.collincountytx.gov/"),
    ("El Paso", "El Paso", "https://www.epcounty.com/"),
    ("Hidalgo", "Edinburg", "https://www.hidalgocounty.us/"),
    ("Williamson", "Georgetown", "https://www.wilcotx.gov/"),
    ("Webb", "Laredo", "https://www.webbcountytx.gov/"),
    ("Lubbock", "Lubbock", "https://www.lubbockcounty.gov/"),
    ("Bell", "Belton", "https://www.bellcountytx.com/"),
    ("Galveston", "Galveston", "https://www.galvestoncountytx.gov/"),
    ("Kerr", "Kerrville", "https://kerrcountytx.gov/"),
    ("Gillespie", "Fredericksburg", "https://www.gillespiecounty.gov/"),
    ("Medina", "Hondo", "https://www.medinatx.gov/"),
    ("Llano", "Llano", "https://www.co.llano.tx.us/"),
    ("Brewster", "Alpine", "https://www.brewstercounty.gov/"),
    ("Presidio", "Marfa", "https://www.co.presidio.tx.us/"),
    ("Hartley", "Channing", "https://www.co.hartley.tx.us/"),
    ("Roberts", "Miami", "https://www.co.roberts.tx.us/"),
    ("Loving", "Mentone", "https://www.co.loving.tx.us/"),
    ("King", "Guthrie", "https://www.co.king.tx.us/"),
    ("Kenedy", "Sarita", "https://www.kenedycountytx.gov/"),
]

# batch 2 — (county, seat)
BATCH2 = [
    ("Anderson", "Palestine"), ("Andrews", "Andrews"), ("Angelina", "Lufkin"),
    ("Aransas", "Rockport"), ("Archer", "Archer City"), ("Armstrong", "Claude"),
    ("Atascosa", "Jourdanton"), ("Austin", "Bellville"), ("Bailey", "Muleshoe"),
    ("Bandera", "Bandera"), ("Bastrop", "Bastrop"), ("Baylor", "Seymour"),
    ("Bee", "Beeville"), ("Blanco", "Johnson City"), ("Borden", "Gail"),
    ("Bosque", "Meridian"), ("Bowie", "Boston"), ("Brazoria", "Angleton"),
    ("Brazos", "Bryan"), ("Briscoe", "Silverton"), ("Brooks", "Falfurrias"),
    ("Brown", "Brownwood"), ("Burleson", "Caldwell"), ("Burnet", "Burnet"),
    ("Caldwell", "Lockhart"), ("Calhoun", "Port Lavaca"), ("Callahan", "Baird"),
    ("Cameron", "Brownsville"), ("Camp", "Pittsburg"), ("Carson", "Panhandle"),
    ("Cass", "Linden"), ("Castro", "Dimmitt"), ("Chambers", "Anahuac"),
    ("Cherokee", "Rusk"), ("Childress", "Childress"), ("Clay", "Henrietta"),
    ("Cochran", "Morton"), ("Coke", "Robert Lee"), ("Coleman", "Coleman"),
    ("Collingsworth", "Wellington"), ("Colorado", "Columbus"),
    ("Comal", "New Braunfels"), ("Comanche", "Comanche"), ("Concho", "Paint Rock"),
    ("Cooke", "Gainesville"), ("Coryell", "Gatesville"), ("Cottle", "Paducah"),
    ("Crane", "Crane"), ("Crockett", "Ozona"), ("Crosby", "Crosbyton"),
    ("Culberson", "Van Horn"), ("Dallam", "Dalhart"), ("Dawson", "Lamesa"),
    ("Deaf Smith", "Hereford"), ("Delta", "Cooper"), ("Denton", "Denton"),
    ("DeWitt", "Cuero"), ("Dickens", "Dickens"), ("Dimmit", "Carrizo Springs"),
    ("Donley", "Clarendon"), ("Duval", "San Diego"), ("Eastland", "Eastland"),
    ("Ector", "Odessa"), ("Edwards", "Rocksprings"), ("Ellis", "Waxahachie"),
    ("Erath", "Stephenville"), ("Falls", "Marlin"), ("Fannin", "Bonham"),
    ("Fayette", "La Grange"), ("Fisher", "Roby"), ("Floyd", "Floydada"),
    ("Foard", "Crowell"), ("Fort Bend", "Richmond"), ("Franklin", "Mount Vernon"),
    ("Freestone", "Fairfield"), ("Frio", "Pearsall"), ("Gaines", "Seminole"),
    ("Garza", "Post"), ("Glasscock", "Garden City"), ("Goliad", "Goliad"),
    ("Gonzales", "Gonzales"), ("Gray", "Pampa"), ("Grayson", "Sherman"),
    ("Gregg", "Longview"), ("Grimes", "Anderson"), ("Guadalupe", "Seguin"),
    ("Hale", "Plainview"), ("Hall", "Memphis"), ("Hamilton", "Hamilton"),
    ("Hansford", "Spearman"), ("Hardeman", "Quanah"), ("Hardin", "Kountze"),
    ("Harrison", "Marshall"), ("Haskell", "Haskell"), ("Hays", "San Marcos"),
    ("Hemphill", "Canadian"), ("Henderson", "Athens"), ("Hill", "Hillsboro"),
    ("Hockley", "Levelland"), ("Hood", "Granbury"),
]

# batch 3 — (county, seat)
BATCH3 = [
    ("Hopkins", "Sulphur Springs"), ("Houston", "Crockett"), ("Howard", "Big Spring"),
    ("Hudspeth", "Sierra Blanca"), ("Hunt", "Greenville"), ("Hutchinson", "Stinnett"),
    ("Irion", "Mertzon"), ("Jack", "Jacksboro"), ("Jackson", "Edna"),
    ("Jasper", "Jasper"), ("Jeff Davis", "Fort Davis"), ("Jefferson", "Beaumont"),
    ("Jim Hogg", "Hebbronville"), ("Jim Wells", "Alice"), ("Johnson", "Cleburne"),
    ("Jones", "Anson"), ("Karnes", "Karnes City"), ("Kaufman", "Kaufman"),
    ("Kendall", "Boerne"), ("Kent", "Jayton"), ("Kimble", "Junction"),
    ("Kinney", "Brackettville"), ("Kleberg", "Kingsville"), ("Knox", "Benjamin"),
    ("Lamar", "Paris"), ("Lamb", "Littlefield"), ("Lampasas", "Lampasas"),
    ("La Salle", "Cotulla"), ("Lavaca", "Hallettsville"), ("Lee", "Giddings"),
    ("Leon", "Centerville"), ("Liberty", "Liberty"), ("Limestone", "Groesbeck"),
    ("Lipscomb", "Lipscomb"), ("Live Oak", "George West"), ("Lynn", "Tahoka"),
    ("Madison", "Madisonville"), ("Marion", "Jefferson"), ("Martin", "Stanton"),
    ("Mason", "Mason"), ("Matagorda", "Bay City"), ("Maverick", "Eagle Pass"),
    ("McCulloch", "Brady"), ("McLennan", "Waco"), ("McMullen", "Tilden"),
    ("Menard", "Menard"), ("Midland", "Midland"), ("Milam", "Cameron"),
    ("Mills", "Goldthwaite"), ("Mitchell", "Colorado City"), ("Montague", "Montague"),
    ("Montgomery", "Conroe"), ("Moore", "Dumas"), ("Morris", "Daingerfield"),
    ("Motley", "Matador"), ("Nacogdoches", "Nacogdoches"), ("Navarro", "Corsicana"),
    ("Newton", "Newton"), ("Nolan", "Sweetwater"), ("Nueces", "Corpus Christi"),
    ("Ochiltree", "Perryton"), ("Oldham", "Vega"), ("Orange", "Orange"),
    ("Palo Pinto", "Palo Pinto"), ("Panola", "Carthage"), ("Parker", "Weatherford"),
    ("Parmer", "Farwell"), ("Pecos", "Fort Stockton"), ("Polk", "Livingston"),
    ("Potter", "Amarillo"), ("Rains", "Emory"), ("Randall", "Canyon"),
    ("Reagan", "Big Lake"), ("Real", "Leakey"), ("Red River", "Clarksville"),
    ("Reeves", "Pecos"), ("Refugio", "Refugio"), ("Robertson", "Franklin"),
    ("Rockwall", "Rockwall"), ("Runnels", "Ballinger"), ("Rusk", "Henderson"),
    ("Sabine", "Hemphill"), ("San Augustine", "San Augustine"),
    ("San Jacinto", "Coldspring"), ("San Patricio", "Sinton"),
    ("San Saba", "San Saba"), ("Schleicher", "Eldorado"), ("Scurry", "Snyder"),
    ("Shackelford", "Albany"), ("Shelby", "Center"), ("Sherman", "Stratford"),
    ("Smith", "Tyler"), ("Somervell", "Glen Rose"), ("Starr", "Rio Grande City"),
    ("Stephens", "Breckenridge"), ("Sterling", "Sterling City"),
    ("Stonewall", "Aspermont"), ("Sutton", "Sonora"), ("Swisher", "Tulia"),
    ("Taylor", "Abilene"), ("Terrell", "Sanderson"), ("Terry", "Brownfield"),
    ("Throckmorton", "Throckmorton"), ("Titus", "Mount Pleasant"),
    ("Tom Green", "San Angelo"), ("Trinity", "Groveton"), ("Tyler", "Woodville"),
    ("Upshur", "Gilmer"), ("Upton", "Rankin"), ("Uvalde", "Uvalde"),
    ("Val Verde", "Del Rio"), ("Van Zandt", "Canton"), ("Victoria", "Victoria"),
    ("Walker", "Huntsville"), ("Waller", "Hempstead"), ("Ward", "Monahans"),
    ("Washington", "Brenham"), ("Wharton", "Wharton"), ("Wheeler", "Wheeler"),
    ("Wichita", "Wichita Falls"), ("Wilbarger", "Vernon"),
    ("Willacy", "Raymondville"), ("Wilson", "Floresville"), ("Winkler", "Kermit"),
    ("Wise", "Decatur"), ("Wood", "Quitman"), ("Yoakum", "Plains"),
    ("Young", "Graham"), ("Zapata", "Zapata"), ("Zavala", "Crystal City"),
]


def main() -> None:
    rows = []
    for c, s, h in BATCH1:
        rows.append({"county": c, "seat": s, "batch": "1", "homepage": h})
    for c, s in BATCH2:
        rows.append({"county": c, "seat": s, "batch": "2", "homepage": ""})
    for c, s in BATCH3:
        rows.append({"county": c, "seat": s, "batch": "3", "homepage": ""})

    names = [r["county"] for r in rows]
    assert len(names) == len(set(names)) == 254, (
        f"expected 254 unique counties, got {len(names)} rows / {len(set(names))} unique")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["county", "seat", "batch", "homepage"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT} — {len(rows)} counties "
          f"(batch1={len(BATCH1)}, batch2={len(BATCH2)}, batch3={len(BATCH3)})")


if __name__ == "__main__":
    main()
