"""Generate 200 synthetic form leads for Fieldnote and the answer key for them.

Fieldnote is a made-up SaaS for tracking construction projects. Emails and
websites use example.com subdomains and phones use ranges reserved for fiction,
so nothing here points to a real person or company.
"""

import csv
import json
import random
import re
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from faker import Faker

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT

SEED = 42
DATA_DIR = ROOT / "data"
INTENT_COUNTS = {
    "demo_request": 50,
    "pricing": 35,
    "support_existing_customer": 25,
    "partnership": 20,
    "job_seeker": 20,
    "spam": 20,
}
DUPLICATES = 20
JUNK = 10
TOTAL = sum(INTENT_COUNTS.values()) + DUPLICATES + JUNK
START = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)

COUNTRIES = ["US", "UK", "CA", "AU"]
COUNTRY_WEIGHTS = [50, 20, 15, 15]
LOCALE = {"US": "en_US", "CA": "en_US", "UK": "en_GB", "AU": "en_GB"}
COUNTRY_NAME = {"US": "the US", "UK": "the UK", "CA": "Canada", "AU": "Australia"}

SIZES = ["1-10", "11-50", "51-200", "201-1000", "1000+"]
SIZE_WEIGHTS = [15, 25, 30, 20, 10]
BIG_SIZES = {"51-200", "201-1000", "1000+"}

DECISION_TITLES = [
    "Owner",
    "Co-Owner",
    "Managing Director",
    "Director of Operations",
    "Construction Director",
    "Operations Manager",
    "Project Manager",
    "Senior Project Manager",
]
OTHER_TITLES = [
    "Site Engineer",
    "Estimator",
    "Office Administrator",
    "Marketing Coordinator",
    "Foreman",
    "Accountant",
    "Safety Officer",
    "Intern",
]
PARTNER_TITLES = ["Founder", "CEO", "Partnerships Manager", "Business Development Lead"]
SPAM_TITLES = ["SEO Specialist", "Account Executive", "Growth Manager", "Founder"]

COMPANY_WORDS = {
    "builder": [
        "Construction",
        "Builders",
        "Contracting",
        "Homes",
        "Civil",
        "Developments",
    ],
    "partner": ["Software", "Consulting", "Estimating", "Equipment Rental"],
    "spammer": ["SEO", "Digital", "Growth Media", "Web Solutions"],
}

