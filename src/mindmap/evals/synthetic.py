"""Deterministic synthetic documents for offline pipeline measurements (no model involved).

`city_report()` imitates a long municipal annual report: 30 sections, each about one
distinct programme (its key phrase appears in one or two sentences only), padded with
realistic boilerplate that repeats across sections with different numbers, followed by an
appendix of references (URLs, dates) and numeric tables. It is used to measure whether
passage selection keeps every section's key concept, and how much of the model's input
budget goes to low-value appendix text.
"""

from __future__ import annotations

import random

# (key phrase, two detail clauses unique to the section)
TOPICS: list[tuple[str, str, str]] = [
    ("bus rapid transit", "added dedicated lanes on the northern corridor", "cut average journey times for commuters"),
    ("stormwater tunnels", "diverted overflow away from the riverside district", "reduced basement flooding claims"),
    ("library digitisation", "scanned the historic newspaper archive", "opened the collection to remote researchers"),
    ("street lighting retrofit", "replaced sodium lamps with dimmable fixtures", "lowered the electricity bill for public lighting"),
    ("school meal programme", "sourced vegetables from regional farms", "extended free breakfasts to two more districts"),
    ("cycle lane network", "connected the university to the central station", "separated riders from heavy goods traffic"),
    ("social housing renovation", "insulated older apartment blocks", "replaced failing lifts in tower buildings"),
    ("urban tree canopy", "planted shade trees along exposed avenues", "mapped heat islands with satellite imagery"),
    ("waste sorting centre", "installed optical sorters for plastics", "raised the recycling rate for packaging"),
    ("noise monitoring", "placed sensors near the ring road", "published hourly decibel readings online"),
    ("youth employment scheme", "paired apprentices with local employers", "funded driving lessons for job seekers"),
    ("harbour dredging", "deepened the inner basin for ferries", "relocated contaminated sediment to a sealed site"),
    ("emergency dispatch upgrade", "merged police and ambulance call handling", "shortened response times in rural districts"),
    ("district heating expansion", "laid insulated pipes under the old town", "connected hospitals to waste heat from the incinerator"),
    ("air quality zone", "restricted older diesel vans in the centre", "measured nitrogen dioxide at school gates"),
    ("cemetery capacity", "opened a woodland burial ground", "digitised plot records for families"),
    ("public wifi rollout", "covered market squares and bus shelters", "filtered traffic to protect minors"),
    ("flood barrier maintenance", "replaced hydraulic seals on the tidal gates", "tested evacuation sirens twice a year"),
    ("senior care visits", "trained volunteers to check on isolated residents", "introduced tablets for video calls"),
    ("parking sensor pilot", "guided drivers to free spaces by app", "reduced cruising traffic around the stadium"),
    ("museum roof repair", "removed asbestos from the attic", "restored the copper dome"),
    ("allotment waiting list", "split large plots for new gardeners", "added raised beds for wheelchair users"),
    ("graffiti removal service", "cleaned listed buildings within two days", "commissioned legal mural walls"),
    ("water meter replacement", "installed smart meters in every household", "detected leaks through night-time flow analysis"),
    ("bridge inspection programme", "used drones to survey steel girders", "closed one footbridge for urgent repairs"),
    ("refugee welcome centre", "offered language classes and legal advice", "matched families with host volunteers"),
    ("sports hall accessibility", "fitted hoists in changing rooms", "added tactile paving at entrances"),
    ("procurement reform", "published every contract above fifty thousand", "required carbon reporting from suppliers"),
    ("tourism tax", "charged visitors per night in hotels", "ring-fenced income for street cleaning"),
    ("open data portal", "released transport and budget datasets", "hosted a hackathon for civic apps"),
]

BOILERPLATE = [
    "The department reported progress on this programme to the council in quarter {q} of {y}.",
    "Officials said that further work would continue during the {y} financial year.",
    "Residents were consulted through {n} public meetings and an online survey.",
    "The budget line was reviewed by the finance committee and approved with {n} amendments.",
    "Staff costs rose by {p} percent compared with the previous year.",
    "An external auditor examined the accounts and raised {n} minor observations.",
    "The project board met {n} times and kept a public record of its decisions.",
    "Delays were attributed to supply chain problems and staff shortages in {y}.",
    "A further update will be presented in the next annual report.",
    "Councillors from all parties supported the continuation of the work.",
]


def city_report(seed: int = 11, filler_per_section: int = 8) -> str:
    rng = random.Random(seed)
    sections = []
    for i, (key, detail_a, detail_b) in enumerate(TOPICS, start=1):
        filler = [
            rng.choice(BOILERPLATE).format(q=rng.randint(1, 4), y=rng.randint(2019, 2026),
                                           n=rng.randint(2, 40), p=rng.randint(1, 15))
            for _ in range(filler_per_section)
        ]
        topical = [
            f"The {key} programme {detail_a}.",
            f"According to the evaluation, the {key} work also {detail_b}.",
        ]
        a, b = filler_per_section // 3, 2 * filler_per_section // 3
        body = filler[:a] + topical[:1] + filler[a:b] + topical[1:] + filler[b:]
        sections.append(f"Section {i}. {key.title()}\n\n" + " ".join(body))
    appendix = ["Appendix A. References and data tables"]
    for j in range(1, 121):
        appendix.append(
            f"[{j}] https://data.example-city.gov/reports/{rng.randint(2015, 2026)}/"
            f"{rng.choice(['ridership', 'budget', 'survey', 'audit', 'sensor'])}-{rng.randint(100, 999)}.csv "
            f"accessed {rng.randint(1, 28)}/{rng.randint(1, 12)}/{rng.randint(2020, 2026)}."
        )
    for t in range(1, 25):
        row = " ".join(f"{rng.randint(1000, 99999):,}" for _ in range(8))
        appendix.append(f"Table {t}: {row}.")
    return "\n\n".join(sections) + "\n\n" + "\n".join(appendix) + "\n"


def topic_keys() -> list[str]:
    return [t[0] for t in TOPICS]