MESSAGES = {
    "demo_request": [
        "Can we get a demo of Fieldnote? We have {n} active sites right now.",
        (
            "Hi, I'm the {title} at {company}. Our site reports still live in spreadsheets "
            "and photos get lost in group chats. Could someone walk us through Fieldnote this week?"
        ),
        "hey, saw fieldnote at a trade show. would love a quick demo for our PMs",
        (
            "Hello. We are evaluating tools to track progress across {n} projects in {city}. "
            "Please contact me to schedule a product demonstration."
        ),
        "Looking for a demo. Main pain is daily logs and punch lists across {n} jobs.",
    ],
    "pricing": [
        "How much does Fieldnote cost for about {users} users?",
        "Hi, can you send pricing? We're a {size} person firm running {n} projects at a time.",
        "do you have annual plans or only monthly? need a number for next year's budget",
        (
            "Good afternoon. Please share your pricing tiers and whether you charge per project "
            "or per user. We would roll it out to {users} field staff."
        ),
    ],
    "support_existing_customer": [
        "We're already on Fieldnote and photos from the mobile app stopped syncing yesterday.",
        "How do I add a subcontractor to an existing project? Can't find the option.",
        "Our account admin left the company. Who can reset admin access for {company}?",
        (
            "The daily report PDF export cuts off the last page. We use Fieldnote on {n} projects "
            "so this is urgent for us."
        ),
    ],
    "partnership": [
        (
            "We build estimating software for general contractors. An integration with Fieldnote "
            "could help both our customers. Open to a call?"
        ),
        "I run a consultancy that helps builders go digital. Do you have a referral or partner program?",
        "We rent heavy equipment in {city} and would like to explore a co-marketing partnership.",
        "Interested in reselling Fieldnote to our clients in {country_name}. Who should I talk to?",
    ],
    "job_seeker": [
        "Hi, I'm a {title} with {years} years of experience. Are you hiring?",
        "Do you have any open roles in customer success? I know construction software well.",
        "I'd love to join the Fieldnote team in any role. Happy to send my CV.",
        "looking for an internship in product, can send my portfolio",
    ],
    "spam": [
        "We can get your website to page 1 on Google in 30 days. Reply for a free audit.",
        "Guest post opportunity on our high authority blog. Only $49 per article.",
        "Congratulations! Your business was selected for a free listing upgrade. Click to claim.",
        "We sell verified email lists of construction decision makers. 10,000 contacts for $199.",
    ],
}
CONTEXT = ["We are based in {city}.", "Happy to jump on a call."]
CLOSINGS = ["Thanks.", "Thanks in advance!", "Best regards.", "Cheers"]
FOLLOW_UPS = [
    "Following up on my message from last week.",
    "Sending this again in case it got lost.",
    "Any update on this?",
    "Resending, not sure the first form went through.",
]
JUNK_KINDS = ["bad_email"] * 5 + ["no_name"] * 3 + ["gibberish"] * 2
BAD_EMAILS = [
    "{first}.{last}@",
    "{first}{last}(at)example.net",
    "{first} {last}@example.com",
    "{first}@@example.com",
    "{first}@example",
]

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def new_id(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def fake_phone(rng: random.Random, country: str) -> str:
    # Only ranges reserved for film and TV, so no number can ring a real person.
    if country in ("US", "CA"):
        areas = (
            ["212", "312", "415", "617", "713"]
            if country == "US"
            else ["416", "604", "403"]
        )
        a, n = rng.choice(areas), rng.randint(100, 199)
        return rng.choice([f"({a}) 555-0{n}", f"{a}-555-0{n}", f"+1 {a} 555 0{n}"])
    if country == "UK":
        n = rng.randint(0, 999)
        return rng.choice(
            [f"07700 900{n:03d}", f"+44 7700 900{n:03d}", f"+44 (0)7700 900{n:03d}"]
        )
    n = rng.randint(6, 159)
    return rng.choice([f"0491 570 {n:03d}", f"+61 491 570 {n:03d}"])


def expected_tier(intent: str, title: str, size: str) -> str:
    """The answer-key rule documented in the README."""
    big = size in BIG_SIZES
    if intent in ("demo_request", "pricing"):
        return "hot" if title in DECISION_TITLES and big else "warm"
    if intent in ("support_existing_customer", "partnership"):
        return "warm" if big else "cold"
    return "cold"


def pick_title(rng: random.Random, intent: str) -> str:
    if intent in ("demo_request", "pricing"):
        pool = DECISION_TITLES if rng.random() < 0.65 else OTHER_TITLES
    elif intent == "support_existing_customer":
        pool = DECISION_TITLES if rng.random() < 0.4 else OTHER_TITLES
    elif intent == "partnership":
        pool = PARTNER_TITLES
    elif intent == "spam":
        pool = SPAM_TITLES
    else:
        pool = OTHER_TITLES if rng.random() < 0.8 else ["Project Manager"]
    return rng.choice(pool)


def write_message(rng: random.Random, intent: str, values: dict) -> str:
    text = rng.choice(MESSAGES[intent]).format(**values)
    if rng.random() < 0.3:
        text += " " + rng.choice(CONTEXT).format(**values)
    if rng.random() < 0.5:
        text += " " + rng.choice(CLOSINGS)
    return text


def make_lead(rng: random.Random, fake: Faker, intent: str, taken: set[str]) -> dict:
    country = rng.choices(COUNTRIES, COUNTRY_WEIGHTS)[0]
    f = fake[LOCALE[country]]
    first, last = f.first_name(), f.last_name()
    kind = {"partnership": "partner", "spam": "spammer"}.get(intent, "builder")
    company = f"{f.last_name()} {rng.choice(COMPANY_WORDS[kind])}"
    domain = f"{slug(company)}.example.com"
    title = pick_title(rng, intent)
    size = rng.choices(SIZES, SIZE_WEIGHTS)[0]

    local = rng.choice([f"{first}.{last}", f"{first[0]}{last}", first])
    local = re.sub(r"[^a-z.]", "", local.lower())
    email, n = f"{local}@{domain}", 2
    while email in taken:
        email, n = f"{local}{n}@{domain}", n + 1
    taken.add(email)

    # A few messy inputs so the Normalize node has something to fix.
    if rng.random() < 0.1:
        first, last = first.lower(), last.lower()
    values = {
        "n": rng.randint(3, 60),
        "users": rng.randint(5, 200),
        "years": rng.randint(2, 15),
        "size": size,
        "title": title,
        "company": company,
        "city": f.city(),
        "country_name": COUNTRY_NAME[country],
    }
    return {
        "submission_id": new_id(rng),
        "first_name": first,
        "last_name": last,
        "email": email,
        "phone": fake_phone(rng, country),
        "company": company,
        "website": rng.choice(
            [
                f"https://{domain}",
                f"https://www.{domain}/",
                f"www.{domain}",
                f"http://{domain}/contact",
            ]
        ),
        "job_title": title,
        "company_size": size,
        "country": country,
        "message": write_message(rng, intent, values),
        "submitted_at": "",
    }


def make_duplicate(rng: random.Random, original: dict) -> dict:
    email = original["email"]
    variant = rng.choice(
        [email.upper(), f"  {email} ", email.title(), f" {email.upper()}"]
    )
    message = original["message"]
    if rng.random() < 0.6:
        message = f"{rng.choice(FOLLOW_UPS)} {message}"
    return {
        **original,
        "submission_id": new_id(rng),
        "email": variant,
        "message": message,
    }


def make_junk(rng: random.Random, fake: Faker, kind: str, i: int) -> dict:
    country = rng.choice(COUNTRIES)
    f = fake[LOCALE[country]]
    first, last = f.first_name(), f.last_name()
    lead = {
        "submission_id": new_id(rng),
        "first_name": first,
        "last_name": last,
        "email": f"lead{i}@example.net",
        "phone": fake_phone(rng, country),
        "company": "",
        "website": "",
        "job_title": "",
        "company_size": "",
        "country": country,
        "message": rng.choice(MESSAGES["demo_request"][:1] + MESSAGES["spam"]).format(
            n=5
        ),
        "submitted_at": "",
    }
    if kind == "bad_email":
        lead["email"] = rng.choice(BAD_EMAILS).format(
            first=first.lower(), last=last.lower()
        )
    elif kind == "no_name":
        lead["first_name"], lead["last_name"] = rng.choice([("", ""), ("  ", " ")])
    else:
        mash = "".join(rng.choice("qwrtzxcvbnmlkjhgf") for _ in range(24))
        lead.update(
            first_name=mash[:5], last_name=mash[5:11], email=mash[11:16], message=mash
        )
    return lead


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_junk(lead: dict) -> bool:
    # Same rule as the Normalize node in n8n, so these counts match what the flow rejects.
    name = f"{lead['first_name']} {lead['last_name']}".strip()
    return not name or not EMAIL_RE.match(normalize_email(lead["email"]))


def build(rng: random.Random, fake: Faker) -> list[tuple[dict, dict]]:
    """Return (lead, answer key) pairs in the order they will be sent."""
    intents = [i for i, count in INTENT_COUNTS.items() for _ in range(count)]
    rng.shuffle(intents)
    taken: set[str] = set()
    rows = []
    for intent in intents:
        lead = make_lead(rng, fake, intent, taken)
        tier = expected_tier(intent, lead["job_title"], lead["company_size"])
        rows.append(
            (lead, {"intent": intent, "tier": tier, "dup": False, "junk": False})
        )

    # Each duplicate goes somewhere after its original, so the original is sent first.
    for original, key in rng.sample(rows, DUPLICATES):
        after = next(i for i, (lead, _) in enumerate(rows) if lead is original)
        row = (make_duplicate(rng, original), {**key, "dup": True})
        rows.insert(rng.randint(after + 1, len(rows)), row)

    for i, kind in enumerate(JUNK_KINDS):
        row = (
            make_junk(rng, fake, kind, i),
            {"intent": "", "tier": "", "dup": False, "junk": True},
        )
        rows.insert(rng.randint(0, len(rows)), row)

    when = START
    for lead, _ in rows:
        when += timedelta(minutes=rng.randint(20, 400))
        lead["submitted_at"] = when.isoformat().replace("+00:00", "Z")
    return rows


def check(rows: list[tuple[dict, dict]]) -> Counter:
    """Recount from the leads themselves and fail if anything is off."""
    seen: set[str] = set()
    counts: Counter = Counter()
    for lead, key in rows:
        junk = is_junk(lead)
        dup = not junk and normalize_email(lead["email"]) in seen
        if not junk:
            seen.add(normalize_email(lead["email"]))
        if junk != key["junk"] or dup != key["dup"]:
            raise SystemExit(f"answer key is wrong for {lead['submission_id']}")
        counts["junk"] += junk
        counts["duplicate"] += dup
        if not junk and not dup:
            counts[key["intent"]] += 1
            counts["tier_" + key["tier"]] += 1
    counts["new"] = len(seen)

    wanted = {"duplicate": DUPLICATES, "junk": JUNK, **INTENT_COUNTS}
    wrong = {k: (counts[k], v) for k, v in wanted.items() if counts[k] != v}
    if len(rows) != TOTAL or wrong:
        raise SystemExit(f"counts are off: {len(rows)} rows, (got, wanted) {wrong}")
    return counts


def write(rows: list[tuple[dict, dict]]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    lines = [json.dumps(lead, ensure_ascii=False) for lead, _ in rows]
    (DATA_DIR / "leads.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (DATA_DIR / "sample_leads.jsonl").write_text(
        "\n".join(lines[:10]) + "\n", encoding="utf-8"
    )
    with open(DATA_DIR / "expected.csv", "w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh)
        out.writerow(
            [
                "submission_id",
                "expected_intent",
                "expected_tier",
                "is_duplicate",
                "is_junk",
            ]
        )
        for lead, key in rows:
            out.writerow(
                [
                    lead["submission_id"],
                    key["intent"],
                    key["tier"],
                    str(key["dup"]).lower(),
                    str(key["junk"]).lower(),
                ]
            )


def main() -> None:
    Faker.seed(SEED)
    rows = build(random.Random(SEED), Faker(["en_US", "en_GB"]))
    counts = check(rows)
    write(rows)
    print(
        f"wrote {len(rows)} leads to data/leads.jsonl, answer key in data/expected.csv"
    )
    print(
        f"duplicates {counts['duplicate']}, junk {counts['junk']}, new contacts {counts['new']}"
    )
    print("intents: " + ", ".join(f"{i} {counts[i]}" for i in INTENT_COUNTS))
    print(
        "tiers: "
        + ", ".join(f"{t} {counts['tier_' + t]}" for t in ("hot", "warm", "cold"))
    )


if __name__ == "__main__":
    main()
